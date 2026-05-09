"""
Bear Protection Service.

Supreme risk layer with VETO EXIT POWER over all pattern trades.
Monitors motion derivatives and enforces position limits.

UPDATED v3: Simplified to AJ (Acceleration + Jerk) - tested on 65 stocks + crypto
- Removed velocity requirement (barely improved performance)
- Looser acceleration threshold for better signal quality

DEFENSIVE (0% max) - Requires 2+ TFs showing:
    acc < -1.5 AND adx_jerk < -0.5
    (velocity removed - testing showed +9.1% vs +2.4% avg ROI improvement)

AGGRESSIVE (90% max) - Only 1 TF needed:
    vel < -0.5 AND acc > 1.5

NEUTRAL (65% max) - Default when no signals

Note: ADX jerk fails on hypergrowth assets (SOL, NVDA, AVGO) - consider
sector-specific overrides for momentum stocks in future versions.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class Regime(Enum):
    """Market regime states."""
    DEFENSIVE = "DEFENSIVE"   # Crash protection - 25% max
    NEUTRAL = "NEUTRAL"       # Normal operation - 50% max
    AGGRESSIVE = "AGGRESSIVE" # Opportunity mode - 75% max


@dataclass
class RegimeConfig:
    """Position limits by regime."""
    defensive_max: float = 0.0    # 0% - FULL EXIT in DEFENSIVE
    neutral_max: float = 0.65     # 65% max position in NEUTRAL (was 50%)
    aggressive_max: float = 0.90  # 90% max position in AGGRESSIVE (was 85%)

    # DEFENSIVE signal thresholds - AJ config (Acceleration + Jerk only)
    # Velocity removed after testing: acc+jerk outperformed vel+acc+jerk
    exit_vel_threshold: float = 1.0       # DEPRECATED - not used in v3 DEFENSIVE
    exit_acc_threshold: float = -1.5      # Was -2.0 - looser for better signal quality
    exit_adx_jerk_threshold: float = -0.5 # Unchanged - requires negative jerk

    # AGGRESSIVE signal thresholds - made EASIER to trigger
    entry_vel_threshold: float = -0.5     # Was -1.5 - easier to recognize recovery
    entry_acc_threshold: float = 1.5      # Was 3.0 - lower bar for acceleration

    # Multi-timeframe confirmation: require N timeframes to agree
    defensive_tf_confirm: int = 2  # Need 2+ timeframes showing danger (was 1)
    aggressive_tf_confirm: int = 1 # Only 1 timeframe needed for opportunity


@dataclass
class MarketState:
    """Current market state from derivatives."""
    time: datetime
    symbol: str

    # 1h timeframe
    tf_1h_vel: Optional[float] = None
    tf_1h_acc: Optional[float] = None
    tf_1h_adx_jerk: Optional[float] = None

    # 4h timeframe
    tf_4h_vel: Optional[float] = None
    tf_4h_acc: Optional[float] = None
    tf_4h_adx_jerk: Optional[float] = None

    # 1d timeframe
    tf_1d_vel: Optional[float] = None
    tf_1d_acc: Optional[float] = None
    tf_1d_adx_jerk: Optional[float] = None


@dataclass
class RegimeState:
    """Current regime and limits."""
    regime: Regime
    max_position: float
    triggered_by: str  # Which timeframe/signal triggered
    since: datetime
    exit_signal_active: bool
    entry_signal_active: bool
    # Conviction metrics for graduated position sizing
    entry_confirmation_count: int = 0  # How many TFs confirm entry signal (0-3)
    entry_avg_depth: float = 0.0  # Average z-score depth past threshold (higher = stronger)


class BearProtectionService:
    """
    Supreme risk layer with VETO EXIT POWER.

    Monitors motion derivatives across timeframes and:
    1. Sets position limits based on regime
    2. Can FORCE EXIT positions during crashes (veto power)
    3. Patterns must respect these limits

    Usage:
        service = BearProtectionService()
        state = service.evaluate(market_state)

        # Check if pattern can trade
        if state.regime == Regime.DEFENSIVE:
            # Reduce all positions to 25% max
            pass

        # Get max allowed position
        max_size = state.max_position * capital
    """

    def __init__(self, config: Optional[RegimeConfig] = None):
        self.config = config or RegimeConfig()
        self._current_regime = Regime.NEUTRAL
        self._regime_since = datetime.now(timezone.utc)
        self._last_trigger = "startup"

    def _check_exit_signal(self, vel: float, acc: float, adx_jerk: float) -> bool:
        """
        Check if exit (danger) signal fires for one timeframe.

        v3: Uses AJ config (Acceleration + Jerk only).
        Velocity removed after testing showed acc+jerk outperformed vel+acc+jerk
        by 3.8x on 65-stock backtest (+9.1% vs +2.4% avg ROI diff).
        """
        # Only require acc and adx_jerk (velocity ignored in v3)
        if acc is None or adx_jerk is None:
            return False
        return (
            acc < self.config.exit_acc_threshold
            and adx_jerk < self.config.exit_adx_jerk_threshold
        )

    def _check_entry_signal(self, vel: float, acc: float) -> bool:
        """Check if entry (opportunity) signal fires for one timeframe."""
        if vel is None or acc is None:
            return False
        return (
            vel < self.config.entry_vel_threshold
            and acc > self.config.entry_acc_threshold
        )

    def evaluate(self, state: MarketState) -> RegimeState:
        """
        Evaluate market state and return current regime.

        Returns RegimeState with:
        - regime: DEFENSIVE/NEUTRAL/AGGRESSIVE
        - max_position: Maximum allowed position (0.25-0.75)
        - exit_signal_active: True if any TF shows exit signal
        - entry_signal_active: True if any TF shows entry signal
        """
        exit_signals = []
        entry_signals = []
        entry_depths = []  # How far past threshold each confirming TF is

        # Check all timeframes
        for tf, vel, acc, jerk in [
            ("1h", state.tf_1h_vel, state.tf_1h_acc, state.tf_1h_adx_jerk),
            ("4h", state.tf_4h_vel, state.tf_4h_acc, state.tf_4h_adx_jerk),
            ("1d", state.tf_1d_vel, state.tf_1d_acc, state.tf_1d_adx_jerk),
        ]:
            if self._check_exit_signal(vel, acc, jerk):
                exit_signals.append(tf)
            if self._check_entry_signal(vel, acc):
                entry_signals.append(tf)
                # Measure depth: how far past the threshold each value is
                vel_depth = abs(vel - self.config.entry_vel_threshold) if vel is not None else 0
                acc_depth = abs(acc - self.config.entry_acc_threshold) if acc is not None else 0
                entry_depths.append(vel_depth + acc_depth)

        exit_count = len(exit_signals)
        entry_count = len(entry_signals)

        # Multi-timeframe confirmation required for DEFENSIVE
        # This lets bulls run - a single TF pullback won't trigger exit
        exit_confirmed = exit_count >= self.config.defensive_tf_confirm
        entry_confirmed = entry_count >= self.config.aggressive_tf_confirm

        # Determine regime (exit signal takes priority IF confirmed)
        new_regime = self._current_regime
        trigger = self._last_trigger

        if exit_confirmed:
            new_regime = Regime.DEFENSIVE
            trigger = f"exit:{','.join(exit_signals)}[{exit_count}TF]"
        elif entry_confirmed:
            new_regime = Regime.AGGRESSIVE
            trigger = f"entry:{','.join(entry_signals)}[{entry_count}TF]"
        elif exit_count == 0 and entry_count == 0 and self._current_regime != Regime.NEUTRAL:
            # Return to NEUTRAL when no signals (allows bulls to run)
            new_regime = Regime.NEUTRAL
            trigger = "no_signals"
        # Note: Regime is STICKY - stays until opposite signal or all-clear

        # Update internal state if changed
        if new_regime != self._current_regime:
            logger.info(
                f"REGIME CHANGE: {self._current_regime.value} -> {new_regime.value} "
                f"triggered by {trigger} for {state.symbol}"
            )
            self._current_regime = new_regime
            self._regime_since = state.time
            self._last_trigger = trigger

        # Get position limit
        if new_regime == Regime.DEFENSIVE:
            max_pos = self.config.defensive_max
        elif new_regime == Regime.AGGRESSIVE:
            max_pos = self.config.aggressive_max
        else:
            max_pos = self.config.neutral_max

        return RegimeState(
            regime=new_regime,
            max_position=max_pos,
            triggered_by=trigger,
            since=self._regime_since,
            exit_signal_active=exit_confirmed,
            entry_signal_active=entry_confirmed,
            entry_confirmation_count=entry_count,
            entry_avg_depth=sum(entry_depths) / len(entry_depths) if entry_depths else 0.0,
        )

    def get_position_limit(self, capital: float) -> float:
        """Get maximum position size in dollars."""
        if self._current_regime == Regime.DEFENSIVE:
            return capital * self.config.defensive_max
        elif self._current_regime == Regime.AGGRESSIVE:
            return capital * self.config.aggressive_max
        return capital * self.config.neutral_max

    def should_force_exit(self, state: MarketState) -> bool:
        """
        Check if positions should be force-reduced.

        This is the VETO POWER - when True, ALL positions must be
        reduced to DEFENSIVE limit regardless of pattern signals.
        """
        result = self.evaluate(state)
        return result.exit_signal_active and result.regime == Regime.DEFENSIVE

    def get_regime(self) -> Regime:
        """Get current regime."""
        return self._current_regime

    def get_regime_duration_hours(self) -> float:
        """Get hours in current regime."""
        delta = datetime.now(timezone.utc) - self._regime_since
        return delta.total_seconds() / 3600


# Singleton instance
_bear_protection: Optional[BearProtectionService] = None


def get_bear_protection() -> BearProtectionService:
    """Get singleton bear protection service."""
    global _bear_protection
    if _bear_protection is None:
        _bear_protection = BearProtectionService()
    return _bear_protection
