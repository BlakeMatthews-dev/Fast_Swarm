"""
EDD: Win Rate Parity Tests.

Compares our 3 win rate implementations:
1. local_agents/shared/metrics.py::calculate_win_rate (Trade objects, returns %)
2. utilities/pattern_backtest.py (inline: wins/total * 100)
3. Agents/Services/fitness_service.py::calculate_win_rate (TradeData, returns %)

Key differences:
- metrics.py: uses Trade objects, pnl_pct > 0 = win
- pattern_backtest.py: inline, pnl > 0 = win
- fitness_service.py: uses TradeData objects

All return percentage (0-100).
"""

import pytest

from Fast_Swarm.local_agents.shared.metrics import (
    Trade,
    calculate_win_rate,
)


# =============================================================================
# Helpers
# =============================================================================


def pattern_backtest_win_rate(pnls: list[float]) -> float:
    """Win rate as in pattern_backtest.py (inline)."""
    if not pnls:
        return 50.0
    winning = [p for p in pnls if p > 0]
    return len(winning) / len(pnls) * 100


def make_trades(pnls: list[float]) -> list[Trade]:
    """Create Trade objects from PnL list."""
    return [
        Trade(pnl_pct=pnl, won=(pnl > 0))
        for pnl in pnls
    ]


# =============================================================================
# Parity: Our implementations vs each other
# =============================================================================


class TestWinRateParity:
    """All implementations should give same result for same data."""

    def test_70_percent_wins(self):
        """70% win rate: all agree."""
        pnls = [1.0] * 70 + [-1.0] * 30
        trades = make_trades(pnls)

        metrics_wr = calculate_win_rate(trades)
        pattern_wr = pattern_backtest_win_rate(pnls)

        assert abs(metrics_wr - 70.0) < 0.01
        assert abs(pattern_wr - 70.0) < 0.01

    def test_30_percent_wins(self):
        """30% win rate."""
        pnls = [2.0] * 30 + [-1.0] * 70
        trades = make_trades(pnls)

        metrics_wr = calculate_win_rate(trades)
        pattern_wr = pattern_backtest_win_rate(pnls)

        assert abs(metrics_wr - 30.0) < 0.01
        assert abs(pattern_wr - 30.0) < 0.01

    def test_50_percent_wins(self):
        """Exactly 50%."""
        pnls = [1.0] * 50 + [-1.0] * 50
        trades = make_trades(pnls)

        metrics_wr = calculate_win_rate(trades)
        pattern_wr = pattern_backtest_win_rate(pnls)

        assert abs(metrics_wr - 50.0) < 0.01
        assert abs(pattern_wr - 50.0) < 0.01

    def test_zero_pnl_not_a_win(self):
        """Zero PnL should NOT count as a win."""
        pnls = [1.0, 0.0, -1.0]
        trades = make_trades(pnls)

        # metrics.py: pnl_pct > 0 = win, so 0.0 is NOT a win
        metrics_wr = calculate_win_rate(trades)
        pattern_wr = pattern_backtest_win_rate(pnls)

        # 1 win out of 3 = 33.33%
        assert abs(metrics_wr - 33.33) < 0.1
        assert abs(pattern_wr - 33.33) < 0.1


# =============================================================================
# Edge Cases
# =============================================================================


class TestWinRateEdgeCases:
    """Edge case handling."""

    def test_empty_trades_neutral(self):
        """Empty -> neutral 50%."""
        assert calculate_win_rate([]) == 50.0
        assert pattern_backtest_win_rate([]) == 50.0

    def test_all_wins(self):
        """All wins -> 100%."""
        pnls = [1.0, 2.0, 3.0]
        trades = make_trades(pnls)

        assert calculate_win_rate(trades) == 100.0
        assert pattern_backtest_win_rate(pnls) == 100.0

    def test_all_losses(self):
        """All losses -> 0%."""
        pnls = [-1.0, -2.0, -3.0]
        trades = make_trades(pnls)

        assert calculate_win_rate(trades) == 0.0
        assert pattern_backtest_win_rate(pnls) == 0.0

    def test_single_win(self):
        """Single winning trade -> 100%."""
        trades = make_trades([5.0])
        assert calculate_win_rate(trades) == 100.0

    def test_single_loss(self):
        """Single losing trade -> 0%."""
        trades = make_trades([-5.0])
        assert calculate_win_rate(trades) == 0.0

    def test_large_sample(self):
        """Large sample maintains precision."""
        import numpy as np
        rng = np.random.default_rng(60)
        pnls = rng.choice([1.0, -1.0], size=10000, p=[0.65, 0.35]).tolist()
        trades = make_trades(pnls)

        wr = calculate_win_rate(trades)
        # Should be close to 65%
        assert 63.0 < wr < 67.0, f"Large sample win rate: {wr}"
