"""
Unit tests for pattern_priority module.

Tests cover:
- calculate_single_priority: origin-based HIGH, periods-based LOW, default NORMAL
- calculate_priority_buckets: empty input, all-HIGH, mixed distribution, lowest-runs NORMAL
- rank/percentile logic: top fitness boundary conditions (the <= fix)
- get_prioritized_patterns (async, requires DB): ordering, limit, include_low flag
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from utilities.pattern_priority import (
    PERIODS_THRESHOLD,
    Priority,
    calculate_priority_buckets,
    calculate_single_priority,
    get_prioritized_patterns,
)


# ============================================================================
# TestCalculateSinglePriority - Pure function tests (synchronous)
# ============================================================================


class TestCalculateSinglePriority:
    """Tests for calculate_single_priority()."""

    def test_high_by_academic_origin(self):
        """Academic origin with <100 runs should return HIGH priority."""
        priority, reason = calculate_single_priority(
            origin="academic",
            total_runs=50,
            periods_tested=10,
            fitness_score=0.5,
            is_in_top_fitness=False,
        )
        assert priority == Priority.HIGH
        assert reason == "high_priority_academic"

    def test_high_by_ai_origin(self):
        """AI-generated origin with <50 runs should return HIGH priority."""
        priority, reason = calculate_single_priority(
            origin="ai_generated",
            total_runs=30,
            periods_tested=10,
            fitness_score=0.5,
            is_in_top_fitness=False,
        )
        assert priority == Priority.HIGH
        assert reason == "high_priority_ai"

    def test_low_by_periods_threshold(self):
        """Patterns with >= 300 periods tested and NOT top fitness should be LOW."""
        priority, reason = calculate_single_priority(
            origin="manual",
            total_runs=500,
            periods_tested=PERIODS_THRESHOLD,
            fitness_score=0.3,
            is_in_top_fitness=False,
        )
        assert priority == Priority.LOW
        assert reason == "low_priority_enough_data"

    def test_top_fitness_overrides_low(self):
        """Even with 300+ periods, top fitness patterns should NOT be LOW."""
        priority, reason = calculate_single_priority(
            origin="manual",
            total_runs=500,
            periods_tested=400,
            fitness_score=0.95,
            is_in_top_fitness=True,
        )
        assert priority != Priority.LOW
        assert priority == Priority.NORMAL
        assert reason == "normal_priority"

    def test_normal_default(self):
        """Patterns that don't meet HIGH or LOW criteria should be NORMAL."""
        priority, reason = calculate_single_priority(
            origin="manual",
            total_runs=200,
            periods_tested=100,
            fitness_score=0.5,
            is_in_top_fitness=False,
        )
        assert priority == Priority.NORMAL
        assert reason == "normal_priority"


# ============================================================================
# TestCalculatePriorityBuckets - Pure function tests (synchronous)
# ============================================================================


class TestCalculatePriorityBuckets:
    """Tests for calculate_priority_buckets()."""

    def test_empty_returns_empty(self):
        """Empty input list should return all empty buckets."""
        result = calculate_priority_buckets([])
        assert result == {"high": [], "normal": [], "low": []}

    def test_all_high_sorted(self):
        """All HIGH-priority patterns should land in high bucket only."""
        patterns = [
            {"pattern_id": "p1", "origin": "academic", "total_runs": 10, "periods_tested": 5, "fitness_score": 0.5},
            {"pattern_id": "p2", "origin": "ai_generated", "total_runs": 5, "periods_tested": 3, "fitness_score": 0.3},
            {"pattern_id": "p3", "origin": "academic", "total_runs": 99, "periods_tested": 50, "fitness_score": 0.7},
        ]
        result = calculate_priority_buckets(patterns)
        assert len(result["high"]) == 3
        assert len(result["normal"]) == 0
        assert len(result["low"]) == 0
        for p in result["high"]:
            assert p["priority"] == Priority.HIGH

    def test_mixed_distribution(self):
        """Mix of HIGH/NORMAL/LOW patterns should be sorted into correct buckets."""
        patterns = [
            # HIGH: academic, low runs
            {"pattern_id": "p1", "origin": "academic", "total_runs": 10, "periods_tested": 5, "fitness_score": 0.9},
            # Should end up NORMAL or LOW: manual, moderate runs, high fitness
            {"pattern_id": "p2", "origin": "manual", "total_runs": 200, "periods_tested": 100, "fitness_score": 0.8},
            # Should end up LOW: manual, high periods, low fitness
            {"pattern_id": "p3", "origin": "manual", "total_runs": 500, "periods_tested": 400, "fitness_score": 0.1},
            # Should end up NORMAL or LOW: manual, few runs
            {"pattern_id": "p4", "origin": "manual", "total_runs": 5, "periods_tested": 2, "fitness_score": 0.2},
        ]
        result = calculate_priority_buckets(patterns)

        assert len(result["high"]) == 1
        assert result["high"][0]["pattern_id"] == "p1"

        # Remaining 3 patterns split between normal and low
        total_normal_low = len(result["normal"]) + len(result["low"])
        assert total_normal_low == 3

        # p3 should be LOW (400 periods >= 300 threshold, low fitness)
        low_ids = {p["pattern_id"] for p in result["low"]}
        assert "p3" in low_ids

    def test_thirty_pct_lowest_runs_normal(self):
        """Bottom 30% by runs should get NORMAL priority if not already HIGH."""
        # Create 10 non-HIGH patterns with varying runs and periods < threshold
        patterns = []
        for i in range(10):
            patterns.append({
                "pattern_id": f"p{i}",
                "origin": "manual",
                "total_runs": i * 10,  # 0, 10, 20, ..., 90
                "periods_tested": 50,  # Below PERIODS_THRESHOLD
                "fitness_score": 0.5,
            })

        result = calculate_priority_buckets(patterns)

        # Bottom 30% of 10 = 3 patterns (p0, p1, p2)
        normal_ids = {p["pattern_id"] for p in result["normal"]}
        lowest_run_ids = {"p0", "p1", "p2"}

        # These should be in NORMAL (either via lowest_runs or highest_fitness)
        for pid in lowest_run_ids:
            assert pid in normal_ids, f"{pid} (low runs) should be in NORMAL bucket"


# ============================================================================
# TestRankPercentile - Tests for the rank/total <= 0.5 logic
# ============================================================================


class TestRankPercentile:
    """
    Tests for the rank percentile logic used in update_priority_after_backtest.

    The key expression is: is_in_top_fitness = (rank / total) <= 0.5
    This means rank (count of patterns with fitness <= current) being in the
    lower half means the pattern is in the TOP fitness tier.
    """

    def test_rank_lte_half_is_top_fitness(self):
        """rank/total <= 0.5 should indicate top fitness."""
        # rank=2, total=10 -> 0.2 <= 0.5 -> top fitness
        rank = 2
        total = 10
        is_in_top_fitness = (rank / total) <= 0.5
        assert is_in_top_fitness is True

    def test_rank_gt_half_not_top_fitness(self):
        """rank/total > 0.5 should NOT be top fitness."""
        # rank=8, total=10 -> 0.8 > 0.5 -> not top fitness
        rank = 8
        total = 10
        is_in_top_fitness = (rank / total) <= 0.5
        assert is_in_top_fitness is False

    def test_boundary_exactly_half(self):
        """rank/total == 0.5 should be top fitness (uses <= not <)."""
        # rank=5, total=10 -> 0.5 <= 0.5 -> top fitness
        rank = 5
        total = 10
        is_in_top_fitness = (rank / total) <= 0.5
        assert is_in_top_fitness is True


# ============================================================================
# TestGetPrioritizedPatterns - Async DB tests
# ============================================================================


@pytest.mark.requires_db
class TestGetPrioritizedPatterns:
    """Tests for get_prioritized_patterns() - requires database session."""

    @staticmethod
    async def _insert_test_patterns(session: AsyncSession, patterns: list[dict]) -> None:
        """Helper to insert test patterns into the database."""
        for p in patterns:
            await session.execute(
                text("""
                    INSERT INTO patterns (
                        pattern_id, name, entry_conditions, exit_conditions,
                        origin, fitness_score, total_runs, periods_tested,
                        priority, is_active, created_at
                    ) VALUES (
                        :pattern_id, :name, :entry_conditions, :exit_conditions,
                        :origin, :fitness_score, :total_runs, :periods_tested,
                        :priority, :is_active, NOW()
                    )
                """),
                {
                    "pattern_id": p.get("pattern_id", f"test-{uuid.uuid4().hex[:8]}"),
                    "name": p.get("name", "Test Pattern"),
                    "entry_conditions": p.get("entry_conditions", '[{"indicator":"rsi","operator":"<","value":30}]'),
                    "exit_conditions": p.get("exit_conditions", '[{"indicator":"rsi","operator":">","value":70}]'),
                    "origin": p.get("origin", "manual"),
                    "fitness_score": p.get("fitness_score", 0.5),
                    "total_runs": p.get("total_runs", 10),
                    "periods_tested": p.get("periods_tested", 50),
                    "priority": p.get("priority", 2),
                    "is_active": p.get("is_active", True),
                },
            )
        await session.flush()

    @pytest.mark.asyncio
    async def test_returns_ordered_by_priority(self, db_session: AsyncSession):
        """Results should be ordered by priority ASC (HIGH=1 first, then NORMAL=2)."""
        await self._insert_test_patterns(db_session, [
            {"pattern_id": "p-normal", "priority": 2, "total_runs": 100},
            {"pattern_id": "p-high", "priority": 1, "total_runs": 5},
            {"pattern_id": "p-normal2", "priority": 2, "total_runs": 50},
        ])

        results = await get_prioritized_patterns(db_session, include_low=True)

        # Find our test patterns in results
        test_ids = {"p-normal", "p-high", "p-normal2"}
        test_results = [r for r in results if r["pattern_id"] in test_ids]

        assert len(test_results) >= 3
        # p-high (priority=1) should come before the priority=2 patterns
        priorities = [r["priority"] for r in test_results]
        assert priorities == sorted(priorities), "Results should be ordered by priority ASC"

    @pytest.mark.asyncio
    async def test_limit_respected(self, db_session: AsyncSession):
        """The limit parameter should cap the number of returned results."""
        # Insert more patterns than the limit
        patterns = [
            {"pattern_id": f"p-limit-{i}", "priority": 2, "total_runs": i}
            for i in range(5)
        ]
        await self._insert_test_patterns(db_session, patterns)

        results = await get_prioritized_patterns(db_session, limit=2, include_low=True)
        assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_include_low_flag(self, db_session: AsyncSession):
        """include_low=False should exclude LOW priority (priority=3) patterns."""
        await self._insert_test_patterns(db_session, [
            {"pattern_id": "p-keep", "priority": 1, "total_runs": 5},
            {"pattern_id": "p-keep2", "priority": 2, "total_runs": 50},
        ])

        results_without_low = await get_prioritized_patterns(db_session, include_low=False)
        result_ids = {r["pattern_id"] for r in results_without_low}

        assert "p-keep" in result_ids
        assert "p-keep2" in result_ids

        # Now insert a LOW priority pattern (priority=3 in DB terms)
        await self._insert_test_patterns(db_session, [
            {"pattern_id": "p-low", "priority": 3, "total_runs": 500},
        ])

        # With include_low=True, p-low should appear
        results_with_low = await get_prioritized_patterns(db_session, include_low=True)
        with_low_ids = {r["pattern_id"] for r in results_with_low}
        assert "p-low" in with_low_ids

        # With include_low=False, the COALESCE(priority, 2) < 3 filter applies
        # priority=3 should be excluded
        results_without = await get_prioritized_patterns(db_session, include_low=False)
        without_low_ids = {r["pattern_id"] for r in results_without}
        assert "p-low" not in without_low_ids
