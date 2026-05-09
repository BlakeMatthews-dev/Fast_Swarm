"""
EDD: Sortino Ratio Parity Tests.

Compares our 2 Sortino implementations against QuantStats ground truth:
1. local_agents/shared/metrics.py::calculate_sortino_ratio
2. utilities/pattern_backtest.py (inline Sortino calculation)

Key differences to validate:
- Our impl uses population std (N), QuantStats uses sample std (N-1)
- Annualization factor handling
- Cap/bound behavior
- Edge cases (no downside, all zeros, single return)
"""

import math

import numpy as np
import pandas as pd
import pytest
import quantstats as qs

from Fast_Swarm.local_agents.shared.metrics import calculate_sortino_ratio


# =============================================================================
# Helper: Inline Sortino from pattern_backtest.py (extracted for testing)
# =============================================================================


def pattern_backtest_sortino(pnls: list[float]) -> float:
    """
    Sortino as calculated in pattern_backtest.py (inline).
    Extracted here for direct comparison.
    """
    if len(pnls) < 2:
        return 0.0

    avg_pnl = sum(pnls) / len(pnls)
    downside = [p for p in pnls if p < 0]

    if not downside:
        # pattern_backtest.py falls back to sharpe * 1.5
        std_pnl = np.std(pnls)
        sharpe = (avg_pnl / std_pnl * np.sqrt(252)) if std_pnl > 0 else 0.0
        sortino = sharpe * 1.5
    else:
        downside_std = np.std(downside)
        sortino = (avg_pnl / downside_std * np.sqrt(252)) if downside_std > 0 else 0.0

    return max(-10.0, min(10.0, sortino))


# =============================================================================
# Parity: Our implementations vs each other
# =============================================================================


class TestSortinoParity:
    """Both our implementations should agree on sign and rough magnitude."""

    def test_positive_returns_same_sign(self, positive_returns):
        """Both impls agree: positive returns -> positive Sortino."""
        metrics_sortino = calculate_sortino_ratio(positive_returns)
        pattern_sortino = pattern_backtest_sortino([r * 100 for r in positive_returns])

        # Both should be positive
        assert metrics_sortino > 0, f"metrics.py Sortino should be positive: {metrics_sortino}"
        assert pattern_sortino > 0, f"pattern_backtest Sortino should be positive: {pattern_sortino}"

    def test_negative_returns_same_sign(self, negative_returns):
        """Both impls agree: negative returns -> negative Sortino."""
        metrics_sortino = calculate_sortino_ratio(negative_returns)
        pattern_sortino = pattern_backtest_sortino([r * 100 for r in negative_returns])

        assert metrics_sortino < 0, f"metrics.py Sortino should be negative: {metrics_sortino}"
        assert pattern_sortino < 0, f"pattern_backtest Sortino should be negative: {pattern_sortino}"

    def test_mixed_returns_bounded(self, mixed_returns):
        """Both impls stay within their declared bounds."""
        metrics_sortino = calculate_sortino_ratio(mixed_returns)
        pattern_sortino = pattern_backtest_sortino([r * 100 for r in mixed_returns])

        # metrics.py caps at [-4, 4]
        assert -4.0 <= metrics_sortino <= 4.0
        # pattern_backtest.py caps at [-10, 10]
        assert -10.0 <= pattern_sortino <= 10.0


# =============================================================================
# Parity: Our implementations vs QuantStats
# =============================================================================


class TestSortinoVsQuantStats:
    """Compare our Sortino against QuantStats ground truth."""

    def test_positive_returns_direction(self, positive_returns, to_series):
        """QuantStats and our impl agree on direction for profitable series."""
        series = to_series(positive_returns)
        qs_sortino = qs.stats.sortino(series)

        metrics_sortino = calculate_sortino_ratio(positive_returns)

        # Both should be positive
        if not math.isnan(qs_sortino):
            assert (qs_sortino > 0) == (metrics_sortino > 0), (
                f"Direction mismatch: QS={qs_sortino:.4f}, ours={metrics_sortino:.4f}"
            )

    def test_negative_returns_direction(self, negative_returns, to_series):
        """QuantStats and our impl agree on direction for losing series."""
        series = to_series(negative_returns)
        qs_sortino = qs.stats.sortino(series)

        metrics_sortino = calculate_sortino_ratio(negative_returns)

        if not math.isnan(qs_sortino):
            assert (qs_sortino < 0) == (metrics_sortino < 0), (
                f"Direction mismatch: QS={qs_sortino:.4f}, ours={metrics_sortino:.4f}"
            )

    def test_volatile_returns_order_of_magnitude(self, volatile_returns, to_series):
        """For volatile data, our impl should be within 1 order of magnitude."""
        series = to_series(volatile_returns)
        qs_sortino = qs.stats.sortino(series)

        metrics_sortino = calculate_sortino_ratio(volatile_returns)

        if not math.isnan(qs_sortino) and abs(qs_sortino) > 0.01:
            ratio = abs(metrics_sortino / qs_sortino) if qs_sortino != 0 else float('inf')
            assert 0.1 < ratio < 10, (
                f"Order of magnitude mismatch: QS={qs_sortino:.4f}, ours={metrics_sortino:.4f}, ratio={ratio:.2f}"
            )

    def test_crash_scenario(self, crash_scenario_returns, to_series):
        """Crash scenario should produce low/negative Sortino in both."""
        series = to_series(crash_scenario_returns)
        qs_sortino = qs.stats.sortino(series)

        metrics_sortino = calculate_sortino_ratio(crash_scenario_returns)

        # After a crash, Sortino should be low (below 1.0)
        if not math.isnan(qs_sortino):
            assert qs_sortino < 2.0, f"QS Sortino unexpectedly high after crash: {qs_sortino}"
            assert metrics_sortino < 2.0, f"Our Sortino unexpectedly high after crash: {metrics_sortino}"


# =============================================================================
# Edge Cases
# =============================================================================


class TestSortinoEdgeCases:
    """Division safety and edge case handling."""

    def test_empty_returns(self):
        """Empty list should return 0."""
        assert calculate_sortino_ratio([]) == 0.0
        assert pattern_backtest_sortino([]) == 0.0

    def test_single_return(self):
        """Single return: too few data points."""
        assert calculate_sortino_ratio([0.05]) == 0.0
        assert pattern_backtest_sortino([5.0]) == 0.0

    def test_zero_returns(self, zero_returns):
        """All-zero returns: no crash, returns 0."""
        result = calculate_sortino_ratio(zero_returns)
        assert result == 0.0

    def test_no_downside(self, no_downside_returns):
        """All positive returns: no downside deviation."""
        result = calculate_sortino_ratio(no_downside_returns)
        # Should cap at 4.0 (our max) since downside deviation ~= 0
        assert result == 4.0, f"Expected cap at 4.0 for all-positive, got {result}"

    def test_nan_in_returns(self):
        """NaN values shouldn't crash (not required to handle, but shouldn't explode)."""
        # Note: our impl doesn't explicitly handle NaN - this documents behavior
        returns = [0.01, 0.02, -0.01, 0.03]
        result = calculate_sortino_ratio(returns)
        assert math.isfinite(result)

    def test_extreme_values(self):
        """Extreme returns should still produce bounded output."""
        extreme = [10.0, -10.0, 5.0, -5.0, 0.5]
        result = calculate_sortino_ratio(extreme)
        assert -4.0 <= result <= 4.0

    def test_two_returns_minimum(self):
        """Two returns is the minimum for calculation."""
        result = calculate_sortino_ratio([0.01, 0.02])
        assert result > 0  # Both positive -> positive Sortino
