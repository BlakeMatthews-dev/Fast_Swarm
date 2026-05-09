"""
TDD: Risk Metrics Interface Tests.

Tests for VaR, CVaR, risk_of_ruin, exposure, consecutive_losses
as a focused battery. These supplement test_metrics_engine.py with
more detailed behavioral tests for the risk-specific functions.
"""

import math

import numpy as np
import pytest

from Fast_Swarm.Metrics.metrics_engine import (
    calculate_consecutive_losses,
    calculate_cvar,
    calculate_exposure,
    calculate_risk_of_ruin,
    calculate_value_at_risk,
)


# =============================================================================
# VaR/CVaR Relationship Tests
# =============================================================================


class TestVaRCVaRRelationship:
    """CVaR should always be worse than VaR."""

    def test_cvar_worse_than_var_mixed(self):
        """For mixed returns, CVaR <= VaR (more negative)."""
        rng = np.random.default_rng(80)
        returns = rng.normal(0.001, 0.02, 200).tolist()

        var = calculate_value_at_risk(returns)
        cvar = calculate_cvar(returns)

        assert cvar <= var + 0.001  # CVaR is tail average, always worse

    def test_cvar_worse_than_var_crash(self):
        """Crash scenario: large gap between VaR and CVaR."""
        rng = np.random.default_rng(81)
        # Normal returns with fat left tail
        normal = rng.normal(0.001, 0.01, 180).tolist()
        crashes = [-0.10, -0.15, -0.20, -0.25, -0.30] * 4
        returns = normal + crashes

        var = calculate_value_at_risk(returns)
        cvar = calculate_cvar(returns)

        # CVaR captures the tail events
        assert cvar < var

    def test_var_confidence_level_default(self):
        """Default 5% VaR: 95% of returns should be better than this."""
        rng = np.random.default_rng(82)
        returns = rng.normal(0, 0.02, 1000).tolist()

        var = calculate_value_at_risk(returns)
        worse_count = sum(1 for r in returns if r < var)
        # ~5% should be worse than VaR
        assert 20 < worse_count < 80  # 2-8% tolerance


# =============================================================================
# Risk of Ruin Tests
# =============================================================================


class TestRiskOfRuin:
    """Risk of ruin should correlate with strategy quality."""

    def test_winning_strategy_low_ruin(self):
        """High win rate + good payoff = low ruin risk."""
        returns = [0.03] * 70 + [-0.01] * 30
        result = calculate_risk_of_ruin(returns)
        assert result < 0.05

    def test_losing_strategy_high_ruin(self):
        """Low win rate + bad payoff = high ruin risk."""
        returns = [0.01] * 20 + [-0.03] * 80
        result = calculate_risk_of_ruin(returns)
        assert result > 0.3

    def test_breakeven_moderate_ruin(self):
        """Near breakeven = moderate ruin risk."""
        rng = np.random.default_rng(83)
        returns = rng.choice([0.01, -0.01], size=200, p=[0.5, 0.5]).tolist()
        result = calculate_risk_of_ruin(returns)
        assert 0.0 <= result <= 1.0

    def test_all_wins_zero_ruin(self):
        """All wins = effectively zero ruin."""
        returns = [0.02] * 100
        result = calculate_risk_of_ruin(returns)
        assert result < 0.01


# =============================================================================
# Exposure Tests
# =============================================================================


class TestExposure:
    """Exposure = fraction of non-zero return periods."""

    def test_half_exposure(self):
        """50% in market."""
        returns = [0.01, 0.0] * 50
        result = calculate_exposure(returns)
        assert abs(result - 0.5) < 0.01

    def test_sparse_trading(self):
        """10% in market (lots of sitting out)."""
        returns = [0.02] * 10 + [0.0] * 90
        result = calculate_exposure(returns)
        assert abs(result - 0.1) < 0.01

    def test_includes_losses(self):
        """Losses also count as exposure."""
        returns = [0.0, -0.01, 0.0, 0.0, 0.0]
        result = calculate_exposure(returns)
        assert abs(result - 0.2) < 0.01


# =============================================================================
# Consecutive Losses Tests
# =============================================================================


class TestConsecutiveLosses:
    """Track maximum losing streak."""

    def test_alternating_zero(self):
        """Win-loss-win-loss: max consecutive = 1."""
        returns = [0.01, -0.01] * 50
        result = calculate_consecutive_losses(returns)
        assert result == 1

    def test_streak_at_start(self):
        """Losing streak at beginning."""
        returns = [-0.01, -0.02, -0.03, 0.01, 0.02]
        result = calculate_consecutive_losses(returns)
        assert result == 3

    def test_streak_at_end(self):
        """Losing streak at end."""
        returns = [0.01, 0.02, -0.01, -0.02, -0.03, -0.04]
        result = calculate_consecutive_losses(returns)
        assert result == 4

    def test_multiple_streaks_returns_max(self):
        """Multiple streaks: returns the longest."""
        returns = [-0.01, -0.02, 0.01, -0.01, -0.02, -0.03, -0.04, 0.01]
        result = calculate_consecutive_losses(returns)
        assert result == 4  # The longer streak

    def test_zero_not_a_loss(self):
        """Zero return breaks the streak."""
        returns = [-0.01, -0.02, 0.0, -0.01, -0.02]
        result = calculate_consecutive_losses(returns)
        assert result == 2  # Zero breaks the streak
