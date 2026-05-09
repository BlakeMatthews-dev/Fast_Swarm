"""
Tests for indicator_enrichment_service.compute_derived_for_candle().

Tests the pure-Python single-candle enrichment function that computes
derived indicators (MA cross, RSI conditions, Bollinger conditions, etc.)
from raw candle data.  All tests are synchronous -- no DB required.
"""

import math
from datetime import datetime, timezone

import pytest

from Fast_Swarm.Infrastructure.Services.indicator_enrichment_service import (
    compute_derived_for_candle,
    enrich_candle_dict,
)


# ---------------------------------------------------------------------------
# Helper: build a candle dict with sensible defaults
# ---------------------------------------------------------------------------

def _candle(
    close=100.0,
    ema_9=None,
    ema_21=None,
    sma_50=None,
    sma_200=None,
    macd_line=None,
    macd_signal=None,
    rsi_14=None,
    stoch_k=None,
    adx_14=None,
    plus_di=None,
    minus_di=None,
    natr_14=None,
    bb_upper=None,
    bb_lower=None,
    bb_width=None,
    volume=None,
    volume_sma_20=None,
    time=None,
    **extra,
) -> dict:
    d = {
        "close": close,
        "ema_9": ema_9,
        "ema_21": ema_21,
        "sma_50": sma_50,
        "sma_200": sma_200,
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "rsi_14": rsi_14,
        "stoch_k": stoch_k,
        "adx_14": adx_14,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "natr_14": natr_14,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_width": bb_width,
        "volume": volume,
        "volume_sma_20": volume_sma_20,
        "time": time,
    }
    d.update(extra)
    return d


# =========================================================================
# Moving Average Cross Tests (~6)
# =========================================================================


class TestMACrosses:
    """Tests for MA cross signals computed from EMA/SMA values."""

    def test_ma_cross_bullish(self):
        """ema_21 > sma_50 should produce ma_cross_20_50 = 1."""
        result = compute_derived_for_candle(_candle(ema_21=110, sma_50=100))
        assert result["ma_cross_20_50"] == 1

    def test_ma_cross_bearish(self):
        """ema_21 < sma_50 should produce ma_cross_20_50 = -1."""
        result = compute_derived_for_candle(_candle(ema_21=90, sma_50=100))
        assert result["ma_cross_20_50"] == -1

    def test_ma_cross_neutral(self):
        """ema_21 == sma_50 should produce ma_cross_20_50 = 0."""
        result = compute_derived_for_candle(_candle(ema_21=100, sma_50=100))
        assert result["ma_cross_20_50"] == 0

    def test_golden_cross(self):
        """sma_50 > sma_200 should flag golden_cross = 1."""
        result = compute_derived_for_candle(_candle(sma_50=210, sma_200=200))
        assert result["golden_cross"] == 1
        assert result["death_cross"] == 0

    def test_death_cross(self):
        """sma_50 < sma_200 should flag death_cross = 1."""
        result = compute_derived_for_candle(_candle(sma_50=190, sma_200=200))
        assert result["death_cross"] == 1
        assert result["golden_cross"] == 0

    def test_ma_cross_missing_ema(self):
        """If ema_21 is None, ma_cross_20_50 should not be set."""
        result = compute_derived_for_candle(_candle(ema_21=None, sma_50=100))
        assert "ma_cross_20_50" not in result


# =========================================================================
# Momentum Indicator Tests (~6)
# =========================================================================


class TestMomentum:
    """Tests for RSI, MACD, and Stochastic-based derived indicators."""

    def test_rsi_oversold(self):
        """RSI < 30 should mark rsi_oversold = 1."""
        result = compute_derived_for_candle(_candle(rsi_14=25))
        assert result["rsi_oversold"] == 1
        assert result["rsi_overbought"] == 0
        assert result["rsi_neutral"] == 0

    def test_rsi_overbought(self):
        """RSI > 70 should mark rsi_overbought = 1."""
        result = compute_derived_for_candle(_candle(rsi_14=75))
        assert result["rsi_overbought"] == 1
        assert result["rsi_oversold"] == 0
        assert result["rsi_neutral"] == 0

    def test_rsi_neutral(self):
        """RSI between 30 and 70 inclusive should mark rsi_neutral = 1."""
        result = compute_derived_for_candle(_candle(rsi_14=50))
        assert result["rsi_neutral"] == 1
        assert result["rsi_oversold"] == 0
        assert result["rsi_overbought"] == 0

    def test_rsi_boundary_30(self):
        """RSI == 30 is in the neutral zone (>= 30)."""
        result = compute_derived_for_candle(_candle(rsi_14=30))
        assert result["rsi_neutral"] == 1
        assert result["rsi_oversold"] == 0

    def test_macd_cross_bullish(self):
        """macd_line > macd_signal should flag macd_cross = 1."""
        result = compute_derived_for_candle(_candle(macd_line=5, macd_signal=3))
        assert result["macd_cross"] == 1

    def test_macd_cross_bearish(self):
        """macd_line < macd_signal should flag macd_cross = -1."""
        result = compute_derived_for_candle(_candle(macd_line=3, macd_signal=5))
        assert result["macd_cross"] == -1

    def test_stoch_oversold(self):
        """stoch_k < 20 should flag stoch_oversold = 1."""
        result = compute_derived_for_candle(_candle(stoch_k=15))
        assert result["stoch_oversold"] == 1
        assert result["stoch_overbought"] == 0

    def test_stoch_overbought(self):
        """stoch_k > 80 should flag stoch_overbought = 1."""
        result = compute_derived_for_candle(_candle(stoch_k=85))
        assert result["stoch_overbought"] == 1
        assert result["stoch_oversold"] == 0


# =========================================================================
# Volatility / Regime Tests (~6)
# =========================================================================


class TestVolatilityAndRegime:
    """Tests for Bollinger conditions, volatility regime, trend regime."""

    def test_bb_upper_touch(self):
        """Close >= bb_upper should mark price_at_bb_upper = 1."""
        result = compute_derived_for_candle(_candle(close=105, bb_upper=105))
        assert result["price_at_bb_upper"] == 1

    def test_bb_lower_touch(self):
        """Close <= bb_lower should mark price_at_bb_lower = 1."""
        result = compute_derived_for_candle(_candle(close=95, bb_lower=95))
        assert result["price_at_bb_lower"] == 1

    def test_bb_squeeze(self):
        """bb_width < 0.05 should flag bb_squeeze = 1."""
        result = compute_derived_for_candle(_candle(bb_width=0.03))
        assert result["bb_squeeze"] == 1

    def test_volatility_regime_low(self):
        """natr_14 < 2 => low volatility regime."""
        result = compute_derived_for_candle(_candle(natr_14=1.5))
        assert result["volatility_regime"] == "low"

    def test_volatility_regime_medium(self):
        """2 <= natr_14 < 5 => medium volatility regime."""
        result = compute_derived_for_candle(_candle(natr_14=3.5))
        assert result["volatility_regime"] == "medium"

    def test_volatility_regime_high(self):
        """natr_14 >= 5 => high volatility regime."""
        result = compute_derived_for_candle(_candle(natr_14=6.0))
        assert result["volatility_regime"] == "high"

    def test_trend_regime_sideways(self):
        """adx_14 < 20 should give sideways trend regime."""
        result = compute_derived_for_candle(_candle(adx_14=15))
        assert result["trend_regime"] == "sideways"

    def test_trend_regime_uptrend(self):
        """adx_14 >= 20 and plus_di > minus_di => uptrend."""
        result = compute_derived_for_candle(_candle(adx_14=30, plus_di=25, minus_di=15))
        assert result["trend_regime"] == "uptrend"

    def test_trend_regime_downtrend(self):
        """adx_14 >= 20 and minus_di > plus_di => downtrend."""
        result = compute_derived_for_candle(_candle(adx_14=30, plus_di=10, minus_di=20))
        assert result["trend_regime"] == "downtrend"


# =========================================================================
# Volume Condition Tests (~4)
# =========================================================================


class TestVolumeConditions:
    """Tests for high/low volume derived indicators."""

    def test_high_volume(self):
        """Volume > 1.5x SMA should flag high_volume = 1."""
        result = compute_derived_for_candle(_candle(volume=2000, volume_sma_20=1000))
        assert result["high_volume"] == 1
        assert result["low_volume"] == 0

    def test_low_volume(self):
        """Volume < 0.5x SMA should flag low_volume = 1."""
        result = compute_derived_for_candle(_candle(volume=300, volume_sma_20=1000))
        assert result["low_volume"] == 1
        assert result["high_volume"] == 0

    def test_normal_volume(self):
        """Volume between 0.5x and 1.5x SMA should be neither high nor low."""
        result = compute_derived_for_candle(_candle(volume=1000, volume_sma_20=1000))
        assert result["high_volume"] == 0
        assert result["low_volume"] == 0

    def test_volume_zero_sma(self):
        """volume_sma_20 == 0 should not produce volume conditions."""
        result = compute_derived_for_candle(_candle(volume=1000, volume_sma_20=0))
        assert "high_volume" not in result
        assert "low_volume" not in result


# =========================================================================
# Price-vs-MA Percentage Tests
# =========================================================================


class TestPriceVsMA:
    """Tests for price-vs-MA percentage and boolean indicators."""

    def test_price_vs_ema9_pct(self):
        """Percentage calculation: ((close - ema_9) / ema_9) * 100."""
        result = compute_derived_for_candle(_candle(close=105, ema_9=100))
        assert abs(result["price_vs_ema_9_pct"] - 5.0) < 0.001

    def test_price_above_sma50(self):
        """close > sma_50 should set price_above_sma_50 = 1."""
        result = compute_derived_for_candle(_candle(close=110, sma_50=100))
        assert result["price_above_sma_50"] == 1

    def test_price_below_sma50(self):
        """close < sma_50 should set price_above_sma_50 = 0."""
        result = compute_derived_for_candle(_candle(close=90, sma_50=100))
        assert result["price_above_sma_50"] == 0

    def test_price_vs_sma200_pct_negative(self):
        """Negative percentage when close < sma_200."""
        result = compute_derived_for_candle(_candle(close=90, sma_200=100))
        assert result["price_vs_sma_200_pct"] == pytest.approx(-10.0)


# =========================================================================
# Session Indicator Tests
# =========================================================================


class TestSessionIndicators:
    """Tests for trading session detection based on candle timestamp."""

    def test_asian_session(self):
        """Hour 3 UTC should be Asian session."""
        ts = datetime(2024, 6, 15, 3, 0, 0, tzinfo=timezone.utc)
        result = compute_derived_for_candle(_candle(time=ts))
        assert result["is_asian_session"] == 1
        assert result["is_london_session"] == 0

    def test_london_session(self):
        """Hour 10 UTC should be London session."""
        ts = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        result = compute_derived_for_candle(_candle(time=ts))
        assert result["is_london_session"] == 1
        assert result["is_asian_session"] == 0

    def test_us_session(self):
        """Hour 15 UTC should be US session (and also London overlap)."""
        ts = datetime(2024, 6, 15, 15, 0, 0, tzinfo=timezone.utc)
        result = compute_derived_for_candle(_candle(time=ts))
        assert result["is_us_session"] == 1
        assert result["is_london_session"] == 1

    def test_us_market_hours(self):
        """Hour 16 UTC should be US market hours."""
        ts = datetime(2024, 6, 15, 16, 0, 0, tzinfo=timezone.utc)
        result = compute_derived_for_candle(_candle(time=ts))
        assert result["is_us_market_hours"] == 1


# =========================================================================
# Edge Case Tests (~8)
# =========================================================================


class TestEdgeCases:
    """Edge cases: empty data, NaN, zero prices, etc."""

    def test_empty_candle(self):
        """Completely empty dict should return empty derived dict."""
        result = compute_derived_for_candle({})
        # close defaults to 0 inside the function, but no indicators should fire
        # because all optional fields are None
        assert isinstance(result, dict)
        # No MA cross, RSI, etc. should be set
        assert "ma_cross_20_50" not in result
        assert "rsi_oversold" not in result

    def test_close_zero(self):
        """close=0 should not crash; percentage fields need non-zero denominators."""
        result = compute_derived_for_candle(_candle(close=0, ema_9=100))
        # price_vs_ema_9_pct uses ema_9 as denominator, so it should compute
        assert "price_vs_ema_9_pct" in result
        assert result["price_vs_ema_9_pct"] == pytest.approx(-100.0)

    def test_all_zero_ma(self):
        """Zero-valued MAs should not produce percentage fields (division guard)."""
        result = compute_derived_for_candle(_candle(close=0, ema_9=0, sma_50=0))
        # ema_9=0 guard: ema_9 > 0 check should prevent division by zero
        assert "price_vs_ema_9_pct" not in result

    def test_nan_rsi(self):
        """NaN RSI should still compute conditions (NaN is not None)."""
        result = compute_derived_for_candle(_candle(rsi_14=float("nan")))
        # rsi_14 is not None, so conditions fire.  NaN comparisons are False.
        assert result["rsi_oversold"] == 0
        assert result["rsi_overbought"] == 0
        assert result["rsi_neutral"] == 0

    def test_negative_close(self):
        """Negative close should not crash (edge case for bad data)."""
        result = compute_derived_for_candle(_candle(close=-50, ema_9=100))
        assert "price_vs_ema_9_pct" in result
        assert result["price_vs_ema_9_pct"] == pytest.approx(-150.0)

    def test_very_large_values(self):
        """Very large values should not overflow."""
        big = 1e18
        result = compute_derived_for_candle(_candle(close=big, ema_9=big, sma_50=big))
        assert result["ma_cross_20_50"] == 0  # ema_21 is None => not set
        assert result["price_above_ema_9"] == 0  # equal, not above

    def test_only_close_provided(self):
        """Only close provided, all indicators None -- no derived fields besides those with defaults."""
        result = compute_derived_for_candle(_candle(close=42000))
        # Nothing should crash, and no indicator keys should appear
        assert "rsi_oversold" not in result
        assert "macd_cross" not in result

    def test_enrich_candle_dict_idempotent(self):
        """enrich_candle_dict should not overwrite existing derived values."""
        candle = _candle(rsi_14=25)
        candle["rsi_oversold"] = 0  # Manually set to 0 (wrong but pre-existing)
        candle["derived_computed_at"] = None  # Not yet enriched

        enriched = enrich_candle_dict(candle)
        # Should NOT overwrite because the key exists and is not None
        assert enriched["rsi_oversold"] == 0

    def test_enrich_candle_dict_skips_already_enriched(self):
        """enrich_candle_dict should skip if derived_computed_at is set."""
        candle = _candle(rsi_14=25)
        candle["derived_computed_at"] = datetime.now(timezone.utc)
        original_keys = set(candle.keys())
        enriched = enrich_candle_dict(candle)
        assert set(enriched.keys()) == original_keys


# =========================================================================
# Integration with sample_candles fixture
# =========================================================================


class TestWithSampleCandles:
    """Run compute_derived_for_candle against the conftest sample_candles data."""

    def test_sample_candles_no_crash(self, sample_candles):
        """Every candle from the fixture should enrich without error."""
        for candle in sample_candles:
            result = compute_derived_for_candle(candle)
            assert isinstance(result, dict)

    def test_sample_candles_returns_session_indicators(self, sample_candles):
        """Sample candles have timestamps, so session indicators should appear."""
        # sample_candles use 'timestamp' key (milliseconds), function checks 'time' first
        candle = dict(sample_candles[0])
        candle["time"] = candle.pop("timestamp")
        result = compute_derived_for_candle(candle)
        # Timestamp is epoch ms: 1704067200000 = 2024-01-01 00:00 UTC => Asian session
        assert result.get("is_asian_session") == 1

    def test_sample_candles_timestamp_as_ms(self, sample_candles):
        """Function should handle raw epoch-ms timestamps via 'timestamp' key."""
        candle = dict(sample_candles[0])
        # Keep 'timestamp' key (not 'time') -- function falls back to it
        result = compute_derived_for_candle(candle)
        assert "is_asian_session" in result
