"""
Tests for AgentRankingService - Agent fitness ranking pipeline.

Tests ranking by fitness, top/bottom agent selection,
population stats, and edge cases.

All tests use AsyncMock for DB sessions (no real database required).
"""

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
import pytest_asyncio

from Fast_Swarm.Agents.Services.ranking_service import AgentRankingService


# =============================================================================
# Helpers
# =============================================================================

def _mock_agent(agent_id, fitness_score, generation=1, status="active",
                sharpe_ratio=None, win_rate=None, total_trades=0):
    """Create a mock Agent object."""
    agent = MagicMock()
    agent.id = hash(agent_id) % 10000
    agent.agent_id = agent_id
    agent.fitness_score = fitness_score
    agent.generation = generation
    agent.status = status
    agent.sharpe_ratio = sharpe_ratio
    agent.win_rate = win_rate
    agent.total_trades = total_trades
    agent.is_active = status == "active"
    return agent


def _mock_session_exec(agents):
    """
    Create an AsyncMock session whose .exec() returns agents.

    Handles both .exec() -> .all() and .execute() -> .scalars().all() patterns.
    """
    session = AsyncMock()

    # For session.exec(query) -> result with .all()
    exec_result = MagicMock()
    exec_result.all.return_value = agents
    exec_result.one.return_value = MagicMock(
        total=len(agents),
        avg_fitness=sum(a.fitness_score or 0 for a in agents) / max(len(agents), 1),
        max_fitness=max((a.fitness_score or 0 for a in agents), default=0),
        min_fitness=min((a.fitness_score or 0 for a in agents), default=0),
        avg_generation=sum(a.generation for a in agents) / max(len(agents), 1),
        max_generation=max((a.generation for a in agents), default=0),
    )
    session.exec = AsyncMock(return_value=exec_result)

    # For session.execute(query) -> result with .scalars().all()
    execute_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = agents
    execute_result.scalars.return_value = scalars_mock
    execute_result.scalar.return_value = (
        sum(a.fitness_score or 0 for a in agents) / max(len(agents), 1)
        if agents else 0
    )
    session.execute = AsyncMock(return_value=execute_result)

    return session


# =============================================================================
# Rank by Fitness Tests
# =============================================================================


class TestRankByFitness:
    """Tests for ranking agents by fitness score."""

    @pytest.mark.asyncio
    async def test_rank_agents_ordered_by_fitness(self):
        agents = [
            _mock_agent("a1", 90.0),
            _mock_agent("a2", 50.0),
            _mock_agent("a3", 70.0),
        ]
        # Pre-sort descending (as the DB query would)
        agents_sorted = sorted(agents, key=lambda a: a.fitness_score, reverse=True)
        session = _mock_session_exec(agents_sorted)

        service = AgentRankingService()
        ranked = await service.rank_agents(session)

        assert ranked[0]["agent_id"] == "a1"
        assert ranked[1]["agent_id"] == "a3"
        assert ranked[2]["agent_id"] == "a2"

    @pytest.mark.asyncio
    async def test_rank_includes_rank_numbers(self):
        agents = [_mock_agent(f"a{i}", float(100 - i * 10)) for i in range(5)]
        session = _mock_session_exec(agents)

        service = AgentRankingService()
        ranked = await service.rank_agents(session)

        for i, entry in enumerate(ranked):
            assert entry["rank"] == i + 1

    @pytest.mark.asyncio
    async def test_rank_returns_fitness_fields(self):
        agent = _mock_agent("a1", 85.0, sharpe_ratio=1.5, win_rate=0.65, total_trades=100)
        session = _mock_session_exec([agent])

        service = AgentRankingService()
        ranked = await service.rank_agents(session)

        assert ranked[0]["fitness_score"] == 85.0
        assert ranked[0]["sharpe_ratio"] == 1.5
        assert ranked[0]["win_rate"] == 0.65
        assert ranked[0]["total_trades"] == 100

    @pytest.mark.asyncio
    async def test_rank_specific_agent_ids(self):
        agents = [_mock_agent("a1", 80.0), _mock_agent("a2", 60.0)]
        session = _mock_session_exec(agents)

        service = AgentRankingService()
        ranked = await service.rank_agents(session, agent_ids=["a1", "a2"])
        assert len(ranked) == 2


# =============================================================================
# Top / Bottom Agent Tests
# =============================================================================


class TestTopBottomAgents:
    """Tests for get_top_agents and get_bottom_agents."""

    @pytest.mark.asyncio
    async def test_get_all_agents_ranked(self):
        agents = [
            _mock_agent("a1", 90.0),
            _mock_agent("a2", 50.0),
        ]
        session = _mock_session_exec(agents)

        service = AgentRankingService()
        result = await service.get_all_agents_ranked(session)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_top_agents(self):
        agents = [_mock_agent(f"a{i}", float(100 - i * 10)) for i in range(10)]
        session = _mock_session_exec(agents[:3])

        service = AgentRankingService()
        result = await service.get_top_agents(session, top_n=3)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_get_bottom_agents(self):
        agents = [_mock_agent(f"a{i}", float(i * 10)) for i in range(10)]
        session = _mock_session_exec(agents[:3])

        service = AgentRankingService()
        result = await service.get_bottom_agents(session, bottom_n=3)
        assert len(result) == 3


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestRankingEdgeCases:
    """Edge cases for ranking."""

    @pytest.mark.asyncio
    async def test_single_agent(self):
        agents = [_mock_agent("solo", 50.0)]
        session = _mock_session_exec(agents)

        service = AgentRankingService()
        ranked = await service.rank_agents(session)
        assert len(ranked) == 1
        assert ranked[0]["rank"] == 1

    @pytest.mark.asyncio
    async def test_all_equal_fitness(self):
        agents = [_mock_agent(f"a{i}", 50.0) for i in range(5)]
        session = _mock_session_exec(agents)

        service = AgentRankingService()
        ranked = await service.rank_agents(session)
        assert len(ranked) == 5
        # All should still get sequential ranks
        ranks = [r["rank"] for r in ranked]
        assert ranks == [1, 2, 3, 4, 5]

    @pytest.mark.asyncio
    async def test_zero_fitness(self):
        agents = [_mock_agent("zero", 0.0)]
        session = _mock_session_exec(agents)

        service = AgentRankingService()
        ranked = await service.rank_agents(session)
        assert ranked[0]["fitness_score"] == 0.0

    @pytest.mark.asyncio
    async def test_none_fitness_handled(self):
        agent = _mock_agent("null-fit", None)
        session = _mock_session_exec([agent])

        service = AgentRankingService()
        ranked = await service.rank_agents(session)
        assert len(ranked) == 1
        assert ranked[0]["fitness_score"] is None

    @pytest.mark.asyncio
    async def test_empty_population(self):
        session = _mock_session_exec([])

        service = AgentRankingService()
        ranked = await service.rank_agents(session)
        assert ranked == []
