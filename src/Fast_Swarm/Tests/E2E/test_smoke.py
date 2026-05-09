"""
E2E Smoke Test - Full Pipeline Validation.

One comprehensive test that exercises the entire CoinSwarm pipeline:
Create patterns -> Spawn agents -> Backtest (mocked) -> Rank -> Evolution -> Paper trade -> Evaluate -> Stop.

This is a slow test that validates end-to-end data flow.
"""

import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from Fast_Swarm.Agents.Models.agent_models import Agent
from Fast_Swarm.Agents.Services.cull_service import AgentCullService
from Fast_Swarm.Agents.Services.ranking_service import AgentRankingService
from Fast_Swarm.Agents.Services.spawn_service import AgentSpawnService
from Fast_Swarm.Patterns.Models.pattern_models import Pattern
from Fast_Swarm.Patterns.Services.pattern_service import create_pattern, get_tiers_by_quintile
from Fast_Swarm.Trading.Services.agent_paper_trading_service import AgentPaperTradingService


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_full_pipeline_smoke(db_session: AsyncSession, sample_traits):
    """
    End-to-end pipeline:
    1. Create 5 patterns
    2. Spawn 20 agents with those patterns
    3. Simulate backtest (set fitness scores)
    4. Rank agents
    5. Run evolution cycle (cull + spawn replacements)
    6. Paper trade the top agent
    7. Evaluate a candle
    8. Stop trading

    Each step asserts valid output before proceeding.
    """

    # ====================================================================
    # Step 1: Create 5 patterns
    # ====================================================================
    patterns = []
    for i in range(5):
        pattern = await create_pattern(
            session=db_session,
            name=f"Smoke Pattern {i}",
            entry_conditions=[{"indicator": "rsi_14", "min": 15 + i * 5, "max": 35 + i * 5}],
            exit_conditions=[{"indicator": "rsi_14", "min": 65 + i * 3, "max": 85 + i * 3}],
            origin="technical",
        )
        patterns.append(pattern)

    assert len(patterns) == 5
    for p in patterns:
        assert p.pattern_id is not None
        assert p.fitness_score == 50.0  # Default

    # Convert patterns to spawn-compatible format
    available_patterns = [
        {
            "pattern_id": p.pattern_id,
            "entry_conditions": p.entry_conditions,
            "exit_conditions": p.exit_conditions,
            "type": "momentum",
            "fitness_score": p.fitness_score or 50.0,
            "win_rate": 0.55,
            "volatility": 0.5,
        }
        for p in patterns
    ]

    # ====================================================================
    # Step 2: Spawn 20 agents
    # ====================================================================
    spawn_svc = AgentSpawnService()
    agent_ids = await spawn_svc.spawn_new_agents(
        session=db_session,
        count=20,
        generation=1,
        available_patterns=available_patterns,
    )

    assert len(agent_ids) == 20
    for aid in agent_ids:
        assert aid.startswith("agent-")

    # ====================================================================
    # Step 3: Simulate backtest (set fitness scores)
    # ====================================================================
    ranking_svc = AgentRankingService()
    all_agents = await ranking_svc.get_all_agents_ranked(session=db_session)
    assert len(all_agents) >= 20

    # Assign varying fitness to simulate backtest results
    for i, agent in enumerate(all_agents):
        agent.fitness_score = float(i * 5)
        agent.backtest_count = 5
        db_session.add(agent)
    await db_session.flush()

    # ====================================================================
    # Step 4: Rank agents
    # ====================================================================
    rankings = await ranking_svc.rank_agents(session=db_session)
    assert len(rankings) >= 20

    # Rankings should be sorted by fitness descending
    fitness_values = [r["fitness_score"] for r in rankings]
    assert fitness_values == sorted(fitness_values, reverse=True)

    top_agent_id = rankings[0]["agent_id"]
    top_fitness = rankings[0]["fitness_score"]
    assert top_fitness > 0

    # ====================================================================
    # Step 5: Evolution cycle (cull bottom 30% + spawn replacements)
    # ====================================================================
    cull_svc = AgentCullService()
    cull_result = await cull_svc.cull_agents(
        session=db_session,
        cull_percentile=0.3,
        min_population=10,
    )
    assert cull_result["culled_count"] > 0
    assert cull_result["remaining_count"] >= 10

    # Spawn replacements
    replacement_count = cull_result["culled_count"]
    new_ids = await spawn_svc.spawn_new_agents(
        session=db_session,
        count=min(replacement_count, 10),
        generation=2,
        available_patterns=available_patterns,
    )
    assert len(new_ids) > 0

    # ====================================================================
    # Step 6: Paper trade the top agent
    # ====================================================================
    trading_svc = AgentPaperTradingService()

    # Fetch the top agent from DB
    result = await db_session.execute(
        select(Agent).where(Agent.agent_id == top_agent_id)
    )
    top_agent = result.scalars().first()
    assert top_agent is not None
    assert top_agent.status == "active"

    start_result = await trading_svc.start_paper_trading(
        session=db_session,
        agent_id=top_agent.agent_id,
        symbols=["BTC-USDT"],
        initial_balance=10000.0,
    )
    assert start_result["status"] == "started"

    # ====================================================================
    # Step 7: Evaluate a candle (open a position manually)
    # ====================================================================
    open_result = await trading_svc._open_position(
        session=db_session,
        agent=top_agent,
        symbol="BTC-USDT",
        side="long",
        price=50000.0,
        candle_data={"rsi_14": 25, "ema_21": 49000, "close": 50000},
        regime="bull",
    )
    assert open_result["action"] == "open"
    assert open_result["trade_id"] is not None

    # Close with profit
    close_result = await trading_svc._close_position(
        session=db_session,
        agent=top_agent,
        symbol="BTC-USDT",
        price=51000.0,
        candle_data={"rsi_14": 72, "ema_21": 50500, "close": 51000},
        regime="bull",
    )
    assert close_result["action"] == "close"
    assert close_result["pnl_pct"] > 0

    # ====================================================================
    # Step 8: Stop trading
    # ====================================================================
    stop_result = await trading_svc.stop_paper_trading(top_agent.agent_id)
    assert stop_result["status"] == "stopped"
    assert stop_result["trades_count"] == 1
    assert stop_result["total_pnl"] > 0
    assert stop_result["final_balance"] > 10000.0

    # ====================================================================
    # Final validation: population is healthy
    # ====================================================================
    final_agents = await ranking_svc.get_all_agents_ranked(session=db_session)
    assert len(final_agents) >= 10, f"Population too small: {len(final_agents)}"
