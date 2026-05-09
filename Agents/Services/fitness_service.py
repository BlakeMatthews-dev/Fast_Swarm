"""
Fitness Service for Fast_Swarm.

Implements the 100-Point Fitness Model from Master_plan.md:
- EV Gate: Blocks agents with EV <= 0%
- EV Multiplier: Scales fitness based on expectancy (0.35-1.5)
- Signed Components: Alpha (±35), Calibration (±10)
- Unsigned Components: Win Rate (10), Sortino (15), Drawdown (10),
                       Exit Efficiency (10), Loss Sizing (5), AI Accuracy (5)
- Formula: (signed + unsigned) × EV_multiplier, clamped to [0, 100]
"""

import math
from dataclasses import dataclass
from typing import Any

# =============================================================================
# Data Classes for Fitness Calculation
# =============================================================================


@dataclass
class TradeData:
    """Trade data for fitness calculation."""

    pnl: float  # Absolute PnL
    pnl_pct: float  # Percentage PnL
    is_win: bool  # Whether trade was profitable
    entry_price: float = 0.0
    exit_price: float = 0.0
    size: float = 0.0


@dataclass
class FitnessMetrics:
    """Intermediate metrics for fitness calculation."""

    ev: float  # Expected Value (average PnL %)
    win_rate: float  # Win rate (0-100)
    sortino: float  # Sortino ratio
    max_drawdown: float  # Max drawdown (0-100)
    alpha: float  # Benchmark comparison (-100 to +100)
    calibration: float  # Calibration score (0-1)
    exit_efficiency: float  # Exit efficiency (0-1)
    loss_sizing: float  # Loss sizing ratio
    ai_accuracy: float  # AI prediction accuracy (0-1)


@dataclass
class FitnessResult:
    """Complete fitness calculation result."""

    fitness_score: float  # Final score [0, 100]
    tier: str  # "DIES", "SURVIVES", or "PROMOTED"
    metrics: FitnessMetrics
    ev_multiplier: float
    component_breakdown: dict[str, float]


# =============================================================================
# EV Gate and Multiplier
# =============================================================================


def calculate_ev(trades: list[TradeData]) -> float:
    """
    Calculate Expected Value (average PnL %).

    Args:
        trades: List of trade data

    Returns:
        EV as a percentage
    """
    if not trades:
        return 0.0

    valid_pnls = [t.pnl_pct for t in trades if _is_valid_number(t.pnl_pct)]

    if not valid_pnls:
        return 0.0

    return sum(valid_pnls) / len(valid_pnls)


def ev_gate(ev: float) -> bool:
    """
    Check if EV passes the gate.

    Args:
        ev: Expected value percentage

    Returns:
        True if EV > 0 (passes gate), False otherwise
    """
    return ev > 0.0


def calculate_ev_multiplier(ev: float) -> float:
    """
    Calculate EV multiplier using piecewise linear interpolation.

    EV=0% → 0.35
    EV=1% → 0.8
    EV=3% → 1.2
    EV≥9% → 1.5 (capped)

    Args:
        ev: Expected value percentage

    Returns:
        EV multiplier between 0.35 and 1.5
    """
    if ev <= 0:
        return 0.35

    # Interpolation points: (ev, multiplier)
    points = [
        (0, 0.35),
        (1, 0.8),
        (3, 1.2),
        (9, 1.5),
    ]

    # Cap at 9%
    if ev >= 9:
        return 1.5

    # Find interpolation segment
    for i in range(len(points) - 1):
        ev_low, mult_low = points[i]
        ev_high, mult_high = points[i + 1]

        if ev_low <= ev <= ev_high:
            # Linear interpolation
            denominator = ev_high - ev_low
            # GUARD: Handle identical interpolation points (CRASH-002)
            ratio = (ev - ev_low) / denominator if denominator != 0 else 0.5
            return mult_low + ratio * (mult_high - mult_low)

    # Fallback (shouldn't reach here)
    return 0.35


# =============================================================================
# Signed Components (can be positive or negative)
# =============================================================================


def calculate_alpha_component(benchmark_pct: float) -> float:
    """
    Calculate alpha component based on benchmark comparison.

    Alpha = ±35 points
    -100% benchmark → -35 points
    0% benchmark → 0 points
    +100% benchmark → +35 points

    Args:
        benchmark_pct: Benchmark comparison percentage (-100 to +100)

    Returns:
        Alpha component between -35 and +35
    """
    # Clamp to reasonable range
    clamped = max(-100, min(100, benchmark_pct))
    # Scale to ±35
    return clamped * 35 / 100


def calculate_calibration_component(calibration_score: float) -> float:
    """
    Calculate calibration component.

    Calibration = ±10 points
    0.0 → -10 points
    0.5 → 0 points (baseline)
    1.0 → +10 points

    Args:
        calibration_score: Calibration value (0-1)

    Returns:
        Calibration component between -10 and +10
    """
    # 0.5 is baseline (0 points)
    clamped = max(0.0, min(1.0, calibration_score))
    return (clamped - 0.5) * 20  # Scale from [-0.5, 0.5] to [-10, +10]


# =============================================================================
# Unsigned Components (always positive)
# =============================================================================


def calculate_win_rate_component(win_rate: float) -> float:
    """
    Calculate win rate component.

    Win Rate = 0-10 points (30-70% range)
    30% → 0 points
    70% → 10 points

    Args:
        win_rate: Win rate percentage (0-100)

    Returns:
        Win rate component between 0 and 10
    """
    if win_rate <= 30:
        return 0.0
    if win_rate >= 70:
        return 10.0

    # Linear interpolation from 30-70%
    return (win_rate - 30) / 40 * 10


def calculate_sortino_component(sortino: float) -> float:
    """
    Calculate Sortino ratio component.

    Sortino = 0-15 points (0-4 range)
    0 → 0 points
    4 → 15 points

    Args:
        sortino: Sortino ratio

    Returns:
        Sortino component between 0 and 15
    """
    if not _is_valid_number(sortino):
        return 0.0

    clamped = max(0, min(4, sortino))
    return clamped / 4 * 15


def calculate_drawdown_component(max_drawdown: float) -> float:
    """
    Calculate drawdown component (inverted).

    Drawdown = 0-10 points (0-50% inverted)
    0% → 10 points (best)
    50% → 0 points (worst)

    Args:
        max_drawdown: Maximum drawdown percentage (0-100)

    Returns:
        Drawdown component between 0 and 10
    """
    if max_drawdown <= 0:
        return 10.0
    if max_drawdown >= 50:
        return 0.0

    # Inverted: lower drawdown = higher score
    return (50 - max_drawdown) / 50 * 10


def calculate_exit_efficiency_component(exit_efficiency: float) -> float:
    """
    Calculate exit efficiency component.

    Exit Efficiency = 0-10 points (0.3-0.8 range)
    0.3 → 0 points
    0.8 → 10 points

    Args:
        exit_efficiency: Exit efficiency ratio (0-1)

    Returns:
        Exit efficiency component between 0 and 10
    """
    if exit_efficiency <= 0.3:
        return 0.0
    if exit_efficiency >= 0.8:
        return 10.0

    return (exit_efficiency - 0.3) / 0.5 * 10


def calculate_loss_sizing_component(loss_sizing: float) -> float:
    """
    Calculate loss sizing component.

    Loss Sizing = 0-5 points (0.5-2.0 range)
    0.5 → 0 points
    2.0 → 5 points

    Args:
        loss_sizing: Loss sizing ratio

    Returns:
        Loss sizing component between 0 and 5
    """
    if loss_sizing <= 0.5:
        return 0.0
    if loss_sizing >= 2.0:
        return 5.0

    return (loss_sizing - 0.5) / 1.5 * 5


def calculate_ai_accuracy_component(ai_accuracy: float) -> float:
    """
    Calculate AI accuracy component.

    AI Accuracy = 0-5 points (0.4-0.8 range)
    0.4 → 0 points
    0.8 → 5 points

    Args:
        ai_accuracy: AI prediction accuracy (0-1)

    Returns:
        AI accuracy component between 0 and 5
    """
    if ai_accuracy <= 0.4:
        return 0.0
    if ai_accuracy >= 0.8:
        return 5.0

    return (ai_accuracy - 0.4) / 0.4 * 5


# =============================================================================
# Metrics Calculation from Trades
# =============================================================================


def calculate_win_rate(trades: list[TradeData]) -> float:
    """Calculate win rate percentage from trades."""
    if not trades:
        return 0.0

    wins = sum(1 for t in trades if t.is_win)
    return (wins / len(trades)) * 100


def calculate_sortino(trades: list[TradeData]) -> float:
    """
    Calculate Sortino ratio from trades.

    Sortino = (mean_return - risk_free) / downside_deviation

    Args:
        trades: List of trade data

    Returns:
        Sortino ratio (0 if insufficient data or no downside)
    """
    if len(trades) < 2:
        return 0.0

    pnls = [t.pnl_pct for t in trades if _is_valid_number(t.pnl_pct)]

    if len(pnls) < 2:
        return 0.0

    mean_return = sum(pnls) / len(pnls)

    # Downside deviation (only negative returns)
    negative_returns = [p for p in pnls if p < 0]

    if not negative_returns:
        # No losses = infinite Sortino, cap at 4
        return 4.0

    sum_squared = sum(p**2 for p in negative_returns)
    # FIX: Divide by count of negative returns, not total trades (CALC-001)
    downside_dev = math.sqrt(sum_squared / len(negative_returns)) if negative_returns else 0.0

    if downside_dev == 0:
        return 4.0 if mean_return > 0 else 0.0

    sortino = mean_return / downside_dev

    # Bound to reasonable range
    return max(0, min(4, sortino))


def calculate_max_drawdown(trades: list[TradeData]) -> float:
    """
    Calculate maximum drawdown from trades.

    Args:
        trades: List of trade data

    Returns:
        Maximum drawdown as a percentage (0-100)
    """
    if not trades:
        return 0.0

    pnls = [t.pnl_pct for t in trades if _is_valid_number(t.pnl_pct)]

    if not pnls:
        return 0.0

    # Build equity curve
    equity = 100.0  # Start at 100
    peak = equity
    max_dd = 0.0

    for pnl_pct in pnls:
        # FIX: Prevent negative equity (can happen with >100% loss) (CALC-005)
        equity = max(0.0, equity * (1 + pnl_pct / 100))
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

    return min(100, max_dd)


# =============================================================================
# Main Fitness Calculation
# =============================================================================


def calculate_fitness(
    trades: list[TradeData],
    benchmark_pct: float = 0.0,
    calibration_score: float = 0.5,
    exit_efficiency: float = 0.55,
    loss_sizing: float = 1.25,
    ai_accuracy: float = 0.6,
) -> FitnessResult:
    """
    Calculate fitness score using the 100-point model.

    Formula: (signed + unsigned) × EV_multiplier, clamped to [0, 100]

    Args:
        trades: List of trade data
        benchmark_pct: Benchmark comparison (-100 to +100)
        calibration_score: Calibration accuracy (0-1)
        exit_efficiency: Exit efficiency ratio (0-1)
        loss_sizing: Loss sizing ratio
        ai_accuracy: AI prediction accuracy (0-1)

    Returns:
        FitnessResult with score, tier, metrics, and component breakdown
    """
    # Filter out invalid trades
    valid_trades = _filter_valid_trades(trades)

    # Handle no trades case
    if not valid_trades:
        return _zero_fitness_result("No valid trades")

    # Calculate EV
    ev = calculate_ev(valid_trades)

    # EV Gate: Block negative expectancy
    if not ev_gate(ev):
        return _zero_fitness_result("EV gate failed")

    # Calculate EV multiplier
    ev_multiplier = calculate_ev_multiplier(ev)

    # Calculate metrics
    win_rate = calculate_win_rate(valid_trades)
    sortino = calculate_sortino(valid_trades)
    max_drawdown = calculate_max_drawdown(valid_trades)

    metrics = FitnessMetrics(
        ev=ev,
        win_rate=win_rate,
        sortino=sortino,
        max_drawdown=max_drawdown,
        alpha=benchmark_pct,
        calibration=calibration_score,
        exit_efficiency=exit_efficiency,
        loss_sizing=loss_sizing,
        ai_accuracy=ai_accuracy,
    )

    # Calculate components
    alpha_component = calculate_alpha_component(benchmark_pct)
    calibration_component = calculate_calibration_component(calibration_score)
    win_rate_component = calculate_win_rate_component(win_rate)
    sortino_component = calculate_sortino_component(sortino)
    drawdown_component = calculate_drawdown_component(max_drawdown)
    exit_eff_component = calculate_exit_efficiency_component(exit_efficiency)
    loss_size_component = calculate_loss_sizing_component(loss_sizing)
    ai_acc_component = calculate_ai_accuracy_component(ai_accuracy)

    # Sum components
    raw_score = (
        alpha_component
        + calibration_component
        + win_rate_component
        + sortino_component
        + drawdown_component
        + exit_eff_component
        + loss_size_component
        + ai_acc_component
    )

    # Apply EV multiplier
    weighted_score = raw_score * ev_multiplier

    # Clamp to [0, 100]
    fitness_score = max(0.0, min(100.0, weighted_score))

    # Determine tier
    tier = get_tier(fitness_score)

    return FitnessResult(
        fitness_score=fitness_score,
        tier=tier,
        metrics=metrics,
        ev_multiplier=ev_multiplier,
        component_breakdown={
            "alpha": alpha_component,
            "calibration": calibration_component,
            "win_rate": win_rate_component,
            "sortino": sortino_component,
            "drawdown": drawdown_component,
            "exit_efficiency": exit_eff_component,
            "loss_sizing": loss_size_component,
            "ai_accuracy": ai_acc_component,
            "raw_total": raw_score,
            "ev_multiplier": ev_multiplier,
        },
    )


# =============================================================================
# Tier Mapping
# =============================================================================


def get_tier(fitness_score: float) -> str:
    """
    Map fitness score to tier.

    < 40: DIES
    40-79: SURVIVES
    80+: PROMOTED

    Args:
        fitness_score: Fitness score [0, 100]

    Returns:
        Tier string
    """
    if fitness_score < 40:
        return "DIES"
    elif fitness_score < 80:
        return "SURVIVES"
    else:
        return "PROMOTED"


def fitness_below_threshold(fitness_score: float, threshold: float = 40.0) -> bool:
    """Check if fitness is below death threshold."""
    return fitness_score < threshold


def fitness_survives(fitness_score: float) -> bool:
    """Check if fitness is in survival range (40-79)."""
    return 40 <= fitness_score < 80


def fitness_promoted(fitness_score: float) -> bool:
    """Check if fitness is in promotion range (80+)."""
    return fitness_score >= 80


# =============================================================================
# Helpers
# =============================================================================


def _is_valid_number(value: Any) -> bool:
    """Check if value is a valid finite number."""
    if value is None:
        return False
    try:
        f = float(value)
        return math.isfinite(f)
    except (TypeError, ValueError):
        return False


def _filter_valid_trades(trades: list[TradeData]) -> list[TradeData]:
    """Filter out trades with invalid PnL values."""
    if not trades:
        return []

    return [t for t in trades if _is_valid_number(t.pnl) and _is_valid_number(t.pnl_pct)]


def _zero_fitness_result(reason: str) -> FitnessResult:
    """Create a zero fitness result."""
    return FitnessResult(
        fitness_score=0.0,
        tier="DIES",
        metrics=FitnessMetrics(
            ev=0.0,
            win_rate=0.0,
            sortino=0.0,
            max_drawdown=0.0,
            alpha=0.0,
            calibration=0.5,
            exit_efficiency=0.0,
            loss_sizing=0.0,
            ai_accuracy=0.0,
        ),
        ev_multiplier=0.0,
        component_breakdown={"reason": 0.0},
    )


# =============================================================================
# Simple Calculate Fitness (for backwards compatibility)
# =============================================================================


def simple_calculate_fitness(
    total_pnl_pct: float,
    trade_count: int,
    win_rate: float = 50.0,
    max_drawdown: float = 10.0,
    sortino: float = 1.0,
) -> float:
    """
    Simplified fitness calculation from aggregate metrics.

    Used when full trade history isn't available.

    Args:
        total_pnl_pct: Total PnL percentage
        trade_count: Number of trades
        win_rate: Win rate percentage
        max_drawdown: Max drawdown percentage
        sortino: Sortino ratio

    Returns:
        Fitness score [0, 100]
    """
    if trade_count == 0:
        return 0.0

    # EV approximation from total PnL
    ev = total_pnl_pct / trade_count if trade_count > 0 else 0.0

    # EV Gate
    if ev <= 0:
        return 0.0

    # EV Multiplier
    ev_mult = calculate_ev_multiplier(ev)

    # Components (using defaults for missing data)
    alpha_component = 0.0  # No benchmark data
    calibration_component = 0.0  # Baseline
    win_rate_component = calculate_win_rate_component(win_rate)
    sortino_component = calculate_sortino_component(sortino)
    drawdown_component = calculate_drawdown_component(max_drawdown)
    exit_eff_component = 5.0  # Default middle
    loss_size_component = 2.5  # Default middle
    ai_acc_component = 2.5  # Default middle

    raw_score = (
        alpha_component
        + calibration_component
        + win_rate_component
        + sortino_component
        + drawdown_component
        + exit_eff_component
        + loss_size_component
        + ai_acc_component
    )

    weighted_score = raw_score * ev_mult

    return max(0.0, min(100.0, weighted_score))
