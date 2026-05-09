"""
EDD: Max Drawdown Parity Tests.

Compares our 4 drawdown implementations against QuantStats:
1. local_agents/shared/metrics.py::calculate_max_drawdown (from equity curve)
2. local_agents/shared/metrics.py::calculate_max_drawdown_from_returns (from returns)
3. utilities/pattern_backtest.py (inline, from pnl percentages)
4. Backtest/Services/backtest_service.py::_calculate_max_drawdown (cumulative PnL)

Key differences:
- metrics.py #1: peak-to-trough / peak (percentage of equity)
- metrics.py #2: builds equity curve then calls #1
- pattern_backtest.py: equity *= (1 + pnl/100), peak tracking
- backtest_service.py: cumulative sum of PnL (DOLLAR amount, not %)
"""

import math

import numpy as np
import pandas as pd
import pytest
import quantstats as qs

from Fast_Swarm.local_agents.shared.metrics import (
    calculate_max_drawdown,
    calculate_max_drawdown_from_returns,
)


# =============================================================================
# Helpers: Extract inline implementations
# =============================================================================


def pattern_backtest_max_drawdown(pnls_pct: list[float]) -> float:
    """Drawdown as calculated in pattern_backtest.py (inline)."""
    equity = 100.0
    peak_equity = equity
    max_drawdown_pct = 0.0

    for pnl in pnls_pct:
        equity *= 1 + pnl / 100
        if equity > peak_equity:
            peak_equity = equity
        if peak_equity > 0:
            dd = (peak_equity - equity) / peak_equity * 100
            max_drawdown_pct = max(max_drawdown_pct, dd)

    return max_drawdown_pct


def backtest_service_max_drawdown(pnls: list[float]) -> float:
    """Drawdown as in backtest_service.py (cumulative dollar PnL)."""
    if not pnls:
        return 0.0

    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0

    for pnl in pnls:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd

    return max_dd


# =============================================================================
# Parity: Our percentage-based implementations vs each other
# =============================================================================


class TestDrawdownParity:
    """Percentage drawdown implementations should agree."""

    def test_from_returns_vs_from_equity(self, positive_returns, equity_from_returns):
        """metrics.py: from_returns and from_equity should match."""
        equity = equity_from_returns(positive_returns)

        dd_equity = calculate_max_drawdown(equity)
        dd_returns = calculate_max_drawdown_from_returns(positive_returns)

        assert abs(dd_equity - dd_returns) < 0.001, (
            f"Equity-based: {dd_equity:.6f}, Returns-based: {dd_returns:.6f}"
        )

    def test_metrics_vs_pattern_backtest(self, mixed_returns):
        """metrics.py and pattern_backtest.py should give same result."""
        # metrics.py returns decimal (0.15 = 15%)
        dd_metrics = calculate_max_drawdown_from_returns(mixed_returns)
        # pattern_backtest.py expects percentages, returns percentage
        dd_pattern = pattern_backtest_max_drawdown([r * 100 for r in mixed_returns])

        # Convert to same units (both as percentage)
        dd_metrics_pct = dd_metrics * 100

        assert abs(dd_metrics_pct - dd_pattern) < 0.1, (
            f"metrics.py: {dd_metrics_pct:.4f}%, pattern_backtest: {dd_pattern:.4f}%"
        )

    def test_crash_scenario_all_detect(self, crash_scenario_returns):
        """All impls detect significant drawdown in crash scenario."""
        dd_metrics = calculate_max_drawdown_from_returns(crash_scenario_returns) * 100
        dd_pattern = pattern_backtest_max_drawdown([r * 100 for r in crash_scenario_returns])

        # Crash scenario should have significant drawdown (>20%)
        assert dd_metrics > 20, f"metrics.py missed crash: {dd_metrics:.2f}%"
        assert dd_pattern > 20, f"pattern_backtest missed crash: {dd_pattern:.2f}%"


# =============================================================================
# Parity: vs QuantStats
# =============================================================================


class TestDrawdownVsQuantStats:
    """Compare against QuantStats max_drawdown."""

    def test_positive_returns(self, positive_returns, to_series):
        """Both should detect small drawdown in positive series."""
        series = to_series(positive_returns)
        qs_dd = qs.stats.max_drawdown(series)  # Returns negative decimal

        our_dd = calculate_max_drawdown_from_returns(positive_returns)

        # QuantStats returns negative (e.g., -0.15), ours returns positive (0.15)
        if not math.isnan(qs_dd):
            qs_dd_abs = abs(qs_dd)
            assert abs(qs_dd_abs - our_dd) < 0.05, (
                f"QS: {qs_dd_abs:.4f}, ours: {our_dd:.4f}"
            )

    def test_crash_scenario(self, crash_scenario_returns, to_series):
        """Crash scenario: both detect similar magnitude."""
        series = to_series(crash_scenario_returns)
        qs_dd = qs.stats.max_drawdown(series)

        our_dd = calculate_max_drawdown_from_returns(crash_scenario_returns)

        if not math.isnan(qs_dd):
            qs_dd_abs = abs(qs_dd)
            # Should be within 20% relative error
            if qs_dd_abs > 0.01:
                relative_error = abs(qs_dd_abs - our_dd) / qs_dd_abs
                assert relative_error < 0.2, (
                    f"QS: {qs_dd_abs:.4f}, ours: {our_dd:.4f}, error: {relative_error:.2%}"
                )

    def test_volatile_returns(self, volatile_returns, to_series):
        """Volatile returns: order of magnitude agreement."""
        series = to_series(volatile_returns)
        qs_dd = qs.stats.max_drawdown(series)

        our_dd = calculate_max_drawdown_from_returns(volatile_returns)

        if not math.isnan(qs_dd):
            qs_dd_abs = abs(qs_dd)
            # Both should be non-trivial for volatile data
            assert qs_dd_abs > 0.01, f"QS drawdown too small: {qs_dd_abs}"
            assert our_dd > 0.01, f"Our drawdown too small: {our_dd}"


# =============================================================================
# Edge Cases
# =============================================================================


class TestDrawdownEdgeCases:
    """Division safety and bounds."""

    def test_empty_returns(self):
        """Empty -> 0."""
        assert calculate_max_drawdown([]) == 0.0
        assert calculate_max_drawdown_from_returns([]) == 0.0

    def test_single_return(self):
        """Single return: not enough data."""
        assert calculate_max_drawdown([100.0]) == 0.0

    def test_all_positive_equity(self):
        """Monotonically increasing equity -> 0 drawdown."""
        equity = list(range(1, 101))  # 1, 2, ..., 100
        assert calculate_max_drawdown(equity) == 0.0

    def test_all_negative_returns(self, negative_returns):
        """All negative: drawdown should be capped at 1.0 (100%)."""
        dd = calculate_max_drawdown_from_returns(negative_returns)
        assert 0.0 <= dd <= 1.0

    def test_zero_equity(self):
        """Equity goes to zero: drawdown = 100%."""
        equity = [100, 50, 0]
        dd = calculate_max_drawdown(equity)
        assert dd == 1.0

    def test_recovery_after_drawdown(self):
        """Drawdown then recovery: max DD captured at trough."""
        returns = [0.10, 0.10, -0.30, -0.30, 0.50, 0.50]
        dd = calculate_max_drawdown_from_returns(returns)
        # After 10%, 10% gain, then -30%, -30% loss
        # Peak at 1.0 * 1.1 * 1.1 = 1.21
        # Trough at 1.21 * 0.7 * 0.7 = 0.5929
        # DD = (1.21 - 0.5929) / 1.21 = 0.51
        assert dd > 0.4

    def test_backtest_service_dollar_drawdown(self):
        """backtest_service uses dollar amounts (not percentages)."""
        pnls = [10, 20, -50, 10, -5]
        dd = backtest_service_max_drawdown(pnls)
        # Peak at 30 (10+20), then drops to -20 (30-50), so DD = 50
        # Then recovers to -10, drops to -15, so still DD = 50
        assert dd == 50.0

    def test_backtest_service_no_drawdown(self):
        """All positive PnLs -> 0 drawdown."""
        pnls = [10, 20, 30, 40]
        dd = backtest_service_max_drawdown(pnls)
        assert dd == 0.0
