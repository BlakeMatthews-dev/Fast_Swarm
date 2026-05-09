"""
Real Integration Tests for Trio Management Service.

Tests trio formation, regrouping, disbanding, and lifecycle management
against a real PostgreSQL database using the db_session fixture with
transaction rollback for isolation.

All tests use real Coach and Trio objects persisted to DB.
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from Fast_Swarm.Agents.Hivemind.Models.coach_models import (
    Coach,
    CoachStatus,
    Trio,
    TRIO_ELO_GAP_THRESHOLD,
)
from Fast_Swarm.Agents.Hivemind.Services.trio_management_service import (
    calculate_trio_spread,
    check_trio_needs_regrouping,
    complete_trio,
    disband_trio,
    ensure_all_coaches_in_trios,
    find_trios_needing_regroup,
    form_trios,
    get_all_active_trios,
    get_coach_trio,
    get_trio_coaches,
    get_trio_stats,
    get_unassigned_coaches,
    handle_coach_death_in_trio,
    regroup_all_trios,
)


# =============================================================================
# Helper: Create a real Coach in the database
# =============================================================================


COACH_TRAITS = {
    "kelly_fraction": 0.5,
    "action_threshold": 0.6,
    "regime_sensitivity": 0.7,
    "specialist_preference": 0.4,
    "patience": 0.5,
    "roster_size_preference": 5.0,
}


async def create_coach(
    db_session: AsyncSession,
    coach_id: str | None = None,
    elo: float = 1500.0,
    status: str = "active",
    name: str | None = None,
) -> Coach:
    """Create a real Coach object in the database."""
    cid = coach_id or str(uuid.uuid4())
    coach = Coach(
        coach_id=cid,
        name=name or f"Coach {cid[:8]}",
        generation=0,
        elo_rating=Decimal(str(elo)),
        traits=COACH_TRAITS.copy(),
        status=status,
    )
    db_session.add(coach)
    await db_session.flush()
    return coach


# =============================================================================
# Test: Form trios from 9 coaches (expect 3 trios)
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.critical
@pytest.mark.requires_db
async def test_form_trios_9_coaches_yields_3_trios(db_session: AsyncSession):
    """9 active coaches should produce exactly 3 trios, grouped by ELO."""
    # Create 9 coaches with distinct ELO ratings
    elos = [1800, 1780, 1760, 1600, 1580, 1560, 1400, 1380, 1360]
    coaches = []
    for elo in elos:
        c = await create_coach(db_session, elo=elo)
        coaches.append(c)

    # Form trios
    trios = await form_trios(db_session)

    # Exactly 3 trios
    assert len(trios) == 3, f"Expected 3 trios, got {len(trios)}"

    # All trios should be active
    for trio in trios:
        assert trio.status == "active"
        assert trio.trio_id is not None

    # Verify coaches are grouped by ELO proximity (sorted descending)
    # Trio 1 should have the top 3 ELO coaches, etc.
    sorted_coaches = sorted(coaches, key=lambda c: float(c.elo_rating), reverse=True)

    trio_1_ids = {trios[0].coach_id_1, trios[0].coach_id_2, trios[0].coach_id_3}
    expected_top_3_ids = {sorted_coaches[0].coach_id, sorted_coaches[1].coach_id, sorted_coaches[2].coach_id}
    assert trio_1_ids == expected_top_3_ids, "Top trio should contain top 3 ELO coaches"

    trio_2_ids = {trios[1].coach_id_1, trios[1].coach_id_2, trios[1].coach_id_3}
    expected_mid_3_ids = {sorted_coaches[3].coach_id, sorted_coaches[4].coach_id, sorted_coaches[5].coach_id}
    assert trio_2_ids == expected_mid_3_ids, "Middle trio should contain mid 3 ELO coaches"

    trio_3_ids = {trios[2].coach_id_1, trios[2].coach_id_2, trios[2].coach_id_3}
    expected_bot_3_ids = {sorted_coaches[6].coach_id, sorted_coaches[7].coach_id, sorted_coaches[8].coach_id}
    assert trio_3_ids == expected_bot_3_ids, "Bottom trio should contain bottom 3 ELO coaches"

    # Each trio should have reasonable ELO spread (within group)
    for trio in trios:
        spread = float(trio.elo_spread)
        assert spread <= 50, f"Spread within group should be small, got {spread}"

    # No unassigned coaches left
    unassigned = await get_unassigned_coaches(db_session)
    assert len(unassigned) == 0, f"Expected 0 unassigned, got {len(unassigned)}"


# =============================================================================
# Test: Form trios with <3 coaches (no trios formed)
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.critical
@pytest.mark.requires_db
async def test_form_trios_fewer_than_3_coaches_returns_empty(db_session: AsyncSession):
    """Fewer than 3 coaches should produce zero trios."""
    # Create only 2 coaches
    await create_coach(db_session, elo=1500)
    await create_coach(db_session, elo=1600)

    trios = await form_trios(db_session)
    assert len(trios) == 0, f"Expected 0 trios with 2 coaches, got {len(trios)}"

    # Both should remain unassigned
    unassigned = await get_unassigned_coaches(db_session)
    assert len(unassigned) == 2


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_form_trios_zero_coaches_returns_empty(db_session: AsyncSession):
    """Zero coaches should produce zero trios."""
    trios = await form_trios(db_session)
    assert len(trios) == 0


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_form_trios_one_coach_returns_empty(db_session: AsyncSession):
    """One coach should produce zero trios."""
    await create_coach(db_session, elo=1500)
    trios = await form_trios(db_session)
    assert len(trios) == 0


# =============================================================================
# Test: Form trios with remainder (7 coaches -> 2 trios, 1 leftover)
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.critical
@pytest.mark.requires_db
async def test_form_trios_with_remainder(db_session: AsyncSession):
    """7 coaches should form 2 trios with 1 leftover coach."""
    elos = [1700, 1680, 1660, 1500, 1480, 1460, 1300]
    for elo in elos:
        await create_coach(db_session, elo=elo)

    trios = await form_trios(db_session)

    assert len(trios) == 2, f"Expected 2 trios from 7 coaches, got {len(trios)}"

    # 1 coach should remain unassigned
    unassigned = await get_unassigned_coaches(db_session)
    assert len(unassigned) == 1, f"Expected 1 leftover, got {len(unassigned)}"

    # The leftover should be the lowest ELO coach (last one not grouped)
    assert float(unassigned[0].elo_rating) == 1300.0


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_form_trios_6_coaches_yields_2_trios_no_remainder(db_session: AsyncSession):
    """6 coaches should form exactly 2 trios with 0 remainder."""
    for elo in [1700, 1680, 1660, 1500, 1480, 1460]:
        await create_coach(db_session, elo=elo)

    trios = await form_trios(db_session)
    assert len(trios) == 2

    unassigned = await get_unassigned_coaches(db_session)
    assert len(unassigned) == 0


# =============================================================================
# Test: Detect regrouping need when ELO spread > 300
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.critical
@pytest.mark.requires_db
async def test_detect_regrouping_need_when_elo_spread_exceeds_threshold(db_session: AsyncSession):
    """A trio with ELO spread > 300 should be flagged for regrouping."""
    # Create 3 coaches with a wide spread (> 300)
    c1 = await create_coach(db_session, elo=1800)
    c2 = await create_coach(db_session, elo=1600)
    c3 = await create_coach(db_session, elo=1400)  # spread = 400

    # Form trio from these specific coaches
    trios = await form_trios(db_session, coaches=[c1, c2, c3])
    assert len(trios) == 1
    trio = trios[0]

    # Spread should be 400 (1800 - 1400)
    spread = await calculate_trio_spread(db_session, trio)
    assert spread == 400.0, f"Expected spread 400, got {spread}"
    assert spread > TRIO_ELO_GAP_THRESHOLD

    # Should need regrouping
    needs_regroup = await check_trio_needs_regrouping(db_session, trio)
    assert needs_regroup is True

    # Should appear in the "needs regroup" list
    needing = await find_trios_needing_regroup(db_session)
    assert len(needing) >= 1
    assert any(t.trio_id == trio.trio_id for t in needing)


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_no_regrouping_when_elo_spread_within_threshold(db_session: AsyncSession):
    """A trio with ELO spread <= 300 should NOT be flagged for regrouping."""
    c1 = await create_coach(db_session, elo=1600)
    c2 = await create_coach(db_session, elo=1500)
    c3 = await create_coach(db_session, elo=1400)  # spread = 200

    trios = await form_trios(db_session, coaches=[c1, c2, c3])
    trio = trios[0]

    spread = await calculate_trio_spread(db_session, trio)
    assert spread == 200.0
    assert spread <= TRIO_ELO_GAP_THRESHOLD

    needs_regroup = await check_trio_needs_regrouping(db_session, trio)
    assert needs_regroup is False


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_regrouping_at_exact_threshold_boundary(db_session: AsyncSession):
    """A trio with ELO spread == 300 exactly should NOT need regrouping (> not >=)."""
    c1 = await create_coach(db_session, elo=1650)
    c2 = await create_coach(db_session, elo=1500)
    c3 = await create_coach(db_session, elo=1350)  # spread = 300

    trios = await form_trios(db_session, coaches=[c1, c2, c3])
    trio = trios[0]

    spread = await calculate_trio_spread(db_session, trio)
    assert spread == 300.0

    needs_regroup = await check_trio_needs_regrouping(db_session, trio)
    assert needs_regroup is False, "Spread == 300 should NOT trigger regrouping (threshold is >300)"


# =============================================================================
# Test: Disband trio
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.critical
@pytest.mark.requires_db
async def test_disband_trio(db_session: AsyncSession):
    """Disbanding a trio should set status to 'regrouping' and record timestamp."""
    c1 = await create_coach(db_session, elo=1600)
    c2 = await create_coach(db_session, elo=1550)
    c3 = await create_coach(db_session, elo=1500)

    trios = await form_trios(db_session, coaches=[c1, c2, c3])
    trio = trios[0]

    assert trio.status == "active"
    assert trio.disbanded_at is None

    await disband_trio(db_session, trio)

    assert trio.status == "regrouping"
    assert trio.disbanded_at is not None

    # Coaches should now be unassigned (no active trio)
    unassigned = await get_unassigned_coaches(db_session)
    coach_ids = {c.coach_id for c in unassigned}
    assert c1.coach_id in coach_ids
    assert c2.coach_id in coach_ids
    assert c3.coach_id in coach_ids


# =============================================================================
# Test: Handle coach death in trio
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.critical
@pytest.mark.requires_db
async def test_handle_coach_death_in_trio(db_session: AsyncSession):
    """When a coach dies, its trio should be disbanded."""
    c1 = await create_coach(db_session, elo=1600)
    c2 = await create_coach(db_session, elo=1550)
    c3 = await create_coach(db_session, elo=1500)

    trios = await form_trios(db_session, coaches=[c1, c2, c3])
    trio = trios[0]
    assert trio.status == "active"

    # Coach c2 dies
    disbanded = await handle_coach_death_in_trio(db_session, c2.coach_id)

    assert disbanded is not None
    assert disbanded.trio_id == trio.trio_id
    assert disbanded.status == "regrouping"
    assert disbanded.disbanded_at is not None


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_handle_coach_death_not_in_trio(db_session: AsyncSession):
    """Handling death for a coach not in any trio should return None."""
    c1 = await create_coach(db_session, elo=1500)

    disbanded = await handle_coach_death_in_trio(db_session, c1.coach_id)
    assert disbanded is None


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_handle_coach_death_nonexistent_coach(db_session: AsyncSession):
    """Handling death for a nonexistent coach ID should return None."""
    disbanded = await handle_coach_death_in_trio(db_session, "nonexistent-id")
    assert disbanded is None


# =============================================================================
# Test: Get trio stats
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.critical
@pytest.mark.requires_db
async def test_get_trio_stats(db_session: AsyncSession):
    """Trio stats should reflect correct counts and spread statistics."""
    # Create 9 coaches -> 3 trios
    for elo in [1700, 1690, 1680, 1500, 1490, 1480, 1300, 1290, 1280]:
        await create_coach(db_session, elo=elo)

    trios = await form_trios(db_session)
    assert len(trios) == 3

    stats = await get_trio_stats(db_session)

    assert stats["active_trios"] == 3
    assert stats["regrouping_trios"] == 0
    assert stats["completed_trios"] == 0
    assert stats["coaches_in_trios"] == 9
    assert stats["unassigned_coaches"] == 0
    assert stats["spread_threshold"] == TRIO_ELO_GAP_THRESHOLD

    # All spreads should be 20 (within each group)
    assert stats["avg_elo_spread"] == 20.0
    assert stats["max_elo_spread"] == 20.0
    assert stats["min_elo_spread"] == 20.0


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_get_trio_stats_empty(db_session: AsyncSession):
    """Trio stats with no trios should return zeroed values."""
    stats = await get_trio_stats(db_session)

    assert stats["active_trios"] == 0
    assert stats["coaches_in_trios"] == 0
    assert stats["avg_elo_spread"] == 0
    assert stats["max_elo_spread"] == 0
    assert stats["min_elo_spread"] == 0


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_get_trio_stats_after_disband(db_session: AsyncSession):
    """Stats should update after disbanding a trio."""
    for elo in [1600, 1590, 1580]:
        await create_coach(db_session, elo=elo)

    trios = await form_trios(db_session)
    assert len(trios) == 1

    # Disband the trio
    await disband_trio(db_session, trios[0])

    stats = await get_trio_stats(db_session)
    assert stats["active_trios"] == 0
    assert stats["regrouping_trios"] == 1
    assert stats["unassigned_coaches"] == 3


# =============================================================================
# Test: Ensure all coaches in trios
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.critical
@pytest.mark.requires_db
async def test_ensure_all_coaches_in_trios(db_session: AsyncSession):
    """ensure_all_coaches_in_trios should form trios for all unassigned coaches."""
    # Create 6 coaches
    for elo in [1700, 1680, 1660, 1500, 1480, 1460]:
        await create_coach(db_session, elo=elo)

    # Initially no trios
    active = await get_all_active_trios(db_session)
    assert len(active) == 0

    # Ensure all in trios
    new_trios = await ensure_all_coaches_in_trios(db_session)
    assert len(new_trios) == 2

    # All 6 coaches should be assigned
    unassigned = await get_unassigned_coaches(db_session)
    assert len(unassigned) == 0


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_ensure_all_coaches_in_trios_does_not_duplicate(db_session: AsyncSession):
    """Calling ensure twice should not create duplicate trios."""
    for elo in [1600, 1580, 1560]:
        await create_coach(db_session, elo=elo)

    first_run = await ensure_all_coaches_in_trios(db_session)
    assert len(first_run) == 1

    # Second call should find no unassigned coaches, form no new trios
    second_run = await ensure_all_coaches_in_trios(db_session)
    assert len(second_run) == 0

    active = await get_all_active_trios(db_session)
    assert len(active) == 1


# =============================================================================
# Test: Regroup all trios end-to-end
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.critical
@pytest.mark.requires_db
async def test_regroup_all_trios_end_to_end(db_session: AsyncSession):
    """Full regrouping: divergent trios get disbanded and new ones formed."""
    # Create a trio that WILL need regrouping (spread > 300)
    c1 = await create_coach(db_session, elo=1900)
    c2 = await create_coach(db_session, elo=1600)
    c3 = await create_coach(db_session, elo=1300)  # spread = 600

    trios = await form_trios(db_session, coaches=[c1, c2, c3])
    assert len(trios) == 1
    old_trio = trios[0]

    # Regroup
    disbanded, new_trios = await regroup_all_trios(db_session)

    assert len(disbanded) == 1
    assert disbanded[0].trio_id == old_trio.trio_id
    assert disbanded[0].status == "regrouping"

    # New trio should have been formed from the now-unassigned coaches
    assert len(new_trios) == 1
    assert new_trios[0].status == "active"
    assert new_trios[0].trio_id != old_trio.trio_id


# =============================================================================
# Test: Coach lookup and trio membership
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_get_coach_trio(db_session: AsyncSession):
    """get_coach_trio should return the active trio for a coach."""
    c1 = await create_coach(db_session, elo=1600)
    c2 = await create_coach(db_session, elo=1550)
    c3 = await create_coach(db_session, elo=1500)

    trios = await form_trios(db_session, coaches=[c1, c2, c3])
    trio = trios[0]

    # Each coach should find this trio
    for coach in [c1, c2, c3]:
        found = await get_coach_trio(db_session, coach.coach_id)
        assert found is not None
        assert found.trio_id == trio.trio_id


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_get_coach_trio_returns_none_for_unassigned(db_session: AsyncSession):
    """get_coach_trio should return None for an unassigned coach."""
    c1 = await create_coach(db_session, elo=1500)
    found = await get_coach_trio(db_session, c1.coach_id)
    assert found is None


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_get_trio_coaches_returns_all_three(db_session: AsyncSession):
    """get_trio_coaches should return exactly 3 Coach objects."""
    c1 = await create_coach(db_session, elo=1600)
    c2 = await create_coach(db_session, elo=1550)
    c3 = await create_coach(db_session, elo=1500)

    trios = await form_trios(db_session, coaches=[c1, c2, c3])
    trio = trios[0]

    coaches = await get_trio_coaches(db_session, trio)
    assert len(coaches) == 3
    coach_ids = {c.coach_id for c in coaches}
    assert coach_ids == {c1.coach_id, c2.coach_id, c3.coach_id}


# =============================================================================
# Test: Complete trio lifecycle
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_complete_trio(db_session: AsyncSession):
    """Completing a trio should set status to 'completed'."""
    c1 = await create_coach(db_session, elo=1600)
    c2 = await create_coach(db_session, elo=1550)
    c3 = await create_coach(db_session, elo=1500)

    trios = await form_trios(db_session, coaches=[c1, c2, c3])
    trio = trios[0]
    assert trio.status == "active"

    await complete_trio(db_session, trio)
    assert trio.status == "completed"

    # Completed trios should not appear in active list
    active = await get_all_active_trios(db_session)
    assert len(active) == 0


# =============================================================================
# Test: Dead coaches are excluded from trio formation
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_dead_coaches_excluded_from_formation(db_session: AsyncSession):
    """Dead coaches should not be included in trio formation."""
    await create_coach(db_session, elo=1600, status="active")
    await create_coach(db_session, elo=1550, status="active")
    await create_coach(db_session, elo=1500, status="dead")  # Dead coach

    trios = await form_trios(db_session)
    assert len(trios) == 0, "Should not form a trio when only 2 active coaches exist"

    unassigned = await get_unassigned_coaches(db_session)
    assert len(unassigned) == 2, "Only active coaches should be unassigned"
