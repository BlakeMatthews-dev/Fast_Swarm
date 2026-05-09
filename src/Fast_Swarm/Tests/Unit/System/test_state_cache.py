"""
Tests for System.Services.state_cache_service.StateCacheService.

Validates cache loading, invalidation, ranking, thread safety,
and empty-cache behavior.  Uses mocks for the database layer.
"""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from Fast_Swarm.System.Services.state_cache_service import StateCacheService


# ---------------------------------------------------------------------------
# Helpers: fake ORM objects returned by mocked queries
# ---------------------------------------------------------------------------


def _fake_pattern(pid="p1", fitness=1.0, win_rate=0.6, sharpe=1.5, trades=100):
    p = MagicMock()
    p.pattern_id = pid
    p.entry_conditions = [{"indicator": "rsi", "operator": "<", "value": 30}]
    p.exit_conditions = [{"indicator": "rsi", "operator": ">", "value": 70}]
    p.fitness_score = fitness
    p.win_rate = win_rate
    p.sharpe_ratio = sharpe
    p.total_trades = trades
    p.is_active = True
    return p


def _fake_agent(aid="a1", fitness=50.0, bc=10, gen=1, active=True, patterns=None):
    a = MagicMock()
    a.agent_id = aid
    a.fitness_score = fitness
    a.backtest_count = bc
    a.generation = gen
    a.is_active = active
    a.assigned_patterns = patterns or []
    a.status = "active"
    return a


def _mock_session_with_patterns(patterns):
    """Return an AsyncMock session whose .exec() yields the given patterns."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.all.return_value = patterns
    session.exec.return_value = result_mock
    return session


def _mock_session_with_agents(agents):
    """Return an AsyncMock session whose .execute().scalars().all() yields agents."""
    session = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = agents
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute.return_value = result_mock
    return session


# =========================================================================
# Cache Loading / Refresh
# =========================================================================


class TestCacheLoading:
    """Tests for load_pattern_cache and load_agent_index."""

    @pytest.mark.asyncio
    async def test_load_pattern_cache(self):
        """Patterns are loaded into cache on first call."""
        svc = StateCacheService()
        patterns = [_fake_pattern("p1"), _fake_pattern("p2", fitness=2.0)]
        session = _mock_session_with_patterns(patterns)

        result = await svc.load_pattern_cache(session)

        assert len(result) == 2
        assert "p1" in result
        assert result["p2"]["fitness_score"] == 2.0

    @pytest.mark.asyncio
    async def test_load_pattern_cache_skips_if_loaded(self):
        """Second call without force_reload returns cached data without querying."""
        svc = StateCacheService()
        session = _mock_session_with_patterns([_fake_pattern()])

        await svc.load_pattern_cache(session)
        session.exec.reset_mock()

        result = await svc.load_pattern_cache(session)
        session.exec.assert_not_called()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_force_reload_reloads(self):
        """force_reload=True should re-query even if cache is loaded."""
        svc = StateCacheService()
        session = _mock_session_with_patterns([_fake_pattern()])

        await svc.load_pattern_cache(session)
        session.exec.reset_mock()

        # Add a second pattern on reload
        session_2 = _mock_session_with_patterns([_fake_pattern(), _fake_pattern("p2")])
        result = await svc.load_pattern_cache(session_2, force_reload=True)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_load_agent_index(self):
        """Agents are loaded into index on first call."""
        svc = StateCacheService()
        agents = [_fake_agent("a1"), _fake_agent("a2", fitness=80.0)]
        session = _mock_session_with_agents(agents)

        result = await svc.load_agent_index(session)

        assert len(result) == 2
        assert result["a2"]["fitness_score"] == 80.0


# =========================================================================
# Cache Invalidation
# =========================================================================


class TestCacheInvalidation:
    """Tests for invalidate_* methods."""

    @pytest.mark.asyncio
    async def test_invalidate_pattern_cache(self):
        """invalidate_pattern_cache clears cache and forces reload on next access."""
        svc = StateCacheService()
        session = _mock_session_with_patterns([_fake_pattern()])
        await svc.load_pattern_cache(session)

        svc.invalidate_pattern_cache()

        assert svc._pattern_cache_loaded is False
        assert len(svc.pattern_cache) == 0

    @pytest.mark.asyncio
    async def test_invalidate_agent_index(self):
        """invalidate_agent_index clears index and forces reload."""
        svc = StateCacheService()
        session = _mock_session_with_agents([_fake_agent()])
        await svc.load_agent_index(session)

        svc.invalidate_agent_index()

        assert svc._agent_index_loaded is False
        assert len(svc.agent_index) == 0

    @pytest.mark.asyncio
    async def test_invalidate_all(self):
        """invalidate_all clears both caches."""
        svc = StateCacheService()
        p_session = _mock_session_with_patterns([_fake_pattern()])
        a_session = _mock_session_with_agents([_fake_agent()])
        await svc.load_pattern_cache(p_session)
        await svc.load_agent_index(a_session)

        svc.invalidate_all()

        assert svc._pattern_cache_loaded is False
        assert svc._agent_index_loaded is False


# =========================================================================
# Lookup Methods
# =========================================================================


class TestLookups:
    """Tests for get_pattern, get_top_patterns, get_agent_metadata."""

    @pytest.mark.asyncio
    async def test_get_pattern_found(self):
        svc = StateCacheService()
        session = _mock_session_with_patterns([_fake_pattern("p1")])
        await svc.load_pattern_cache(session)

        p = svc.get_pattern("p1")
        assert p is not None
        assert p["pattern_id"] == "p1"

    @pytest.mark.asyncio
    async def test_get_pattern_not_found(self):
        svc = StateCacheService()
        session = _mock_session_with_patterns([])
        await svc.load_pattern_cache(session)

        assert svc.get_pattern("nonexistent") is None

    @pytest.mark.asyncio
    async def test_get_top_patterns_sorted(self):
        svc = StateCacheService()
        patterns = [
            _fake_pattern("low", fitness=1.0),
            _fake_pattern("high", fitness=10.0),
            _fake_pattern("mid", fitness=5.0),
        ]
        session = _mock_session_with_patterns(patterns)
        await svc.load_pattern_cache(session)

        top = svc.get_top_patterns(limit=2)
        assert len(top) == 2
        assert top[0]["pattern_id"] == "high"
        assert top[1]["pattern_id"] == "mid"

    @pytest.mark.asyncio
    async def test_get_top_agents_sorted(self):
        svc = StateCacheService()
        agents = [
            _fake_agent("low", fitness=10),
            _fake_agent("high", fitness=90),
        ]
        session = _mock_session_with_agents(agents)
        await svc.load_agent_index(session)

        top = svc.get_top_agents(limit=1)
        assert len(top) == 1
        assert top[0]["agent_id"] == "high"


# =========================================================================
# Empty Cache Behavior
# =========================================================================


class TestEmptyCache:
    """Verify sensible behavior before any data is loaded."""

    def test_get_pattern_empty_cache(self):
        svc = StateCacheService()
        assert svc.get_pattern("anything") is None

    def test_get_top_patterns_empty(self):
        svc = StateCacheService()
        assert svc.get_top_patterns() == []

    def test_get_agent_metadata_empty(self):
        svc = StateCacheService()
        assert svc.get_agent_metadata("anything") is None

    def test_cache_stats_initial(self):
        svc = StateCacheService()
        stats = svc.get_cache_stats()
        assert stats["pattern_cache_loaded"] is False
        assert stats["pattern_cache_size"] == 0
        assert stats["agent_index_loaded"] is False
        assert stats["agent_index_size"] == 0


# =========================================================================
# Concurrent Access (Thread Safety)
# =========================================================================


class TestConcurrentAccess:
    """Verify concurrent reads do not corrupt the cache."""

    @pytest.mark.asyncio
    async def test_concurrent_reads_no_error(self):
        """Multiple threads reading the cache simultaneously should not raise."""
        svc = StateCacheService()
        patterns = [_fake_pattern(f"p{i}", fitness=float(i)) for i in range(50)]
        session = _mock_session_with_patterns(patterns)
        await svc.load_pattern_cache(session)

        errors = []

        def _read():
            try:
                for _ in range(100):
                    svc.get_pattern("p25")
                    svc.get_top_patterns(10)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_read) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent read errors: {errors}"

    @pytest.mark.asyncio
    async def test_invalidate_during_read(self):
        """Invalidating while reading should not crash (eventual consistency)."""
        svc = StateCacheService()
        patterns = [_fake_pattern(f"p{i}") for i in range(10)]
        session = _mock_session_with_patterns(patterns)
        await svc.load_pattern_cache(session)

        errors = []

        def _read_and_invalidate():
            try:
                for _ in range(50):
                    svc.get_top_patterns(5)
                    svc.invalidate_pattern_cache()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_read_and_invalidate) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# =========================================================================
# Cache Stats
# =========================================================================


class TestCacheStats:
    """Verify get_cache_stats reflects state correctly."""

    @pytest.mark.asyncio
    async def test_stats_after_load(self):
        svc = StateCacheService()
        session = _mock_session_with_patterns([_fake_pattern()])
        await svc.load_pattern_cache(session)

        stats = svc.get_cache_stats()
        assert stats["pattern_cache_loaded"] is True
        assert stats["pattern_cache_size"] == 1
