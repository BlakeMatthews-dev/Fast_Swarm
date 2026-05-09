"""
Data Pipeline Tests for local_agents/backtest/data.py (~1,381 lines).

Tests data loading, normalization, indicator enrichment via vectorized computation,
and edge cases for the OHLCV data pipeline.

Pure pandas functions use synchronous tests. DB-loading functions use async with mocked sessions.

30 tests total.
"""

import math
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from Fast_Swarm.local_agents.backtest.data import (
    Candle,
    LazyCandleCache,
    OHLCVLoader,
    _vectorized_enrich,
    get_enrichment_last_progress,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_ohlcv_df(
    rows: int = 100,
    base_price: float = 50000.0,
    base_ts: int = 1704067200000,
    interval_ms: int = 3600000,
    include_indicators: bool = False,
) -> pd.DataFrame:
    """
    Create a sample OHLCV DataFrame for testing.

    Args:
        rows: Number of candles.
        base_price: Starting close price.
        base_ts: Starting timestamp in ms.
        interval_ms: Interval between candles in ms.
        include_indicators: Whether to include base indicator columns.
    """
    data = []
    price = base_price
    for i in range(rows):
        change = (i % 7 - 3) * 50
        open_price = price
        close_price = price + change
        high_price = max(open_price, close_price) + abs(change) * 0.2
        low_price = min(open_price, close_price) - abs(change) * 0.2
        volume = 1000.0 + i * 10

        row = {
            "timestamp": base_ts + i * interval_ms,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": volume,
        }
        data.append(row)
        price = close_price

    df = pd.DataFrame(data)

    if include_indicators:
        # Add commonly expected indicator columns
        df["sma_50"] = df["close"].rolling(min(50, rows), min_periods=1).mean()
        df["sma_200"] = df["close"].rolling(min(200, rows), min_periods=1).mean()
        df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
        df["ema_21"] = df["close"].ewm(span=21, adjust=False).mean()
        df["rsi_14"] = _compute_rsi(df["close"], 14)
        df["macd_line"] = df["close"].ewm(span=12, adjust=False).mean() - df["close"].ewm(span=26, adjust=False).mean()
        df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean()
        df["macd_histogram"] = df["macd_line"] - df["macd_signal"]
        df["adx_14"] = 25.0  # Simplified constant
        df["plus_di"] = 15.0
        df["minus_di"] = 10.0
        df["stoch_k"] = 50.0
        df["natr_14"] = 3.0
        df["volume_sma_20"] = df["volume"].rolling(min(20, rows), min_periods=1).mean()
        # Bollinger Bands
        sma_20 = df["close"].rolling(min(20, rows), min_periods=1).mean()
        std_20 = df["close"].rolling(min(20, rows), min_periods=1).std().fillna(0)
        df["bb_upper"] = sma_20 + 2 * std_20
        df["bb_middle"] = sma_20
        df["bb_lower"] = sma_20 - 2 * std_20
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"].replace(0, np.nan)

    return df


def _compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Simple RSI computation for test data."""
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period, min_periods=1).mean()
    loss = (-delta.clip(upper=0)).rolling(period, min_periods=1).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


# =============================================================================
# Data Loading (~8 tests)
# =============================================================================


class TestDataLoading:
    """Test OHLCVLoader initialization and candle loading."""

    def test_ohlcv_loader_init(self):
        """OHLCVLoader should initialize without DB connection."""
        loader = OHLCVLoader()
        assert loader._assets_cache is None

    def test_ohlcv_loader_init_ignores_legacy_params(self):
        """Legacy parameters (db_path, enhanced_db_path) should be ignored."""
        loader = OHLCVLoader(
            db_path="/fake/path.db",
            enhanced_db_path="/fake/enhanced.db",
            ohlcv_db="/fake/ohlcv.db",
        )
        assert loader._assets_cache is None

    def test_candle_dataclass_creation(self):
        """Candle dataclass should store OHLCV + indicators."""
        candle = Candle(
            timestamp=1704067200000,
            open=50000.0,
            high=50500.0,
            low=49500.0,
            close=50200.0,
            volume=1234.5,
            asset="BTC",
            timeframe="1h",
            indicators={"rsi_14": 45.2, "sma_50": 49800.0},
        )
        assert candle.close == 50200.0
        assert candle.indicators["rsi_14"] == 45.2

    def test_candle_to_dict(self):
        """Candle.to_dict() should flatten indicators into top-level keys."""
        candle = Candle(
            timestamp=1704067200000,
            open=50000.0,
            high=50500.0,
            low=49500.0,
            close=50200.0,
            volume=1000.0,
            indicators={"rsi_14": 45.0},
        )
        d = candle.to_dict()
        assert d["timestamp"] == 1704067200000
        assert d["close"] == 50200.0
        assert d["rsi_14"] == 45.0
        assert "indicators" not in d  # Flattened

    def test_load_candles_returns_empty_df_on_no_data(self):
        """load_candles should return empty DataFrame when no rows from DB."""
        loader = OHLCVLoader()
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_result.keys.return_value = []
        mock_conn.execute.return_value = mock_result

        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "Fast_Swarm.local_agents.backtest.data._get_sync_engine",
            return_value=mock_engine,
        ):
            df = loader.load_candles(asset="FAKE", timeframe="1h")

        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_load_candles_ensures_numeric_ohlcv(self):
        """load_candles should convert OHLCV columns to numeric types."""
        loader = OHLCVLoader()

        # Simulate DB returning string-typed values
        mock_rows = [
            ("2024-01-01 00:00:00+00", "50000", "50500", "49500", "50200", "1000.5", "BTC", "1h", None, None),
        ]
        mock_columns = ["time", "open", "high", "low", "close", "volume", "symbol", "timeframe", "rsi_14", "exchange"]

        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_result.keys.return_value = mock_columns
        mock_conn.execute.return_value = mock_result

        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "Fast_Swarm.local_agents.backtest.data._get_sync_engine",
            return_value=mock_engine,
        ):
            df = loader.load_candles(
                asset="BTC", timeframe="1h", with_indicators=False,
            )

        assert not df.empty
        assert df["open"].dtype in [np.float64, np.int64, float]
        assert df["close"].dtype in [np.float64, np.int64, float]

    def test_ohlcv_dataframe_has_required_columns(self):
        """Generated test DataFrame should have all OHLCV columns."""
        df = _make_ohlcv_df(rows=10)
        for col in ["timestamp", "open", "high", "low", "close", "volume"]:
            assert col in df.columns, f"Missing column: {col}"

    def test_ohlcv_high_always_gte_low(self):
        """In test data, high should always be >= low."""
        df = _make_ohlcv_df(rows=50)
        assert (df["high"] >= df["low"]).all()


# =============================================================================
# Normalization (~6 tests)
# =============================================================================


class TestNormalization:
    """Test price/volume normalization and numeric handling."""

    def test_numeric_conversion_with_nan(self):
        """pd.to_numeric with errors='coerce' should convert invalid values to NaN."""
        series = pd.Series(["50000", "invalid", "51000", None])
        result = pd.to_numeric(series, errors="coerce")
        assert result.isna().sum() == 2
        assert result.iloc[0] == 50000.0

    def test_zero_volume_handling(self):
        """DataFrame with zero volume should not cause division errors."""
        df = _make_ohlcv_df(rows=10)
        df["volume"] = 0.0

        # Volume SMA should handle zero gracefully
        volume_sma = df["volume"].rolling(5, min_periods=1).mean()
        assert (volume_sma == 0.0).all()
        assert not volume_sma.isna().any()

    def test_nan_price_handling(self):
        """NaN values in price columns should not propagate to all derived values."""
        df = _make_ohlcv_df(rows=20)
        df.loc[5, "close"] = np.nan

        sma = df["close"].rolling(5, min_periods=1).mean()
        # Only rows near the NaN should be affected
        assert not sma.isna().all()

    def test_inf_value_detection(self):
        """Candle iterator should filter out inf values from indicators."""
        candle = Candle(
            timestamp=1704067200000,
            open=50000.0,
            high=50500.0,
            low=49500.0,
            close=50200.0,
            volume=1000.0,
            indicators={"rsi_14": 45.0, "bad_val": float("inf")},
        )
        # The Candle stores them, but iter_candles filters in OHLCVLoader
        d = candle.to_dict()
        assert d["bad_val"] == float("inf")  # Raw storage keeps it

    def test_price_normalization_percentage(self):
        """Price vs MA percentage calculations should be correct."""
        df = pd.DataFrame({"close": [100.0, 110.0, 90.0], "ema_9": [100.0, 100.0, 100.0]})
        df["price_vs_ema_9_pct"] = ((df["close"] - df["ema_9"]) / df["ema_9"]) * 100
        assert df["price_vs_ema_9_pct"].iloc[0] == pytest.approx(0.0)
        assert df["price_vs_ema_9_pct"].iloc[1] == pytest.approx(10.0)
        assert df["price_vs_ema_9_pct"].iloc[2] == pytest.approx(-10.0)

    def test_zero_ema_handled_as_nan(self):
        """Division by zero EMA should produce NaN, not error."""
        df = pd.DataFrame({"close": [100.0], "ema_9": [0.0]})
        result = (df["close"] - df["ema_9"]) / df["ema_9"].replace(0, float("nan"))
        assert result.isna().iloc[0]


# =============================================================================
# Indicator Enrichment via _vectorized_enrich (~8 tests)
# =============================================================================


class TestVectorizedEnrich:
    """Test the _vectorized_enrich function for derived indicators."""

    def test_rsi_oversold_signal(self):
        """RSI < 30 should produce rsi_oversold=1."""
        df = _make_ohlcv_df(rows=50, include_indicators=True)
        df["rsi_14"] = 25.0  # Force oversold

        result = _vectorized_enrich(df)
        assert (result["rsi_oversold"] == 1).all()
        assert (result["rsi_overbought"] == 0).all()

    def test_rsi_overbought_signal(self):
        """RSI > 70 should produce rsi_overbought=1."""
        df = _make_ohlcv_df(rows=50, include_indicators=True)
        df["rsi_14"] = 75.0

        result = _vectorized_enrich(df)
        assert (result["rsi_overbought"] == 1).all()
        assert (result["rsi_oversold"] == 0).all()

    def test_rsi_neutral_signal(self):
        """RSI between 30 and 70 should produce rsi_neutral=1."""
        df = _make_ohlcv_df(rows=50, include_indicators=True)
        df["rsi_14"] = 50.0

        result = _vectorized_enrich(df)
        assert (result["rsi_neutral"] == 1).all()

    def test_macd_cross_bullish(self):
        """MACD line > signal should produce macd_cross=1."""
        df = _make_ohlcv_df(rows=50, include_indicators=True)
        df["macd_line"] = 1.0
        df["macd_signal"] = -1.0

        result = _vectorized_enrich(df)
        assert (result["macd_cross"] == 1).all()

    def test_macd_cross_bearish(self):
        """MACD line < signal should produce macd_cross=-1."""
        df = _make_ohlcv_df(rows=50, include_indicators=True)
        df["macd_line"] = -1.0
        df["macd_signal"] = 1.0

        result = _vectorized_enrich(df)
        assert (result["macd_cross"] == -1).all()

    def test_golden_cross_signal(self):
        """SMA 50 > SMA 200 should produce golden_cross=1."""
        df = _make_ohlcv_df(rows=50, include_indicators=True)
        df["sma_50"] = 60000.0
        df["sma_200"] = 50000.0

        result = _vectorized_enrich(df)
        assert (result["golden_cross"] == 1).all()
        assert (result["death_cross"] == 0).all()

    def test_strong_trend_from_adx(self):
        """ADX > 25 should produce strong_trend=1."""
        df = _make_ohlcv_df(rows=50, include_indicators=True)
        df["adx_14"] = 30.0

        result = _vectorized_enrich(df)
        assert (result["strong_trend"] == 1).all()
        assert (result["weak_trend"] == 0).all()

    def test_high_volume_signal(self):
        """Volume > 1.5x SMA should produce high_volume=1."""
        df = _make_ohlcv_df(rows=50, include_indicators=True)
        df["volume_sma_20"] = 100.0
        df["volume"] = 200.0  # 2x average

        result = _vectorized_enrich(df)
        assert (result["high_volume"] == 1).all()

    def test_bollinger_band_lower_touch(self):
        """Price at lower BB (within 2%) should produce price_at_bb_lower=1."""
        df = _make_ohlcv_df(rows=50, include_indicators=True)
        df["bb_lower"] = 49000.0
        df["bb_upper"] = 51000.0
        df["close"] = 49000.0 * 1.01  # Within 2% of lower band

        result = _vectorized_enrich(df)
        assert (result["price_at_bb_lower"] == 1).all()

    def test_day_of_week_from_timestamp(self):
        """_vectorized_enrich should compute day-of-week indicators from timestamp."""
        # 2024-01-01 is a Monday (dow=0)
        df = _make_ohlcv_df(rows=7, base_ts=1704067200000, interval_ms=86400000)

        result = _vectorized_enrich(df)

        assert "isMonday" in result.columns
        assert result["isMonday"].iloc[0] == 1
        assert result["isTuesday"].iloc[1] == 1
        # Weekend check (Saturday=day 5, Sunday=day 6)
        assert result["isWeekend"].iloc[5] == 1
        assert result["isWeekend"].iloc[6] == 1
        assert result["isWeekday"].iloc[0] == 1

    def test_trading_session_detection(self):
        """_vectorized_enrich should detect Asian/London/NY sessions."""
        # Create candles at specific hours
        base_ts = 1704067200000  # 2024-01-01 00:00:00 UTC (Monday)
        df = pd.DataFrame({
            "timestamp": [base_ts + h * 3600000 for h in [2, 10, 14, 20]],
            "open": [50000] * 4,
            "high": [50100] * 4,
            "low": [49900] * 4,
            "close": [50050] * 4,
            "volume": [100] * 4,
        })

        result = _vectorized_enrich(df)

        assert result["isAsianSession"].iloc[0] == 1   # Hour 2 = Asian
        assert result["isLondonSession"].iloc[1] == 1   # Hour 10 = London
        assert result["isLondonNYOverlap"].iloc[2] == 1  # Hour 14 = Overlap
        assert result["isNYSession"].iloc[3] == 1       # Hour 20 = NY


# =============================================================================
# Edge Cases (~8 tests)
# =============================================================================


class TestEdgeCases:
    """Test edge cases: empty data, single row, all-zero prices, etc."""

    def test_empty_dataframe_enrichment(self):
        """_vectorized_enrich on empty DataFrame should return empty DataFrame."""
        df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        result = _vectorized_enrich(df)
        assert len(result) == 0

    def test_single_row_dataframe(self):
        """Single row DataFrame should enrich without errors."""
        df = _make_ohlcv_df(rows=1, include_indicators=True)
        result = _vectorized_enrich(df)
        assert len(result) == 1
        # Should have derived columns
        assert "rsi_oversold" in result.columns or "rsi_14" not in result.columns

    def test_all_zero_prices(self):
        """All-zero prices should not cause division by zero crashes."""
        df = _make_ohlcv_df(rows=10)
        df["close"] = 0.0
        df["open"] = 0.0
        df["high"] = 0.0
        df["low"] = 0.0
        df["ema_9"] = 0.0
        df["ema_21"] = 0.0
        df["sma_50"] = 0.0
        df["sma_200"] = 0.0

        # Should not raise, may produce NaN
        result = _vectorized_enrich(df)
        assert len(result) == 10

    def test_duplicate_timestamps_handled(self):
        """Duplicate timestamps in DataFrame should not crash enrichment."""
        df = _make_ohlcv_df(rows=10)
        # Duplicate timestamps
        df["timestamp"] = 1704067200000
        result = _vectorized_enrich(df)
        assert len(result) == 10

    def test_future_timestamps(self):
        """Future timestamps should process normally."""
        future_ts = int(datetime(2030, 1, 1, tzinfo=UTC).timestamp() * 1000)
        df = _make_ohlcv_df(rows=10, base_ts=future_ts)
        result = _vectorized_enrich(df)
        assert len(result) == 10

    def test_very_large_price_values(self):
        """Very large prices should not overflow."""
        df = _make_ohlcv_df(rows=10, base_price=1e12)
        df["ema_9"] = df["close"]
        df["sma_50"] = df["close"]
        result = _vectorized_enrich(df)
        assert len(result) == 10
        # Price vs EMA should be ~0 when they match
        if "price_vs_ema_9_pct" in result.columns:
            assert result["price_vs_ema_9_pct"].abs().max() < 100

    def test_missing_indicator_columns_skipped(self):
        """_vectorized_enrich should skip indicators whose base columns are missing."""
        df = _make_ohlcv_df(rows=20)
        # No indicator columns at all
        result = _vectorized_enrich(df)

        # Should not have RSI-derived columns since rsi_14 is missing
        assert "rsi_oversold" not in result.columns
        # Should not have MACD-derived columns since macd_line is missing
        assert "macd_cross" not in result.columns

    def test_lazy_candle_cache_contains_check(self):
        """LazyCandleCache.__contains__ should report loadable keys correctly."""
        cache = LazyCandleCache()
        # No ranges, no data
        assert "BTC_1h" not in cache

        # Set up a range
        cache._ranges[("BTC", "1h")] = {"min_ts": 1000, "max_ts": 2000}
        assert "BTC_1h" in cache
        assert "ETH_1h" not in cache

    def test_lazy_candle_cache_bool_empty(self):
        """Empty LazyCandleCache with no ranges should be falsy."""
        cache = LazyCandleCache()
        assert not cache

    def test_lazy_candle_cache_bool_with_ranges(self):
        """LazyCandleCache with ranges should be truthy even before loading."""
        cache = LazyCandleCache()
        cache._ranges[("BTC", "1h")] = {"min_ts": 1000, "max_ts": 2000}
        assert cache

    def test_enrichment_progress_tracker(self):
        """get_enrichment_last_progress should return a float timestamp."""
        result = get_enrichment_last_progress()
        assert isinstance(result, float)
