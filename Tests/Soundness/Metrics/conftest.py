"""
Shared fixtures for metrics parity tests.

Provides deterministic return series for comparing our implementations
against QuantStats ground truth.
"""

import numpy as np
import pandas as pd
import pytest


# =============================================================================
# Return Series Generators (deterministic seeds)
# =============================================================================


@pytest.fixture
def positive_returns() -> list[float]:
    """Consistently profitable returns (daily, 100 periods)."""
    rng = np.random.default_rng(42)
    # Mean positive, low vol
    returns = rng.normal(0.002, 0.01, 100).tolist()
    return returns


@pytest.fixture
def negative_returns() -> list[float]:
    """Consistently losing returns (daily, 100 periods)."""
    rng = np.random.default_rng(43)
    returns = rng.normal(-0.003, 0.015, 100).tolist()
    return returns


@pytest.fixture
def mixed_returns() -> list[float]:
    """Realistic mixed returns (daily, 200 periods)."""
    rng = np.random.default_rng(44)
    returns = rng.normal(0.0005, 0.02, 200).tolist()
    return returns


@pytest.fixture
def zero_returns() -> list[float]:
    """All zeros - edge case for division safety."""
    return [0.0] * 50


@pytest.fixture
def single_return() -> list[float]:
    """Single return - edge case."""
    return [0.05]


@pytest.fixture
def volatile_returns() -> list[float]:
    """High volatility returns (daily, 150 periods)."""
    rng = np.random.default_rng(45)
    returns = rng.normal(0.001, 0.05, 150).tolist()
    return returns


@pytest.fixture
def trending_up_returns() -> list[float]:
    """Trending upward (daily, 120 periods)."""
    rng = np.random.default_rng(46)
    base = np.linspace(0.001, 0.005, 120)
    noise = rng.normal(0, 0.005, 120)
    returns = (base + noise).tolist()
    return returns


@pytest.fixture
def crash_scenario_returns() -> list[float]:
    """Bull run followed by crash (daily, 100 periods)."""
    rng = np.random.default_rng(47)
    # 80 days of gains
    bull = rng.normal(0.003, 0.01, 80)
    # 20 days of crash
    crash = rng.normal(-0.05, 0.03, 20)
    returns = np.concatenate([bull, crash]).tolist()
    return returns


@pytest.fixture
def no_downside_returns() -> list[float]:
    """All positive returns - tests zero downside deviation."""
    rng = np.random.default_rng(48)
    returns = np.abs(rng.normal(0.005, 0.003, 50)).tolist()
    return returns


# =============================================================================
# Pandas Series Converters
# =============================================================================


@pytest.fixture
def to_series():
    """Convert list to pandas Series with DatetimeIndex (QuantStats requires it)."""
    def _convert(returns: list[float]) -> pd.Series:
        index = pd.date_range(start="2020-01-01", periods=len(returns), freq="D")
        return pd.Series(returns, index=index, dtype=float)
    return _convert


# =============================================================================
# Equity Curve Generators
# =============================================================================


@pytest.fixture
def equity_from_returns():
    """Build equity curve from returns list."""
    def _build(returns: list[float], start: float = 1.0) -> list[float]:
        equity = [start]
        for r in returns:
            equity.append(equity[-1] * (1 + r))
        return equity
    return _build


# =============================================================================
# Trade Generators (for win rate / expectancy / profit factor)
# =============================================================================


@pytest.fixture
def winning_trades() -> list[float]:
    """PnL percentages: 70% win rate, positive EV."""
    rng = np.random.default_rng(50)
    wins = rng.uniform(0.5, 5.0, 70).tolist()
    losses = rng.uniform(-4.0, -0.3, 30).tolist()
    trades = wins + losses
    rng.shuffle(trades)
    return trades.tolist() if hasattr(trades, 'tolist') else list(trades)


@pytest.fixture
def losing_trades() -> list[float]:
    """PnL percentages: 30% win rate, negative EV."""
    rng = np.random.default_rng(51)
    wins = rng.uniform(0.5, 3.0, 30).tolist()
    losses = rng.uniform(-5.0, -0.5, 70).tolist()
    trades = wins + losses
    rng.shuffle(trades)
    return trades.tolist() if hasattr(trades, 'tolist') else list(trades)


@pytest.fixture
def breakeven_trades() -> list[float]:
    """PnL percentages: ~50% win rate, near-zero EV."""
    rng = np.random.default_rng(52)
    wins = rng.uniform(0.5, 2.0, 50).tolist()
    losses = rng.uniform(-2.0, -0.5, 50).tolist()
    trades = wins + losses
    rng.shuffle(trades)
    return trades.tolist() if hasattr(trades, 'tolist') else list(trades)
