"""
Fitness Service GREEN — V4 Specialist Model.

Drop-in replacement for fitness_service.py (blue) using the V4 specialist
scoring model from Metrics/fitness_model.py.

V4 changes from V3 (blue):
- Hard EV gate: 0.0 for EV <= 0 (not 0.35)
- Diminishing returns normalization for Sortino (not linear)
- Specialist focus: agents scored on performance in BEST regime
- Risk discipline: 35 pts for safety OUTSIDE best regime
- Signal quality: 20 pts for statistical edge + mutual information
- Interaction penalties: multiplicative (fragile, high ruin, low trades)
- Uniqueness: 5 pt tiebreaker for diversity

Activated via: FAST_SWARM_FITNESS_VERSION=green
"""

import math
from dataclasses import dataclass
from typing import Any

from Fast_Swarm.Metrics.fitness_model import (
    calculate_specialist_fitness,
    classify_specialist_regime,
    ev_multiplier as v4_ev_multiplier,
)
from Fast_Swarm.Metrics.metrics_engine import (
    calculate_expectancy,
    calculate_max_drawdown,
    calculate_sortino,
    calculate_win_rate,
)

# Re-export data classes for API compatibility with blue version
from .fitness_service import (
    FitnessMetrics,
    FitnessResult,
    TradeData,
    calculate_ev,
    calculate_ev_multiplier,
    get_tier,
    fitness_below_threshold,
    fitness_survives,
    fitness_promoted,
)


# =============================================================================
# V4 Specialist Metrics Adapter
# =============================================================================


@dataclass
class _SpecialistMetrics:
    """Adapter to provide attribute access for V4 fitness_model functions."""

    sortino: float = 0.0
    alpha_pct: float = 0.0
    expectancy_pct: float = 0.0
    exit_efficiency: float = 0.5
    payoff_ratio: float = 1.0
    exposure: float = 0.0
    max_drawdown_pct: float = 0.0
    risk_of_ruin: float = 0.0
    max_consecutive_losses: int = 0
    n_trades: int = 0


def _trades_to_returns(trades: list[TradeData]) -> list[float]:
    """Convert TradeData list to decimal returns."""
    return [
        t.pnl_pct / 100.0
        for t in trades
        if t.pnl_pct is not None and math.isfinite(t.pnl_pct)
    ]


def _compute_payoff_ratio(trades: list[TradeData]) -> float:
    """Avg win / avg loss ratio."""
    wins = [t.pnl_pct for t in trades if t.pnl_pct and t.pnl_pct > 0]
    losses = [abs(t.pnl_pct) for t in trades if t.pnl_pct and t.pnl_pct < 0]
    if not wins or not losses:
        return 1.0
    avg_win = sum(wins) / len(wins)
    avg_loss = sum(losses) / len(losses)
    if avg_loss < 0.0001:
        return 3.0
    return min(3.0, avg_win / avg_loss)


def _compute_max_consecutive_losses(trades: list[TradeData]) -> int:
    """Count longest losing streak."""
    max_streak = 0
    current = 0
    for t in trades:
        if t.pnl_pct is not None and t.pnl_pct < 0:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak


def _build_specialist_metrics(trades: list[TradeData], returns: list[float]) -> _SpecialistMetrics:
    """Build a metrics object from trades for the V4 model."""
    if not returns:
        return _SpecialistMetrics()

    sortino = calculate_sortino(returns)
    max_dd = calculate_max_drawdown(returns) * 100  # V4 expects percentage
    win_rate = calculate_win_rate(returns)
    expectancy = calculate_expectancy(returns) * 100  # V4 expects percentage

    return _SpecialistMetrics(
        sortino=max(0, min(4, sortino)),
        alpha_pct=0.0,  # Requires benchmark — 0 if unavailable
        expectancy_pct=expectancy,
        exit_efficiency=0.55,  # Default — requires MFE data
        payoff_ratio=_compute_payoff_ratio(trades),
        exposure=1.0 if trades else 0.0,
        max_drawdown_pct=max_dd,
        risk_of_ruin=0.0,  # Computed by V4 internally if needed
        max_consecutive_losses=_compute_max_consecutive_losses(trades),
        n_trades=len(trades),
    )


def _trades_to_signal_dicts(trades: list[TradeData]) -> list[dict]:
    """Convert TradeData to dicts with entry_confidence and outcome for signal_quality."""
    return [
        {
            "entry_confidence": 0.5,  # TradeData doesn't carry confidence
            "outcome": t.pnl_pct if t.pnl_pct else 0.0,
        }
        for t in trades
    ]


# =============================================================================
# Main V4 Fitness Calculation (API-compatible with blue version)
# =============================================================================


def calculate_fitness(
    trades: list[TradeData],
    benchmark_pct: float = 0.0,
    calibration_score: float = 0.5,
    exit_efficiency: float = 0.55,
    loss_sizing: float = 1.25,
    ai_accuracy: float = 0.6,
    # V4-specific optional parameters
    specialist_type: str | None = None,
    fitness_by_regime: dict[str, float] | None = None,
    population_returns: list[float] | None = None,
) -> FitnessResult:
    """
    Calculate fitness using V4 specialist model.

    API-compatible with blue version's calculate_fitness(). Returns the same
    FitnessResult dataclass. Additional V4 parameters are optional — when not
    provided, the function infers specialist type from trades and uses
    conservative defaults.

    Args:
        trades: List of trade data (same as blue)
        benchmark_pct: Benchmark comparison (used for alpha)
        calibration_score: Calibration accuracy (unused in V4, kept for compat)
        exit_efficiency: Exit efficiency ratio
        loss_sizing: Loss sizing ratio (unused in V4, kept for compat)
        ai_accuracy: AI prediction accuracy (unused in V4, kept for compat)
        specialist_type: Agent's specialist regime (V4-specific)
        fitness_by_regime: Per-regime fitness scores for classification (V4-specific)
        population_returns: Population average returns for uniqueness (V4-specific)

    Returns:
        FitnessResult with score, tier, metrics, and component breakdown
    """
    # Filter invalid trades
    valid_trades = [
        t for t in trades
        if t.pnl_pct is not None and math.isfinite(t.pnl_pct)
        and t.pnl is not None and math.isfinite(t.pnl)
    ]

    if not valid_trades:
        return _zero_result("No valid trades")

    returns = _trades_to_returns(valid_trades)

    if not returns:
        return _zero_result("No valid returns")

    # EV check
    ev = sum(t.pnl_pct for t in valid_trades) / len(valid_trades)
    if ev <= 0:
        return _zero_result("EV gate failed (V4 hard gate)")

    # Determine specialist type
    if specialist_type is None:
        if fitness_by_regime:
            specialist_type = classify_specialist_regime(fitness_by_regime)
        else:
            specialist_type = "bull"  # Default assumption

    # Build metrics objects
    specialist_metrics = _build_specialist_metrics(valid_trades, returns)
    specialist_metrics.alpha_pct = benchmark_pct
    specialist_metrics.exit_efficiency = exit_efficiency

    # Out-of-regime metrics: conservative defaults (full 35 risk pts)
    # When regime-split data is unavailable, assume agent is disciplined
    out_of_regime_metrics = _SpecialistMetrics(
        exposure=0.0,
        max_drawdown_pct=0.0,
        risk_of_ruin=0.0,
        max_consecutive_losses=0,
    )

    # Signal quality trades
    signal_trades = _trades_to_signal_dicts(valid_trades)

    # Calculate V4 specialist fitness
    fitness_score = calculate_specialist_fitness(
        specialist_metrics=specialist_metrics,
        out_of_regime_metrics=out_of_regime_metrics,
        trades=signal_trades,
        agent_returns=returns,
        population_returns=population_returns or [],
        specialist_type=specialist_type,
    )

    # Build compatible FitnessMetrics
    win_rate_pct = sum(1 for t in valid_trades if t.is_win) / len(valid_trades) * 100
    sortino_val = specialist_metrics.sortino
    max_dd_val = specialist_metrics.max_drawdown_pct

    metrics = FitnessMetrics(
        ev=ev,
        win_rate=win_rate_pct,
        sortino=sortino_val,
        max_drawdown=max_dd_val,
        alpha=benchmark_pct,
        calibration=calibration_score,
        exit_efficiency=exit_efficiency,
        loss_sizing=loss_sizing,
        ai_accuracy=ai_accuracy,
    )

    ev_mult = v4_ev_multiplier(ev)
    tier = get_tier(fitness_score)

    return FitnessResult(
        fitness_score=fitness_score,
        tier=tier,
        metrics=metrics,
        ev_multiplier=ev_mult,
        component_breakdown={
            "model": "V4_specialist",
            "specialist_type": specialist_type,
            "specialist_depth": "40pt_max",
            "risk_discipline": "35pt_max",
            "signal_quality": "20pt_max",
            "uniqueness": "5pt_max",
            "ev_multiplier": ev_mult,
            "n_trades": len(valid_trades),
        },
    )


def _zero_result(reason: str) -> FitnessResult:
    """Create a zero fitness result (API-compatible with blue)."""
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
        component_breakdown={"reason": 0.0, "model": "V4_specialist"},
    )
