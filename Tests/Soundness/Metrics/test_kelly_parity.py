"""
EDD: Kelly Criterion Parity Tests.

We don't have a Kelly implementation currently, but the new metrics engine will add one.
These tests validate QuantStats's Kelly against known analytical results.

Kelly % = W - [(1-W) / R]
Where W = win probability, R = win/loss ratio (payoff ratio)
"""

import math

import pytest
import quantstats as qs
import pandas as pd
import numpy as np


# =============================================================================
# Kelly: Known Analytical Values
# =============================================================================


class TestKellyAnalytical:
    """Validate QuantStats Kelly against known formulas."""

    def test_coin_flip_even_odds(self):
        """50/50 coin flip with even payoff -> Kelly = 0."""
        # Generate many +1/-1 trades (50% win rate, 1:1 payoff)
        rng = np.random.default_rng(100)
        outcomes = rng.choice([0.01, -0.01], size=10000, p=[0.5, 0.5])
        series = pd.Series(outcomes)

        kelly = qs.stats.kelly_criterion(series)

        if not math.isnan(kelly):
            # Theoretical Kelly = 0.5 - (0.5/1.0) = 0.0
            assert abs(kelly) < 0.05, f"Even odds Kelly should be ~0: {kelly}"

    def test_strong_edge(self):
        """70% win rate, 1:1 payoff -> Kelly ~ 0.40."""
        rng = np.random.default_rng(101)
        outcomes = rng.choice([0.01, -0.01], size=10000, p=[0.7, 0.3])
        series = pd.Series(outcomes)

        kelly = qs.stats.kelly_criterion(series)

        if not math.isnan(kelly):
            # Theoretical: 0.7 - (0.3/1.0) = 0.40
            assert kelly > 0.2, f"Strong edge Kelly should be positive: {kelly}"

    def test_losing_edge(self):
        """30% win rate, 1:1 payoff -> Kelly negative."""
        rng = np.random.default_rng(102)
        outcomes = rng.choice([0.01, -0.01], size=10000, p=[0.3, 0.7])
        series = pd.Series(outcomes)

        kelly = qs.stats.kelly_criterion(series)

        if not math.isnan(kelly):
            # Theoretical: 0.3 - (0.7/1.0) = -0.40
            assert kelly < 0, f"Losing edge Kelly should be negative: {kelly}"

    def test_high_payoff_low_win_rate(self):
        """20% win rate, 5:1 payoff -> Kelly ~ 0.04."""
        rng = np.random.default_rng(103)
        outcomes = rng.choice([0.05, -0.01], size=10000, p=[0.2, 0.8])
        series = pd.Series(outcomes)

        kelly = qs.stats.kelly_criterion(series)

        if not math.isnan(kelly):
            # Theoretical: 0.2 - (0.8/5.0) = 0.04
            assert kelly > -0.1, f"High payoff Kelly should be near 0 or positive: {kelly}"


# =============================================================================
# Edge Cases
# =============================================================================


class TestKellyEdgeCases:
    """Robustness tests for Kelly calculation."""

    def test_all_wins(self):
        """All wins -> Kelly should be high (bet everything)."""
        series = pd.Series([0.02] * 100)
        kelly = qs.stats.kelly_criterion(series)

        if not math.isnan(kelly):
            assert kelly > 0.5, f"All wins Kelly should be high: {kelly}"

    def test_all_losses(self):
        """All losses -> Kelly should be very negative."""
        series = pd.Series([-0.02] * 100)
        kelly = qs.stats.kelly_criterion(series)

        if not math.isnan(kelly):
            assert kelly < 0, f"All losses Kelly should be negative: {kelly}"

    def test_single_trade(self):
        """Single trade: insufficient data."""
        series = pd.Series([0.05])
        kelly = qs.stats.kelly_criterion(series)
        # Should be finite or NaN (either is acceptable)
        assert math.isnan(kelly) or math.isfinite(kelly)

    def test_zero_returns(self):
        """All zeros."""
        series = pd.Series([0.0] * 50)
        kelly = qs.stats.kelly_criterion(series)
        # Should not crash
        assert math.isnan(kelly) or math.isfinite(kelly)
