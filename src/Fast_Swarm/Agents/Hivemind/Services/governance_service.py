"""
Governance Service for Committee Voting and ELO Management.

Provides:
- Vote casting with validation
- ELO-weighted vote aggregation
- Quorum enforcement
- ELO updates from outcomes
"""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import desc, select

from ..Models.governance_models import Committee, CommitteeDecision, CommitteeVote

# =============================================================================
# Constants
# =============================================================================

BASE_ELO = 1500.0  # Starting ELO for all agents
ELO_K_FACTOR = 32  # Standard chess K-factor
MAX_CONFIDENCE = 0.95  # Cap confidence to prevent single-agent hijacking
MIN_ELO_WEIGHT = 0.5  # Minimum ELO weight (even low-ELO agents matter)


async def get_all_committees(session: AsyncSession):
    statement = select(Committee).where(Committee.is_active.is_(True))
    result = await session.exec(statement)
    return result.all()


async def get_committee_by_id(session: AsyncSession, committee_id: str):
    statement = select(Committee).where(Committee.committee_id == committee_id)
    result = await session.exec(statement)
    return result.first()


async def get_recent_decisions(session: AsyncSession, committee_id: str, limit: int = 20):
    statement = (
        select(CommitteeDecision)
        .where(CommitteeDecision.committee_id == committee_id)
        .order_by(desc(CommitteeDecision.decided_at))
        .limit(limit)
    )
    result = await session.exec(statement)
    return result.all()


async def get_votes_for_decision(session: AsyncSession, decision_id: str):
    # This is complex because votes map to a timestamp/committee, not directly to decision_id in the schema provided.
    # However, we can approximate by finding votes around the decision time or if there's a linking logic.
    # For now, let's just expose recent votes for a committee as a separate stream.
    pass


async def get_recent_votes(session: AsyncSession, committee_id: str, limit: int = 50):
    statement = (
        select(CommitteeVote)
        .where(CommitteeVote.committee_id == committee_id)
        .order_by(desc(CommitteeVote.voted_at))
        .limit(limit)
    )
    result = await session.exec(statement)
    return result.all()


# =============================================================================
# Voting Logic
# =============================================================================


async def cast_vote(
    session: AsyncSession,
    committee_id: str,
    agent_id: str,
    vote_value: float,
    confidence: float,
    asset: str,
    candle_timestamp: datetime,
    reasoning: str | None = None,
    triggered_pattern_id: str | None = None,
) -> CommitteeVote:
    """
    Cast a weighted vote from an agent.

    Args:
        session: Database session
        committee_id: Committee to vote in
        agent_id: Voting agent
        vote_value: -1.0 (strong sell) to +1.0 (strong buy)
        confidence: 0.0 to 1.0 (capped at MAX_CONFIDENCE)
        asset: Asset being voted on
        candle_timestamp: Candle this vote applies to
        reasoning: Optional explanation
        triggered_pattern_id: Pattern that triggered vote

    Returns:
        Created CommitteeVote

    Raises:
        ValueError: Invalid vote_value or confidence
    """
    # Validate vote_value bounds
    if vote_value < -1.0 or vote_value > 1.0:
        raise ValueError(f"vote_value must be in [-1, 1], got {vote_value}")

    # Validate and cap confidence (anti-poisoning)
    if confidence < 0.0 or confidence > 1.0:
        raise ValueError(f"confidence must be in [0, 1], got {confidence}")
    capped_confidence = min(confidence, MAX_CONFIDENCE)

    # Check committee exists
    committee = await get_committee_by_id(session, committee_id)
    if not committee:
        raise ValueError(f"Committee {committee_id} not found")

    # Create vote
    vote = CommitteeVote(
        vote_id=str(uuid.uuid4()),
        committee_id=committee_id,
        agent_id=agent_id,
        vote_value=vote_value,
        confidence=capped_confidence,
        reasoning=reasoning,
        asset=asset,
        candle_timestamp=candle_timestamp,
        triggered_pattern_id=triggered_pattern_id,
        voted_at=datetime.utcnow(),
    )

    session.add(vote)
    await session.commit()
    await session.refresh(vote)

    return vote


async def get_votes_for_timestamp(
    session: AsyncSession,
    committee_id: str,
    candle_timestamp: datetime,
) -> list[CommitteeVote]:
    """Get all votes for a specific candle timestamp."""
    statement = (
        select(CommitteeVote)
        .where(CommitteeVote.committee_id == committee_id)
        .where(CommitteeVote.candle_timestamp == candle_timestamp)
    )
    result = await session.exec(statement)
    return list(result.all())


async def aggregate_votes(
    session: AsyncSession,
    committee_id: str,
    candle_timestamp: datetime,
    asset: str,
) -> CommitteeDecision | None:
    """
    Aggregate votes into weighted decision with ELO weighting.

    Args:
        session: Database session
        committee_id: Committee to aggregate
        candle_timestamp: Candle to aggregate votes for
        asset: Asset being decided on

    Returns:
        CommitteeDecision if quorum met, None otherwise
    """
    # Import here to avoid circular dependency
    from ...Models.agent_models import Agent

    committee = await get_committee_by_id(session, committee_id)
    if not committee:
        return None

    votes = await get_votes_for_timestamp(session, committee_id, candle_timestamp)

    # Check quorum
    if len(votes) < committee.min_quorum:
        return None  # Quorum not met

    # Get agent ELO ratings
    agent_ids = [v.agent_id for v in votes]
    agent_result = await session.exec(select(Agent).where(Agent.agent_id.in_(agent_ids)))
    agents = {a.agent_id: a for a in agent_result.all()}

    # ELO-weighted aggregation
    weighted_sum = 0.0
    weight_total = 0.0
    raw_sum = 0.0

    for vote in votes:
        agent = agents.get(vote.agent_id)
        elo_rating = agent.elo_rating if agent else BASE_ELO

        # Normalize ELO weight (1500 = 1.0, floor at MIN_ELO_WEIGHT)
        elo_weight = max(MIN_ELO_WEIGHT, elo_rating / BASE_ELO)

        # Combined weight = ELO weight * confidence
        vote_weight = elo_weight * vote.confidence

        weighted_sum += vote.vote_value * vote_weight
        weight_total += vote_weight
        raw_sum += vote.vote_value

    # Calculate final values
    weighted_vote = weighted_sum / weight_total if weight_total > 0 else 0.0
    raw_vote = raw_sum / len(votes) if votes else 0.0

    # Determine decision based on threshold
    if weighted_vote > committee.voting_threshold:
        decision = "BUY"
    elif weighted_vote < -committee.voting_threshold:
        decision = "SELL"
    else:
        decision = "HOLD"

    # Create and persist decision
    committee_decision = CommitteeDecision(
        decision_id=str(uuid.uuid4()),
        committee_id=committee_id,
        weighted_vote=weighted_vote,
        raw_vote=raw_vote,
        num_voters=len(votes),
        decision=decision,
        threshold_used=committee.voting_threshold,
        asset=asset,
        decided_at=datetime.utcnow(),
    )

    session.add(committee_decision)

    # Update committee stats
    committee.total_votes += len(votes)
    session.add(committee)

    await session.commit()
    await session.refresh(committee_decision)

    return committee_decision


# =============================================================================
# ELO Updates
# =============================================================================


async def update_elo_from_outcome(
    session: AsyncSession,
    decision_id: str,
    actual_outcome: float,
) -> dict:
    """
    Update agent ELO based on vote correctness.

    Uses standard ELO formula:
    new_elo = old_elo + K * (actual - expected)

    Where:
    - K = 32 (standard factor)
    - expected = 1 / (1 + 10^((1500 - elo) / 400))
    - actual = 1.0 if vote aligned with outcome, else 0.0

    Args:
        session: Database session
        decision_id: Decision to evaluate
        actual_outcome: Actual price movement (-1 to +1)

    Returns:
        Dict with agent_id -> new_elo mappings
    """
    from ...Models.agent_models import Agent

    # Get decision
    decision_result = await session.exec(select(CommitteeDecision).where(CommitteeDecision.decision_id == decision_id))
    decision = decision_result.first()
    if not decision:
        return {}

    # Get votes for this decision's timestamp
    votes = await get_votes_for_timestamp(
        session,
        decision.committee_id,
        decision.decided_at,  # Use decided_at as proxy for candle_timestamp
    )

    elo_updates = {}

    for vote in votes:
        # Get agent
        agent_result = await session.exec(select(Agent).where(Agent.agent_id == vote.agent_id))
        agent = agent_result.first()
        if not agent:
            continue

        old_elo = agent.elo_rating or BASE_ELO

        # Determine if vote was correct
        # Vote aligns if: (positive vote AND positive outcome) OR (negative vote AND negative outcome)
        vote_correct = (
            (vote.vote_value > 0 and actual_outcome > 0)
            or (vote.vote_value < 0 and actual_outcome < 0)
            or (abs(vote.vote_value) < 0.1 and abs(actual_outcome) < 0.01)
        )  # HOLD was correct

        # ELO calculation
        expected = 1.0 / (1.0 + 10.0 ** ((BASE_ELO - old_elo) / 400.0))
        actual = 1.0 if vote_correct else 0.0

        new_elo = old_elo + ELO_K_FACTOR * (actual - expected)

        # Bound ELO to reasonable range [1000, 2500]
        new_elo = max(1000.0, min(2500.0, new_elo))

        agent.elo_rating = new_elo
        session.add(agent)

        elo_updates[vote.agent_id] = {
            "old_elo": old_elo,
            "new_elo": new_elo,
            "vote_correct": vote_correct,
            "expected": expected,
        }

    # Update committee correct votes count
    committee = await get_committee_by_id(session, decision.committee_id)
    if committee:
        # If weighted vote aligned with outcome, count as correct
        decision_correct = (decision.weighted_vote > 0 and actual_outcome > 0) or (
            decision.weighted_vote < 0 and actual_outcome < 0
        )
        if decision_correct:
            committee.correct_votes += 1
        committee.total_pnl += actual_outcome
        session.add(committee)

    await session.commit()

    return elo_updates


def calculate_elo_weight(elo_rating: float) -> float:
    """
    Calculate voting weight from ELO rating.

    Returns normalized weight where 1500 ELO = 1.0 weight.
    Floor at MIN_ELO_WEIGHT to prevent complete silencing.
    """
    return max(MIN_ELO_WEIGHT, elo_rating / BASE_ELO)
