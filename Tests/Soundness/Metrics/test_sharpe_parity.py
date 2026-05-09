"""
EDD: Sharpe Ratio Parity Tests.

Compares our 3 Sharpe implementations against QuantStats:
1. local_agents/shared/metrics.py::calculate_sharpe_ratio
2. utilities/pattern_backtest.py (inline, uses np.std)
3. Backtest/Services/backtest_service.py::_calculate_sharpe (non-annualized)

Key differences:
- metrics.py uses population std (N) and annualizes
- pattern_backtest.py uses numpy std (N-1 by default? No, np.std uses N) and annualizes
- backtest_service.py uses population std (N) and does NOT annualize
- QuantStats annualizes by default
"""

import math

import numpy as np
import pandas as pd
import pytest
import quantstats as qs

from Fast_Swarm.local_agents.shared.metrics import calculate_sharpe_ratio


# =============================================================================
# Helpers: Extract inline implementations for testing
# =============================================================================


def pattern_backtest_sharpe(pnls: list[float]) -> float:
    """Sharpe as calculated in pattern_backtest.py (inline)."""
    if len(pnls) < 2:
        return 0.0

    avg_pnl = sum(pnls) / len(pnls)
    std_pnl = np.std(pnls)
    sharpe = (avg_pnl / std_pnl * np.sqrt(252)) if std_pnl > 0 else 0.0
    return max(-6.0, min(6.0, sharpe))


def backtest_service_sharpe(pnls: list[float]) -> float:
    """Sharpe as calculated in backtest_service.py (_calculate_sharpe)."""
    if len(pnls) < 2:
        return 0.0

    mean_return = sum(pnls) / len(pnls)
    variance = sum((p - mean_return) ** 2 for p in pnls) / len(pnls)
    std_dev = variance**0.5 if variance > 0 else 0

    sharpe = mean_return / std_dev if std_dev > 0 else 0
    return max(-6.0, min(6.0, sharpe))


# =============================================================================
# Parity: Our implementations vs each other
# =============================================================================


class TestSharpeParity:
    """All 3 implementations should agree on direction."""

    def test_positive_returns_all_positive(self, positive_returns):
        """All 3 impls: positive returns -> positive Sharpe."""
        # metrics.py expects decimals
        m = calculate_sharpe_ratio(positive_returns)
        # pattern_backtest expects percentages
        p = pattern_backtest_sharpe([r * 100 for r in positive_returns])
        # backtest_service expects raw PnL values
        b = backtest_service_sharpe([r * 100 for r in positive_returns])

        assert m > 0, f"metrics.py: {m}"
        assert p > 0, f"pattern_backtest: {p}"
        assert b > 0, f"backtest_service: {b}"

    def test_negative_returns_all_negative(self, negative_returns):
        """All 3 impls: negative returns -> negative Sharpe."""
        m = calculate_sharpe_ratio(negative_returns)
        p = pattern_backtest_sharpe([r * 100 for r in negative_returns])
        b = backtest_service_sharpe([r * 100 for r in negative_returns])

        assert m < 0, f"metrics.py: {m}"
        assert p < 0, f"pattern_backtest: {p}"
        assert b < 0, f"backtest_service: {b}"

    def test_annualized_vs_not(self, mixed_returns):
        """
        metrics.py and pattern_backtest annualize; backtest_service does NOT.
        Annualized should be larger in magnitude.
        """
        m = calculate_sharpe_ratio(mixed_returns)
        b = backtest_service_sharpe([r * 100 for r in mixed_returns])

        # Annualized should be ~sqrt(252) = ~15.87x larger
        # (unless capped at bounds)
        if abs(b) > 0.001 and abs(m) < 4.0:
            ratio = abs(m / b) if b != 0 else float('inf')
            # Should be roughly sqrt(252) ~ 15.87
            assert ratio > 5, f"Annualization ratio too low: {ratio:.2f}"


# =============================================================================
# Parity: Our implementations vs QuantStats
# =============================================================================


class TestSharpeVsQuantStats:
    """Compare our Sharpe against QuantStats."""

    def test_direction_agreement(self, positive_returns, to_series):
        """QuantStats and our impl agree on direction."""
        series = to_series(positive_returns)
        qs_sharpe = qs.stats.sharpe(series)

        our_sharpe = calculate_sharpe_ratio(positive_returns)

        if not math.isnan(qs_sharpe):
            assert (qs_sharpe > 0) == (our_sharpe > 0), (
                f"Direction mismatch: QS={qs_sharpe:.4f}, ours={our_sharpe:.4f}"
            )

    def test_negative_direction(self, negative_returns, to_series):
        """Both negative for losing series."""
        series = to_series(negative_returns)
        qs_sharpe = qs.stats.sharpe(series)

        our_sharpe = calculate_sharpe_ratio(negative_returns)

        if not math.isnan(qs_sharpe):
            assert (qs_sharpe < 0) == (our_sharpe < 0), (
                f"Direction mismatch: QS={qs_sharpe:.4f}, ours={our_sharpe:.4f}"
            )

    def test_magnitude_reasonable(self, mixed_returns, to_series):
        """Both should be in reasonable range for mixed returns."""
        series = to_series(mixed_returns)
        qs_sharpe = qs.stats.sharpe(series)

        our_sharpe = calculate_sharpe_ratio(mixed_returns)

        if not math.isnan(qs_sharpe):
            assert abs(qs_sharpe) < 5.0, f"QS unreasonably large: {qs_sharpe}"
            assert abs(our_sharpe) < 5.0, f"Ours unreasonably large: {our_sharpe}"


# =============================================================================
# Edge Cases
# =============================================================================


class TestSharpeEdgeCases:
    """Division safety and bounds."""

    def test_empty_returns(self):
        """Empty -> 0."""
        assert calculate_sharpe_ratio([]) == 0.0

    def test_single_return(self):
        """Single -> 0."""
        assert calculate_sharpe_ratio([0.05]) == 0.0

    def test_zero_returns(self, zero_returns):
        """All zeros -> 0 (no variance)."""
        assert calculate_sharpe_ratio(zero_returns) == 0.0

    def test_constant_positive(self):
        """Constant positive returns -> 0 (zero std dev)."""
        result = calculate_sharpe_ratio([0.01] * 50)
        assert result == 0.0

    def test_bounds_respected(self):
        """Extreme inputs stay within [-4, 4] for metrics.py."""
        extreme = [10.0, -10.0, 10.0, -10.0, 10.0]
        result = calculate_sharpe_ratio(extreme)
        assert -4.0 <= result <= 4.0

    def test_pattern_backtest_bounds(self):
        """pattern_backtest.py caps at [-6, 6]."""
        extreme = [100.0, -1.0, 100.0, -1.0, 100.0]
        result = pattern_backtest_sharpe(extreme)
        assert -6.0 <= result <= 6.0
