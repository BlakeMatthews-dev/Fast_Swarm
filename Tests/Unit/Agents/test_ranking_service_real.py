"""
Real-DB integration tests for AgentRankingService.

Uses db_session fixture (PostgreSQL with transaction rollback).
Tests ranking order, tier assignments, percentile queries, and population stats.
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from Fast_Swarm.Agents.Models.agent_models import Agent
from Fast_Swarm.Agents.Services.ranking_service import AgentRankingService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _make_agent(
    fitness: float = 50.0,
    status: str = "active",
    generation: int = 1,
    win_rate: float | None = None,
    sharpe: float | None = None,
    total_trades: int = 0,
) -> Agent:
    return Agent(
        agent_id=f"test-{uuid.uuid4().hex[:8]}",
        name=f"Agent-{uuid.uuid4().hex[:4]}",
        generation=generation,
        traits=_default_traits(),
        status=status,
        is_active=(status == "active"),
        fitness_score=Decimal(str(fitness)),
        elo_rating=Decimal("1500"),
        win_rate=win_rate,
        sharpe_ratio=sharpe,
        total_trades=total_trades,
    )


async def _insert_agents(session: AsyncSession, specs: list[dict]) -> list[Agent]:
    """Insert agents from a list of keyword specs."""
    agents = []
    for s in specs:
        a = _make_agent(**s)
        session.add(a)
        agents.append(a)
    await session.flush()
    for a in agents:
        await session.refresh(a)
    return agents


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.requires_db
class TestRankAgents:
    """Tests for rank_agents method."""

    async def test_rank_agents_descending_by_fitness(self, db_session: AsyncSession):
        """Agents should be ranked in descending fitness order."""
        agents = await _insert_agents(db_session, [
            {"fitness": 10.0},
            {"fitness": 90.0},
            {"fitness": 50.0},
            {"fitness": 70.0},
            {"fitness": 30.0},
        ])

        svc = AgentRankingService()
        ranked = await svc.rank_agents(session=db_session)

        scores = [float(r["fitness_score"]) for r in ranked]
        assert scores == sorted(scores, reverse=True)
        assert ranked[0]["rank"] == 1
        assert ranked[-1]["rank"] == 5

    async def test_rank_agents_includes_metadata(self, db_session: AsyncSession):
        """Ranked result should contain agent_id, fitness_score, generation, etc."""
        await _insert_agents(db_session, [
            {"fitness": 60.0, "win_rate": 0.65, "sharpe": 1.2, "total_trades": 100},
        ])

        svc = AgentRankingService()
        ranked = await svc.rank_agents(session=db_session)

        assert len(ranked) == 1
        r = ranked[0]
        assert "agent_id" in r
        assert "fitness_score" in r
        assert "sharpe_ratio" in r
        assert "win_rate" in r
        assert "total_trades" in r
        assert "generation" in r
        assert r["win_rate"] == 0.65
        assert r["sharpe_ratio"] == 1.2

    async def test_rank_specific_agent_ids(self, db_session: AsyncSession):
        """rank_agents with agent_ids should only rank those agents."""
        agents = await _insert_agents(db_session, [
            {"fitness": 80.0},
            {"fitness": 60.0},
            {"fitness": 40.0},
            {"fitness": 20.0},
        ])

        svc = AgentRankingService()
        subset_ids = [agents[0].agent_id, agents[2].agent_id]
        ranked = await svc.rank_agents(session=db_session, agent_ids=subset_ids)

        assert len(ranked) == 2
        assert ranked[0]["agent_id"] == agents[0].agent_id  # fitness 80
        assert ranked[1]["agent_id"] == agents[2].agent_id  # fitness 40

    async def test_rank_agents_empty_population(self, db_session: AsyncSession):
        """Empty population should return empty list."""
        svc = AgentRankingService()
        ranked = await svc.rank_agents(session=db_session)
        assert ranked == []

    async def test_rank_agents_excludes_non_active(self, db_session: AsyncSession):
        """Only 'active' status agents should appear in rankings."""
        await _insert_agents(db_session, [
            {"fitness": 90.0, "status": "active"},
            {"fitness": 95.0, "status": "retired"},
            {"fitness": 5.0, "status": "culled"},
            {"fitness": 80.0, "status": "active"},
        ])

        svc = AgentRankingService()
        ranked = await svc.rank_agents(session=db_session)

        assert len(ranked) == 2
        agent_ids = [r["agent_id"] for r in ranked]
        # The retired (95.0) and culled (5.0) should be absent


@pytest.mark.asyncio
@pytest.mark.requires_db
class TestGetAllAgentsRanked:
    """Tests for get_all_agents_ranked method."""

    async def test_returns_agent_objects(self, db_session: AsyncSession):
        """Should return actual Agent model instances, not dicts."""
        await _insert_agents(db_session, [
            {"fitness": 70.0},
            {"fitness": 30.0},
        ])

        svc = AgentRankingService()
        agents = await svc.get_all_agents_ranked(session=db_session)

        assert len(agents) == 2
        assert all(isinstance(a, Agent) for a in agents)
        assert float(agents[0].fitness_score) > float(agents[1].fitness_score)


@pytest.mark.asyncio
@pytest.mark.requires_db
class TestTopBottomAgents:
    """Tests for get_top_agents and get_bottom_agents."""

    async def test_top_agents_fixed_count(self, db_session: AsyncSession):
        """get_top_agents(top_n=3) should return the 3 highest fitness agents."""
        await _insert_agents(db_session, [
            {"fitness": f} for f in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        ])

        svc = AgentRankingService()
        top3 = await svc.get_top_agents(session=db_session, top_n=3)

        assert len(top3) == 3
        scores = [float(a.fitness_score) for a in top3]
        assert scores == [100.0, 90.0, 80.0]

    async def test_top_agents_by_percentile(self, db_session: AsyncSession):
        """get_top_agents with top_percentile=0.20 on 10 agents should return 2."""
        await _insert_agents(db_session, [
            {"fitness": float(i * 10)} for i in range(1, 11)
        ])

        svc = AgentRankingService()
        top20 = await svc.get_top_agents(session=db_session, top_percentile=0.20)
        assert len(top20) == 2

    async def test_bottom_agents_fixed_count(self, db_session: AsyncSession):
        """get_bottom_agents(bottom_n=3) should return the 3 lowest fitness agents."""
        await _insert_agents(db_session, [
            {"fitness": f} for f in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        ])

        svc = AgentRankingService()
        bottom3 = await svc.get_bottom_agents(session=db_session, bottom_n=3)

        assert len(bottom3) == 3
        scores = [float(a.fitness_score) for a in bottom3]
        assert scores == [10.0, 20.0, 30.0]

    async def test_bottom_agents_by_percentile(self, db_session: AsyncSession):
        """get_bottom_agents with bottom_percentile=0.30 on 10 agents should return 3."""
        await _insert_agents(db_session, [
            {"fitness": float(i * 10)} for i in range(1, 11)
        ])

        svc = AgentRankingService()
        bottom30 = await svc.get_bottom_agents(session=db_session, bottom_percentile=0.30)
        assert len(bottom30) == 3


@pytest.mark.asyncio
@pytest.mark.requires_db
class TestPopulationStats:
    """Tests for calculate_population_stats."""

    async def test_stats_with_agents(self, db_session: AsyncSession):
        """Stats should include correct min, max, avg, median."""
        # Fitness: 10, 20, 30, 40, 50 -> avg=30, median=30, min=10, max=50
        await _insert_agents(db_session, [
            {"fitness": float(f)} for f in [10, 20, 30, 40, 50]
        ])

        svc = AgentRankingService()
        stats = await svc.calculate_population_stats(session=db_session)

        assert stats["total_agents"] == 5
        assert stats["min_fitness"] == 10.0
        assert stats["max_fitness"] == 50.0
        assert stats["avg_fitness"] == 30.0
        assert stats["median_fitness"] == 30.0

    async def test_stats_empty_population(self, db_session: AsyncSession):
        """Empty population should return zeroed stats."""
        svc = AgentRankingService()
        stats = await svc.calculate_population_stats(session=db_session)

        assert stats["total_agents"] == 0
        assert stats["avg_fitness"] == 0

    async def test_stats_single_agent(self, db_session: AsyncSession):
        """Single agent: min == max == avg == median."""
        await _insert_agents(db_session, [{"fitness": 75.0}])

        svc = AgentRankingService()
        stats = await svc.calculate_population_stats(session=db_session)

        assert stats["total_agents"] == 1
        assert stats["min_fitness"] == 75.0
        assert stats["max_fitness"] == 75.0
        assert stats["avg_fitness"] == 75.0
        assert stats["median_fitness"] == 75.0

    async def test_stats_generation_tracking(self, db_session: AsyncSession):
        """Stats should track generation info."""
        await _insert_agents(db_session, [
            {"fitness": 50.0, "generation": 1},
            {"fitness": 60.0, "generation": 3},
            {"fitness": 70.0, "generation": 5},
        ])

        svc = AgentRankingService()
        stats = await svc.calculate_population_stats(session=db_session)

        assert stats["max_generation"] == 5
        assert stats["avg_generation"] == 3.0
