"""
Fitness Calculator - DUAL FORMULA (Agent + Pattern)

This module provides TWO fitness formulas:
1. calculate_agent_fitness() - V3 + EV Gate (for agent evaluation)
2. calculate_pattern_fitness() - V2 Signed Risk (for pattern backtests)

=============================================================================
AGENT FITNESS (V3 + EV Gate)
=============================================================================
100-point system with EV gate.

Signed Components (can go negative):
- Alpha: ±35 pts (normalized from -100% to +100%)
- Calibration: ±10 pts (0.5 baseline = 0 pts)

Unsigned Components (always positive):
- Win Rate: 10 pts (30-70% normalized)
- Sortino: 15 pts (0-4 normalized)
- Drawdown: 10 pts (0-50% normalized, inverted)
- Exit Efficiency: 10 pts (0.3-0.8 normalized)
- Loss Sizing: 5 pts (0.5-2.0 normalized)
- AI Accuracy: 5 pts (0.4-0.8 normalized)

EV Gate:
- expectancy <= 0 -> fitness = 0
- Multiplier: 0% -> 0, 1% -> 0.8, 3% -> 1.2, 9%+ -> 1.5 cap

=============================================================================
PATTERN FITNESS (V2 Signed Risk)
=============================================================================
100-point system WITHOUT EV gate.

Signed Components (can go negative):
- Alpha: ±35 pts (outperformance vs benchmark)
- Sortino: ±14 pts (downside risk-adjusted, capped at ±10)
- Calmar: ±11 pts (return vs max drawdown, capped at ±10)

Normalized Components (0 to max):
- Expectancy: 0-25 pts (expected value per trade)
- Drawdown: 0-5 pts (bonus for low drawdown)
- Exit Efficiency: 0-10 pts (pnl/mfe ratio)

Total range: -60 to +100, clamped to 0-100
"""

import math
from dataclasses import dataclass
from typing import Protocol

# =============================================================================
# Constants (V3 Parity)
# =============================================================================

AGENT_FITNESS_WEIGHTS = {
    # Signed components
    "alpha": 35,
    "calibration": 10,
    # Unsigned components
    "win_rate": 10,
    "sortino": 15,
    "drawdown": 10,
    "exit_efficiency": 10,
    "loss_sizing": 5,
    "ai_accuracy": 5,
}

AGENT_FITNESS_BOUNDS = {
    "alpha_pct": {"min": -100, "max": 100},
    "calibration_score": {"min": 0, "max": 1},
    "win_rate_pct": {"min": 30, "max": 70},
    "sortino_ratio": {"min": 0, "max": 4},
    "max_drawdown_pct": {"min": 0, "max": 50},
    "exit_efficiency": {"min": 0.3, "max": 0.8},
    "loss_sizing_ratio": {"min": 0.5, "max": 2.0},
    "ai_accuracy": {"min": 0.4, "max": 0.8},
}

# EV Multiplier breakpoints
EV_BREAKPOINTS = [
    (0.0, 0.0),  # 0% EV -> 0 multiplier (gate closed)
    (0.0001, 0.35),  # Just above 0 -> 0.35
    (1.0, 0.8),  # 1% EV -> 0.8x
    (3.0, 1.2),  # 3% EV -> 1.2x
    (9.0, 1.5),  # 9%+ EV -> 1.5x (cap)
]


# =============================================================================
# Data Classes
# =============================================================================


class AgentMetricsProtocol(Protocol):
    """Protocol for agent metrics input."""

    alpha_pct: float
    expectancy_pct: float
    win_rate_pct: float
    sortino_ratio: float
    max_drawdown_pct: float
    calibration_score: float
    exit_efficiency: float
    loss_sizing_ratio: float
    ai_decisions: int
    ai_correct: int


@dataclass
class FitnessBreakdown:
    """Detailed fitness calculation result."""

    # EV Gate
    expectancy_pct: float = 0.0
    ev_multiplier: float = 0.0
    ev_gate_passed: bool = False

    # Signed components
    alpha_contribution: float = 0.0
    calibration_contribution: float = 0.0
    signed_total: float = 0.0

    # Unsigned components
    win_rate_score: float = 0.0
    sortino_score: float = 0.0
    drawdown_score: float = 0.0
    exit_efficiency_score: float = 0.0
    loss_sizing_score: float = 0.0
    ai_accuracy_score: float = 0.0
    unsigned_total: float = 0.0

    # Final scores
    raw_fitness: float = 0.0
    scaled_fitness: float = 0.0
    final_fitness: float = 0.0


# =============================================================================
# EV Gate
# =============================================================================


def expectancy_multiplier(ev_pct: float) -> float:
    """
    Calculate EV multiplier from expectancy percentage.

    V3 Parity: Linear interpolation between breakpoints.

    Args:
        ev_pct: Expectancy percentage (can be negative).

    Returns:
        Multiplier in range [0, 1.5].
        0 if EV <= 0 (gate closed).
    """
    # Handle special values
    if math.isnan(ev_pct):
        return 0.0
    if ev_pct == float("-inf"):
        return 0.0
    if ev_pct == float("inf"):
        return 1.5

    # Gate closed for non-positive EV
    if ev_pct <= 0:
        return 0.0

    # Find the right segment and interpolate
    for i in range(len(EV_BREAKPOINTS) - 1):
        ev_low, mult_low = EV_BREAKPOINTS[i]
        ev_high, mult_high = EV_BREAKPOINTS[i + 1]

        if ev_pct <= ev_high:
            # Linear interpolation
            if ev_high == ev_low:
                return mult_high
            ratio = (ev_pct - ev_low) / (ev_high - ev_low)
            return mult_low + ratio * (mult_high - mult_low)

    # Above all breakpoints - cap at max
    return 1.5


# =============================================================================
# Signed Components
# =============================================================================


def calculate_alpha_contribution(alpha_pct: float) -> float:
    """
    Calculate alpha contribution to fitness (-35 to +35).

    Args:
        alpha_pct: Alpha percentage (-100 to +100).

    Returns:
        Contribution in range [-35, +35].
    """
    if math.isnan(alpha_pct):
        return 0.0

    # Clamp to bounds
    alpha_pct = max(-100, min(100, alpha_pct))

    # Normalize to [-1, 1] and scale by weight
    normalized = alpha_pct / 100
    return normalized * AGENT_FITNESS_WEIGHTS["alpha"]


def calculate_calibration_contribution(calibration_score: float) -> float:
    """
    Calculate calibration contribution to fitness (-10 to +10).

    0.5 is baseline (random) = 0 pts.
    1.0 is perfect = +10 pts.
    0.0 is inverse = -10 pts.

    Args:
        calibration_score: Calibration score (0 to 1).

    Returns:
        Contribution in range [-10, +10].
    """
    if math.isnan(calibration_score):
        return 0.0

    # Clamp to bounds
    calibration_score = max(0, min(1, calibration_score))

    # 0.5 is neutral, map to [-1, 1]
    normalized = (calibration_score - 0.5) * 2
    return normalized * AGENT_FITNESS_WEIGHTS["calibration"]


# =============================================================================
# Unsigned Components (all use same pattern)
# =============================================================================


def _normalize_and_score(value: float, min_val: float, max_val: float, weight: float, invert: bool = False) -> float:
    """
    Normalize value to [0, 1] and scale by weight.

    Args:
        value: Input value.
        min_val: Minimum bound.
        max_val: Maximum bound.
        weight: Weight to multiply by.
        invert: If True, lower values are better.

    Returns:
        Score in range [0, weight].
    """
    if not math.isfinite(value):
        return 0.0

    # Clamp to bounds
    value = max(min_val, min(max_val, value))

    # Normalize to [0, 1]
    if max_val == min_val:
        normalized = 0.5
    else:
        normalized = (value - min_val) / (max_val - min_val)

    # Invert if needed (e.g., drawdown)
    if invert:
        normalized = 1 - normalized

    return normalized * weight


def calculate_win_rate_score(win_rate_pct: float) -> float:
    """Calculate win rate score (0-10 pts)."""
    bounds = AGENT_FITNESS_BOUNDS["win_rate_pct"]
    return _normalize_and_score(win_rate_pct, bounds["min"], bounds["max"], AGENT_FITNESS_WEIGHTS["win_rate"])


def calculate_sortino_score(sortino_ratio: float) -> float:
    """Calculate Sortino ratio score (0-15 pts)."""
    bounds = AGENT_FITNESS_BOUNDS["sortino_ratio"]
    return _normalize_and_score(sortino_ratio, bounds["min"], bounds["max"], AGENT_FITNESS_WEIGHTS["sortino"])


def calculate_drawdown_score(max_drawdown_pct: float) -> float:
    """Calculate drawdown score (0-10 pts, inverted - lower is better)."""
    bounds = AGENT_FITNESS_BOUNDS["max_drawdown_pct"]
    return _normalize_and_score(
        max_drawdown_pct, bounds["min"], bounds["max"], AGENT_FITNESS_WEIGHTS["drawdown"], invert=True
    )


def calculate_exit_efficiency_score(exit_efficiency: float) -> float:
    """Calculate exit efficiency score (0-10 pts)."""
    bounds = AGENT_FITNESS_BOUNDS["exit_efficiency"]
    return _normalize_and_score(exit_efficiency, bounds["min"], bounds["max"], AGENT_FITNESS_WEIGHTS["exit_efficiency"])


def calculate_loss_sizing_score(loss_sizing_ratio: float) -> float:
    """Calculate loss sizing ratio score (0-5 pts)."""
    bounds = AGENT_FITNESS_BOUNDS["loss_sizing_ratio"]
    return _normalize_and_score(loss_sizing_ratio, bounds["min"], bounds["max"], AGENT_FITNESS_WEIGHTS["loss_sizing"])


def calculate_ai_accuracy_score(ai_accuracy: float) -> float:
    """Calculate AI accuracy score (0-5 pts)."""
    bounds = AGENT_FITNESS_BOUNDS["ai_accuracy"]
    return _normalize_and_score(ai_accuracy, bounds["min"], bounds["max"], AGENT_FITNESS_WEIGHTS["ai_accuracy"])


def calculate_ai_accuracy_from_counts(ai_decisions: int, ai_correct: int) -> float:
    """
    Calculate AI accuracy score from decision counts.

    Args:
        ai_decisions: Total AI consultations.
        ai_correct: Correct AI decisions.

    Returns:
        Score in range [0, 5].
    """
    if ai_decisions == 0:
        # No AI decisions = neutral score
        return AGENT_FITNESS_WEIGHTS["ai_accuracy"] / 2

    accuracy = ai_correct / ai_decisions
    return calculate_ai_accuracy_score(accuracy)


# =============================================================================
# Full Fitness Calculation
# =============================================================================


def calculate_agent_fitness(metrics: AgentMetricsProtocol) -> FitnessBreakdown:
    """
    Calculate full agent fitness with breakdown.

    V3 Parity: Exact same formula as TypeScript implementation.

    Args:
        metrics: Agent metrics object.

    Returns:
        FitnessBreakdown with all components.
    """
    result = FitnessBreakdown()

    # === EV Gate ===
    result.expectancy_pct = metrics.expectancy_pct
    result.ev_multiplier = expectancy_multiplier(metrics.expectancy_pct)
    result.ev_gate_passed = result.ev_multiplier > 0

    # If gate is closed, return zero fitness
    if not result.ev_gate_passed:
        result.final_fitness = 0
        return result

    # === Signed Components ===
    result.alpha_contribution = calculate_alpha_contribution(metrics.alpha_pct)
    result.calibration_contribution = calculate_calibration_contribution(metrics.calibration_score)
    result.signed_total = result.alpha_contribution + result.calibration_contribution

    # === Unsigned Components ===
    result.win_rate_score = calculate_win_rate_score(metrics.win_rate_pct)
    result.sortino_score = calculate_sortino_score(metrics.sortino_ratio)
    result.drawdown_score = calculate_drawdown_score(metrics.max_drawdown_pct)
    result.exit_efficiency_score = calculate_exit_efficiency_score(metrics.exit_efficiency)
    result.loss_sizing_score = calculate_loss_sizing_score(metrics.loss_sizing_ratio)

    # AI accuracy from counts
    if hasattr(metrics, "ai_decisions") and hasattr(metrics, "ai_correct"):
        result.ai_accuracy_score = calculate_ai_accuracy_from_counts(metrics.ai_decisions, metrics.ai_correct)
    else:
        result.ai_accuracy_score = AGENT_FITNESS_WEIGHTS["ai_accuracy"] / 2

    result.unsigned_total = (
        result.win_rate_score
        + result.sortino_score
        + result.drawdown_score
        + result.exit_efficiency_score
        + result.loss_sizing_score
        + result.ai_accuracy_score
    )

    # === Final Calculation ===
    result.raw_fitness = result.signed_total + result.unsigned_total
    result.scaled_fitness = result.raw_fitness * result.ev_multiplier

    # Clamp to [0, 100]
    result.final_fitness = max(0, min(100, result.scaled_fitness))

    return result


# =============================================================================
# PATTERN FITNESS (V2 Signed Risk) - For pattern backtests
# =============================================================================

PATTERN_FITNESS_WEIGHTS = {
    # Signed components (can go negative)
    "alpha": 35,  # -35 to +35 pts
    "sortino": 14,  # -14 to +14 pts
    "calmar": 11,  # -11 to +11 pts
    # Normalized components (0 to max)
    "expectancy": 25,  # 0-25 pts
    "drawdown": 5,  # 0-5 pts
    "exit_efficiency": 10,  # 0-10 pts
}

PATTERN_FITNESS_BOUNDS = {
    "alpha_pct": {"min": -100, "max": 100},
    "sortino_ratio": {"min": -10, "max": 10},
    "calmar_ratio": {"min": -10, "max": 10},
    "expectancy_pct": {"min": -10, "max": 10},
    "max_drawdown_pct": {"min": 0, "max": 50},
    "exit_efficiency": {"min": 0, "max": 1},
}


class PatternMetricsProtocol(Protocol):
    """Protocol for pattern metrics input."""

    alpha_pct: float
    sortino_ratio: float
    calmar_ratio: float
    expectancy_pct: float
    max_drawdown_pct: float
    exit_efficiency: float


@dataclass
class PatternFitnessBreakdown:
    """Detailed pattern fitness calculation result."""

    # Signed components
    alpha_contribution: float = 0.0
    sortino_contribution: float = 0.0
    calmar_contribution: float = 0.0
    signed_total: float = 0.0

    # Normalized components
    expectancy_score: float = 0.0
    drawdown_score: float = 0.0
    exit_efficiency_score: float = 0.0
    normalized_total: float = 0.0

    # Final scores
    raw_fitness: float = 0.0
    final_fitness: float = 0.0


def calculate_calmar_ratio(annualized_return_pct: float, max_drawdown_pct: float) -> float:
    """
    Calculate Calmar Ratio.

    Calmar = Annualized Return / Max Drawdown

    Args:
        annualized_return_pct: Annualized return percentage.
        max_drawdown_pct: Maximum drawdown percentage.

    Returns:
        Calmar ratio (capped at ±10).
    """
    abs_drawdown = abs(max_drawdown_pct)

    if abs_drawdown == 0:
        return 10.0 if annualized_return_pct > 0 else 0.0

    calmar = annualized_return_pct / abs_drawdown if abs_drawdown != 0 else 0.0

    # Cap at ±10
    return max(-10, min(10, calmar))


def _pattern_signed_contribution(value: float, min_val: float, max_val: float, weight: float) -> float:
    """
    Calculate signed contribution for pattern fitness.

    Maps value from [min_val, max_val] to [-weight, +weight].

    Args:
        value: Input value.
        min_val: Minimum bound.
        max_val: Maximum bound.
        weight: Weight to multiply by.

    Returns:
        Contribution in range [-weight, +weight].
    """
    if not math.isfinite(value):
        return 0.0

    # Clamp to bounds
    value = max(min_val, min(max_val, value))

    # Normalize to [-1, 1]
    normalized = value / max_val if max_val != 0 else 0.0

    return normalized * weight


def _pattern_normalized_contribution(
    value: float, min_val: float, max_val: float, weight: float, invert: bool = False
) -> float:
    """
    Calculate normalized contribution for pattern fitness.

    Maps value from [min_val, max_val] to [0, weight].

    Args:
        value: Input value.
        min_val: Minimum bound.
        max_val: Maximum bound.
        weight: Weight to multiply by.
        invert: If True, lower values are better.

    Returns:
        Contribution in range [0, weight].
    """
    if not math.isfinite(value):
        return weight / 2 if not invert else weight / 2  # Neutral default

    # Clamp to bounds
    value = max(min_val, min(max_val, value))

    # Normalize to [0, 1]
    if max_val == min_val:
        normalized = 0.5
    else:
        normalized = (value - min_val) / (max_val - min_val)

    # Invert if needed
    if invert:
        normalized = 1 - normalized

    return normalized * weight


def calculate_pattern_fitness(metrics: PatternMetricsProtocol) -> PatternFitnessBreakdown:
    """
    Calculate pattern fitness using V2 Signed Risk formula.

    NO EV gate - negative values just reduce score.
    Total range: -60 to +100, clamped to 0-100.

    Args:
        metrics: Pattern metrics object.

    Returns:
        PatternFitnessBreakdown with all components.
    """
    result = PatternFitnessBreakdown()

    # === Signed Components ===
    bounds = PATTERN_FITNESS_BOUNDS

    # Alpha contribution (-35 to +35)
    result.alpha_contribution = _pattern_signed_contribution(
        metrics.alpha_pct, bounds["alpha_pct"]["min"], bounds["alpha_pct"]["max"], PATTERN_FITNESS_WEIGHTS["alpha"]
    )

    # Sortino contribution (-14 to +14)
    result.sortino_contribution = _pattern_signed_contribution(
        metrics.sortino_ratio,
        bounds["sortino_ratio"]["min"],
        bounds["sortino_ratio"]["max"],
        PATTERN_FITNESS_WEIGHTS["sortino"],
    )

    # Calmar contribution (-11 to +11)
    result.calmar_contribution = _pattern_signed_contribution(
        metrics.calmar_ratio,
        bounds["calmar_ratio"]["min"],
        bounds["calmar_ratio"]["max"],
        PATTERN_FITNESS_WEIGHTS["calmar"],
    )

    result.signed_total = result.alpha_contribution + result.sortino_contribution + result.calmar_contribution

    # === Normalized Components ===

    # Expectancy (0-25)
    result.expectancy_score = _pattern_normalized_contribution(
        metrics.expectancy_pct,
        bounds["expectancy_pct"]["min"],
        bounds["expectancy_pct"]["max"],
        PATTERN_FITNESS_WEIGHTS["expectancy"],
    )

    # Drawdown (0-5, inverted - lower is better)
    result.drawdown_score = _pattern_normalized_contribution(
        metrics.max_drawdown_pct,
        bounds["max_drawdown_pct"]["min"],
        bounds["max_drawdown_pct"]["max"],
        PATTERN_FITNESS_WEIGHTS["drawdown"],
        invert=True,
    )

    # Exit efficiency (0-10)
    result.exit_efficiency_score = _pattern_normalized_contribution(
        metrics.exit_efficiency,
        bounds["exit_efficiency"]["min"],
        bounds["exit_efficiency"]["max"],
        PATTERN_FITNESS_WEIGHTS["exit_efficiency"],
    )

    result.normalized_total = result.expectancy_score + result.drawdown_score + result.exit_efficiency_score

    # === Final Calculation ===
    result.raw_fitness = result.signed_total + result.normalized_total

    # Clamp to [0, 100]
    result.final_fitness = max(0, min(100, result.raw_fitness))

    return result


def calculate_pattern_fitness_simple(
    alpha_pct: float,
    sortino_ratio: float,
    max_drawdown_pct: float,
    expectancy_pct: float,
    exit_efficiency: float = 0.5,
    annualized_roi_pct: float = 0.0,
) -> float:
    """
    Simple pattern fitness calculation - returns just the score.

    Convenience function for callers who don't need the full breakdown.

    Args:
        alpha_pct: Alpha vs benchmark.
        sortino_ratio: Sortino ratio.
        max_drawdown_pct: Maximum drawdown percentage.
        expectancy_pct: Expected value per trade.
        exit_efficiency: Exit efficiency (pnl/mfe), default 0.5.
        annualized_roi_pct: Annualized ROI for Calmar calculation.

    Returns:
        Fitness score 0-100.
    """
    # Calculate Calmar from annualized return and drawdown
    calmar = calculate_calmar_ratio(annualized_roi_pct, max_drawdown_pct)

    # Create metrics object
    class Metrics:
        pass

    m = Metrics()
    m.alpha_pct = alpha_pct
    m.sortino_ratio = sortino_ratio
    m.calmar_ratio = calmar
    m.expectancy_pct = expectancy_pct
    m.max_drawdown_pct = max_drawdown_pct
    m.exit_efficiency = exit_efficiency

    result = calculate_pattern_fitness(m)
    return result.final_fitness
