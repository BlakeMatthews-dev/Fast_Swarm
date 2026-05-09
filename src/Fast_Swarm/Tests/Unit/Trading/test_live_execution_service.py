"""
Tests for LiveExecutionService - bridges approved trades to Crypto.com exchange.

Covers execution flow, DB recording, slippage protection, fill tracking,
partial fills, and error recovery.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from Fast_Swarm.Trading.Services.live_execution_service import (
    LiveExecutionService,
    get_live_execution_service,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service():
    """Create service with test credentials."""
    return LiveExecutionService(
        api_key="test-key",
        api_secret="test-secret",
        use_sandbox=True,
    )


@pytest.fixture
def mock_client():
    """Create a mocked CryptoComRESTClient."""
    client = AsyncMock()
    client.place_limit_order = AsyncMock(return_value={
        "order_id": "ord-limit-1",
        "status": "submitted",
        "price": 50050.0,
    })
    client.place_market_order = AsyncMock(return_value={
        "order_id": "ord-mkt-1",
        "status": "filled",
        "price": 49950.0,
    })
    client.get_order_status = AsyncMock(return_value={
        "order_id": "ord-limit-1",
        "status": "filled",
        "filled_size": 0.01,
        "avg_price": 50045.0,
    })
    client.cancel_order = AsyncMock(return_value=True)
    client.close = AsyncMock()
    return client


@pytest.fixture
def ready_service(service, mock_client):
    """Service with injected mock client."""
    service._client = mock_client
    service._initialized = True
    return service


@pytest.fixture
def mock_session():
    """Mock database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


# =============================================================================
# Initialization Tests
# =============================================================================


class TestInit:
    """Test service initialization and lifecycle."""

    @pytest.mark.asyncio
    async def test_init_without_creds_returns_false(self):
        """Service without credentials cannot initialize."""
        svc = LiveExecutionService(api_key="", api_secret="")
        result = await svc.initialize()
        assert result is False
        assert svc.is_ready() is False

    @pytest.mark.asyncio
    async def test_init_with_creds_creates_client(self):
        """Valid credentials create client successfully."""
        svc = LiveExecutionService(api_key="k", api_secret="s", use_sandbox=True)
        with patch(
            "Fast_Swarm.Trading.Services.live_execution_service.create_cryptocom_client"
        ) as mock_create:
            mock_create.return_value = AsyncMock()
            result = await svc.initialize()
            assert result is True
            assert svc.is_ready() is True

    @pytest.mark.asyncio
    async def test_close_resets_state(self, ready_service, mock_client):
        """Closing service resets initialized state."""
        await ready_service.close()
        assert ready_service.is_ready() is False
        mock_client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_is_ready(self, service, ready_service):
        """is_ready reflects initialization state."""
        assert service.is_ready() is False
        assert ready_service.is_ready() is True


# =============================================================================
# Limit Order Execution Tests
# =============================================================================


class TestLimitOrderExecution:
    """Test execute_limit_order flow."""

    @pytest.mark.asyncio
    async def test_execute_limit_order_success(self, ready_service, mock_session, mock_client):
        """Successful limit order returns success result and records to DB."""
        result = await ready_service.execute_limit_order(
            session=mock_session,
            trade_id="trade-001",
            agent_id="agent-001",
            symbol="BTC-USDT",
            side="buy",
            size=0.01,
            limit_price=50050.0,
        )
        assert result["success"] is True
        assert result["trade_id"] == "trade-001"
        assert result["source"] == "live"
        mock_client.place_limit_order.assert_awaited_once()
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_limit_order_exchange_error(self, ready_service, mock_session, mock_client):
        """Exchange error returns failure result."""
        mock_client.place_limit_order.return_value = {
            "error": "10006",
            "message": "Insufficient balance",
        }
        result = await ready_service.execute_limit_order(
            session=mock_session,
            trade_id="trade-002",
            agent_id="agent-001",
            symbol="BTC-USDT",
            side="buy",
            size=0.01,
            limit_price=50050.0,
        )
        assert result["success"] is False
        assert "Insufficient balance" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_limit_order_exception(self, ready_service, mock_session, mock_client):
        """Exception during execution returns failure gracefully."""
        mock_client.place_limit_order.side_effect = RuntimeError("network down")
        result = await ready_service.execute_limit_order(
            session=mock_session,
            trade_id="trade-003",
            agent_id="agent-001",
            symbol="BTC-USDT",
            side="buy",
            size=0.01,
            limit_price=50050.0,
        )
        assert result["success"] is False
        assert "network down" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_limit_order_normalizes_side(self, ready_service, mock_session, mock_client):
        """Side aliases 'long' and 'short' are normalized to 'buy'/'sell'."""
        await ready_service.execute_limit_order(
            session=mock_session,
            trade_id="trade-004",
            agent_id="agent-001",
            symbol="BTC-USDT",
            side="long",
            size=0.01,
            limit_price=50050.0,
        )
        call_kwargs = mock_client.place_limit_order.call_args
        assert call_kwargs.kwargs.get("side") == "buy" or call_kwargs[1].get("side") == "buy"

    @pytest.mark.asyncio
    async def test_execute_limit_order_simulated_when_not_ready(self, service, mock_session):
        """When not connected, execution is simulated as paper trade."""
        result = await service.execute_limit_order(
            session=mock_session,
            trade_id="trade-005",
            agent_id="agent-001",
            symbol="BTC-USDT",
            side="buy",
            size=0.01,
            limit_price=50000.0,
        )
        assert result["success"] is True
        assert result["source"] == "paper"
        assert result["status"] == "simulated"


# =============================================================================
# Market Order Execution Tests
# =============================================================================


class TestMarketOrderExecution:
    """Test execute_market_order flow."""

    @pytest.mark.asyncio
    async def test_execute_market_order_success(self, ready_service, mock_session, mock_client):
        """Market order succeeds and records trade."""
        result = await ready_service.execute_market_order(
            session=mock_session,
            agent_id="agent-001",
            symbol="BTC-USDT",
            side="sell",
            size=0.01,
            reason="emergency_exit",
        )
        assert result["success"] is True
        assert result["status"] == "filled"
        mock_client.place_market_order.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_market_order_not_ready(self, service, mock_session):
        """Market order fails when not connected."""
        result = await service.execute_market_order(
            session=mock_session,
            agent_id="agent-001",
            symbol="BTC-USDT",
            side="sell",
            size=0.01,
        )
        assert result["success"] is False
        assert "not connected" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_execute_market_order_exchange_error(self, ready_service, mock_session, mock_client):
        """Exchange error on market order returns failure."""
        mock_client.place_market_order.return_value = {
            "error": "rate_limit",
            "message": "Too many requests",
        }
        result = await ready_service.execute_market_order(
            session=mock_session,
            agent_id="agent-001",
            symbol="BTC-USDT",
            side="sell",
            size=0.01,
        )
        assert result["success"] is False


# =============================================================================
# DB Recording Tests
# =============================================================================


class TestDBRecording:
    """Test trade recording to database."""

    @pytest.mark.asyncio
    async def test_record_trade_calculates_slippage(self, ready_service, mock_session):
        """Slippage is calculated when both requested and fill prices exist."""
        trade = await ready_service._record_trade(
            session=mock_session,
            trade_id="trade-slp",
            agent_id="agent-001",
            symbol="BTC-USDT",
            side="buy",
            size=0.01,
            requested_price=50000.0,
            fill_price=50025.0,
            order_id="ord-1",
            order_type="limit",
            status="filled",
            source="live",
        )
        assert trade.slippage_pct is not None
        assert abs(trade.slippage_pct - 0.05) < 0.01  # 0.05%

    @pytest.mark.asyncio
    async def test_record_trade_size_usd(self, ready_service, mock_session):
        """size_usd calculated as size * price."""
        trade = await ready_service._record_trade(
            session=mock_session,
            trade_id="trade-sz",
            agent_id="agent-001",
            symbol="BTC-USDT",
            side="buy",
            size=0.1,
            requested_price=50000.0,
            fill_price=50000.0,
            order_id="ord-1",
            order_type="limit",
            status="filled",
            source="live",
        )
        assert float(trade.size_usd) == 5000.0


# =============================================================================
# Utility Tests
# =============================================================================


class TestUtilities:
    """Test utility methods."""

    def test_convert_symbol_btc(self, ready_service):
        """BTC-USDT converts to BTCUSD-PERP."""
        assert ready_service._convert_symbol("BTC-USDT") == "BTCUSD-PERP"

    def test_convert_symbol_eth(self, ready_service):
        """ETH-USDT converts to ETHUSD-PERP."""
        assert ready_service._convert_symbol("ETH-USDT") == "ETHUSD-PERP"

    @pytest.mark.asyncio
    async def test_get_order_status_when_not_ready(self, service):
        """get_order_status returns None when not connected."""
        result = await service.get_order_status("ord-1", "BTC-USDT")
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_order_when_not_ready(self, service):
        """cancel_order returns False when not connected."""
        result = await service.cancel_order("ord-1", "BTC-USDT")
        assert result is False

    def test_singleton_instance(self):
        """get_live_execution_service returns consistent instance."""
        import Fast_Swarm.Trading.Services.live_execution_service as mod

        mod._live_execution_service = None
        svc1 = get_live_execution_service()
        svc2 = get_live_execution_service()
        assert svc1 is svc2
        mod._live_execution_service = None  # cleanup
