"""
Phase 5 - Trade Router Integration Tests (Real DB)

Tests trade routes against real PostgreSQL with transaction rollback.
Exercises: GET /trades/, GET /trades/{trade_id}, GET /trades/stats/{agent_id},
           GET /trades/agent, GET /trades/live
"""

import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from Fast_Swarm.Agents.Models.agent_models import Agent
from Fast_Swarm.Trades.Models.trade_models import BacktestTrade


# =============================================================================
# FIXTURES
# =============================================================================


def _make_agent_id():
    return f"trade-test-agent-{uuid.uuid4().hex[:8]}"


def _make_pattern_id():
    return f"trade-test-pat-{uuid.uuid4().hex[:8]}"


def _make_trade_id():
    return f"trade-test-{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture
async def trade_agent(db_session: AsyncSession, sample_traits):
    """Create an agent for trade tests."""
    agent = Agent(
        agent_id=_make_agent_id(),
        name="Trade Test Agent",
        generation=1,
        traits=sample_traits,
        status="active",
        is_active=True,
        fitness_score=50.0,
        elo_rating=1500.0,
    )
    db_session.add(agent)
    await db_session.flush()
    await db_session.refresh(agent)
    return agent


@pytest_asyncio.fixture
async def backtest_trades(db_session: AsyncSession, trade_agent):
    """Create multiple BacktestTrade rows for filtering/pagination tests."""
    now_ms = int(time.time() * 1000)
    trades = []
    symbols = ["BTC", "ETH", "SOL"]
    sides = ["long", "short"]

    for i in range(15):
        t = BacktestTrade(
            trade_id=_make_trade_id(),
            source="evolution_backtest" if i % 3 != 0 else "pattern_backtest",
            pattern_id=f"pat-{i % 3}",
            agent_id=trade_agent.agent_id,
            symbol=symbols[i % 3],
            timeframe="1h",
            side=sides[i % 2],
            entry_timestamp=now_ms - (i * 3600000),
            exit_timestamp=now_ms - (i * 3600000) + 1800000,
            hold_bars=i + 1,
            entry_price=Decimal("50000") + i * 100,
            exit_price=Decimal("50500") + i * 100 if i % 2 == 0 else Decimal("49500") + i * 100,
            gross_pnl_pct=2.0 if i % 2 == 0 else -1.0,
            net_pnl_pct=1.9 if i % 2 == 0 else -1.1,
            is_winner=i % 2 == 0,
        )
        db_session.add(t)
        trades.append(t)

    await db_session.flush()
    for t in trades:
        await db_session.refresh(t)
    return trades


# =============================================================================
# GET /trades/ - List trades with filtering
# =============================================================================


class TestListTrades:
    """Tests for GET /trades/ endpoint (trade_service.get_all_trades)."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_list_trades_returns_results(
        self, db_session: AsyncSession, backtest_trades
    ):
        """Listing trades returns non-empty list when trades exist."""
        from Fast_Swarm.Trades.Services.trade_service import get_all_trades

        result = await get_all_trades(db_session, limit=100)

        assert len(result) >= 15

    @pytest.mark.asyncio
    async def test_list_trades_pagination_limit(
        self, db_session: AsyncSession, backtest_trades
    ):
        """Limit parameter restricts number of returned trades."""
        from Fast_Swarm.Trades.Services.trade_service import get_all_trades

        result = await get_all_trades(db_session, limit=5)

        assert len(result) <= 5

    @pytest.mark.asyncio
    async def test_list_trades_pagination_offset(
        self, db_session: AsyncSession, backtest_trades
    ):
        """Offset parameter skips trades for pagination."""
        from Fast_Swarm.Trades.Services.trade_service import get_all_trades

        page1 = await get_all_trades(db_session, limit=5, offset=0)
        page2 = await get_all_trades(db_session, limit=5, offset=5)

        # Pages should not overlap (different trade_ids)
        page1_ids = {t.trade_id for t in page1}
        page2_ids = {t.trade_id for t in page2}
        assert page1_ids.isdisjoint(page2_ids)

    @pytest.mark.asyncio
    async def test_list_trades_filter_by_agent_id(
        self, db_session: AsyncSession, backtest_trades, trade_agent
    ):
        """Filter by agent_id returns only that agent's trades."""
        from Fast_Swarm.Trades.Services.trade_service import get_all_trades

        result = await get_all_trades(
            db_session, limit=100, agent_id=trade_agent.agent_id
        )

        assert len(result) >= 15
        assert all(t.agent_id == trade_agent.agent_id for t in result)

    @pytest.mark.asyncio
    async def test_list_trades_filter_by_symbol(
        self, db_session: AsyncSession, backtest_trades
    ):
        """Filter by symbol returns only matching trades."""
        from Fast_Swarm.Trades.Services.trade_service import get_all_trades

        result = await get_all_trades(db_session, limit=100, symbol="BTC")

        assert len(result) >= 1
        assert all(t.symbol == "BTC" for t in result)

    @pytest.mark.asyncio
    async def test_list_trades_filter_by_source(
        self, db_session: AsyncSession, backtest_trades
    ):
        """Filter by source returns only matching trades."""
        from Fast_Swarm.Trades.Services.trade_service import get_all_trades

        result = await get_all_trades(
            db_session, limit=100, source="pattern_backtest"
        )

        assert len(result) >= 1
        assert all(t.source == "pattern_backtest" for t in result)

    @pytest.mark.asyncio
    async def test_list_trades_filter_nonexistent_agent(
        self, db_session: AsyncSession, backtest_trades
    ):
        """Filtering by nonexistent agent returns empty."""
        from Fast_Swarm.Trades.Services.trade_service import get_all_trades

        result = await get_all_trades(
            db_session, limit=100, agent_id="does-not-exist"
        )

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_list_trades_combined_filters(
        self, db_session: AsyncSession, backtest_trades, trade_agent
    ):
        """Multiple filters combine (AND logic)."""
        from Fast_Swarm.Trades.Services.trade_service import get_all_trades

        result = await get_all_trades(
            db_session,
            limit=100,
            agent_id=trade_agent.agent_id,
            symbol="BTC",
            source="evolution_backtest",
        )

        for t in result:
            assert t.agent_id == trade_agent.agent_id
            assert t.symbol == "BTC"
            assert t.source == "evolution_backtest"


# =============================================================================
# GET /trades/{trade_id} - Get single trade
# =============================================================================


class TestGetTradeById:
    """Tests for GET /trades/{trade_id} endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_get_trade_by_id_found(
        self, db_session: AsyncSession, backtest_trades
    ):
        """Getting a trade by valid ID returns the trade."""
        from Fast_Swarm.Trades.Services.trade_service import get_trade_by_id

        target = backtest_trades[0]
        result = await get_trade_by_id(db_session, target.trade_id)

        assert result is not None
        assert result.trade_id == target.trade_id

    @pytest.mark.asyncio
    async def test_get_trade_by_id_not_found(self, db_session: AsyncSession):
        """Getting a nonexistent trade returns None."""
        from Fast_Swarm.Trades.Services.trade_service import get_trade_by_id

        result = await get_trade_by_id(db_session, "nonexistent-trade-id")

        assert result is None


# =============================================================================
# GET /trades/stats/{agent_id} - Agent trade statistics
# =============================================================================


class TestAgentTradeStats:
    """Tests for GET /trades/stats/{agent_id} endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_agent_trade_stats_returns_dict(
        self, db_session: AsyncSession, backtest_trades, trade_agent
    ):
        """Agent trade stats returns a dict with expected keys."""
        from Fast_Swarm.Trades.Services.trade_service import get_agent_trade_stats

        result = await get_agent_trade_stats(db_session, trade_agent.agent_id)

        assert isinstance(result, dict)
        assert "total_trades" in result
        assert "win_count" in result or "win_rate" in result

    @pytest.mark.asyncio
    async def test_agent_trade_stats_counts_correct(
        self, db_session: AsyncSession, backtest_trades, trade_agent
    ):
        """Agent trade stats counts trades accurately."""
        from Fast_Swarm.Trades.Services.trade_service import get_agent_trade_stats

        result = await get_agent_trade_stats(db_session, trade_agent.agent_id)

        # We created 15 trades for this agent
        assert result["total_trades"] >= 15

    @pytest.mark.asyncio
    async def test_agent_trade_stats_nonexistent_agent(
        self, db_session: AsyncSession
    ):
        """Stats for nonexistent agent returns zero counts (not error)."""
        from Fast_Swarm.Trades.Services.trade_service import get_agent_trade_stats

        result = await get_agent_trade_stats(db_session, "nonexistent-agent")

        assert isinstance(result, dict)
        assert result["total_trades"] == 0
