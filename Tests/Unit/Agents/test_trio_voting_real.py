"""
Real Integration Tests for Trio Voting Service.

Tests agent voting, hivemind aggregation, trio decisions, trade legs,
and full voting rounds against a real PostgreSQL database using the
db_session fixture with transaction rollback for isolation.

All tests use real Coach, AgentInstance, Trio, TradeLeg, and HivemindVote
objects persisted to DB. Only evaluate_conditions is mocked (external
pattern matcher dependency).
"""

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from Fast_Swarm.Agents.Hivemind.Models.coach_models import (
    AgentInstance,
    AgentTemplate,
    Coach,
    CoachStatus,
    HivemindVote,
    TradeLeg,
    Trio,
)
from Fast_Swarm.Agents.Hivemind.Services.trio_voting_service import (
    AgentVote,
    HivemindDecision,
    TrioDecision,
    aggregate_hivemind_votes,
    calculate_trio_decision,
    close_trade_leg,
    collect_agent_votes,
    create_trade_leg,
    evaluate_agent_patterns,
    execute_trio_voting_round,
    record_hivemind_vote,
)


# =============================================================================
# Helper: Create real DB objects
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
    kelly_fraction: float = 0.5,
) -> Coach:
    """Create a real Coach object in the database."""
    cid = coach_id or str(uuid.uuid4())
    traits = COACH_TRAITS.copy()
    traits["kelly_fraction"] = kelly_fraction
    coach = Coach(
        coach_id=cid,
        name=f"Coach {cid[:8]}",
        generation=0,
        elo_rating=Decimal(str(elo)),
        traits=traits,
        status=status,
    )
    db_session.add(coach)
    await db_session.flush()
    return coach


async def create_template(
    db_session: AsyncSession,
    template_id: str | None = None,
) -> AgentTemplate:
    """Create a real AgentTemplate for agent instance FK."""
    tid = template_id or str(uuid.uuid4())
    template = AgentTemplate(
        template_id=tid,
        origin_type="crucible",
        name=f"Template {tid[:8]}",
        traits={"risk_tolerance": 0.5},
        assigned_patterns=["pattern-1", "pattern-2"],
        pattern_weights={"pattern-1": 1.0, "pattern-2": 0.8},
    )
    db_session.add(template)
    await db_session.flush()
    return template


async def create_agent_instance(
    db_session: AsyncSession,
    coach_id: str,
    template_id: str,
    instance_id: str | None = None,
    elo: float = 1500.0,
    roster_status: str = "active",
    is_active: bool = True,
    assigned_patterns: list[str] | None = None,
    pattern_weights: dict[str, float] | None = None,
) -> AgentInstance:
    """Create a real AgentInstance object in the database."""
    iid = instance_id or str(uuid.uuid4())
    agent = AgentInstance(
        instance_id=iid,
        template_id=template_id,
        coach_id=coach_id,
        name=f"Agent {iid[:8]}",
        roster_status=roster_status,
        is_active=is_active,
        elo_rating=Decimal(str(elo)),
        traits={"risk_tolerance": 0.5},
        assigned_patterns=assigned_patterns or ["pattern-1"],
        pattern_weights=pattern_weights or {"pattern-1": 1.0},
    )
    db_session.add(agent)
    await db_session.flush()
    return agent


async def create_trio(
    db_session: AsyncSession,
    coach_ids: list[str],
    trio_id: str | None = None,
) -> Trio:
    """Create a real Trio object in the database."""
    tid = trio_id or str(uuid.uuid4())
    trio = Trio(
        trio_id=tid,
        coach_id_1=coach_ids[0],
        coach_id_2=coach_ids[1],
        coach_id_3=coach_ids[2],
        elo_spread=Decimal("50.0"),
        status="active",
    )
    db_session.add(trio)
    await db_session.flush()
    return trio


# =============================================================================
# Test: evaluate_agent_patterns with known candle data
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.critical
@pytest.mark.requires_db
async def test_evaluate_agent_patterns_with_known_candle_data(db_session: AsyncSession):
    """evaluate_agent_patterns should return direction and confidence from pattern match."""
    template = await create_template(db_session)
    coach = await create_coach(db_session)
    agent = await create_agent_instance(
        db_session,
        coach_id=coach.coach_id,
        template_id=template.template_id,
        assigned_patterns=["pat-1"],
        pattern_weights={"BullishRSI": 1.0},
    )

    candle_data = {
        "open": 50000.0,
        "high": 51000.0,
        "low": 49500.0,
        "close": 50800.0,
        "volume": 1200.0,
        "rsi": 25.0,  # Oversold
        "volume_ratio": 2.0,  # High volume
    }

    patterns = [
        {
            "pattern_id": "pat-1",
            "name": "BullishRSI",
            "direction": "long",
            "entry_conditions": {
                "rsi": {"operator": "<", "value": 30},
                "volume_ratio": {"operator": ">", "value": 1.5},
            },
        },
    ]

    # Mock evaluate_conditions to return a match with high confidence
    mock_result = MagicMock()
    mock_result.matched = True
    mock_result.confidence = 0.9

    with patch(
        "Fast_Swarm.Agents.Hivemind.Services.trio_voting_service.evaluate_agent_patterns.__module__",
        new="test",
    ):
        pass  # Just to ensure module loads

    with patch(
        "Fast_Swarm.local_agents.backtest.pattern_matcher.evaluate_conditions",
        return_value=mock_result,
    ):
        direction, confidence, reasoning = evaluate_agent_patterns(
            agent=agent,
            candle_data=candle_data,
            patterns=patterns,
        )

    # High confidence long pattern -> Strong Buy (+2)
    assert direction == 2, f"Expected Strong Buy (+2), got {direction}"
    assert confidence == 0.9, f"Expected 0.9 confidence, got {confidence}"
    assert reasoning is not None
    assert "BullishRSI" in reasoning


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_evaluate_agent_patterns_no_match(db_session: AsyncSession):
    """evaluate_agent_patterns should return 0 direction when no patterns match."""
    template = await create_template(db_session)
    coach = await create_coach(db_session)
    agent = await create_agent_instance(
        db_session,
        coach_id=coach.coach_id,
        template_id=template.template_id,
        assigned_patterns=["pat-1"],
    )

    candle_data = {"close": 50000.0, "rsi": 50.0}

    patterns = [
        {
            "pattern_id": "pat-1",
            "name": "BullishRSI",
            "direction": "long",
            "entry_conditions": {"rsi": {"operator": "<", "value": 30}},
        },
    ]

    mock_result = MagicMock()
    mock_result.matched = False
    mock_result.confidence = 0.0

    with patch(
        "Fast_Swarm.local_agents.backtest.pattern_matcher.evaluate_conditions",
        return_value=mock_result,
    ):
        direction, confidence, reasoning = evaluate_agent_patterns(
            agent=agent,
            candle_data=candle_data,
            patterns=patterns,
        )

    assert direction == 0
    assert confidence == 0.0
    assert reasoning is None


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_evaluate_agent_patterns_short_direction(db_session: AsyncSession):
    """evaluate_agent_patterns should return negative direction for short patterns."""
    template = await create_template(db_session)
    coach = await create_coach(db_session)
    agent = await create_agent_instance(
        db_session,
        coach_id=coach.coach_id,
        template_id=template.template_id,
        assigned_patterns=["pat-short"],
        pattern_weights={"BearishRSI": 1.0},
    )

    candle_data = {"close": 50000.0, "rsi": 80.0}

    patterns = [
        {
            "pattern_id": "pat-short",
            "name": "BearishRSI",
            "direction": "short",
            "entry_conditions": {"rsi": {"operator": ">", "value": 70}},
        },
    ]

    mock_result = MagicMock()
    mock_result.matched = True
    mock_result.confidence = 0.85  # > 0.8 => Strong Sell (-2)

    with patch(
        "Fast_Swarm.local_agents.backtest.pattern_matcher.evaluate_conditions",
        return_value=mock_result,
    ):
        direction, confidence, reasoning = evaluate_agent_patterns(
            agent=agent,
            candle_data=candle_data,
            patterns=patterns,
        )

    assert direction == -2, f"Expected Strong Sell (-2), got {direction}"
    assert "BearishRSI" in reasoning


# =============================================================================
# Test: aggregate_hivemind_votes with known agent votes
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.critical
@pytest.mark.requires_db
async def test_aggregate_hivemind_votes_majority_buy(db_session: AsyncSession):
    """Hivemind aggregation with majority BUY votes should yield positive direction."""
    coach = await create_coach(db_session, elo=1600, kelly_fraction=0.6)

    agent_votes = [
        AgentVote(instance_id="a1", direction=2, confidence=0.9, elo_rating=1600),
        AgentVote(instance_id="a2", direction=1, confidence=0.8, elo_rating=1500),
        AgentVote(instance_id="a3", direction=-1, confidence=0.5, elo_rating=1400),
    ]
    # Weighted sum: 2*0.9*1600 + 1*0.8*1500 + (-1)*0.5*1400 = 2880 + 1200 - 700 = 3380
    # Total ELO: 1600 + 1500 + 1400 = 4500
    # Avg direction: 3380 / 4500 = 0.751 -> rounds to 1 (Buy)

    decision = await aggregate_hivemind_votes(db_session, coach.coach_id, agent_votes)

    assert decision.coach_id == coach.coach_id
    assert decision.coach_elo == 1600.0
    assert decision.kelly_fraction == 0.6
    assert decision.direction >= 1, f"Expected positive direction, got {decision.direction}"
    assert decision.participating_agents == 3
    assert len(decision.agent_votes) == 3


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_aggregate_hivemind_votes_all_hold(db_session: AsyncSession):
    """All HOLD votes should produce direction=0."""
    coach = await create_coach(db_session, elo=1500)

    agent_votes = [
        AgentVote(instance_id="a1", direction=0, confidence=0.5, elo_rating=1500),
        AgentVote(instance_id="a2", direction=0, confidence=0.6, elo_rating=1500),
    ]

    decision = await aggregate_hivemind_votes(db_session, coach.coach_id, agent_votes)

    assert decision.direction == 0
    assert decision.participating_agents == 0  # Non-zero votes only
    assert decision.confidence == pytest.approx(0.55, abs=0.01)


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_aggregate_hivemind_votes_strong_sell(db_session: AsyncSession):
    """Unanimous strong sell votes should produce direction=-2."""
    coach = await create_coach(db_session, elo=1500)

    agent_votes = [
        AgentVote(instance_id="a1", direction=-2, confidence=0.9, elo_rating=1500),
        AgentVote(instance_id="a2", direction=-2, confidence=0.85, elo_rating=1600),
        AgentVote(instance_id="a3", direction=-2, confidence=0.95, elo_rating=1400),
    ]

    decision = await aggregate_hivemind_votes(db_session, coach.coach_id, agent_votes)

    assert decision.direction == -2, f"Expected -2, got {decision.direction}"
    assert decision.raw_vote_sum < 0


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_aggregate_hivemind_votes_elo_weighting(db_session: AsyncSession):
    """Higher ELO agents should have more influence on the aggregate."""
    coach = await create_coach(db_session, elo=1500)

    # Two low-ELO agents vote BUY, one high-ELO agent votes SELL
    agent_votes = [
        AgentVote(instance_id="a1", direction=1, confidence=0.8, elo_rating=1000),
        AgentVote(instance_id="a2", direction=1, confidence=0.8, elo_rating=1000),
        AgentVote(instance_id="a3", direction=-2, confidence=0.9, elo_rating=5000),
    ]

    decision = await aggregate_hivemind_votes(db_session, coach.coach_id, agent_votes)

    # The high-ELO agent's strong sell should dominate
    assert decision.direction < 0, f"High-ELO agent should dominate, got direction={decision.direction}"


# =============================================================================
# Test: calculate_trio_decision with 3 hivemind decisions
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.critical
async def test_calculate_trio_decision_majority_long():
    """2 long votes vs 1 short should yield direction=+1."""
    decisions = [
        HivemindDecision(
            coach_id="c1", coach_elo=1600, kelly_fraction=0.5,
            direction=1, confidence=0.8, raw_vote_sum=100, participating_agents=3,
        ),
        HivemindDecision(
            coach_id="c2", coach_elo=1550, kelly_fraction=0.6,
            direction=1, confidence=0.7, raw_vote_sum=80, participating_agents=3,
        ),
        HivemindDecision(
            coach_id="c3", coach_elo=1500, kelly_fraction=0.4,
            direction=-1, confidence=0.6, raw_vote_sum=-60, participating_agents=3,
        ),
    ]

    result = calculate_trio_decision(decisions, "trio-1")

    assert result.trio_id == "trio-1"
    assert result.direction == 1, f"Expected long (+1), got {result.direction}"
    assert result.is_trade is True
    assert "c1" in result.winning_coaches
    assert "c2" in result.winning_coaches
    assert "c3" in result.losing_coaches
    assert result.position_size_pct > 0
    assert result.votes_for > result.votes_against


@pytest.mark.asyncio
@pytest.mark.critical
async def test_calculate_trio_decision_majority_short():
    """2 short votes vs 1 long should yield direction=-1."""
    decisions = [
        HivemindDecision(
            coach_id="c1", coach_elo=1600, kelly_fraction=0.5,
            direction=-1, confidence=0.8, raw_vote_sum=-100, participating_agents=3,
        ),
        HivemindDecision(
            coach_id="c2", coach_elo=1550, kelly_fraction=0.6,
            direction=-2, confidence=0.9, raw_vote_sum=-150, participating_agents=3,
        ),
        HivemindDecision(
            coach_id="c3", coach_elo=1500, kelly_fraction=0.4,
            direction=1, confidence=0.6, raw_vote_sum=60, participating_agents=3,
        ),
    ]

    result = calculate_trio_decision(decisions, "trio-2")

    assert result.direction == -1, f"Expected short (-1), got {result.direction}"
    assert result.is_trade is True
    assert "c1" in result.winning_coaches
    assert "c2" in result.winning_coaches
    assert "c3" in result.losing_coaches


@pytest.mark.asyncio
@pytest.mark.critical
async def test_calculate_trio_decision_all_hold():
    """3 HOLD votes should yield direction=0 and no trade."""
    decisions = [
        HivemindDecision(
            coach_id="c1", coach_elo=1600, kelly_fraction=0.5,
            direction=0, confidence=0.5, raw_vote_sum=0, participating_agents=0,
        ),
        HivemindDecision(
            coach_id="c2", coach_elo=1550, kelly_fraction=0.6,
            direction=0, confidence=0.4, raw_vote_sum=0, participating_agents=0,
        ),
        HivemindDecision(
            coach_id="c3", coach_elo=1500, kelly_fraction=0.4,
            direction=0, confidence=0.3, raw_vote_sum=0, participating_agents=0,
        ),
    ]

    result = calculate_trio_decision(decisions, "trio-3")

    assert result.direction == 0
    assert result.is_trade is False
    assert result.position_size_pct == 0.0


async def test_calculate_trio_decision_requires_3_decisions():
    """calculate_trio_decision should raise ValueError with != 3 decisions."""
    with pytest.raises(ValueError, match="exactly 3"):
        calculate_trio_decision([], "trio-err")

    with pytest.raises(ValueError, match="exactly 3"):
        calculate_trio_decision(
            [HivemindDecision(
                coach_id="c1", coach_elo=1500, kelly_fraction=0.5,
                direction=1, confidence=0.8, raw_vote_sum=100, participating_agents=3,
            )],
            "trio-err",
        )


@pytest.mark.asyncio
@pytest.mark.critical
async def test_calculate_trio_decision_position_size_uses_kelly():
    """Position size should be weighted average of winning coaches' Kelly fractions."""
    decisions = [
        HivemindDecision(
            coach_id="c1", coach_elo=1600, kelly_fraction=0.8,
            direction=1, confidence=0.9, raw_vote_sum=100, participating_agents=3,
        ),
        HivemindDecision(
            coach_id="c2", coach_elo=1400, kelly_fraction=0.4,
            direction=1, confidence=0.7, raw_vote_sum=80, participating_agents=3,
        ),
        HivemindDecision(
            coach_id="c3", coach_elo=1500, kelly_fraction=0.3,
            direction=-1, confidence=0.6, raw_vote_sum=-60, participating_agents=3,
        ),
    ]

    result = calculate_trio_decision(decisions, "trio-kelly")

    # Winning coaches: c1 (ELO 1600, kelly 0.8) and c2 (ELO 1400, kelly 0.4)
    # Weighted Kelly = (0.8 * 1600 + 0.4 * 1400) / (1600 + 1400) = (1280 + 560) / 3000 = 0.6133
    # Position size = 0.6133 * 100 = 61.33%
    expected_kelly = (0.8 * 1600 + 0.4 * 1400) / (1600 + 1400)
    expected_size = expected_kelly * 100

    assert result.position_size_pct == pytest.approx(expected_size, abs=0.01)


# =============================================================================
# Test: record_hivemind_vote persists to DB
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.critical
@pytest.mark.requires_db
async def test_record_hivemind_vote_persists(db_session: AsyncSession):
    """record_hivemind_vote should create a HivemindVote record in the DB."""
    # Set up required FK chain: Coach -> Trio -> TradeLeg
    coach = await create_coach(db_session, elo=1600)
    c2 = await create_coach(db_session, elo=1550)
    c3 = await create_coach(db_session, elo=1500)
    trio = await create_trio(db_session, [coach.coach_id, c2.coach_id, c3.coach_id])

    # Create a trade leg (FK for HivemindVote)
    leg = TradeLeg(
        leg_id=str(uuid.uuid4()),
        trio_id=trio.trio_id,
        leg_type="entry",
        direction=1,
        size_pct=Decimal("50.0"),
        asset="BTC/USDT",
        open_price=Decimal("50000.0"),
        open_candle_idx=0,
        elo_weight=Decimal("2.0"),
    )
    db_session.add(leg)
    await db_session.flush()

    # Create hivemind decision
    agent_votes = [
        AgentVote(instance_id="a1", direction=1, confidence=0.8, elo_rating=1500, reasoning="pattern:BullishRSI"),
        AgentVote(instance_id="a2", direction=1, confidence=0.7, elo_rating=1600, reasoning=None),
    ]

    hd = HivemindDecision(
        coach_id=coach.coach_id,
        coach_elo=1600,
        kelly_fraction=0.5,
        direction=1,
        confidence=0.75,
        raw_vote_sum=2380,
        participating_agents=2,
        agent_votes=agent_votes,
    )

    vote = await record_hivemind_vote(db_session, leg.leg_id, trio.trio_id, hd)

    # Verify persisted
    assert vote.id is not None
    assert vote.vote_id is not None
    assert vote.leg_id == leg.leg_id
    assert vote.trio_id == trio.trio_id
    assert vote.coach_id == coach.coach_id
    assert vote.vote_direction == 1
    assert float(vote.confidence) == pytest.approx(0.75, abs=0.001)

    # Verify agent_votes JSON was stored
    assert "a1" in vote.agent_votes
    assert vote.agent_votes["a1"]["direction"] == 1
    assert vote.agent_votes["a1"]["confidence"] == 0.8
    assert vote.agent_votes["a1"]["reasoning"] == "pattern:BullishRSI"

    # Verify we can read it back
    result = await db_session.exec(
        select(HivemindVote).where(HivemindVote.vote_id == vote.vote_id)
    )
    fetched = result.first()
    assert fetched is not None
    assert fetched.vote_direction == 1


# =============================================================================
# Test: create_trade_leg and close_trade_leg with P&L calculation
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.critical
@pytest.mark.requires_db
async def test_create_and_close_trade_leg_long_profit(db_session: AsyncSession):
    """Create a long trade leg, close at higher price -> positive P&L."""
    coach = await create_coach(db_session)
    c2 = await create_coach(db_session)
    c3 = await create_coach(db_session)
    trio = await create_trio(db_session, [coach.coach_id, c2.coach_id, c3.coach_id])

    trio_decision = TrioDecision(
        trio_id=trio.trio_id,
        direction=1,
        confidence=0.8,
        position_size_pct=50.0,
        votes_for=100.0,
        votes_against=30.0,
        winning_coaches=[coach.coach_id, c2.coach_id],
        losing_coaches=[c3.coach_id],
    )

    # Create entry leg at $50,000
    leg = await create_trade_leg(
        db_session,
        trio_id=trio.trio_id,
        trio_decision=trio_decision,
        asset="BTC/USDT",
        current_price=50000.0,
        candle_idx=10,
        leg_type="entry",
    )

    assert leg.leg_id is not None
    assert leg.direction == 1
    assert float(leg.open_price) == 50000.0
    assert leg.is_closed is False
    assert float(leg.elo_weight) == 2.0  # entry leg
    assert float(leg.size_pct) == 50.0

    # Close at $52,000 (4% profit for long)
    closed = await close_trade_leg(db_session, leg.leg_id, 52000.0, candle_idx=20)

    assert closed.is_closed is True
    assert float(closed.close_price) == 52000.0
    assert closed.close_candle_idx == 20
    assert closed.closed_at is not None

    # P&L: ((52000 - 50000) / 50000) * 100 = 4.0%
    assert float(closed.pnl_pct) == pytest.approx(4.0, abs=0.01)


@pytest.mark.asyncio
@pytest.mark.critical
@pytest.mark.requires_db
async def test_create_and_close_trade_leg_short_profit(db_session: AsyncSession):
    """Create a short trade leg, close at lower price -> positive P&L."""
    coach = await create_coach(db_session)
    c2 = await create_coach(db_session)
    c3 = await create_coach(db_session)
    trio = await create_trio(db_session, [coach.coach_id, c2.coach_id, c3.coach_id])

    trio_decision = TrioDecision(
        trio_id=trio.trio_id,
        direction=-1,
        confidence=0.7,
        position_size_pct=40.0,
        votes_for=80.0,
        votes_against=40.0,
        winning_coaches=[coach.coach_id],
        losing_coaches=[c2.coach_id, c3.coach_id],
    )

    # Open short at $50,000
    leg = await create_trade_leg(
        db_session,
        trio_id=trio.trio_id,
        trio_decision=trio_decision,
        asset="ETH/USDT",
        current_price=50000.0,
        candle_idx=5,
        leg_type="entry",
    )

    assert leg.direction == -1

    # Close at $48,000 (4% profit for short)
    closed = await close_trade_leg(db_session, leg.leg_id, 48000.0, candle_idx=15)

    # P&L: ((50000 - 48000) / 50000) * 100 = 4.0%
    assert float(closed.pnl_pct) == pytest.approx(4.0, abs=0.01)
    assert closed.is_closed is True


@pytest.mark.asyncio
@pytest.mark.critical
@pytest.mark.requires_db
async def test_create_and_close_trade_leg_long_loss(db_session: AsyncSession):
    """Create a long trade leg, close at lower price -> negative P&L."""
    coach = await create_coach(db_session)
    c2 = await create_coach(db_session)
    c3 = await create_coach(db_session)
    trio = await create_trio(db_session, [coach.coach_id, c2.coach_id, c3.coach_id])

    trio_decision = TrioDecision(
        trio_id=trio.trio_id, direction=1, confidence=0.6,
        position_size_pct=30.0, votes_for=60.0, votes_against=50.0,
        winning_coaches=[coach.coach_id], losing_coaches=[c2.coach_id, c3.coach_id],
    )

    leg = await create_trade_leg(
        db_session, trio_id=trio.trio_id, trio_decision=trio_decision,
        asset="BTC/USDT", current_price=50000.0, candle_idx=0, leg_type="entry",
    )

    # Close at $47,500 (-5% loss for long)
    closed = await close_trade_leg(db_session, leg.leg_id, 47500.0, candle_idx=10)

    # P&L: ((47500 - 50000) / 50000) * 100 = -5.0%
    assert float(closed.pnl_pct) == pytest.approx(-5.0, abs=0.01)


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_close_trade_leg_already_closed_raises(db_session: AsyncSession):
    """Closing an already-closed leg should raise ValueError."""
    coach = await create_coach(db_session)
    c2 = await create_coach(db_session)
    c3 = await create_coach(db_session)
    trio = await create_trio(db_session, [coach.coach_id, c2.coach_id, c3.coach_id])

    trio_decision = TrioDecision(
        trio_id=trio.trio_id, direction=1, confidence=0.8,
        position_size_pct=50.0, votes_for=100, votes_against=30,
        winning_coaches=[coach.coach_id], losing_coaches=[],
    )

    leg = await create_trade_leg(
        db_session, trio_id=trio.trio_id, trio_decision=trio_decision,
        asset="BTC/USDT", current_price=50000.0, candle_idx=0,
    )

    await close_trade_leg(db_session, leg.leg_id, 51000.0, candle_idx=5)

    with pytest.raises(ValueError, match="already closed"):
        await close_trade_leg(db_session, leg.leg_id, 52000.0, candle_idx=10)


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_close_trade_leg_nonexistent_raises(db_session: AsyncSession):
    """Closing a nonexistent leg should raise ValueError."""
    with pytest.raises(ValueError, match="not found"):
        await close_trade_leg(db_session, "nonexistent-leg-id", 50000.0, candle_idx=0)


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_trade_leg_elo_weight_mid_trade(db_session: AsyncSession):
    """Add/trim legs should get 1.0 ELO weight instead of 2.0."""
    coach = await create_coach(db_session)
    c2 = await create_coach(db_session)
    c3 = await create_coach(db_session)
    trio = await create_trio(db_session, [coach.coach_id, c2.coach_id, c3.coach_id])

    trio_decision = TrioDecision(
        trio_id=trio.trio_id, direction=1, confidence=0.7,
        position_size_pct=20.0, votes_for=70, votes_against=40,
        winning_coaches=[coach.coach_id], losing_coaches=[],
    )

    leg_add = await create_trade_leg(
        db_session, trio_id=trio.trio_id, trio_decision=trio_decision,
        asset="BTC/USDT", current_price=50000.0, candle_idx=0, leg_type="add",
    )
    assert float(leg_add.elo_weight) == 1.0

    leg_trim = await create_trade_leg(
        db_session, trio_id=trio.trio_id, trio_decision=trio_decision,
        asset="BTC/USDT", current_price=50000.0, candle_idx=0, leg_type="trim",
    )
    assert float(leg_trim.elo_weight) == 1.0


# =============================================================================
# Test: Full voting round (execute_trio_voting_round)
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.critical
@pytest.mark.requires_db
async def test_execute_trio_voting_round_full(db_session: AsyncSession):
    """Full end-to-end voting round: 3 coaches with agents vote, trade leg created."""
    # Create 3 coaches
    c1 = await create_coach(db_session, elo=1600, kelly_fraction=0.6)
    c2 = await create_coach(db_session, elo=1550, kelly_fraction=0.5)
    c3 = await create_coach(db_session, elo=1500, kelly_fraction=0.4)

    # Create a trio
    trio = await create_trio(db_session, [c1.coach_id, c2.coach_id, c3.coach_id])

    # Create agent templates and instances for each coach
    template = await create_template(db_session)

    for coach in [c1, c2, c3]:
        for i in range(2):
            await create_agent_instance(
                db_session,
                coach_id=coach.coach_id,
                template_id=template.template_id,
                elo=1500.0 + i * 50,
                roster_status="active",
                is_active=True,
                assigned_patterns=["pat-buy"],
                pattern_weights={"BullSetup": 1.0},
            )

    candle_data = {
        "close": 50000.0,
        "rsi": 25.0,
        "volume_ratio": 2.0,
    }

    patterns = [
        {
            "pattern_id": "pat-buy",
            "name": "BullSetup",
            "direction": "long",
            "entry_conditions": {"rsi": {"operator": "<", "value": 30}},
        },
    ]

    # Mock evaluate_conditions to return a high-confidence long signal
    mock_result = MagicMock()
    mock_result.matched = True
    mock_result.confidence = 0.85

    with patch(
        "Fast_Swarm.local_agents.backtest.pattern_matcher.evaluate_conditions",
        return_value=mock_result,
    ):
        trio_decision, trade_leg = await execute_trio_voting_round(
            session=db_session,
            trio=trio,
            candle_data=candle_data,
            patterns=patterns,
            asset="BTC/USDT",
            candle_idx=42,
            current_price=50000.0,
            leg_type="entry",
        )

    # All agents voted long -> trio should go long
    assert trio_decision.direction == 1 or trio_decision.direction == 2, \
        f"Expected long direction, got {trio_decision.direction}"
    assert trio_decision.is_trade is True

    # Trade leg should have been created
    assert trade_leg is not None
    assert trade_leg.leg_id is not None
    assert trade_leg.asset == "BTC/USDT"
    assert float(trade_leg.open_price) == 50000.0
    assert trade_leg.open_candle_idx == 42
    assert trade_leg.is_closed is False

    # Hivemind votes should have been recorded (3 coaches = 3 votes)
    vote_result = await db_session.exec(
        select(HivemindVote).where(HivemindVote.leg_id == trade_leg.leg_id)
    )
    votes = vote_result.all()
    assert len(votes) == 3, f"Expected 3 hivemind votes, got {len(votes)}"

    # Each vote should reference a different coach
    vote_coach_ids = {v.coach_id for v in votes}
    assert vote_coach_ids == {c1.coach_id, c2.coach_id, c3.coach_id}


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_execute_trio_voting_round_no_trade_when_hold(db_session: AsyncSession):
    """When all agents produce HOLD, no trade leg should be created."""
    c1 = await create_coach(db_session, elo=1600)
    c2 = await create_coach(db_session, elo=1550)
    c3 = await create_coach(db_session, elo=1500)
    trio = await create_trio(db_session, [c1.coach_id, c2.coach_id, c3.coach_id])

    template = await create_template(db_session)
    for coach in [c1, c2, c3]:
        await create_agent_instance(
            db_session,
            coach_id=coach.coach_id,
            template_id=template.template_id,
            assigned_patterns=["pat-1"],
        )

    candle_data = {"close": 50000.0, "rsi": 50.0}
    patterns = [
        {
            "pattern_id": "pat-1",
            "name": "NeutralPattern",
            "direction": "long",
            "entry_conditions": {"rsi": {"operator": "<", "value": 30}},
        },
    ]

    # No pattern matches -> all agents vote HOLD (direction=0)
    mock_result = MagicMock()
    mock_result.matched = False
    mock_result.confidence = 0.0

    with patch(
        "Fast_Swarm.local_agents.backtest.pattern_matcher.evaluate_conditions",
        return_value=mock_result,
    ):
        trio_decision, trade_leg = await execute_trio_voting_round(
            session=db_session,
            trio=trio,
            candle_data=candle_data,
            patterns=patterns,
            asset="BTC/USDT",
            candle_idx=0,
            current_price=50000.0,
        )

    assert trio_decision.direction == 0
    assert trio_decision.is_trade is False
    assert trade_leg is None

    # No hivemind votes should have been recorded
    vote_result = await db_session.exec(
        select(HivemindVote).where(HivemindVote.trio_id == trio.trio_id)
    )
    votes = vote_result.all()
    assert len(votes) == 0


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_execute_trio_voting_round_mixed_votes(db_session: AsyncSession):
    """Mixed agent votes across coaches should produce a majority decision."""
    c1 = await create_coach(db_session, elo=1600, kelly_fraction=0.6)
    c2 = await create_coach(db_session, elo=1550, kelly_fraction=0.5)
    c3 = await create_coach(db_session, elo=1500, kelly_fraction=0.4)
    trio = await create_trio(db_session, [c1.coach_id, c2.coach_id, c3.coach_id])

    template = await create_template(db_session)

    # c1 and c2 each get one agent with a "long" pattern
    for coach in [c1, c2]:
        await create_agent_instance(
            db_session,
            coach_id=coach.coach_id,
            template_id=template.template_id,
            assigned_patterns=["pat-buy"],
            pattern_weights={"BullSetup": 1.0},
        )

    # c3 gets one agent with a "short" pattern
    await create_agent_instance(
        db_session,
        coach_id=c3.coach_id,
        template_id=template.template_id,
        assigned_patterns=["pat-sell"],
        pattern_weights={"BearSetup": 1.0},
    )

    candle_data = {"close": 50000.0, "rsi": 25.0}

    patterns = [
        {
            "pattern_id": "pat-buy",
            "name": "BullSetup",
            "direction": "long",
            "entry_conditions": {"rsi": {"operator": "<", "value": 30}},
        },
        {
            "pattern_id": "pat-sell",
            "name": "BearSetup",
            "direction": "short",
            "entry_conditions": {"rsi": {"operator": "<", "value": 30}},
        },
    ]

    mock_result = MagicMock()
    mock_result.matched = True
    mock_result.confidence = 0.85

    with patch(
        "Fast_Swarm.local_agents.backtest.pattern_matcher.evaluate_conditions",
        return_value=mock_result,
    ):
        trio_decision, trade_leg = await execute_trio_voting_round(
            session=db_session,
            trio=trio,
            candle_data=candle_data,
            patterns=patterns,
            asset="BTC/USDT",
            candle_idx=5,
            current_price=50000.0,
        )

    # 2 coaches long, 1 short -> should be a trade
    assert trio_decision.is_trade is True
    assert trade_leg is not None
