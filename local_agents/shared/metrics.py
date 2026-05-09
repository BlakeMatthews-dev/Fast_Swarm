"""
Trading Metrics - V3 Parity.

Calculates performance metrics used in fitness scoring:
- Sortino Ratio (downside deviation)
- Max Drawdown
- Calibration Score (confidence vs outcome)
- Exit Efficiency (captured vs available profit)
- Loss Sizing Ratio (avg loss size vs avg win size)
"""

import math
from dataclasses import dataclass

# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class Trade:
    """Trade record for metrics calculation."""

    trade_id: str = ""
    pnl_pct: float = 0.0
    entry_confidence: float = 0.5
    mfe_pct: float = 0.0  # Maximum Favorable Excursion
    mae_pct: float = 0.0  # Maximum Adverse Excursion
    position_size_pct: float = 1.0
    won: bool = False


# =============================================================================
# Sortino Ratio
# =============================================================================


def calculate_sortino_ratio(returns: list[float], target: float = 0.0, annualization_factor: float = 252.0) -> float:
    """
    Calculate Sortino ratio (risk-adjusted return using downside deviation).

    Sortino = (Mean Return - Target) / Downside Deviation

    Args:
        returns: List of period returns (as decimals, e.g., 0.02 for 2%).
        target: Minimum acceptable return (default 0).
        annualization_factor: Factor for annualizing (252 for daily, 52 for weekly).

    Returns:
        Sortino ratio (capped at reasonable bounds).
    """
    if not returns or len(returns) < 2:
        return 0.0

    # Calculate mean return
    mean_return = sum(returns) / len(returns)

    # Calculate downside deviation (only negative deviations from target)
    downside_returns = [min(0, r - target) for r in returns]
    downside_squared = [r**2 for r in downside_returns]

    if not downside_squared:
        return 0.0

    downside_variance = sum(downside_squared) / len(downside_squared)
    downside_deviation = math.sqrt(downside_variance)

    if downside_deviation < 0.0001:
        # No downside risk - cap at reasonable max
        return 4.0 if mean_return > target else 0.0

    sortino = (mean_return - target) / downside_deviation

    # Annualize
    sortino_annualized = sortino * math.sqrt(annualization_factor)

    # Cap at reasonable bounds
    return max(-4.0, min(4.0, sortino_annualized))


# =============================================================================
# Max Drawdown
# =============================================================================


def calculate_max_drawdown(equity_curve: list[float]) -> float:
    """
    Calculate maximum drawdown from equity curve.

    Max Drawdown = max((peak - trough) / peak)

    Args:
        equity_curve: List of equity values over time.

    Returns:
        Max drawdown as decimal (0.15 = 15% drawdown).
    """
    if not equity_curve or len(equity_curve) < 2:
        return 0.0

    peak = equity_curve[0]
    max_dd = 0.0

    for value in equity_curve:
        if value > peak:
            peak = value

        if peak > 0:
            drawdown = (peak - value) / peak
            max_dd = max(max_dd, drawdown)

    # Cap at 100%
    return min(1.0, max_dd)


def calculate_max_drawdown_from_returns(returns: list[float]) -> float:
    """
    Calculate max drawdown from returns (builds equity curve internally).

    Args:
        returns: List of period returns as decimals.

    Returns:
        Max drawdown as decimal.
    """
    if not returns:
        return 0.0

    # Build equity curve from returns
    equity = [1.0]  # Start at 1.0
    for r in returns:
        equity.append(equity[-1] * (1 + r))

    return calculate_max_drawdown(equity)


# =============================================================================
# Calibration Score
# =============================================================================


def calculate_calibration_score(trades: list[Trade]) -> float:
    """
    Calculate calibration score (how well confidence predicts outcomes).

    V3 Formula: Measures correlation between entry_confidence and actual win.
    Perfect calibration = 1.0 (high confidence trades win, low confidence lose)
    Random = 0.5
    Inverse = 0.0 (high confidence trades lose)

    Args:
        trades: List of Trade objects with entry_confidence and won fields.

    Returns:
        Calibration score 0.0-1.0.
    """
    if not trades or len(trades) < 5:
        return 0.5  # Neutral default

    # Bin trades by confidence quartiles
    sorted_trades = sorted(trades, key=lambda t: t.entry_confidence)
    n = len(sorted_trades)
    quartile_size = max(1, n // 4)

    # Calculate win rate per quartile
    quartile_win_rates = []
    for i in range(4):
        start = i * quartile_size
        end = start + quartile_size if i < 3 else n
        quartile = sorted_trades[start:end]

        if quartile:
            wins = sum(1 for t in quartile if t.won)
            win_rate = wins / len(quartile)
            quartile_win_rates.append(win_rate)

    if len(quartile_win_rates) < 2:
        return 0.5

    # Check if win rate increases with confidence (monotonic)
    # Perfect: Q1 < Q2 < Q3 < Q4
    increases = 0
    for i in range(len(quartile_win_rates) - 1):
        if quartile_win_rates[i + 1] > quartile_win_rates[i]:
            increases += 1
        elif quartile_win_rates[i + 1] == quartile_win_rates[i]:
            increases += 0.5  # Partial credit for ties

    # Normalize to 0-1
    max_increases = len(quartile_win_rates) - 1
    if max_increases == 0:
        return 0.5

    calibration = increases / max_increases

    # Shift to 0.5-1.0 scale (0.5 = random, 1.0 = perfect)
    return 0.5 + (calibration * 0.5)


# =============================================================================
# Exit Efficiency
# =============================================================================


def calculate_exit_efficiency(trades: list[Trade]) -> float:
    """
    Calculate exit efficiency (how much profit captured vs available).

    V3 Formula: avg(pnl / mfe) for winning trades
    Perfect exit = 1.0 (captured all MFE)
    Early exit = 0.5 (captured half of available profit)

    Args:
        trades: List of Trade objects with pnl_pct and mfe_pct.

    Returns:
        Exit efficiency 0.0-1.0.
    """
    winning_trades = [t for t in trades if t.pnl_pct > 0 and t.mfe_pct > 0]

    if not winning_trades:
        return 0.5  # Neutral default

    efficiencies = []
    for trade in winning_trades:
        if trade.mfe_pct > 0:
            efficiency = trade.pnl_pct / trade.mfe_pct
            # Cap at 1.0 (can't capture more than MFE)
            efficiencies.append(min(1.0, max(0.0, efficiency)))

    if not efficiencies:
        return 0.5

    return sum(efficiencies) / len(efficiencies)


# =============================================================================
# Loss Sizing Ratio
# =============================================================================


def calculate_loss_sizing_ratio(trades: list[Trade]) -> float:
    """
    Calculate loss sizing ratio (are losses smaller than wins?).

    V3 Formula: avg_win_size / avg_loss_size
    > 1.0 = Good (wins bigger than losses)
    = 1.0 = Neutral
    < 1.0 = Bad (losses bigger than wins)

    Args:
        trades: List of Trade objects with pnl_pct.

    Returns:
        Loss sizing ratio (capped at 0.0-3.0).
    """
    wins = [t for t in trades if t.pnl_pct > 0]
    losses = [t for t in trades if t.pnl_pct < 0]

    if not wins or not losses:
        return 1.0  # Neutral default

    avg_win = sum(t.pnl_pct for t in wins) / len(wins)
    avg_loss = abs(sum(t.pnl_pct for t in losses) / len(losses))

    if avg_loss < 0.0001:
        return 3.0  # Max (no real losses)

    ratio = avg_win / avg_loss

    # Cap at reasonable bounds
    return max(0.0, min(3.0, ratio))


# =============================================================================
# Win Rate
# =============================================================================


def calculate_win_rate(trades: list[Trade]) -> float:
    """
    Calculate win rate percentage.

    Args:
        trades: List of Trade objects.

    Returns:
        Win rate as percentage (0-100).
    """
    if not trades:
        return 50.0  # Neutral default

    wins = sum(1 for t in trades if t.pnl_pct > 0)
    return (wins / len(trades)) * 100


# =============================================================================
# Expectancy
# =============================================================================


def calculate_expectancy(trades: list[Trade]) -> float:
    """
    Calculate expected value per trade.

    Expectancy = (Win% * Avg Win) - (Loss% * Avg Loss)

    Args:
        trades: List of Trade objects.

    Returns:
        Expectancy as percentage.
    """
    if not trades:
        return 0.0

    wins = [t for t in trades if t.pnl_pct > 0]
    losses = [t for t in trades if t.pnl_pct <= 0]

    if not wins and not losses:
        return 0.0

    win_rate = len(wins) / len(trades)
    loss_rate = len(losses) / len(trades)

    avg_win = sum(t.pnl_pct for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(t.pnl_pct for t in losses) / len(losses)) if losses else 0

    expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
    return expectancy


# =============================================================================
# Alpha Calculation
# =============================================================================


def calculate_alpha(strategy_returns: list[float], benchmark_returns: list[float]) -> float:
    """
    Calculate alpha (excess return over benchmark).

    Alpha = Strategy Return - Benchmark Return

    Args:
        strategy_returns: List of strategy period returns.
        benchmark_returns: List of benchmark period returns.

    Returns:
        Alpha as percentage (-100 to 100, capped).
    """
    if not strategy_returns or not benchmark_returns:
        return 0.0

    # Use total return
    strategy_total = 1.0
    for r in strategy_returns:
        strategy_total *= 1 + r
    strategy_return = (strategy_total - 1) * 100

    benchmark_total = 1.0
    for r in benchmark_returns:
        benchmark_total *= 1 + r
    benchmark_return = (benchmark_total - 1) * 100

    alpha = strategy_return - benchmark_return

    # Cap at reasonable bounds
    return max(-100, min(100, alpha))


# =============================================================================
# Sharpe Ratio
# =============================================================================


def calculate_sharpe_ratio(
    returns: list[float], risk_free_rate: float = 0.0, annualization_factor: float = 252.0
) -> float:
    """
    Calculate Sharpe ratio.

    Sharpe = (Mean Return - Risk Free Rate) / Std Dev

    Args:
        returns: List of period returns.
        risk_free_rate: Risk-free rate per period.
        annualization_factor: Factor for annualizing.

    Returns:
        Sharpe ratio (capped at reasonable bounds).
    """
    if not returns or len(returns) < 2:
        return 0.0

    mean_return = sum(returns) / len(returns)

    # Calculate standard deviation
    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
    std_dev = math.sqrt(variance)

    if std_dev < 0.0001:
        return 0.0

    sharpe = (mean_return - risk_free_rate) / std_dev

    # Annualize
    sharpe_annualized = sharpe * math.sqrt(annualization_factor)

    # Cap at reasonable bounds
    return max(-4.0, min(4.0, sharpe_annualized))


# =============================================================================
# Aggregate Metrics
# =============================================================================


@dataclass
class AggregateMetrics:
    """All metrics for an agent/pattern."""

    expectancy_pct: float = 0.0
    alpha_pct: float = 0.0
    win_rate_pct: float = 50.0
    sortino_ratio: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    calibration_score: float = 0.5
    exit_efficiency: float = 0.5
    loss_sizing_ratio: float = 1.0
    trade_count: int = 0


def calculate_all_metrics(trades: list[Trade], benchmark_returns: list[float] | None = None) -> AggregateMetrics:
    """
    Calculate all metrics from a list of trades.

    Args:
        trades: List of Trade objects.
        benchmark_returns: Optional benchmark returns for alpha.

    Returns:
        AggregateMetrics with all calculated values.
    """
    if not trades:
        return AggregateMetrics()

    # Extract returns
    returns = [t.pnl_pct / 100 for t in trades]  # Convert to decimal

    # Calculate all metrics
    metrics = AggregateMetrics(
        expectancy_pct=calculate_expectancy(trades),
        win_rate_pct=calculate_win_rate(trades),
        sortino_ratio=calculate_sortino_ratio(returns),
        sharpe_ratio=calculate_sharpe_ratio(returns),
        max_drawdown_pct=calculate_max_drawdown_from_returns(returns) * 100,
        calibration_score=calculate_calibration_score(trades),
        exit_efficiency=calculate_exit_efficiency(trades),
        loss_sizing_ratio=calculate_loss_sizing_ratio(trades),
        trade_count=len(trades),
    )

    # Calculate alpha if benchmark provided
    if benchmark_returns:
        strategy_returns = returns
        metrics.alpha_pct = calculate_alpha(strategy_returns, benchmark_returns)

    return metrics
