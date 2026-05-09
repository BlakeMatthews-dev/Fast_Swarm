"""
Tests for AgentLiveTradingService - the direct agent -> Crypto.com execution bridge.

Covers initialization, pattern evaluation, order placement, fill polling,
emergency exits, and error handling. All exchange API calls are mocked.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from Fast_Swarm.Trading.Services.agent_live_trading_service import AgentLiveTradingService


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service():
    """Create a service with fake credentials."""
    svc = AgentLiveTradingService(
        api_key="test-key",
        api_secret="test-secret",
        use_sandbox=True,
    )
    return svc


@pytest.fixture
def mock_client():
    """Create a fully-mocked CryptoComRESTClient."""
    client = AsyncMock()
    client.get_account_balance = AsyncMock(return_value={"USD": 10000.0})
    client.get_positions = AsyncMock(return_value=[])
    client.place_limit_order = AsyncMock(return_value={
        "order_id": "ord-123",
        "client_oid": "c-123",
        "symbol": "BTCUSD-PERP",
        "side": "buy",
        "size": 0.01,
        "price": 50050.0,
        "status": "submitted",
        "commission": 0,
    })
    client.place_market_order = AsyncMock(return_value={
        "order_id": "ord-mkt-456",
        "symbol": "BTCUSD-PERP",
        "side": "sell",
        "size": 0.01,
        "price": 49900.0,
        "status": "filled",
        "commission": 0,
    })
    client.get_order_status = AsyncMock(return_value={
        "order_id": "ord-123",
        "symbol": "BTCUSD-PERP",
        "side": "buy",
        "status": "filled",
        "size": 0.01,
        "filled_size": 0.01,
        "avg_price": 50050.0,
        "commission": 0.5,
    })
    client.cancel_order = AsyncMock(return_value=True)
    client.cancel_all_orders = AsyncMock(return_value=1)
    client.close = AsyncMock()
    return client


@pytest.fixture
def initialized_service(service, mock_client):
    """Service with mock client already injected."""
    service._client = mock_client
    service._initialized = True
    return service


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    # exec returns a mock result whose .first() returns an agent
    mock_result = MagicMock()
    mock_agent = MagicMock()
    mock_agent.agent_id = "agent-001"
    mock_agent.name = "TestAgent"
    mock_agent.status = "active"
    mock_agent.traits = {"kelly_fraction": 0.1, "risk_tolerance": 0.5}
    mock_agent.assigned_patterns = {
        "pat-1": {
            "entry_conditions": {"rsi": {"operator": "<", "value": 30}},
            "exit_conditions": {"rsi": {"operator": ">", "value": 70}},
            "direction": "long",
        }
    }
    mock_agent.pattern_weights = {"pat-1": 1.0}
    mock_result.first.return_value = mock_agent
    session.exec = AsyncMock(return_value=mock_result)
    return session


@pytest.fixture
def sample_candle_data():
    """Sample candle data with indicators."""
    return {
        "open": 50000.0,
        "high": 50500.0,
        "low": 49500.0,
        "close": 50200.0,
        "volume": 1000.0,
        "rsi": 25.0,
        "volume_ratio": 1.8,
        "defensive_trigger": 0,
    }


# =============================================================================
# Init Tests (~4 tests)
# =============================================================================


class TestInit:
    """Test service initialization."""

    @pytest.mark.asyncio
    async def test_init_with_credentials(self, service):
        """Service stores credentials from constructor."""
        assert service.api_key == "test-key"
        assert service.api_secret == "test-secret"
        assert service.use_sandbox is True

    @pytest.mark.asyncio
    async def test_init_without_credentials(self):
        """Service falls back to env vars when no creds provided."""
        with patch.dict("os.environ", {"CRYPTOCOM_API_KEY": "", "CRYPTOCOM_API_SECRET": ""}, clear=False):
            svc = AgentLiveTradingService()
            result = await svc.initialize()
            assert result is False

    @pytest.mark.asyncio
    async def test_initialize_creates_client(self):
        """Successful initialize creates exchange client."""
        svc = AgentLiveTradingService(api_key="k", api_secret="s", use_sandbox=True)
        with patch(
            "Fast_Swarm.Trading.Services.agent_live_trading_service.create_cryptocom_client"
        ) as mock_create:
            mock_create.return_value = AsyncMock()
            result = await svc.initialize()
            assert result is True
            assert svc.is_ready() is True
            mock_create.assert_called_once_with(api_key="k", api_secret="s", use_sandbox=True)

    @pytest.mark.asyncio
    async def test_initialize_handles_exception(self):
        """Initialize returns False on client creation error."""
        svc = AgentLiveTradingService(api_key="k", api_secret="s")
        with patch(
            "Fast_Swarm.Trading.Services.agent_live_trading_service.create_cryptocom_client",
            side_effect=RuntimeError("connection refused"),
        ):
            result = await svc.initialize()
            assert result is False
            assert svc.is_ready() is False


# =============================================================================
# Evaluate Tests (~8 tests)
# =============================================================================


class TestEvaluate:
    """Test pattern evaluation and signal generation."""

    @pytest.mark.asyncio
    async def test_evaluate_returns_none_if_agent_not_active(
        self, initialized_service, mock_session, sample_candle_data
    ):
        """evaluate_and_execute returns None if agent is not in active_agents."""
        result = await initialized_service.evaluate_and_execute(
            mock_session, "nonexistent-agent", "BTC-USDT", 50000.0, sample_candle_data
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_returns_none_when_paused(
        self, initialized_service, mock_session, sample_candle_data
    ):
        """No action when agent is paused."""
        initialized_service.active_agents["agent-001"] = {
            "agent_id": "agent-001",
            "agent_name": "Test",
            "symbols": ["BTC-USDT"],
            "positions": {},
            "open_orders": {},
            "started_at": datetime.now(timezone.utc),
            "trades_count": 0,
            "total_pnl": 0.0,
            "paused": True,
            "max_position_pct": 0.25,
            "max_daily_trades": 10,
            "daily_trades": 0,
            "daily_reset": datetime.now(timezone.utc).date(),
        }
        result = await initialized_service.evaluate_and_execute(
            mock_session, "agent-001", "BTC-USDT", 50000.0, sample_candle_data
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_respects_daily_trade_limit(
        self, initialized_service, mock_session, sample_candle_data
    ):
        """No action when daily trade limit reached."""
        initialized_service.active_agents["agent-001"] = {
            "agent_id": "agent-001",
            "agent_name": "Test",
            "symbols": ["BTC-USDT"],
            "positions": {},
            "open_orders": {},
            "started_at": datetime.now(timezone.utc),
            "trades_count": 10,
            "total_pnl": 0.0,
            "paused": False,
            "max_position_pct": 0.25,
            "max_daily_trades": 10,
            "daily_trades": 10,
            "daily_reset": datetime.now(timezone.utc).date(),
        }
        result = await initialized_service.evaluate_and_execute(
            mock_session, "agent-001", "BTC-USDT", 50000.0, sample_candle_data
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_hold_signal_returns_none(
        self, initialized_service, mock_session
    ):
        """Hold signal produces no action."""
        initialized_service.active_agents["agent-001"] = {
            "agent_id": "agent-001",
            "agent_name": "Test",
            "symbols": ["BTC-USDT"],
            "positions": {},
            "open_orders": {},
            "started_at": datetime.now(timezone.utc),
            "trades_count": 0,
            "total_pnl": 0.0,
            "paused": False,
            "max_position_pct": 0.25,
            "max_daily_trades": 10,
            "daily_trades": 0,
            "daily_reset": datetime.now(timezone.utc).date(),
        }
        with patch.object(initialized_service, "_evaluate_patterns", return_value="hold"):
            result = await initialized_service.evaluate_and_execute(
                mock_session, "agent-001", "BTC-USDT", 50000.0, {"defensive_trigger": 0}
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_defensive_trigger_closes_existing_position(
        self, initialized_service, mock_session
    ):
        """DEFENSIVE trigger force-closes an open position via market order."""
        initialized_service.active_agents["agent-001"] = {
            "agent_id": "agent-001",
            "agent_name": "Test",
            "symbols": ["BTC-USDT"],
            "positions": {
                "BTC-USDT": {
                    "trade_id": "trade-abc",
                    "side": "long",
                    "size": 0.01,
                    "entry_price": 49000.0,
                    "size_usd": 490.0,
                    "entry_time": datetime.now(timezone.utc),
                }
            },
            "open_orders": {},
            "started_at": datetime.now(timezone.utc),
            "trades_count": 1,
            "total_pnl": 0.0,
            "paused": False,
            "max_position_pct": 0.25,
            "max_daily_trades": 10,
            "daily_trades": 1,
            "daily_reset": datetime.now(timezone.utc).date(),
        }
        candle = {"defensive_trigger": 1}
        result = await initialized_service.evaluate_and_execute(
            mock_session, "agent-001", "BTC-USDT", 50000.0, candle
        )
        assert result is not None
        assert result.get("action") in ("emergency_closed", "emergency_close_failed")

    @pytest.mark.asyncio
    async def test_defensive_trigger_blocks_new_entry(
        self, initialized_service, mock_session
    ):
        """DEFENSIVE trigger without position blocks new entries."""
        initialized_service.active_agents["agent-001"] = {
            "agent_id": "agent-001",
            "agent_name": "Test",
            "symbols": ["BTC-USDT"],
            "positions": {},
            "open_orders": {},
            "started_at": datetime.now(timezone.utc),
            "trades_count": 0,
            "total_pnl": 0.0,
            "paused": False,
            "max_position_pct": 0.25,
            "max_daily_trades": 10,
            "daily_trades": 0,
            "daily_reset": datetime.now(timezone.utc).date(),
        }
        candle = {"defensive_trigger": 1}
        result = await initialized_service.evaluate_and_execute(
            mock_session, "agent-001", "BTC-USDT", 50000.0, candle
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_patterns_returns_hold_without_patterns(self, initialized_service):
        """Agent with no assigned patterns returns hold."""
        agent = MagicMock()
        agent.assigned_patterns = None
        result = await initialized_service._evaluate_patterns(agent, {})
        assert result == "hold"

    @pytest.mark.asyncio
    async def test_evaluate_patterns_returns_hold_with_empty_patterns(self, initialized_service):
        """Agent with empty assigned_patterns returns hold."""
        agent = MagicMock()
        agent.assigned_patterns = {}
        result = await initialized_service._evaluate_patterns(agent, {})
        assert result == "hold"


# =============================================================================
# Order Placement Tests (~8 tests)
# =============================================================================


class TestOrderPlacement:
    """Test order placement through the exchange API."""

    def _setup_agent(self, service, agent_id="agent-001"):
        """Helper to register an active agent."""
        service.active_agents[agent_id] = {
            "agent_id": agent_id,
            "agent_name": "Test",
            "symbols": ["BTC-USDT"],
            "positions": {},
            "open_orders": {},
            "started_at": datetime.now(timezone.utc),
            "trades_count": 0,
            "total_pnl": 0.0,
            "paused": False,
            "max_position_pct": 0.25,
            "max_daily_trades": 10,
            "daily_trades": 0,
            "daily_reset": datetime.now(timezone.utc).date(),
        }

    @pytest.mark.asyncio
    async def test_place_entry_order_long(self, initialized_service, mock_session, mock_client):
        """Placing a long entry order calls place_limit_order with buy side."""
        self._setup_agent(initialized_service)
        mock_client.get_account_balance.return_value = {"USD": 10000.0}
        agent = MagicMock()
        agent.agent_id = "agent-001"
        agent.traits = {"kelly_fraction": 0.1}
        agent.pattern_weights = {}

        result = await initialized_service._place_entry_order(
            mock_session, agent, "BTC-USDT", "long", 50000.0, {}, "bull"
        )
        assert result["action"] == "order_placed"
        assert result["side"] == "long"
        mock_client.place_limit_order.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_place_entry_order_short(self, initialized_service, mock_session, mock_client):
        """Placing a short entry order uses sell side."""
        self._setup_agent(initialized_service)
        mock_client.get_account_balance.return_value = {"USD": 10000.0}
        agent = MagicMock()
        agent.agent_id = "agent-001"
        agent.traits = {"kelly_fraction": 0.1}
        agent.pattern_weights = {}

        result = await initialized_service._place_entry_order(
            mock_session, agent, "BTC-USDT", "short", 50000.0, {}, "bear"
        )
        assert result["action"] == "order_placed"
        assert result["side"] == "short"

    @pytest.mark.asyncio
    async def test_place_entry_order_applies_buffer(self, initialized_service, mock_session, mock_client):
        """Long entry price includes 0.1% buffer above signal price."""
        self._setup_agent(initialized_service)
        mock_client.get_account_balance.return_value = {"USD": 10000.0}
        agent = MagicMock()
        agent.agent_id = "agent-001"
        agent.traits = {"kelly_fraction": 0.1}
        agent.pattern_weights = {}

        await initialized_service._place_entry_order(
            mock_session, agent, "BTC-USDT", "long", 50000.0, {}, "bull"
        )

        call_kwargs = mock_client.place_limit_order.call_args
        limit_price = call_kwargs.kwargs.get("price") or call_kwargs[1].get("price")
        expected = 50000.0 * (1 + 0.001)
        assert abs(limit_price - expected) < 0.01

    @pytest.mark.asyncio
    async def test_place_entry_order_respects_kelly_fraction(
        self, initialized_service, mock_session, mock_client
    ):
        """Position size derived from kelly_fraction of available balance."""
        self._setup_agent(initialized_service)
        mock_client.get_account_balance.return_value = {"USD": 20000.0}
        agent = MagicMock()
        agent.agent_id = "agent-001"
        agent.traits = {"kelly_fraction": 0.05}
        agent.pattern_weights = {}

        result = await initialized_service._place_entry_order(
            mock_session, agent, "BTC-USDT", "long", 50000.0, {}, "bull"
        )
        # kelly=0.05 of 20k = 1000 USD / 50000 = 0.02 BTC
        assert abs(result["size_usd"] - 1000.0) < 1.0

    @pytest.mark.asyncio
    async def test_place_entry_order_caps_at_max_position_pct(
        self, initialized_service, mock_session, mock_client
    ):
        """Position size capped at max_position_pct even if kelly is higher."""
        self._setup_agent(initialized_service)
        initialized_service.active_agents["agent-001"]["max_position_pct"] = 0.05
        mock_client.get_account_balance.return_value = {"USD": 10000.0}
        agent = MagicMock()
        agent.agent_id = "agent-001"
        agent.traits = {"kelly_fraction": 0.5}  # 50% kelly, but capped at 5%
        agent.pattern_weights = {}

        result = await initialized_service._place_entry_order(
            mock_session, agent, "BTC-USDT", "long", 50000.0, {}, "bull"
        )
        assert result["size_usd"] <= 10000.0 * 0.05 + 1.0

    @pytest.mark.asyncio
    async def test_place_entry_order_records_to_db(self, initialized_service, mock_session, mock_client):
        """Order placement records LiveTradeUnified to the database."""
        self._setup_agent(initialized_service)
        mock_client.get_account_balance.return_value = {"USD": 10000.0}
        agent = MagicMock()
        agent.agent_id = "agent-001"
        agent.traits = {"kelly_fraction": 0.1}
        agent.pattern_weights = {}

        await initialized_service._place_entry_order(
            mock_session, agent, "BTC-USDT", "long", 50000.0, {}, "bull"
        )
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_place_entry_order_handles_exchange_error(
        self, initialized_service, mock_session, mock_client
    ):
        """Exchange error returns error dict without crashing."""
        self._setup_agent(initialized_service)
        mock_client.get_account_balance.return_value = {"USD": 10000.0}
        mock_client.place_limit_order.return_value = {
            "error": "10006",
            "message": "Insufficient balance",
        }
        agent = MagicMock()
        agent.agent_id = "agent-001"
        agent.traits = {"kelly_fraction": 0.1}
        agent.pattern_weights = {}

        result = await initialized_service._place_entry_order(
            mock_session, agent, "BTC-USDT", "long", 50000.0, {}, "bull"
        )
        assert result["action"] == "order_failed"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_place_entry_order_zero_balance(
        self, initialized_service, mock_session, mock_client
    ):
        """Zero balance returns error."""
        self._setup_agent(initialized_service)
        mock_client.get_account_balance.return_value = {"USD": 0.0}
        agent = MagicMock()
        agent.agent_id = "agent-001"
        agent.traits = {"kelly_fraction": 0.1}
        agent.pattern_weights = {}

        result = await initialized_service._place_entry_order(
            mock_session, agent, "BTC-USDT", "long", 50000.0, {}, "bull"
        )
        assert "error" in result


# =============================================================================
# Fill Polling Tests (~5 tests)
# =============================================================================


class TestFillPolling:
    """Test order fill status polling."""

    def _setup_agent_with_order(self, service, agent_id="agent-001"):
        """Helper to set up an agent with a pending open order."""
        service.active_agents[agent_id] = {
            "agent_id": agent_id,
            "agent_name": "Test",
            "symbols": ["BTC-USDT"],
            "positions": {},
            "open_orders": {
                "ord-123": {
                    "order_id": "ord-123",
                    "trade_id": "trade-abc",
                    "symbol": "BTC-USDT",
                    "side": "long",
                    "signal_price": 50000.0,
                    "limit_price": 50050.0,
                    "size": 0.01,
                    "size_usd": 500.0,
                    "regime": "bull",
                    "placed_at": datetime.now(timezone.utc),
                }
            },
            "started_at": datetime.now(timezone.utc),
            "trades_count": 0,
            "total_pnl": 0.0,
            "paused": False,
            "max_position_pct": 0.25,
            "max_daily_trades": 10,
            "daily_trades": 0,
            "daily_reset": datetime.now(timezone.utc).date(),
        }

    @pytest.mark.asyncio
    async def test_check_fills_detects_filled_order(
        self, initialized_service, mock_session, mock_client
    ):
        """Filled order is detected and processed."""
        self._setup_agent_with_order(initialized_service)
        mock_client.get_order_status.return_value = {
            "order_id": "ord-123",
            "status": "filled",
            "avg_price": 50045.0,
            "filled_size": 0.01,
        }

        events = await initialized_service.check_order_fills(mock_session)
        assert len(events) >= 1

    @pytest.mark.asyncio
    async def test_check_fills_handles_cancelled_order(
        self, initialized_service, mock_session, mock_client
    ):
        """Cancelled orders are removed from tracking."""
        self._setup_agent_with_order(initialized_service)
        mock_client.get_order_status.return_value = {
            "order_id": "ord-123",
            "status": "cancelled",
        }

        events = await initialized_service.check_order_fills(mock_session)
        assert any(e.get("action") == "order_cancelled" for e in events)

    @pytest.mark.asyncio
    async def test_check_fills_handles_api_error(
        self, initialized_service, mock_session, mock_client
    ):
        """API error on status check is handled gracefully."""
        self._setup_agent_with_order(initialized_service)
        mock_client.get_order_status.return_value = {
            "error": "timeout",
            "message": "Connection timeout",
        }

        events = await initialized_service.check_order_fills(mock_session)
        # Should not crash, may return empty events
        assert isinstance(events, list)

    @pytest.mark.asyncio
    async def test_check_fills_timeout_cancels_stale_order(
        self, initialized_service, mock_session, mock_client
    ):
        """Orders older than ORDER_TIMEOUT are cancelled."""
        from datetime import timedelta

        self._setup_agent_with_order(initialized_service)
        # Make the order appear old
        agent_info = initialized_service.active_agents["agent-001"]
        agent_info["open_orders"]["ord-123"]["placed_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=400)
        )
        mock_client.get_order_status.return_value = {
            "order_id": "ord-123",
            "status": "pending",
        }

        events = await initialized_service.check_order_fills(mock_session)
        # Should attempt to cancel the stale order
        mock_client.cancel_order.assert_awaited()

    @pytest.mark.asyncio
    async def test_check_fills_no_agents_returns_empty(
        self, initialized_service, mock_session
    ):
        """No active agents means no events."""
        events = await initialized_service.check_order_fills(mock_session)
        assert events == []


# =============================================================================
# Emergency Exit Tests (~5 tests)
# =============================================================================


class TestEmergencyExit:
    """Test emergency position closing."""

    def _setup_agent_with_position(self, service, agent_id="agent-001"):
        """Helper to create agent with open position."""
        service.active_agents[agent_id] = {
            "agent_id": agent_id,
            "agent_name": "Test",
            "symbols": ["BTC-USDT"],
            "positions": {
                "BTC-USDT": {
                    "trade_id": "trade-abc",
                    "side": "long",
                    "size": 0.01,
                    "entry_price": 49000.0,
                    "size_usd": 490.0,
                    "entry_time": datetime.now(timezone.utc),
                }
            },
            "open_orders": {},
            "started_at": datetime.now(timezone.utc),
            "trades_count": 1,
            "total_pnl": 0.0,
            "paused": False,
            "max_position_pct": 0.25,
            "max_daily_trades": 10,
            "daily_trades": 1,
            "daily_reset": datetime.now(timezone.utc).date(),
        }

    @pytest.mark.asyncio
    async def test_emergency_close_uses_market_order(
        self, initialized_service, mock_session, mock_client
    ):
        """Emergency close places a market order (not limit)."""
        self._setup_agent_with_position(initialized_service)
        result = await initialized_service._emergency_close(
            mock_session, "agent-001", "BTC-USDT", 50000.0, "defensive_regime"
        )
        mock_client.place_market_order.assert_awaited_once()
        assert result["action"] == "emergency_closed"

    @pytest.mark.asyncio
    async def test_emergency_close_calculates_pnl(
        self, initialized_service, mock_session, mock_client
    ):
        """Emergency close calculates P&L correctly."""
        self._setup_agent_with_position(initialized_service)
        mock_client.place_market_order.return_value = {
            "order_id": "ord-emg",
            "price": 51000.0,
            "status": "filled",
        }
        result = await initialized_service._emergency_close(
            mock_session, "agent-001", "BTC-USDT", 51000.0, "take_profit"
        )
        # Entry at 49000, exit at 51000 for long = ~4.08% profit
        assert result["pnl_pct"] > 0

    @pytest.mark.asyncio
    async def test_emergency_close_removes_position(
        self, initialized_service, mock_session, mock_client
    ):
        """After emergency close, position is removed from tracking."""
        self._setup_agent_with_position(initialized_service)
        await initialized_service._emergency_close(
            mock_session, "agent-001", "BTC-USDT", 50000.0, "stop_loss"
        )
        assert "BTC-USDT" not in initialized_service.active_agents["agent-001"]["positions"]

    @pytest.mark.asyncio
    async def test_emergency_close_no_position(
        self, initialized_service, mock_session, mock_client
    ):
        """Emergency close with no position returns error."""
        initialized_service.active_agents["agent-001"] = {
            "agent_id": "agent-001",
            "agent_name": "Test",
            "symbols": ["BTC-USDT"],
            "positions": {},
            "open_orders": {},
            "started_at": datetime.now(timezone.utc),
            "trades_count": 0,
            "total_pnl": 0.0,
            "paused": False,
            "max_position_pct": 0.25,
            "max_daily_trades": 10,
            "daily_trades": 0,
            "daily_reset": datetime.now(timezone.utc).date(),
        }
        result = await initialized_service._emergency_close(
            mock_session, "agent-001", "BTC-USDT", 50000.0, "defensive"
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_emergency_close_exchange_failure(
        self, initialized_service, mock_session, mock_client
    ):
        """Exchange failure on emergency close returns failure action."""
        self._setup_agent_with_position(initialized_service)
        mock_client.place_market_order.return_value = {
            "error": "exchange_down",
            "message": "Exchange maintenance",
        }
        result = await initialized_service._emergency_close(
            mock_session, "agent-001", "BTC-USDT", 50000.0, "defensive"
        )
        assert result["action"] == "emergency_close_failed"


# =============================================================================
# Error Handling Tests (~5 tests)
# =============================================================================


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_close_cleans_up_client(self, initialized_service, mock_client):
        """close() disposes client and resets state."""
        await initialized_service.close()
        mock_client.close.assert_awaited_once()
        assert initialized_service.is_ready() is False
        assert initialized_service._client is None

    @pytest.mark.asyncio
    async def test_is_ready_false_before_init(self, service):
        """is_ready is False before initialization."""
        assert service.is_ready() is False

    @pytest.mark.asyncio
    async def test_start_live_trading_requires_init(self, service, mock_session):
        """start_live_trading fails if service not initialized."""
        result = await service.start_live_trading(mock_session, "agent-001")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_stop_live_trading_unknown_agent(self, initialized_service):
        """Stopping a non-trading agent returns error."""
        result = await initialized_service.stop_live_trading("nonexistent")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_symbol_conversion(self, initialized_service):
        """_convert_symbol maps BTC-USDT to BTCUSD-PERP."""
        result = initialized_service._convert_symbol("BTC-USDT")
        assert result == "BTCUSD-PERP"
        result2 = initialized_service._convert_symbol("ETH-USDT")
        assert result2 == "ETHUSD-PERP"
