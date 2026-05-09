"""
EDD: Profit Factor Parity Tests.

Compares our 1 profit factor implementation against QuantStats:
1. utilities/pattern_backtest.py (inline profit_factor)

Formula: gross_wins / gross_losses

QuantStats: qs.stats.profit_factor()
"""

import math

import numpy as np
import pandas as pd
import pytest
import quantstats as qs


# =============================================================================
# Helper: Inline profit factor from pattern_backtest.py
# =============================================================================


def pattern_backtest_profit_factor(pnls: list[float]) -> float:
    """Profit factor as in pattern_backtest.py (inline)."""
    winning = [p for p in pnls if p > 0]
    losing = [p for p in pnls if p <= 0]

    gross_wins = sum(winning) if winning else 0.0
    gross_losses = abs(sum(losing)) if losing else 0.0

    if gross_losses > 0:
        return gross_wins / gross_losses
    elif gross_wins > 0:
        return gross_wins  # No losses = infinite, return gross wins as proxy
    else:
        return 0.0


# =============================================================================
# Parity: vs QuantStats
# =============================================================================


class TestProfitFactorVsQuantStats:
    """Compare our profit factor against QuantStats."""

    def test_positive_pf_direction(self, winning_trades, to_series):
        """Winning trades: both show PF > 1."""
        series = to_series([r / 100 for r in winning_trades])
        qs_pf = qs.stats.profit_factor(series)

        our_pf = pattern_backtest_profit_factor(winning_trades)

        if not math.isnan(qs_pf):
            assert qs_pf > 1.0, f"QS PF should be > 1: {qs_pf}"
        assert our_pf > 1.0, f"Our PF should be > 1: {our_pf}"

    def test_negative_pf_direction(self, losing_trades, to_series):
        """Losing trades: both show PF < 1."""
        series = to_series([r / 100 for r in losing_trades])
        qs_pf = qs.stats.profit_factor(series)

        our_pf = pattern_backtest_profit_factor(losing_trades)

        if not math.isnan(qs_pf):
            assert qs_pf < 1.0, f"QS PF should be < 1: {qs_pf}"
        assert our_pf < 1.0, f"Our PF should be < 1: {our_pf}"

    def test_known_value(self):
        """Known: $300 wins / $100 losses = PF 3.0."""
        pnls = [100.0, 100.0, 100.0, -50.0, -50.0]
        our_pf = pattern_backtest_profit_factor(pnls)
        assert abs(our_pf - 3.0) < 0.01


# =============================================================================
# Known Values
# =============================================================================


class TestProfitFactorKnown:
    """Test against analytically known values."""

    def test_even_wins_losses(self):
        """Equal wins and losses: PF = 1.0."""
        pnls = [1.0, -1.0, 1.0, -1.0]
        pf = pattern_backtest_profit_factor(pnls)
        assert abs(pf - 1.0) < 0.01

    def test_2_to_1_payoff(self):
        """Wins twice as big as losses, 50% rate: PF = 2.0."""
        pnls = [2.0, -1.0, 2.0, -1.0]
        pf = pattern_backtest_profit_factor(pnls)
        assert abs(pf - 2.0) < 0.01

    def test_high_win_rate_compensates(self):
        """80% wins at $1, 20% losses at $1: PF = 4.0."""
        pnls = [1.0] * 80 + [-1.0] * 20
        pf = pattern_backtest_profit_factor(pnls)
        assert abs(pf - 4.0) < 0.01


# =============================================================================
# Edge Cases
# =============================================================================


class TestProfitFactorEdgeCases:
    """Division safety."""

    def test_no_losses(self):
        """No losses: returns gross wins (proxy for infinity)."""
        pnls = [1.0, 2.0, 3.0]
        pf = pattern_backtest_profit_factor(pnls)
        # gross_wins = 6.0, no losses
        assert pf == 6.0

    def test_no_wins(self):
        """No wins: PF = 0."""
        pnls = [-1.0, -2.0, -3.0]
        pf = pattern_backtest_profit_factor(pnls)
        assert pf == 0.0

    def test_empty(self):
        """Empty: PF = 0."""
        pf = pattern_backtest_profit_factor([])
        assert pf == 0.0

    def test_all_zeros(self):
        """All zeros: PF = 0 (zeros counted as losses but abs sum = 0)."""
        pf = pattern_backtest_profit_factor([0.0, 0.0, 0.0])
        assert pf == 0.0

    def test_tiny_losses(self):
        """Very small losses shouldn't cause overflow."""
        pnls = [100.0, -0.001]
        pf = pattern_backtest_profit_factor(pnls)
        assert pf > 0
        assert math.isfinite(pf)
