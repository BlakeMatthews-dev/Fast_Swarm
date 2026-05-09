"""
Real-DB integration tests for PatternService CRUD and tier management.

Uses db_session fixture (PostgreSQL with transaction rollback).
Tests create, read, update, soft-delete, tier calculations, and batch ops.
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from Fast_Swarm.Patterns.Models.pattern_models import Pattern
from Fast_Swarm.Patterns.Services.pattern_service import (
    batch_create_patterns,
    create_pattern,
    get_all_patterns,
    get_pattern_by_id,
    get_patterns_by_origin,
    get_patterns_by_tier,
    get_tier_from_fitness,
    get_tiers_by_quintile,
    is_spawn_eligible,
    should_demote,
    should_promote,
    soft_delete_pattern,
    update_pattern,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_ENTRY = [{"indicator": "rsi", "min": 20, "max": 35}]
VALID_EXIT = [{"indicator": "rsi", "min": 65, "max": 80}]


def _make_pattern(
    fitness: float = 50.0,
    origin: str = "technical",
    is_active: bool = True,
    status: str = "untested",
) -> Pattern:
    return Pattern(
        pattern_id=f"pat-{uuid.uuid4().hex[:8]}",
        name=f"Pattern-{uuid.uuid4().hex[:4]}",
        origin=origin,
        status=status,
        is_active=is_active,
        entry_conditions=VALID_ENTRY,
        exit_conditions=VALID_EXIT,
        fitness_score=Decimal(str(fitness)),
        total_trades=0,
        total_runs=0,
    )


# ---------------------------------------------------------------------------
# CRUD Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.requires_db
class TestPatternCRUD:
    """Tests for pattern CRUD operations against real PostgreSQL."""

    async def test_create_pattern_persists(self, db_session: AsyncSession):
        """create_pattern should insert a row and return a Pattern with an ID."""
        pattern = await create_pattern(
            session=db_session,
            name="RSI Oversold Buy",
            entry_conditions=VALID_ENTRY,
            exit_conditions=VALID_EXIT,
            origin="technical",
        )

        assert pattern.id is not None
        assert pattern.pattern_id is not None
        assert pattern.fitness_score == Decimal("50.0")
        assert pattern.status == "untested"
        assert pattern.is_active is True

    async def test_get_pattern_by_id_returns_correct_pattern(self, db_session: AsyncSession):
        """get_pattern_by_id should find the exact pattern."""
        created = await create_pattern(
            session=db_session,
            name="Test Get",
            entry_conditions=VALID_ENTRY,
            origin="technical",
        )

        fetched = await get_pattern_by_id(db_session, created.pattern_id)
        assert fetched is not None
        assert fetched.pattern_id == created.pattern_id
        assert fetched.name == "Test Get"

    async def test_get_pattern_by_id_missing_returns_none(self, db_session: AsyncSession):
        """Missing pattern_id should return None."""
        result = await get_pattern_by_id(db_session, "nonexistent-pattern-id")
        assert result is None

    async def test_update_pattern_changes_fitness(self, db_session: AsyncSession):
        """update_pattern should modify and persist fitness_score."""
        created = await create_pattern(
            session=db_session,
            name="Update Me",
            entry_conditions=VALID_ENTRY,
            origin="technical",
        )

        updated = await update_pattern(db_session, created.pattern_id, fitness_score=85.0)
        assert updated is not None
        assert float(updated.fitness_score) == 85.0

        # Re-fetch to confirm persistence
        refetched = await get_pattern_by_id(db_session, created.pattern_id)
        assert float(refetched.fitness_score) == 85.0

    async def test_update_pattern_bounds_fitness_to_100(self, db_session: AsyncSession):
        """Fitness above 100 should be clamped."""
        created = await create_pattern(
            session=db_session,
            name="High Fitness",
            entry_conditions=VALID_ENTRY,
            origin="technical",
        )

        updated = await update_pattern(db_session, created.pattern_id, fitness_score=150.0)
        assert float(updated.fitness_score) == 100.0

    async def test_update_pattern_bounds_fitness_to_zero(self, db_session: AsyncSession):
        """Fitness below 0 should be clamped."""
        created = await create_pattern(
            session=db_session,
            name="Low Fitness",
            entry_conditions=VALID_ENTRY,
            origin="technical",
        )

        updated = await update_pattern(db_session, created.pattern_id, fitness_score=-10.0)
        assert float(updated.fitness_score) == 0.0

    async def test_soft_delete_archives_pattern(self, db_session: AsyncSession):
        """soft_delete_pattern should set status=archived and is_active=False."""
        created = await create_pattern(
            session=db_session,
            name="Delete Me",
            entry_conditions=VALID_ENTRY,
            origin="technical",
        )

        result = await soft_delete_pattern(db_session, created.pattern_id)
        assert result is True

        # Should not appear in normal get (excludes archived)
        normal_get = await get_pattern_by_id(db_session, created.pattern_id)
        assert normal_get is None

        # Should appear with include_archived=True
        archived = await get_pattern_by_id(db_session, created.pattern_id, include_archived=True)
        assert archived is not None
        assert archived.status == "archived"
        assert archived.is_active is False

    async def test_get_all_patterns_pagination(self, db_session: AsyncSession):
        """get_all_patterns should respect limit and offset."""
        for i in range(15):
            p = _make_pattern(fitness=float(i * 5))
            db_session.add(p)
        await db_session.flush()

        page1 = await get_all_patterns(db_session, limit=5, offset=0)
        page2 = await get_all_patterns(db_session, limit=5, offset=5)

        assert len(page1) == 5
        assert len(page2) == 5
        # No overlap
        ids1 = {p.pattern_id for p in page1}
        ids2 = {p.pattern_id for p in page2}
        assert ids1.isdisjoint(ids2)

    async def test_get_patterns_by_origin_filters(self, db_session: AsyncSession):
        """Patterns should be filterable by origin."""
        for origin in ["technical", "chaos", "academic"]:
            for _ in range(3):
                p = _make_pattern(origin=origin)
                db_session.add(p)
        await db_session.flush()

        techs = await get_patterns_by_origin(db_session, "technical")
        assert len(techs) == 3
        assert all(p.origin == "technical" for p in techs)

    async def test_batch_create_patterns(self, db_session: AsyncSession):
        """batch_create_patterns should create multiple patterns atomically."""
        batch = [
            {
                "name": f"Batch-{i}",
                "entry_conditions": VALID_ENTRY,
                "origin": "technical",
            }
            for i in range(5)
        ]

        ids = await batch_create_patterns(db_session, batch)
        assert len(ids) == 5

        for pid in ids:
            p = await get_pattern_by_id(db_session, pid)
            assert p is not None

    async def test_update_nonexistent_pattern_raises(self, db_session: AsyncSession):
        """Updating a non-existent pattern should raise ValueError."""
        with pytest.raises(ValueError, match="Pattern not found"):
            await update_pattern(db_session, "does-not-exist", fitness_score=99.0)


# ---------------------------------------------------------------------------
# Tier and Evolution Logic Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.requires_db
class TestPatternTiers:
    """Tests for quintile-based tier assignment and spawn eligibility."""

    async def test_quintile_tiers_distribute_correctly(self, db_session: AsyncSession):
        """10 patterns should produce 2 per tier (quintile distribution)."""
        patterns = []
        for i in range(10):
            p = _make_pattern(fitness=float(i * 10))
            db_session.add(p)
            patterns.append(p)
        await db_session.flush()

        pattern_dicts = [
            {"pattern_id": p.pattern_id, "fitness_score": float(p.fitness_score)}
            for p in patterns
        ]
        tiers = get_tiers_by_quintile(pattern_dicts)

        assert len(tiers) == 10
        tier_counts = {}
        for t in tiers.values():
            tier_counts[t] = tier_counts.get(t, 0) + 1

        # Each quintile should have 2 patterns
        assert tier_counts.get(1, 0) == 2
        assert tier_counts.get(5, 0) == 2

    async def test_spawn_eligibility_tier_based(self, db_session: AsyncSession):
        """Only tier 1 and 2 should be spawn-eligible (simple tier check)."""
        assert is_spawn_eligible(tier=1) is True
        assert is_spawn_eligible(tier=2) is True
        assert is_spawn_eligible(tier=3) is False
        assert is_spawn_eligible(tier=4) is False
        assert is_spawn_eligible(tier=5) is False

    async def test_should_promote_with_sufficient_trades(self, db_session: AsyncSession):
        """Promotion requires minimum trades and fitness threshold."""
        # should_promote takes a dict, returns target tier (int) or None
        # Tier 3 -> 2 requires fitness >= 60 and >= 20 trades
        assert should_promote({"fitness_score": 65.0, "tier": 3, "number_of_runs": 25}) == 2
        assert should_promote({"fitness_score": 55.0, "tier": 3, "number_of_runs": 25}) is None
        assert should_promote({"fitness_score": 65.0, "tier": 3, "number_of_runs": 10}) is None

    async def test_should_demote_below_threshold(self, db_session: AsyncSession):
        """Demotion triggers when fitness drops below tier threshold."""
        # should_demote takes a dict, returns target tier (int) or None
        assert should_demote({"fitness_score": 65.0, "tier": 1}) == 2  # < 70 -> demote to 2
        assert should_demote({"fitness_score": 75.0, "tier": 1}) is None  # >= 70
        assert should_demote({"fitness_score": 45.0, "tier": 2}) == 3  # < 50 -> demote to 3
        assert should_demote({"fitness_score": 55.0, "tier": 2}) is None  # >= 50

    async def test_fitness_update_changes_tier(self, db_session: AsyncSession):
        """Updating fitness should change the quintile tier assignment."""
        patterns = []
        for i in range(5):
            p = _make_pattern(fitness=float(50 + i * 10))  # 50, 60, 70, 80, 90
            db_session.add(p)
            patterns.append(p)
        await db_session.flush()

        # Initial tiers
        dicts = [
            {"pattern_id": p.pattern_id, "fitness_score": float(p.fitness_score)}
            for p in patterns
        ]
        initial_tiers = get_tiers_by_quintile(dicts)

        # Pattern with fitness=90 should be tier 1
        top_pattern = [p for p in patterns if float(p.fitness_score) == 90.0][0]
        assert initial_tiers[top_pattern.pattern_id] == 1

        # Now update it to lowest fitness
        await update_pattern(db_session, top_pattern.pattern_id, fitness_score=5.0)
        await db_session.refresh(top_pattern)

        dicts2 = [
            {"pattern_id": p.pattern_id, "fitness_score": float(p.fitness_score)}
            for p in patterns
        ]
        new_tiers = get_tiers_by_quintile(dicts2)
        assert new_tiers[top_pattern.pattern_id] == 5

    async def test_get_patterns_by_tier_1(self, db_session: AsyncSession):
        """get_patterns_by_tier(1) should return patterns with fitness >= 80."""
        for fitness in [85.0, 90.0, 70.0, 50.0, 30.0]:
            p = _make_pattern(fitness=fitness)
            db_session.add(p)
        await db_session.flush()

        tier1 = await get_patterns_by_tier(db_session, tier=1)
        assert len(tier1) == 2  # 85 and 90
        assert all(float(p.fitness_score) >= 80 for p in tier1)
