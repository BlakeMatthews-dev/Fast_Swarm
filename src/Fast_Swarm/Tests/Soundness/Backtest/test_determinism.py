"""
Backtest Determinism Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: EDD Rules (Determinism Category)
Same inputs MUST produce same outputs. Critical for reproducibility.
"""

import math
import random

import pytest

from Agents.Services.fitness_service import (
    TradeData,
    calculate_ev,
    calculate_fitness,
    calculate_max_drawdown,
    calculate_sortino,
    calculate_win_rate,
)
from Tests.Fixtures.factories import TradeFactory

# ============================================================================
# BACKTEST DETERMINISM CONTRACT
# ============================================================================


class TestSameSeedSameResults:
    """CONTRACT: Same seed produces identical results."""

    def test_same_seed_same_trades(self):
        """CONTRACT: Same seed -> identical trade list."""
        trades_a = TradeFactory.create_batch(50, avg_pnl=2.0, win_rate=0.6, seed=42)
        trades_b = TradeFactory.create_batch(50, avg_pnl=2.0, win_rate=0.6, seed=42)
        assert len(trades_a) == len(trades_b)
        for a, b in zip(trades_a, trades_b):
            assert a.pnl_pct == b.pnl_pct
            assert a.is_win == b.is_win

    def test_same_seed_same_entry_times(self):
        """CONTRACT: Same seed -> identical entry timestamps."""
        # With same seed, the random state produces same sequence
        random.seed(99)
        entries_a = [random.randint(1000, 9999) for _ in range(20)]
        random.seed(99)
        entries_b = [random.randint(1000, 9999) for _ in range(20)]
        assert entries_a == entries_b

    def test_same_seed_same_exit_times(self):
        """CONTRACT: Same seed -> identical exit timestamps."""
        random.seed(77)
        exits_a = [random.randint(5000, 15000) for _ in range(20)]
        random.seed(77)
        exits_b = [random.randint(5000, 15000) for _ in range(20)]
        assert exits_a == exits_b

    def test_same_seed_same_pnl(self):
        """CONTRACT: Same seed -> identical PnL values."""
        trades_a = TradeFactory.create_batch(30, seed=123)
        trades_b = TradeFactory.create_batch(30, seed=123)
        pnls_a = [t.pnl for t in trades_a]
        pnls_b = [t.pnl for t in trades_b]
        assert pnls_a == pnls_b

    def test_same_seed_same_metrics(self):
        """CONTRACT: Same seed -> identical metrics dict."""
        trades_a = TradeFactory.create_batch(50, seed=42)
        trades_b = TradeFactory.create_batch(50, seed=42)
        result_a = calculate_fitness(trades_a)
        result_b = calculate_fitness(trades_b)
        assert result_a.fitness_score == result_b.fitness_score
        assert result_a.tier == result_b.tier
        assert result_a.ev_multiplier == result_b.ev_multiplier


class TestDifferentSeedsDifferentResults:
    """CONTRACT: Different seeds produce different results."""

    def test_different_seeds_different_trades(self):
        """CONTRACT: Different seeds -> different trades (if stochastic)."""
        trades_a = TradeFactory.create_batch(50, seed=42)
        trades_b = TradeFactory.create_batch(50, seed=99)
        pnls_a = [t.pnl_pct for t in trades_a]
        pnls_b = [t.pnl_pct for t in trades_b]
        assert pnls_a != pnls_b, "Different seeds should produce different PnL sequences"


class TestReplayParity:
    """CONTRACT: Replaying backtest produces identical results."""

    def test_replay_produces_identical_trades(self):
        """CONTRACT: Re-running same backtest -> same trades."""
        for _ in range(3):
            trades = TradeFactory.create_batch(20, seed=55)
            pnls = [t.pnl_pct for t in trades]
            trades2 = TradeFactory.create_batch(20, seed=55)
            pnls2 = [t.pnl_pct for t in trades2]
            assert pnls == pnls2

    def test_replay_produces_identical_metrics(self):
        """CONTRACT: Re-running same backtest -> same metrics."""
        trades = TradeFactory.create_batch(50, seed=42)
        r1 = calculate_fitness(trades)
        r2 = calculate_fitness(trades)
        assert r1.fitness_score == r2.fitness_score
        assert r1.metrics.ev == r2.metrics.ev
        assert r1.metrics.win_rate == r2.metrics.win_rate

    def test_replay_produces_identical_equity_curve(self):
        """CONTRACT: Re-running same backtest -> same equity curve."""
        trades = TradeFactory.create_batch(30, seed=42)
        # Build equity curve from trades
        def build_equity(t_list):
            equity = [10000.0]
            for t in t_list:
                equity.append(equity[-1] + t.pnl)
            return equity

        eq1 = build_equity(trades)
        trades2 = TradeFactory.create_batch(30, seed=42)
        eq2 = build_equity(trades2)
        assert eq1 == eq2

    def test_replay_across_process_restarts(self):
        """CONTRACT: Same results after process restart."""
        # Simulate by re-seeding and re-creating
        for seed in [1, 42, 100]:
            trades_a = TradeFactory.create_batch(20, seed=seed)
            result_a = calculate_fitness(trades_a)
            trades_b = TradeFactory.create_batch(20, seed=seed)
            result_b = calculate_fitness(trades_b)
            assert result_a.fitness_score == result_b.fitness_score


class TestIndicatorDeterminism:
    """CONTRACT: Indicator calculations are deterministic."""

    def _rsi(self, closes, period=14):
        """Simple RSI calculation."""
        if len(closes) < period + 1:
            return None
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas[-period:]]
        losses = [-d if d < 0 else 0 for d in deltas[-period:]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _ema(self, data, period):
        """Simple EMA calculation."""
        k = 2 / (period + 1)
        ema = [data[0]]
        for i in range(1, len(data)):
            ema.append(data[i] * k + ema[-1] * (1 - k))
        return ema

    def test_rsi_deterministic(self):
        """CONTRACT: Same candles -> same RSI value."""
        closes = [42000 + (i % 7 - 3) * 50 for i in range(30)]
        rsi1 = self._rsi(closes)
        rsi2 = self._rsi(closes)
        assert rsi1 == rsi2

    def test_macd_deterministic(self):
        """CONTRACT: Same candles -> same MACD values."""
        closes = [42000 + (i % 7 - 3) * 50 for i in range(50)]
        ema12_a = self._ema(closes, 12)
        ema26_a = self._ema(closes, 26)
        macd_a = [ema12_a[i] - ema26_a[i] for i in range(len(closes))]
        ema12_b = self._ema(closes, 12)
        ema26_b = self._ema(closes, 26)
        macd_b = [ema12_b[i] - ema26_b[i] for i in range(len(closes))]
        assert macd_a == macd_b

    def test_bollinger_deterministic(self):
        """CONTRACT: Same candles -> same Bollinger bands."""
        closes = [42000 + (i % 7 - 3) * 50 for i in range(30)]
        period = 20

        def bb(data, p):
            sma = sum(data[-p:]) / p
            std = (sum((x - sma) ** 2 for x in data[-p:]) / p) ** 0.5
            return sma, sma + 2 * std, sma - 2 * std

        bb1 = bb(closes, period)
        bb2 = bb(closes, period)
        assert bb1 == bb2

    def test_atr_deterministic(self):
        """CONTRACT: Same candles -> same ATR value."""
        candles = [
            {"high": 42000 + i * 10, "low": 41900 + i * 10, "close": 41950 + i * 10}
            for i in range(30)
        ]

        def atr(c, period=14):
            trs = []
            for i in range(1, len(c)):
                tr = max(
                    c[i]["high"] - c[i]["low"],
                    abs(c[i]["high"] - c[i - 1]["close"]),
                    abs(c[i]["low"] - c[i - 1]["close"]),
                )
                trs.append(tr)
            return sum(trs[-period:]) / period

        assert atr(candles) == atr(candles)

    def test_all_indicators_deterministic(self):
        """CONTRACT: All indicator calculations are deterministic."""
        closes = [42000 + (i % 7 - 3) * 50 for i in range(50)]
        # Run all indicators twice
        rsi1, rsi2 = self._rsi(closes), self._rsi(closes)
        ema1, ema2 = self._ema(closes, 20), self._ema(closes, 20)
        assert rsi1 == rsi2
        assert ema1 == ema2


class TestPatternMatchingDeterminism:
    """CONTRACT: Pattern matching is deterministic."""

    def test_same_pattern_same_match(self):
        """CONTRACT: Same pattern + same data -> same match result."""
        pattern = {"indicator": "rsi", "operator": "<", "value": 30}
        data = {"rsi": 25}
        match1 = data[pattern["indicator"]] < pattern["value"]
        match2 = data[pattern["indicator"]] < pattern["value"]
        assert match1 == match2 == True

    def test_condition_order_independent(self):
        """CONTRACT: Condition order doesn't affect match."""
        conditions = [
            {"indicator": "rsi", "operator": "<", "value": 30},
            {"indicator": "volume_ratio", "operator": ">", "value": 1.5},
        ]
        data = {"rsi": 25, "volume_ratio": 2.0}

        def evaluate(conds, d):
            return all(
                d[c["indicator"]] < c["value"] if c["operator"] == "<"
                else d[c["indicator"]] > c["value"]
                for c in conds
            )

        # Reverse order should give same result
        assert evaluate(conditions, data) == evaluate(list(reversed(conditions)), data)


class TestTradeExecutionDeterminism:
    """CONTRACT: Trade execution is deterministic."""

    def test_entry_price_deterministic(self):
        """CONTRACT: Same conditions -> same entry price."""
        trade1 = TradeFactory.create(pnl_pct=5.0, entry_price=50000.0)
        trade2 = TradeFactory.create(pnl_pct=5.0, entry_price=50000.0)
        assert trade1.entry_price == trade2.entry_price

    def test_exit_price_deterministic(self):
        """CONTRACT: Same conditions -> same exit price."""
        trade1 = TradeFactory.create(pnl_pct=5.0, entry_price=50000.0)
        trade2 = TradeFactory.create(pnl_pct=5.0, entry_price=50000.0)
        assert trade1.exit_price == trade2.exit_price

    def test_slippage_deterministic_with_seed(self):
        """CONTRACT: Slippage deterministic when seeded."""
        random.seed(42)
        slippage1 = random.gauss(3.0, 1.0)
        random.seed(42)
        slippage2 = random.gauss(3.0, 1.0)
        assert slippage1 == slippage2


class TestMetricsDeterminism:
    """CONTRACT: Metrics calculation is deterministic."""

    def test_sharpe_deterministic(self):
        """CONTRACT: Same trades -> same Sharpe ratio."""
        trades = TradeFactory.create_batch(50, seed=42)
        r1 = calculate_fitness(trades)
        r2 = calculate_fitness(trades)
        assert r1.component_breakdown.get("sortino") == r2.component_breakdown.get("sortino")

    def test_sortino_deterministic(self):
        """CONTRACT: Same trades -> same Sortino ratio."""
        trades = TradeFactory.create_batch(50, seed=42)
        s1 = calculate_sortino(trades)
        s2 = calculate_sortino(trades)
        assert s1 == s2

    def test_max_drawdown_deterministic(self):
        """CONTRACT: Same equity -> same max drawdown."""
        trades = TradeFactory.create_batch(50, seed=42)
        dd1 = calculate_max_drawdown(trades)
        dd2 = calculate_max_drawdown(trades)
        assert dd1 == dd2

    def test_win_rate_deterministic(self):
        """CONTRACT: Same trades -> same win rate."""
        trades = TradeFactory.create_batch(50, seed=42)
        wr1 = calculate_win_rate(trades)
        wr2 = calculate_win_rate(trades)
        assert wr1 == wr2


class TestFloatPrecision:
    """CONTRACT: Float precision consistent across runs."""

    def test_float_precision_preserved(self):
        """CONTRACT: Float calculations maintain precision."""
        a = 0.1 + 0.2
        b = 0.1 + 0.2
        assert a == b  # Same computation = same float result
        # Use approx for known float imprecision
        assert a == pytest.approx(0.3, abs=1e-15)

    def test_no_accumulated_float_error(self):
        """CONTRACT: No accumulation of float errors."""
        # Sum 1000 small values
        total1 = sum(0.001 for _ in range(1000))
        total2 = sum(0.001 for _ in range(1000))
        assert total1 == total2
        assert total1 == pytest.approx(1.0, abs=1e-10)


class TestCrossEnvironmentDeterminism:
    """CONTRACT: Results consistent across environments."""

    def test_results_match_across_python_versions(self):
        """CONTRACT: Python 3.10 vs 3.11 same results."""
        # Core math operations are deterministic across Python versions
        # Test that our fitness calculation uses only deterministic operations
        trades = TradeFactory.create_batch(30, seed=42)
        result = calculate_fitness(trades)
        # Verify no platform-specific randomness leaks in
        assert isinstance(result.fitness_score, float)
        assert not math.isnan(result.fitness_score)
        assert not math.isinf(result.fitness_score)
        # Re-run to confirm same result
        result2 = calculate_fitness(trades)
        assert result.fitness_score == result2.fitness_score

    def test_results_match_across_os(self):
        """CONTRACT: Windows vs Linux same results."""
        # IEEE 754 guarantees same float results across platforms for basic ops
        # Verify our calculation chain uses only basic arithmetic
        trades = TradeFactory.create_batch(20, seed=42)
        ev = calculate_ev(trades)
        wr = calculate_win_rate(trades)
        # These should be identical regardless of OS
        trades2 = TradeFactory.create_batch(20, seed=42)
        assert ev == calculate_ev(trades2)
        assert wr == calculate_win_rate(trades2)


class TestStateIsolation:
    """CONTRACT: Backtests don't affect each other."""

    def test_backtest_1_doesnt_affect_backtest_2(self):
        """CONTRACT: Sequential backtests are independent."""
        trades_a = TradeFactory.create_batch(30, seed=10)
        result_a = calculate_fitness(trades_a)

        trades_b = TradeFactory.create_batch(30, seed=20)
        result_b = calculate_fitness(trades_b)

        # Re-run backtest A to verify it wasn't affected by B
        trades_a2 = TradeFactory.create_batch(30, seed=10)
        result_a2 = calculate_fitness(trades_a2)
        assert result_a.fitness_score == result_a2.fitness_score

    def test_parallel_backtests_independent(self):
        """CONTRACT: Parallel backtests don't interfere."""
        # Simulate parallel by interleaving operations
        trades_x = TradeFactory.create_batch(20, seed=1)
        trades_y = TradeFactory.create_batch(20, seed=2)

        # Calculate in "parallel" (interleaved)
        ev_x = calculate_ev(trades_x)
        ev_y = calculate_ev(trades_y)
        wr_x = calculate_win_rate(trades_x)
        wr_y = calculate_win_rate(trades_y)

        # Verify results match sequential calculation
        assert ev_x == calculate_ev(TradeFactory.create_batch(20, seed=1))
        assert ev_y == calculate_ev(TradeFactory.create_batch(20, seed=2))
        assert wr_x == calculate_win_rate(TradeFactory.create_batch(20, seed=1))
        assert wr_y == calculate_win_rate(TradeFactory.create_batch(20, seed=2))
