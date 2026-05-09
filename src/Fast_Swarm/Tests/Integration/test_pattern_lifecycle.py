"""
Pattern Lifecycle Integration Tests.

Tests the full pattern lifecycle:
discovery -> backtest -> tier assignment -> cull -> redistribution.

Uses transaction rollback for test isolation.
"""

import uuid
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from Fast_Swarm.Patterns.Models.pattern_models import Pattern
from Fast_Swarm.Patterns.Services.pattern_service import (
    create_pattern,
    get_all_patterns,
    get_pattern_by_id,
    get_tiers_by_quintile,
    is_spawn_eligible,
    soft_delete_pattern,
    update_pattern,
    validate_conditions,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def pattern_population(db_session: AsyncSession) -> list[Pattern]:
    """Create 20 patterns with varying fitness scores."""
    patterns = []
    for i in range(20):
        pattern = Pattern(
            pattern_id=f"lifecycle-pat-{uuid.uuid4().hex[:8]}",
            name=f"Lifecycle Pattern {i}",
            entry_conditions=[{"indicator": "rsi_14", "min": 10 + i, "max": 30 + i}],
            exit_conditions=[{"indicator": "rsi_14", "min": 60 + i, "max": 90}],
            origin="technical",
            status="active",
            is_active=True,
            fitness_score=float(i * 5),  # 0 to 95
            total_trades=50,
            total_runs=10,
            backtest_count=150,
            assets_tested=["BTC", "ETH", "SOL"],
            timeframes_tested=["1m", "15m", "1h", "1d"],
        )
        db_session.add(pattern)
        patterns.append(pattern)
    await db_session.flush()
    for p in patterns:
        await db_session.refresh(p)
    return patterns


# ============================================================================
# TESTS
# ============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discovery_backtest_tier_assignment(db_session: AsyncSession):
    """Discover pattern -> backtest -> tier assigned via quintile system."""
    # Create a pattern
    pattern = await create_pattern(
        session=db_session,
        name="Discovery Test Pattern",
        entry_conditions=[{"indicator": "rsi_14", "min": 20, "max": 30}],
        exit_conditions=[{"indicator": "rsi_14", "min": 70, "max": 80}],
        origin="technical",
    )
    assert pattern.pattern_id is not None
    assert pattern.fitness_score == 50.0  # Default

    # Simulate backtest updating fitness
    updated = await update_pattern(
        session=db_session,
        pattern_id=pattern.pattern_id,
        fitness_score=85.0,
        total_trades=100,
    )
    assert updated.fitness_score == 85.0

    # Tier assignment via quintile
    pattern_dicts = [{"pattern_id": pattern.pattern_id, "fitness_score": 85.0}]
    tiers = get_tiers_by_quintile(pattern_dicts)
    assert tiers[pattern.pattern_id] == 1  # Only one pattern = top 20%


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cull_removes_low_fitness(db_session: AsyncSession, pattern_population):
    """Low fitness patterns should be identified for cull via quintile tier 5."""
    pattern_dicts = [
        {"pattern_id": p.pattern_id, "fitness_score": p.fitness_score or 0}
        for p in pattern_population
    ]
    tiers = get_tiers_by_quintile(pattern_dicts)

    # Bottom 20% should be tier 5 (CULL)
    tier_5_patterns = [pid for pid, tier in tiers.items() if tier == 5]
    assert len(tier_5_patterns) == 4  # 20% of 20

    # Verify these are the lowest fitness patterns
    lowest_fitness = sorted(pattern_population, key=lambda p: p.fitness_score or 0)[:4]
    lowest_ids = {p.pattern_id for p in lowest_fitness}
    assert set(tier_5_patterns) == lowest_ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_quintile_redistribution(db_session: AsyncSession, pattern_population):
    """After removing tier 5, remaining patterns should redistribute across tiers."""
    pattern_dicts = [
        {"pattern_id": p.pattern_id, "fitness_score": p.fitness_score or 0}
        for p in pattern_population
    ]
    tiers = get_tiers_by_quintile(pattern_dicts)

    # Remove tier 5 patterns
    remaining = [d for d in pattern_dicts if tiers[d["pattern_id"]] != 5]
    assert len(remaining) == 16  # 20 - 4

    # Recalculate tiers on remaining population
    new_tiers = get_tiers_by_quintile(remaining)
    tier_counts = {}
    for tier in new_tiers.values():
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    # Should redistribute into all 5 quintiles
    # With 16 patterns: ~3-4 per quintile
    assert all(tier in tier_counts for tier in [1, 2, 3, 4, 5])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_priority_recalculation(db_session: AsyncSession, pattern_population):
    """Priorities (tiers) should update after backtest changes fitness."""
    # Get initial tiers
    pattern_dicts = [
        {"pattern_id": p.pattern_id, "fitness_score": p.fitness_score or 0}
        for p in pattern_population
    ]
    initial_tiers = get_tiers_by_quintile(pattern_dicts)

    # Find a tier 5 (bottom) pattern
    bottom_pattern = None
    for p in pattern_population:
        if initial_tiers.get(p.pattern_id) == 5:
            bottom_pattern = p
            break
    assert bottom_pattern is not None

    # Simulate backtest giving it a high score
    bottom_pattern.fitness_score = 999.0
    db_session.add(bottom_pattern)
    await db_session.flush()

    # Recalculate tiers
    updated_dicts = [
        {"pattern_id": p.pattern_id, "fitness_score": p.fitness_score or 0}
        for p in pattern_population
    ]
    new_tiers = get_tiers_by_quintile(updated_dicts)

    # The formerly bottom pattern should now be tier 1
    assert new_tiers[bottom_pattern.pattern_id] == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_spawn_eligibility(db_session: AsyncSession, pattern_population):
    """Only tier 1-2 patterns should be spawn eligible."""
    pattern_dicts = [
        {"pattern_id": p.pattern_id, "fitness_score": p.fitness_score or 0}
        for p in pattern_population
    ]
    tiers = get_tiers_by_quintile(pattern_dicts)

    for pid, tier in tiers.items():
        eligible = is_spawn_eligible(tier=tier)
        if tier in [1, 2]:
            assert eligible, f"Tier {tier} pattern {pid} should be spawn eligible"
        else:
            assert not eligible, f"Tier {tier} pattern {pid} should NOT be spawn eligible"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_batch_backtest_updates_all(db_session: AsyncSession, pattern_population):
    """Batch backtest should update all pattern fitness scores."""
    # Simulate batch backtest by updating all patterns
    for i, pattern in enumerate(pattern_population):
        pattern.fitness_score = float(100 - i * 4)  # New scores
        pattern.total_runs = (pattern.total_runs or 0) + 1
        db_session.add(pattern)
    await db_session.flush()

    # Verify all were updated
    all_patterns = await get_all_patterns(db_session, limit=100)
    updated_count = sum(
        1 for p in all_patterns
        if p.pattern_id in {pp.pattern_id for pp in pattern_population}
        and p.total_runs is not None
        and p.total_runs > 0
    )
    assert updated_count == 20


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pattern_deactivation(db_session: AsyncSession):
    """Deactivated patterns should be excluded from active queries."""
    # Create an active pattern
    pattern = await create_pattern(
        session=db_session,
        name="Deactivation Test",
        entry_conditions=[{"indicator": "rsi_14", "min": 20, "max": 30}],
        exit_conditions=[{"indicator": "rsi_14", "min": 70, "max": 80}],
        origin="technical",
    )
    pid = pattern.pattern_id

    # Soft delete (archive)
    await soft_delete_pattern(db_session, pid)
    await db_session.flush()

    # Pattern should not appear in active queries
    result = await get_pattern_by_id(db_session, pid, include_archived=False)
    assert result is None

    # But should appear with include_archived=True
    result = await get_pattern_by_id(db_session, pid, include_archived=True)
    assert result is not None
    assert result.status == "archived"
    assert result.is_active is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_condition_validation(db_session: AsyncSession):
    """Invalid conditions should be rejected during creation."""
    # Missing indicator
    is_valid, error = validate_conditions([{"min": 20, "max": 30}])
    assert not is_valid
    assert "indicator" in error.lower()

    # min > max
    is_valid, error = validate_conditions([{"indicator": "rsi_14", "min": 80, "max": 20}])
    assert not is_valid
    assert "min" in error.lower()

    # Not a list
    is_valid, error = validate_conditions("not a list")
    assert not is_valid

    # Invalid should raise on create_pattern
    with pytest.raises(ValueError, match="Invalid entry conditions"):
        await create_pattern(
            session=db_session,
            name="Bad Pattern",
            entry_conditions=[{"min": 20}],  # missing indicator
            origin="technical",
        )
