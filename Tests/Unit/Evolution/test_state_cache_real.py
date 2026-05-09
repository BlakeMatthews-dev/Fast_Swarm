"""
Real-DB integration tests for StateCacheService.

Uses db_session fixture (PostgreSQL with transaction rollback).
Tests cache load, get, invalidation, stats, and refresh.
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from Fast_Swarm.Agents.Models.agent_models import Agent
from Fast_Swarm.Patterns.Models.pattern_models import Pattern
from Fast_Swarm.System.Services.state_cache_service import StateCacheService


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


def _make_agent(fitness: float = 50.0, status: str = "active") -> Agent:
    return Agent(
        agent_id=f"test-{uuid.uuid4().hex[:8]}",
        name=f"CacheAgent-{uuid.uuid4().hex[:4]}",
        generation=1,
        traits=_default_traits(),
        status=status,
        is_active=(status == "active"),
        fitness_score=Decimal(str(fitness)),
        elo_rating=Decimal("1500"),
        backtest_count=10,
    )


def _make_pattern(fitness: float = 60.0, is_active: bool = True) -> Pattern:
    return Pattern(
        pattern_id=f"pat-{uuid.uuid4().hex[:8]}",
        name=f"CachePattern-{uuid.uuid4().hex[:4]}",
        origin="technical",
        status="untested",
        is_active=is_active,
        entry_conditions=[{"indicator": "rsi", "min": 20, "max": 35}],
        exit_conditions=[{"indicator": "rsi", "min": 65, "max": 80}],
        fitness_score=Decimal(str(fitness)),
        win_rate=0.55,
        sharpe_ratio=1.1,
        total_trades=50,
    )


async def _seed_agents(session: AsyncSession, count: int = 5) -> list[Agent]:
    agents = []
    for i in range(count):
        a = _make_agent(fitness=float(10 + i * 15))
        session.add(a)
        agents.append(a)
    await session.flush()
    return agents


async def _seed_patterns(session: AsyncSession, count: int = 5) -> list[Pattern]:
    patterns = []
    for i in range(count):
        p = _make_pattern(fitness=float(30 + i * 15))
        session.add(p)
        patterns.append(p)
    await session.flush()
    return patterns


# ---------------------------------------------------------------------------
# Pattern Cache Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.requires_db
class TestPatternCache:
    """Tests for pattern cache loading and retrieval."""

    async def test_load_pattern_cache(self, db_session: AsyncSession):
        """Loading pattern cache should populate all active patterns."""
        patterns = await _seed_patterns(db_session, count=5)

        cache = StateCacheService()
        result = await cache.load_pattern_cache(db_session)

        assert len(result) >= 5
        for p in patterns:
            assert p.pattern_id in result
            cached = result[p.pattern_id]
            assert cached["pattern_id"] == p.pattern_id
            assert cached["entry_conditions"] == p.entry_conditions
            assert cached["exit_conditions"] == p.exit_conditions

    async def test_get_pattern_from_cache(self, db_session: AsyncSession):
        """get_pattern should return the cached pattern dict."""
        patterns = await _seed_patterns(db_session, count=3)

        cache = StateCacheService()
        await cache.load_pattern_cache(db_session)

        p = cache.get_pattern(patterns[0].pattern_id)
        assert p is not None
        assert p["pattern_id"] == patterns[0].pattern_id

    async def test_get_pattern_missing_returns_none(self, db_session: AsyncSession):
        """get_pattern for a non-cached ID should return None."""
        cache = StateCacheService()
        await cache.load_pattern_cache(db_session)

        result = cache.get_pattern("nonexistent-pattern-id")
        assert result is None

    async def test_get_patterns_by_ids(self, db_session: AsyncSession):
        """get_patterns_by_ids should return matching patterns."""
        patterns = await _seed_patterns(db_session, count=5)

        cache = StateCacheService()
        await cache.load_pattern_cache(db_session)

        ids = [patterns[0].pattern_id, patterns[2].pattern_id]
        result = cache.get_patterns_by_ids(ids)
        assert len(result) == 2

    async def test_inactive_patterns_excluded_from_cache(self, db_session: AsyncSession):
        """Inactive patterns should not appear in the cache."""
        active = _make_pattern(fitness=70.0, is_active=True)
        inactive = _make_pattern(fitness=80.0, is_active=False)
        db_session.add_all([active, inactive])
        await db_session.flush()

        cache = StateCacheService()
        await cache.load_pattern_cache(db_session)

        assert active.pattern_id in cache.pattern_cache
        assert inactive.pattern_id not in cache.pattern_cache

    async def test_get_top_patterns_sorted(self, db_session: AsyncSession):
        """get_top_patterns should return patterns sorted by fitness desc."""
        await _seed_patterns(db_session, count=10)

        cache = StateCacheService()
        await cache.load_pattern_cache(db_session)

        top5 = cache.get_top_patterns(limit=5)
        assert len(top5) == 5
        scores = [p.get("fitness_score", 0) for p in top5]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Agent Index Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.requires_db
class TestAgentIndex:
    """Tests for agent index loading and retrieval."""

    async def test_load_agent_index(self, db_session: AsyncSession):
        """Loading agent index should populate all active agents."""
        agents = await _seed_agents(db_session, count=5)

        cache = StateCacheService()
        result = await cache.load_agent_index(db_session)

        assert len(result) >= 5
        for a in agents:
            assert a.agent_id in result
            indexed = result[a.agent_id]
            assert indexed["agent_id"] == a.agent_id
            assert indexed["generation"] == a.generation

    async def test_get_agent_metadata(self, db_session: AsyncSession):
        """get_agent_metadata should return the indexed agent dict."""
        agents = await _seed_agents(db_session, count=3)

        cache = StateCacheService()
        await cache.load_agent_index(db_session)

        meta = cache.get_agent_metadata(agents[1].agent_id)
        assert meta is not None
        assert meta["agent_id"] == agents[1].agent_id

    async def test_retired_agents_excluded_from_index(self, db_session: AsyncSession):
        """Only active agents should appear in the index."""
        active = _make_agent(fitness=60.0, status="active")
        retired = _make_agent(fitness=80.0, status="retired")
        db_session.add_all([active, retired])
        await db_session.flush()

        cache = StateCacheService()
        await cache.load_agent_index(db_session)

        assert active.agent_id in cache.agent_index
        assert retired.agent_id not in cache.agent_index

    async def test_get_top_agents_from_index(self, db_session: AsyncSession):
        """get_top_agents should return agents sorted by fitness desc."""
        await _seed_agents(db_session, count=8)

        cache = StateCacheService()
        await cache.load_agent_index(db_session)

        top3 = cache.get_top_agents(limit=3)
        assert len(top3) == 3
        scores = [a.get("fitness_score", 0) for a in top3]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Cache Invalidation and Refresh Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.requires_db
class TestCacheInvalidation:
    """Tests for cache invalidation and refresh."""

    async def test_invalidate_pattern_cache(self, db_session: AsyncSession):
        """invalidate_pattern_cache should clear and mark as unloaded."""
        await _seed_patterns(db_session, count=3)

        cache = StateCacheService()
        await cache.load_pattern_cache(db_session)
        assert cache._pattern_cache_loaded is True
        assert len(cache.pattern_cache) >= 3

        cache.invalidate_pattern_cache()
        assert cache._pattern_cache_loaded is False
        assert len(cache.pattern_cache) == 0

    async def test_invalidate_agent_index(self, db_session: AsyncSession):
        """invalidate_agent_index should clear and mark as unloaded."""
        await _seed_agents(db_session, count=3)

        cache = StateCacheService()
        await cache.load_agent_index(db_session)
        assert cache._agent_index_loaded is True

        cache.invalidate_agent_index()
        assert cache._agent_index_loaded is False
        assert len(cache.agent_index) == 0

    async def test_invalidate_all(self, db_session: AsyncSession):
        """invalidate_all should clear both caches."""
        await _seed_agents(db_session, count=2)
        await _seed_patterns(db_session, count=2)

        cache = StateCacheService()
        await cache.refresh_caches(db_session)
        assert cache._pattern_cache_loaded is True
        assert cache._agent_index_loaded is True

        cache.invalidate_all()
        assert cache._pattern_cache_loaded is False
        assert cache._agent_index_loaded is False

    async def test_refresh_caches_reloads_both(self, db_session: AsyncSession):
        """refresh_caches should force-reload both caches."""
        agents = await _seed_agents(db_session, count=3)
        patterns = await _seed_patterns(db_session, count=3)

        cache = StateCacheService()
        await cache.refresh_caches(db_session)

        stats = cache.get_cache_stats()
        assert stats["pattern_cache_loaded"] is True
        assert stats["agent_index_loaded"] is True
        assert stats["pattern_cache_size"] >= 3
        assert stats["agent_index_size"] >= 3

    async def test_load_skips_if_already_loaded(self, db_session: AsyncSession):
        """Loading without force_reload should use existing cache."""
        await _seed_patterns(db_session, count=3)

        cache = StateCacheService()
        first_load = await cache.load_pattern_cache(db_session)
        first_size = len(first_load)

        # Add more patterns but don't force reload
        await _seed_patterns(db_session, count=5)
        second_load = await cache.load_pattern_cache(db_session)  # No force
        assert len(second_load) == first_size

        # Force reload should pick up the new patterns
        third_load = await cache.load_pattern_cache(db_session, force_reload=True)
        assert len(third_load) >= first_size + 5


# ---------------------------------------------------------------------------
# Cache Stats Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.requires_db
class TestCacheStats:
    """Tests for get_cache_stats."""

    async def test_stats_before_loading(self, db_session: AsyncSession):
        """Before loading, stats should show unloaded and empty."""
        cache = StateCacheService()
        stats = cache.get_cache_stats()

        assert stats["pattern_cache_loaded"] is False
        assert stats["pattern_cache_size"] == 0
        assert stats["agent_index_loaded"] is False
        assert stats["agent_index_size"] == 0

    async def test_stats_after_loading(self, db_session: AsyncSession):
        """After loading, stats should reflect actual counts."""
        await _seed_agents(db_session, count=7)
        await _seed_patterns(db_session, count=4)

        cache = StateCacheService()
        await cache.refresh_caches(db_session)
        stats = cache.get_cache_stats()

        assert stats["pattern_cache_loaded"] is True
        assert stats["pattern_cache_size"] >= 4
        assert stats["agent_index_loaded"] is True
        assert stats["agent_index_size"] >= 7
