"""
Pattern Service Comprehensive Tests - 40 tests.

Tests CRUD operations, validation, tier assignment, spawn eligibility,
batch operations, and edge cases for pattern_service.py (1,441 lines).

All async tests use unittest.mock.AsyncMock for DB session isolation.
No database required.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from Fast_Swarm.Patterns.Models.pattern_models import Pattern
from Fast_Swarm.Patterns.Services.pattern_service import (
    BOTTOM_PERCENT_CULL,
    DEMOTION_TIER_1_THRESHOLD,
    DEMOTION_TIER_2_THRESHOLD,
    FITNESS_CULL_THRESHOLD,
    FITNESS_TIER_1_THRESHOLD,
    FITNESS_TIER_2_THRESHOLD,
    MIN_ASSETS_TESTED,
    MIN_BACKTEST_WINDOWS,
    MIN_TRADES_FOR_PROMOTION,
    MUTATION_RATE,
    REQUIRED_TIMEFRAMES,
    TOP_PERCENT_CLONE,
    VALID_ORIGINS,
    VALID_TIERS,
    apply_selection_pressure_dict,
    calculate_pattern_fitness,
    crossover_patterns_dict,
    get_tier_from_fitness,
    get_tiers_by_quintile,
    is_assignable_to_agent_dict,
    is_cull_eligible,
    is_spawn_eligible,
    mutate_condition_dict,
    mutate_conditions_dict,
    mutate_pattern_dict,
    should_cull_dict,
    should_demote,
    should_demote_dict,
    should_promote,
    should_promote_dict,
    validate_conditions,
    validate_origin,
    validate_tier,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_pattern_dict(
    pattern_id: str | None = None,
    fitness_score: float = 50.0,
    tier: int = 3,
    number_of_runs: int = 0,
    status: str = "active",
    entry_conditions: list | None = None,
    exit_conditions: list | None = None,
    **kwargs,
) -> dict[str, Any]:
    """Create a pattern dict for pure-function testing."""
    return {
        "pattern_id": pattern_id or f"pat-{uuid.uuid4().hex[:8]}",
        "name": "Test Pattern",
        "fitness_score": fitness_score,
        "tier": tier,
        "number_of_runs": number_of_runs,
        "total_runs": number_of_runs,
        "backtest_count": number_of_runs,
        "status": status,
        "origin": "technical",
        "entry_conditions": entry_conditions or [{"indicator": "rsi", "min": 20, "max": 30}],
        "exit_conditions": exit_conditions or [{"indicator": "rsi", "min": 70, "max": 80}],
        "generation": 1,
        "assets_tested": kwargs.pop("assets_tested", []),
        "timeframes_tested": kwargs.pop("timeframes_tested", []),
        **kwargs,
    }


def _make_spawn_eligible_pattern(tier: int = 1, fitness: float = 90.0) -> dict[str, Any]:
    """Create a pattern that meets all spawn eligibility requirements."""
    return _make_pattern_dict(
        fitness_score=fitness,
        tier=tier,
        number_of_runs=200,
        assets_tested=["BTC", "ETH", "SOL"],
        timeframes_tested=["1m", "15m", "1h", "1d"],
    )


# =============================================================================
# CRUD Operations (~10 tests)
# =============================================================================


class TestPatternCRUD:
    """Test create, get, update, delete, list operations."""

    @pytest.mark.asyncio
    async def test_create_pattern_returns_pattern_with_id(self):
        """create_pattern should return a Pattern with a UUID pattern_id."""
        from Fast_Swarm.Patterns.Services.pattern_service import create_pattern

        session = AsyncMock()
        session.flush = AsyncMock()

        with patch(
            "Fast_Swarm.Patterns.Services.pattern_service.validate_conditions",
            return_value=(True, ""),
        ):
            result = await create_pattern(
                session=session,
                name="RSI Oversold",
                entry_conditions=[{"indicator": "rsi", "min": 20, "max": 30}],
                origin="technical",
            )

        assert isinstance(result, Pattern)
        assert result.pattern_id is not None
        assert result.name == "RSI Oversold"
        assert result.origin == "technical"
        assert result.status == "untested"
        assert result.is_active is True
        assert result.fitness_score == 50.0
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_pattern_with_exit_conditions(self):
        """create_pattern should store both entry and exit conditions."""
        from Fast_Swarm.Patterns.Services.pattern_service import create_pattern

        session = AsyncMock()
        session.flush = AsyncMock()

        entry = [{"indicator": "rsi", "min": 20, "max": 30}]
        exit_conds = [{"indicator": "rsi", "min": 70, "max": 80}]

        with patch(
            "Fast_Swarm.Patterns.Services.pattern_service.validate_conditions",
            return_value=(True, ""),
        ):
            result = await create_pattern(
                session=session,
                name="RSI Bounce",
                entry_conditions=entry,
                exit_conditions=exit_conds,
                origin="technical",
            )

        assert len(result.exit_conditions) == 1
        assert result.exit_conditions[0]["indicator"] == "rsi"

    @pytest.mark.asyncio
    async def test_create_pattern_invalid_origin_raises(self):
        """create_pattern should raise ValueError for invalid origin."""
        from Fast_Swarm.Patterns.Services.pattern_service import create_pattern

        session = AsyncMock()
        with pytest.raises(ValueError, match="Invalid origin"):
            await create_pattern(
                session=session,
                name="Bad Pattern",
                entry_conditions=[{"indicator": "rsi"}],
                origin="invalid_origin",
            )

    @pytest.mark.asyncio
    async def test_get_pattern_by_id_found(self):
        """get_pattern_by_id should return pattern when found."""
        from Fast_Swarm.Patterns.Services.pattern_service import get_pattern_by_id

        mock_pattern = Pattern(
            pattern_id="test-123",
            name="Test",
            status="active",
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_pattern

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        result = await get_pattern_by_id(session, "test-123")
        assert result is not None
        assert result.pattern_id == "test-123"

    @pytest.mark.asyncio
    async def test_get_pattern_by_id_not_found(self):
        """get_pattern_by_id should return None when pattern not found."""
        from Fast_Swarm.Patterns.Services.pattern_service import get_pattern_by_id

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        result = await get_pattern_by_id(session, "nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_pattern_applies_changes(self):
        """update_pattern should apply field updates and set updated_at."""
        from Fast_Swarm.Patterns.Services.pattern_service import update_pattern

        mock_pattern = Pattern(
            pattern_id="upd-123",
            name="Old Name",
            fitness_score=50.0,
            status="active",
        )

        with patch(
            "Fast_Swarm.Patterns.Services.pattern_service.get_pattern_by_id",
            return_value=mock_pattern,
        ):
            session = AsyncMock()
            session.flush = AsyncMock()

            result = await update_pattern(session, "upd-123", name="New Name")

        assert result.name == "New Name"
        assert result.updated_at is not None

    @pytest.mark.asyncio
    async def test_update_pattern_bounds_fitness_score(self):
        """update_pattern should clamp fitness_score to [0, 100]."""
        from Fast_Swarm.Patterns.Services.pattern_service import update_pattern

        mock_pattern = Pattern(
            pattern_id="bound-123",
            name="Test",
            fitness_score=50.0,
            status="active",
        )

        with patch(
            "Fast_Swarm.Patterns.Services.pattern_service.get_pattern_by_id",
            return_value=mock_pattern,
        ):
            session = AsyncMock()
            session.flush = AsyncMock()

            result = await update_pattern(session, "bound-123", fitness_score=150.0)
            assert result.fitness_score == 100.0

            result = await update_pattern(session, "bound-123", fitness_score=-20.0)
            assert result.fitness_score == 0.0

    @pytest.mark.asyncio
    async def test_update_pattern_not_found_raises(self):
        """update_pattern should raise ValueError if pattern not found."""
        from Fast_Swarm.Patterns.Services.pattern_service import update_pattern

        with patch(
            "Fast_Swarm.Patterns.Services.pattern_service.get_pattern_by_id",
            return_value=None,
        ):
            session = AsyncMock()
            with pytest.raises(ValueError, match="Pattern not found"):
                await update_pattern(session, "missing-123", name="Nope")

    @pytest.mark.asyncio
    async def test_soft_delete_pattern_archives(self):
        """soft_delete_pattern should set status to 'archived' and deactivate."""
        from Fast_Swarm.Patterns.Services.pattern_service import soft_delete_pattern

        mock_pattern = Pattern(
            pattern_id="del-123",
            name="To Delete",
            status="active",
            is_active=True,
            assigned_agent_id="agent-1",
        )

        with patch(
            "Fast_Swarm.Patterns.Services.pattern_service.get_pattern_by_id",
            return_value=mock_pattern,
        ):
            session = AsyncMock()
            session.flush = AsyncMock()

            result = await soft_delete_pattern(session, "del-123")

        assert result is True
        assert mock_pattern.status == "archived"
        assert mock_pattern.is_active is False
        assert mock_pattern.assigned_agent_id is None

    @pytest.mark.asyncio
    async def test_get_all_patterns_pagination(self):
        """get_all_patterns should respect limit and offset."""
        from Fast_Swarm.Patterns.Services.pattern_service import get_all_patterns

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            Pattern(pattern_id=f"p-{i}", name=f"Pattern {i}") for i in range(5)
        ]

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        result = await get_all_patterns(session, limit=5, offset=10)
        assert len(result) == 5
        session.execute.assert_awaited_once()


# =============================================================================
# Validation (~8 tests)
# =============================================================================


class TestValidation:
    """Test validation of origins, tiers, and conditions."""

    def test_validate_origin_valid(self):
        """All valid origins should pass validation."""
        for origin in VALID_ORIGINS:
            is_valid, error = validate_origin(origin)
            assert is_valid, f"Origin '{origin}' should be valid"
            assert error == ""

    def test_validate_origin_invalid(self):
        """Invalid origins should fail validation."""
        is_valid, error = validate_origin("invalid")
        assert not is_valid
        assert "Invalid origin" in error

    def test_validate_tier_valid(self):
        """All valid tiers should pass validation."""
        for tier in VALID_TIERS:
            is_valid, error = validate_tier(tier)
            assert is_valid
            assert error == ""

    def test_validate_tier_invalid(self):
        """Invalid tiers should fail validation."""
        is_valid, error = validate_tier(99)
        assert not is_valid
        assert "Invalid tier" in error

    def test_validate_conditions_valid(self):
        """Well-formed conditions should pass validation."""
        conditions = [{"indicator": "rsi", "min": 20, "max": 30}]
        with patch(
            "Fast_Swarm.Patterns.Services.pattern_service.INDICATORS",
            new=["rsi", "macd", "volume_ratio"],
        ):
            with patch(
                "Fast_Swarm.Patterns.Services.pattern_matching_service.INDICATORS",
                new=["rsi", "macd", "volume_ratio"],
            ):
                is_valid, error = validate_conditions(conditions)
        assert is_valid

    def test_validate_conditions_not_a_list(self):
        """Non-list conditions should fail validation."""
        is_valid, error = validate_conditions("not a list")
        assert not is_valid
        assert "must be a list" in error

    def test_validate_conditions_missing_indicator(self):
        """Conditions without 'indicator' key should fail."""
        conditions = [{"min": 20, "max": 30}]
        is_valid, error = validate_conditions(conditions)
        assert not is_valid
        assert "missing 'indicator'" in error

    def test_validate_conditions_min_greater_than_max(self):
        """Conditions with min > max should fail."""
        conditions = [{"indicator": "rsi", "min": 80, "max": 20}]
        with patch(
            "Fast_Swarm.Patterns.Services.pattern_matching_service.INDICATORS",
            new=["rsi"],
        ):
            is_valid, error = validate_conditions(conditions)
        assert not is_valid
        assert "min" in error.lower()

    def test_validate_conditions_non_dict_element(self):
        """Conditions containing non-dict elements should fail."""
        conditions = [{"indicator": "rsi"}, "not_a_dict"]
        is_valid, error = validate_conditions(conditions)
        assert not is_valid
        assert "must be a dict" in error


# =============================================================================
# Tier Assignment (~6 tests)
# =============================================================================


class TestTierAssignment:
    """Test tier determination from fitness scores and quintile system."""

    def test_get_tier_from_fitness_tier_1(self):
        """Fitness >= 80 should be tier 1 (legacy)."""
        assert get_tier_from_fitness(80) == 1
        assert get_tier_from_fitness(100) == 1
        assert get_tier_from_fitness(85) == 1

    def test_get_tier_from_fitness_tier_2(self):
        """Fitness 60-79 should be tier 2 (legacy)."""
        assert get_tier_from_fitness(60) == 2
        assert get_tier_from_fitness(79.9) == 2

    def test_get_tier_from_fitness_tier_3(self):
        """Fitness < 60 should be tier 3 (legacy)."""
        assert get_tier_from_fitness(59.9) == 3
        assert get_tier_from_fitness(0) == 3

    def test_get_tiers_by_quintile_empty(self):
        """Empty pattern list should return empty dict."""
        assert get_tiers_by_quintile([]) == {}

    def test_get_tiers_by_quintile_correct_distribution(self):
        """10 patterns should distribute as 2 per quintile (tiers 1-5)."""
        patterns = [
            {"pattern_id": f"p-{i}", "fitness_score": 100 - i * 10}
            for i in range(10)
        ]
        tiers = get_tiers_by_quintile(patterns)

        assert len(tiers) == 10
        # Top 20% (indices 0-1) = tier 1
        assert tiers["p-0"] == 1
        assert tiers["p-1"] == 1
        # 20-40% (indices 2-3) = tier 2
        assert tiers["p-2"] == 2
        assert tiers["p-3"] == 2
        # 40-60% = tier 3
        assert tiers["p-4"] == 3
        assert tiers["p-5"] == 3
        # 60-80% = tier 4
        assert tiers["p-6"] == 4
        assert tiers["p-7"] == 4
        # Bottom 20% = tier 5
        assert tiers["p-8"] == 5
        assert tiers["p-9"] == 5

    def test_get_tiers_by_quintile_single_pattern(self):
        """Single pattern should be tier 1 (top of population)."""
        patterns = [{"pattern_id": "solo", "fitness_score": 50}]
        tiers = get_tiers_by_quintile(patterns)
        assert tiers["solo"] == 1


# =============================================================================
# Spawn Eligibility (~6 tests)
# =============================================================================


class TestSpawnEligibility:
    """Test spawn eligibility criteria for patterns."""

    def test_spawn_eligible_tier_1_int(self):
        """Tier 1 (int) should be spawn eligible."""
        assert is_spawn_eligible(1) is True

    def test_spawn_eligible_tier_2_int(self):
        """Tier 2 (int) should be spawn eligible."""
        assert is_spawn_eligible(2) is True

    def test_spawn_ineligible_tier_3_int(self):
        """Tier 3+ (int) should NOT be spawn eligible."""
        assert is_spawn_eligible(3) is False
        assert is_spawn_eligible(4) is False
        assert is_spawn_eligible(5) is False

    def test_spawn_eligible_full_pattern(self):
        """Pattern meeting all requirements should be spawn eligible."""
        pattern = _make_spawn_eligible_pattern(tier=1)
        assert is_spawn_eligible(pattern) is True

    def test_spawn_ineligible_insufficient_backtests(self):
        """Pattern with < MIN_BACKTEST_WINDOWS should not be eligible."""
        pattern = _make_spawn_eligible_pattern(tier=1)
        pattern["backtest_count"] = MIN_BACKTEST_WINDOWS - 1
        pattern["total_runs"] = MIN_BACKTEST_WINDOWS - 1
        assert is_spawn_eligible(pattern) is False

    def test_spawn_ineligible_insufficient_assets(self):
        """Pattern tested on < MIN_ASSETS_TESTED assets should not be eligible."""
        pattern = _make_spawn_eligible_pattern(tier=1)
        pattern["assets_tested"] = ["BTC"]  # Need 3+
        assert is_spawn_eligible(pattern) is False

    def test_spawn_ineligible_missing_timeframes(self):
        """Pattern missing required timeframes should not be eligible."""
        pattern = _make_spawn_eligible_pattern(tier=1)
        pattern["timeframes_tested"] = ["1h", "1d"]  # Missing 1m, 15m
        assert is_spawn_eligible(pattern) is False

    def test_cull_eligible_tier_5_with_testing(self):
        """Tier 5 pattern with sufficient testing should be cull eligible."""
        pattern = _make_spawn_eligible_pattern(tier=1)
        pattern["tier"] = 5
        assert is_cull_eligible(pattern) is True

    def test_cull_ineligible_tier_5_undertested(self):
        """Tier 5 pattern without sufficient testing should NOT be cull eligible."""
        pattern = _make_pattern_dict(tier=5, number_of_runs=10)
        assert is_cull_eligible(pattern) is False


# =============================================================================
# Promotion / Demotion / Cull Logic (~5 tests)
# =============================================================================


class TestPromotionDemotion:
    """Test promotion, demotion, and cull logic."""

    def test_should_promote_tier_3_to_2(self):
        """Tier 3 with fitness >= 60 and enough trades should promote to tier 2."""
        pattern = _make_pattern_dict(
            tier=3, fitness_score=65, number_of_runs=30,
        )
        result = should_promote_dict(pattern)
        assert result == 2

    def test_should_promote_tier_2_to_1(self):
        """Tier 2 with fitness >= 80 and enough trades should promote to tier 1."""
        pattern = _make_pattern_dict(
            tier=2, fitness_score=85, number_of_runs=30,
        )
        result = should_promote_dict(pattern)
        assert result == 1

    def test_should_not_promote_insufficient_trades(self):
        """Pattern with too few trades should not promote regardless of fitness."""
        pattern = _make_pattern_dict(
            tier=3, fitness_score=90, number_of_runs=MIN_TRADES_FOR_PROMOTION - 1,
        )
        result = should_promote_dict(pattern)
        assert result is None

    def test_should_demote_tier_1_low_fitness(self):
        """Tier 1 pattern with fitness < 70 should demote to tier 2."""
        pattern = _make_pattern_dict(tier=1, fitness_score=60)
        result = should_demote_dict(pattern)
        assert result == 2

    def test_should_demote_tier_2_low_fitness(self):
        """Tier 2 pattern with fitness < 50 should demote to tier 3."""
        pattern = _make_pattern_dict(tier=2, fitness_score=40)
        result = should_demote_dict(pattern)
        assert result == 3

    def test_should_not_demote_healthy_pattern(self):
        """Pattern with good fitness should not be demoted."""
        pattern = _make_pattern_dict(tier=1, fitness_score=85)
        result = should_demote_dict(pattern)
        assert result is None

    def test_should_cull_tier_3_below_threshold(self):
        """Tier 3 pattern with fitness < 40 should be culled."""
        pattern = _make_pattern_dict(tier=3, fitness_score=30)
        assert should_cull_dict(pattern) is True

    def test_should_not_cull_above_threshold(self):
        """Pattern with fitness >= 40 should not be culled."""
        pattern = _make_pattern_dict(tier=3, fitness_score=50)
        assert should_cull_dict(pattern) is False


# =============================================================================
# Batch Operations (~5 tests)
# =============================================================================


class TestBatchOperations:
    """Test batch create, selection pressure, and mutation operations."""

    @pytest.mark.asyncio
    async def test_batch_create_patterns_returns_ids(self):
        """batch_create_patterns should return list of pattern_ids."""
        from Fast_Swarm.Patterns.Services.pattern_service import batch_create_patterns

        session = AsyncMock()
        session.flush = AsyncMock()

        patterns_data = [
            {
                "name": f"Pattern {i}",
                "entry_conditions": [{"indicator": "rsi", "min": 20}],
                "origin": "technical",
            }
            for i in range(3)
        ]

        with patch(
            "Fast_Swarm.Patterns.Services.pattern_service.validate_conditions",
            return_value=(True, ""),
        ):
            result = await batch_create_patterns(session, patterns_data)

        assert len(result) == 3
        assert all(isinstance(pid, str) for pid in result)

    def test_selection_pressure_empty_list(self):
        """Selection pressure on empty list should return zeros."""
        result = apply_selection_pressure_dict([])
        assert result["cloned_count"] == 0
        assert result["culled_count"] == 0
        assert result["survivors"] == []

    def test_selection_pressure_culls_low_fitness(self):
        """Selection pressure should cull patterns below fitness threshold."""
        patterns = [
            _make_pattern_dict(pattern_id=f"p-{i}", fitness_score=i * 10)
            for i in range(10)
        ]
        result = apply_selection_pressure_dict(patterns)

        # Patterns with fitness < 40 should be culled
        assert result["culled_count"] > 0
        for culled in result["culled"]:
            assert culled["fitness_score"] < FITNESS_CULL_THRESHOLD

    def test_selection_pressure_clones_top_performers(self):
        """Selection pressure should clone top 20% of patterns."""
        patterns = [
            _make_pattern_dict(pattern_id=f"p-{i}", fitness_score=50 + i * 5)
            for i in range(10)
        ]

        with patch(
            "Fast_Swarm.Patterns.Services.pattern_service.mutate_pattern_dict",
            side_effect=lambda p, **kw: {**p, "pattern_id": f"clone-{p['pattern_id']}"},
        ):
            result = apply_selection_pressure_dict(patterns)

        assert result["cloned_count"] >= 1

    def test_mutate_pattern_dict_preserves_lineage(self):
        """Mutated pattern should track parent_id and increment generation."""
        parent = _make_pattern_dict(pattern_id="parent-1", generation=3)

        with patch(
            "Fast_Swarm.Patterns.Services.pattern_service.mutate_conditions_dict",
            side_effect=lambda c, r: c,
        ):
            child = mutate_pattern_dict(parent)

        assert child["parent_id"] == "parent-1"
        assert child["generation"] == 4
        assert child["pattern_id"] != "parent-1"
        assert child["fitness_score"] == 50.0  # Reset for new pattern
        assert child["status"] == "untested"


# =============================================================================
# Fitness Calculation (~4 tests)
# =============================================================================


class TestFitnessCalculation:
    """Test pattern fitness calculation formula."""

    def test_fitness_perfect_scores(self):
        """Perfect metrics should yield high (but capped) fitness."""
        fitness = calculate_pattern_fitness(
            roi_pct=50, sharpe_ratio=3, win_rate=1.0, trade_count=200,
        )
        assert fitness == pytest.approx(100.0, abs=1.0)

    def test_fitness_terrible_scores(self):
        """Terrible metrics should yield low fitness."""
        fitness = calculate_pattern_fitness(
            roi_pct=-50, sharpe_ratio=-3, win_rate=0.0, trade_count=0,
        )
        assert fitness == 0.0

    def test_fitness_capped_at_bounds(self):
        """Fitness should always be in [0, 100] regardless of extreme inputs."""
        fitness_high = calculate_pattern_fitness(
            roi_pct=500, sharpe_ratio=50, win_rate=1.0, trade_count=10000,
        )
        fitness_low = calculate_pattern_fitness(
            roi_pct=-500, sharpe_ratio=-50, win_rate=0.0, trade_count=0,
            max_drawdown_pct=100,
        )
        assert 0 <= fitness_high <= 100
        assert 0 <= fitness_low <= 100

    def test_fitness_drawdown_penalty(self):
        """Higher drawdown should reduce fitness."""
        fitness_no_dd = calculate_pattern_fitness(
            roi_pct=20, sharpe_ratio=1.5, win_rate=0.6, trade_count=50,
            max_drawdown_pct=0,
        )
        fitness_high_dd = calculate_pattern_fitness(
            roi_pct=20, sharpe_ratio=1.5, win_rate=0.6, trade_count=50,
            max_drawdown_pct=30,
        )
        assert fitness_no_dd > fitness_high_dd

    def test_fitness_from_backtest_dict(self):
        """calculate_pattern_fitness should accept a backtest dict."""
        backtest = {
            "total_trades": 100,
            "winning_trades": 60,
            "total_roi_pct": 15.0,
            "sharpe_ratio": 1.2,
            "max_drawdown_pct": 10.0,
        }
        fitness = calculate_pattern_fitness(backtest)
        assert 0 <= fitness <= 100


# =============================================================================
# Evolution / Mutation (~3 tests)
# =============================================================================


class TestEvolution:
    """Test mutation and crossover operations."""

    def test_mutate_condition_changes_bounds(self):
        """Mutation should change min/max within mutation rate."""
        condition = {"indicator": "rsi", "min": 30.0, "max": 70.0}

        with patch(
            "Fast_Swarm.Patterns.Services.pattern_service.INDICATOR_BOUNDS",
            new={"rsi": (0, 100)},
        ):
            mutated = mutate_condition_dict(condition, mutation_rate=0.10)

        assert mutated["indicator"] == "rsi"
        # Values should change but stay within bounded range
        assert mutated["min"] != condition["min"] or mutated["max"] != condition["max"]
        assert mutated["min"] <= mutated["max"]

    def test_mutate_condition_ensures_min_leq_max(self):
        """Mutation should swap min/max if mutation inverts them."""
        # Set up a condition where mutation could potentially invert min/max
        condition = {"indicator": "rsi", "min": 49.0, "max": 51.0}

        with patch(
            "Fast_Swarm.Patterns.Services.pattern_service.INDICATOR_BOUNDS",
            new={"rsi": (0, 100)},
        ):
            # Run many times to exercise the swap path
            for _ in range(50):
                mutated = mutate_condition_dict(condition, mutation_rate=0.20)
                assert mutated["min"] <= mutated["max"], (
                    f"min={mutated['min']} > max={mutated['max']}"
                )

    def test_crossover_patterns_dict_combines_conditions(self):
        """Crossover should combine entry/exit conditions from both parents."""
        parent_a = _make_pattern_dict(
            pattern_id="parent-a",
            entry_conditions=[
                {"indicator": "rsi", "min": 20},
                {"indicator": "macd", "min": 0},
            ],
            exit_conditions=[
                {"indicator": "rsi", "max": 80},
            ],
        )
        parent_b = _make_pattern_dict(
            pattern_id="parent-b",
            entry_conditions=[
                {"indicator": "adx", "min": 25},
                {"indicator": "atr", "min": 1.0},
            ],
            exit_conditions=[
                {"indicator": "adx", "max": 50},
            ],
        )

        child = crossover_patterns_dict(parent_a, parent_b)

        assert child["origin"] == "hybrid"
        assert child["parent_a_id"] == "parent-a"
        assert child["parent_b_id"] == "parent-b"
        assert len(child["entry_conditions"]) > 0
        assert child["fitness_score"] == 50.0  # Reset
        assert child["status"] == "untested"


# =============================================================================
# Edge Cases (~5 tests)
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_conditions_pattern(self):
        """Pattern with empty entry_conditions should still work for dict functions."""
        pattern = _make_pattern_dict(entry_conditions=[], exit_conditions=[])
        child = mutate_pattern_dict(pattern)
        assert child["entry_conditions"] == []
        assert child["exit_conditions"] == []

    def test_is_assignable_archived_pattern(self):
        """Archived patterns should not be assignable regardless of tier."""
        pattern = _make_pattern_dict(tier=1, status="archived")
        assert is_assignable_to_agent_dict(pattern) is False

    def test_is_assignable_active_tier_1(self):
        """Active tier 1 pattern should be assignable."""
        pattern = _make_pattern_dict(tier=1, status="active")
        assert is_assignable_to_agent_dict(pattern) is True

    def test_is_assignable_active_tier_3(self):
        """Active tier 3 pattern should NOT be assignable."""
        pattern = _make_pattern_dict(tier=3, status="active")
        assert is_assignable_to_agent_dict(pattern) is False

    @pytest.mark.asyncio
    async def test_soft_delete_not_found_raises(self):
        """soft_delete_pattern should raise ValueError for nonexistent pattern."""
        from Fast_Swarm.Patterns.Services.pattern_service import soft_delete_pattern

        with patch(
            "Fast_Swarm.Patterns.Services.pattern_service.get_pattern_by_id",
            return_value=None,
        ):
            session = AsyncMock()
            with pytest.raises(ValueError, match="Pattern not found"):
                await soft_delete_pattern(session, "missing-id")

    def test_quintile_tiers_with_none_fitness(self):
        """Patterns with None fitness should sort to the bottom."""
        patterns = [
            {"pattern_id": "good", "fitness_score": 80},
            {"pattern_id": "none1", "fitness_score": None},
            {"pattern_id": "mid", "fitness_score": 50},
            {"pattern_id": "none2", "fitness_score": None},
            {"pattern_id": "low", "fitness_score": 10},
        ]
        tiers = get_tiers_by_quintile(patterns)
        assert tiers["good"] == 1
        assert tiers["none1"] in [4, 5]  # None fitness sorts low
        assert tiers["none2"] in [4, 5]

    def test_spawn_eligible_none_tier_kwarg(self):
        """is_spawn_eligible with tier=None and pattern_or_tier=None should return False."""
        assert is_spawn_eligible(None, tier=None) is False

    def test_mutate_conditions_dict_empty_list(self):
        """Mutating empty conditions list should return empty list."""
        result = mutate_conditions_dict([], mutation_rate=0.10)
        assert result == []
