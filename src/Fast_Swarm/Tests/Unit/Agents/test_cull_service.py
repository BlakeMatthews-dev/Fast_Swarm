"""
Tests for AgentCullService - Underperforming agent removal.

Tests culling by percentile, minimum population protection,
specialist elitism, soft delete, and edge cases.

All tests use AsyncMock for DB sessions (no real database required).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from Fast_Swarm.Agents.Services.cull_service import AgentCullService, get_best_regime_fitness


# =============================================================================
# Helpers
# =============================================================================

def _mock_agent(agent_id, fitness_score, status="active", backtest_count=10,
                fitness_by_regime=None, generation=1):
    """Create a mock Agent object for cull tests."""
    agent = MagicMock()
    agent.agent_id = agent_id
    agent.name = f"Agent-{agent_id}"
    agent.fitness_score = fitness_score
    agent.status = status
    agent.is_active = status == "active"
    agent.backtest_count = backtest_count
    agent.fitness_by_regime = fitness_by_regime
    agent.generation = generation
    return agent


def _mock_session_with_agents(agents):
    """
    Create an AsyncMock session whose execute() returns agents.
    Also mocks commit().
    """
    session = AsyncMock()

    execute_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = agents
    execute_result.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=execute_result)

    session.commit = AsyncMock()
    session.add = MagicMock()

    return session


# =============================================================================
# get_best_regime_fitness Tests
# =============================================================================


class TestGetBestRegimeFitness:
    """Tests for the regime-aware fitness function."""

    def test_returns_aggregate_when_no_regime_data(self):
        agent = _mock_agent("a1", 75.0, fitness_by_regime=None)
        assert get_best_regime_fitness(agent) == 75.0

    def test_returns_aggregate_when_empty_regime_data(self):
        agent = _mock_agent("a1", 75.0, fitness_by_regime={})
        assert get_best_regime_fitness(agent) == 75.0

    def test_returns_best_regime(self):
        agent = _mock_agent("a1", 50.0, fitness_by_regime={
            "bull": 90.0, "bear": 20.0, "crash": 10.0
        })
        assert get_best_regime_fitness(agent) == 90.0

    def test_filters_none_values(self):
        agent = _mock_agent("a1", 40.0, fitness_by_regime={
            "bull": None, "bear": 60.0, "sideways": None
        })
        assert get_best_regime_fitness(agent) == 60.0

    def test_all_none_falls_back_to_aggregate(self):
        agent = _mock_agent("a1", 30.0, fitness_by_regime={
            "bull": None, "bear": None
        })
        assert get_best_regime_fitness(agent) == 30.0


# =============================================================================
# Cull Bottom Percentile Tests
# =============================================================================


class TestCullBottomPercentile:
    """Tests for culling the bottom N% of agents."""

    @pytest.mark.asyncio
    async def test_cull_bottom_30_percent(self):
        # 10 agents, cull 30% = 3 agents
        agents = [_mock_agent(f"a{i}", float(i * 10), backtest_count=10) for i in range(10)]
        session = _mock_session_with_agents(agents)

        service = AgentCullService()
        result = await service.cull_agents(session, cull_percentile=0.3, min_population=0)

        assert result["culled_count"] == 3
        assert len(result["culled_ids"]) == 3

    @pytest.mark.asyncio
    async def test_culled_agents_marked_status_culled(self):
        agents = [_mock_agent(f"a{i}", float(i * 10), backtest_count=5) for i in range(10)]
        session = _mock_session_with_agents(agents)

        service = AgentCullService()
        await service.cull_agents(session, cull_percentile=0.3, min_population=0)

        # Verify culled agents had status set
        culled = [a for a in agents if a.status == "culled"]
        assert len(culled) == 3

    @pytest.mark.asyncio
    async def test_cull_zero_percentile(self):
        agents = [_mock_agent(f"a{i}", float(i * 10), backtest_count=5) for i in range(10)]
        session = _mock_session_with_agents(agents)

        service = AgentCullService()
        result = await service.cull_agents(session, cull_percentile=0.0, min_population=0)
        assert result["culled_count"] == 0


# =============================================================================
# Minimum Population Protection Tests
# =============================================================================


class TestMinimumPopulation:
    """Tests for minimum population enforcement."""

    @pytest.mark.asyncio
    async def test_no_cull_at_min_population(self):
        agents = [_mock_agent(f"a{i}", float(i * 10), backtest_count=5) for i in range(5)]
        session = _mock_session_with_agents(agents)

        service = AgentCullService()
        result = await service.cull_agents(session, cull_percentile=0.5, min_population=5)

        assert result["culled_count"] == 0
        assert "below minimum" in result.get("message", "")

    @pytest.mark.asyncio
    async def test_cull_limited_by_min_population(self):
        # 10 agents, want to cull 50% (5), but min_population=8 means max_cull=2
        agents = [_mock_agent(f"a{i}", float(i * 10), backtest_count=10) for i in range(10)]
        session = _mock_session_with_agents(agents)

        service = AgentCullService()
        result = await service.cull_agents(session, cull_percentile=0.5, min_population=8)

        assert result["culled_count"] <= 2

    @pytest.mark.asyncio
    async def test_below_min_population_skips_cull(self):
        agents = [_mock_agent(f"a{i}", float(i * 10), backtest_count=5) for i in range(3)]
        session = _mock_session_with_agents(agents)

        service = AgentCullService()
        result = await service.cull_agents(session, cull_percentile=0.5, min_population=150)

        assert result["culled_count"] == 0


# =============================================================================
# Elitism / Specialist Protection Tests
# =============================================================================


class TestElitism:
    """Tests for specialist and backtest-count protection."""

    @pytest.mark.asyncio
    async def test_untested_agents_protected(self):
        # 5 tested agents, 5 untested (backtest_count=0)
        agents = []
        for i in range(5):
            agents.append(_mock_agent(f"tested-{i}", float(i * 10), backtest_count=10))
        for i in range(5):
            agents.append(_mock_agent(f"untested-{i}", float(i * 5), backtest_count=0))

        session = _mock_session_with_agents(agents)

        service = AgentCullService()
        result = await service.cull_agents(session, cull_percentile=0.5, min_population=0)

        # Untested agents should not be in culled list
        for cid in result["culled_ids"]:
            assert not cid.startswith("untested-"), f"Untested agent {cid} should be protected"

    @pytest.mark.asyncio
    async def test_specialist_with_high_regime_fitness_survives(self):
        # Agent has low aggregate fitness but high in one regime
        specialist = _mock_agent("specialist", 20.0, backtest_count=10,
                                 fitness_by_regime={"bull": 95.0, "bear": 5.0})
        low_agent = _mock_agent("low", 15.0, backtest_count=10,
                                fitness_by_regime={"bull": 10.0, "bear": 10.0})
        agents = [specialist, low_agent]
        session = _mock_session_with_agents(agents)

        service = AgentCullService()
        result = await service.cull_agents(session, cull_percentile=0.5, min_population=0)

        # Specialist has best_regime=95, low has best_regime=10
        # Specialist should survive because best-regime sorting protects them
        if result["culled_count"] > 0:
            assert "specialist" not in result["culled_ids"]


# =============================================================================
# Soft Delete Tests
# =============================================================================


class TestSoftDelete:
    """Tests for soft delete behavior (status change, not hard delete)."""

    @pytest.mark.asyncio
    async def test_cull_sets_status_not_deletes(self):
        agents = [_mock_agent(f"a{i}", float(i * 10), backtest_count=5) for i in range(5)]
        session = _mock_session_with_agents(agents)

        service = AgentCullService()
        await service.cull_agents(session, cull_percentile=0.5, min_population=0)

        # Verify session.add was called (update), not session.delete
        session.add.assert_called()

    @pytest.mark.asyncio
    async def test_cull_specific_agents(self):
        agents = [
            _mock_agent("keep-1", 90.0),
            _mock_agent("cull-1", 10.0),
            _mock_agent("cull-2", 20.0),
        ]
        session = _mock_session_with_agents(agents)

        service = AgentCullService()
        result = await service.cull_specific_agents(session, ["cull-1", "cull-2"])

        assert result["culled_count"] == 3  # all returned by mock
        # All agents in mock are returned; in real DB it filters by agent_id


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestCullEdgeCases:
    """Edge cases for culling."""

    @pytest.mark.asyncio
    async def test_cull_single_agent_at_min_pop(self):
        agents = [_mock_agent("solo", 10.0, backtest_count=5)]
        session = _mock_session_with_agents(agents)

        service = AgentCullService()
        result = await service.cull_agents(session, cull_percentile=1.0, min_population=1)
        # Can't cull below min_population=1
        assert result["culled_count"] == 0

    @pytest.mark.asyncio
    async def test_cull_empty_population(self):
        session = _mock_session_with_agents([])

        service = AgentCullService()
        result = await service.cull_agents(session, cull_percentile=0.5, min_population=0)
        assert result["culled_count"] == 0

    @pytest.mark.asyncio
    async def test_cull_all_untested(self):
        agents = [_mock_agent(f"a{i}", float(i * 10), backtest_count=0) for i in range(5)]
        session = _mock_session_with_agents(agents)

        service = AgentCullService()
        result = await service.cull_agents(session, cull_percentile=1.0, min_population=0)

        # All agents have 0 backtests, so none are evaluated for culling
        assert result["culled_count"] == 0
        assert "No agents with" in result.get("message", "")
