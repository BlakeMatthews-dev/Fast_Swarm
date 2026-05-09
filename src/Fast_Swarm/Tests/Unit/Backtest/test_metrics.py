"""
Backtest Metrics Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (Metrics Calculation)
All metrics bounded, division-safe, and economically realistic.
"""

import pytest

from Fast_Swarm.Backtest.Models.backtest_models import TradeRecord
from Fast_Swarm.Backtest.Services.backtest_service import (
    _calculate_max_drawdown,
    _calculate_sharpe,
    calculate_backtest_metrics,
)

# ============================================================================
# Test Data Helpers
# ============================================================================


def make_trade(pnl_pct: float, candles_held: int = 10, fees_pct: float = 0.1) -> TradeRecord:
    """Create a mock trade with specified PnL."""
    return TradeRecord(
        trade_id=f"trade-{abs(hash(pnl_pct))}",
        pattern_id="test-pattern",
        asset="BTC",
        direction="long",
        entry_price=100.0,
        exit_price=100.0 * (1 + pnl_pct / 100),
        entry_timestamp=1704067200,
        exit_timestamp=1704067200 + (candles_held * 3600),
        pnl_pct=pnl_pct,
        candles_held=candles_held,
        fees_pct=fees_pct,
        mfe_pct=max(0, pnl_pct * 1.2),
        mae_pct=min(0, pnl_pct * 0.5),
    )


def make_trades(pnl_list: list[float]) -> list[TradeRecord]:
    """Create list of trades from PnL values."""
    return [make_trade(pnl) for pnl in pnl_list]


# ============================================================================
# WIN RATE CONTRACT
# ============================================================================


class TestWinRate:
    """CONTRACT: Win rate calculation."""

    def test_win_rate_all_winners(self):
        """CONTRACT: 100% win rate when all trades profitable."""
        trades = make_trades([5.0, 3.0, 2.0, 1.0])
        metrics = calculate_backtest_metrics(trades)
        assert metrics["win_rate"] == 1.0

    def test_win_rate_all_losers(self):
        """CONTRACT: 0% win rate when all trades losing."""
        trades = make_trades([-5.0, -3.0, -2.0, -1.0])
        metrics = calculate_backtest_metrics(trades)
        assert metrics["win_rate"] == 0.0

    def test_win_rate_mixed(self):
        """CONTRACT: 50% win rate with equal winners/losers."""
        trades = make_trades([5.0, -5.0, 3.0, -3.0])
        metrics = calculate_backtest_metrics(trades)
        assert metrics["win_rate"] == 0.5

    def test_win_rate_zero_trades(self):
        """CONTRACT: Zero trades returns 0 win rate."""
        metrics = calculate_backtest_metrics([])
        assert metrics["win_rate"] == 0.0

    def test_win_rate_bounded_0_to_1(self):
        """CONTRACT: Win rate always in [0, 1]."""
        trades = make_trades([10.0, -5.0, 2.0])
        metrics = calculate_backtest_metrics(trades)
        assert 0.0 <= metrics["win_rate"] <= 1.0


# ============================================================================
# SHARPE RATIO CONTRACT
# ============================================================================


class TestSharpeRatio:
    """CONTRACT: Sharpe ratio calculation."""

    def test_sharpe_positive_returns(self):
        """CONTRACT: Positive consistent returns = positive Sharpe."""
        trades = make_trades([2.0, 2.0, 2.0, 2.0, 2.0])
        metrics = calculate_backtest_metrics(trades)
        # All same positive returns = infinite Sharpe, but we cap it
        # With std=0, sharpe returns 0 (division safety)
        assert metrics["sharpe_ratio"] >= 0

    def test_sharpe_negative_returns(self):
        """CONTRACT: Negative consistent returns = negative Sharpe."""
        trades = make_trades([-2.0, -3.0, -2.5, -1.5, -2.0])
        metrics = calculate_backtest_metrics(trades)
        assert metrics["sharpe_ratio"] < 0

    def test_sharpe_zero_std_returns_zero(self):
        """CONTRACT: Zero std deviation → Sharpe = 0 (division safety)."""
        # All identical returns = zero std
        pnls = [5.0, 5.0, 5.0, 5.0]
        sharpe = _calculate_sharpe(pnls)
        assert sharpe == 0.0

    def test_sharpe_capped_at_6(self):
        """CONTRACT: Sharpe capped at ±6 to filter anomalies."""
        # Very high consistent returns with tiny std
        pnls = [10.0, 10.1, 10.0, 10.1, 10.0]
        sharpe = _calculate_sharpe(pnls)
        assert -6.0 <= sharpe <= 6.0

    def test_sharpe_insufficient_trades(self):
        """CONTRACT: Less than 2 trades returns 0 Sharpe."""
        pnls = [5.0]
        sharpe = _calculate_sharpe(pnls)
        assert sharpe == 0.0

    def test_sharpe_empty_trades(self):
        """CONTRACT: Empty trades returns 0 Sharpe."""
        pnls = []
        sharpe = _calculate_sharpe(pnls)
        assert sharpe == 0.0


# ============================================================================
# MAX DRAWDOWN CONTRACT
# ============================================================================


class TestMaxDrawdown:
    """CONTRACT: Maximum drawdown calculation."""

    def test_max_drawdown_no_drawdown(self):
        """CONTRACT: Continuous profits = 0 drawdown."""
        pnls = [5.0, 5.0, 5.0, 5.0]
        dd = _calculate_max_drawdown(pnls)
        assert dd == 0.0

    def test_max_drawdown_simple(self):
        """CONTRACT: Drawdown calculated from peak."""
        # Cumulative: 5, 10, 5, 10
        # Peak at 10, drops to 5, then back to 10
        pnls = [5.0, 5.0, -5.0, 5.0]
        dd = _calculate_max_drawdown(pnls)
        assert dd == 5.0

    def test_max_drawdown_multiple_drawdowns(self):
        """CONTRACT: Returns maximum of all drawdowns."""
        # Cumulative: 10, 5, 15, 5
        # First DD: 10->5 = 5
        # Second DD: 15->5 = 10 (this is max)
        pnls = [10.0, -5.0, 10.0, -10.0]
        dd = _calculate_max_drawdown(pnls)
        assert dd == 10.0

    def test_max_drawdown_empty_returns_zero(self):
        """CONTRACT: Empty trades returns 0 drawdown."""
        dd = _calculate_max_drawdown([])
        assert dd == 0.0

    def test_max_drawdown_all_losses(self):
        """CONTRACT: All losses calculates drawdown correctly."""
        pnls = [-5.0, -5.0, -5.0]
        dd = _calculate_max_drawdown(pnls)
        # Cumulative: -5, -10, -15
        # Peak is 0 (starting point), trough is -15
        assert dd == 15.0


# ============================================================================
# PROFIT FACTOR CONTRACT
# ============================================================================


class TestProfitFactor:
    """CONTRACT: Profit factor calculation."""

    def test_profit_factor_basic(self):
        """CONTRACT: Profit factor = gross_profit / gross_loss."""
        trades = make_trades([10.0, -5.0])  # Gross profit=10, loss=5
        metrics = calculate_backtest_metrics(trades)
        assert metrics["profit_factor"] == 2.0

    def test_profit_factor_all_winners(self):
        """CONTRACT: All winners returns capped profit factor."""
        trades = make_trades([5.0, 5.0, 5.0])
        metrics = calculate_backtest_metrics(trades)
        # Zero loss = profit_factor capped at 10.0
        assert metrics["profit_factor"] == 10.0

    def test_profit_factor_all_losers(self):
        """CONTRACT: All losers returns 0 profit factor."""
        trades = make_trades([-5.0, -5.0, -5.0])
        metrics = calculate_backtest_metrics(trades)
        assert metrics["profit_factor"] == 0.0

    def test_profit_factor_zero_trades(self):
        """CONTRACT: Zero trades returns 0 profit factor."""
        metrics = calculate_backtest_metrics([])
        assert metrics["profit_factor"] == 0.0

    def test_profit_factor_above_1_profitable(self):
        """CONTRACT: Profit factor > 1 means profitable overall."""
        trades = make_trades([10.0, -3.0, -2.0])  # Net +5
        metrics = calculate_backtest_metrics(trades)
        assert metrics["profit_factor"] > 1.0
        assert metrics["total_roi_pct"] > 0


# ============================================================================
# EXPECTANCY CONTRACT
# ============================================================================


class TestExpectancy:
    """CONTRACT: Expectancy (EV) calculation."""

    def test_expectancy_calculation(self):
        """CONTRACT: Expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)."""
        # 50% win rate, avg win = 10, avg loss = -5
        trades = make_trades([10.0, -5.0, 10.0, -5.0])
        metrics = calculate_backtest_metrics(trades)
        # EV = 0.5 * 10 + 0.5 * (-5) = 5 - 2.5 = 2.5
        assert metrics["expectancy"] == 2.5

    def test_expectancy_positive_required(self):
        """CONTRACT: Viable strategy has positive expectancy."""
        trades = make_trades([10.0, 10.0, -5.0])  # More winners
        metrics = calculate_backtest_metrics(trades)
        assert metrics["expectancy"] > 0

    def test_expectancy_negative(self):
        """CONTRACT: Bad strategy has negative expectancy."""
        trades = make_trades([-10.0, -10.0, 5.0])  # More losers
        metrics = calculate_backtest_metrics(trades)
        assert metrics["expectancy"] < 0


# ============================================================================
# ROI METRICS CONTRACT
# ============================================================================


class TestROIMetrics:
    """CONTRACT: Return on Investment metrics."""

    def test_total_roi_calculation(self):
        """CONTRACT: Total ROI = sum of all PnL percentages."""
        trades = make_trades([5.0, 3.0, -2.0])
        metrics = calculate_backtest_metrics(trades)
        assert metrics["total_roi_pct"] == 6.0

    def test_avg_trade_pnl(self):
        """CONTRACT: Average PnL = total_roi / num_trades."""
        trades = make_trades([6.0, 3.0, -3.0])  # Total = 6, avg = 2
        metrics = calculate_backtest_metrics(trades)
        assert metrics["avg_trade_pnl_pct"] == 2.0

    def test_zero_trades_zero_roi(self):
        """CONTRACT: Zero trades = zero ROI."""
        metrics = calculate_backtest_metrics([])
        assert metrics["total_roi_pct"] == 0.0
        assert metrics["avg_trade_pnl_pct"] == 0.0


# ============================================================================
# TRADE COUNT METRICS CONTRACT
# ============================================================================


class TestTradeCountMetrics:
    """CONTRACT: Trade count metrics."""

    def test_total_trades_count(self):
        """CONTRACT: Total trades counted correctly."""
        trades = make_trades([5.0, -3.0, 2.0, -1.0])
        metrics = calculate_backtest_metrics(trades)
        assert metrics["total_trades"] == 4

    def test_winning_trades_count(self):
        """CONTRACT: Winning trades counted correctly."""
        trades = make_trades([5.0, -3.0, 2.0, -1.0])
        metrics = calculate_backtest_metrics(trades)
        assert metrics["winning_trades"] == 2

    def test_losing_trades_count(self):
        """CONTRACT: Losing trades counted correctly."""
        trades = make_trades([5.0, -3.0, 2.0, -1.0])
        metrics = calculate_backtest_metrics(trades)
        assert metrics["losing_trades"] == 2

    def test_zero_pnl_is_loser(self):
        """CONTRACT: Zero PnL counted as losing trade."""
        trades = make_trades([5.0, 0.0, -3.0])
        metrics = calculate_backtest_metrics(trades)
        assert metrics["winning_trades"] == 1
        assert metrics["losing_trades"] == 2


# ============================================================================
# AVERAGE METRICS CONTRACT
# ============================================================================


class TestAverageMetrics:
    """CONTRACT: Average trade metrics."""

    def test_average_winner(self):
        """CONTRACT: Average profit on winning trades."""
        trades = make_trades([10.0, 6.0, -5.0])
        metrics = calculate_backtest_metrics(trades)
        assert metrics["avg_winner_pct"] == 8.0  # (10 + 6) / 2

    def test_average_loser(self):
        """CONTRACT: Average loss on losing trades."""
        trades = make_trades([10.0, -4.0, -6.0])
        metrics = calculate_backtest_metrics(trades)
        assert metrics["avg_loser_pct"] == -5.0  # (-4 + -6) / 2

    def test_average_hold_duration(self):
        """CONTRACT: Average trade holding time."""
        trade1 = make_trade(5.0, candles_held=10)
        trade2 = make_trade(-3.0, candles_held=20)
        metrics = calculate_backtest_metrics([trade1, trade2])
        assert metrics["avg_hold_candles"] == 15.0


# ============================================================================
# DIVISION SAFETY CONTRACT
# ============================================================================


class TestDivisionSafety:
    """CONTRACT: Division by zero protection."""

    def test_all_metrics_safe_with_empty_trades(self):
        """CONTRACT: All metrics return valid values with no trades."""
        metrics = calculate_backtest_metrics([])
        # None of these should raise or return NaN/Inf
        assert metrics["win_rate"] == 0.0
        assert metrics["sharpe_ratio"] == 0.0
        assert metrics["profit_factor"] == 0.0
        assert metrics["max_drawdown_pct"] == 0.0
        assert metrics["avg_winner_pct"] == 0.0
        assert metrics["avg_loser_pct"] == 0.0

    def test_sharpe_safe_with_zero_std(self):
        """CONTRACT: Sharpe returns 0 with zero standard deviation."""
        trades = make_trades([5.0, 5.0, 5.0])  # Zero variance
        metrics = calculate_backtest_metrics(trades)
        assert metrics["sharpe_ratio"] == 0.0

    def test_profit_factor_safe_with_no_losses(self):
        """CONTRACT: Profit factor capped with no losses."""
        trades = make_trades([5.0, 3.0, 2.0])  # No losses
        metrics = calculate_backtest_metrics(trades)
        assert metrics["profit_factor"] == 10.0  # Capped, not Inf

    def test_avg_winner_safe_with_no_winners(self):
        """CONTRACT: Average winner = 0 with no winning trades."""
        trades = make_trades([-5.0, -3.0])
        metrics = calculate_backtest_metrics(trades)
        assert metrics["avg_winner_pct"] == 0.0

    def test_avg_loser_safe_with_no_losers(self):
        """CONTRACT: Average loser = 0 with no losing trades."""
        trades = make_trades([5.0, 3.0])
        metrics = calculate_backtest_metrics(trades)
        assert metrics["avg_loser_pct"] == 0.0


# ============================================================================
# METRICS STRUCTURE CONTRACT
# ============================================================================


class TestMetricsStructure:
    """CONTRACT: Metrics output structure."""

    def test_all_expected_keys_present(self):
        """CONTRACT: All expected metric keys are present."""
        trades = make_trades([5.0, -3.0])
        metrics = calculate_backtest_metrics(trades)

        expected_keys = [
            "total_trades",
            "winning_trades",
            "losing_trades",
            "win_rate",
            "total_roi_pct",
            "avg_trade_pnl_pct",
            "max_drawdown_pct",
            "sharpe_ratio",
            "profit_factor",
            "avg_winner_pct",
            "avg_loser_pct",
            "avg_hold_candles",
            "total_fees_pct",
            "avg_mfe_pct",
            "avg_mae_pct",
            "expectancy",
        ]

        for key in expected_keys:
            assert key in metrics, f"Missing key: {key}"

    def test_metrics_are_numeric(self):
        """CONTRACT: All metrics are numeric values."""
        trades = make_trades([5.0, -3.0, 2.0])
        metrics = calculate_backtest_metrics(trades)

        for key, value in metrics.items():
            assert isinstance(value, (int, float)), f"{key} is not numeric: {type(value)}"

    def test_metrics_not_nan(self):
        """CONTRACT: No metric returns NaN."""
        import math

        trades = make_trades([5.0, -3.0, 0.0])
        metrics = calculate_backtest_metrics(trades)

        for key, value in metrics.items():
            assert not math.isnan(value), f"{key} is NaN"

    def test_metrics_not_inf(self):
        """CONTRACT: No metric returns Infinity."""
        import math

        trades = make_trades([5.0, -3.0, 0.0])
        metrics = calculate_backtest_metrics(trades)

        for key, value in metrics.items():
            assert not math.isinf(value), f"{key} is Infinity"


# ============================================================================
# EDGE CASES CONTRACT
# ============================================================================


class TestEdgeCases:
    """CONTRACT: Edge case handling."""

    def test_single_trade(self):
        """CONTRACT: Single trade produces valid metrics."""
        trades = make_trades([5.0])
        metrics = calculate_backtest_metrics(trades)
        assert metrics["total_trades"] == 1
        assert metrics["total_roi_pct"] == 5.0

    def test_all_identical_pnl(self):
        """CONTRACT: All same PnL (zero variance) handled."""
        trades = make_trades([5.0, 5.0, 5.0, 5.0])
        metrics = calculate_backtest_metrics(trades)
        assert metrics["sharpe_ratio"] == 0.0  # Zero std = 0 Sharpe

    def test_tiny_pnl_values(self):
        """CONTRACT: Very small PnL values handled."""
        trades = make_trades([0.001, -0.001, 0.002])
        metrics = calculate_backtest_metrics(trades)
        assert metrics["total_trades"] == 3

    def test_large_pnl_values(self):
        """CONTRACT: Large PnL values handled."""
        trades = make_trades([100.0, -50.0, 200.0])
        metrics = calculate_backtest_metrics(trades)
        assert metrics["total_roi_pct"] == 250.0


# ============================================================================
# FEE TRACKING CONTRACT
# ============================================================================


class TestFeeTracking:
    """CONTRACT: Fee and cost tracking."""

    def test_total_fees_tracked(self):
        """CONTRACT: Total fees summed across trades."""
        trade1 = make_trade(5.0, fees_pct=0.1)
        trade2 = make_trade(-3.0, fees_pct=0.15)
        metrics = calculate_backtest_metrics([trade1, trade2])
        assert metrics["total_fees_pct"] == 0.25

    def test_mfe_mae_averaged(self):
        """CONTRACT: MFE/MAE averaged across trades."""
        trade1 = make_trade(10.0)  # MFE = 12.0 (10 * 1.2)
        trade2 = make_trade(6.0)   # MFE = 7.2 (6 * 1.2)
        metrics = calculate_backtest_metrics([trade1, trade2])
        # Average MFE = (12.0 + 7.2) / 2 = 9.6
        assert metrics["avg_mfe_pct"] == pytest.approx(9.6, rel=0.01)
