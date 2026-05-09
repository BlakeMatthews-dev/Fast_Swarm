"""
Real integration tests for agent_stats_service.py

Tests the get_agent_average_stats() function which:
- Aggregates fitness, win_rate, backtest_count across active agents
- Extracts and averages JSONB trait values
- Aggregates regime-specific fitness
- Counts specialists (agents with 50+ fitness in at least one regime)

Uses db_session fixture — all DB writes rolled back after each test.
"""

import uuid
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from Fast_Swarm.Agents.Models.agent_models import Agent
from Fast_Swarm.Agents.Services.agent_stats_service import TRAIT_KEYS, get_agent_average_stats


# =============================================================================
# Helpers
# =============================================================================


def make_agent(
    status: str = "active",
    fitness: float = 50.0,
    win_rate: float = 0.55,
    backtest_count: int = 100,
    traits: dict[str, Any] | None = None,
    fitness_by_regime: dict[str, Any] | None = {},
    elo_rating: float = 1500.0,
) -> Agent:
    """Create an Agent model instance with known values."""
    default_traits = {k: 0.5 for k in TRAIT_KEYS}
    if traits:
        default_traits.update(traits)

    return Agent(
        agent_id=f"test-agent-{uuid.uuid4().hex[:8]}",
        name=f"Agent {uuid.uuid4().hex[:4]}",
        generation=1,
        traits=default_traits,
        status=status,
        is_active=(status == "active"),
        fitness_score=fitness,
        win_rate=win_rate,
        backtest_count=backtest_count,
        elo_rating=elo_rating,
        fitness_by_regime=fitness_by_regime,
    )


async def insert_agents(session: AsyncSession, agents: list[Agent]) -> None:
    """Insert a batch of agents into the DB."""
    for agent in agents:
        session.add(agent)
    await session.flush()


# =============================================================================
# Basic Aggregation Tests
# =============================================================================


@pytest.mark.asyncio
class TestBasicAggregation:
    """Test basic stat aggregation (count, fitness, win_rate)."""

    async def test_no_agents_returns_zero_count(self, db_session: AsyncSession):
        result = await get_agent_average_stats(db_session)
        assert result["count"] == 0 or result.get("active_count", 0) == 0

    async def test_single_agent_stats(self, db_session: AsyncSession):
        agent = make_agent(fitness=75.0, win_rate=0.65, backtest_count=200)
        await insert_agents(db_session, [agent])

        result = await get_agent_average_stats(db_session)
        assert result["active_count"] == 1
        assert result["avg_fitness"] == 75.0
        assert result["avg_win_rate"] == pytest.approx(0.65, abs=0.01)
        assert result["avg_backtest_count"] == 200.0

    async def test_multiple_agents_average(self, db_session: AsyncSession):
        agents = [
            make_agent(fitness=60.0, win_rate=0.50, backtest_count=100),
            make_agent(fitness=80.0, win_rate=0.70, backtest_count=300),
            make_agent(fitness=40.0, win_rate=0.40, backtest_count=50),
        ]
        await insert_agents(db_session, agents)

        result = await get_agent_average_stats(db_session)
        assert result["active_count"] == 3
        assert result["avg_fitness"] == pytest.approx(60.0, abs=0.1)
        assert result["avg_win_rate"] == pytest.approx(0.5333, abs=0.01)

    async def test_retired_agents_excluded(self, db_session: AsyncSession):
        agents = [
            make_agent(status="active", fitness=80.0),
            make_agent(status="retired", fitness=90.0),
        ]
        await insert_agents(db_session, agents)

        result = await get_agent_average_stats(db_session)
        assert result["active_count"] == 1
        assert result["avg_fitness"] == 80.0

    async def test_fitness_50_plus_count(self, db_session: AsyncSession):
        agents = [
            make_agent(fitness=30.0),
            make_agent(fitness=55.0),
            make_agent(fitness=70.0),
            make_agent(fitness=45.0),
            make_agent(fitness=90.0),
        ]
        await insert_agents(db_session, agents)

        result = await get_agent_average_stats(db_session)
        assert result["fitness_50_plus"] == 3  # 55, 70, 90


# =============================================================================
# Trait Aggregation Tests
# =============================================================================


@pytest.mark.asyncio
class TestTraitAggregation:
    """Test JSONB trait extraction and averaging."""

    async def test_uniform_traits_average(self, db_session: AsyncSession):
        """When all agents have the same traits, average should equal the value."""
        agents = [
            make_agent(traits={"risk_tolerance": 0.7, "hold_duration_bias": 0.3}),
            make_agent(traits={"risk_tolerance": 0.7, "hold_duration_bias": 0.3}),
        ]
        await insert_agents(db_session, agents)

        result = await get_agent_average_stats(db_session)
        avg_traits = result["average_traits"]
        assert avg_traits["risk_tolerance"] == pytest.approx(0.7, abs=0.01)
        assert avg_traits["hold_duration_bias"] == pytest.approx(0.3, abs=0.01)

    async def test_varied_traits_average(self, db_session: AsyncSession):
        agents = [
            make_agent(traits={"risk_tolerance": 0.2}),
            make_agent(traits={"risk_tolerance": 0.8}),
        ]
        await insert_agents(db_session, agents)

        result = await get_agent_average_stats(db_session)
        avg_traits = result["average_traits"]
        assert avg_traits["risk_tolerance"] == pytest.approx(0.5, abs=0.01)

    async def test_null_traits_handled(self, db_session: AsyncSession):
        """Agents with empty traits should not crash the query."""
        agent = make_agent(fitness=50.0)
        # Manually override traits to empty after construction
        agent.traits = {}
        await insert_agents(db_session, [agent])

        result = await get_agent_average_stats(db_session)
        assert result["active_count"] == 1
        # No trait values to average — all should be None
        for key in TRAIT_KEYS:
            assert result["average_traits"][key] is None


# =============================================================================
# Regime Fitness Aggregation Tests
# =============================================================================


@pytest.mark.asyncio
class TestRegimeFitness:
    """Test regime-specific fitness aggregation."""

    async def test_regime_fitness_aggregation(self, db_session: AsyncSession):
        agents = [
            make_agent(fitness_by_regime={
                "bull": {"fitness": 80.0, "trades": 50, "win_rate": 0.7},
                "bear": {"fitness": 30.0, "trades": 20, "win_rate": 0.3},
            }),
            make_agent(fitness_by_regime={
                "bull": {"fitness": 60.0, "trades": 40, "win_rate": 0.6},
                "bear": {"fitness": 50.0, "trades": 30, "win_rate": 0.5},
            }),
        ]
        await insert_agents(db_session, agents)

        result = await get_agent_average_stats(db_session)
        regime = result["regime_fitness"]

        assert "bull" in regime
        assert regime["bull"]["fitness"] == pytest.approx(70.0, abs=0.1)
        assert "bear" in regime
        assert regime["bear"]["fitness"] == pytest.approx(40.0, abs=0.1)

    async def test_no_regime_data(self, db_session: AsyncSession):
        agents = [make_agent(fitness_by_regime={})]
        await insert_agents(db_session, agents)

        result = await get_agent_average_stats(db_session)
        assert result["regime_fitness"] == {}


# =============================================================================
# Specialist Counting Tests
# =============================================================================


@pytest.mark.asyncio
class TestSpecialists:
    """Test specialist counting (agents with 50+ fitness in any regime)."""

    async def test_specialist_count(self, db_session: AsyncSession):
        agents = [
            make_agent(fitness_by_regime={
                "bull": {"fitness": 60.0, "trades": 10, "win_rate": 0.6},
            }),
            make_agent(fitness_by_regime={
                "bull": {"fitness": 30.0, "trades": 10, "win_rate": 0.3},
            }),
            make_agent(fitness_by_regime={
                "bear": {"fitness": 55.0, "trades": 10, "win_rate": 0.5},
            }),
        ]
        await insert_agents(db_session, agents)

        result = await get_agent_average_stats(db_session)
        # Agent 1: bull fitness 60 >= 50 => specialist
        # Agent 2: bull fitness 30 < 50 => not specialist
        # Agent 3: bear fitness 55 >= 50 => specialist
        assert result["specialists"] == 2

    async def test_no_specialists(self, db_session: AsyncSession):
        agents = [
            make_agent(fitness_by_regime={
                "bull": {"fitness": 20.0, "trades": 10, "win_rate": 0.3},
            }),
        ]
        await insert_agents(db_session, agents)

        result = await get_agent_average_stats(db_session)
        assert result["specialists"] == 0


# =============================================================================
# Scaling / 20-Agent Test
# =============================================================================


@pytest.mark.asyncio
class TestScaling:
    """Test with 20 agents as specified in the requirements."""

    async def test_twenty_agents_aggregation(self, db_session: AsyncSession):
        """Insert 20 agents with varying stats, verify aggregation."""
        agents = []
        for i in range(20):
            agents.append(make_agent(
                fitness=10.0 + i * 4.5,  # 10 to 95.5
                win_rate=0.3 + i * 0.02,  # 0.3 to 0.68
                backtest_count=50 + i * 25,
                traits={"risk_tolerance": 0.1 + i * 0.04},  # 0.1 to 0.86
                fitness_by_regime={
                    "bull": {"fitness": 20.0 + i * 3, "trades": 10, "win_rate": 0.5},
                } if i % 2 == 0 else {},
            ))
        await insert_agents(db_session, agents)

        result = await get_agent_average_stats(db_session)

        assert result["active_count"] == 20
        # avg fitness = mean(10, 14.5, 19, ..., 95.5) = 52.75
        assert result["avg_fitness"] == pytest.approx(52.75, abs=1.0)
        # avg win_rate = mean(0.3, 0.32, ..., 0.68) = 0.49
        assert result["avg_win_rate"] == pytest.approx(0.49, abs=0.02)
        # Fitness 50+ count: agents with fitness >= 50 are indices 9..19 (fitness 50.5..95.5) = 11
        assert result["fitness_50_plus"] >= 10
        # Risk tolerance average: mean(0.1, 0.14, ..., 0.86) = 0.48
        assert result["average_traits"]["risk_tolerance"] == pytest.approx(0.48, abs=0.05)
