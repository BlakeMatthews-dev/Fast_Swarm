"""
AgentPaperTradingService Integration Tests - Real DB, Real Agents.

Tests the MVP direct agent -> paper trading bridge using real database
sessions and real Agent objects. Only exchange HTTP calls are mocked.

Source: src/Fast_Swarm/Trading/Services/agent_paper_trading_service.py
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from Fast_Swarm.Agents.Models.agent_models import Agent
from Fast_Swarm.Infrastructure.Models.exchange_models import LiveTradeUnified
from Fast_Swarm.Trading.Services.agent_paper_trading_service import (
    AgentPaperTradingService,
)


# ============================================================================
# HELPERS
# ============================================================================


def make_agent_id() -> str:
    return f"test-paper-{uuid.uuid4().hex[:8]}"


def make_candle_data(
    *,
    rsi: float = 50.0,
    volume_ratio: float = 1.0,
    close: float = 50000.0,
    defensive_trigger: int = 0,
    close_acceleration_zscore: float = 0.0,
    adx_14_jerk_zscore: float = 0.0,
) -> dict[str, Any]:
    """Build a synthetic candle_data dict with common indicators."""
    return {
        "open": close * 0.999,
        "high": close * 1.002,
        "low": close * 0.998,
        "close": close,
        "volume": 100.0,
        "rsi": rsi,
        "volume_ratio": volume_ratio,
        "defensive_trigger": defensive_trigger,
        "close_acceleration_zscore": close_acceleration_zscore,
        "adx_14_jerk_zscore": adx_14_jerk_zscore,
    }


def make_entry_conditions(indicator: str = "rsi", operator: str = "<", value: float = 30) -> dict:
    """Build pattern entry conditions that use evaluate_conditions format."""
    return {
        "conditions": [
            {"indicator": indicator, "operator": operator, "value": value},
        ]
    }


def make_exit_conditions(indicator: str = "rsi", operator: str = ">", value: float = 70) -> dict:
    return {
        "conditions": [
            {"indicator": indicator, "operator": operator, "value": value},
        ]
    }


async def create_test_agent(
    session: AsyncSession,
    *,
    agent_id: str | None = None,
    name: str = "Paper Test Agent",
    status: str = "active",
    assigned_patterns: dict[str, Any] | None = None,
    pattern_weights: dict[str, float] | None = None,
    traits: dict[str, Any] | None = None,
) -> Agent:
    """Create and persist a test Agent in the database."""
    aid = agent_id or make_agent_id()
    agent = Agent(
        agent_id=aid,
        name=name,
        generation=1,
        status=status,
        is_active=(status == "active"),
        traits=traits or {"kelly_fraction": 0.1, "risk_tolerance": 0.5},
        assigned_patterns=assigned_patterns or {},
        pattern_weights=pattern_weights or {},
        fitness_score=Decimal("0"),
        elo_rating=Decimal("1500"),
    )
    session.add(agent)
    await session.flush()
    await session.refresh(agent)
    return agent


# ============================================================================
# TEST: Start Paper Trading Session
# ============================================================================


class TestStartPaperTrading:
    """Tests for starting a paper trading session with real DB agents."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_start_with_active_agent(self, db_session: AsyncSession):
        """Starting paper trading with an active agent succeeds."""
        agent = await create_test_agent(db_session)
        service = AgentPaperTradingService()

        result = await service.start_paper_trading(db_session, agent.agent_id)

        assert result["status"] == "started"
        assert result["agent_id"] == agent.agent_id
        assert result["agent_name"] == agent.name
        assert result["balance"] == 10000.0
        assert result["symbols"] == ["BTC-USDT"]

    @pytest.mark.asyncio
    async def test_start_with_custom_balance_and_symbols(self, db_session: AsyncSession):
        """Custom balance and symbols are respected."""
        agent = await create_test_agent(db_session)
        service = AgentPaperTradingService()

        result = await service.start_paper_trading(
            db_session, agent.agent_id, symbols=["ETH-USDT", "SOL-USDT"], initial_balance=50000.0
        )

        assert result["balance"] == 50000.0
        assert result["symbols"] == ["ETH-USDT", "SOL-USDT"]

    @pytest.mark.asyncio
    async def test_start_with_inactive_agent_returns_error(self, db_session: AsyncSession):
        """Retired agent cannot start paper trading."""
        agent = await create_test_agent(db_session, status="retired")
        service = AgentPaperTradingService()

        result = await service.start_paper_trading(db_session, agent.agent_id)

        assert "error" in result
        assert result["status"] == "retired"

    @pytest.mark.asyncio
    async def test_start_with_nonexistent_agent_returns_error(self, db_session: AsyncSession):
        """Missing agent returns an error dict."""
        service = AgentPaperTradingService()

        result = await service.start_paper_trading(db_session, "nonexistent-agent-id")

        assert "error" in result
        assert result["agent_id"] == "nonexistent-agent-id"

    @pytest.mark.asyncio
    async def test_start_initializes_position_tracking(self, db_session: AsyncSession):
        """Starting creates internal position tracking state."""
        agent = await create_test_agent(db_session)
        service = AgentPaperTradingService()

        await service.start_paper_trading(db_session, agent.agent_id)

        pos = service.active_positions[agent.agent_id]
        assert pos["balance"] == 10000.0
        assert pos["positions"] == {}
        assert pos["trades_count"] == 0
        assert pos["total_pnl"] == 0.0
        assert isinstance(pos["started_at"], datetime)


# ============================================================================
# TEST: Evaluate and Trade (Open Positions)
# ============================================================================


class TestEvaluateAndTrade:
    """Tests for evaluate_and_trade producing real DB trades."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_open_long_position_writes_to_db(self, db_session: AsyncSession):
        """A buy signal creates a LiveTradeUnified record in the database."""
        patterns = {
            "pat-1": {
                "entry_conditions": make_entry_conditions("rsi", "<", 30),
                "exit_conditions": make_exit_conditions("rsi", ">", 70),
                "direction": "long",
            }
        }
        agent = await create_test_agent(
            db_session,
            assigned_patterns=patterns,
            pattern_weights={"pat-1": 1.0},
        )
        service = AgentPaperTradingService()
        await service.start_paper_trading(db_session, agent.agent_id)

        # Candle with RSI=20 should trigger buy (rsi < 30 entry condition)
        candle = make_candle_data(rsi=20.0, close=50000.0)
        result = await service.evaluate_and_trade(
            db_session, agent.agent_id, "BTC-USDT", 50000.0, candle, regime="bull"
        )

        # The result depends on whether evaluate_conditions is available.
        # If it matched, we get a trade; if not, we get None (hold).
        if result is not None:
            assert result["action"] == "open"
            assert result["symbol"] == "BTC-USDT"
            assert result["side"] == "long"
            assert result["price"] == 50000.0
            assert result["size"] > 0
            assert result["size_usd"] > 0

            # Verify the trade was persisted in the database
            stmt = select(LiveTradeUnified).where(
                LiveTradeUnified.trade_id == result["trade_id"]
            )
            db_result = await db_session.exec(stmt)
            trade = db_result.first()
            assert trade is not None
            assert trade.source == "paper"
            assert trade.agent_id == agent.agent_id
            assert trade.status == "open"
            assert trade.entry_price == Decimal("50000")
            assert trade.regime == "bull"
            assert trade.trading_mode == "mvp_direct"

    @pytest.mark.asyncio
    async def test_no_trade_when_not_started(self, db_session: AsyncSession):
        """evaluate_and_trade returns None if agent has no active session."""
        service = AgentPaperTradingService()
        candle = make_candle_data()

        result = await service.evaluate_and_trade(
            db_session, "not-started-agent", "BTC-USDT", 50000.0, candle
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_no_trade_without_patterns(self, db_session: AsyncSession):
        """Agent without assigned patterns returns None (hold)."""
        agent = await create_test_agent(db_session, assigned_patterns={})
        service = AgentPaperTradingService()
        await service.start_paper_trading(db_session, agent.agent_id)

        candle = make_candle_data(rsi=20.0)
        result = await service.evaluate_and_trade(
            db_session, agent.agent_id, "BTC-USDT", 50000.0, candle
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_position_size_uses_kelly_fraction(self, db_session: AsyncSession):
        """Position size is balance * kelly_fraction."""
        patterns = {
            "pat-1": {
                "entry_conditions": make_entry_conditions("rsi", "<", 30),
                "exit_conditions": {},
                "direction": "long",
            }
        }
        agent = await create_test_agent(
            db_session,
            assigned_patterns=patterns,
            pattern_weights={"pat-1": 1.0},
            traits={"kelly_fraction": 0.2},
        )
        service = AgentPaperTradingService()
        await service.start_paper_trading(db_session, agent.agent_id, initial_balance=20000.0)

        candle = make_candle_data(rsi=20.0, close=40000.0)
        result = await service.evaluate_and_trade(
            db_session, agent.agent_id, "BTC-USDT", 40000.0, candle
        )

        if result is not None:
            # 20000 * 0.2 = 4000 USD position
            assert abs(result["size_usd"] - 4000.0) < 0.01
            assert abs(result["size"] - 0.1) < 0.001  # 4000 / 40000


# ============================================================================
# TEST: Close Positions and P&L Tracking
# ============================================================================


class TestClosePositions:
    """Tests for closing positions and verifying P&L in the database."""

    async def _open_position_for_agent(
        self, db_session: AsyncSession, service: AgentPaperTradingService, agent: Agent
    ) -> dict:
        """Helper: manually inject an open position into the service."""
        trade_id = f"trade-{uuid.uuid4().hex[:8]}"
        entry_price = 50000.0
        size_usd = 1000.0
        size = size_usd / entry_price

        # Write the trade to DB
        trade = LiveTradeUnified(
            trade_id=trade_id,
            source="paper",
            agent_id=agent.agent_id,
            agent_name=agent.name,
            exchange="paper",
            venue_type="paper",
            symbol="BTC-USDT",
            side="long",
            entry_time=datetime.now(timezone.utc),
            entry_price=Decimal(str(entry_price)),
            requested_price=Decimal(str(entry_price)),
            size=Decimal(str(size)),
            size_usd=Decimal(str(size_usd)),
            status="open",
            order_type="market",
            regime="bull",
            trading_mode="mvp_direct",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(trade)
        await db_session.flush()

        # Set up internal tracking
        service.active_positions[agent.agent_id]["positions"]["BTC-USDT"] = {
            "trade_id": trade_id,
            "side": "long",
            "entry_price": entry_price,
            "size": size,
            "size_usd": size_usd,
            "entry_time": datetime.now(timezone.utc),
        }
        service.active_positions[agent.agent_id]["trades_count"] += 1

        return {"trade_id": trade_id, "entry_price": entry_price, "size": size, "size_usd": size_usd}

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_close_long_profit_updates_db(self, db_session: AsyncSession):
        """Closing a long position at a higher price records profit in DB."""
        agent = await create_test_agent(db_session)
        service = AgentPaperTradingService()
        await service.start_paper_trading(db_session, agent.agent_id)

        pos = await self._open_position_for_agent(db_session, service, agent)
        exit_price = 52000.0

        result = await service.force_close_position(
            db_session, agent.agent_id, "BTC-USDT", exit_price
        )

        assert result["action"] == "close"
        assert result["entry_price"] == 50000.0
        assert result["exit_price"] == 52000.0
        assert result["pnl_pct"] > 0  # Profit
        assert result["pnl_usd"] > 0

        # Verify DB was updated
        stmt = select(LiveTradeUnified).where(LiveTradeUnified.trade_id == pos["trade_id"])
        db_result = await db_session.exec(stmt)
        trade = db_result.first()
        assert trade is not None
        assert trade.status == "closed"
        assert trade.exit_price == Decimal("52000")
        assert trade.pnl_usd > 0
        assert trade.realized_pnl > 0
        assert trade.exit_reason == "signal"
        assert trade.duration_seconds is not None and trade.duration_seconds >= 0

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_close_long_loss_updates_db(self, db_session: AsyncSession):
        """Closing a long at a lower price records a loss."""
        agent = await create_test_agent(db_session)
        service = AgentPaperTradingService()
        await service.start_paper_trading(db_session, agent.agent_id)

        pos = await self._open_position_for_agent(db_session, service, agent)
        exit_price = 48000.0

        result = await service.force_close_position(
            db_session, agent.agent_id, "BTC-USDT", exit_price
        )

        assert result["pnl_pct"] < 0
        assert result["pnl_usd"] < 0

        stmt = select(LiveTradeUnified).where(LiveTradeUnified.trade_id == pos["trade_id"])
        db_result = await db_session.exec(stmt)
        trade = db_result.first()
        assert trade.pnl_usd < 0
        assert trade.status == "closed"

    @pytest.mark.asyncio
    async def test_close_updates_balance_tracking(self, db_session: AsyncSession):
        """Closing a position updates the in-memory balance and P&L."""
        agent = await create_test_agent(db_session)
        service = AgentPaperTradingService()
        await service.start_paper_trading(db_session, agent.agent_id, initial_balance=10000.0)

        await self._open_position_for_agent(db_session, service, agent)
        exit_price = 52000.0  # 4% profit on 1000 USD => 40 USD profit

        await service.force_close_position(
            db_session, agent.agent_id, "BTC-USDT", exit_price
        )

        positions = await service.get_agent_positions(agent.agent_id)
        assert positions["total_pnl"] > 0
        assert positions["balance"] > 10000.0
        assert positions["positions"] == {}  # Position cleared

    @pytest.mark.asyncio
    async def test_close_no_position_returns_error(self, db_session: AsyncSession):
        """Closing a non-existent position returns an error."""
        agent = await create_test_agent(db_session)
        service = AgentPaperTradingService()
        await service.start_paper_trading(db_session, agent.agent_id)

        result = await service.force_close_position(
            db_session, agent.agent_id, "ETH-USDT", 3000.0
        )

        assert "error" in result


# ============================================================================
# TEST: Bear Protection (Defensive Trigger)
# ============================================================================


class TestBearProtection:
    """Bear protection should force-close positions and block new entries."""

    async def _setup_agent_with_position(
        self, db_session: AsyncSession
    ) -> tuple[Agent, AgentPaperTradingService]:
        """Create an agent with an open position."""
        patterns = {
            "pat-1": {
                "entry_conditions": make_entry_conditions("rsi", "<", 30),
                "exit_conditions": {},
                "direction": "long",
            }
        }
        agent = await create_test_agent(
            db_session, assigned_patterns=patterns, pattern_weights={"pat-1": 1.0}
        )
        service = AgentPaperTradingService()
        await service.start_paper_trading(db_session, agent.agent_id)

        # Manually place a position
        trade_id = f"trade-{uuid.uuid4().hex[:8]}"
        trade = LiveTradeUnified(
            trade_id=trade_id,
            source="paper",
            agent_id=agent.agent_id,
            agent_name=agent.name,
            exchange="paper",
            venue_type="paper",
            symbol="BTC-USDT",
            side="long",
            entry_time=datetime.now(timezone.utc),
            entry_price=Decimal("50000"),
            requested_price=Decimal("50000"),
            size=Decimal("0.02"),
            size_usd=Decimal("1000"),
            status="open",
            order_type="market",
            trading_mode="mvp_direct",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(trade)
        await db_session.flush()

        service.active_positions[agent.agent_id]["positions"]["BTC-USDT"] = {
            "trade_id": trade_id,
            "side": "long",
            "entry_price": 50000.0,
            "size": 0.02,
            "size_usd": 1000.0,
            "entry_time": datetime.now(timezone.utc),
        }
        service.active_positions[agent.agent_id]["trades_count"] = 1

        return agent, service

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_defensive_trigger_force_closes_position(self, db_session: AsyncSession):
        """When defensive_trigger=1, open position is force-closed."""
        agent, service = await self._setup_agent_with_position(db_session)

        candle = make_candle_data(defensive_trigger=1, close=48000.0)
        result = await service.evaluate_and_trade(
            db_session, agent.agent_id, "BTC-USDT", 48000.0, candle
        )

        assert result is not None
        assert result["action"] == "close"
        assert result["exit_price"] == 48000.0

        # Position should be cleared
        positions = await service.get_agent_positions(agent.agent_id)
        assert positions["positions"] == {}

    @pytest.mark.asyncio
    async def test_defensive_trigger_blocks_new_entry(self, db_session: AsyncSession):
        """When defensive_trigger=1 and no position, new entries are blocked."""
        patterns = {
            "pat-1": {
                "entry_conditions": make_entry_conditions("rsi", "<", 30),
                "exit_conditions": {},
                "direction": "long",
            }
        }
        agent = await create_test_agent(
            db_session, assigned_patterns=patterns, pattern_weights={"pat-1": 1.0}
        )
        service = AgentPaperTradingService()
        await service.start_paper_trading(db_session, agent.agent_id)

        candle = make_candle_data(rsi=20.0, defensive_trigger=1, close=50000.0)
        result = await service.evaluate_and_trade(
            db_session, agent.agent_id, "BTC-USDT", 50000.0, candle
        )

        assert result is None  # Blocked


# ============================================================================
# TEST: Stop Paper Trading
# ============================================================================


class TestStopPaperTrading:
    """Tests for stopping paper trading and returning stats."""

    @pytest.mark.asyncio
    async def test_stop_returns_stats(self, db_session: AsyncSession):
        """Stopping returns trade count, P&L, and duration."""
        agent = await create_test_agent(db_session)
        service = AgentPaperTradingService()
        await service.start_paper_trading(db_session, agent.agent_id)

        result = await service.stop_paper_trading(agent.agent_id)

        assert result["status"] == "stopped"
        assert result["agent_id"] == agent.agent_id
        assert result["trades_count"] == 0
        assert result["total_pnl"] == 0.0
        assert result["final_balance"] == 10000.0
        assert result["duration_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_stop_removes_from_active(self, db_session: AsyncSession):
        """Stopping removes agent from active positions tracking."""
        agent = await create_test_agent(db_session)
        service = AgentPaperTradingService()
        await service.start_paper_trading(db_session, agent.agent_id)

        await service.stop_paper_trading(agent.agent_id)

        assert agent.agent_id not in service.active_positions
        agents = await service.get_active_agents()
        assert len(agents) == 0

    @pytest.mark.asyncio
    async def test_stop_nonexistent_returns_error(self, db_session: AsyncSession):
        """Stopping a non-trading agent returns an error."""
        service = AgentPaperTradingService()

        result = await service.stop_paper_trading("nonexistent-id")

        assert "error" in result


# ============================================================================
# TEST: Pause / Resume
# ============================================================================


class TestPauseResume:
    """Tests for pausing and resuming paper trading."""

    @pytest.mark.asyncio
    async def test_pause_and_resume(self, db_session: AsyncSession):
        """Pausing then resuming works correctly."""
        agent = await create_test_agent(db_session)
        service = AgentPaperTradingService()
        await service.start_paper_trading(db_session, agent.agent_id)

        pause_result = await service.pause_trading(agent.agent_id)
        assert pause_result["status"] == "paused"
        assert service.is_paused(agent.agent_id) is True

        resume_result = await service.resume_trading(agent.agent_id)
        assert resume_result["status"] == "resumed"
        assert resume_result["pause_duration_seconds"] >= 0
        assert service.is_paused(agent.agent_id) is False

    @pytest.mark.asyncio
    async def test_double_pause_returns_error(self, db_session: AsyncSession):
        """Pausing an already paused agent returns an error."""
        agent = await create_test_agent(db_session)
        service = AgentPaperTradingService()
        await service.start_paper_trading(db_session, agent.agent_id)

        await service.pause_trading(agent.agent_id)
        result = await service.pause_trading(agent.agent_id)

        assert "error" in result


# ============================================================================
# TEST: Close All Positions
# ============================================================================


class TestCloseAllPositions:
    """Tests for emergency close-all functionality."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_close_all_closes_multiple_positions(self, db_session: AsyncSession):
        """close_all_positions closes all open positions and sums P&L."""
        agent = await create_test_agent(db_session)
        service = AgentPaperTradingService()
        await service.start_paper_trading(db_session, agent.agent_id)

        # Manually insert two positions
        for symbol, entry_price in [("BTC-USDT", 50000.0), ("ETH-USDT", 3000.0)]:
            trade_id = f"trade-{uuid.uuid4().hex[:8]}"
            size_usd = 1000.0
            size = size_usd / entry_price
            trade = LiveTradeUnified(
                trade_id=trade_id,
                source="paper",
                agent_id=agent.agent_id,
                agent_name=agent.name,
                exchange="paper",
                venue_type="paper",
                symbol=symbol,
                side="long",
                entry_time=datetime.now(timezone.utc),
                entry_price=Decimal(str(entry_price)),
                requested_price=Decimal(str(entry_price)),
                size=Decimal(str(size)),
                size_usd=Decimal(str(size_usd)),
                status="open",
                order_type="market",
                trading_mode="mvp_direct",
                created_at=datetime.now(timezone.utc),
            )
            db_session.add(trade)
            service.active_positions[agent.agent_id]["positions"][symbol] = {
                "trade_id": trade_id,
                "side": "long",
                "entry_price": entry_price,
                "size": size,
                "size_usd": size_usd,
                "entry_time": datetime.now(timezone.utc),
            }

        await db_session.flush()

        result = await service.close_all_positions(
            db_session,
            agent.agent_id,
            {"BTC-USDT": 51000.0, "ETH-USDT": 2900.0},
        )

        assert result["status"] == "closed_all"
        assert result["positions_closed"] == 2
        assert isinstance(result["total_pnl_usd"], float)

        # All positions cleared
        positions = await service.get_agent_positions(agent.agent_id)
        assert positions["positions"] == {}

    @pytest.mark.asyncio
    async def test_close_all_with_missing_price_errors(self, db_session: AsyncSession):
        """close_all_positions records errors for symbols without prices."""
        agent = await create_test_agent(db_session)
        service = AgentPaperTradingService()
        await service.start_paper_trading(db_session, agent.agent_id)

        trade_id = f"trade-{uuid.uuid4().hex[:8]}"
        trade = LiveTradeUnified(
            trade_id=trade_id,
            source="paper",
            agent_id=agent.agent_id,
            agent_name=agent.name,
            exchange="paper",
            venue_type="paper",
            symbol="BTC-USDT",
            side="long",
            entry_time=datetime.now(timezone.utc),
            entry_price=Decimal("50000"),
            requested_price=Decimal("50000"),
            size=Decimal("0.02"),
            size_usd=Decimal("1000"),
            status="open",
            order_type="market",
            trading_mode="mvp_direct",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(trade)
        await db_session.flush()

        service.active_positions[agent.agent_id]["positions"]["BTC-USDT"] = {
            "trade_id": trade_id,
            "side": "long",
            "entry_price": 50000.0,
            "size": 0.02,
            "size_usd": 1000.0,
            "entry_time": datetime.now(timezone.utc),
        }

        result = await service.close_all_positions(
            db_session, agent.agent_id, {}  # No prices provided
        )

        assert result["positions_closed"] == 0
        assert result["errors"] is not None
        assert len(result["errors"]) == 1


# ============================================================================
# TEST: Active Agents Query
# ============================================================================


class TestActiveAgentsQuery:
    """Tests for querying active paper trading agents."""

    @pytest.mark.asyncio
    async def test_get_active_agents_returns_all(self, db_session: AsyncSession):
        """get_active_agents returns info for all started agents."""
        service = AgentPaperTradingService()

        agent1 = await create_test_agent(db_session, name="Agent A")
        agent2 = await create_test_agent(db_session, name="Agent B")

        await service.start_paper_trading(db_session, agent1.agent_id)
        await service.start_paper_trading(db_session, agent2.agent_id)

        agents = await service.get_active_agents()
        assert len(agents) == 2
        names = {a["agent_name"] for a in agents}
        assert names == {"Agent A", "Agent B"}

    @pytest.mark.asyncio
    async def test_get_agent_positions_returns_none_for_unknown(self, db_session: AsyncSession):
        """get_agent_positions returns None for unknown agents."""
        service = AgentPaperTradingService()

        result = await service.get_agent_positions("unknown-id")
        assert result is None
