"""
EDD: Expectancy Parity Tests.

Compares our 2 expectancy implementations:
1. local_agents/shared/metrics.py::calculate_expectancy
2. utilities/pattern_backtest.py (inline expectancy)

Formula: (Win% * AvgWin) - (Loss% * AvgLoss)

Key differences:
- metrics.py uses Trade objects
- pattern_backtest.py uses raw PnL list with pre-computed win_rate
"""

import pytest
import numpy as np

from Fast_Swarm.local_agents.shared.metrics import (
    Trade,
    calculate_expectancy,
)


# =============================================================================
# Helpers
# =============================================================================


def pattern_backtest_expectancy(pnls: list[float]) -> float:
    """Expectancy as in pattern_backtest.py (inline)."""
    if not pnls:
        return 0.0

    winning = [p for p in pnls if p > 0]
    losing = [p for p in pnls if p <= 0]

    win_rate = len(winning) / len(pnls) * 100

    avg_win = sum(winning) / len(winning) if winning else 0.0
    avg_loss = abs(sum(losing) / len(losing)) if losing else 0.0

    expectancy_pct = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * avg_loss)
    return expectancy_pct


def make_trades(pnls: list[float]) -> list[Trade]:
    """Create Trade objects from PnL list."""
    return [Trade(pnl_pct=pnl, won=(pnl > 0)) for pnl in pnls]


# =============================================================================
# Parity: Our implementations vs each other
# =============================================================================


class TestExpectancyParity:
    """Both implementations should give same result."""

    def test_positive_ev(self, winning_trades):
        """Winning trades: positive expectancy in both."""
        trades = make_trades(winning_trades)

        metrics_ev = calculate_expectancy(trades)
        pattern_ev = pattern_backtest_expectancy(winning_trades)

        assert metrics_ev > 0, f"metrics.py EV: {metrics_ev}"
        assert pattern_ev > 0, f"pattern_backtest EV: {pattern_ev}"
        # Should be close (same formula, same data)
        assert abs(metrics_ev - pattern_ev) < 0.01, (
            f"Mismatch: metrics={metrics_ev:.4f}, pattern={pattern_ev:.4f}"
        )

    def test_negative_ev(self, losing_trades):
        """Losing trades: negative expectancy in both."""
        trades = make_trades(losing_trades)

        metrics_ev = calculate_expectancy(trades)
        pattern_ev = pattern_backtest_expectancy(losing_trades)

        assert metrics_ev < 0, f"metrics.py EV: {metrics_ev}"
        assert pattern_ev < 0, f"pattern_backtest EV: {pattern_ev}"
        assert abs(metrics_ev - pattern_ev) < 0.01

    def test_breakeven_near_zero(self, breakeven_trades):
        """Breakeven trades: near-zero expectancy."""
        trades = make_trades(breakeven_trades)

        metrics_ev = calculate_expectancy(trades)
        pattern_ev = pattern_backtest_expectancy(breakeven_trades)

        # Should be near zero (within 1%)
        assert abs(metrics_ev) < 2.0, f"metrics.py EV too far from 0: {metrics_ev}"
        assert abs(pattern_ev) < 2.0, f"pattern_backtest EV too far from 0: {pattern_ev}"

    def test_known_values(self):
        """Exact known calculation."""
        # 60% wins at +2%, 40% losses at -3%
        pnls = [2.0] * 60 + [-3.0] * 40
        trades = make_trades(pnls)

        metrics_ev = calculate_expectancy(trades)
        pattern_ev = pattern_backtest_expectancy(pnls)

        # Expected: 0.6 * 2.0 - 0.4 * 3.0 = 1.2 - 1.2 = 0.0
        assert abs(metrics_ev) < 0.01, f"Should be ~0: {metrics_ev}"
        assert abs(pattern_ev) < 0.01, f"Should be ~0: {pattern_ev}"

    def test_asymmetric_payoff(self):
        """High payoff ratio compensates low win rate."""
        # 30% wins at +5%, 70% losses at -1%
        pnls = [5.0] * 30 + [-1.0] * 70
        trades = make_trades(pnls)

        metrics_ev = calculate_expectancy(trades)
        pattern_ev = pattern_backtest_expectancy(pnls)

        # Expected: 0.3 * 5.0 - 0.7 * 1.0 = 1.5 - 0.7 = 0.8
        assert abs(metrics_ev - 0.8) < 0.01
        assert abs(pattern_ev - 0.8) < 0.01


# =============================================================================
# Edge Cases
# =============================================================================


class TestExpectancyEdgeCases:
    """Division safety."""

    def test_empty(self):
        """Empty -> 0."""
        assert calculate_expectancy([]) == 0.0
        assert pattern_backtest_expectancy([]) == 0.0

    def test_all_wins(self):
        """All wins: EV = avg win."""
        pnls = [2.0, 3.0, 4.0]
        trades = make_trades(pnls)

        ev = calculate_expectancy(trades)
        # 100% win rate * avg(2,3,4) = 3.0
        assert abs(ev - 3.0) < 0.01

    def test_all_losses(self):
        """All losses: EV = -avg loss."""
        pnls = [-2.0, -3.0, -4.0]
        trades = make_trades(pnls)

        ev = calculate_expectancy(trades)
        # 0% win * 0 - 100% loss * avg(2,3,4) = -3.0
        assert abs(ev - (-3.0)) < 0.01

    def test_single_win(self):
        """Single trade win."""
        trades = make_trades([5.0])
        ev = calculate_expectancy(trades)
        assert abs(ev - 5.0) < 0.01

    def test_single_loss(self):
        """Single trade loss."""
        trades = make_trades([-5.0])
        ev = calculate_expectancy(trades)
        assert abs(ev - (-5.0)) < 0.01

    def test_zero_pnl_counted_as_loss(self):
        """Zero PnL trades counted as losses in both impls."""
        pnls = [2.0, 0.0, -2.0]
        trades = make_trades(pnls)

        ev = calculate_expectancy(trades)
        # Win: 1/3 * 2.0 = 0.667
        # Loss: 2/3 * avg(0, 2) = 2/3 * 1.0 = 0.667
        # EV = 0.667 - 0.667 = 0.0
        assert abs(ev) < 0.01
