"""
ELO Transfer Service for Coopetition System.

Implements:
- Sqrt-scaled P&L → ELO transfers (diminishing returns on big wins)
- Flat backtest tax (5 ELO per backtest, split across trio)
- Entry/Exit 2x weight multiplier
- HOLD miss threshold (1% - only wrong if missed > 1% move)
- Confidence scaling (affects both gains AND losses)

Design Philosophy:
- Winners steal from losers (coopetition)
- Sqrt scaling prevents outlier trades from dominating
- Flat tax creates deflationary pressure (point sink)
- Confidence affects accountability in both directions
"""

import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..Models.coach_models import (
    BACKTEST_ELO_TAX,
    ELO_K_BASE,
    HOLD_MISS_THRESHOLD,
    AgentInstance,
    Coach,
    ELOTransfer,
    HivemindVote,
    TradeLegType,
)

# =============================================================================
# Data Classes for Transfer Calculations
# =============================================================================


@dataclass
class VoteOutcome:
    """Result of evaluating a single vote against actual price movement."""

    coach_id: str
    vote_direction: int  # -2 to +2
    confidence: float
    was_correct: bool
    elo_change: float  # Positive = gained, negative = lost
    reason: str  # "correct_trade", "wrong_trade", "correct_hold", "missed_opportunity"


@dataclass
class TransferResult:
    """Result of calculating all ELO transfers for a trade leg."""

    leg_id: str
    outcomes: list[VoteOutcome]
    total_tax: float  # Flat tax applied
    net_elo_moved: float  # Total ELO that changed hands


# =============================================================================
# Core ELO Transfer Logic
# =============================================================================


def sqrt_scale_pnl(pnl_pct: float) -> float:
    """
    Apply sqrt scaling to P&L for diminishing returns.

    Examples:
        1% → 1.0
        4% → 2.0
        9% → 3.0
        16% → 4.0

    This prevents outlier trades (10%+ wins) from dominating ELO changes.
    """
    if pnl_pct == 0:
        return 0.0
    sign = 1 if pnl_pct > 0 else -1
    return sign * math.sqrt(abs(pnl_pct))


def calculate_elo_change(
    pnl_pct: float,
    confidence: float,
    elo_weight: float = 1.0,
    was_correct: bool = True,
) -> float:
    """
    Calculate ELO change for a vote.

    Formula: K_BASE * sqrt(|P&L%|) * confidence * elo_weight * direction

    Args:
        pnl_pct: The P&L percentage of the trade
        confidence: Vote confidence (0.0 to 1.0)
        elo_weight: Multiplier (2.0 for entry/exit, 1.0 for mid-trade)
        was_correct: Whether the vote was correct

    Returns:
        ELO change (positive if correct, negative if wrong)
    """
    # Sqrt scale the P&L
    scaled_pnl = sqrt_scale_pnl(abs(pnl_pct))

    # Base ELO change
    base_change = ELO_K_BASE * scaled_pnl * confidence * elo_weight

    # Direction based on correctness
    return base_change if was_correct else -base_change


def evaluate_trade_vote(
    vote_direction: int,
    confidence: float,
    pnl_pct: float,
) -> tuple[bool, str]:
    """
    Evaluate if a trade vote (non-HOLD) was correct.

    Trade votes are correct if:
    - BUY/STRONG_BUY (+1/+2) and trade was profitable
    - SELL/STRONG_SELL (-1/-2) and trade was profitable (short)

    Any loss counts as wrong for trade votes.

    Returns:
        Tuple of (was_correct, reason)
    """
    if vote_direction == 0:
        raise ValueError("Use evaluate_hold_vote for HOLD votes")

    # Trade direction matches sign of vote
    # Positive vote = long position, negative vote = short position
    # P&L is already direction-adjusted (positive = profitable)

    if pnl_pct > 0:
        return True, "correct_trade"
    else:
        return False, "wrong_trade"


def evaluate_hold_vote(
    confidence: float,
    price_change_pct: float,
) -> tuple[bool, str]:
    """
    Evaluate if a HOLD vote was correct.

    HOLD is only wrong if missed > HOLD_MISS_THRESHOLD (1%) profit opportunity.

    Args:
        confidence: Vote confidence
        price_change_pct: Absolute price change during the period

    Returns:
        Tuple of (was_correct, reason)
    """
    missed_opportunity = abs(price_change_pct) > (HOLD_MISS_THRESHOLD * 100)

    if missed_opportunity:
        return False, "missed_opportunity"
    else:
        return True, "correct_hold"


# =============================================================================
# Trio-Level Transfer Calculations
# =============================================================================


def calculate_trio_transfers(
    votes: list[HivemindVote],
    pnl_pct: float,
    price_change_pct: float,
    leg_type: str,
) -> TransferResult:
    """
    Calculate ELO transfers for all votes on a trade leg.

    This is the main entry point for scoring a completed trade leg.

    Args:
        votes: List of HivemindVote records for this leg
        pnl_pct: Actual P&L of the trade leg
        price_change_pct: Raw price change (for HOLD evaluation)
        leg_type: Type of leg (entry, add, trim, exit, flip)

    Returns:
        TransferResult with all outcomes and transfers
    """
    # Determine ELO weight based on leg type
    if leg_type in (TradeLegType.ENTRY.value, TradeLegType.EXIT.value, TradeLegType.FLIP.value):
        elo_weight = 2.0
    else:
        elo_weight = 1.0

    outcomes: list[VoteOutcome] = []

    for vote in votes:
        direction = vote.vote_direction
        confidence = float(vote.confidence)

        if direction == 0:
            # HOLD vote - different evaluation
            was_correct, reason = evaluate_hold_vote(confidence, price_change_pct)
            # HOLD votes use price change magnitude, not trade P&L
            elo_change = calculate_elo_change(
                pnl_pct=price_change_pct if not was_correct else 0,  # Only penalize if wrong
                confidence=confidence,
                elo_weight=elo_weight,
                was_correct=was_correct,
            )
        else:
            # Trade vote
            was_correct, reason = evaluate_trade_vote(direction, confidence, pnl_pct)
            elo_change = calculate_elo_change(
                pnl_pct=pnl_pct,
                confidence=confidence,
                elo_weight=elo_weight,
                was_correct=was_correct,
            )

        outcomes.append(
            VoteOutcome(
                coach_id=vote.coach_id,
                vote_direction=direction,
                confidence=confidence,
                was_correct=was_correct,
                elo_change=elo_change,
                reason=reason,
            )
        )

    # Calculate flat tax (split across trio)
    tax_per_coach = BACKTEST_ELO_TAX / 3.0

    # Apply tax to all participants
    for outcome in outcomes:
        outcome.elo_change -= tax_per_coach

    # Calculate net ELO moved (should be negative due to tax = deflationary)
    net_elo = sum(o.elo_change for o in outcomes)

    return TransferResult(
        leg_id=votes[0].leg_id if votes else "",
        outcomes=outcomes,
        total_tax=BACKTEST_ELO_TAX,
        net_elo_moved=net_elo,
    )


# =============================================================================
# Database Operations
# =============================================================================


async def apply_elo_transfers(
    session: AsyncSession,
    transfer_result: TransferResult,
    trio_id: str,
) -> list[ELOTransfer]:
    """
    Apply calculated ELO transfers to coaches and create audit records.

    Args:
        session: Database session
        transfer_result: Calculated transfers from calculate_trio_transfers
        trio_id: ID of the trio for record keeping

    Returns:
        List of created ELOTransfer records
    """
    transfers: list[ELOTransfer] = []

    for outcome in transfer_result.outcomes:
        # Get coach
        result = await session.exec(
            select(Coach).where(Coach.coach_id == outcome.coach_id)
        )
        coach = result.first()

        if not coach:
            continue

        # Update coach ELO
        old_elo = float(coach.elo_rating)
        new_elo = max(0, old_elo + outcome.elo_change)  # Floor at 0
        coach.elo_rating = Decimal(str(new_elo))
        coach.updated_at = datetime.utcnow()

        session.add(coach)

        # Determine transfer parties
        if outcome.elo_change > 0:
            # Coach gained - from losers (abstracted as "trio_pool")
            from_entity = "trio_pool"
            to_entity = outcome.coach_id
        else:
            # Coach lost - to winners (abstracted as "trio_pool")
            from_entity = outcome.coach_id
            to_entity = "trio_pool"

        # Create transfer record
        transfer = ELOTransfer(
            transfer_type="trade",
            from_entity_type="coach" if outcome.elo_change < 0 else "system",
            from_entity_id=from_entity if outcome.elo_change < 0 else None,
            to_entity_type="coach" if outcome.elo_change > 0 else "system",
            to_entity_id=to_entity if outcome.elo_change > 0 else None,
            amount=Decimal(str(abs(outcome.elo_change))),
            leg_id=transfer_result.leg_id,
            trio_id=trio_id,
            reason=outcome.reason,
        )

        session.add(transfer)
        transfers.append(transfer)

    # Create tax transfer record (ELO leaving the system)
    tax_transfer = ELOTransfer(
        transfer_type="tax",
        from_entity_type="system",
        from_entity_id="trio_pool",
        to_entity_type="system",
        to_entity_id="void",  # ELO sink
        amount=Decimal(str(transfer_result.total_tax)),
        trio_id=trio_id,
        reason="backtest_flat_tax",
    )
    session.add(tax_transfer)
    transfers.append(tax_transfer)

    await session.commit()

    return transfers


async def apply_agent_elo_transfers(
    session: AsyncSession,
    agent_votes: dict[str, VoteOutcome],
    leg_id: str,
) -> list[ELOTransfer]:
    """
    Apply ELO transfers to agent instances within a hivemind.

    Similar to coach transfers but for individual agents.

    Args:
        session: Database session
        agent_votes: Dict of instance_id -> VoteOutcome
        leg_id: ID of the trade leg

    Returns:
        List of created ELOTransfer records
    """
    transfers: list[ELOTransfer] = []

    for instance_id, outcome in agent_votes.items():
        # Get agent instance
        result = await session.exec(
            select(AgentInstance).where(AgentInstance.instance_id == instance_id)
        )
        agent = result.first()

        if not agent:
            continue

        # Update agent ELO
        old_elo = float(agent.elo_rating)
        new_elo = max(0, old_elo + outcome.elo_change)
        agent.elo_rating = Decimal(str(new_elo))

        # Update stats
        agent.total_votes += 1
        if outcome.was_correct:
            agent.correct_votes += 1

        session.add(agent)

        # Create transfer record
        transfer = ELOTransfer(
            transfer_type="trade",
            from_entity_type="agent_instance" if outcome.elo_change < 0 else "system",
            from_entity_id=instance_id if outcome.elo_change < 0 else None,
            to_entity_type="agent_instance" if outcome.elo_change > 0 else "system",
            to_entity_id=instance_id if outcome.elo_change > 0 else None,
            amount=Decimal(str(abs(outcome.elo_change))),
            leg_id=leg_id,
            reason=outcome.reason,
        )

        session.add(transfer)
        transfers.append(transfer)

    await session.commit()

    return transfers


# =============================================================================
# Lifecycle ELO Events
# =============================================================================


async def apply_spawn_elo(
    session: AsyncSession,
    coach_id: str,
    starting_elo: float = 1500.0,
) -> ELOTransfer:
    """
    Create ELO transfer record for new coach spawn.

    New coaches enter with 1500 ELO (point source into the system).
    """
    transfer = ELOTransfer(
        transfer_type="spawn",
        from_entity_type="system",
        from_entity_id="genesis",
        to_entity_type="coach",
        to_entity_id=coach_id,
        amount=Decimal(str(starting_elo)),
        reason="new_coach_spawn",
    )

    session.add(transfer)
    await session.commit()

    return transfer


async def apply_death_elo(
    session: AsyncSession,
    coach: Coach,
) -> ELOTransfer:
    """
    Create ELO transfer record for coach death.

    When a coach dies, their remaining ELO leaves the system (point sink).
    """
    remaining_elo = float(coach.elo_rating)

    transfer = ELOTransfer(
        transfer_type="death_penalty",
        from_entity_type="coach",
        from_entity_id=coach.coach_id,
        to_entity_type="system",
        to_entity_id="void",
        amount=Decimal(str(remaining_elo)),
        reason=f"coach_death_at_{remaining_elo:.0f}_elo",
    )

    session.add(transfer)
    await session.commit()

    return transfer


async def apply_clone_bonus(
    session: AsyncSession,
    parent_coach_id: str,
    child_coach_id: str,
    clone_elo: float = 1500.0,
) -> ELOTransfer:
    """
    Create ELO transfer record for coach clone.

    Clones enter at 1500 ELO (point source), parent keeps their ELO.
    """
    transfer = ELOTransfer(
        transfer_type="clone_bonus",
        from_entity_type="system",
        from_entity_id="genesis",
        to_entity_type="coach",
        to_entity_id=child_coach_id,
        amount=Decimal(str(clone_elo)),
        reason=f"clone_from_{parent_coach_id}",
    )

    session.add(transfer)
    await session.commit()

    return transfer


# =============================================================================
# Query Helpers
# =============================================================================


async def get_coach_elo_history(
    session: AsyncSession,
    coach_id: str,
    limit: int = 100,
) -> list[ELOTransfer]:
    """Get recent ELO transfer history for a coach."""
    result = await session.exec(
        select(ELOTransfer)
        .where(
            (ELOTransfer.from_entity_id == coach_id)
            | (ELOTransfer.to_entity_id == coach_id)
        )
        .order_by(ELOTransfer.created_at.desc())
        .limit(limit)
    )
    return list(result.all())


async def get_system_elo_balance(session: AsyncSession) -> dict:
    """
    Calculate total ELO in the system.

    Returns dict with:
    - total_coach_elo: Sum of all coach ELO
    - total_spawned: Total ELO from spawns
    - total_taxed: Total ELO removed via tax
    - total_deaths: Total ELO removed via deaths
    - net_balance: Should trend toward equilibrium
    """
    # Get all active coaches
    coaches_result = await session.exec(
        select(Coach).where(Coach.status == "active")
    )
    coaches = coaches_result.all()
    total_coach_elo = sum(float(c.elo_rating) for c in coaches)

    # Get spawn totals
    spawn_result = await session.exec(
        select(ELOTransfer).where(ELOTransfer.transfer_type == "spawn")
    )
    spawns = spawn_result.all()
    total_spawned = sum(float(s.amount) for s in spawns)

    # Get tax totals
    tax_result = await session.exec(
        select(ELOTransfer).where(ELOTransfer.transfer_type == "tax")
    )
    taxes = tax_result.all()
    total_taxed = sum(float(t.amount) for t in taxes)

    # Get death totals
    death_result = await session.exec(
        select(ELOTransfer).where(ELOTransfer.transfer_type == "death_penalty")
    )
    deaths = death_result.all()
    total_deaths = sum(float(d.amount) for d in deaths)

    return {
        "total_coach_elo": total_coach_elo,
        "total_spawned": total_spawned,
        "total_taxed": total_taxed,
        "total_deaths": total_deaths,
        "net_balance": total_spawned - total_taxed - total_deaths,
        "active_coaches": len(coaches),
    }


# =============================================================================
# Backtest Integration Functions
# =============================================================================


async def apply_backtest_tax(
    session: AsyncSession,
    trio_id: str,
    tax_amount: float = BACKTEST_ELO_TAX,
) -> ELOTransfer:
    """
    Apply flat backtest tax to a trio (ELO sink).

    Every backtest costs a flat tax that leaves the system permanently.
    This creates deflationary pressure - coaches must consistently perform
    well just to maintain their ELO, preventing passive accumulation.

    The tax is split equally across all coaches in the trio (tax_amount / 3 each).

    Args:
        session: Database session
        trio_id: ID of the trio being taxed
        tax_amount: Amount of ELO to remove (default: BACKTEST_ELO_TAX = 5)

    Returns:
        ELOTransfer record for audit trail
    """
    from .trio_management_service import get_trio_coaches

    # Get all coaches in this trio
    trio_coaches = await get_trio_coaches(session, trio_id)

    if not trio_coaches:
        # No coaches to tax - create record but no actual transfers
        transfer = ELOTransfer(
            transfer_type="tax",
            from_entity_type="system",
            from_entity_id=trio_id,
            to_entity_type="system",
            to_entity_id="void",
            amount=Decimal("0"),
            trio_id=trio_id,
            reason="backtest_tax_no_coaches",
        )
        session.add(transfer)
        await session.commit()
        return transfer

    # Split tax equally across coaches
    tax_per_coach = tax_amount / len(trio_coaches)

    # Deduct from each coach's ELO
    for coach in trio_coaches:
        old_elo = float(coach.elo_rating)
        new_elo = max(0, old_elo - tax_per_coach)  # Floor at 0
        coach.elo_rating = Decimal(str(new_elo))
        coach.updated_at = datetime.utcnow()
        session.add(coach)

    # Create aggregate tax transfer record (ELO leaving the system)
    transfer = ELOTransfer(
        transfer_type="tax",
        from_entity_type="trio",
        from_entity_id=trio_id,
        to_entity_type="system",
        to_entity_id="void",  # ELO permanently removed
        amount=Decimal(str(tax_amount)),
        trio_id=trio_id,
        reason=f"backtest_flat_tax_{tax_per_coach:.2f}_per_coach",
    )

    session.add(transfer)
    await session.commit()

    return transfer


async def process_trade_leg_results(
    session: AsyncSession,
    leg_id: str,
    pnl_pct: float,
    price_change_pct: float,
) -> TransferResult:
    """
    Process trade leg results and apply ELO transfers.

    This is the main orchestration function that gets called when a trade leg
    closes. It handles the full pipeline:

    1. Fetches the TradeLeg to get leg_type and trio_id
    2. Fetches all HivemindVotes for this leg
    3. Calculates ELO transfers using calculate_trio_transfers()
    4. Applies transfers to coach ELO ratings
    5. Updates vote records with outcomes
    6. Creates audit trail records

    Args:
        session: Database session
        leg_id: ID of the completed trade leg
        pnl_pct: P&L percentage of the leg (positive = profitable)
        price_change_pct: Raw price change during leg (for HOLD evaluation)

    Returns:
        TransferResult with all outcomes and transfers applied
    """
    from ..Models.coach_models import TradeLeg

    # 1. Fetch the trade leg
    leg_result = await session.exec(
        select(TradeLeg).where(TradeLeg.leg_id == leg_id)
    )
    leg = leg_result.first()

    if not leg:
        raise ValueError(f"Trade leg not found: {leg_id}")

    # 2. Fetch all votes for this leg
    votes_result = await session.exec(
        select(HivemindVote).where(HivemindVote.leg_id == leg_id)
    )
    votes = list(votes_result.all())

    if not votes:
        # No votes cast for this leg - return empty result
        return TransferResult(
            leg_id=leg_id,
            outcomes=[],
            total_tax=0.0,
            net_elo_moved=0.0,
        )

    # 3. Calculate all transfers
    transfer_result = calculate_trio_transfers(
        votes=votes,
        pnl_pct=pnl_pct,
        price_change_pct=price_change_pct,
        leg_type=leg.leg_type,
    )

    # 4. Apply ELO transfers to coaches
    await apply_elo_transfers(session, transfer_result, leg.trio_id)

    # 5. Update vote records with outcomes
    for outcome in transfer_result.outcomes:
        # Find the vote record for this coach
        for vote in votes:
            if vote.coach_id == outcome.coach_id:
                vote.was_correct = outcome.was_correct
                vote.elo_change = Decimal(str(outcome.elo_change))
                session.add(vote)
                break

    # 6. Mark the leg as closed with P&L
    leg.is_closed = True
    leg.pnl_pct = Decimal(str(pnl_pct))
    leg.closed_at = datetime.utcnow()
    session.add(leg)

    await session.commit()

    return transfer_result
