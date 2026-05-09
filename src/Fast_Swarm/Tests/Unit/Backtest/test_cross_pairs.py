"""
Unit tests for cross_pairs.py — Cross-Pair Synthesizer and Multi-Asset Data Handler.

Tests cover:
- synthesize_cross_pair_candle: single candle synthesis from USD pairs
- Zero/negative guard in synthesize_cross_pairs_df
- Batch synthesis of all 6 trio pairs
- TrioDataBundle pair lookup, relative strength, rotation suggestions
- merge_real_and_synthetic priority and gap-fill logic

All tests are synchronous and use pure pandas DataFrames — no mocks or DB needed.
"""

import pandas as pd
import pytest

from local_agents.backtest.cross_pairs import (
    DataSource,
    TrioDataBundle,
    merge_real_and_synthetic,
    synthesize_cross_pair_candle,
    synthesize_cross_pairs_df,
)


# ============================================================================
# Helper: build a minimal USD candle DataFrame
# ============================================================================


def _make_usd_df(
    timestamps: list[int],
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float] | None = None,
) -> pd.DataFrame:
    """Build a candle DataFrame with the columns expected by synthesize_cross_pairs_df."""
    n = len(timestamps)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes if volumes is not None else [100.0] * n,
        }
    )


# ============================================================================
# TestSynthesizeCrossPairCandle
# ============================================================================


class TestSynthesizeCrossPairCandle:
    """Tests for the single-candle synthesize_cross_pair_candle function."""

    def test_basic_eth_btc_ratio(self):
        """ETH/BTC open and close should equal ETH_USD / BTC_USD."""
        base = {"timestamp": 1000, "open": 3000.0, "high": 3100.0, "low": 2900.0, "close": 3050.0, "volume": 500.0}
        quote = {"timestamp": 1000, "open": 60000.0, "high": 61000.0, "low": 59000.0, "close": 60500.0, "volume": 200.0}

        candle = synthesize_cross_pair_candle(base, quote, "ETH/BTC")

        assert candle.open == pytest.approx(3000.0 / 60000.0)
        assert candle.close == pytest.approx(3050.0 / 60500.0)
        assert candle.pair == "ETH/BTC"
        assert candle.source == DataSource.SYNTHETIC

    def test_high_low_buffer(self):
        """High and low should include a 0.1% buffer around the open/close ratio range."""
        base = {"timestamp": 1000, "open": 2000.0, "high": 2200.0, "low": 1800.0, "close": 2100.0, "volume": 10.0}
        quote = {"timestamp": 1000, "open": 50000.0, "high": 51000.0, "low": 49000.0, "close": 50500.0, "volume": 5.0}

        candle = synthesize_cross_pair_candle(base, quote, "SOL/BTC")

        ratio_open = 2000.0 / 50000.0
        ratio_close = 2100.0 / 50500.0
        expected_high = max(ratio_open, ratio_close) * 1.001
        expected_low = min(ratio_open, ratio_close) * 0.999

        assert candle.high == pytest.approx(expected_high)
        assert candle.low == pytest.approx(expected_low)

    def test_volume_from_base(self):
        """Volume should come from the base asset candle."""
        base = {"timestamp": 1000, "open": 150.0, "high": 160.0, "low": 140.0, "close": 155.0, "volume": 9999.0}
        quote = {"timestamp": 1000, "open": 3000.0, "high": 3100.0, "low": 2900.0, "close": 3050.0, "volume": 1.0}

        candle = synthesize_cross_pair_candle(base, quote, "SOL/ETH")

        assert candle.volume == 9999.0
        assert candle.base_usd_volume == 9999.0
        assert candle.quote_usd_volume == 1.0


# ============================================================================
# TestZeroGuard
# ============================================================================


class TestZeroGuard:
    """Tests for zero/negative price filtering in synthesize_cross_pairs_df."""

    _TS = [1000, 2000, 3000]

    def _trio_dfs(self, btc_lows, eth_lows, sol_lows):
        """Build three USD DataFrames with configurable lows (highs = low + 100)."""
        def _df(lows):
            return _make_usd_df(
                timestamps=self._TS,
                opens=[v + 50 for v in lows],
                highs=[v + 100 for v in lows],
                lows=lows,
                closes=[v + 60 for v in lows],
            )

        return _df(btc_lows), _df(eth_lows), _df(sol_lows)

    def test_zero_low_filtered(self):
        """A row where BTC low is zero should be excluded from results."""
        btc, eth, sol = self._trio_dfs([50000, 0, 50000], [3000, 3000, 3000], [150, 150, 150])
        result = synthesize_cross_pairs_df(btc, eth, sol)

        # The zero-low row (ts=2000) should be removed
        for pair_name, df in result.items():
            assert 2000 not in df["timestamp"].values, f"{pair_name} still contains ts=2000"
            assert len(df) == 2

    def test_zero_high_filtered(self):
        """A row where ETH high is zero should be excluded."""
        # high = low + 100, so set low = -100 to get high = 0
        btc, eth, sol = self._trio_dfs([50000, 50000, 50000], [3000, -100, 3000], [150, 150, 150])
        result = synthesize_cross_pairs_df(btc, eth, sol)

        for pair_name, df in result.items():
            assert len(df) == 2, f"{pair_name} should have 2 rows after filtering"

    def test_all_invalid_returns_empty(self):
        """If every row has a zero low or high, result DataFrames should be empty."""
        btc, eth, sol = self._trio_dfs([0, 0, 0], [3000, 3000, 3000], [150, 150, 150])
        result = synthesize_cross_pairs_df(btc, eth, sol)

        for pair_name, df in result.items():
            assert len(df) == 0, f"{pair_name} should be empty"

    def test_partial_invalid_only_bad_rows_removed(self):
        """Only the invalid rows should be removed; valid rows are kept intact."""
        btc, eth, sol = self._trio_dfs(
            [50000, 0, 50000],
            [3000, 3000, 3000],
            [150, 150, 0],
        )
        result = synthesize_cross_pairs_df(btc, eth, sol)

        # ts=2000 invalid (btc low=0), ts=3000 invalid (sol low=0) -> only ts=1000 survives
        for pair_name, df in result.items():
            assert len(df) == 1, f"{pair_name} should have 1 row"
            assert df["timestamp"].iloc[0] == 1000


# ============================================================================
# TestBatchSynthesize
# ============================================================================


class TestBatchSynthesize:
    """Tests for synthesize_cross_pairs_df batch synthesis."""

    def test_all_six_trio_pairs_generated(self):
        """Should produce exactly 3 cross-pair DataFrames: ETH/BTC, SOL/BTC, SOL/ETH."""
        ts = list(range(1000, 6000, 1000))
        btc = _make_usd_df(ts, [60000]*5, [61000]*5, [59000]*5, [60500]*5, [100]*5)
        eth = _make_usd_df(ts, [3000]*5, [3100]*5, [2900]*5, [3050]*5, [200]*5)
        sol = _make_usd_df(ts, [150]*5, [160]*5, [140]*5, [155]*5, [300]*5)

        result = synthesize_cross_pairs_df(btc, eth, sol)

        assert set(result.keys()) == {"ETH/BTC", "SOL/BTC", "SOL/ETH"}
        for pair_name, df in result.items():
            assert len(df) == 5, f"{pair_name} should have 5 rows"
            assert "source" in df.columns
            # Verify OHLCV columns present
            for col in ("timestamp", "open", "high", "low", "close", "volume"):
                assert col in df.columns, f"{pair_name} missing column {col}"

    def test_misaligned_timestamps_common_index(self):
        """DataFrames with different timestamps should align on the common intersection."""
        btc = _make_usd_df([1000, 2000, 3000], [60000]*3, [61000]*3, [59000]*3, [60500]*3)
        eth = _make_usd_df([2000, 3000, 4000], [3000]*3, [3100]*3, [2900]*3, [3050]*3)
        sol = _make_usd_df([1000, 2000, 3000, 4000], [150]*4, [160]*4, [140]*4, [155]*4)

        result = synthesize_cross_pairs_df(btc, eth, sol)

        # Common timestamps: {2000, 3000}
        for pair_name, df in result.items():
            assert len(df) == 2, f"{pair_name} should have 2 rows (common timestamps)"
            assert set(df["timestamp"]) == {2000, 3000}


# ============================================================================
# TestTrioDataBundle
# ============================================================================


def _sample_candle(pair: str, open_: float, close_: float) -> dict:
    """Build a minimal candle dict for TrioDataBundle tests."""
    return {
        "pair": pair,
        "open": open_,
        "high": max(open_, close_) * 1.01,
        "low": min(open_, close_) * 0.99,
        "close": close_,
        "volume": 100.0,
        "source": "synthetic",
    }


class TestTrioDataBundle:
    """Tests for TrioDataBundle pair lookup, relative strength, and rotation."""

    def _make_bundle(self, eth_btc_open=0.05, eth_btc_close=0.048,
                     sol_btc_open=0.0025, sol_btc_close=0.0024,
                     sol_eth_open=0.05, sol_eth_close=0.049):
        return TrioDataBundle(
            timestamp=1000,
            btc_usd=_sample_candle("BTC-USD", 60000, 60500),
            eth_usd=_sample_candle("ETH-USD", 3000, 3050),
            sol_usd=_sample_candle("SOL-USD", 150, 155),
            eth_btc=_sample_candle("ETH/BTC", eth_btc_open, eth_btc_close),
            sol_btc=_sample_candle("SOL/BTC", sol_btc_open, sol_btc_close),
            sol_eth=_sample_candle("SOL/ETH", sol_eth_open, sol_eth_close),
        )

    def test_get_pair(self):
        """get_pair should return the correct candle dict for various name formats."""
        bundle = self._make_bundle()

        # Slash format
        assert bundle.get_pair("ETH/BTC")["pair"] == "ETH/BTC"
        # Dash format
        assert bundle.get_pair("BTC-USD")["pair"] == "BTC-USD"
        # No-separator format
        assert bundle.get_pair("SOLUSD")["pair"] == "SOL-USD"
        # Unknown pair returns None
        assert bundle.get_pair("DOGE/USD") is None

    def test_relative_strength(self):
        """Relative strength returns percentage changes, and all values are finite."""
        bundle = self._make_bundle()
        rs = bundle.get_relative_strength()

        assert set(rs.keys()) == {"ETH_vs_BTC", "SOL_vs_BTC", "SOL_vs_ETH"}

        # ETH/BTC went from 0.05 to 0.048 -> (0.048 - 0.05)/0.05 * 100 = -4.0%
        assert rs["ETH_vs_BTC"] == pytest.approx(-4.0)
        # SOL/BTC went from 0.0025 to 0.0024 -> -4.0%
        assert rs["SOL_vs_BTC"] == pytest.approx(-4.0)
        # SOL/ETH went from 0.05 to 0.049 -> -2.0%
        assert rs["SOL_vs_ETH"] == pytest.approx(-2.0)

    def test_suggest_rotation(self):
        """When an asset is >2% cheaper, rotation should be suggested."""
        # ETH/BTC drops 4% -> if holding BTC, should suggest rotating to ETH
        bundle = self._make_bundle(eth_btc_open=0.05, eth_btc_close=0.048)
        suggestion = bundle.suggest_rotation("BTC")

        assert suggestion is not None
        sell, buy, strength = suggestion
        assert sell == "BTC"
        assert buy in ("ETH", "SOL")  # Both drop 4%, either could be suggested
        assert strength == pytest.approx(4.0)

    def test_suggest_rotation_no_suggestion(self):
        """When price changes are small, no rotation should be suggested."""
        # All cross pairs barely move (< 2% threshold)
        bundle = self._make_bundle(
            eth_btc_open=0.05, eth_btc_close=0.0498,
            sol_btc_open=0.0025, sol_btc_close=0.02498,
            sol_eth_open=0.05, sol_eth_close=0.0499,
        )
        suggestion = bundle.suggest_rotation("BTC")
        assert suggestion is None


# ============================================================================
# TestMergeRealAndSynthetic
# ============================================================================


class TestMergeRealAndSynthetic:
    """Tests for merge_real_and_synthetic priority and gap-fill logic."""

    def test_real_preferred_over_synthetic(self):
        """When real and synthetic share a timestamp, real data takes precedence."""
        real = pd.DataFrame(
            {
                "timestamp": [1000, 2000, 3000],
                "open": [60000, 61000, 62000],
                "high": [60500, 61500, 62500],
                "low": [59500, 60500, 61500],
                "close": [60200, 61200, 62200],
                "volume": [10, 20, 30],
                "source": ["exchange", "exchange", "exchange"],
            }
        )
        synthetic = pd.DataFrame(
            {
                "timestamp": [1000, 2000, 3000, 4000],
                "open": [59999, 60999, 61999, 63000],
                "high": [60499, 61499, 62499, 63500],
                "low": [59499, 60499, 61499, 62500],
                "close": [60199, 61199, 62199, 63200],
                "volume": [1, 2, 3, 4],
                "source": ["synthetic", "synthetic", "synthetic", "synthetic"],
            }
        )

        merged = merge_real_and_synthetic(real, synthetic, "ETH/BTC")

        # Overlapping timestamps (1000, 2000, 3000) should use real data
        for ts in [1000, 2000, 3000]:
            row = merged[merged["timestamp"] == ts].iloc[0]
            assert row["source"] == "exchange"
            # Real open values differ from synthetic
            real_row = real[real["timestamp"] == ts].iloc[0]
            assert row["open"] == real_row["open"]

        # ts=4000 only exists in synthetic
        row_4000 = merged[merged["timestamp"] == 4000].iloc[0]
        assert row_4000["source"] == "synthetic"

        # Total rows = 4 (3 real + 1 synthetic gap fill)
        assert len(merged) == 4

    def test_synthetic_fills_gaps(self):
        """When real data has gaps, synthetic data should fill them."""
        real = pd.DataFrame(
            {
                "timestamp": [1000, 3000],
                "open": [60000, 62000],
                "high": [60500, 62500],
                "low": [59500, 61500],
                "close": [60200, 62200],
                "volume": [10, 30],
            }
        )
        synthetic = pd.DataFrame(
            {
                "timestamp": [1000, 2000, 3000],
                "open": [59999, 61000, 61999],
                "high": [60499, 61500, 62499],
                "low": [59499, 60500, 61499],
                "close": [60199, 61200, 62199],
                "volume": [1, 2, 3],
            }
        )

        merged = merge_real_and_synthetic(real, synthetic, "SOL/BTC")

        assert len(merged) == 3
        # ts=2000 should come from synthetic
        row_2000 = merged[merged["timestamp"] == 2000].iloc[0]
        assert row_2000["source"] == "synthetic"
        assert row_2000["open"] == 61000

        # ts=1000 and 3000 should come from real (source column added by function)
        row_1000 = merged[merged["timestamp"] == 1000].iloc[0]
        assert row_1000["source"] == "exchange"

    def test_none_real_returns_all_synthetic(self):
        """When real_df is None, all synthetic data should be returned."""
        synthetic = pd.DataFrame(
            {
                "timestamp": [1000, 2000],
                "open": [100, 200],
                "high": [110, 210],
                "low": [90, 190],
                "close": [105, 205],
                "volume": [50, 60],
            }
        )

        merged = merge_real_and_synthetic(None, synthetic, "ETH/BTC")

        assert len(merged) == 2
        assert (merged["source"] == "synthetic").all()
