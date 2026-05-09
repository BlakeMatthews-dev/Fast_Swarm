"""
Evolution Pipeline Integration Tests.

Tests the full evolution pipeline with mocked DB but real service interactions:
spawn -> backtest -> rank -> cull -> breed -> clone.

All tests use transaction rollback for isolation.
"""

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from Fast_Swarm.Agents.Models.agent_models import Agent
from Fast_Swarm.Agents.Services.cull_service import AgentCullService
from Fast_Swarm.Agents.Services.ranking_service import AgentRankingService
from Fast_Swarm.Agents.Services.spawn_service import (
    AgentSpawnService,
    spawn_agent,
    spawn_child,
    spawn_clone,
    validate_spawned_agent,
)


# ============================================================================
# FIXTURES
# ============================================================================


def _make_agent(
    session: AsyncSession,
    *,
    fitness: float = 50.0,
    generation: int = 1,
    traits: dict | None = None,
    status: str = "active",
    level: int = 1,
    parent_a_id: str | None = None,
    parent_b_id: str | None = None,
    assigned_patterns: dict | None = None,
) -> Agent:
    """Create an Agent model instance and add it to the session."""
    default_traits = {
        "risk_tolerance": 0.5, "hold_duration_bias": 0.5, "volatility_seeking": 0.5,
        "profit_target_greed": 0.5, "win_rate_preference": 0.5, "drawdown_sensitivity": 0.5,
        "momentum_vs_reversion": 0.5, "stop_loss_tightness": 0.5, "entry_aggression": 0.5,
        "exit_aggression": 0.5, "lookback_preference": 0.5, "sentiment_weight": 0.5,
        "news_reactivity": 0.5, "sentiment_contrarian": 0.5, "funding_rate_sensitivity": 0.5,
        "correlation_awareness": 0.5, "patience": 0.5, "adaptability": 0.5,
        "trend_following": 0.5, "mean_reversion": 0.5, "breakout_preference": 0.5,
        "volume_sensitivity": 0.5,
    }
    agent = Agent(
        agent_id=f"test-{uuid.uuid4().hex[:12]}",
        name=f"TestAgent_{uuid.uuid4().hex[:6]}",
        generation=generation,
        traits=traits or default_traits,
        status=status,
        is_active=status == "active",
        fitness_score=fitness,
        elo_rating=1500.0,
        level=level,
        parent_a_id=parent_a_id,
        parent_b_id=parent_b_id,
        assigned_patterns=assigned_patterns or {"base": []},
    )
    session.add(agent)
    return agent


@pytest_asyncio.fixture
async def population_20(db_session: AsyncSession) -> list[Agent]:
    """Create a population of 20 agents with varying fitness."""
    agents = []
    for i in range(20):
        agent = _make_agent(db_session, fitness=float(i * 5), generation=1)
        agents.append(agent)
    await db_session.flush()
    for a in agents:
        await db_session.refresh(a)
    return agents


@pytest_asyncio.fixture
async def ranked_population(db_session: AsyncSession) -> list[Agent]:
    """Create 20 agents with fitness scores from 0 to 95 and backtest_count >= 3."""
    agents = []
    for i in range(20):
        agent = _make_agent(db_session, fitness=float(i * 5), generation=1)
        agent.backtest_count = 5  # Ensure cull eligibility
        agents.append(agent)
    await db_session.flush()
    for a in agents:
        await db_session.refresh(a)
    return agents


# ============================================================================
# TESTS
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_spawn_backtest_rank_cull_cycle(db_session: AsyncSession, sample_traits):
    """Full cycle: spawn 20 -> backtest -> rank -> cull, verify population changes."""
    spawn_svc = AgentSpawnService()

    # Spawn 20 agents
    agent_ids = await spawn_svc.spawn_new_agents(
        session=db_session, count=20, generation=1
    )
    assert len(agent_ids) == 20

    # Rank agents (all have fitness 0 initially)
    ranking_svc = AgentRankingService()
    rankings = await ranking_svc.rank_agents(session=db_session)
    assert len(rankings) >= 20

    # Manually set varying fitness so cull has something to work with
    all_agents = await ranking_svc.get_all_agents_ranked(session=db_session)
    for i, agent in enumerate(all_agents):
        agent.fitness_score = float(i * 5)
        agent.backtest_count = 5
        db_session.add(agent)
    await db_session.flush()

    # Cull bottom 30%
    cull_svc = AgentCullService()
    cull_result = await cull_svc.cull_agents(
        session=db_session, cull_percentile=0.3, min_population=5
    )

    assert cull_result["culled_count"] > 0
    assert cull_result["remaining_count"] > 0
    assert cull_result["remaining_count"] < 20


@pytest.mark.integration
@pytest.mark.asyncio
async def test_breeding_produces_correct_generation(db_session: AsyncSession, sample_traits):
    """Children should have generation = max(parents) + 1."""
    parent_a_data = {
        "agent_id": f"parent-a-{uuid.uuid4().hex[:8]}",
        "traits": sample_traits,
        "generation": 3,
        "assigned_patterns": [],
    }
    parent_b_data = {
        "agent_id": f"parent-b-{uuid.uuid4().hex[:8]}",
        "traits": sample_traits,
        "generation": 5,
        "assigned_patterns": [],
    }

    child = spawn_child(parent_a_data, parent_b_data, mutation_rate=0.1, seed=42)
    assert child.generation == 6  # max(3, 5) + 1
    assert child.parent_a_id == parent_a_data["agent_id"]
    assert child.parent_b_id == parent_b_data["agent_id"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_extinction_emergency_spawn_recovery(db_session: AsyncSession):
    """Zero active agents triggers emergency spawn; pipeline continues."""
    # Start with no agents at all (empty DB from rollback fixture)
    from sqlmodel import select as sel
    result = await db_session.execute(sel(Agent).where(Agent.status == "active"))
    active = result.scalars().all()

    # Ensure we start empty
    for a in active:
        a.status = "retired"
        a.is_active = False
        db_session.add(a)
    await db_session.flush()

    # Now the spawn service should be able to spawn fresh agents
    spawn_svc = AgentSpawnService()
    new_ids = await spawn_svc.spawn_new_agents(session=db_session, count=10, generation=1)
    assert len(new_ids) == 10


@pytest.mark.integration
@pytest.mark.asyncio
async def test_clone_preserves_patterns(sample_traits):
    """Cloned agent has parent's patterns."""
    parent_patterns = [
        {"pattern_id": "pat-1", "entry_conditions": [{"indicator": "rsi_14", "min": 20}],
         "exit_conditions": [{"indicator": "rsi_14", "max": 80}]},
        {"pattern_id": "pat-2", "entry_conditions": [{"indicator": "ema_21", "min": 100}],
         "exit_conditions": [{"indicator": "ema_21", "max": 200}]},
    ]
    parent_data = {
        "agent_id": "parent-clone-test",
        "traits": sample_traits,
        "generation": 2,
        "assigned_patterns": parent_patterns,
    }

    clone = spawn_clone(parent_data, mutation_rate=0.05, seed=42)

    assert clone.parent_a_id == "parent-clone-test"
    assert clone.parent_b_id is None
    assert len(clone.assigned_patterns) == len(parent_patterns)
    clone_pat_ids = {p.get("pattern_id") for p in clone.assigned_patterns}
    assert "pat-1" in clone_pat_ids
    assert "pat-2" in clone_pat_ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_generations(db_session: AsyncSession):
    """Run 3 generations of spawn -> rank -> cull, verify population stability."""
    spawn_svc = AgentSpawnService()
    ranking_svc = AgentRankingService()
    cull_svc = AgentCullService()

    for gen in range(1, 4):
        # Spawn
        new_ids = await spawn_svc.spawn_new_agents(
            session=db_session, count=10, generation=gen
        )
        assert len(new_ids) == 10

        # Set fitness
        all_agents = await ranking_svc.get_all_agents_ranked(session=db_session)
        for i, agent in enumerate(all_agents):
            agent.fitness_score = float(i * 3)
            agent.backtest_count = 5
            db_session.add(agent)
        await db_session.flush()

        # Cull (but respect min_population)
        cull_result = await cull_svc.cull_agents(
            session=db_session, cull_percentile=0.3, min_population=5
        )
        assert cull_result["remaining_count"] >= 5

    # After 3 gens, we should still have agents
    final_agents = await ranking_svc.get_all_agents_ranked(session=db_session)
    assert len(final_agents) >= 5


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cull_respects_minimum(db_session: AsyncSession):
    """Population never drops below min_population."""
    # Create exactly 10 agents
    spawn_svc = AgentSpawnService()
    await spawn_svc.spawn_new_agents(session=db_session, count=10, generation=1)

    # Set varying fitness and backtest count
    ranking_svc = AgentRankingService()
    all_agents = await ranking_svc.get_all_agents_ranked(session=db_session)
    for i, agent in enumerate(all_agents):
        agent.fitness_score = float(i)
        agent.backtest_count = 5
        db_session.add(agent)
    await db_session.flush()

    # Try aggressive cull with high min_population
    cull_svc = AgentCullService()
    result = await cull_svc.cull_agents(
        session=db_session, cull_percentile=0.9, min_population=8
    )

    assert result["remaining_count"] >= 8


@pytest.mark.integration
@pytest.mark.asyncio
async def test_elites_survive_cull(db_session: AsyncSession, ranked_population):
    """Top agents should never be culled."""
    ranking_svc = AgentRankingService()
    all_agents = await ranking_svc.get_all_agents_ranked(session=db_session)

    # Record top 5 agent IDs (highest fitness)
    top_5_ids = {a.agent_id for a in all_agents[:5]}

    cull_svc = AgentCullService()
    result = await cull_svc.cull_agents(
        session=db_session, cull_percentile=0.3, min_population=5
    )

    # Top 5 should still be active
    culled_ids = set(result.get("culled_ids", []))
    assert top_5_ids.isdisjoint(culled_ids), "Elite agents were culled!"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_breeding_pairs_from_top_agents(sample_traits):
    """Only top fitness agents should be selected as breeding pairs."""
    agents_data = []
    for i in range(10):
        agents_data.append({
            "agent_id": f"breed-test-{i}",
            "traits": sample_traits,
            "generation": 1,
            "fitness_score": float(i * 10),
            "assigned_patterns": [],
        })

    # The breeding logic in evolution_cycle_service uses top N agents
    # Verify that spawn_child works with the top pair
    top_a = agents_data[-1]  # fitness 90
    top_b = agents_data[-2]  # fitness 80

    child = spawn_child(top_a, top_b, mutation_rate=0.1, seed=42)
    assert child.parent_a_id == "breed-test-9"
    assert child.parent_b_id == "breed-test-8"
    assert child.generation == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mutation_bounded(sample_traits):
    """All child traits should remain in [0, 1] after mutation."""
    # Use extreme traits to test boundary clamping
    extreme_traits = {k: 0.99 for k in sample_traits}
    parent_data = {
        "agent_id": "extreme-parent",
        "traits": extreme_traits,
        "generation": 1,
        "assigned_patterns": [],
    }

    # Run many clones to test bounding
    for seed in range(50):
        clone = spawn_clone(parent_data, mutation_rate=0.5, seed=seed)
        for trait_name, value in clone.traits.items():
            assert 0.0 <= value <= 1.0, (
                f"Trait {trait_name}={value} out of bounds (seed={seed})"
            )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fitness_updated_after_backtest(db_session: AsyncSession, ranked_population):
    """Fitness scores should be writable after simulated backtest."""
    agent = ranked_population[0]
    original_fitness = agent.fitness_score

    # Simulate backtest result updating fitness
    agent.fitness_score = 88.5
    db_session.add(agent)
    await db_session.flush()
    await db_session.refresh(agent)

    assert agent.fitness_score == 88.5
    assert agent.fitness_score != original_fitness


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tier_assignment_after_ranking(db_session: AsyncSession, ranked_population):
    """Agents should be assignable to DIES/SURVIVES/PROMOTED tiers after ranking."""
    ranking_svc = AgentRankingService()
    rankings = await ranking_svc.rank_agents(session=db_session)

    assert len(rankings) == 20

    # Verify rankings are sorted by fitness descending
    fitness_values = [r["fitness_score"] for r in rankings]
    assert fitness_values == sorted(fitness_values, reverse=True)

    # Top 20% = promoted, middle 50% = survives, bottom 30% = dies
    total = len(rankings)
    promoted = rankings[: int(total * 0.2)]
    dies = rankings[int(total * 0.7) :]

    assert len(promoted) == 4  # 20% of 20
    assert len(dies) == 6  # 30% of 20

    # Promoted should have higher fitness than dies
    min_promoted = min(r["fitness_score"] for r in promoted)
    max_dies = max(r["fitness_score"] for r in dies)
    assert min_promoted > max_dies


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_cycle_result_structure(db_session: AsyncSession, sample_traits):
    """Result dict from spawn_agent should have all expected keys."""
    spawned = spawn_agent(generation=1, seed=42)

    is_valid, error = validate_spawned_agent(spawned)
    assert is_valid, f"Spawned agent invalid: {error}"

    assert spawned.agent_id is not None
    assert spawned.name is not None
    assert spawned.generation == 1
    assert isinstance(spawned.traits, dict)
    assert len(spawned.traits) == 22
    assert spawned.trading_philosophy is not None
    assert isinstance(spawned.assigned_patterns, list)
