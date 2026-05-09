"""
Tests for PortfolioAgentService - dedicated agent per exchange for position management.

Covers position tracking, risk limits, rebalancing, PaperTradingClient,
order execution, and edge cases.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from Fast_Swarm.Agents.Hivemind.Services.portfolio_agent_service import (
    ALLOWED_CLOSE_FRACTIONS,
    ExchangeClient,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperTradingClient,
    PortfolioAgent,
    PortfolioState,
    Position,
    PositionSide,
    RiskLimits,
    TradeCommand,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def paper_client():
    """Create a PaperTradingClient with default settings."""
    client = PaperTradingClient(initial_balance=100000.0, slippage_bps=5.0, fee_bps=10.0)
    client.set_price("BTCUSD-PERP", 50000.0)
    client.set_price("ETHUSD-PERP", 3000.0)
    return client


@pytest.fixture
def mock_exchange():
    """Create a fully mocked exchange client."""
    client = AsyncMock(spec=ExchangeClient)
    client.get_account_balance = AsyncMock(return_value={"USD": 100000.0, "BTC": 1.0})
    client.get_positions = AsyncMock(return_value=[])
    client.place_market_order = AsyncMock(return_value={
        "order_id": "ord-1",
        "symbol": "BTCUSD-PERP",
        "side": "buy",
        "size": 0.1,
        "price": 50010.0,
        "status": "filled",
        "commission": 0.5,
    })
    client.place_limit_order = AsyncMock(return_value={
        "order_id": "ord-lim-1",
        "symbol": "BTCUSD-PERP",
        "side": "buy",
        "size": 0.1,
        "price": 50000.0,
        "status": "pending",
    })
    client.cancel_order = AsyncMock(return_value=True)
    client.get_order_status = AsyncMock(return_value={
        "order_id": "ord-1",
        "status": "filled",
        "filled_size": 0.1,
        "avg_price": 50010.0,
    })
    client.get_ticker = AsyncMock(return_value={
        "symbol": "BTCUSD-PERP",
        "price": 50000.0,
        "bid": 49999.0,
        "ask": 50001.0,
    })
    return client


@pytest.fixture
def agent(mock_exchange):
    """Create a PortfolioAgent with mocked exchange."""
    return PortfolioAgent(
        exchange_name="test-exchange",
        client=mock_exchange,
        risk_limits=RiskLimits(
            max_position_pct=0.10,
            max_total_exposure_pct=0.50,
            max_daily_loss_pct=0.05,
            max_order_size_usd=10000.0,
            min_order_size_usd=10.0,
        ),
    )


def _make_command(
    symbol="BTCUSD-PERP",
    side=OrderSide.BUY,
    size_pct=0.05,
    order_type=OrderType.MARKET,
    **kwargs,
):
    """Helper to create a TradeCommand."""
    return TradeCommand(
        command_id=str(uuid.uuid4())[:8],
        trio_id="trio-1",
        symbol=symbol,
        side=side,
        size_pct=size_pct,
        order_type=order_type,
        **kwargs,
    )


# =============================================================================
# PaperTradingClient - Position Tracking (~6 tests)
# =============================================================================


class TestPaperTradingPositions:
    """Test PaperTradingClient position tracking."""

    @pytest.mark.asyncio
    async def test_market_buy_creates_position(self, paper_client):
        """Buying creates a long position."""
        result = await paper_client.place_market_order("BTCUSD-PERP", "buy", 0.1)
        assert "error" not in result
        assert "BTCUSD-PERP" in paper_client.positions
        assert paper_client.positions["BTCUSD-PERP"]["side"] == "long"

    @pytest.mark.asyncio
    async def test_market_sell_closes_position(self, paper_client):
        """Selling full size closes the position."""
        await paper_client.place_market_order("BTCUSD-PERP", "buy", 0.1)
        await paper_client.place_market_order("BTCUSD-PERP", "sell", 0.1)
        assert "BTCUSD-PERP" not in paper_client.positions

    @pytest.mark.asyncio
    async def test_averaging_in_updates_entry_price(self, paper_client):
        """Adding to position updates average entry price."""
        await paper_client.place_market_order("BTCUSD-PERP", "buy", 0.1)
        entry1 = paper_client.positions["BTCUSD-PERP"]["entry_price"]

        paper_client.set_price("BTCUSD-PERP", 52000.0)
        await paper_client.place_market_order("BTCUSD-PERP", "buy", 0.1)

        entry2 = paper_client.positions["BTCUSD-PERP"]["entry_price"]
        # Average should be between 50000 and 52000
        assert entry1 < entry2 < 52000.0
        assert paper_client.positions["BTCUSD-PERP"]["size"] == pytest.approx(0.2, abs=0.001)

    @pytest.mark.asyncio
    async def test_sell_without_position_fails(self, paper_client):
        """Selling without a position returns error."""
        result = await paper_client.place_market_order("BTCUSD-PERP", "sell", 0.1)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_sell_more_than_position_fails(self, paper_client):
        """Selling more than position size returns error."""
        await paper_client.place_market_order("BTCUSD-PERP", "buy", 0.1)
        result = await paper_client.place_market_order("BTCUSD-PERP", "sell", 0.5)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_no_price_returns_error(self, paper_client):
        """Attempting trade on unknown symbol fails."""
        result = await paper_client.place_market_order("UNKNOWNCOIN-PERP", "buy", 0.1)
        assert "error" in result


# =============================================================================
# PaperTradingClient - Balance Tracking (~4 tests)
# =============================================================================


class TestPaperTradingBalance:
    """Test PaperTradingClient balance management."""

    @pytest.mark.asyncio
    async def test_buy_deducts_balance(self, paper_client):
        """Buying deducts from USD balance."""
        initial = paper_client.balance["USD"]
        await paper_client.place_market_order("BTCUSD-PERP", "buy", 0.1)
        assert paper_client.balance["USD"] < initial

    @pytest.mark.asyncio
    async def test_sell_adds_balance(self, paper_client):
        """Selling adds proceeds to USD balance."""
        await paper_client.place_market_order("BTCUSD-PERP", "buy", 0.1)
        after_buy = paper_client.balance["USD"]
        await paper_client.place_market_order("BTCUSD-PERP", "sell", 0.1)
        assert paper_client.balance["USD"] > after_buy

    @pytest.mark.asyncio
    async def test_insufficient_funds(self, paper_client):
        """Buying more than balance allows returns error."""
        # Try to buy 100 BTC at 50k = $5M, only have $100k
        result = await paper_client.place_market_order("BTCUSD-PERP", "buy", 100.0)
        assert "error" in result
        assert result["error"] == "insufficient_funds"

    @pytest.mark.asyncio
    async def test_get_balance(self, paper_client):
        """get_account_balance returns current balance."""
        balance = await paper_client.get_account_balance()
        assert balance["USD"] == 100000.0


# =============================================================================
# PaperTradingClient - Partial Closes (~4 tests)
# =============================================================================


class TestPaperTradingPartialClose:
    """Test partial position closing."""

    @pytest.mark.asyncio
    async def test_partial_close_25_percent(self, paper_client):
        """25% partial close reduces position by 1/4."""
        await paper_client.place_market_order("BTCUSD-PERP", "buy", 1.0)
        result = await paper_client.close_position_partial("BTCUSD-PERP", 0.25)
        assert "error" not in result
        assert paper_client.positions["BTCUSD-PERP"]["size"] == pytest.approx(0.75, abs=0.01)

    @pytest.mark.asyncio
    async def test_partial_close_full(self, paper_client):
        """100% partial close removes position entirely."""
        await paper_client.place_market_order("BTCUSD-PERP", "buy", 1.0)
        result = await paper_client.close_position_partial("BTCUSD-PERP", 1.00)
        assert "error" not in result
        assert "BTCUSD-PERP" not in paper_client.positions

    @pytest.mark.asyncio
    async def test_partial_close_invalid_fraction(self, paper_client):
        """Invalid fraction (e.g., 0.33) returns error."""
        await paper_client.place_market_order("BTCUSD-PERP", "buy", 1.0)
        result = await paper_client.close_position_partial("BTCUSD-PERP", 0.33)
        assert "error" in result
        assert result["error"] == "invalid_fraction"

    @pytest.mark.asyncio
    async def test_partial_close_no_position(self, paper_client):
        """Partial close on nonexistent position returns error."""
        result = await paper_client.close_position_partial("BTCUSD-PERP", 0.25)
        assert "error" in result


# =============================================================================
# PaperTradingClient - Limit Orders (~3 tests)
# =============================================================================


class TestPaperTradingLimitOrders:
    """Test limit order placement and pending order book."""

    @pytest.mark.asyncio
    async def test_limit_order_fills_immediately_when_favorable(self, paper_client):
        """Limit buy at or above current price fills as market order."""
        result = await paper_client.place_limit_order("BTCUSD-PERP", "buy", 0.1, 51000.0)
        assert result["status"] == "filled"

    @pytest.mark.asyncio
    async def test_limit_order_rests_when_not_fillable(self, paper_client):
        """Limit buy below market rests on book."""
        result = await paper_client.place_limit_order("BTCUSD-PERP", "buy", 0.1, 49000.0)
        assert result["status"] == "pending"
        assert result["order_id"] in paper_client.pending_orders

    @pytest.mark.asyncio
    async def test_cancel_order(self, paper_client):
        """Cancelling a pending order marks it cancelled."""
        result = await paper_client.place_limit_order("BTCUSD-PERP", "buy", 0.1, 49000.0)
        order_id = result["order_id"]
        cancelled = await paper_client.cancel_order(order_id, "BTCUSD-PERP")
        assert cancelled is True
        assert paper_client.orders[order_id]["status"] == "cancelled"


# =============================================================================
# PaperTradingClient - Trade History & Events (~3 tests)
# =============================================================================


class TestPaperTradingHistory:
    """Test trade history and event callbacks."""

    @pytest.mark.asyncio
    async def test_trade_history_recorded(self, paper_client):
        """Filled trades are recorded in trade_history."""
        await paper_client.place_market_order("BTCUSD-PERP", "buy", 0.1)
        history = paper_client.get_trade_history()
        assert len(history) == 1
        assert history[0]["symbol"] == "BTCUSD-PERP"

    @pytest.mark.asyncio
    async def test_event_callback_fired(self, paper_client):
        """Trade events trigger registered callbacks."""
        events = []
        paper_client.on_trade_event(lambda e: events.append(e))
        await paper_client.place_market_order("BTCUSD-PERP", "buy", 0.1)
        assert len(events) == 1
        assert events[0]["type"] == "trade_executed"

    @pytest.mark.asyncio
    async def test_portfolio_summary(self, paper_client):
        """Portfolio summary reflects current state."""
        await paper_client.place_market_order("BTCUSD-PERP", "buy", 0.1)
        summary = paper_client.get_portfolio_summary()
        assert summary["positions"] == 1
        assert summary["total_trades"] == 1
        assert summary["balance_usd"] < 100000.0


# =============================================================================
# PortfolioAgent - Risk Limits (~5 tests)
# =============================================================================


class TestRiskLimits:
    """Test risk control enforcement."""

    @pytest.mark.asyncio
    async def test_risk_check_max_position_size(self, agent):
        """Orders exceeding max_position_pct are rejected."""
        # Set up portfolio with equity
        agent.portfolio.total_equity = 100000.0
        agent.portfolio.available_balance = 100000.0

        cmd = _make_command(size_pct=0.50)  # 50% > 10% limit
        risk_msg = agent._check_risk_limits(cmd)
        assert risk_msg is not None
        assert "position" in risk_msg.lower() or "risk" in risk_msg.lower()

    @pytest.mark.asyncio
    async def test_risk_check_passes_within_limits(self, agent):
        """Orders within limits pass risk check."""
        agent.portfolio.total_equity = 100000.0
        agent.portfolio.available_balance = 100000.0

        cmd = _make_command(size_pct=0.05)  # 5% < 10% limit
        risk_msg = agent._check_risk_limits(cmd)
        assert risk_msg is None

    @pytest.mark.asyncio
    async def test_rate_limit_check(self, agent):
        """Rate limiter rejects when too many orders per minute."""
        now = datetime.now(UTC)
        # Fill up rate limit
        agent._orders_this_minute = [now] * 15
        assert agent._check_rate_limit() is False

    @pytest.mark.asyncio
    async def test_rate_limit_allows_when_under_limit(self, agent):
        """Rate limiter allows when under limit."""
        agent._orders_this_minute = []
        assert agent._check_rate_limit() is True

    def test_risk_limits_defaults(self):
        """RiskLimits has sensible defaults."""
        limits = RiskLimits()
        assert limits.max_position_pct == 0.10
        assert limits.max_total_exposure_pct == 0.50
        assert limits.max_daily_loss_pct == 0.05


# =============================================================================
# PortfolioAgent - Command Execution (~5 tests)
# =============================================================================


class TestCommandExecution:
    """Test trade command execution flow."""

    @pytest.mark.asyncio
    async def test_submit_command(self, agent):
        """Submitting a command queues it and returns command_id."""
        cmd = _make_command()
        cmd_id = await agent.submit_command(cmd)
        assert cmd_id == cmd.command_id
        assert cmd.command_id in agent._command_history

    @pytest.mark.asyncio
    async def test_execute_market_order_command(self, agent, mock_exchange):
        """Market order command calls exchange place_market_order."""
        agent.portfolio.total_equity = 100000.0
        agent.portfolio.available_balance = 100000.0

        cmd = _make_command(order_type=OrderType.MARKET, size_pct=0.05)
        result = await agent._execute_command(cmd)
        assert result.status in (OrderStatus.FILLED, OrderStatus.SUBMITTED)

    @pytest.mark.asyncio
    async def test_execute_rejected_by_risk(self, agent):
        """Command rejected by risk limits returns REJECTED status."""
        agent.portfolio.total_equity = 100000.0
        agent.portfolio.available_balance = 100000.0

        cmd = _make_command(size_pct=0.99)  # Way over limit
        result = await agent._execute_command(cmd)
        assert result.status == OrderStatus.REJECTED
        assert result.error_code == "risk_limit"

    @pytest.mark.asyncio
    async def test_fill_callbacks_called(self, agent, mock_exchange):
        """Fill callbacks are called after command execution."""
        results = []
        agent.on_fill(lambda r: results.append(r))
        agent.portfolio.total_equity = 100000.0
        agent.portfolio.available_balance = 100000.0

        agent._running = True
        cmd = _make_command(size_pct=0.05)
        await agent._pending_commands.put(cmd)

        # Run one iteration of command processor manually
        try:
            command = await asyncio.wait_for(agent._pending_commands.get(), timeout=1.0)
            result = await agent._execute_command(command)
            agent._order_history[command.command_id] = result
            for cb in agent._fill_callbacks:
                cb(result)
        except TimeoutError:
            pass

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self, agent):
        """Start and stop don't crash."""
        # We can't truly test the background tasks in unit tests,
        # but we verify the flags are set
        await agent.start()
        assert agent._running is True
        await agent.stop()
        assert agent._running is False


# =============================================================================
# Data Structures Tests (~5 tests)
# =============================================================================


class TestDataStructures:
    """Test dataclass structures."""

    def test_trade_command_defaults(self):
        """TradeCommand has sensible defaults."""
        cmd = TradeCommand(
            command_id="c1",
            trio_id="t1",
            symbol="BTCUSD-PERP",
            side=OrderSide.BUY,
            size_pct=0.05,
        )
        assert cmd.order_type == OrderType.MARKET
        assert cmd.confidence == 0.5
        assert cmd.time_in_force == "GTC"

    def test_position_notional_value(self):
        """Position.notional_value is size * current_price."""
        pos = Position(
            symbol="BTCUSD-PERP",
            exchange="test",
            side=PositionSide.LONG,
            size=0.5,
            entry_price=50000.0,
            current_price=51000.0,
            unrealized_pnl=500.0,
            unrealized_pnl_pct=1.0,
            realized_pnl=0.0,
        )
        assert pos.notional_value == 25500.0

    def test_portfolio_state_defaults(self):
        """PortfolioState initializes with empty positions."""
        state = PortfolioState(
            exchange="test",
            total_equity=100000.0,
            available_balance=100000.0,
            margin_used=0.0,
        )
        assert len(state.positions) == 0
        assert state.daily_pnl == 0.0

    def test_order_side_enum(self):
        """OrderSide enum values are strings."""
        assert OrderSide.BUY == "buy"
        assert OrderSide.SELL == "sell"

    def test_order_status_enum(self):
        """OrderStatus enum has all expected values."""
        assert OrderStatus.PENDING == "pending"
        assert OrderStatus.FILLED == "filled"
        assert OrderStatus.CANCELLED == "cancelled"
        assert OrderStatus.REJECTED == "rejected"


# =============================================================================
# Edge Cases (~3 tests)
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_portfolio_balance(self, paper_client):
        """Empty portfolio returns initial balance."""
        balance = await paper_client.get_account_balance()
        assert "USD" in balance

    @pytest.mark.asyncio
    async def test_get_positions_empty(self, paper_client):
        """No positions returns empty list."""
        positions = await paper_client.get_positions()
        assert positions == []

    @pytest.mark.asyncio
    async def test_get_ticker(self, paper_client):
        """Ticker returns current price info."""
        ticker = await paper_client.get_ticker("BTCUSD-PERP")
        assert ticker["price"] == 50000.0
        assert ticker["bid"] < ticker["ask"]
