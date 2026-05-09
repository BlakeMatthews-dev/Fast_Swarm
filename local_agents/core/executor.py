"""
Agent Executor - Solo Trading Life Orchestration.

The Agent Executor is the core of an agent's life BEFORE they join a committee.
Each agent trades SOLO, building experience and proving themselves through:

LIFECYCLE:
    BIRTH --> SOLO TRADING --> CRUCIBLE --> ROSTER SELECTION --> COMMITTEE

This module handles the SOLO TRADING phase where agents:
1. Receive candle data individually
2. Evaluate their patterns against market data
3. Apply personality traits to decisions
4. Make individual trading decisions (3-zone system)
5. Build episodic memories from trades
6. Consolidate memories into wisdom over time
7. Build track record (fitness/ELO) for Crucible qualification
"""

import logging
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from Fast_Swarm.local_agents.backtest.pattern_matcher import PatternMatcher
from Fast_Swarm.local_agents.core.decision import (
    DecisionZone,
    PatternAITracker,
    TradeDecisionResult,
    determine_zone,
)
from Fast_Swarm.local_agents.core.memory import (
    create_memory,
)
from Fast_Swarm.local_agents.core.state import AgentDatabase, AgentRecord, TradeRecord
from Fast_Swarm.local_agents.core.traits import (
    AgentTraits,
    calculate_position_size,
    calculate_stop_loss_distance,
    calculate_take_profit_distance,
)
from Fast_Swarm.local_agents.shared.llm_client import AIZoneHandler, AIZoneMode

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Constants
# =============================================================================


class AgentState(Enum):
    """Agent trading state."""

    IDLE = "idle"  # No position, looking for entry
    IN_POSITION = "position"  # In a trade, monitoring for exit
    PAUSED = "paused"  # Temporarily inactive
    DEAD = "dead"  # Fitness below survival threshold


class TradeOutcome(Enum):
    """Trade outcome types."""

    WIN = "win"  # Positive PnL
    LOSS = "loss"  # Negative PnL
    BREAKEVEN = "even"  # Near-zero PnL (-0.1% to 0.1%)


# Crucible qualification thresholds
CRUCIBLE_MIN_TRADES = 50  # Minimum trades to qualify
CRUCIBLE_MIN_FITNESS = 50.0  # Minimum fitness score
CRUCIBLE_MIN_WIN_RATE = 0.45  # Minimum win rate

# Fitness thresholds
FITNESS_SURVIVAL_THRESHOLD = 40.0  # Below this = DEAD
FITNESS_PROMOTION_THRESHOLD = 80.0  # Above this = eligible for promotion


# =============================================================================
# Position Tracking
# =============================================================================


@dataclass
class Position:
    """Current position state."""

    pattern_id: str
    asset: str
    direction: str  # "long" or "short"
    entry_price: float
    entry_timestamp: int
    entry_confidence: float
    decision_zone: DecisionZone
    ai_consulted: bool = False
    position_size_pct: float = 1.0
    stop_loss_price: float = 0.0
    take_profit_price: float = 0.0
    # Pattern exit conditions (indicator-based)
    exit_conditions: dict | None = None
    mfe: float = 0.0  # Maximum Favorable Excursion (best unrealized)
    mae: float = 0.0  # Maximum Adverse Excursion (worst unrealized)
    candles_held: int = 0  # Track for pattern conditions that use it


@dataclass
class TradeResult:
    """Completed trade result."""

    trade_id: str
    pattern_id: str
    asset: str
    direction: str
    entry_price: float
    exit_price: float
    entry_timestamp: int
    exit_timestamp: int
    pnl_pct: float
    mfe_pct: float
    mae_pct: float
    position_size_pct: float
    entry_confidence: float
    decision_zone: DecisionZone
    exit_reason: str  # "stop_loss", "take_profit", "condition", "max_hold"
    ai_consulted: bool = False
    outcome: TradeOutcome = TradeOutcome.LOSS


# =============================================================================
# Agent Performance Metrics
# =============================================================================


@dataclass
class AgentMetrics:
    """Accumulated agent performance metrics."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    peak_equity: float = 100.0  # Starting with 100%
    current_equity: float = 100.0
    sharpe_numerator: float = 0.0  # Sum of returns for Sharpe
    sharpe_denominator: float = 0.0  # Sum of squared returns
    consecutive_losses: int = 0
    max_consecutive_losses: int = 0
    ai_consultations: int = 0

    @property
    def win_rate(self) -> float:
        """Calculate win rate."""
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    @property
    def avg_pnl(self) -> float:
        """Calculate average PnL per trade."""
        if self.total_trades == 0:
            return 0.0
        return self.total_pnl_pct / self.total_trades

    @property
    def profit_factor(self) -> float:
        """Calculate profit factor (gross profit / gross loss)."""
        # Simplified - would need separate tracking for accuracy
        if self.losing_trades == 0:
            return 10.0 if self.winning_trades > 0 else 0.0
        if self.winning_trades == 0:
            return 0.0
        return self.winning_trades / self.losing_trades

    def calculate_fitness(self) -> float:
        """
        Calculate overall fitness score (0-100).

        Components:
        - ROI contribution (40%)
        - Win rate contribution (30%)
        - Drawdown penalty (20%)
        - Consistency bonus (10%)
        """
        if self.total_trades < 5:
            return 50.0  # Neutral until enough trades

        # ROI component (0-40 points)
        # Map -50% to +100% to 0-40 points
        roi_normalized = max(-0.5, min(1.0, self.total_pnl_pct / 100))
        roi_score = (roi_normalized + 0.5) / 1.5 * 40

        # Win rate component (0-30 points)
        win_rate_score = self.win_rate * 30

        # Drawdown penalty (0-20 points, higher = worse)
        # Max drawdown of 0% = 20 points, 50%+ = 0 points
        dd_normalized = min(1.0, self.max_drawdown_pct / 50)
        dd_score = (1 - dd_normalized) * 20

        # Consistency bonus (0-10 points)
        # Penalize consecutive losses
        consistency = max(0, 10 - self.max_consecutive_losses)

        fitness = roi_score + win_rate_score + dd_score + consistency
        return max(0, min(100, fitness))


# =============================================================================
# Agent Executor
# =============================================================================


class AgentExecutor:
    """
    Executes an agent's solo trading life.

    This is where agents PROVE themselves before ever joining a committee.
    The executor:
    - Processes candles and generates signals
    - Manages positions (entry/exit)
    - Records trades and outcomes
    - Builds memories from experience
    - Tracks fitness for Crucible qualification

    Usage:
        executor = AgentExecutor(
            agent_record=agent,
            patterns={pid: pattern_dict for pid in agent.pattern_ids},
            db=agent_database,
        )

        # Feed candles (streaming or batch)
        for candle in candle_stream:
            result = executor.process_candle(candle)
            if result:
                print(f"Trade completed: {result.pnl_pct}%")

        # Check if ready for Crucible
        if executor.qualifies_for_crucible():
            crucible.enqueue(executor.agent_record)
    """

    def __init__(
        self,
        agent_record: AgentRecord,
        patterns: dict[str, dict],
        db: AgentDatabase | None = None,
        ai_mode: AIZoneMode = AIZoneMode.UNIFIED,
        ai_zone_handler: AIZoneHandler | None = None,
    ):
        """
        Initialize agent executor.

        Args:
            agent_record: Agent database record.
            patterns: Dict of pattern_id -> pattern dict (with entry_conditions).
            db: Optional database for persistence.
            ai_mode: How to handle AI zone decisions (SKIP, HEURISTIC, LLM, UNIFIED).
            ai_zone_handler: Optional pre-configured AIZoneHandler.
        """
        self.agent = agent_record
        self.patterns = patterns
        self.db = db

        # Reconstruct traits from dict
        self.traits = (
            AgentTraits(**agent_record.traits) if isinstance(agent_record.traits, dict) else agent_record.traits
        )

        # AI zone handler - uses entry_aggression trait by default (HEURISTIC)
        if ai_zone_handler:
            self.ai_zone_handler = ai_zone_handler
        else:
            self.ai_zone_handler = AIZoneHandler(mode=ai_mode)

        # Trading parameters from traits
        self.position_size = calculate_position_size(self.traits.risk_tolerance)
        self.stop_loss_dist = calculate_stop_loss_distance(self.traits.stop_loss_tightness)
        self.take_profit_dist = calculate_take_profit_distance(self.traits.profit_target_greed)
        # NOTE: max_hold removed as primary exit - use pattern exit_conditions instead

        # State
        self.state = AgentState.IDLE
        self.current_position: Position | None = None
        self.metrics = AgentMetrics()
        self.trade_history: list[TradeResult] = []

        # Pattern matchers (lazy initialized)
        self._matchers: dict[str, PatternMatcher] = {}

        # AI tracking
        self.ai_tracker = PatternAITracker()

        # Current candle for decision context
        self._current_candle: dict | None = None
        self._current_indicators: dict[str, float] | None = None

        logger.info(f"[AgentExecutor] Initialized {agent_record.agent_name} with {len(patterns)} patterns")

    # =========================================================================
    # Pattern Matching
    # =========================================================================

    def _get_matcher(self, pattern_id: str) -> PatternMatcher | None:
        """Get or create pattern matcher for a pattern."""
        if pattern_id in self._matchers:
            return self._matchers[pattern_id]

        pattern = self.patterns.get(pattern_id)
        if not pattern:
            return None

        # Get entry conditions - support various formats
        entry_conditions = pattern.get("entry_conditions", pattern.get("conditions", {}))
        if not entry_conditions:
            return None

        # Convert list format to dict if needed
        if isinstance(entry_conditions, list):
            # List of condition dicts: [{indicator, operator, value}, ...]
            entry_dict = {}
            for cond in entry_conditions:
                indicator = cond.get("indicator")
                if indicator:
                    entry_dict[indicator] = {
                        "operator": cond.get("operator", ">"),
                        "value": cond.get("value", cond.get("threshold", 0)),
                    }
            entry_conditions = entry_dict

        matcher = PatternMatcher(
            pattern=pattern,
            entry_conditions=entry_conditions,
            exit_conditions=pattern.get("exit_conditions", {}),
            direction=pattern.get("direction", "long"),
            min_confidence=self.traits.min_threshold,
        )

        self._matchers[pattern_id] = matcher
        return matcher

    def _evaluate_patterns(self, indicators: dict[str, float]) -> list[tuple]:
        """
        Evaluate all agent patterns against current indicators.

        Returns:
            List of (pattern_id, match_result, confidence) for matching patterns.
        """
        matches = []

        for pattern_id in self.agent.pattern_ids:
            matcher = self._get_matcher(pattern_id)
            if not matcher:
                continue

            result = matcher.check_entry(indicators)
            if result.matched and result.confidence >= self.traits.min_threshold:
                matches.append((pattern_id, result, result.confidence))

        # Sort by confidence descending
        matches.sort(key=lambda x: x[2], reverse=True)
        return matches

    # =========================================================================
    # Decision Making
    # =========================================================================

    def _select_best_signal(self, matches: list[tuple]) -> tuple | None:
        """
        Select best signal based on agent personality.

        Considers:
        - Pattern weights (from agent's experience)
        - Confidence scores
        - Trait-based preferences

        Returns:
            (pattern_id, match_result) or None.
        """
        if not matches:
            return None

        # Apply pattern weights if available
        weighted_matches = []
        for pattern_id, result, confidence in matches:
            weight = self.agent.pattern_weights.get(pattern_id, 1.0)
            score = confidence * weight
            weighted_matches.append((score, pattern_id, result))

        # Sort by weighted score
        weighted_matches.sort(reverse=True)

        # Take best match
        _, pattern_id, result = weighted_matches[0]
        return (pattern_id, result)

    def _make_entry_decision(
        self,
        pattern_id: str,
        confidence: float,
        indicators: dict[str, float],
    ) -> TradeDecisionResult:
        """
        Make entry decision using 3-zone system with AI zone handler.

        Zones:
        - SKIP: confidence < min_threshold -> don't trade
        - AI_REFLECT: min_threshold <= confidence < ai_threshold -> consult AI
        - EXECUTE: confidence >= ai_threshold -> auto trade

        Returns:
            TradeDecisionResult with zone and decision.
        """
        pattern = self.patterns.get(pattern_id, {})
        pattern_name = pattern.get("name", pattern_id)

        # Determine which zone we're in
        zone_result = determine_zone(confidence, self.traits)

        if zone_result.zone == DecisionZone.SKIP:
            return TradeDecisionResult(
                zone=DecisionZone.SKIP,
                should_trade=False,
                confidence=confidence,
                ai_consulted=False,
                reasoning=f"Confidence {confidence:.2f} below min threshold {self.traits.min_threshold:.2f}",
            )

        if zone_result.zone == DecisionZone.EXECUTE:
            return TradeDecisionResult(
                zone=DecisionZone.EXECUTE,
                should_trade=True,
                confidence=confidence,
                ai_consulted=False,
                reasoning=f"Confidence {confidence:.2f} above AI threshold - auto execute",
            )

        # AI_REFLECT zone - use AIZoneHandler
        traits_dict = {
            "risk_tolerance": self.traits.risk_tolerance,
            "entry_aggression": self.traits.entry_aggression,
            "volatility_seeking": self.traits.volatility_seeking,
        }

        should_trade, reasoning, ai_consulted = self.ai_zone_handler.decide(
            confidence=confidence,
            pattern_name=pattern_name,
            indicators=indicators,
            traits=traits_dict,
            recent_trades=None,  # Could pass trade history here
        )

        # Track AI consultation
        ai_decision = "TAKE" if should_trade else "SKIP"
        self.ai_tracker.record_decision(
            pattern_id=pattern_id,
            ai_consulted=ai_consulted,
            ai_decision=ai_decision,
        )

        if ai_consulted:
            self.metrics.ai_consultations += 1

        return TradeDecisionResult(
            zone=DecisionZone.AI_REFLECT,
            should_trade=should_trade,
            confidence=confidence,
            ai_consulted=ai_consulted,
            ai_decision=ai_decision,
            reasoning=reasoning,
        )

    # =========================================================================
    # Position Management
    # =========================================================================

    def _open_position(
        self,
        pattern_id: str,
        asset: str,
        current_price: float,
        timestamp: int,
        confidence: float,
        decision: TradeDecisionResult,
    ) -> Position:
        """Open a new position."""
        pattern = self.patterns.get(pattern_id, {})
        direction = pattern.get("direction", "long")

        # Calculate stops based on traits
        if direction == "long":
            stop_loss_price = current_price * (1 - self.stop_loss_dist)
            take_profit_price = current_price * (1 + self.take_profit_dist)
        else:
            stop_loss_price = current_price * (1 + self.stop_loss_dist)
            take_profit_price = current_price * (1 - self.take_profit_dist)

        # Get exit conditions from pattern (indicator-based exits)
        exit_conditions = pattern.get("exit_conditions", {})

        position = Position(
            pattern_id=pattern_id,
            asset=asset,
            direction=direction,
            entry_price=current_price,
            entry_timestamp=timestamp,
            entry_confidence=confidence,
            decision_zone=decision.zone,
            ai_consulted=decision.ai_consulted,
            position_size_pct=self.position_size * 100,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            exit_conditions=exit_conditions,  # Pattern-specific exit rules
        )

        self.current_position = position
        self.state = AgentState.IN_POSITION

        logger.debug(f"[AgentExecutor] {self.agent.agent_name} opened {direction} @ {current_price}")
        return position

    def _close_position(
        self,
        exit_price: float,
        exit_timestamp: int,
        exit_reason: str,
    ) -> TradeResult:
        """Close current position and record trade."""
        pos = self.current_position
        if not pos:
            raise ValueError("No position to close")

        # Calculate PnL
        if pos.direction == "long":
            pnl_pct = ((exit_price - pos.entry_price) / pos.entry_price) * 100
        else:
            pnl_pct = ((pos.entry_price - exit_price) / pos.entry_price) * 100

        # Determine outcome
        if pnl_pct > 0.1:
            outcome = TradeOutcome.WIN
        elif pnl_pct < -0.1:
            outcome = TradeOutcome.LOSS
        else:
            outcome = TradeOutcome.BREAKEVEN

        result = TradeResult(
            trade_id=str(uuid.uuid4()),
            pattern_id=pos.pattern_id,
            asset=pos.asset,
            direction=pos.direction,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            entry_timestamp=pos.entry_timestamp,
            exit_timestamp=exit_timestamp,
            pnl_pct=pnl_pct,
            mfe_pct=pos.mfe,
            mae_pct=pos.mae,
            position_size_pct=pos.position_size_pct,
            entry_confidence=pos.entry_confidence,
            decision_zone=pos.decision_zone,
            exit_reason=exit_reason,
            ai_consulted=pos.ai_consulted,
            outcome=outcome,
        )

        # Update metrics
        self._update_metrics(result)

        # Record to database
        self._record_trade(result)

        # Create memory from trade
        self._create_trade_memory(result)

        # Reset state
        self.trade_history.append(result)
        self.current_position = None
        self.state = AgentState.IDLE

        logger.debug(
            f"[AgentExecutor] {self.agent.agent_name} closed {pos.direction} "
            f"@ {exit_price} ({exit_reason}) PnL: {pnl_pct:.2f}%"
        )

        return result

    def _check_exit_conditions(
        self,
        current_price: float,
        timestamp: int,
        indicators: dict[str, float],
    ) -> tuple | None:
        """
        Check if position should be exited.

        Exit priority:
        1. Stop loss (trait-based, protects capital)
        2. Take profit (trait-based)
        3. Pattern exit conditions (indicator-based, from pattern definition)

        NOTE: max_hold removed - use pattern exit_conditions for time-based exits.

        Returns:
            (should_exit, reason) or None.
        """
        pos = self.current_position
        if not pos:
            return None

        # Track candles held
        pos.candles_held += 1

        # Update MFE/MAE
        if pos.direction == "long":
            unrealized_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100
        else:
            unrealized_pct = ((pos.entry_price - current_price) / pos.entry_price) * 100

        pos.mfe = max(pos.mfe, unrealized_pct)
        pos.mae = min(pos.mae, unrealized_pct)

        # Check stop loss (trait-based, always active)
        if (pos.direction == "long" and current_price <= pos.stop_loss_price) or (
            pos.direction == "short" and current_price >= pos.stop_loss_price
        ):
            return (True, "stop_loss")

        # Check take profit (trait-based)
        if (pos.direction == "long" and current_price >= pos.take_profit_price) or (
            pos.direction == "short" and current_price <= pos.take_profit_price
        ):
            return (True, "take_profit")

        # Check pattern exit conditions (indicator-based exits from pattern definition)
        if pos.exit_conditions:
            from Fast_Swarm.local_agents.backtest.pattern_matcher import evaluate_conditions

            # Skip if exit_conditions is just stop_loss/take_profit params (already handled above)
            # Support both key formats:
            # - Legacy: stop_loss_pct, take_profit_pct, max_hold_periods
            # - New: stop_loss, take_profit, timeout_bars
            param_keys = [
                "stop_loss_pct",
                "take_profit_pct",
                "max_hold_periods",  # Legacy
                "stop_loss",
                "take_profit",
                "timeout_bars",  # New format
            ]
            if not any(k in pos.exit_conditions for k in param_keys):
                exit_result = evaluate_conditions(pos.exit_conditions, indicators)
                if exit_result.matched:
                    return (True, "condition")

        # Also try matcher for more complex exit logic
        matcher = self._get_matcher(pos.pattern_id)
        if matcher and matcher.exit_conditions:
            exit_result = matcher.check_exit(indicators)
            if exit_result.matched:
                return (True, "condition")

        return None

    # =========================================================================
    # Metrics and Learning
    # =========================================================================

    def _update_metrics(self, trade: TradeResult):
        """Update agent metrics after a trade."""
        self.metrics.total_trades += 1
        self.metrics.total_pnl_pct += trade.pnl_pct

        if trade.outcome == TradeOutcome.WIN:
            self.metrics.winning_trades += 1
            self.metrics.consecutive_losses = 0
        elif trade.outcome == TradeOutcome.LOSS:
            self.metrics.losing_trades += 1
            self.metrics.consecutive_losses += 1
            self.metrics.max_consecutive_losses = max(
                self.metrics.max_consecutive_losses, self.metrics.consecutive_losses
            )

        # Update equity curve
        self.metrics.current_equity *= 1 + trade.pnl_pct / 100
        self.metrics.peak_equity = max(self.metrics.peak_equity, self.metrics.current_equity)

        # Calculate drawdown
        drawdown = (self.metrics.peak_equity - self.metrics.current_equity) / self.metrics.peak_equity * 100
        self.metrics.max_drawdown_pct = max(self.metrics.max_drawdown_pct, drawdown)

        # Update pattern weight based on outcome
        self._update_pattern_weight(trade)

        # Track AI outcome for pattern
        self.ai_tracker.record_trade_outcome(trade.pattern_id, trade.pnl_pct)

        # Check if agent should die
        fitness = self.metrics.calculate_fitness()
        if fitness < FITNESS_SURVIVAL_THRESHOLD and self.metrics.total_trades >= 20:
            self.state = AgentState.DEAD
            logger.warning(f"[AgentExecutor] {self.agent.agent_name} DIED (fitness: {fitness:.1f})")

    def _update_pattern_weight(self, trade: TradeResult):
        """Adjust pattern weight based on trade outcome."""
        pattern_id = trade.pattern_id
        current_weight = self.agent.pattern_weights.get(pattern_id, 1.0)

        # Increase weight for wins, decrease for losses
        if trade.outcome == TradeOutcome.WIN:
            new_weight = min(2.0, current_weight * 1.05)  # +5% per win
        elif trade.outcome == TradeOutcome.LOSS:
            new_weight = max(0.1, current_weight * 0.95)  # -5% per loss
        else:
            new_weight = current_weight

        self.agent.pattern_weights[pattern_id] = new_weight

    def _record_trade(self, trade: TradeResult):
        """Record trade to database."""
        if not self.db:
            return

        record = TradeRecord(
            trade_id=trade.trade_id,
            agent_id=self.agent.agent_id,
            pattern_id=trade.pattern_id,
            asset=trade.asset,
            direction=trade.direction,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            entry_timestamp=trade.entry_timestamp,
            exit_timestamp=trade.exit_timestamp,
            pnl_pct=trade.pnl_pct,
            mfe_pct=trade.mfe_pct,
            mae_pct=trade.mae_pct,
            position_size_pct=trade.position_size_pct,
            entry_confidence=trade.entry_confidence,
            decision_zone=trade.decision_zone.value,
            ai_consulted=trade.ai_consulted,
            created_at=int(time.time() * 1000),
        )

        try:
            self.db.create_trade(record)
        except Exception as e:
            logger.error(f"[AgentExecutor] Failed to record trade: {e}")

    def _create_trade_memory(self, trade: TradeResult):
        """Create episodic memory from trade."""
        pattern = self.patterns.get(trade.pattern_id, {})
        pattern_name = pattern.get("name", trade.pattern_id)

        # Determine memory type based on outcome
        if trade.outcome == TradeOutcome.WIN and trade.pnl_pct > 5.0:
            # Strong win -> affirmation
            memory_type = "affirmation"
            content = (
                f"Pattern '{pattern_name}' works well in {trade.asset}. "
                f"Entry at confidence {trade.entry_confidence:.2f} led to {trade.pnl_pct:.1f}% gain."
            )
            weight = 0.7
        elif trade.outcome == TradeOutcome.LOSS and trade.pnl_pct < -5.0:
            # Strong loss -> regret
            memory_type = "regret"
            content = (
                f"Pattern '{pattern_name}' failed in {trade.asset}. "
                f"Lost {abs(trade.pnl_pct):.1f}% despite {trade.entry_confidence:.2f} confidence. "
                f"Exit: {trade.exit_reason}."
            )
            weight = 0.8
        elif trade.outcome == TradeOutcome.WIN:
            # Normal win -> lesson
            memory_type = "lesson"
            content = f"Pattern '{pattern_name}' profitable in {trade.asset}: +{trade.pnl_pct:.1f}%"
            weight = 0.6
        elif trade.outcome == TradeOutcome.LOSS:
            # Normal loss -> lesson
            memory_type = "lesson"
            content = f"Pattern '{pattern_name}' lost in {trade.asset}: {trade.pnl_pct:.1f}%"
            weight = 0.5
        else:
            # Breakeven -> observation
            memory_type = "observation"
            content = f"Pattern '{pattern_name}' breakeven in {trade.asset}"
            weight = 0.3

        context = {
            "trade_id": trade.trade_id,
            "pattern_id": trade.pattern_id,
            "asset": trade.asset,
            "pnl_pct": trade.pnl_pct,
            "entry_confidence": trade.entry_confidence,
            "decision_zone": trade.decision_zone.value,
            "exit_reason": trade.exit_reason,
        }

        try:
            memory = create_memory(
                agent_id=self.agent.agent_id,
                memory_type=memory_type,
                content=content,
                weight=weight,
                linked_trade_ids=[trade.trade_id],
                context_snapshot=context,
            )

            # Persist to database if available
            if self.db:
                self.db.create_memory(memory)

        except Exception as e:
            logger.error(f"[AgentExecutor] Failed to create memory: {e}")

    # =========================================================================
    # Main Processing Loop
    # =========================================================================

    def process_candle(
        self,
        candle: dict[str, Any],
        indicators: dict[str, float],
        asset: str = "BTC",
    ) -> TradeResult | None:
        """
        Process a single candle and indicators.

        This is the main entry point for the agent's trading loop.
        Call this for each new candle in the data stream.

        Args:
            candle: OHLCV candle dict with 'open', 'high', 'low', 'close', 'volume', 'timestamp'.
            indicators: Pre-computed indicator values dict.
            asset: Asset symbol.

        Returns:
            TradeResult if a trade was closed, None otherwise.
        """
        if self.state == AgentState.DEAD:
            return None

        self._current_candle = candle
        self._current_indicators = indicators

        timestamp = candle.get("timestamp", int(time.time() * 1000))
        current_price = candle.get("close", 0)

        # If in position, check exit conditions
        if self.state == AgentState.IN_POSITION and self.current_position:
            exit_check = self._check_exit_conditions(current_price, timestamp, indicators)
            if exit_check:
                should_exit, reason = exit_check
                if should_exit:
                    return self._close_position(current_price, timestamp, reason)

        # If idle, look for entry signals
        if self.state == AgentState.IDLE:
            # Evaluate all patterns
            matches = self._evaluate_patterns(indicators)

            if matches:
                # Select best signal
                best = self._select_best_signal(matches)
                if best:
                    pattern_id, match_result = best

                    # Make entry decision via 3-zone system
                    decision = self._make_entry_decision(
                        pattern_id=pattern_id,
                        confidence=match_result.confidence,
                        indicators=indicators,
                    )

                    # Only trade if decision says yes
                    if decision.should_trade:
                        self._open_position(
                            pattern_id=pattern_id,
                            asset=asset,
                            current_price=current_price,
                            timestamp=timestamp,
                            confidence=match_result.confidence,
                            decision=decision,
                        )

        return None

    # =========================================================================
    # Crucible Qualification
    # =========================================================================

    def qualifies_for_crucible(self) -> bool:
        """
        Check if agent qualifies for Crucible entry.

        Requirements:
        - Minimum number of trades
        - Minimum fitness score
        - Minimum win rate
        - Not dead
        """
        if self.state == AgentState.DEAD:
            return False

        if self.metrics.total_trades < CRUCIBLE_MIN_TRADES:
            return False

        fitness = self.metrics.calculate_fitness()
        if fitness < CRUCIBLE_MIN_FITNESS:
            return False

        if self.metrics.win_rate < CRUCIBLE_MIN_WIN_RATE:
            return False

        return True

    def get_crucible_stats(self) -> dict:
        """Get stats for Crucible evaluation."""
        fitness = self.metrics.calculate_fitness()

        return {
            "agent_id": self.agent.agent_id,
            "agent_name": self.agent.agent_name,
            "generation": self.agent.generation,
            "total_trades": self.metrics.total_trades,
            "win_rate": self.metrics.win_rate,
            "total_pnl_pct": self.metrics.total_pnl_pct,
            "max_drawdown_pct": self.metrics.max_drawdown_pct,
            "fitness": fitness,
            "qualifies": self.qualifies_for_crucible(),
            "patterns_used": len(self.agent.pattern_ids),
            "ai_consultations": self.metrics.ai_consultations,
            "ai_dependency": self.ai_tracker.get_summary().get("global_consultation_rate", 0),
        }

    # =========================================================================
    # Persistence
    # =========================================================================

    def sync_to_database(self):
        """Sync current state to database."""
        if not self.db:
            return

        fitness = self.metrics.calculate_fitness()

        try:
            self.db.update_agent_fitness(
                agent_id=self.agent.agent_id,
                fitness=fitness,
                backtest_count=self.metrics.total_trades,
            )

            if self.state == AgentState.DEAD:
                self.db.update_agent_status(self.agent.agent_id, "dead")

        except Exception as e:
            logger.error(f"[AgentExecutor] Failed to sync to database: {e}")


# =============================================================================
# Batch Execution Helper
# =============================================================================


def run_agent_backtest(
    agent_record: AgentRecord,
    patterns: dict[str, dict],
    candles: list[dict],
    indicators_list: list[dict[str, float]],
    asset: str = "BTC",
    db: AgentDatabase | None = None,
    ai_mode: AIZoneMode = AIZoneMode.UNIFIED,
) -> AgentExecutor:
    """
    Run a full backtest for an agent.

    Args:
        agent_record: Agent to test.
        patterns: Dict of pattern_id -> pattern dict.
        candles: List of OHLCV candles.
        indicators_list: List of indicator dicts (one per candle).
        asset: Asset symbol.
        db: Optional database for persistence.
        ai_mode: AI zone mode (UNIFIED uses ML layer for decisions).

    Returns:
        AgentExecutor with results.
    """
    executor = AgentExecutor(
        agent_record=agent_record,
        patterns=patterns,
        db=db,
        ai_mode=ai_mode,
    )

    for candle, indicators in zip(candles, indicators_list, strict=False):
        executor.process_candle(candle, indicators, asset)

        if executor.state == AgentState.DEAD:
            break

    # Close any open position at the end
    if executor.current_position and candles:
        last_candle = candles[-1]
        executor._close_position(
            exit_price=last_candle.get("close", 0),
            exit_timestamp=last_candle.get("timestamp", int(time.time() * 1000)),
            exit_reason="backtest_end",
        )

    # Sync final state
    executor.sync_to_database()

    return executor
