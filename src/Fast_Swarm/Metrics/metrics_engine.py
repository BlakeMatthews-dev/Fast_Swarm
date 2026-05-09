"""
Metrics Engine - QuantStats-backed calculations.

18 wrapper functions that:
1. Accept list[float] | pd.Series
2. Return bounded float, never NaN
3. Handle edge cases (empty, single, zeros)
4. Delegate to QuantStats where appropriate, custom where needed
"""

import math
from typing import Union

import numpy as np
import pandas as pd
import quantstats as qs


# Type alias for inputs
Returns = Union[list[float], pd.Series]


def _to_series(returns: Returns) -> pd.Series:
    """Convert input to pd.Series with DatetimeIndex (QuantStats requirement)."""
    if isinstance(returns, pd.Series):
        if not isinstance(returns.index, pd.DatetimeIndex):
            returns = returns.copy()
            returns.index = pd.date_range(start="2020-01-01", periods=len(returns), freq="D")
        return returns
    index = pd.date_range(start="2020-01-01", periods=len(returns), freq="D")
    return pd.Series(returns, index=index, dtype=float)


def _safe_float(value: float, default: float = 0.0) -> float:
    """Ensure output is finite float, never NaN/Inf."""
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return default
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


# =============================================================================
# Core Metrics (replacing custom implementations)
# =============================================================================


def calculate_sortino(returns: Returns, target: float = 0.0) -> float:
    """
    Sortino ratio: risk-adjusted return using downside deviation only.

    Args:
        returns: Period returns as decimals.
        target: Minimum acceptable return.

    Returns:
        Annualized Sortino ratio. 0.0 for insufficient data.
    """
    if not _has_enough_data(returns, 2):
        return 0.0

    series = _to_series(returns)
    result = qs.stats.sortino(series, rf=target)
    return _safe_float(result)


def calculate_sharpe(returns: Returns, risk_free_rate: float = 0.0) -> float:
    """
    Sharpe ratio: risk-adjusted return using total standard deviation.

    Returns:
        Annualized Sharpe ratio. 0.0 for insufficient data.
    """
    if not _has_enough_data(returns, 2):
        return 0.0

    series = _to_series(returns)
    result = qs.stats.sharpe(series, rf=risk_free_rate)
    return _safe_float(result)


def calculate_max_drawdown(returns: Returns) -> float:
    """
    Maximum drawdown from peak to trough.

    Returns:
        Positive decimal (0.15 = 15% drawdown). 0.0 for insufficient data.
    """
    if not _has_enough_data(returns, 1):
        return 0.0

    series = _to_series(returns)
    result = qs.stats.max_drawdown(series)

    # QuantStats returns negative (e.g., -0.15), we want positive
    value = _safe_float(result)
    return min(1.0, abs(value))


def calculate_calmar(returns: Returns) -> float:
    """
    Calmar ratio: annualized return / max drawdown.

    Returns:
        Calmar ratio. 0.0 for insufficient data.
    """
    if not _has_enough_data(returns, 2):
        return 0.0

    series = _to_series(returns)
    result = qs.stats.calmar(series)
    return _safe_float(result)


def calculate_kelly(returns: Returns) -> float:
    """
    Kelly criterion: optimal bet fraction.

    Returns:
        Kelly fraction (can be negative for losing strategies). 0.0 for insufficient data.
    """
    if not _has_enough_data(returns, 2):
        return 0.0

    series = _to_series(returns)
    result = qs.stats.kelly_criterion(series)
    return _safe_float(result)


def calculate_cagr(returns: Returns) -> float:
    """
    Compound Annual Growth Rate.

    Returns:
        CAGR as decimal. 0.0 for insufficient data.
    """
    if not _has_enough_data(returns, 1):
        return 0.0

    series = _to_series(returns)
    result = qs.stats.cagr(series)
    return _safe_float(result)


def calculate_win_rate(returns: Returns) -> float:
    """
    Fraction of positive return periods.

    Returns:
        Win rate as decimal (0.70 = 70%). 0.5 for empty data.
    """
    if not _has_enough_data(returns, 1):
        return 0.5

    data = _to_list(returns)
    wins = sum(1 for r in data if r > 0)
    return wins / len(data)


def calculate_expectancy(returns: Returns) -> float:
    """
    Expected value per trade: (Win% * AvgWin) - (Loss% * AvgLoss).

    Returns:
        Expectancy as decimal. 0.0 for empty data.
    """
    if not _has_enough_data(returns, 1):
        return 0.0

    data = _to_list(returns)
    wins = [r for r in data if r > 0]
    losses = [r for r in data if r <= 0]

    if not wins and not losses:
        return 0.0

    win_rate = len(wins) / len(data)
    loss_rate = len(losses) / len(data)

    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0

    return (win_rate * avg_win) - (loss_rate * avg_loss)


def calculate_profit_factor(returns: Returns) -> float:
    """
    Profit factor: gross wins / gross losses.

    Returns:
        Profit factor (>1.0 = profitable). 0.0 for empty data.
    """
    if not _has_enough_data(returns, 1):
        return 0.0

    data = _to_list(returns)
    gross_wins = sum(r for r in data if r > 0)
    gross_losses = abs(sum(r for r in data if r < 0))

    if gross_losses == 0:
        return gross_wins if gross_wins > 0 else 0.0

    return gross_wins / gross_losses


def calculate_alpha(strategy_returns: Returns, benchmark_returns: Returns) -> float:
    """
    Alpha: excess compound return over benchmark.

    CUSTOM: compound subtraction, not CAPM regression.
    Alpha = (1 + r_strategy)^n - (1 + r_benchmark)^n

    Returns:
        Alpha as percentage. 0.0 for empty data.
    """
    if not _has_enough_data(strategy_returns, 1) or not _has_enough_data(benchmark_returns, 1):
        return 0.0

    strat = _to_list(strategy_returns)
    bench = _to_list(benchmark_returns)

    # Compound returns
    strat_total = 1.0
    for r in strat:
        strat_total *= (1 + r)

    bench_total = 1.0
    for r in bench:
        bench_total *= (1 + r)

    alpha_pct = (strat_total - bench_total) * 100
    return max(-100.0, min(100.0, alpha_pct))


# =============================================================================
# New Risk Metrics
# =============================================================================


def calculate_value_at_risk(returns: Returns, confidence: float = 0.05) -> float:
    """
    Value at Risk: worst expected loss at given confidence level.

    Uses empirical percentile (non-parametric).

    Args:
        returns: Period returns.
        confidence: Tail probability (default 5% = 95th percentile VaR).

    Returns:
        VaR as decimal (negative = loss). 0.0 for insufficient data.
    """
    if not _has_enough_data(returns, 2):
        return 0.0

    series = _to_series(returns)
    result = series.quantile(confidence)
    return _safe_float(result)


def calculate_cvar(returns: Returns, confidence: float = 0.05) -> float:
    """
    Conditional Value at Risk: expected loss beyond VaR (tail average).

    CVaR = mean of returns below VaR threshold. Always <= VaR.

    Args:
        returns: Period returns.
        confidence: Tail probability (default 5%).

    Returns:
        CVaR as decimal (negative = loss). 0.0 for insufficient data.
    """
    if not _has_enough_data(returns, 2):
        return 0.0

    series = _to_series(returns)
    var = series.quantile(confidence)
    tail = series[series <= var]
    if tail.empty:
        return _safe_float(var)
    # Enforce CVaR <= VaR invariant (float precision can violate this)
    return min(_safe_float(tail.mean()), _safe_float(var))


def calculate_risk_of_ruin(returns: Returns) -> float:
    """
    Risk of ruin: probability of total capital loss.

    Uses Kelly-based approximation:
    RoR = ((1 - edge) / (1 + edge))^units
    where edge = win_rate * avg_win/avg_loss - (1 - win_rate)

    Returns:
        Probability 0.0-1.0. 0.0 for insufficient/winning data.
    """
    if not _has_enough_data(returns, 5):
        return 0.0

    data = _to_list(returns)
    wins = [r for r in data if r > 0]
    losses = [r for r in data if r < 0]

    if not wins or not losses:
        return 0.0 if wins else 1.0

    win_rate = len(wins) / len(data)
    avg_win = sum(wins) / len(wins)
    avg_loss = abs(sum(losses) / len(losses))

    if avg_loss == 0:
        return 0.0

    payoff_ratio = avg_win / avg_loss
    edge = win_rate * payoff_ratio - (1 - win_rate)

    if edge >= 1.0:
        return 0.0
    if edge <= 0:
        return min(1.0, 0.5 + abs(edge) * 2)  # Bad edge -> high ruin

    # Kelly-based ruin formula
    q = (1 - edge) / (1 + edge)
    # Assume 20 "units" of capital at risk
    ruin = q ** 20
    return max(0.0, min(1.0, ruin))


def calculate_consecutive_losses(returns: Returns) -> int:
    """
    Maximum consecutive losing periods.

    Returns:
        Count of max consecutive losses. 0 for empty data.
    """
    if not _has_enough_data(returns, 1):
        return 0

    data = _to_list(returns)
    max_streak = 0
    current_streak = 0

    for r in data:
        if r < 0:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0

    return max_streak


def calculate_recovery_factor(returns: Returns) -> float:
    """
    Recovery factor: total return / max drawdown.

    Returns:
        Recovery factor. 0.0 for insufficient data.
    """
    if not _has_enough_data(returns, 2):
        return 0.0

    series = _to_series(returns)
    result = qs.stats.recovery_factor(series)
    return _safe_float(result)


def calculate_exposure(returns: Returns) -> float:
    """
    Exposure: fraction of time in market (non-zero returns).

    Returns:
        Exposure 0.0-1.0. 0.0 for empty data.
    """
    if not _has_enough_data(returns, 1):
        return 0.0

    data = _to_list(returns)
    non_zero = sum(1 for r in data if r != 0.0)
    return non_zero / len(data)


# =============================================================================
# Signal/Shape Metrics
# =============================================================================


def calculate_skew(returns: Returns) -> float:
    """
    Skewness of return distribution.

    Positive = right tail (good for bulls).
    Negative = left tail (common in crashes).

    Returns:
        Skewness. 0.0 for insufficient data.
    """
    if not _has_enough_data(returns, 3):
        return 0.0

    series = _to_series(returns)
    result = qs.stats.skew(series)
    return _safe_float(result)


def calculate_kurtosis(returns: Returns) -> float:
    """
    Kurtosis of return distribution (excess kurtosis).

    Higher = fatter tails = more extreme events.

    Returns:
        Excess kurtosis. 0.0 for insufficient data.
    """
    if not _has_enough_data(returns, 4):
        return 0.0

    series = _to_series(returns)
    result = qs.stats.kurtosis(series)
    return _safe_float(result)


# =============================================================================
# Internal Helpers
# =============================================================================


def _has_enough_data(returns: Returns, minimum: int) -> bool:
    """Check if we have enough data points."""
    if returns is None:
        return False
    if isinstance(returns, pd.Series):
        return len(returns) >= minimum
    return len(returns) >= minimum


def _to_list(returns: Returns) -> list[float]:
    """Convert to list."""
    if isinstance(returns, pd.Series):
        return returns.tolist()
    return list(returns)
