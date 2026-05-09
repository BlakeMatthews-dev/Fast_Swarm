"""
Fitness Rules - Named Constants for Fitness Calculation

MASTER TEST ADMIN DECREE: No magic numbers in production code.
All numeric literals must be named, documented, and sourced from here.

100-Point Fitness Model:
    Sortino (25) + Win Rate (20) + Profit Factor (15) + Expectancy (15) +
    Max DD (10) + Trade Count (10) + Consistency (5) = 100 points
"""

# =============================================================================
# FITNESS BOUNDS
# =============================================================================

FITNESS_MIN = 0.0
"""Minimum possible fitness score."""

FITNESS_MAX = 100.0
"""Maximum possible fitness score (perfect agent)."""


# =============================================================================
# TIER THRESHOLDS
# =============================================================================

TIER_DIES_THRESHOLD = 40.0
"""Agents below this fitness are culled (DIES tier)."""

TIER_PROMOTED_THRESHOLD = 80.0
"""Agents at or above this fitness are promoted (elite tier)."""

TIER_DIES = "DIES"
"""Tier name for agents that will be culled."""

TIER_SURVIVES = "SURVIVES"
"""Tier name for agents that survive but aren't elite."""

TIER_PROMOTED = "PROMOTED"
"""Tier name for elite agents that can reproduce."""


# =============================================================================
# EV (EXPECTED VALUE) RULES
# =============================================================================

EV_GATE_THRESHOLD = 0.0
"""EV must be positive for non-zero fitness. The sacred gate."""

EV_MULTIPLIER_MIN = 0.35
"""Minimum EV multiplier (applied when EV <= 0)."""

EV_MULTIPLIER_MAX = 1.5
"""Maximum EV multiplier (applied when EV >= 9)."""

EV_MULTIPLIER_BREAKPOINTS = [
    (0.0, 0.35),  # EV <= 0: minimum multiplier
    (3.0, 0.7),  # EV = 3: 70% multiplier
    (6.0, 1.0),  # EV = 6: 100% multiplier (neutral)
    (9.0, 1.5),  # EV >= 9: maximum multiplier (150% boost)
]
"""Piecewise linear interpolation points for EV multiplier."""


# =============================================================================
# COMPONENT WEIGHTS (100-Point Model)
# =============================================================================

WEIGHT_SORTINO = 25.0
"""Sortino ratio weight (risk-adjusted returns)."""

WEIGHT_WIN_RATE = 20.0
"""Win rate weight (consistency of winners)."""

WEIGHT_PROFIT_FACTOR = 15.0
"""Profit factor weight (gross profit / gross loss)."""

WEIGHT_EXPECTANCY = 15.0
"""Expectancy weight (average profit per trade)."""

WEIGHT_MAX_DRAWDOWN = 10.0
"""Max drawdown weight (capital preservation)."""

WEIGHT_TRADE_COUNT = 10.0
"""Trade count weight (statistical significance)."""

WEIGHT_CONSISTENCY = 5.0
"""Consistency weight (stability of returns)."""


# =============================================================================
# COMPONENT CAPS
# =============================================================================

SORTINO_CAP = 4.0
"""Maximum Sortino ratio (prevents outlier dominance)."""

SORTINO_CAP_NO_LOSSES = 4.0
"""Sortino when no downside deviation (all winners)."""

PROFIT_FACTOR_CAP = 10.0
"""Maximum profit factor (prevents outlier dominance)."""

SHARPE_REASONABLE_MIN = 0.5
"""Minimum reasonable Sharpe ratio for a trading strategy."""

SHARPE_REASONABLE_MAX = 3.0
"""Maximum reasonable Sharpe (above this is likely overfitting or luck)."""


# =============================================================================
# TRADE COUNT THRESHOLDS
# =============================================================================

MIN_TRADES_FOR_SIGNIFICANCE = 30
"""Minimum trades for statistical significance."""

IDEAL_TRADE_COUNT = 100
"""Ideal number of trades for full trade count score."""


# =============================================================================
# WIN RATE BOUNDS
# =============================================================================

WIN_RATE_MIN = 0.0
"""Minimum win rate (0%)."""

WIN_RATE_MAX = 100.0
"""Maximum win rate (100%)."""


# =============================================================================
# DRAWDOWN BOUNDS
# =============================================================================

MAX_DRAWDOWN_MIN = 0.0
"""Minimum drawdown (perfect equity curve - all winners)."""

MAX_DRAWDOWN_MAX = 100.0
"""Maximum drawdown (complete wipeout)."""

MAX_DRAWDOWN_ACCEPTABLE = 20.0
"""Acceptable max drawdown for a trading strategy."""


# =============================================================================
# TRAIT BOUNDS
# =============================================================================

TRAIT_MIN = 0.0
"""Minimum trait value."""

TRAIT_MAX = 1.0
"""Maximum trait value."""

TRAIT_DEFAULT = 0.5
"""Default trait value (middle of range)."""


# =============================================================================
# VALIDATION HELPERS
# =============================================================================


def validate_fitness(score: float) -> bool:
    """Check if fitness score is within valid bounds."""
    return FITNESS_MIN <= score <= FITNESS_MAX


def validate_trait(value: float) -> bool:
    """Check if trait value is within valid bounds."""
    return TRAIT_MIN <= value <= TRAIT_MAX


def get_tier(fitness_score: float) -> str:
    """Get tier name from fitness score."""
    if fitness_score < TIER_DIES_THRESHOLD:
        return TIER_DIES
    elif fitness_score >= TIER_PROMOTED_THRESHOLD:
        return TIER_PROMOTED
    else:
        return TIER_SURVIVES
