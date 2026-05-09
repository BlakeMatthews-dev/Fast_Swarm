"""
TDD: Metrics Engine Interface Tests.

Defines the API contract for src/Fast_Swarm/Metrics/metrics_engine.py.
All 18 wrapper functions must:
1. Accept list[float] | pd.Series
2. Return bounded float, never NaN
3. Handle edge cases (empty, single, zeros)
4. Match QuantStats direction for valid inputs
"""

import math

import pandas as pd
import pytest


# =============================================================================
# Import the module under test (will fail until implemented)
# =============================================================================

from Fast_Swarm.Metrics.metrics_engine import (
    calculate_alpha,
    calculate_calmar,
    calculate_cagr,
    calculate_consecutive_losses,
    calculate_cvar,
    calculate_exposure,
    calculate_expectancy,
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


# =============================================================================
# Shared Test Data
# =============================================================================

POSITIVE_RETURNS = [0.01, 0.02, -0.005, 0.015, 0.008, -0.003, 0.012, 0.009, -0.001, 0.007] * 10
NEGATIVE_RETURNS = [-0.01, -0.02, 0.005, -0.015, -0.008, 0.003, -0.012, -0.009, 0.001, -0.007] * 10
EMPTY = []
SINGLE = [0.05]
ZEROS = [0.0] * 50


# =============================================================================
# Core Metrics (replacing existing implementations)
# =============================================================================


class TestCalculateSortino:
    """Sortino: downside deviation only."""

    def test_positive_returns_positive(self):
        assert calculate_sortino(POSITIVE_RETURNS) > 0

    def test_negative_returns_negative(self):
        assert calculate_sortino(NEGATIVE_RETURNS) < 0

    def test_empty_returns_zero(self):
        assert calculate_sortino(EMPTY) == 0.0

    def test_single_return_zero(self):
        assert calculate_sortino(SINGLE) == 0.0

    def test_zeros_returns_zero(self):
        assert calculate_sortino(ZEROS) == 0.0

    def test_never_nan(self):
        result = calculate_sortino([0.1, -0.1, 0.0])
        assert not math.isnan(result)

    def test_accepts_series(self):
        series = pd.Series(POSITIVE_RETURNS)
        result = calculate_sortino(series)
        assert result > 0

    def test_bounded(self):
        """Output should be in reasonable bounds."""
        result = calculate_sortino([10.0] * 50 + [-10.0] * 50)
        assert -20.0 <= result <= 20.0


class TestCalculateSharpe:
    """Sharpe: total standard deviation."""

    def test_positive_returns_positive(self):
        assert calculate_sharpe(POSITIVE_RETURNS) > 0

    def test_negative_returns_negative(self):
        assert calculate_sharpe(NEGATIVE_RETURNS) < 0

    def test_empty_zero(self):
        assert calculate_sharpe(EMPTY) == 0.0

    def test_zeros_zero(self):
        assert calculate_sharpe(ZEROS) == 0.0

    def test_never_nan(self):
        assert not math.isnan(calculate_sharpe([0.01, -0.01]))


class TestCalculateMaxDrawdown:
    """Max drawdown: returns positive decimal (0.15 = 15%)."""

    def test_positive_non_negative(self):
        result = calculate_max_drawdown(POSITIVE_RETURNS)
        assert result >= 0.0

    def test_crash_scenario_significant(self):
        crash = [0.02] * 50 + [-0.10] * 10
        result = calculate_max_drawdown(crash)
        assert result > 0.3  # >30% drawdown

    def test_empty_zero(self):
        assert calculate_max_drawdown(EMPTY) == 0.0

    def test_all_positive_low_dd(self):
        result = calculate_max_drawdown([0.01] * 100)
        assert result == 0.0

    def test_capped_at_one(self):
        """Max drawdown capped at 1.0 (100%)."""
        result = calculate_max_drawdown([-0.99] * 10)
        assert result <= 1.0


class TestCalculateCalmar:
    """Calmar: annualized return / max drawdown."""

    def test_positive_returns_positive(self):
        assert calculate_calmar(POSITIVE_RETURNS) > 0

    def test_empty_zero(self):
        assert calculate_calmar(EMPTY) == 0.0

    def test_never_nan(self):
        assert not math.isnan(calculate_calmar([0.01, -0.01, 0.02]))


class TestCalculateKelly:
    """Kelly criterion: optimal bet fraction."""

    def test_winning_strategy_positive(self):
        # 70% wins at 2%, 30% losses at 1%
        returns = [0.02] * 70 + [-0.01] * 30
        assert calculate_kelly(returns) > 0

    def test_losing_strategy_negative(self):
        returns = [0.01] * 30 + [-0.02] * 70
        assert calculate_kelly(returns) < 0

    def test_empty_zero(self):
        assert calculate_kelly(EMPTY) == 0.0


class TestCalculateCagr:
    """CAGR: compound annual growth rate."""

    def test_positive_returns_positive(self):
        assert calculate_cagr(POSITIVE_RETURNS) > 0

    def test_empty_zero(self):
        assert calculate_cagr(EMPTY) == 0.0


class TestCalculateWinRate:
    """Win rate: fraction of positive returns."""

    def test_known_value(self):
        returns = [0.01] * 70 + [-0.01] * 30
        result = calculate_win_rate(returns)
        assert abs(result - 0.70) < 0.01

    def test_empty_neutral(self):
        result = calculate_win_rate(EMPTY)
        assert result == 0.5  # Neutral default

    def test_all_wins(self):
        assert calculate_win_rate([0.01] * 100) == 1.0

    def test_all_losses(self):
        assert calculate_win_rate([-0.01] * 100) == 0.0


class TestCalculateExpectancy:
    """Expectancy: expected value per trade."""

    def test_positive_ev(self):
        returns = [0.02] * 60 + [-0.01] * 40
        assert calculate_expectancy(returns) > 0

    def test_negative_ev(self):
        returns = [0.01] * 30 + [-0.02] * 70
        assert calculate_expectancy(returns) < 0

    def test_empty_zero(self):
        assert calculate_expectancy(EMPTY) == 0.0


class TestCalculateProfitFactor:
    """Profit factor: gross wins / gross losses."""

    def test_profitable_above_one(self):
        returns = [0.02] * 60 + [-0.01] * 40
        assert calculate_profit_factor(returns) > 1.0

    def test_losing_below_one(self):
        returns = [0.01] * 30 + [-0.02] * 70
        assert calculate_profit_factor(returns) < 1.0

    def test_empty_zero(self):
        assert calculate_profit_factor(EMPTY) == 0.0


class TestCalculateAlpha:
    """Alpha: strategy return - benchmark return (compound subtraction)."""

    def test_outperformance_positive(self):
        strategy = [0.02] * 50
        benchmark = [0.01] * 50
        assert calculate_alpha(strategy, benchmark) > 0

    def test_underperformance_negative(self):
        strategy = [0.01] * 50
        benchmark = [0.02] * 50
        assert calculate_alpha(strategy, benchmark) < 0

    def test_same_returns_zero(self):
        returns = [0.01] * 50
        result = calculate_alpha(returns, returns)
        assert abs(result) < 0.01

    def test_empty_zero(self):
        assert calculate_alpha(EMPTY, EMPTY) == 0.0


# =============================================================================
# New Risk Metrics
# =============================================================================


class TestCalculateValueAtRisk:
    """VaR: worst expected loss at confidence level."""

    def test_returns_negative_or_zero(self):
        """VaR should be non-positive (it's a loss measure)."""
        result = calculate_value_at_risk(POSITIVE_RETURNS)
        assert result <= 0.01  # Can be slightly positive for very bullish series

    def test_volatile_data_more_negative(self):
        """More volatile data -> larger VaR."""
        calm = [0.001] * 100
        wild = [0.05, -0.05] * 50
        var_calm = calculate_value_at_risk(calm)
        var_wild = calculate_value_at_risk(wild)
        assert var_wild < var_calm  # More negative = worse

    def test_empty_zero(self):
        assert calculate_value_at_risk(EMPTY) == 0.0


class TestCalculateCVaR:
    """CVaR: expected loss beyond VaR (tail risk)."""

    def test_worse_than_var(self):
        """CVaR should be <= VaR (more negative)."""
        var = calculate_value_at_risk(NEGATIVE_RETURNS)
        cvar = calculate_cvar(NEGATIVE_RETURNS)
        assert cvar <= var

    def test_empty_zero(self):
        assert calculate_cvar(EMPTY) == 0.0


class TestCalculateRiskOfRuin:
    """Risk of ruin: probability of total loss."""

    def test_winning_strategy_low(self):
        returns = [0.02] * 80 + [-0.01] * 20
        result = calculate_risk_of_ruin(returns)
        assert result < 0.1

    def test_bounded_zero_one(self):
        result = calculate_risk_of_ruin(NEGATIVE_RETURNS)
        assert 0.0 <= result <= 1.0

    def test_empty_zero(self):
        assert calculate_risk_of_ruin(EMPTY) == 0.0


class TestCalculateConsecutiveLosses:
    """Max consecutive losses."""

    def test_known_value(self):
        returns = [0.01, -0.01, -0.02, -0.03, 0.01, -0.01, -0.02]
        result = calculate_consecutive_losses(returns)
        assert result == 3  # Three consecutive: -0.01, -0.02, -0.03

    def test_all_wins(self):
        assert calculate_consecutive_losses([0.01] * 50) == 0

    def test_empty_zero(self):
        assert calculate_consecutive_losses(EMPTY) == 0


class TestCalculateRecoveryFactor:
    """Recovery factor: total return / max drawdown."""

    def test_positive_for_profitable(self):
        assert calculate_recovery_factor(POSITIVE_RETURNS) > 0

    def test_empty_zero(self):
        assert calculate_recovery_factor(EMPTY) == 0.0


class TestCalculateExposure:
    """Exposure: fraction of time in market (non-zero returns)."""

    def test_known_value(self):
        returns = [0.01, 0.0, 0.0, -0.01, 0.0]
        result = calculate_exposure(returns)
        assert abs(result - 0.4) < 0.01  # 2/5 non-zero

    def test_full_exposure(self):
        assert calculate_exposure([0.01] * 100) == 1.0

    def test_zero_exposure(self):
        assert calculate_exposure([0.0] * 100) == 0.0

    def test_empty_zero(self):
        assert calculate_exposure(EMPTY) == 0.0


# =============================================================================
# Signal/Shape Metrics
# =============================================================================


class TestCalculateSkew:
    """Skewness of return distribution."""

    def test_positive_skew_for_right_tail(self):
        """Returns with fat right tail -> positive skew."""
        import numpy as np
        rng = np.random.default_rng(70)
        # Lognormal has positive skew
        returns = (rng.lognormal(0, 0.5, 200) - 1).tolist()
        result = calculate_skew(returns)
        assert result > 0

    def test_empty_zero(self):
        assert calculate_skew(EMPTY) == 0.0

    def test_never_nan(self):
        assert not math.isnan(calculate_skew([0.01, -0.01, 0.02]))


class TestCalculateKurtosis:
    """Kurtosis: tail heaviness."""

    def test_empty_zero(self):
        assert calculate_kurtosis(EMPTY) == 0.0

    def test_never_nan(self):
        assert not math.isnan(calculate_kurtosis([0.01, -0.01, 0.02, -0.02]))

    def test_normal_near_three(self):
        """Normal distribution has kurtosis ~3 (or 0 excess)."""
        import numpy as np
        rng = np.random.default_rng(71)
        returns = rng.normal(0, 0.01, 10000).tolist()
        result = calculate_kurtosis(returns)
        # Excess kurtosis of normal is ~0, regular is ~3
        assert -1.0 < result < 1.0 or 2.0 < result < 4.0  # Either convention
