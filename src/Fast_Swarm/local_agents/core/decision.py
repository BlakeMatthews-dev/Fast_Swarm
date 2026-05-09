"""
Decision Zone System - V3 Parity.

3-Zone System:
- SKIP: confidence < min_threshold (no trade)
- AI_REFLECT: min_threshold <= confidence < ai_threshold (consult LLM)
- EXECUTE: confidence >= ai_threshold (auto trade)

AI Zone Modes:
- SKIP: Treat AI_REFLECT as SKIP (fast backtesting)
- LLM: Real Ollama calls (live trading)

Note: SIMULATE mode removed per user feedback - left undecided.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

# =============================================================================
# Enums
# =============================================================================


class DecisionZone(Enum):
    """Decision zone types."""

    SKIP = "skip"
    AI_REFLECT = "reflect"
    EXECUTE = "execute"


class AIZoneMode(Enum):
    """AI zone handling modes."""

    SKIP = "skip"  # Treat as SKIP (fast backtesting)
    LLM = "llm"  # Real LLM calls (live trading)
    # SIMULATE mode removed - undecided


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ZoneDecision:
    """Result of zone determination."""

    zone: DecisionZone
    confidence: float
    min_threshold: float
    ai_threshold: float


@dataclass
class AIZoneResult:
    """Result of AI zone handling."""

    action: str  # "skip", "consult_llm"
    trade_decision: bool = False
    requires_llm: bool = False
    reasoning: str | None = None


@dataclass
class LLMDecisionResult:
    """Result of LLM decision parsing."""

    trade_decision: bool
    reasoning: str | None = None
    raw_response: dict | None = None


@dataclass
class TradeDecisionResult:
    """Full trade decision result."""

    zone: DecisionZone
    should_trade: bool
    confidence: float
    reasoning: str | None = None
    ai_consulted: bool = False
    ai_decision: str | None = None


# =============================================================================
# Zone Determination
# =============================================================================


def determine_zone(confidence: float, traits: Any) -> ZoneDecision:
    """
    Determine which decision zone the confidence falls into.

    Args:
        confidence: Pattern confidence score (0-1).
        traits: Agent traits with min_threshold and ai_threshold.

    Returns:
        ZoneDecision with zone and thresholds.
    """
    min_threshold = getattr(traits, "min_threshold", 0.35)
    ai_threshold = getattr(traits, "ai_threshold", 0.65)

    # Handle inverted thresholds gracefully
    if min_threshold > ai_threshold:
        min_threshold, ai_threshold = ai_threshold, min_threshold

    # Determine zone
    if confidence < min_threshold:
        zone = DecisionZone.SKIP
    elif confidence >= ai_threshold:
        zone = DecisionZone.EXECUTE
    else:
        zone = DecisionZone.AI_REFLECT

    return ZoneDecision(
        zone=zone,
        confidence=confidence,
        min_threshold=min_threshold,
        ai_threshold=ai_threshold,
    )


# =============================================================================
# AI Zone Handling
# =============================================================================


def handle_ai_zone(
    confidence: float,
    traits: Any,
    mode: AIZoneMode = AIZoneMode.SKIP,
) -> AIZoneResult:
    """
    Handle decision in AI zone.

    Args:
        confidence: Pattern confidence.
        traits: Agent traits.
        mode: How to handle AI zone.

    Returns:
        AIZoneResult with action to take.
    """
    if mode == AIZoneMode.SKIP:
        return AIZoneResult(
            action="skip",
            trade_decision=False,
            requires_llm=False,
        )
    elif mode == AIZoneMode.LLM:
        return AIZoneResult(
            action="consult_llm",
            trade_decision=False,  # TBD after LLM call
            requires_llm=True,
        )

    # Default to skip
    return AIZoneResult(action="skip", trade_decision=False)


# =============================================================================
# AI Decision Context
# =============================================================================


def build_ai_decision_context(
    confidence: float,
    traits: Any,
    pattern_id: str,
    indicators: dict,
    pattern_name: str | None = None,
) -> dict:
    """
    Build context for AI decision.

    Args:
        confidence: Pattern confidence.
        traits: Agent traits.
        pattern_id: Pattern being evaluated.
        indicators: Current indicator values.
        pattern_name: Optional pattern name.

    Returns:
        Context dict for LLM prompt.
    """
    # Extract relevant traits
    trait_dict = {}
    trait_names = [
        "risk_tolerance",
        "entry_aggression",
        "volatility_seeking",
        "profit_target_greed",
        "hold_duration_bias",
    ]
    for name in trait_names:
        if hasattr(traits, name):
            trait_dict[name] = getattr(traits, name)

    return {
        "confidence": confidence,
        "pattern_id": pattern_id,
        "pattern_name": pattern_name,
        "indicators": indicators,
        "traits": trait_dict,
    }


# =============================================================================
# LLM Decision Parsing
# =============================================================================


def parse_llm_decision(response: dict | None) -> LLMDecisionResult:
    """
    Parse LLM response into decision.

    Expected format:
    {
        "decision": "TAKE" or "SKIP",
        "reasoning": "..."
    }

    Args:
        response: LLM response dict.

    Returns:
        LLMDecisionResult with trade decision.
    """
    if response is None:
        return LLMDecisionResult(trade_decision=False, reasoning="No response")

    if not isinstance(response, dict):
        return LLMDecisionResult(trade_decision=False, reasoning="Invalid response format")

    decision = response.get("decision", "").lower()
    reasoning = response.get("reasoning", "")

    if decision == "take":
        return LLMDecisionResult(
            trade_decision=True,
            reasoning=reasoning,
            raw_response=response,
        )
    else:
        # Default to SKIP for any other value (safe)
        return LLMDecisionResult(
            trade_decision=False,
            reasoning=reasoning,
            raw_response=response,
        )


# =============================================================================
# Decision Tracking
# =============================================================================


@dataclass
class PatternAIStats:
    """Track AI consultation statistics per pattern.

    Used for selection pressure: patterns that need AI help often are weaker.
    """

    pattern_id: str
    total_decisions: int = 0  # Total times pattern was evaluated
    ai_consultations: int = 0  # Times AI was consulted
    ai_took: int = 0  # AI decided TAKE
    ai_skipped: int = 0  # AI decided SKIP
    profitable_trades: int = 0  # Trades with positive PnL
    unprofitable_trades: int = 0  # Trades with negative PnL

    @property
    def consultation_rate(self) -> float:
        """Rate of AI consultations (0-1). Higher = more uncertain pattern."""
        if self.total_decisions == 0:
            return 0.0
        return self.ai_consultations / self.total_decisions

    @property
    def ai_take_rate(self) -> float:
        """Rate of AI TAKE decisions (0-1)."""
        if self.ai_consultations == 0:
            return 0.0
        return self.ai_took / self.ai_consultations

    @property
    def self_sufficient_rate(self) -> float:
        """Rate of decisions NOT needing AI (0-1). Higher = stronger pattern."""
        return 1.0 - self.consultation_rate


class PatternAITracker:
    """
    Track AI consultations across all patterns during backtesting.

    Enables selection pressure: patterns with high AI dependency get fitness penalty.

    Usage:
        tracker = PatternAITracker()

        # During backtest, for each trade decision:
        tracker.record_decision(pattern_id, ai_consulted=True, ai_decision="TAKE")

        # After backtest, get fitness penalty:
        penalty = tracker.get_fitness_penalty(pattern_id)
        adjusted_fitness = base_fitness - penalty
    """

    def __init__(self, penalty_weight: float = 15.0):
        """
        Initialize pattern AI tracker.

        Args:
            penalty_weight: Maximum fitness penalty for 100% AI consultation rate.
                           Default 15 means a pattern needing AI every time loses 15 fitness.
        """
        self._pattern_stats: dict[str, PatternAIStats] = {}
        self.penalty_weight = penalty_weight

    def record_decision(
        self,
        pattern_id: str,
        ai_consulted: bool,
        ai_decision: str | None = None,
        was_profitable: bool | None = None,
    ):
        """
        Record a trading decision for a pattern.

        Args:
            pattern_id: Pattern that triggered the decision.
            ai_consulted: Whether AI was consulted.
            ai_decision: AI decision if consulted ("TAKE" or "SKIP").
            was_profitable: Trade outcome if known (for later correlation).
        """
        if pattern_id not in self._pattern_stats:
            self._pattern_stats[pattern_id] = PatternAIStats(pattern_id=pattern_id)

        stats = self._pattern_stats[pattern_id]
        stats.total_decisions += 1

        if ai_consulted:
            stats.ai_consultations += 1
            if ai_decision:
                if ai_decision.upper() == "TAKE":
                    stats.ai_took += 1
                else:
                    stats.ai_skipped += 1

        if was_profitable is not None:
            if was_profitable:
                stats.profitable_trades += 1
            else:
                stats.unprofitable_trades += 1

    def record_trade_outcome(self, pattern_id: str, pnl_pct: float):
        """Record outcome of a trade for later correlation analysis."""
        if pattern_id not in self._pattern_stats:
            return

        stats = self._pattern_stats[pattern_id]
        if pnl_pct > 0:
            stats.profitable_trades += 1
        else:
            stats.unprofitable_trades += 1

    def get_stats(self, pattern_id: str) -> PatternAIStats | None:
        """Get AI stats for a specific pattern."""
        return self._pattern_stats.get(pattern_id)

    def get_all_stats(self) -> dict[str, PatternAIStats]:
        """Get stats for all patterns."""
        return self._pattern_stats.copy()

    def get_fitness_penalty(self, pattern_id: str) -> float:
        """
        Calculate fitness penalty based on AI consultation rate.

        Selection pressure: patterns that need AI more get penalized.

        Formula:
            penalty = consultation_rate * penalty_weight

        A pattern with 50% consultation rate and penalty_weight=15 gets -7.5 fitness.

        Returns:
            Fitness penalty (0 to penalty_weight).
        """
        stats = self._pattern_stats.get(pattern_id)
        if stats is None:
            return 0.0

        return stats.consultation_rate * self.penalty_weight

    def get_summary(self) -> dict:
        """Get summary statistics across all patterns."""
        if not self._pattern_stats:
            return {
                "total_patterns": 0,
                "total_decisions": 0,
                "total_ai_consultations": 0,
                "global_consultation_rate": 0.0,
                "avg_penalty": 0.0,
            }

        total_decisions = sum(s.total_decisions for s in self._pattern_stats.values())
        total_consultations = sum(s.ai_consultations for s in self._pattern_stats.values())
        total_penalty = sum(self.get_fitness_penalty(pid) for pid in self._pattern_stats)

        return {
            "total_patterns": len(self._pattern_stats),
            "total_decisions": total_decisions,
            "total_ai_consultations": total_consultations,
            "global_consultation_rate": total_consultations / total_decisions if total_decisions > 0 else 0.0,
            "avg_penalty": total_penalty / len(self._pattern_stats) if self._pattern_stats else 0.0,
        }

    def reset(self):
        """Reset all tracking data."""
        self._pattern_stats.clear()


class TradeDecisionTracker:
    """Track AI decision outcomes for metrics."""

    def __init__(self):
        self._consultations: dict[str, bool] = {}  # trade_id -> was_correct
        self._total_consultations = 0
        self._correct_count = 0
        # Add pattern-level tracking
        self._pattern_tracker = PatternAITracker()

    @property
    def ai_consultations(self) -> int:
        """Total AI consultations."""
        return self._total_consultations

    @property
    def ai_correct(self) -> int:
        """Correct AI decisions."""
        return self._correct_count

    @property
    def ai_accuracy(self) -> float | None:
        """AI accuracy rate (0-1)."""
        if self._total_consultations == 0:
            return None
        return self._correct_count / self._total_consultations

    @property
    def pattern_tracker(self) -> PatternAITracker:
        """Access pattern-level AI tracker."""
        return self._pattern_tracker

    def record_ai_consulted(self, trade_id: str, pattern_id: str | None = None):
        """Record that AI was consulted for a trade."""
        self._consultations[trade_id] = None  # Outcome pending
        self._total_consultations += 1

        # Also record at pattern level
        if pattern_id:
            self._pattern_tracker.record_decision(pattern_id, ai_consulted=True)

    def record_ai_outcome(self, trade_id: str, was_correct: bool):
        """Record outcome of AI decision."""
        if trade_id in self._consultations:
            self._consultations[trade_id] = was_correct
            if was_correct:
                self._correct_count += 1


# =============================================================================
# Full Trade Decision
# =============================================================================


def make_trade_decision(
    confidence: float,
    traits: Any,
    pattern_id: str,
    pattern_name: str | None = None,
    indicators: dict | None = None,
    ai_mode: AIZoneMode = AIZoneMode.SKIP,
) -> TradeDecisionResult:
    """
    Make full trade decision.

    Args:
        confidence: Pattern confidence.
        traits: Agent traits.
        pattern_id: Pattern ID.
        pattern_name: Optional pattern name.
        indicators: Current indicators.
        ai_mode: How to handle AI zone.

    Returns:
        TradeDecisionResult with full decision.
    """
    # Determine zone
    zone_decision = determine_zone(confidence, traits)

    # Handle based on zone
    if zone_decision.zone == DecisionZone.SKIP:
        return TradeDecisionResult(
            zone=DecisionZone.SKIP,
            should_trade=False,
            confidence=confidence,
            reasoning="Confidence below minimum threshold",
        )

    elif zone_decision.zone == DecisionZone.EXECUTE:
        return TradeDecisionResult(
            zone=DecisionZone.EXECUTE,
            should_trade=True,
            confidence=confidence,
            reasoning="Confidence above AI threshold - auto execute",
        )

    else:  # AI_REFLECT
        ai_result = handle_ai_zone(confidence, traits, mode=ai_mode)

        if ai_result.requires_llm:
            # LLM would be called here in real implementation
            return TradeDecisionResult(
                zone=DecisionZone.AI_REFLECT,
                should_trade=False,  # Pending LLM
                confidence=confidence,
                reasoning="Awaiting AI consultation",
                ai_consulted=True,
            )
        else:
            # Skip mode - no trade
            return TradeDecisionResult(
                zone=DecisionZone.AI_REFLECT,
                should_trade=False,
                confidence=confidence,
                reasoning="AI zone treated as skip (backtest mode)",
            )
