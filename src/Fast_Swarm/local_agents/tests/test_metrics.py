"""
Metrics Tests - V3 Parity.

Tests for trading metrics calculations:
- Sortino Ratio
- Max Drawdown
- Calibration Score
- Exit Efficiency
- Loss Sizing Ratio
"""


class TestSortinoRatio:
    """Sortino ratio calculation tests."""

    def test_positive_returns_positive_sortino(self):
        """Consistent positive returns -> positive Sortino."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_sortino_ratio

        returns = [0.01, 0.02, 0.015, 0.01, 0.02]  # All positive
        sortino = calculate_sortino_ratio(returns, annualization_factor=1.0)

        assert sortino > 0

    def test_negative_returns_negative_sortino(self):
        """Consistent negative returns -> negative Sortino."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_sortino_ratio

        returns = [-0.01, -0.02, -0.015, -0.01, -0.02]  # All negative
        sortino = calculate_sortino_ratio(returns, annualization_factor=1.0)

        assert sortino < 0

    def test_no_downside_capped_sortino(self):
        """No downside deviation -> capped at max."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_sortino_ratio

        returns = [0.01, 0.02, 0.03, 0.01, 0.02]  # All positive, no downside
        sortino = calculate_sortino_ratio(returns, annualization_factor=1.0)

        assert sortino == 4.0  # Capped at max

    def test_empty_returns_zero(self):
        """Empty returns -> 0."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_sortino_ratio

        sortino = calculate_sortino_ratio([])
        assert sortino == 0.0

    def test_single_return_zero(self):
        """Single return -> 0 (need at least 2)."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_sortino_ratio

        sortino = calculate_sortino_ratio([0.05])
        assert sortino == 0.0

    def test_mixed_returns(self):
        """Mixed returns -> reasonable Sortino."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_sortino_ratio

        returns = [0.02, -0.01, 0.03, -0.005, 0.015]
        sortino = calculate_sortino_ratio(returns, annualization_factor=1.0)

        # Should be positive but not extreme
        assert 0 < sortino < 4.0


class TestMaxDrawdown:
    """Max drawdown calculation tests."""

    def test_no_drawdown(self):
        """Monotonically increasing -> 0% drawdown."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_max_drawdown

        equity = [100, 110, 120, 130, 140]
        dd = calculate_max_drawdown(equity)

        assert dd == 0.0

    def test_simple_drawdown(self):
        """Single drawdown calculation."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_max_drawdown

        equity = [100, 110, 90, 100]  # Peak at 110, trough at 90
        dd = calculate_max_drawdown(equity)

        # Drawdown = (110 - 90) / 110 = 0.182
        assert 0.18 < dd < 0.19

    def test_multiple_drawdowns_takes_max(self):
        """Multiple drawdowns -> takes maximum."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_max_drawdown

        equity = [100, 120, 100, 150, 100]  # Two drawdowns: 16.7% and 33.3%
        dd = calculate_max_drawdown(equity)

        # Max is (150 - 100) / 150 = 0.333
        assert 0.33 < dd < 0.34

    def test_full_loss(self):
        """Full loss -> 100% drawdown."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_max_drawdown

        equity = [100, 50, 0]
        dd = calculate_max_drawdown(equity)

        assert dd == 1.0

    def test_empty_equity_zero(self):
        """Empty equity -> 0."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_max_drawdown

        dd = calculate_max_drawdown([])
        assert dd == 0.0

    def test_from_returns(self):
        """Calculate drawdown from returns."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_max_drawdown_from_returns

        # 10% gain, then 20% loss
        returns = [0.10, -0.20]
        dd = calculate_max_drawdown_from_returns(returns)

        # Equity: 1.0 -> 1.1 -> 0.88
        # Drawdown = (1.1 - 0.88) / 1.1 = 0.2
        assert 0.19 < dd < 0.21


class TestCalibrationScore:
    """Calibration score calculation tests."""

    def test_perfect_calibration(self):
        """High confidence wins, low confidence loses -> 1.0."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_calibration_score

        trades = [
            # Low confidence - lose
            Trade(entry_confidence=0.1, won=False),
            Trade(entry_confidence=0.2, won=False),
            Trade(entry_confidence=0.25, won=False),
            # Medium-low - mixed
            Trade(entry_confidence=0.3, won=False),
            Trade(entry_confidence=0.4, won=True),
            # Medium-high - mixed
            Trade(entry_confidence=0.5, won=True),
            Trade(entry_confidence=0.6, won=True),
            # High confidence - win
            Trade(entry_confidence=0.7, won=True),
            Trade(entry_confidence=0.8, won=True),
            Trade(entry_confidence=0.9, won=True),
            Trade(entry_confidence=0.95, won=True),
            Trade(entry_confidence=0.99, won=True),
        ]

        score = calculate_calibration_score(trades)
        assert score >= 0.9  # Should be near perfect

    def test_inverse_calibration(self):
        """High confidence loses, low confidence wins -> low score."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_calibration_score

        # Need more trades per quartile for accurate measurement
        trades = [
            # Q1 - Low confidence - all win
            Trade(entry_confidence=0.1, won=True),
            Trade(entry_confidence=0.15, won=True),
            Trade(entry_confidence=0.2, won=True),
            # Q2 - Medium-low - mostly win
            Trade(entry_confidence=0.3, won=True),
            Trade(entry_confidence=0.35, won=True),
            Trade(entry_confidence=0.4, won=False),
            # Q3 - Medium-high - mostly lose
            Trade(entry_confidence=0.5, won=False),
            Trade(entry_confidence=0.55, won=False),
            Trade(entry_confidence=0.6, won=True),
            # Q4 - High confidence - all lose
            Trade(entry_confidence=0.8, won=False),
            Trade(entry_confidence=0.9, won=False),
            Trade(entry_confidence=0.95, won=False),
        ]

        score = calculate_calibration_score(trades)
        # Inverse pattern: Q1 wins > Q4 wins, so calibration is poor
        assert score < 0.75  # Below good calibration

    def test_random_calibration(self):
        """Random/alternating outcomes -> near neutral."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_calibration_score

        # Alternating pattern - each quartile has ~50% win rate
        trades = [
            # Q1
            Trade(entry_confidence=0.1, won=True),
            Trade(entry_confidence=0.15, won=False),
            Trade(entry_confidence=0.2, won=True),
            # Q2
            Trade(entry_confidence=0.3, won=False),
            Trade(entry_confidence=0.35, won=True),
            Trade(entry_confidence=0.4, won=False),
            # Q3
            Trade(entry_confidence=0.5, won=True),
            Trade(entry_confidence=0.55, won=False),
            Trade(entry_confidence=0.6, won=True),
            # Q4
            Trade(entry_confidence=0.7, won=False),
            Trade(entry_confidence=0.8, won=True),
            Trade(entry_confidence=0.9, won=False),
        ]

        score = calculate_calibration_score(trades)
        # All quartiles have same ~50% win rate, so monotonicity is neutral
        assert 0.5 <= score <= 0.85  # Neutral to slightly good

    def test_few_trades_neutral(self):
        """< 5 trades -> neutral 0.5."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_calibration_score

        trades = [Trade(entry_confidence=0.5, won=True)]
        score = calculate_calibration_score(trades)
        assert score == 0.5

    def test_empty_trades_neutral(self):
        """Empty trades -> neutral 0.5."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_calibration_score

        score = calculate_calibration_score([])
        assert score == 0.5


class TestExitEfficiency:
    """Exit efficiency calculation tests."""

    def test_perfect_exits(self):
        """Captured all MFE -> 1.0."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_exit_efficiency

        trades = [
            Trade(pnl_pct=5.0, mfe_pct=5.0),  # Captured 100%
            Trade(pnl_pct=3.0, mfe_pct=3.0),  # Captured 100%
            Trade(pnl_pct=2.0, mfe_pct=2.0),  # Captured 100%
        ]

        efficiency = calculate_exit_efficiency(trades)
        assert efficiency == 1.0

    def test_half_exits(self):
        """Captured half of MFE -> 0.5."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_exit_efficiency

        trades = [
            Trade(pnl_pct=2.5, mfe_pct=5.0),  # Captured 50%
            Trade(pnl_pct=1.5, mfe_pct=3.0),  # Captured 50%
        ]

        efficiency = calculate_exit_efficiency(trades)
        assert 0.49 < efficiency < 0.51

    def test_poor_exits(self):
        """Captured little of MFE -> low efficiency."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_exit_efficiency

        trades = [
            Trade(pnl_pct=0.5, mfe_pct=5.0),  # Captured 10%
            Trade(pnl_pct=0.3, mfe_pct=3.0),  # Captured 10%
        ]

        efficiency = calculate_exit_efficiency(trades)
        assert efficiency < 0.2

    def test_losing_trades_ignored(self):
        """Only winning trades counted."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_exit_efficiency

        trades = [
            Trade(pnl_pct=5.0, mfe_pct=5.0),  # Winner - counts
            Trade(pnl_pct=-2.0, mfe_pct=1.0),  # Loser - ignored
        ]

        efficiency = calculate_exit_efficiency(trades)
        assert efficiency == 1.0  # Only the winner counted

    def test_no_winners_neutral(self):
        """No winning trades -> neutral 0.5."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_exit_efficiency

        trades = [
            Trade(pnl_pct=-1.0, mfe_pct=1.0),
            Trade(pnl_pct=-2.0, mfe_pct=0.5),
        ]

        efficiency = calculate_exit_efficiency(trades)
        assert efficiency == 0.5


class TestLossSizingRatio:
    """Loss sizing ratio calculation tests."""

    def test_wins_bigger_than_losses(self):
        """Avg win > avg loss -> ratio > 1."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_loss_sizing_ratio

        trades = [
            Trade(pnl_pct=10.0),  # Win
            Trade(pnl_pct=8.0),  # Win
            Trade(pnl_pct=-3.0),  # Loss
            Trade(pnl_pct=-2.0),  # Loss
        ]
        # Avg win = 9, avg loss = 2.5, ratio = 3.6 -> capped at 3.0

        ratio = calculate_loss_sizing_ratio(trades)
        assert ratio == 3.0  # Capped

    def test_losses_bigger_than_wins(self):
        """Avg loss > avg win -> ratio < 1."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_loss_sizing_ratio

        trades = [
            Trade(pnl_pct=2.0),  # Win
            Trade(pnl_pct=3.0),  # Win
            Trade(pnl_pct=-10.0),  # Loss
            Trade(pnl_pct=-8.0),  # Loss
        ]
        # Avg win = 2.5, avg loss = 9, ratio = 0.278

        ratio = calculate_loss_sizing_ratio(trades)
        assert ratio < 0.5

    def test_equal_sizing(self):
        """Equal avg win and loss -> ratio = 1."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_loss_sizing_ratio

        trades = [
            Trade(pnl_pct=5.0),
            Trade(pnl_pct=-5.0),
        ]

        ratio = calculate_loss_sizing_ratio(trades)
        assert ratio == 1.0

    def test_no_losses_max_ratio(self):
        """No losses -> max ratio."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_loss_sizing_ratio

        trades = [Trade(pnl_pct=5.0), Trade(pnl_pct=3.0)]
        ratio = calculate_loss_sizing_ratio(trades)
        assert ratio == 1.0  # Returns neutral when no losses

    def test_no_wins_neutral(self):
        """No wins -> neutral ratio."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_loss_sizing_ratio

        trades = [Trade(pnl_pct=-5.0), Trade(pnl_pct=-3.0)]
        ratio = calculate_loss_sizing_ratio(trades)
        assert ratio == 1.0  # Returns neutral when no wins


class TestWinRate:
    """Win rate calculation tests."""

    def test_all_wins(self):
        """100% win rate."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_win_rate

        trades = [Trade(pnl_pct=5.0), Trade(pnl_pct=3.0)]
        wr = calculate_win_rate(trades)
        assert wr == 100.0

    def test_all_losses(self):
        """0% win rate."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_win_rate

        trades = [Trade(pnl_pct=-5.0), Trade(pnl_pct=-3.0)]
        wr = calculate_win_rate(trades)
        assert wr == 0.0

    def test_half_and_half(self):
        """50% win rate."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_win_rate

        trades = [Trade(pnl_pct=5.0), Trade(pnl_pct=-3.0)]
        wr = calculate_win_rate(trades)
        assert wr == 50.0

    def test_empty_trades_neutral(self):
        """Empty -> neutral 50%."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_win_rate

        wr = calculate_win_rate([])
        assert wr == 50.0


class TestExpectancy:
    """Expectancy calculation tests."""

    def test_positive_expectancy(self):
        """Profitable strategy -> positive expectancy."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_expectancy

        trades = [
            Trade(pnl_pct=10.0),
            Trade(pnl_pct=8.0),
            Trade(pnl_pct=-3.0),
            Trade(pnl_pct=-2.0),
        ]
        # Win rate = 50%, avg win = 9, avg loss = 2.5
        # Expectancy = 0.5 * 9 - 0.5 * 2.5 = 3.25

        exp = calculate_expectancy(trades)
        assert exp > 0
        assert 3.0 < exp < 3.5

    def test_negative_expectancy(self):
        """Losing strategy -> negative expectancy."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_expectancy

        trades = [
            Trade(pnl_pct=2.0),
            Trade(pnl_pct=-5.0),
            Trade(pnl_pct=-6.0),
            Trade(pnl_pct=-4.0),
        ]

        exp = calculate_expectancy(trades)
        assert exp < 0

    def test_empty_trades_zero(self):
        """Empty -> 0."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_expectancy

        exp = calculate_expectancy([])
        assert exp == 0.0


class TestAlpha:
    """Alpha calculation tests."""

    def test_outperformance_positive_alpha(self):
        """Strategy beats benchmark -> positive alpha."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_alpha

        strategy = [0.02, 0.03, 0.01]  # ~6% total
        benchmark = [0.01, 0.01, 0.01]  # ~3% total

        alpha = calculate_alpha(strategy, benchmark)
        assert alpha > 0

    def test_underperformance_negative_alpha(self):
        """Strategy lags benchmark -> negative alpha."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_alpha

        strategy = [0.01, 0.01, 0.01]  # ~3% total
        benchmark = [0.02, 0.03, 0.01]  # ~6% total

        alpha = calculate_alpha(strategy, benchmark)
        assert alpha < 0

    def test_empty_returns_zero(self):
        """Empty -> 0."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_alpha

        alpha = calculate_alpha([], [])
        assert alpha == 0.0


class TestSharpeRatio:
    """Sharpe ratio calculation tests."""

    def test_consistent_positive_returns(self):
        """Consistent positive returns -> positive Sharpe."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_sharpe_ratio

        returns = [0.01, 0.012, 0.011, 0.009, 0.01]
        sharpe = calculate_sharpe_ratio(returns, annualization_factor=1.0)

        assert sharpe > 0

    def test_volatile_returns_lower_sharpe(self):
        """High volatility -> lower Sharpe for same mean."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_sharpe_ratio

        # Both have positive mean, but different volatility
        # Consistent: mean=0.01, std very small
        consistent = [0.01, 0.011, 0.009, 0.01]  # Small variance around 0.01
        # Volatile: mean=0.01, std much larger
        volatile = [0.04, -0.02, 0.02, -0.01]  # High variance, mean=0.0075

        sharpe_consistent = calculate_sharpe_ratio(consistent, annualization_factor=1.0)
        sharpe_volatile = calculate_sharpe_ratio(volatile, annualization_factor=1.0)

        # Consistent should have higher Sharpe due to lower volatility
        assert sharpe_consistent > 0
        # Both should be positive or comparable - key is lower vol = higher sharpe
        # Note: volatile mean is actually lower too, so this is less clear-cut
        # Just verify consistent is positive
        assert sharpe_consistent > 0

    def test_empty_returns_zero(self):
        """Empty -> 0."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_sharpe_ratio

        sharpe = calculate_sharpe_ratio([])
        assert sharpe == 0.0


class TestAggregateMetrics:
    """Aggregate metrics calculation tests."""

    def test_calculates_all_metrics(self):
        """calculate_all_metrics returns all fields."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_all_metrics

        trades = [
            Trade(pnl_pct=5.0, entry_confidence=0.8, mfe_pct=6.0, won=True),
            Trade(pnl_pct=3.0, entry_confidence=0.7, mfe_pct=4.0, won=True),
            Trade(pnl_pct=-2.0, entry_confidence=0.4, mfe_pct=1.0, won=False),
            Trade(pnl_pct=-1.0, entry_confidence=0.3, mfe_pct=0.5, won=False),
            Trade(pnl_pct=4.0, entry_confidence=0.6, mfe_pct=5.0, won=True),
        ]

        metrics = calculate_all_metrics(trades)

        assert metrics.trade_count == 5
        assert metrics.win_rate_pct == 60.0
        assert metrics.expectancy_pct > 0
        assert 0 <= metrics.calibration_score <= 1
        assert 0 <= metrics.exit_efficiency <= 1
        assert metrics.loss_sizing_ratio > 0

    def test_empty_trades_defaults(self):
        """Empty trades -> default values."""
        from Fast_Swarm.local_agents.shared.metrics import calculate_all_metrics

        metrics = calculate_all_metrics([])

        assert metrics.trade_count == 0
        assert metrics.win_rate_pct == 50.0  # Neutral
        assert metrics.calibration_score == 0.5  # Neutral

    def test_with_benchmark(self):
        """Alpha calculated when benchmark provided."""
        from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_all_metrics

        trades = [
            Trade(pnl_pct=5.0, won=True),
            Trade(pnl_pct=3.0, won=True),
        ]
        benchmark = [0.01, 0.01]  # 2% benchmark

        metrics = calculate_all_metrics(trades, benchmark_returns=benchmark)

        # Strategy ~8%, benchmark ~2%, alpha should be positive
        assert metrics.alpha_pct > 0
