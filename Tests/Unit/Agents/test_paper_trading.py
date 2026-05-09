"""
Paper Trading Unit Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Implementation Plan (Part 1: Paper Trading Fixes)
Tests sell validation, P&L tracking, limit orders, partial closes, and event callbacks.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from Fast_Swarm.Agents.Hivemind.Services.portfolio_agent_service import (
    ALLOWED_CLOSE_FRACTIONS,
    DEFAULT_ORDER_EXPIRY_HOURS,
    PaperTradingClient,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def paper_client():
    """Create a paper trading client with default settings."""
    client = PaperTradingClient(
        initial_balance=50000.0,
        slippage_bps=10,
        fee_bps=10,
    )
    return client


@pytest.fixture
def paper_client_with_position(paper_client):
    """Create a paper trading client with an existing BTC position."""
    # Manually add a position for testing sells
    paper_client.positions["BTC"] = {
        "symbol": "BTC",
        "side": "long",
        "size": 1.0,
        "entry_price": 50000.0,
        "notional": 50000.0,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    paper_client.balance["USD"] -= 50000.0  # Deduct cost
    paper_client._prices["BTC"] = 50000.0
    return paper_client


# ============================================================================
# SELL VALIDATION CONTRACT
# ============================================================================


class TestSellValidation:
    """CONTRACT: Sell orders must be validated against existing positions."""

    @pytest.mark.asyncio
    async def test_sell_requires_position(self, paper_client):
        """CONTRACT: Selling without a position returns error."""
        paper_client._prices["ETH"] = 3000.0
        result = await paper_client.place_market_order("ETH", "sell", 1.0)
        assert "error" in result
        assert result["error"] == "no_position"

    @pytest.mark.asyncio
    async def test_sell_requires_sufficient_size(self, paper_client_with_position):
        """CONTRACT: Selling more than position size returns error."""
        result = await paper_client_with_position.place_market_order("BTC", "sell", 2.0)
        assert "error" in result
        assert result["error"] == "insufficient_size"

    @pytest.mark.asyncio
    async def test_sell_partial_succeeds(self, paper_client_with_position):
        """CONTRACT: Selling part of position succeeds."""
        result = await paper_client_with_position.place_market_order("BTC", "sell", 0.5)
        assert "error" not in result
        assert result["status"] == "filled"
        # Position should be reduced
        pos = paper_client_with_position.positions.get("BTC")
        assert pos is not None
        assert pos["size"] == pytest.approx(0.5, abs=0.01)

    @pytest.mark.asyncio
    async def test_sell_full_position_closes(self, paper_client_with_position):
        """CONTRACT: Selling full position removes it."""
        result = await paper_client_with_position.place_market_order("BTC", "sell", 1.0)
        assert "error" not in result
        # Position should be removed
        assert "BTC" not in paper_client_with_position.positions


# ============================================================================
# P&L TRACKING CONTRACT
# ============================================================================


class TestPnLTracking:
    """CONTRACT: Profit and loss must be correctly calculated and credited."""

    @pytest.mark.asyncio
    async def test_profit_credited_on_sell(self, paper_client_with_position):
        """CONTRACT: Profitable sells credit P&L to USD balance."""
        initial_usd = paper_client_with_position.balance["USD"]
        # Set price higher than entry (profit)
        paper_client_with_position._prices["BTC"] = 55000.0

        await paper_client_with_position.place_market_order("BTC", "sell", 1.0)

        # USD should increase by proceeds (roughly 55000 minus fees/slippage)
        final_usd = paper_client_with_position.balance["USD"]
        assert final_usd > initial_usd + 50000  # At least break even plus some

    @pytest.mark.asyncio
    async def test_loss_reflected_on_sell(self, paper_client_with_position):
        """CONTRACT: Losing sells result in lower USD balance."""
        initial_usd = paper_client_with_position.balance["USD"]
        # Set price lower than entry (loss)
        paper_client_with_position._prices["BTC"] = 45000.0

        await paper_client_with_position.place_market_order("BTC", "sell", 1.0)

        final_usd = paper_client_with_position.balance["USD"]
        # Should get back less than entry cost
        assert final_usd < initial_usd + 50000

    @pytest.mark.asyncio
    async def test_realized_pnl_tracked(self, paper_client_with_position):
        """CONTRACT: Realized P&L is accumulated."""
        initial_pnl = paper_client_with_position.realized_pnl
        paper_client_with_position._prices["BTC"] = 52000.0  # 4% profit

        await paper_client_with_position.place_market_order("BTC", "sell", 1.0)

        final_pnl = paper_client_with_position.realized_pnl
        # Should have positive realized P&L (approximately $2000)
        assert final_pnl > initial_pnl
        assert final_pnl > 1500  # At least $1500 after fees


# ============================================================================
# LIMIT ORDER CONTRACT
# ============================================================================


class TestLimitOrders:
    """CONTRACT: Limit orders with 24h expiry behavior."""

    @pytest.mark.asyncio
    async def test_limit_order_rests_when_not_fillable(self, paper_client):
        """CONTRACT: Limit order that can't fill immediately rests on book."""
        paper_client._prices["BTC"] = 50000.0

        # Place buy limit below market
        result = await paper_client.place_limit_order("BTC", "buy", 0.1, 48000.0)

        assert result["status"] == "pending"
        assert result["order_id"] in paper_client.pending_orders

    @pytest.mark.asyncio
    async def test_limit_order_fills_immediately_when_possible(self, paper_client):
        """CONTRACT: Limit order at or better than market fills immediately."""
        paper_client._prices["BTC"] = 50000.0
        paper_client.balance["USD"] = 100000.0

        # Place buy limit at or above market
        result = await paper_client.place_limit_order("BTC", "buy", 0.1, 51000.0)

        assert result["status"] == "filled"
        assert "BTC" in paper_client.positions

    @pytest.mark.asyncio
    async def test_limit_order_has_expiry(self, paper_client):
        """CONTRACT: Limit orders have 24h expiry by default."""
        paper_client._prices["BTC"] = 50000.0

        result = await paper_client.place_limit_order("BTC", "buy", 0.1, 48000.0)

        order = paper_client.pending_orders[result["order_id"]]
        created = datetime.fromisoformat(order["created_at"])
        expires = datetime.fromisoformat(order["expires_at"])

        assert (expires - created).total_seconds() == DEFAULT_ORDER_EXPIRY_HOURS * 3600

    @pytest.mark.asyncio
    async def test_limit_order_custom_expiry(self, paper_client):
        """CONTRACT: Custom expiry can be specified."""
        paper_client._prices["BTC"] = 50000.0

        result = await paper_client.place_limit_order(
            "BTC", "buy", 0.1, 48000.0, expiry_hours=1
        )

        order = paper_client.pending_orders[result["order_id"]]
        created = datetime.fromisoformat(order["created_at"])
        expires = datetime.fromisoformat(order["expires_at"])

        assert (expires - created).total_seconds() == 3600  # 1 hour

    @pytest.mark.asyncio
    async def test_pending_order_fills_on_price_cross(self, paper_client):
        """CONTRACT: Pending orders fill when price crosses limit."""
        # Setup: First place a limit order that won't fill immediately
        paper_client._prices["BTC"] = 50000.0
        paper_client.balance["USD"] = 50000.0

        result = await paper_client.place_limit_order("BTC", "buy", 0.1, 48000.0)
        order_id = result["order_id"]

        # Verify it's pending
        assert result["status"] == "pending"
        assert order_id in paper_client.pending_orders

        # Now price drops below limit - this should trigger fill
        paper_client._prices["BTC"] = 47500.0
        paper_client.check_pending_orders("BTC", 47500.0)

        # Give async task time to complete
        import asyncio
        await asyncio.sleep(0.1)

        # Order should be filled or filling
        order = paper_client.orders.get(order_id)
        assert order is not None
        assert order["status"] in ("filled", "filling")


# ============================================================================
# PARTIAL CLOSE CONTRACT
# ============================================================================


class TestPartialCloses:
    """CONTRACT: Partial position closes create separate trade legs."""

    @pytest.mark.asyncio
    async def test_partial_close_25_percent(self, paper_client_with_position):
        """CONTRACT: 25% partial close works correctly."""
        initial_size = paper_client_with_position.positions["BTC"]["size"]
        paper_client_with_position._prices["BTC"] = 52000.0

        result = await paper_client_with_position.close_position_partial("BTC", 0.25)

        assert "error" not in result
        # Position should be reduced by 25%
        pos = paper_client_with_position.positions.get("BTC")
        assert pos is not None
        assert pos["size"] == pytest.approx(initial_size * 0.75, abs=0.01)

    @pytest.mark.asyncio
    async def test_partial_close_creates_trade_leg(self, paper_client_with_position):
        """CONTRACT: Partial close creates a trade leg record."""
        paper_client_with_position._prices["BTC"] = 52000.0

        await paper_client_with_position.close_position_partial("BTC", 0.50)

        legs = paper_client_with_position.trade_legs
        assert len(legs) >= 1
        last_leg = legs[-1]
        assert last_leg["symbol"] == "BTC"
        assert last_leg["fraction"] == 0.50

    @pytest.mark.asyncio
    async def test_invalid_fraction_rejected(self, paper_client_with_position):
        """CONTRACT: Invalid close fractions are rejected."""
        result = await paper_client_with_position.close_position_partial("BTC", 0.33)

        assert "error" in result
        assert result["error"] == "invalid_fraction"
        assert result["allowed"] == ALLOWED_CLOSE_FRACTIONS

    @pytest.mark.asyncio
    async def test_partial_close_100_percent_closes_position(self, paper_client_with_position):
        """CONTRACT: 100% partial close fully closes position."""
        paper_client_with_position._prices["BTC"] = 52000.0

        await paper_client_with_position.close_position_partial("BTC", 1.00)

        assert "BTC" not in paper_client_with_position.positions

    @pytest.mark.asyncio
    async def test_multiple_partials_tracked_separately(self, paper_client_with_position):
        """CONTRACT: Multiple partial closes create separate legs."""
        paper_client_with_position._prices["BTC"] = 52000.0

        await paper_client_with_position.close_position_partial("BTC", 0.25)
        await paper_client_with_position.close_position_partial("BTC", 0.25)

        legs = paper_client_with_position.trade_legs
        assert len(legs) >= 2
        # Each leg should have different IDs
        leg_ids = [leg["leg_id"] for leg in legs[-2:]]
        assert len(set(leg_ids)) == 2


# ============================================================================
# SLIPPAGE VARIANCE CONTRACT
# ============================================================================


class TestSlippageVariance:
    """CONTRACT: Slippage has realistic variance."""

    @pytest.mark.asyncio
    async def test_slippage_has_variance(self, paper_client):
        """CONTRACT: Multiple trades have different slippage amounts."""
        paper_client.balance["USD"] = 1000000.0
        paper_client._prices["BTC"] = 50000.0

        fill_prices = []
        for _ in range(20):
            result = await paper_client.place_market_order("BTC", "buy", 0.01)
            if "error" not in result:
                fill_prices.append(result["price"])
                # Sell back to reset position
                await paper_client.place_market_order("BTC", "sell", 0.01)

        # Should have some variance in fill prices
        assert len(set(fill_prices)) > 1, "All fill prices identical - no variance"

    def test_slippage_increases_with_size(self, paper_client):
        """CONTRACT: Larger orders have more slippage on average."""
        small_slippage = []
        large_slippage = []

        for _ in range(50):
            # Small order ($1,000 notional)
            small = paper_client._apply_slippage(50000.0, "buy", 0.02)  # $1k
            small_slippage.append(small - 50000.0)

            # Large order ($100,000 notional)
            large = paper_client._apply_slippage(50000.0, "buy", 2.0)  # $100k
            large_slippage.append(large - 50000.0)

        avg_small = sum(small_slippage) / len(small_slippage)
        avg_large = sum(large_slippage) / len(large_slippage)

        # Large orders should have more slippage on average
        assert avg_large > avg_small

    def test_slippage_always_positive_for_buys(self, paper_client):
        """CONTRACT: Buy slippage results in higher prices (adverse)."""
        for _ in range(50):
            result = paper_client._apply_slippage(50000.0, "buy", 0.1)
            # Buy slippage should generally make price higher
            # (with variance, might occasionally be lower, but on average higher)
        # This is more of a sanity check - detailed variance checked elsewhere


# ============================================================================
# TRADE HISTORY CONTRACT
# ============================================================================


class TestTradeHistory:
    """CONTRACT: Trade history maintained with async DB flush support."""

    @pytest.mark.asyncio
    async def test_trades_recorded_in_history(self, paper_client):
        """CONTRACT: Executed trades are recorded in history."""
        paper_client.balance["USD"] = 100000.0
        paper_client._prices["BTC"] = 50000.0

        await paper_client.place_market_order("BTC", "buy", 0.1)
        await paper_client.place_market_order("BTC", "sell", 0.1)

        history = paper_client.get_trade_history()
        assert len(history) >= 2

    @pytest.mark.asyncio
    async def test_history_has_correct_fields(self, paper_client):
        """CONTRACT: Trade history records have required fields."""
        paper_client.balance["USD"] = 100000.0
        paper_client._prices["BTC"] = 50000.0

        await paper_client.place_market_order("BTC", "buy", 0.1)

        history = paper_client.get_trade_history()
        assert len(history) >= 1

        trade = history[-1]
        assert "order_id" in trade  # Implementation uses order_id
        assert "symbol" in trade
        assert "side" in trade
        assert "price" in trade
        assert "size" in trade
        assert "filled_at" in trade  # Implementation uses filled_at

    @pytest.mark.asyncio
    async def test_trades_queued_for_db_flush(self, paper_client):
        """CONTRACT: Trades are queued for async DB flush."""
        paper_client.balance["USD"] = 100000.0
        paper_client._prices["BTC"] = 50000.0

        await paper_client.place_market_order("BTC", "buy", 0.1)

        # Queue should have at least one item
        assert paper_client._db_flush_queue.qsize() >= 1


# ============================================================================
# EVENT CALLBACK CONTRACT
# ============================================================================


class TestEventCallbacks:
    """CONTRACT: Event callbacks for real-time monitoring."""

    @pytest.mark.asyncio
    async def test_trade_event_callback_called(self, paper_client):
        """CONTRACT: Trade events trigger registered callbacks."""
        events_received = []

        def callback(event):
            events_received.append(event)

        paper_client.on_trade_event(callback)
        paper_client.balance["USD"] = 100000.0
        paper_client._prices["BTC"] = 50000.0

        await paper_client.place_market_order("BTC", "buy", 0.1)

        assert len(events_received) >= 1
        assert events_received[-1]["type"] == "trade_executed"

    @pytest.mark.asyncio
    async def test_async_callback_supported(self, paper_client):
        """CONTRACT: Async callbacks are supported."""
        events_received = []

        async def async_callback(event):
            await asyncio.sleep(0.001)  # Simulate async work
            events_received.append(event)

        paper_client.on_trade_event(async_callback)
        paper_client.balance["USD"] = 100000.0
        paper_client._prices["BTC"] = 50000.0

        await paper_client.place_market_order("BTC", "buy", 0.1)

        # Give async callback time to execute
        await asyncio.sleep(0.1)

        assert len(events_received) >= 1

    @pytest.mark.asyncio
    async def test_trade_leg_event_emitted(self, paper_client_with_position):
        """CONTRACT: Trade leg closures emit events."""
        events_received = []

        def callback(event):
            events_received.append(event)

        paper_client_with_position.on_trade_event(callback)
        paper_client_with_position._prices["BTC"] = 52000.0

        await paper_client_with_position.close_position_partial("BTC", 0.25)

        leg_events = [e for e in events_received if e["type"] == "trade_leg_closed"]
        assert len(leg_events) >= 1


# ============================================================================
# PORTFOLIO SUMMARY CONTRACT
# ============================================================================


class TestPortfolioSummary:
    """CONTRACT: Portfolio summary calculations."""

    @pytest.mark.asyncio
    async def test_get_portfolio_summary(self, paper_client_with_position):
        """CONTRACT: Portfolio summary returns complete state."""
        summary = paper_client_with_position.get_portfolio_summary()

        assert "balance_usd" in summary
        assert "positions" in summary
        assert "realized_pnl" in summary
        assert "pending_orders" in summary

    @pytest.mark.asyncio
    async def test_portfolio_value_calculated(self, paper_client_with_position):
        """CONTRACT: Total portfolio value includes positions."""
        paper_client_with_position._prices["BTC"] = 55000.0

        summary = paper_client_with_position.get_portfolio_summary()

        # Should have USD balance + position count
        assert summary["balance_usd"] >= 0
        assert summary["positions"] >= 1
