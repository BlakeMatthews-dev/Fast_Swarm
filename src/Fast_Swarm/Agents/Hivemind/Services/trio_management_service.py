"""
Trio Management Service for Coopetition System.

Implements:
- Trio formation (grouping coaches by ELO)
- Trio regrouping (when ELO gap exceeds threshold)
- Trio lifecycle management

Design:
- Coaches grouped into trios by similar ELO
- Trios regroup when max ELO spread exceeds 300
- Ensures competitive balance within trios
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from ..Models.coach_models import (
    TRIO_ELO_GAP_THRESHOLD,
    Coach,
    Trio,
)

# =============================================================================
# Trio Formation
# =============================================================================


async def get_unassigned_coaches(session: AsyncSession) -> list[Coach]:
    """
    Get coaches not currently in an active trio.

    Returns:
        List of coaches without trio assignment
    """
    # Get all coach IDs that are in active trios
    trio_result = await session.exec(
        select(Trio).where(Trio.status == "active")
    )
    active_trios = trio_result.all()

    assigned_ids = set()
    for trio in active_trios:
        assigned_ids.add(trio.coach_id_1)
        assigned_ids.add(trio.coach_id_2)
        assigned_ids.add(trio.coach_id_3)

    # Get active coaches not in those IDs
    if assigned_ids:
        coach_result = await session.exec(
            select(Coach)
            .where(Coach.status == "active")
            .where(Coach.coach_id.notin_(assigned_ids))
            .order_by(Coach.elo_rating.desc())
        )
    else:
        coach_result = await session.exec(
            select(Coach)
            .where(Coach.status == "active")
            .order_by(Coach.elo_rating.desc())
        )

    return list(coach_result.all())


async def form_trios(
    session: AsyncSession,
    coaches: list[Coach] | None = None,
) -> list[Trio]:
    """
    Form trios from unassigned coaches, grouping by similar ELO.

    Groups coaches into sets of 3, sorted by ELO so similar-rated
    coaches compete together.

    Args:
        session: Database session
        coaches: Optional list of coaches (fetches unassigned if not provided)

    Returns:
        List of newly created Trio objects
    """
    if coaches is None:
        coaches = await get_unassigned_coaches(session)

    if len(coaches) < 3:
        return []

    # Sort by ELO (descending)
    sorted_coaches = sorted(coaches, key=lambda c: float(c.elo_rating), reverse=True)

    created_trios = []

    # Group into trios of 3
    for i in range(0, len(sorted_coaches) - 2, 3):
        c1 = sorted_coaches[i]
        c2 = sorted_coaches[i + 1]
        c3 = sorted_coaches[i + 2]

        # Calculate ELO spread
        elos = [float(c1.elo_rating), float(c2.elo_rating), float(c3.elo_rating)]
        spread = max(elos) - min(elos)

        trio = Trio(
            trio_id=str(uuid.uuid4()),
            coach_id_1=c1.coach_id,
            coach_id_2=c2.coach_id,
            coach_id_3=c3.coach_id,
            elo_spread=Decimal(str(spread)),
            status="active",
            created_at=datetime.utcnow(),
        )

        session.add(trio)
        created_trios.append(trio)

    await session.commit()

    for trio in created_trios:
        await session.refresh(trio)

    return created_trios


# =============================================================================
# Trio Regrouping
# =============================================================================


async def get_trio_coaches(
    session: AsyncSession,
    trio: Trio,
) -> list[Coach]:
    """Get the 3 coaches in a trio."""
    result = await session.exec(
        select(Coach).where(
            Coach.coach_id.in_([trio.coach_id_1, trio.coach_id_2, trio.coach_id_3])
        )
    )
    return list(result.all())


async def calculate_trio_spread(
    session: AsyncSession,
    trio: Trio,
) -> float:
    """Calculate current ELO spread in a trio."""
    coaches = await get_trio_coaches(session, trio)
    elos = [float(c.elo_rating) for c in coaches]
    return max(elos) - min(elos) if elos else 0


async def check_trio_needs_regrouping(
    session: AsyncSession,
    trio: Trio,
) -> bool:
    """Check if a trio's ELO spread exceeds threshold."""
    spread = await calculate_trio_spread(session, trio)
    return spread > TRIO_ELO_GAP_THRESHOLD


async def find_trios_needing_regroup(
    session: AsyncSession,
) -> list[Trio]:
    """Find all trios that need regrouping due to ELO divergence."""
    result = await session.exec(
        select(Trio).where(Trio.status == "active")
    )
    active_trios = result.all()

    needs_regroup = []
    for trio in active_trios:
        if await check_trio_needs_regrouping(session, trio):
            needs_regroup.append(trio)

    return needs_regroup


async def disband_trio(
    session: AsyncSession,
    trio: Trio,
) -> None:
    """Mark a trio as disbanded (for regrouping)."""
    trio.status = "regrouping"
    trio.disbanded_at = datetime.utcnow()
    session.add(trio)
    await session.commit()


async def regroup_all_trios(
    session: AsyncSession,
) -> tuple[list[Trio], list[Trio]]:
    """
    Regroup all trios that have diverged too much.

    Process:
    1. Find trios with ELO spread > threshold
    2. Disband those trios
    3. Reform all unassigned coaches into new trios

    Returns:
        Tuple of (disbanded_trios, new_trios)
    """
    # Find and disband divergent trios
    divergent = await find_trios_needing_regroup(session)

    for trio in divergent:
        await disband_trio(session, trio)

    # Reform trios from all unassigned coaches
    new_trios = await form_trios(session)

    return divergent, new_trios


# =============================================================================
# Trio Queries
# =============================================================================


async def get_coach_trio(
    session: AsyncSession,
    coach_id: str,
) -> Trio | None:
    """Get the active trio a coach belongs to."""
    result = await session.exec(
        select(Trio)
        .where(Trio.status == "active")
        .where(
            (Trio.coach_id_1 == coach_id)
            | (Trio.coach_id_2 == coach_id)
            | (Trio.coach_id_3 == coach_id)
        )
    )
    return result.first()


async def get_all_active_trios(
    session: AsyncSession,
) -> list[Trio]:
    """Get all active trios."""
    result = await session.exec(
        select(Trio)
        .where(Trio.status == "active")
        .order_by(Trio.created_at.desc())
    )
    return list(result.all())


async def get_trio_stats(
    session: AsyncSession,
) -> dict[str, Any]:
    """Get statistics about current trio state."""
    # Count trios by status
    active_result = await session.exec(
        select(func.count(Trio.id)).where(Trio.status == "active")
    )
    active_count = active_result.one()

    regrouping_result = await session.exec(
        select(func.count(Trio.id)).where(Trio.status == "regrouping")
    )
    regrouping_count = regrouping_result.one()

    completed_result = await session.exec(
        select(func.count(Trio.id)).where(Trio.status == "completed")
    )
    completed_count = completed_result.one()

    # Get spread statistics for active trios
    active_trios = await get_all_active_trios(session)
    spreads = []
    for trio in active_trios:
        spread = await calculate_trio_spread(session, trio)
        spreads.append(spread)

    avg_spread = sum(spreads) / len(spreads) if spreads else 0
    max_spread = max(spreads) if spreads else 0
    min_spread = min(spreads) if spreads else 0

    # Count coaches in trios vs unassigned
    unassigned = await get_unassigned_coaches(session)

    return {
        "active_trios": active_count,
        "regrouping_trios": regrouping_count,
        "completed_trios": completed_count,
        "coaches_in_trios": active_count * 3,
        "unassigned_coaches": len(unassigned),
        "avg_elo_spread": avg_spread,
        "max_elo_spread": max_spread,
        "min_elo_spread": min_spread,
        "spread_threshold": TRIO_ELO_GAP_THRESHOLD,
        "trios_near_regroup": sum(1 for s in spreads if s > TRIO_ELO_GAP_THRESHOLD - 50),
    }


# =============================================================================
# Trio Lifecycle
# =============================================================================


async def complete_trio(
    session: AsyncSession,
    trio: Trio,
) -> None:
    """Mark a trio as completed (finished its backtest run)."""
    trio.status = "completed"
    session.add(trio)
    await session.commit()


async def handle_coach_death_in_trio(
    session: AsyncSession,
    coach_id: str,
) -> Trio | None:
    """
    Handle when a coach dies while in a trio.

    The trio must be disbanded since it cannot operate with 2 coaches.

    Args:
        session: Database session
        coach_id: ID of the coach that died

    Returns:
        The disbanded Trio, or None if coach was not in a trio
    """
    trio = await get_coach_trio(session, coach_id)

    if trio:
        await disband_trio(session, trio)

    return trio


async def ensure_all_coaches_in_trios(
    session: AsyncSession,
) -> list[Trio]:
    """
    Ensure all active coaches are assigned to trios.

    Called during system maintenance to form any missing trios.

    Returns:
        List of newly formed trios
    """
    return await form_trios(session)
