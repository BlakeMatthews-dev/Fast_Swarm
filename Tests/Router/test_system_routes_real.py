"""
Phase 5 - System Router Integration Tests (Real DB)

Tests system routes against real PostgreSQL with transaction rollback.
Exercises: GET /system/health, GET /system/progress, GET /system/crucible/leaderboard,
           GET /system/wisdom/latest, GET /system/memory/{agent_id}
"""

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from Fast_Swarm.Agents.Models.agent_models import Agent


# =============================================================================
# FIXTURES
# =============================================================================


@pytest_asyncio.fixture
async def agents_with_fitness(db_session: AsyncSession, sample_traits):
    """Create agents with varied fitness scores for progress/leaderboard tests."""
    agents = []
    for i in range(5):
        agent = Agent(
            agent_id=f"sys-test-agent-{uuid.uuid4().hex[:8]}",
            name=f"System Test Agent {i}",
            generation=i + 1,
            traits=sample_traits,
            status="active",
            is_active=True,
            fitness_score=float(i * 15 + 10),
            elo_rating=1500.0 + i * 50,
            backtest_count=i * 10,
            total_trades=i * 5,
            winning_trades=i * 3,
        )
        db_session.add(agent)
        agents.append(agent)

    await db_session.flush()
    for a in agents:
        await db_session.refresh(a)
    return agents


# =============================================================================
# GET /system/health
# =============================================================================


class TestSystemHealth:
    """Tests for GET /system/health endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_health_returns_streams_and_robustness(self):
        """Health endpoint returns streams dict and robustness dict.

        The handler reads from global Dependencies (stream_manager, robustness_service)
        which are singletons. We mock them to avoid needing live exchange connections.
        """
        mock_stream_manager = MagicMock()
        mock_stream_manager.clients = {}

        mock_robustness = MagicMock()
        mock_robustness._running = False
        mock_robustness._nightly_hours = range(2, 5)

        with patch(
            "Fast_Swarm.System.Routers.system_router.robustness_service",
            mock_robustness,
        ), patch(
            "Fast_Swarm.System.Routers.system_router.stream_manager",
            mock_stream_manager,
        ):
            from Fast_Swarm.System.Routers.system_router import get_system_health

            result = await get_system_health()

        assert "streams" in result
        assert "robustness" in result
        assert result["robustness"]["is_running"] is False
        assert result["robustness"]["nightly_hours"] == [2, 3, 4]

    @pytest.mark.asyncio
    async def test_health_with_active_streams(self):
        """Health endpoint correctly reports active stream clients."""
        mock_client = MagicMock()
        mock_client.get_status.return_value = {
            "exchange": "binance",
            "state": "connected",
            "reconnect_count": 0,
            "seconds_since_last_message": 1.5,
        }

        mock_stream_manager = MagicMock()
        mock_stream_manager.clients = {"binance": mock_client}

        mock_robustness = MagicMock()
        mock_robustness._running = True
        mock_robustness._nightly_hours = range(2, 5)

        with patch(
            "Fast_Swarm.System.Routers.system_router.robustness_service",
            mock_robustness,
        ), patch(
            "Fast_Swarm.System.Routers.system_router.stream_manager",
            mock_stream_manager,
        ):
            from Fast_Swarm.System.Routers.system_router import get_system_health

            result = await get_system_health()

        assert "binance" in result["streams"]
        assert result["streams"]["binance"]["state"] == "connected"
        assert result["streams"]["binance"]["seconds_since_last_message"] == 1.5

    @pytest.mark.asyncio
    async def test_health_handles_infinity_seconds(self):
        """Health endpoint replaces Infinity with -1 for JSON serialization."""
        import math

        mock_client = MagicMock()
        mock_client.get_status.return_value = {
            "exchange": "coinbase",
            "state": "connecting",
            "reconnect_count": 3,
            "seconds_since_last_message": math.inf,
        }

        mock_stream_manager = MagicMock()
        mock_stream_manager.clients = {"coinbase": mock_client}

        mock_robustness = MagicMock()
        mock_robustness._running = False
        mock_robustness._nightly_hours = range(0, 0)

        with patch(
            "Fast_Swarm.System.Routers.system_router.robustness_service",
            mock_robustness,
        ), patch(
            "Fast_Swarm.System.Routers.system_router.stream_manager",
            mock_stream_manager,
        ):
            from Fast_Swarm.System.Routers.system_router import get_system_health

            result = await get_system_health()

        assert result["streams"]["coinbase"]["seconds_since_last_message"] == -1

    @pytest.mark.asyncio
    async def test_health_handles_stream_error(self):
        """Health endpoint returns error dict if stream_manager raises."""
        mock_stream_manager = MagicMock()
        mock_stream_manager.clients = property(lambda s: (_ for _ in ()).throw(RuntimeError("boom")))
        # Simpler: make .clients raise on iteration
        type(mock_stream_manager).clients = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))

        mock_robustness = MagicMock()
        mock_robustness._running = False
        mock_robustness._nightly_hours = range(0, 0)

        # The handler catches exceptions on stream iteration
        with patch(
            "Fast_Swarm.System.Routers.system_router.robustness_service",
            mock_robustness,
        ), patch(
            "Fast_Swarm.System.Routers.system_router.stream_manager",
            mock_stream_manager,
        ):
            from Fast_Swarm.System.Routers.system_router import get_system_health

            result = await get_system_health()

        assert "error" in result["streams"]


# =============================================================================
# GET /system/progress
# =============================================================================


class TestSystemProgress:
    """Tests for GET /system/progress endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_progress_returns_expected_sections(
        self, db_session: AsyncSession, agents_with_fitness
    ):
        """Progress endpoint returns windows, agents, fitness, patterns, evolution."""
        from Fast_Swarm.System.Routers.system_router import get_evolution_progress

        result = await get_evolution_progress(session=db_session)

        assert "windows" in result
        assert "agents" in result
        assert "fitness" in result
        assert "patterns" in result
        assert "evolution" in result

    @pytest.mark.asyncio
    async def test_progress_agent_counts(
        self, db_session: AsyncSession, agents_with_fitness
    ):
        """Progress reports correct active agent counts."""
        from Fast_Swarm.System.Routers.system_router import get_evolution_progress

        result = await get_evolution_progress(session=db_session)

        # We created 5 active agents
        assert result["agents"]["total_active"] >= 5

    @pytest.mark.asyncio
    async def test_progress_fitness_stats(
        self, db_session: AsyncSession, agents_with_fitness
    ):
        """Progress reports fitness avg, max, min, stddev."""
        from Fast_Swarm.System.Routers.system_router import get_evolution_progress

        result = await get_evolution_progress(session=db_session)

        fitness = result["fitness"]
        assert "avg" in fitness
        assert "max" in fitness
        assert "min" in fitness
        assert "stddev" in fitness
        # Our agents have fitness 10, 25, 40, 55, 70
        assert fitness["max"] >= 70.0

    @pytest.mark.asyncio
    async def test_progress_empty_db(self, db_session: AsyncSession):
        """Progress handles empty database gracefully (no agents/patterns)."""
        from Fast_Swarm.System.Routers.system_router import get_evolution_progress

        result = await get_evolution_progress(session=db_session)

        # Should not raise; values should be zero or empty
        assert result["agents"]["total_active"] >= 0
        assert result["evolution"]["cycles_completed"] >= 0

    @pytest.mark.asyncio
    async def test_progress_windows_constants(self, db_session: AsyncSession):
        """Progress reports correct window constants."""
        from Fast_Swarm.System.Routers.system_router import get_evolution_progress

        result = await get_evolution_progress(session=db_session)

        assert result["windows"]["windows_per_agent"] == 552
        assert result["windows"]["canonical_periods"] == 152
        assert result["windows"]["random_windows"] == 400


# =============================================================================
# GET /system/crucible/leaderboard
# =============================================================================


class TestCrucibleLeaderboard:
    """Tests for GET /system/crucible/leaderboard endpoint."""

    @pytest.mark.asyncio
    async def test_leaderboard_empty(self, db_session: AsyncSession):
        """Leaderboard returns empty list when no crucible entries exist."""
        from Fast_Swarm.System.Routers.system_router import get_crucible_leaderboard

        result = await get_crucible_leaderboard(limit=20, session=db_session)

        assert isinstance(result, list)
        # Empty or whatever exists in the test DB (rolled back)

    @pytest.mark.asyncio
    async def test_leaderboard_respects_limit(self, db_session: AsyncSession):
        """Leaderboard limit parameter is respected."""
        from Fast_Swarm.System.Routers.system_router import get_crucible_leaderboard

        result = await get_crucible_leaderboard(limit=3, session=db_session)

        assert isinstance(result, list)
        assert len(result) <= 3


# =============================================================================
# GET /system/wisdom/latest
# =============================================================================


class TestWisdomLatest:
    """Tests for GET /system/wisdom/latest endpoint."""

    @pytest.mark.asyncio
    async def test_wisdom_latest_returns_list(self, db_session: AsyncSession):
        """Wisdom endpoint returns a list (possibly empty)."""
        from Fast_Swarm.System.Routers.system_router import get_latest_wisdom

        result = await get_latest_wisdom(limit=5, session=db_session)

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_wisdom_latest_respects_limit(self, db_session: AsyncSession):
        """Wisdom endpoint respects the limit parameter."""
        from Fast_Swarm.System.Routers.system_router import get_latest_wisdom

        result = await get_latest_wisdom(limit=2, session=db_session)

        assert len(result) <= 2


# =============================================================================
# GET /system/memory/{agent_id}
# =============================================================================


class TestAgentMemory:
    """Tests for GET /system/memory/{agent_id} endpoint."""

    @pytest.mark.asyncio
    async def test_memory_returns_list(
        self, db_session: AsyncSession, sample_agent
    ):
        """Memory endpoint returns a list for a valid agent."""
        from Fast_Swarm.System.Routers.system_router import get_agent_memories

        result = await get_agent_memories(
            agent_id=sample_agent.agent_id,
            limit=50,
            memory_type=None,
            session=db_session,
        )

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_memory_nonexistent_agent_returns_empty(
        self, db_session: AsyncSession
    ):
        """Memory endpoint returns empty list for nonexistent agent."""
        from Fast_Swarm.System.Routers.system_router import get_agent_memories

        result = await get_agent_memories(
            agent_id="nonexistent-agent-id",
            limit=50,
            memory_type=None,
            session=db_session,
        )

        assert isinstance(result, list)
        assert len(result) == 0
