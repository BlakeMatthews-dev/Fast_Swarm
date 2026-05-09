"""
EDD: Calmar Ratio Parity Tests.

Compares our 2 Calmar implementations against QuantStats:
1. local_agents/shared/fitness.py::calculate_calmar_ratio
2. utilities/pattern_backtest.py (inline calmar)

Key differences:
- fitness.py: annualized_return / abs(max_drawdown), caps at +-10
- pattern_backtest.py: total_pnl_pct / max_drawdown_pct, caps at +-10
- QuantStats: annualized return / max drawdown (compound)
"""

import math

import numpy as np
import pandas as pd
import pytest
import quantstats as qs

from Fast_Swarm.local_agents.shared.fitness import calculate_calmar_ratio


# =============================================================================
# Helper: Inline Calmar from pattern_backtest.py
# =============================================================================


def pattern_backtest_calmar(total_pnl_pct: float, max_drawdown_pct: float) -> float:
    """Calmar as in pattern_backtest.py."""
    calmar = total_pnl_pct / max_drawdown_pct if max_drawdown_pct > 0 else total_pnl_pct
    return max(-10.0, min(10.0, calmar))


# =============================================================================
# Parity: Our implementations vs each other
# =============================================================================


class TestCalmarParity:
    """Both impls should agree on direction and approximate value."""

    def test_positive_return_positive_calmar(self):
        """Positive return with drawdown -> positive Calmar."""
        # fitness.py signature: (annualized_return_pct, max_drawdown_pct)
        c1 = calculate_calmar_ratio(50.0, 25.0)
        # pattern_backtest: (total_pnl_pct, max_drawdown_pct)
        c2 = pattern_backtest_calmar(50.0, 25.0)

        assert c1 > 0
        assert c2 > 0
        # Both should give 2.0 (50/25)
        assert abs(c1 - 2.0) < 0.01
        assert abs(c2 - 2.0) < 0.01

    def test_negative_return_negative_calmar(self):
        """Negative return -> negative Calmar."""
        c1 = calculate_calmar_ratio(-30.0, 40.0)
        c2 = pattern_backtest_calmar(-30.0, 40.0)

        assert c1 < 0
        assert c2 < 0

    def test_zero_drawdown_cap(self):
        """Zero drawdown should not crash."""
        c1 = calculate_calmar_ratio(50.0, 0.0)
        c2 = pattern_backtest_calmar(50.0, 0.0)

        # fitness.py returns 10.0 (cap) for positive return + zero DD
        assert c1 == 10.0
        # pattern_backtest returns total_pnl_pct capped at 10
        assert c2 == 10.0

    def test_both_capped_at_10(self):
        """Both implementations cap at +-10."""
        c1 = calculate_calmar_ratio(500.0, 5.0)  # Would be 100
        c2 = pattern_backtest_calmar(500.0, 5.0)

        assert c1 == 10.0
        assert c2 == 10.0

        c1_neg = calculate_calmar_ratio(-500.0, 5.0)
        c2_neg = pattern_backtest_calmar(-500.0, 5.0)

        assert c1_neg == -10.0
        assert c2_neg == -10.0


# =============================================================================
# Parity: vs QuantStats
# =============================================================================


class TestCalmarVsQuantStats:
    """Compare against QuantStats calmar."""

    def test_positive_direction(self, positive_returns, to_series):
        """Positive returns -> positive Calmar in both."""
        series = to_series(positive_returns)
        qs_calmar = qs.stats.calmar(series)

        # Our impl needs annualized return and max drawdown separately
        total_return = 1.0
        for r in positive_returns:
            total_return *= (1 + r)
        annualized_pct = (total_return - 1) * 100

        from Fast_Swarm.local_agents.shared.metrics import calculate_max_drawdown_from_returns
        max_dd = calculate_max_drawdown_from_returns(positive_returns) * 100

        our_calmar = calculate_calmar_ratio(annualized_pct, max_dd)

        if not math.isnan(qs_calmar):
            # Both should be positive for profitable series
            assert qs_calmar > 0, f"QS negative: {qs_calmar}"
            assert our_calmar > 0, f"Ours negative: {our_calmar}"

    def test_crash_scenario(self, crash_scenario_returns, to_series):
        """Crash scenario: Calmar should be low/negative."""
        series = to_series(crash_scenario_returns)
        qs_calmar = qs.stats.calmar(series)

        total_return = 1.0
        for r in crash_scenario_returns:
            total_return *= (1 + r)
        annualized_pct = (total_return - 1) * 100

        from Fast_Swarm.local_agents.shared.metrics import calculate_max_drawdown_from_returns
        max_dd = calculate_max_drawdown_from_returns(crash_scenario_returns) * 100

        our_calmar = calculate_calmar_ratio(annualized_pct, max_dd)

        # Crash should produce low Calmar
        if not math.isnan(qs_calmar):
            assert qs_calmar < 3.0, f"QS unexpectedly high: {qs_calmar}"


# =============================================================================
# Edge Cases
# =============================================================================


class TestCalmarEdgeCases:
    """Division safety."""

    def test_zero_drawdown_positive_return(self):
        """Zero drawdown with positive return -> cap."""
        assert calculate_calmar_ratio(50.0, 0.0) == 10.0

    def test_zero_drawdown_negative_return(self):
        """Zero drawdown with negative return -> 0."""
        assert calculate_calmar_ratio(-50.0, 0.0) == 0.0

    def test_zero_drawdown_zero_return(self):
        """Zero everything -> 0."""
        assert calculate_calmar_ratio(0.0, 0.0) == 0.0

    def test_tiny_drawdown(self):
        """Very small drawdown -> capped result."""
        result = calculate_calmar_ratio(100.0, 0.01)
        assert result == 10.0  # Should cap at 10

    def test_negative_drawdown_input(self):
        """Negative drawdown input (abs taken internally)."""
        result = calculate_calmar_ratio(50.0, -25.0)
        # abs(max_drawdown_pct) used, so result = 50/25 = 2.0
        assert abs(result - 2.0) < 0.01
