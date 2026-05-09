"""
Real-DB integration tests for EvolutionCycleService.

Uses db_session fixture (PostgreSQL with transaction rollback).
Tests the orchestration of evolution phases with real agents in the database.
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from Fast_Swarm.Agents.Models.agent_models import Agent
from Fast_Swarm.Agents.Services.ranking_service import AgentRankingService
from Fast_Swarm.Agents.Services.spawn_service import AgentSpawnService, spawn_and_persist
from Fast_Swarm.Patterns.Models.pattern_models import Pattern
from Fast_Swarm.System.Services.state_cache_service import StateCacheService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(
    agent_id: str | None = None,
    fitness: float = 50.0,
    generation: int = 1,
    level: int = 1,
    status: str = "active",
    traits: dict | None = None,
) -> Agent:
    """Build an Agent instance (not yet added to session)."""
    return Agent(
        agent_id=agent_id or f"test-{uuid.uuid4().hex[:8]}",
        name=f"TestAgent-{uuid.uuid4().hex[:4]}",
        generation=generation,
        level=level,
        traits=traits or _default_traits(),
        status=status,
        is_active=(status == "active"),
        fitness_score=Decimal(str(fitness)),
        elo_rating=Decimal("1500"),
    )


def _default_traits() -> dict[str, float]:
    return {
        "risk_tolerance": 0.5, "hold_duration_bias": 0.5, "volatility_seeking": 0.5,
        "profit_target_greed": 0.5, "win_rate_preference": 0.5, "drawdown_sensitivity": 0.5,
        "momentum_vs_reversion": 0.5, "stop_loss_tightness": 0.5, "entry_aggression": 0.5,
        "exit_aggression": 0.5, "lookback_preference": 0.5, "sentiment_weight": 0.5,
        "news_reactivity": 0.5, "sentiment_contrarian": 0.5, "funding_rate_sensitivity": 0.5,
        "correlation_awareness": 0.5, "patience": 0.5, "adaptability": 0.5,
        "trend_following": 0.5, "mean_reversion": 0.5, "breakout_preference": 0.5,
        "volume_sensitivity": 0.5,
    }


def _make_pattern(pattern_id: str | None = None, fitness: float = 60.0) -> Pattern:
    """Build a Pattern instance."""
    return Pattern(
        pattern_id=pattern_id or f"pat-{uuid.uuid4().hex[:8]}",
        name=f"TestPattern-{uuid.uuid4().hex[:4]}",
        origin="technical",
        status="untested",
        is_active=True,
        entry_conditions=[{"indicator": "rsi", "min": 20, "max": 35}],
        exit_conditions=[{"indicator": "rsi", "min": 65, "max": 80}],
        fitness_score=Decimal(str(fitness)),
        total_trades=0,
        total_runs=0,
    )


async def _seed_population(session: AsyncSession, count: int = 20) -> list[Agent]:
    """Seed a population of agents with varying fitness."""
    agents = []
    for i in range(count):
        agent = _make_agent(fitness=float(i * 5), generation=(i % 3) + 1, level=(i % 10) + 1)
        session.add(agent)
        agents.append(agent)
    await session.flush()
    for a in agents:
        await session.refresh(a)
    return agents


async def _seed_patterns(session: AsyncSession, count: int = 5) -> list[Pattern]:
    """Seed patterns into DB."""
    patterns = []
    for i in range(count):
        p = _make_pattern(fitness=50.0 + i * 10)
        session.add(p)
        patterns.append(p)
    await session.flush()
    for p in patterns:
        await session.refresh(p)
    return patterns


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.requires_db
class TestEvolutionCyclePopulation:
    """Tests for population management during evolution cycles."""

    async def test_spawn_service_creates_agents_in_db(self, db_session: AsyncSession, sample_traits):
        """spawn_and_persist should insert real Agent rows."""
        ids = await spawn_and_persist(db_session, count=3, generation=1)
        assert len(ids) == 3

        for aid in ids:
            result = await db_session.execute(select(Agent).where(Agent.agent_id == aid))
            agent = result.scalars().first()
            assert agent is not None
            assert agent.status == "active"
            assert len(agent.traits) == 22

    async def test_ranking_service_orders_by_fitness(self, db_session: AsyncSession):
        """Agents should be ranked descending by fitness_score."""
        agents = await _seed_population(db_session, count=10)
        svc = AgentRankingService()
        ranked = await svc.rank_agents(session=db_session)

        assert len(ranked) == 10
        scores = [float(r["fitness_score"]) for r in ranked]
        assert scores == sorted(scores, reverse=True)

    async def test_get_all_agents_ranked_returns_agent_objects(self, db_session: AsyncSession):
        """get_all_agents_ranked should return Agent model instances."""
        await _seed_population(db_session, count=5)
        svc = AgentRankingService()
        agents = await svc.get_all_agents_ranked(session=db_session)

        assert len(agents) == 5
        assert all(isinstance(a, Agent) for a in agents)
        # Verify descending order
        scores = [float(a.fitness_score) for a in agents]
        assert scores == sorted(scores, reverse=True)

    async def test_population_stats_with_real_agents(self, db_session: AsyncSession):
        """calculate_population_stats should return correct aggregates."""
        agents = await _seed_population(db_session, count=10)
        svc = AgentRankingService()
        stats = await svc.calculate_population_stats(session=db_session)

        assert stats["total_agents"] == 10
        assert stats["max_fitness"] == float(max(a.fitness_score for a in agents))
        assert stats["min_fitness"] == float(min(a.fitness_score for a in agents))
        assert stats["avg_fitness"] > 0

    async def test_top_agents_returns_correct_count(self, db_session: AsyncSession):
        """get_top_agents should respect the limit parameter."""
        await _seed_population(db_session, count=20)
        svc = AgentRankingService()
        top5 = await svc.get_top_agents(session=db_session, top_n=5)

        assert len(top5) == 5
        # Should be the 5 highest fitness agents
        all_ranked = await svc.get_all_agents_ranked(session=db_session)
        assert [a.agent_id for a in top5] == [a.agent_id for a in all_ranked[:5]]

    async def test_bottom_agents_returns_lowest_fitness(self, db_session: AsyncSession):
        """get_bottom_agents should return the lowest fitness agents."""
        await _seed_population(db_session, count=20)
        svc = AgentRankingService()
        bottom5 = await svc.get_bottom_agents(session=db_session, bottom_n=5)

        assert len(bottom5) == 5
        # Bottom agents should have the lowest fitness
        scores = [float(a.fitness_score) for a in bottom5]
        assert scores == sorted(scores)

    async def test_spawn_child_persists_with_parents(self, db_session: AsyncSession):
        """Spawning a child from two parents should persist the child and level up parents."""
        parent_a = _make_agent(fitness=80.0, level=3)
        parent_b = _make_agent(fitness=75.0, level=4)
        db_session.add(parent_a)
        db_session.add(parent_b)
        await db_session.flush()

        svc = AgentSpawnService()
        child_id = await svc.spawn_child(
            session=db_session,
            parent_a_id=parent_a.agent_id,
            parent_b_id=parent_b.agent_id,
            mutation_rate=0.1,
        )

        # Verify child exists
        result = await db_session.execute(select(Agent).where(Agent.agent_id == child_id))
        child = result.scalars().first()
        assert child is not None
        assert child.parent_a_id == parent_a.agent_id
        assert child.parent_b_id == parent_b.agent_id
        assert child.generation == max(parent_a.generation, parent_b.generation) + 1

        # Verify parents leveled up
        await db_session.refresh(parent_a)
        await db_session.refresh(parent_b)
        assert parent_a.level == 4  # was 3
        assert parent_b.level == 5  # was 4

    async def test_empty_population_detected(self, db_session: AsyncSession):
        """With no agents, the ranking service should return empty."""
        svc = AgentRankingService()
        ranked = await svc.rank_agents(session=db_session)
        assert ranked == []

        stats = await svc.calculate_population_stats(session=db_session)
        assert stats["total_agents"] == 0

    async def test_retired_agents_excluded_from_ranking(self, db_session: AsyncSession):
        """Only active agents should appear in rankings."""
        active = _make_agent(fitness=80.0, status="active")
        retired = _make_agent(fitness=90.0, status="retired")
        culled = _make_agent(fitness=10.0, status="culled")
        db_session.add_all([active, retired, culled])
        await db_session.flush()

        svc = AgentRankingService()
        ranked = await svc.rank_agents(session=db_session)

        assert len(ranked) == 1
        assert ranked[0]["agent_id"] == active.agent_id

    async def test_state_cache_loads_from_real_db(self, db_session: AsyncSession):
        """StateCacheService should load real agents and patterns into cache."""
        await _seed_population(db_session, count=5)
        await _seed_patterns(db_session, count=3)

        cache = StateCacheService()
        await cache.refresh_caches(db_session)
        stats = cache.get_cache_stats()

        assert stats["pattern_cache_loaded"] is True
        assert stats["agent_index_loaded"] is True
        assert stats["pattern_cache_size"] >= 3
        assert stats["agent_index_size"] >= 5

    async def test_top_percentile_agents(self, db_session: AsyncSession):
        """get_top_agents with top_percentile should return correct fraction."""
        await _seed_population(db_session, count=20)
        svc = AgentRankingService()

        # Top 10% of 20 = 2 agents
        top10pct = await svc.get_top_agents(session=db_session, top_percentile=0.10)
        assert len(top10pct) == 2

    async def test_bottom_percentile_agents(self, db_session: AsyncSession):
        """get_bottom_agents with bottom_percentile should return correct fraction."""
        await _seed_population(db_session, count=20)
        svc = AgentRankingService()

        # Bottom 20% of 20 = 4 agents
        bottom20pct = await svc.get_bottom_agents(session=db_session, bottom_percentile=0.20)
        assert len(bottom20pct) == 4

    async def test_level_increment_persists(self, db_session: AsyncSession):
        """Directly incrementing agent level should persist in DB."""
        agent = _make_agent(level=5)
        db_session.add(agent)
        await db_session.flush()

        agent.level += 2
        db_session.add(agent)
        await db_session.flush()
        await db_session.refresh(agent)

        assert agent.level == 7
