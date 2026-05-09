"""
Trio Voting Service for Coopetition System.

Implements:
- ELO x Confidence weighted voting within hiveminds
- Trio-level decision aggregation (3 hiveminds vote together)
- Position sizing based on weighted Kelly fractions
- Vote scale: -2 (Strong Sell) to +2 (Strong Buy)

Flow:
1. Each agent instance in a hivemind votes with direction + confidence
2. Hivemind aggregates agent votes (ELO-weighted)
3. Trio aggregates hivemind votes (ELO-weighted)
4. Final decision = majority direction, average position size
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..Models.coach_models import (
    AgentInstance,
    Coach,
    HivemindVote,
    TradeLeg,
    Trio,
)

# =============================================================================
# Data Classes for Voting
# =============================================================================


@dataclass
class AgentVote:
    """Individual agent's vote within a hivemind."""

    instance_id: str
    direction: int  # -2 to +2
    confidence: float  # 0.0 to 1.0
    elo_rating: float
    reasoning: str | None = None

    @property
    def weighted_vote(self) -> float:
        """ELO-weighted vote value."""
        return self.direction * self.confidence * self.elo_rating


@dataclass
class HivemindDecision:
    """Aggregated decision from a single hivemind (coach + roster)."""

    coach_id: str
    coach_elo: float
    kelly_fraction: float  # Coach's position sizing preference

    # Aggregated from agent votes
    direction: int  # -2 to +2 (rounded from weighted average)
    confidence: float  # Average confidence of participating agents
    raw_vote_sum: float  # Sum of all weighted votes
    participating_agents: int

    # Individual agent votes for audit
    agent_votes: list[AgentVote] = field(default_factory=list)

    @property
    def weighted_vote(self) -> float:
        """Coach ELO-weighted vote for trio aggregation."""
        return self.direction * self.confidence * self.coach_elo


@dataclass
class TrioDecision:
    """Final decision from a trio of hiveminds."""

    trio_id: str
    direction: int  # +1 (long), -1 (short), 0 (no action)
    confidence: float  # Weighted average confidence
    position_size_pct: float  # Weighted Kelly-based position size

    # Voting breakdown
    votes_for: float  # Total weighted votes in winning direction
    votes_against: float  # Total weighted votes against
    winning_coaches: list[str]  # Coach IDs that voted with majority
    losing_coaches: list[str]  # Coach IDs that voted against

    # Individual hivemind decisions
    hivemind_decisions: list[HivemindDecision] = field(default_factory=list)

    @property
    def is_trade(self) -> bool:
        """Whether this decision results in a trade action."""
        return self.direction != 0


# =============================================================================
# Agent-Level Voting (within a hivemind)
# =============================================================================


async def collect_agent_votes(
    session: AsyncSession,
    coach_id: str,
    candle_data: dict[str, Any],
    patterns: list[dict],
) -> list[AgentVote]:
    """
    Collect votes from all active agents in a coach's roster.

    Each agent evaluates the current candle against their patterns
    and produces a vote direction + confidence.

    Args:
        session: Database session
        coach_id: Coach whose roster to poll
        candle_data: Current candle with indicators
        patterns: Available pattern definitions

    Returns:
        List of AgentVote from active roster members
    """
    # Get active agents on roster
    result = await session.exec(
        select(AgentInstance)
        .where(AgentInstance.coach_id == coach_id)
        .where(AgentInstance.roster_status == "active")
        .where(AgentInstance.is_active.is_(True))
    )
    agents = result.all()

    votes = []

    for agent in agents:
        # Evaluate agent's patterns against candle
        direction, confidence, reasoning = evaluate_agent_patterns(
            agent=agent,
            candle_data=candle_data,
            patterns=patterns,
        )

        votes.append(
            AgentVote(
                instance_id=agent.instance_id,
                direction=direction,
                confidence=confidence,
                elo_rating=float(agent.elo_rating),
                reasoning=reasoning,
            )
        )

    return votes


def evaluate_agent_patterns(
    agent: AgentInstance,
    candle_data: dict[str, Any],
    patterns: list[dict],
) -> tuple[int, float, str | None]:
    """
    Evaluate an agent's assigned patterns against current candle.

    Returns:
        Tuple of (direction, confidence, reasoning)
        - direction: -2 to +2 vote
        - confidence: 0.0 to 1.0
        - reasoning: Optional explanation
    """
    from Fast_Swarm.local_agents.backtest.pattern_matcher import evaluate_conditions

    best_direction = 0
    best_confidence = 0.0
    best_pattern_name = None

    # Check each assigned pattern
    for pattern_id in agent.assigned_patterns:
        # Find pattern definition
        pattern = next((p for p in patterns if p.get("pattern_id") == pattern_id), None)
        if not pattern:
            continue

        # Evaluate entry conditions
        entry_conditions = pattern.get("entry_conditions", pattern.get("conditions", {}))
        if not entry_conditions:
            continue

        result = evaluate_conditions(entry_conditions, candle_data)

        if result.matched and result.confidence > best_confidence:
            best_confidence = result.confidence
            best_pattern_name = pattern.get("name", pattern_id)

            # Determine direction from pattern
            pattern_direction = pattern.get("direction", "long")
            if pattern_direction == "long":
                # Scale confidence to vote strength
                if result.confidence > 0.8:
                    best_direction = 2  # Strong Buy
                else:
                    best_direction = 1  # Buy
            else:
                if result.confidence > 0.8:
                    best_direction = -2  # Strong Sell
                else:
                    best_direction = -1  # Sell

    # Apply agent's pattern weight
    weight = agent.pattern_weights.get(best_pattern_name, 1.0) if best_pattern_name else 1.0
    best_confidence *= weight

    reasoning = "pattern:" + best_pattern_name if best_pattern_name else None

    return best_direction, best_confidence, reasoning


# =============================================================================
# Hivemind-Level Aggregation
# =============================================================================


async def aggregate_hivemind_votes(
    session: AsyncSession,
    coach_id: str,
    agent_votes: list[AgentVote],
) -> HivemindDecision:
    """
    Aggregate agent votes into a hivemind decision.

    Uses ELO-weighted voting where each agent's vote is scaled by their ELO.

    Args:
        session: Database session
        coach_id: Coach ID
        agent_votes: Votes from active roster

    Returns:
        HivemindDecision with aggregated vote
    """
    # Get coach for Kelly fraction and ELO
    result = await session.exec(
        select(Coach).where(Coach.coach_id == coach_id)
    )
    coach = result.first()

    if not coach:
        raise ValueError("Coach not found: " + coach_id)

    # Filter to participating agents (non-zero votes)
    participating = [v for v in agent_votes if v.direction != 0]

    if not participating:
        # All agents voted HOLD
        avg_conf = sum(v.confidence for v in agent_votes) / len(agent_votes) if agent_votes else 0
        return HivemindDecision(
            coach_id=coach_id,
            coach_elo=float(coach.elo_rating),
            kelly_fraction=coach.kelly_fraction,
            direction=0,
            confidence=avg_conf,
            raw_vote_sum=0,
            participating_agents=0,
            agent_votes=agent_votes,
        )

    # ELO-weighted aggregation
    total_weight = sum(v.elo_rating for v in participating)
    weighted_sum = sum(v.weighted_vote for v in participating)

    # Normalize to get average direction
    if total_weight > 0:
        avg_direction = weighted_sum / total_weight
    else:
        avg_direction = 0

    # Round to nearest vote value (-2, -1, 0, 1, 2)
    if avg_direction > 1.5:
        direction = 2
    elif avg_direction > 0.5:
        direction = 1
    elif avg_direction > -0.5:
        direction = 0
    elif avg_direction > -1.5:
        direction = -1
    else:
        direction = -2

    # Average confidence of participating agents
    avg_confidence = sum(v.confidence for v in participating) / len(participating)

    return HivemindDecision(
        coach_id=coach_id,
        coach_elo=float(coach.elo_rating),
        kelly_fraction=coach.kelly_fraction,
        direction=direction,
        confidence=avg_confidence,
        raw_vote_sum=weighted_sum,
        participating_agents=len(participating),
        agent_votes=agent_votes,
    )


# =============================================================================
# Trio-Level Decision Making
# =============================================================================


def calculate_trio_decision(
    hivemind_decisions: list[HivemindDecision],
    trio_id: str,
) -> TrioDecision:
    """
    Calculate final trio decision from 3 hivemind votes.

    Uses ELO x Confidence weighted voting where majority wins.
    Position size is weighted average of winning coaches' Kelly fractions.

    Args:
        hivemind_decisions: List of 3 HivemindDecision objects
        trio_id: ID of the trio

    Returns:
        TrioDecision with final direction and position size
    """
    if len(hivemind_decisions) != 3:
        raise ValueError("Trio requires exactly 3 hivemind decisions")

    # Calculate weighted votes for each direction
    long_votes = 0.0  # Positive direction votes
    short_votes = 0.0  # Negative direction votes
    hold_votes = 0.0  # Zero votes

    for hd in hivemind_decisions:
        weighted = abs(hd.direction) * hd.confidence * hd.coach_elo

        if hd.direction > 0:
            long_votes += weighted
        elif hd.direction < 0:
            short_votes += weighted
        else:
            hold_votes += weighted

    # Determine winning direction
    if long_votes > short_votes and long_votes > hold_votes:
        final_direction = 1
        votes_for = long_votes
        votes_against = short_votes + hold_votes
    elif short_votes > long_votes and short_votes > hold_votes:
        final_direction = -1
        votes_for = short_votes
        votes_against = long_votes + hold_votes
    else:
        # HOLD wins (or tie)
        final_direction = 0
        votes_for = hold_votes
        votes_against = long_votes + short_votes

    # Categorize coaches
    winning_coaches = []
    losing_coaches = []

    for hd in hivemind_decisions:
        if final_direction == 0:
            # HOLD wins - those who voted HOLD win
            if hd.direction == 0:
                winning_coaches.append(hd.coach_id)
            else:
                losing_coaches.append(hd.coach_id)
        elif final_direction > 0:
            # LONG wins
            if hd.direction > 0:
                winning_coaches.append(hd.coach_id)
            else:
                losing_coaches.append(hd.coach_id)
        else:
            # SHORT wins
            if hd.direction < 0:
                winning_coaches.append(hd.coach_id)
            else:
                losing_coaches.append(hd.coach_id)

    # Calculate position size (weighted Kelly of winners)
    if winning_coaches and final_direction != 0:
        winners = [hd for hd in hivemind_decisions if hd.coach_id in winning_coaches]
        total_elo = sum(hd.coach_elo for hd in winners)
        weighted_kelly = sum(hd.kelly_fraction * hd.coach_elo for hd in winners) / total_elo
        position_size = weighted_kelly * 100  # Convert to percentage
    else:
        position_size = 0.0

    # Average confidence of winners
    if winning_coaches:
        winners = [hd for hd in hivemind_decisions if hd.coach_id in winning_coaches]
        avg_confidence = sum(hd.confidence for hd in winners) / len(winners)
    else:
        avg_confidence = 0.0

    return TrioDecision(
        trio_id=trio_id,
        direction=final_direction,
        confidence=avg_confidence,
        position_size_pct=position_size,
        votes_for=votes_for,
        votes_against=votes_against,
        winning_coaches=winning_coaches,
        losing_coaches=losing_coaches,
        hivemind_decisions=hivemind_decisions,
    )


# =============================================================================
# Database Operations
# =============================================================================


async def record_hivemind_vote(
    session: AsyncSession,
    leg_id: str,
    trio_id: str,
    hivemind_decision: HivemindDecision,
) -> HivemindVote:
    """
    Record a hivemind's vote to the database.

    Args:
        session: Database session
        leg_id: Trade leg being voted on
        trio_id: Trio ID
        hivemind_decision: The hivemind's decision

    Returns:
        Created HivemindVote record
    """
    # Serialize agent votes for storage
    agent_votes_json = {
        av.instance_id: {
            "direction": av.direction,
            "confidence": av.confidence,
            "elo": av.elo_rating,
            "reasoning": av.reasoning,
        }
        for av in hivemind_decision.agent_votes
    }

    vote = HivemindVote(
        vote_id=str(uuid.uuid4()),
        leg_id=leg_id,
        trio_id=trio_id,
        coach_id=hivemind_decision.coach_id,
        vote_direction=hivemind_decision.direction,
        confidence=Decimal(str(hivemind_decision.confidence)),
        weighted_vote=Decimal(str(hivemind_decision.weighted_vote)),
        agent_votes=agent_votes_json,
    )

    session.add(vote)
    await session.commit()
    await session.refresh(vote)

    return vote


async def create_trade_leg(
    session: AsyncSession,
    trio_id: str,
    trio_decision: TrioDecision,
    asset: str,
    current_price: float,
    candle_idx: int,
    leg_type: str = "entry",
) -> TradeLeg:
    """
    Create a new trade leg from a trio decision.

    Args:
        session: Database session
        trio_id: Trio ID
        trio_decision: The trio's decision
        asset: Asset being traded
        current_price: Entry price
        candle_idx: Candle index for timing
        leg_type: Type of leg (entry, add, trim, exit, flip)

    Returns:
        Created TradeLeg record
    """
    # Determine ELO weight based on leg type
    if leg_type in ("entry", "exit", "flip"):
        elo_weight = 2.0
    else:
        elo_weight = 1.0

    leg = TradeLeg(
        leg_id=str(uuid.uuid4()),
        trio_id=trio_id,
        leg_type=leg_type,
        direction=trio_decision.direction,
        size_pct=Decimal(str(trio_decision.position_size_pct)),
        asset=asset,
        open_price=Decimal(str(current_price)),
        open_candle_idx=candle_idx,
        elo_weight=Decimal(str(elo_weight)),
    )

    session.add(leg)
    await session.commit()
    await session.refresh(leg)

    return leg


async def close_trade_leg(
    session: AsyncSession,
    leg_id: str,
    close_price: float,
    candle_idx: int,
) -> TradeLeg:
    """
    Close an open trade leg and calculate P&L.

    Args:
        session: Database session
        leg_id: Leg to close
        close_price: Exit price
        candle_idx: Candle index for timing

    Returns:
        Updated TradeLeg record
    """
    result = await session.exec(
        select(TradeLeg).where(TradeLeg.leg_id == leg_id)
    )
    leg = result.first()

    if not leg:
        raise ValueError("Trade leg not found: " + leg_id)

    if leg.is_closed:
        raise ValueError("Trade leg already closed: " + leg_id)

    # Calculate P&L
    open_price = float(leg.open_price)
    if leg.direction > 0:  # Long
        pnl_pct = ((close_price - open_price) / open_price) * 100
    else:  # Short
        pnl_pct = ((open_price - close_price) / open_price) * 100

    leg.close_price = Decimal(str(close_price))
    leg.close_candle_idx = candle_idx
    leg.pnl_pct = Decimal(str(pnl_pct))
    leg.is_closed = True
    leg.closed_at = datetime.utcnow()

    session.add(leg)
    await session.commit()
    await session.refresh(leg)

    return leg


# =============================================================================
# Full Voting Flow
# =============================================================================


async def execute_trio_voting_round(
    session: AsyncSession,
    trio: Trio,
    candle_data: dict[str, Any],
    patterns: list[dict],
    asset: str,
    candle_idx: int,
    current_price: float,
    leg_type: str = "entry",
) -> tuple[TrioDecision, TradeLeg | None]:
    """
    Execute a complete voting round for a trio.

    This is the main entry point for trio voting.

    Args:
        session: Database session
        trio: Trio to vote
        candle_data: Current candle with indicators
        patterns: Available pattern definitions
        asset: Asset being evaluated
        candle_idx: Current candle index
        current_price: Current price
        leg_type: Type of leg being decided

    Returns:
        Tuple of (TrioDecision, TradeLeg or None if no trade)
    """
    coach_ids = [trio.coach_id_1, trio.coach_id_2, trio.coach_id_3]
    hivemind_decisions = []

    # Collect votes from each hivemind
    for coach_id in coach_ids:
        # Get agent votes
        agent_votes = await collect_agent_votes(
            session=session,
            coach_id=coach_id,
            candle_data=candle_data,
            patterns=patterns,
        )

        # Aggregate into hivemind decision
        hd = await aggregate_hivemind_votes(
            session=session,
            coach_id=coach_id,
            agent_votes=agent_votes,
        )

        hivemind_decisions.append(hd)

    # Calculate trio decision
    trio_decision = calculate_trio_decision(
        hivemind_decisions=hivemind_decisions,
        trio_id=trio.trio_id,
    )

    # If trade decision, create leg and record votes
    trade_leg = None
    if trio_decision.is_trade:
        # Create trade leg
        trade_leg = await create_trade_leg(
            session=session,
            trio_id=trio.trio_id,
            trio_decision=trio_decision,
            asset=asset,
            current_price=current_price,
            candle_idx=candle_idx,
            leg_type=leg_type,
        )

        # Record each hivemind's vote
        for hd in hivemind_decisions:
            await record_hivemind_vote(
                session=session,
                leg_id=trade_leg.leg_id,
                trio_id=trio.trio_id,
                hivemind_decision=hd,
            )

    return trio_decision, trade_leg
