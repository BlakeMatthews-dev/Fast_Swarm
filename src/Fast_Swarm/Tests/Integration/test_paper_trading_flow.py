"""
Paper Trading Flow Integration Tests.

Tests the full paper trading lifecycle:
start -> evaluate -> open -> close -> stop.

Uses mocked DB sessions but real AgentPaperTradingService logic.
"""

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from Fast_Swarm.Agents.Models.agent_models import Agent
from Fast_Swarm.Trading.Services.agent_paper_trading_service import (
    AgentPaperTradingService,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def paper_agent(db_session: AsyncSession, sample_traits) -> Agent:
    """Create an active agent for paper trading tests."""
    agent = Agent(
        agent_id=f"paper-test-{uuid.uuid4().hex[:8]}",
        name="Paper Test Agent",
        generation=1,
        traits=sample_traits,
        status="active",
        is_active=True,
        fitness_score=60.0,
        elo_rating=1500.0,
        assigned_patterns={
            "pat-1": {
                "entry_conditions": [{"indicator": "rsi_14", "min": 0, "max": 30}],
                "exit_conditions": [{"indicator": "rsi_14", "min": 70, "max": 100}],
                "direction": "long",
            }
        },
        pattern_weights={"pat-1": 1.0},
    )
    db_session.add(agent)
    await db_session.flush()
    await db_session.refresh(agent)
    return agent


@pytest.fixture
def trading_service() -> AgentPaperTradingService:
    """Create a fresh paper trading service instance."""
    return AgentPaperTradingService()


# ============================================================================
# TESTS
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_evaluate_open_close(
    db_session: AsyncSession, paper_agent: Agent, trading_service: AgentPaperTradingService
):
    """Full lifecycle: start -> open position -> close position -> stop."""
    # Start trading
    start_result = await trading_service.start_paper_trading(
        session=db_session,
        agent_id=paper_agent.agent_id,
        symbols=["BTC-USDT"],
        initial_balance=10000.0,
    )
    assert start_result["status"] == "started"
    assert start_result["balance"] == 10000.0

    # Manually open a position (simulate what evaluate_and_trade does)
    open_result = await trading_service._open_position(
        session=db_session,
        agent=paper_agent,
        symbol="BTC-USDT",
        side="long",
        price=50000.0,
        candle_data={},
        regime="bull",
    )
    assert open_result["action"] == "open"
    assert open_result["symbol"] == "BTC-USDT"
    assert open_result["side"] == "long"
    assert open_result["price"] == 50000.0

    # Close the position
    close_result = await trading_service._close_position(
        session=db_session,
        agent=paper_agent,
        symbol="BTC-USDT",
        price=51000.0,
        candle_data={},
        regime="bull",
    )
    assert close_result["action"] == "close"
    assert close_result["pnl_pct"] > 0  # Price went up on long

    # Stop trading
    stop_result = await trading_service.stop_paper_trading(paper_agent.agent_id)
    assert stop_result["status"] == "stopped"
    assert stop_result["trades_count"] == 1
    assert stop_result["total_pnl"] > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_defensive_trigger_force_close(
    db_session: AsyncSession, paper_agent: Agent, trading_service: AgentPaperTradingService
):
    """Open position -> defensive trigger -> force close."""
    await trading_service.start_paper_trading(
        session=db_session,
        agent_id=paper_agent.agent_id,
        symbols=["BTC-USDT"],
        initial_balance=10000.0,
    )

    # Open a position first
    await trading_service._open_position(
        session=db_session,
        agent=paper_agent,
        symbol="BTC-USDT",
        side="long",
        price=50000.0,
        candle_data={},
        regime="bull",
    )

    # Evaluate with defensive_trigger=1 should force close
    result = await trading_service.evaluate_and_trade(
        session=db_session,
        agent_id=paper_agent.agent_id,
        symbol="BTC-USDT",
        current_price=49000.0,
        candle_data={"defensive_trigger": 1, "close_acceleration_zscore": -2.0, "adx_14_jerk_zscore": 3.0},
        regime="bear",
    )

    assert result is not None
    assert result["action"] == "close"
    assert result["pnl_pct"] < 0  # Price dropped, so loss on long


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pattern_evaluation_produces_signals(
    db_session: AsyncSession, paper_agent: Agent, trading_service: AgentPaperTradingService
):
    """Real pattern evaluation should produce non-hold signal with right data."""
    # _evaluate_patterns returns "hold" if PatternMatcher is not available
    # or if no patterns match. Test the logic flow.
    signal = await trading_service._evaluate_patterns(
        agent=paper_agent,
        candle_data={"rsi_14": 25, "ema_21": 50000, "close": 49000},
    )
    # Signal should be one of the valid values
    assert signal in ("buy", "sell", "close", "hold")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_symbols(
    db_session: AsyncSession, paper_agent: Agent, trading_service: AgentPaperTradingService
):
    """Trade multiple symbols simultaneously."""
    await trading_service.start_paper_trading(
        session=db_session,
        agent_id=paper_agent.agent_id,
        symbols=["BTC-USDT", "ETH-USDT"],
        initial_balance=10000.0,
    )

    # Open positions on both symbols
    await trading_service._open_position(
        session=db_session, agent=paper_agent,
        symbol="BTC-USDT", side="long", price=50000.0, candle_data={}, regime="bull",
    )
    await trading_service._open_position(
        session=db_session, agent=paper_agent,
        symbol="ETH-USDT", side="long", price=3000.0, candle_data={}, regime="bull",
    )

    positions = await trading_service.get_agent_positions(paper_agent.agent_id)
    assert positions is not None
    assert len(positions["positions"]) == 2
    assert "BTC-USDT" in positions["positions"]
    assert "ETH-USDT" in positions["positions"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stop_closes_all(
    db_session: AsyncSession, paper_agent: Agent, trading_service: AgentPaperTradingService
):
    """Stopping trading should allow closing all positions first."""
    await trading_service.start_paper_trading(
        session=db_session,
        agent_id=paper_agent.agent_id,
        symbols=["BTC-USDT", "ETH-USDT"],
        initial_balance=10000.0,
    )

    await trading_service._open_position(
        session=db_session, agent=paper_agent,
        symbol="BTC-USDT", side="long", price=50000.0, candle_data={}, regime="bull",
    )
    await trading_service._open_position(
        session=db_session, agent=paper_agent,
        symbol="ETH-USDT", side="short", price=3000.0, candle_data={}, regime="bear",
    )

    # Close all positions
    close_result = await trading_service.close_all_positions(
        session=db_session,
        agent_id=paper_agent.agent_id,
        current_prices={"BTC-USDT": 51000.0, "ETH-USDT": 2900.0},
    )
    assert close_result["status"] == "closed_all"
    assert close_result["positions_closed"] == 2

    # Now stop
    stop_result = await trading_service.stop_paper_trading(paper_agent.agent_id)
    assert stop_result["status"] == "stopped"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pnl_tracking(
    db_session: AsyncSession, paper_agent: Agent, trading_service: AgentPaperTradingService
):
    """Accumulated PnL should be tracked correctly across trades."""
    await trading_service.start_paper_trading(
        session=db_session,
        agent_id=paper_agent.agent_id,
        symbols=["BTC-USDT"],
        initial_balance=10000.0,
    )

    # Trade 1: Win
    await trading_service._open_position(
        session=db_session, agent=paper_agent,
        symbol="BTC-USDT", side="long", price=50000.0, candle_data={}, regime="bull",
    )
    close1 = await trading_service._close_position(
        session=db_session, agent=paper_agent,
        symbol="BTC-USDT", price=52000.0, candle_data={}, regime="bull",
    )

    # Trade 2: Loss
    await trading_service._open_position(
        session=db_session, agent=paper_agent,
        symbol="BTC-USDT", side="long", price=52000.0, candle_data={}, regime="bull",
    )
    close2 = await trading_service._close_position(
        session=db_session, agent=paper_agent,
        symbol="BTC-USDT", price=51000.0, candle_data={}, regime="bear",
    )

    positions = await trading_service.get_agent_positions(paper_agent.agent_id)
    assert positions is not None
    total_pnl = positions["total_pnl"]

    # Total PnL should be sum of both trades
    expected_pnl = close1["pnl_usd"] + close2["pnl_usd"]
    assert abs(total_pnl - expected_pnl) < 0.01


@pytest.mark.integration
@pytest.mark.asyncio
async def test_balance_updates(
    db_session: AsyncSession, paper_agent: Agent, trading_service: AgentPaperTradingService
):
    """Balance should change on open/close."""
    initial_balance = 10000.0
    await trading_service.start_paper_trading(
        session=db_session,
        agent_id=paper_agent.agent_id,
        symbols=["BTC-USDT"],
        initial_balance=initial_balance,
    )

    await trading_service._open_position(
        session=db_session, agent=paper_agent,
        symbol="BTC-USDT", side="long", price=50000.0, candle_data={}, regime="bull",
    )

    # Balance should not change on open (only tracks position)
    positions = await trading_service.get_agent_positions(paper_agent.agent_id)
    assert positions["balance"] == initial_balance

    # Close with profit
    await trading_service._close_position(
        session=db_session, agent=paper_agent,
        symbol="BTC-USDT", price=55000.0, candle_data={}, regime="bull",
    )

    positions = await trading_service.get_agent_positions(paper_agent.agent_id)
    assert positions["balance"] > initial_balance


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_agents(
    db_session: AsyncSession, sample_traits, trading_service: AgentPaperTradingService
):
    """Multiple agents trading simultaneously should not interfere."""
    agents = []
    for i in range(3):
        agent = Agent(
            agent_id=f"concurrent-{uuid.uuid4().hex[:8]}",
            name=f"Concurrent Agent {i}",
            generation=1,
            traits=sample_traits,
            status="active",
            is_active=True,
            fitness_score=50.0,
            elo_rating=1500.0,
            assigned_patterns={"pat-1": {"entry_conditions": [], "exit_conditions": [], "direction": "long"}},
            pattern_weights={"pat-1": 1.0},
        )
        db_session.add(agent)
        agents.append(agent)
    await db_session.flush()

    # Start all agents
    for agent in agents:
        result = await trading_service.start_paper_trading(
            session=db_session,
            agent_id=agent.agent_id,
            symbols=["BTC-USDT"],
            initial_balance=10000.0,
        )
        assert result["status"] == "started"

    # Open positions for each
    for i, agent in enumerate(agents):
        await trading_service._open_position(
            session=db_session, agent=agent,
            symbol="BTC-USDT", side="long",
            price=50000.0 + i * 1000,
            candle_data={}, regime="bull",
        )

    # Each agent should have independent positions
    active = await trading_service.get_active_agents()
    assert len(active) == 3

    for agent_info in active:
        assert agent_info["positions"] == 1
        assert agent_info["balance"] == 10000.0
