"""
Coach LLM Service.

Provides LLM-guided decision making for coaches to manage their rosters.

Architecture Note:
- Hiveminds start in PAPER TRADING mode (backtests on live tick data)
- Successful hiveminds get PROMOTED to LIVE TRADING
- This creates a two-tier system: paper -> live

Coaches use LLMs to decide:
- Which agents to bench/activate based on market conditions
- When to swap templates between roster slots
- How to adapt roster composition to regime changes
- Whether to accept/reject cloned agents

The LLM acts as the coach's "brain" - coaches have traits that influence
their strategic preferences, but the LLM makes the actual decisions.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..Models.coach_models import (
    AgentInstance,
    AgentTemplate,
    Coach,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Trading Tier System
# =============================================================================


class TradingTier(str, Enum):
    """Trading tier for coaches/hiveminds."""

    PAPER = "paper"  # Paper trading on live tick data
    LIVE = "live"  # Real money trading


# Promotion thresholds
PAPER_TO_LIVE_ELO_THRESHOLD = 1650  # Must reach 1650 ELO to get promoted
PAPER_MIN_TRADES = 50  # Must have at least 50 paper trades
PAPER_MIN_WIN_RATE = 0.55  # Must have >55% win rate
LIVE_DEMOTION_ELO = 1400  # Demoted back to paper if drop below 1400


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class RosterContext:
    """
    Context for roster decision making.

    Includes all information a coach needs to make roster decisions.
    """

    coach: Coach
    trading_tier: TradingTier  # Paper or Live
    current_roster: list[AgentInstance]
    benched_agents: list[AgentInstance]
    available_templates: list[AgentTemplate]

    # Performance metrics
    coach_elo: float
    roster_avg_elo: float
    best_agent_elo: float
    worst_agent_elo: float

    # Market context
    current_regime: str  # 'bull', 'bear', 'chop', 'flat'
    regime_indicators: dict[str, float]

    # Recent history
    recent_trades: list[dict]
    recent_win_rate: float
    recent_pnl: float
    total_trades: int

    # Promotion status
    eligible_for_promotion: bool = False
    promotion_blockers: list[str] = None

    def to_prompt_context(self) -> str:
        """Format context for LLM prompt."""
        roster_summary = []
        for agent in self.current_roster:
            roster_summary.append(
                f"  - {agent.name} (ELO: {float(agent.elo_rating):.0f}, "
                f"patterns: {len(agent.assigned_patterns)}, "
                f"slot: {agent.slot_number})"
            )

        bench_summary = []
        for agent in self.benched_agents:
            bench_summary.append(
                f"  - {agent.name} (ELO: {float(agent.elo_rating):.0f})"
            )

        template_summary = []
        for template in self.available_templates[:10]:  # Top 10
            template_summary.append(
                f"  - {template.name} (fitness: {float(template.overall_fitness):.2f}, "
                f"copied: {template.times_copied}x)"
            )

        tier_status = f"TRADING TIER: {self.trading_tier.value.upper()}"
        if self.trading_tier == TradingTier.PAPER:
            if self.eligible_for_promotion:
                tier_status += " (ELIGIBLE FOR PROMOTION TO LIVE)"
            elif self.promotion_blockers:
                tier_status += f" (Blockers: {', '.join(self.promotion_blockers)})"

        return f"""
COACH: {self.coach.name}
ELO: {self.coach_elo:.0f}
Generation: {self.coach.generation}
{tier_status}

COACH TRAITS:
- Kelly Fraction: {self.coach.traits.get('kelly_fraction', 0.5):.2f} (higher = more aggressive sizing)
- Action Threshold: {self.coach.traits.get('action_threshold', 0.5):.2f} (higher = requires more confidence)
- Regime Sensitivity: {self.coach.traits.get('regime_sensitivity', 0.5):.2f} (higher = more reactive to regime)
- Roster Size Preference: {self.coach.traits.get('roster_size_preference', 3):.0f}

CURRENT ROSTER ({len(self.current_roster)} active):
{chr(10).join(roster_summary) if roster_summary else "  (empty)"}

BENCHED AGENTS ({len(self.benched_agents)}):
{chr(10).join(bench_summary) if bench_summary else "  (none)"}

AVAILABLE TEMPLATES (top 10 by fitness):
{chr(10).join(template_summary) if template_summary else "  (none available)"}

MARKET REGIME: {self.current_regime.upper()}
Regime Indicators:
- Trend strength: {self.regime_indicators.get('trend_strength', 0):.2f}
- Volatility: {self.regime_indicators.get('volatility', 0):.2f}
- Momentum: {self.regime_indicators.get('momentum', 0):.2f}

RECENT PERFORMANCE:
- Win Rate: {self.recent_win_rate:.1%}
- P&L: ${self.recent_pnl:.2f}
- Total Trades: {self.total_trades}
- Roster Avg ELO: {self.roster_avg_elo:.0f}
- Best Agent ELO: {self.best_agent_elo:.0f}
- Worst Agent ELO: {self.worst_agent_elo:.0f}
"""


@dataclass
class RosterDecision:
    """
    A roster management decision from the LLM.
    """

    action: str  # 'bench', 'activate', 'swap', 'acquire', 'release', 'none'
    target_agent_id: str | None = None  # Agent to act on
    source_slot: int | None = None  # For swaps
    dest_slot: int | None = None  # For swaps
    template_id: str | None = None  # For acquisitions
    reasoning: str = ""  # LLM's explanation


# =============================================================================
# Promotion Logic
# =============================================================================


def check_promotion_eligibility(
    coach: Coach,
    total_trades: int,
    win_rate: float,
) -> tuple[bool, list[str]]:
    """
    Check if a paper-trading coach is eligible for promotion to live.

    Args:
        coach: Coach to check
        total_trades: Total paper trades completed
        win_rate: Recent win rate

    Returns:
        Tuple of (is_eligible, list of blockers)
    """
    blockers = []

    elo = float(coach.elo_rating)
    if elo < PAPER_TO_LIVE_ELO_THRESHOLD:
        blockers.append(f"ELO {elo:.0f} < {PAPER_TO_LIVE_ELO_THRESHOLD}")

    if total_trades < PAPER_MIN_TRADES:
        blockers.append(f"Trades {total_trades} < {PAPER_MIN_TRADES}")

    if win_rate < PAPER_MIN_WIN_RATE:
        blockers.append(f"Win rate {win_rate:.1%} < {PAPER_MIN_WIN_RATE:.1%}")

    return len(blockers) == 0, blockers


def check_demotion_needed(coach: Coach) -> bool:
    """Check if a live coach should be demoted to paper."""
    return float(coach.elo_rating) < LIVE_DEMOTION_ELO


async def promote_coach_to_live(
    session: AsyncSession,
    coach: Coach,
) -> bool:
    """
    Promote a coach from paper to live trading.

    Args:
        session: Database session
        coach: Coach to promote

    Returns:
        True if promotion successful
    """
    if coach.trading_tier == TradingTier.LIVE.value:
        return False  # Already live

    coach.trading_tier = TradingTier.LIVE.value
    coach.promoted_at = datetime.now(UTC)
    session.add(coach)
    await session.commit()

    logger.info("Coach %s PROMOTED to LIVE trading (ELO: %.0f)",
                coach.name, float(coach.elo_rating))
    return True


async def demote_coach_to_paper(
    session: AsyncSession,
    coach: Coach,
) -> bool:
    """
    Demote a coach from live back to paper trading.

    Args:
        session: Database session
        coach: Coach to demote

    Returns:
        True if demotion occurred
    """
    if coach.trading_tier == TradingTier.PAPER.value:
        return False  # Already paper

    coach.trading_tier = TradingTier.PAPER.value
    coach.demoted_at = datetime.now(UTC)
    session.add(coach)
    await session.commit()

    logger.warning("Coach %s DEMOTED to PAPER trading (ELO: %.0f)",
                   coach.name, float(coach.elo_rating))
    return True


# =============================================================================
# LLM Integration
# =============================================================================


class CoachLLMService:
    """
    Service for LLM-guided coach decisions.

    Uses the system's existing LLM infrastructure to make roster decisions.
    """

    def __init__(self, llm_client=None):
        """
        Initialize the service.

        Args:
            llm_client: LLM client for generating decisions
        """
        self.llm_client = llm_client

    async def get_roster_decision(
        self,
        context: RosterContext,
    ) -> RosterDecision:
        """
        Get LLM recommendation for roster management.

        Args:
            context: Full context for decision making

        Returns:
            RosterDecision with recommended action
        """
        if not self.llm_client:
            # No LLM available - return no action
            return RosterDecision(action="none", reasoning="No LLM client configured")

        prompt = self._build_roster_prompt(context)

        try:
            response = await self._query_llm(prompt)
            decision = self._parse_roster_response(response, context)
            return decision

        except Exception as e:
            logger.error("LLM roster decision error: %s", e)
            return RosterDecision(action="none", reasoning=f"Error: {e}")

    def _build_roster_prompt(self, context: RosterContext) -> str:
        """Build prompt for roster decision."""
        tier_note = ""
        if context.trading_tier == TradingTier.PAPER:
            tier_note = """
NOTE: This coach is in PAPER TRADING mode. Focus on:
- Learning which agents work in current regime
- Building a consistent track record
- Preparing for promotion to live trading
"""
        else:
            tier_note = """
NOTE: This coach is in LIVE TRADING mode. Be more conservative:
- Prioritize capital preservation
- Only make changes with strong reasoning
- Consider the real money at stake
"""

        return f"""You are an AI trading coach managing a roster of trading agents.
{tier_note}
{context.to_prompt_context()}

Based on the current market regime and your roster's performance, decide on ONE roster action.

Available actions:
1. BENCH <agent_id> - Move an active agent to the bench (saves their state)
2. ACTIVATE <agent_id> - Move a benched agent to active roster
3. SWAP <slot_a> <slot_b> - Swap positions of two agents
4. ACQUIRE <template_id> - Add a new agent from template catalog (if under roster limit)
5. RELEASE <agent_id> - Permanently remove agent (saves to template catalog with current traits)
6. NONE - No roster changes needed

Consider:
- Your coach traits (especially regime_sensitivity for regime changes)
- Which agents perform well in the current regime
- Whether you're at roster capacity
- Recent performance trends

Respond in JSON format:
{{
    "action": "BENCH|ACTIVATE|SWAP|ACQUIRE|RELEASE|NONE",
    "target_agent_id": "id or null",
    "source_slot": "number or null",
    "dest_slot": "number or null",
    "template_id": "id or null",
    "reasoning": "brief explanation"
}}
"""

    async def _query_llm(self, prompt: str) -> str:
        """Query the LLM for a decision."""
        if hasattr(self.llm_client, "generate"):
            # Async generate method
            return await self.llm_client.generate(prompt)
        elif hasattr(self.llm_client, "complete"):
            # Completion method
            return self.llm_client.complete(prompt)
        else:
            raise ValueError("LLM client has no generate or complete method")

    def _parse_roster_response(
        self,
        response: str,
        context: RosterContext,
    ) -> RosterDecision:
        """Parse LLM response into a RosterDecision."""
        try:
            # Try to extract JSON from response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1

            if json_start == -1 or json_end == 0:
                return RosterDecision(
                    action="none",
                    reasoning="Could not parse LLM response as JSON",
                )

            json_str = response[json_start:json_end]
            data = json.loads(json_str)

            action = data.get("action", "NONE").upper()

            # Validate action
            valid_actions = {"BENCH", "ACTIVATE", "SWAP", "ACQUIRE", "RELEASE", "NONE"}
            if action not in valid_actions:
                action = "NONE"

            return RosterDecision(
                action=action.lower(),
                target_agent_id=data.get("target_agent_id"),
                source_slot=data.get("source_slot"),
                dest_slot=data.get("dest_slot"),
                template_id=data.get("template_id"),
                reasoning=data.get("reasoning", ""),
            )

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse LLM JSON response: %s", e)
            return RosterDecision(
                action="none",
                reasoning=f"JSON parse error: {e}",
            )


# =============================================================================
# Roster Management Operations
# =============================================================================


async def bench_agent(
    session: AsyncSession,
    coach: Coach,
    agent_id: str,
) -> bool:
    """Move an active agent to the bench."""
    result = await session.exec(
        select(AgentInstance)
        .where(AgentInstance.instance_id == agent_id)
        .where(AgentInstance.coach_id == coach.coach_id)
        .where(AgentInstance.is_active == True)
    )
    agent = result.first()

    if not agent:
        logger.warning("Agent %s not found or not active for coach %s", agent_id, coach.coach_id)
        return False

    agent.roster_status = "benched"
    agent.is_active = False
    agent.slot_number = None
    session.add(agent)
    await session.commit()

    logger.info("Coach %s benched agent %s", coach.name, agent.name)
    return True


async def activate_agent(
    session: AsyncSession,
    coach: Coach,
    agent_id: str,
) -> bool:
    """Move a benched agent to active roster."""
    # Check roster capacity
    active_result = await session.exec(
        select(AgentInstance)
        .where(AgentInstance.coach_id == coach.coach_id)
        .where(AgentInstance.is_active == True)
    )
    active_count = len(active_result.all())

    if active_count >= coach.max_roster_size:
        logger.warning("Coach %s at roster capacity (%d)", coach.name, active_count)
        return False

    # Find benched agent
    result = await session.exec(
        select(AgentInstance)
        .where(AgentInstance.instance_id == agent_id)
        .where(AgentInstance.coach_id == coach.coach_id)
        .where(AgentInstance.roster_status == "benched")
    )
    agent = result.first()

    if not agent:
        logger.warning("Benched agent %s not found for coach %s", agent_id, coach.coach_id)
        return False

    # Find next available slot
    next_slot = active_count + 1

    agent.roster_status = "active"
    agent.is_active = True
    agent.slot_number = next_slot
    session.add(agent)
    await session.commit()

    logger.info("Coach %s activated agent %s to slot %d", coach.name, agent.name, next_slot)
    return True


async def swap_agents(
    session: AsyncSession,
    coach: Coach,
    slot_a: int,
    slot_b: int,
) -> bool:
    """Swap positions of two agents."""
    result = await session.exec(
        select(AgentInstance)
        .where(AgentInstance.coach_id == coach.coach_id)
        .where(AgentInstance.is_active == True)
        .where(AgentInstance.slot_number.in_([slot_a, slot_b]))
    )
    agents = result.all()

    if len(agents) != 2:
        logger.warning("Could not find both agents for swap (slots %d, %d)", slot_a, slot_b)
        return False

    # Swap slots
    for agent in agents:
        if agent.slot_number == slot_a:
            agent.slot_number = slot_b
        else:
            agent.slot_number = slot_a
        session.add(agent)

    await session.commit()
    logger.info("Coach %s swapped slots %d and %d", coach.name, slot_a, slot_b)
    return True


async def acquire_agent_from_template(
    session: AsyncSession,
    coach: Coach,
    template_id: str,
) -> AgentInstance | None:
    """Add a new agent from the template catalog."""
    import uuid

    # Check roster capacity
    active_result = await session.exec(
        select(AgentInstance)
        .where(AgentInstance.coach_id == coach.coach_id)
        .where(AgentInstance.is_active == True)
    )
    active_agents = active_result.all()
    active_count = len(active_agents)

    if active_count >= coach.max_roster_size:
        logger.warning("Coach %s at roster capacity", coach.name)
        return None

    # Get template
    template_result = await session.exec(
        select(AgentTemplate).where(AgentTemplate.template_id == template_id)
    )
    template = template_result.first()

    if not template:
        logger.warning("Template %s not found", template_id)
        return None

    # Create new agent instance
    next_slot = active_count + 1

    instance = AgentInstance(
        instance_id=str(uuid.uuid4()),
        template_id=template.template_id,
        coach_id=coach.coach_id,
        roster_status="active",
        slot_number=next_slot,
        name=template.name,
        traits=template.traits.copy(),
        assigned_patterns=template.assigned_patterns.copy(),
        pattern_weights=template.pattern_weights.copy(),
        elo_rating=Decimal("1500"),
        generation=0,
        acquired_at=datetime.now(UTC),
    )

    session.add(instance)

    # Update template popularity
    template.times_copied += 1
    session.add(template)

    await session.commit()
    await session.refresh(instance)

    logger.info("Coach %s acquired agent %s from template", coach.name, instance.name)
    return instance


async def release_agent(
    session: AsyncSession,
    coach: Coach,
    agent_id: str,
) -> AgentTemplate | None:
    """Permanently release an agent, saving to template catalog if mutated."""
    import uuid

    result = await session.exec(
        select(AgentInstance)
        .where(AgentInstance.instance_id == agent_id)
        .where(AgentInstance.coach_id == coach.coach_id)
    )
    agent = result.first()

    if not agent:
        logger.warning("Agent %s not found for coach %s", agent_id, coach.coach_id)
        return None

    # Check if agent has diverged from template
    new_template = None
    if agent.template_id:
        template_result = await session.exec(
            select(AgentTemplate).where(AgentTemplate.template_id == agent.template_id)
        )
        original_template = template_result.first()

        if original_template and agent.traits != original_template.traits:
            # Agent has evolved - save as new template
            new_template = AgentTemplate(
                template_id=str(uuid.uuid4()),
                origin_type="release",
                source_agent_id=agent.instance_id,
                parent_template_id=agent.template_id,
                name=f"{agent.name} (released)",
                traits=agent.traits.copy(),
                assigned_patterns=agent.assigned_patterns.copy(),
                pattern_weights=agent.pattern_weights.copy(),
                overall_fitness=Decimal(str(float(agent.elo_rating) / 10)),
                regime_scores={},
                created_at=datetime.now(UTC),
            )
            session.add(new_template)

    # Mark agent as released
    agent.is_active = False
    agent.roster_status = "released"
    agent.released_at = datetime.now(UTC)
    session.add(agent)

    await session.commit()

    if new_template:
        await session.refresh(new_template)
        logger.info("Coach %s released agent %s, created template %s",
                    coach.name, agent.name, new_template.template_id[:8])
    else:
        logger.info("Coach %s released agent %s (no new template)", coach.name, agent.name)

    return new_template


# =============================================================================
# Roster Decision Execution
# =============================================================================


async def execute_roster_decision(
    session: AsyncSession,
    coach: Coach,
    decision: RosterDecision,
) -> bool:
    """Execute a roster decision."""
    action = decision.action.lower()

    if action == "none":
        return True

    if action == "bench" and decision.target_agent_id:
        return await bench_agent(session, coach, decision.target_agent_id)

    if action == "activate" and decision.target_agent_id:
        return await activate_agent(session, coach, decision.target_agent_id)

    if action == "swap" and decision.source_slot and decision.dest_slot:
        return await swap_agents(session, coach, decision.source_slot, decision.dest_slot)

    if action == "acquire" and decision.template_id:
        result = await acquire_agent_from_template(session, coach, decision.template_id)
        return result is not None

    if action == "release" and decision.target_agent_id:
        await release_agent(session, coach, decision.target_agent_id)
        return True

    logger.warning("Invalid roster decision: %s", decision)
    return False


# =============================================================================
# Context Building
# =============================================================================


async def build_roster_context(
    session: AsyncSession,
    coach: Coach,
    current_regime: str = "unknown",
    regime_indicators: dict | None = None,
    recent_trades: list | None = None,
) -> RosterContext:
    """Build full context for roster decision making."""
    # Get active roster
    active_result = await session.exec(
        select(AgentInstance)
        .where(AgentInstance.coach_id == coach.coach_id)
        .where(AgentInstance.is_active == True)
        .order_by(AgentInstance.slot_number)
    )
    active_roster = list(active_result.all())

    # Get benched agents
    benched_result = await session.exec(
        select(AgentInstance)
        .where(AgentInstance.coach_id == coach.coach_id)
        .where(AgentInstance.roster_status == "benched")
    )
    benched_agents = list(benched_result.all())

    # Get available templates (top 50 by fitness)
    template_result = await session.exec(
        select(AgentTemplate)
        .order_by(AgentTemplate.overall_fitness.desc())
        .limit(50)
    )
    available_templates = list(template_result.all())

    # Calculate roster metrics
    roster_elos = [float(a.elo_rating) for a in active_roster] if active_roster else [1500]
    roster_avg_elo = sum(roster_elos) / len(roster_elos)
    best_agent_elo = max(roster_elos)
    worst_agent_elo = min(roster_elos)

    # Calculate recent performance
    recent_trades = recent_trades or []
    total_trades = len(recent_trades)
    wins = sum(1 for t in recent_trades if t.get("pnl", 0) > 0)
    recent_win_rate = wins / total_trades if total_trades else 0.5
    recent_pnl = sum(t.get("pnl", 0) for t in recent_trades)

    # Determine trading tier
    trading_tier = TradingTier(coach.trading_tier) if hasattr(coach, "trading_tier") else TradingTier.PAPER

    # Check promotion eligibility for paper traders
    eligible, blockers = check_promotion_eligibility(coach, total_trades, recent_win_rate)

    return RosterContext(
        coach=coach,
        trading_tier=trading_tier,
        current_roster=active_roster,
        benched_agents=benched_agents,
        available_templates=available_templates,
        coach_elo=float(coach.elo_rating),
        roster_avg_elo=roster_avg_elo,
        best_agent_elo=best_agent_elo,
        worst_agent_elo=worst_agent_elo,
        current_regime=current_regime,
        regime_indicators=regime_indicators or {},
        recent_trades=recent_trades,
        recent_win_rate=recent_win_rate,
        recent_pnl=recent_pnl,
        total_trades=total_trades,
        eligible_for_promotion=eligible,
        promotion_blockers=blockers,
    )


# =============================================================================
# Scheduled Reviews
# =============================================================================


async def run_roster_review_cycle(
    session: AsyncSession,
    llm_service: CoachLLMService,
    coach: Coach,
    current_regime: str = "unknown",
    regime_indicators: dict | None = None,
) -> RosterDecision:
    """
    Run a complete roster review cycle for a coach.

    Returns the decision that was made (and executed).
    """
    # Build context
    context = await build_roster_context(
        session=session,
        coach=coach,
        current_regime=current_regime,
        regime_indicators=regime_indicators,
    )

    # Check for promotion/demotion
    if context.trading_tier == TradingTier.PAPER and context.eligible_for_promotion:
        await promote_coach_to_live(session, coach)

    if context.trading_tier == TradingTier.LIVE and check_demotion_needed(coach):
        await demote_coach_to_paper(session, coach)

    # Get LLM decision
    decision = await llm_service.get_roster_decision(context)

    # Execute decision
    if decision.action != "none":
        success = await execute_roster_decision(session, coach, decision)
        if success:
            logger.info(
                "Coach %s (%s) executed roster action: %s - %s",
                coach.name,
                context.trading_tier.value,
                decision.action,
                decision.reasoning,
            )
        else:
            logger.warning(
                "Coach %s failed to execute roster action: %s",
                coach.name,
                decision.action,
            )

    return decision
