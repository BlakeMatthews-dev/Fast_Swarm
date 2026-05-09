"""
Fast_Swarm Metrics Module.

Provides:
- metrics_engine: 18 QuantStats-backed metric calculations
- metrics_constants: Regime taxonomy, bounds, normalization params
- fitness_model: V4 specialist scoring model
- normalization: Sigmoid, logarithmic, diminishing returns curves
- signal_quality: Mutual information, confidence weighting
"""

from Fast_Swarm.Metrics.metrics_engine import (
    calculate_alpha,
    calculate_calmar,
    calculate_cagr,
    calculate_consecutive_losses,
    calculate_cvar,
    calculate_expectancy,
    calculate_exposure,
    calculate_kelly,
    calculate_kurtosis,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_recovery_factor,
    calculate_risk_of_ruin,
    calculate_sharpe,
    calculate_skew,
    calculate_sortino,
    calculate_value_at_risk,
    calculate_win_rate,
)

__all__ = [
    "calculate_alpha",
    "calculate_calmar",
    "calculate_cagr",
    "calculate_consecutive_losses",
    "calculate_cvar",
    "calculate_expectancy",
    "calculate_exposure",
    "calculate_kelly",
    "calculate_kurtosis",
    "calculate_max_drawdown",
    "calculate_profit_factor",
    "calculate_recovery_factor",
    "calculate_risk_of_ruin",
    "calculate_sharpe",
    "calculate_skew",
    "calculate_sortino",
    "calculate_value_at_risk",
    "calculate_win_rate",
]
