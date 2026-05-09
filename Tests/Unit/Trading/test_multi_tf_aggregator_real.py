"""
Real integration tests for multi_tf_aggregator_service.py

Tests the MultiTFAggregator class and helper functions:
- Insert 1-minute equivalent indicator data per timeframe
- Aggregate across timeframes with tf_ prefix
- Verify staleness, freshness, and merging logic

No DB needed for the stateful aggregator (MultiTFAggregator).
"""

from datetime import datetime, timedelta, timezone

import pytest

from Fast_Swarm.Infrastructure.Services.multi_tf_aggregator_service import (
    BEAR_PROTECTION_TIMEFRAMES,
    MOTION_DERIVATIVE_COLUMNS,
    MultiTFAggregator,
    build_market_state_indicators,
    merge_indicators_with_tf_prefix,
)


# =============================================================================
# MultiTFAggregator Tests
# =============================================================================


class TestMultiTFAggregator:
    """Tests for the stateful MultiTFAggregator class."""

    def test_default_timeframes(self):
        agg = MultiTFAggregator()
        assert agg.timeframes == ["1h", "4h", "1d"]

    def test_custom_timeframes(self):
        agg = MultiTFAggregator(timeframes=["5m", "15m", "1h"])
        assert agg.timeframes == ["5m", "15m", "1h"]

    def test_update_and_get_combined_single_tf(self):
        agg = MultiTFAggregator()
        indicators = {
            "close_velocity_zscore": -1.5,
            "close_acceleration_zscore": -2.0,
            "close_jerk_zscore": 0.3,
            "adx_14_jerk_zscore": -0.8,
        }
        agg.update_timeframe("1h", indicators)
        combined = agg.get_combined()

        assert combined["tf_1h_close_velocity_zscore"] == -1.5
        assert combined["tf_1h_close_acceleration_zscore"] == -2.0
        assert combined["tf_1h_close_jerk_zscore"] == 0.3
        assert combined["tf_1h_adx_14_jerk_zscore"] == -0.8

    def test_update_and_get_combined_all_timeframes(self):
        agg = MultiTFAggregator()

        for tf, mult in [("1h", 1.0), ("4h", 2.0), ("1d", 3.0)]:
            indicators = {
                "close_velocity_zscore": -1.0 * mult,
                "close_acceleration_zscore": -1.5 * mult,
                "close_jerk_zscore": 0.5 * mult,
                "adx_14_jerk_zscore": -0.3 * mult,
            }
            agg.update_timeframe(tf, indicators)

        combined = agg.get_combined()

        # Verify all 12 keys present (4 indicators x 3 timeframes)
        assert len(combined) == 12

        # Spot-check values
        assert combined["tf_4h_close_velocity_zscore"] == pytest.approx(-2.0)
        assert combined["tf_1d_close_acceleration_zscore"] == pytest.approx(-4.5)

    def test_ignores_unknown_timeframe(self):
        agg = MultiTFAggregator()
        agg.update_timeframe("5m", {"close_velocity_zscore": 1.0})
        combined = agg.get_combined()
        assert len(combined) == 0

    def test_none_values_excluded(self):
        agg = MultiTFAggregator()
        indicators = {
            "close_velocity_zscore": None,
            "close_acceleration_zscore": -2.0,
        }
        agg.update_timeframe("1h", indicators)
        combined = agg.get_combined()

        assert "tf_1h_close_velocity_zscore" not in combined
        assert combined["tf_1h_close_acceleration_zscore"] == -2.0

    def test_only_motion_derivative_columns_stored(self):
        agg = MultiTFAggregator()
        indicators = {
            "close_velocity_zscore": -1.0,
            "rsi_14": 42.0,  # Not a motion derivative column
            "sma_200": 50000.0,  # Not a motion derivative column
        }
        agg.update_timeframe("1h", indicators)
        combined = agg.get_combined()

        assert "tf_1h_close_velocity_zscore" in combined
        assert "tf_1h_rsi_14" not in combined
        assert "tf_1h_sma_200" not in combined

    def test_latest_update_overwrites_previous(self):
        agg = MultiTFAggregator()
        agg.update_timeframe("1h", {"close_velocity_zscore": -1.0})
        agg.update_timeframe("1h", {"close_velocity_zscore": 5.0})
        combined = agg.get_combined()
        assert combined["tf_1h_close_velocity_zscore"] == 5.0


# =============================================================================
# Staleness / Freshness Tests
# =============================================================================


class TestStaleness:
    """Test staleness tracking and freshness checks."""

    def test_staleness_infinite_when_never_updated(self):
        agg = MultiTFAggregator()
        staleness = agg.get_staleness()
        for tf in agg.timeframes:
            assert staleness[tf] == float("inf")

    def test_staleness_after_update(self):
        agg = MultiTFAggregator()
        now = datetime.now(timezone.utc)
        agg.update_timeframe("1h", {"close_velocity_zscore": 1.0}, timestamp=now)
        staleness = agg.get_staleness()
        # Staleness should be very small (< 2 seconds)
        assert staleness["1h"] < 2.0
        # Others still infinite
        assert staleness["4h"] == float("inf")

    def test_is_fresh_all_updated(self):
        agg = MultiTFAggregator()
        now = datetime.now(timezone.utc)
        for tf in agg.timeframes:
            agg.update_timeframe(tf, {"close_velocity_zscore": 0.0}, timestamp=now)
        assert agg.is_fresh() is True

    def test_is_not_fresh_when_missing_update(self):
        agg = MultiTFAggregator()
        now = datetime.now(timezone.utc)
        agg.update_timeframe("1h", {"close_velocity_zscore": 0.0}, timestamp=now)
        # 4h and 1d never updated
        assert agg.is_fresh() is False

    def test_is_not_fresh_when_stale(self):
        agg = MultiTFAggregator()
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        for tf in agg.timeframes:
            agg.update_timeframe(tf, {"close_velocity_zscore": 0.0}, timestamp=old_time)
        # 1h data older than 3700 seconds (1h + 100s buffer)
        assert agg.is_fresh() is False


# =============================================================================
# merge_indicators_with_tf_prefix Tests
# =============================================================================


class TestMergeIndicators:
    """Test the merge_indicators_with_tf_prefix utility function."""

    def test_merge_adds_prefix(self):
        base = {}
        tf_indicators = {
            "close_velocity_zscore": -1.2,
            "close_acceleration_zscore": -0.5,
        }
        result = merge_indicators_with_tf_prefix(base, "1h", tf_indicators)
        assert result["tf_1h_close_velocity_zscore"] == -1.2
        assert result["tf_1h_close_acceleration_zscore"] == -0.5

    def test_merge_preserves_existing(self):
        base = {"existing_key": 42.0}
        tf_indicators = {"close_velocity_zscore": -1.0}
        result = merge_indicators_with_tf_prefix(base, "4h", tf_indicators)
        assert result["existing_key"] == 42.0
        assert result["tf_4h_close_velocity_zscore"] == -1.0

    def test_merge_skips_none_values(self):
        base = {}
        tf_indicators = {
            "close_velocity_zscore": None,
            "close_acceleration_zscore": -2.0,
        }
        result = merge_indicators_with_tf_prefix(base, "1d", tf_indicators)
        assert "tf_1d_close_velocity_zscore" not in result
        assert result["tf_1d_close_acceleration_zscore"] == -2.0

    def test_merge_only_motion_derivative_columns(self):
        base = {}
        tf_indicators = {
            "close_velocity_zscore": -1.0,
            "rsi_14": 55.0,  # Not in MOTION_DERIVATIVE_COLUMNS
        }
        result = merge_indicators_with_tf_prefix(base, "1h", tf_indicators)
        assert "tf_1h_close_velocity_zscore" in result
        assert "tf_1h_rsi_14" not in result


# =============================================================================
# build_market_state_indicators Tests
# =============================================================================


class TestBuildMarketState:
    """Test building complete market state from individual TF candle rows."""

    def test_build_from_all_timeframes(self):
        row_1h = {"close_velocity_zscore": -1.0, "close_acceleration_zscore": -2.0}
        row_4h = {"close_velocity_zscore": -0.5, "adx_14_jerk_zscore": -1.5}
        row_1d = {"close_jerk_zscore": 0.3}

        result = build_market_state_indicators("BTC", row_1h, row_4h, row_1d)

        assert result["tf_1h_close_velocity_zscore"] == -1.0
        assert result["tf_1h_close_acceleration_zscore"] == -2.0
        assert result["tf_4h_close_velocity_zscore"] == -0.5
        assert result["tf_4h_adx_14_jerk_zscore"] == -1.5
        assert result["tf_1d_close_jerk_zscore"] == 0.3

    def test_build_with_none_timeframes(self):
        result = build_market_state_indicators("BTC", tf_1h_row=None, tf_4h_row=None, tf_1d_row=None)
        assert result == {}

    def test_build_partial_timeframes(self):
        row_1h = {"close_velocity_zscore": -1.0}
        result = build_market_state_indicators("ETH", tf_1h_row=row_1h)
        assert len(result) == 1
        assert result["tf_1h_close_velocity_zscore"] == -1.0

    def test_build_skips_none_values_in_row(self):
        row_1h = {"close_velocity_zscore": None, "close_acceleration_zscore": -2.0}
        result = build_market_state_indicators("BTC", tf_1h_row=row_1h)
        assert "tf_1h_close_velocity_zscore" not in result
        assert result["tf_1h_close_acceleration_zscore"] == -2.0

    def test_build_converts_to_float(self):
        row_1h = {"close_velocity_zscore": -1}  # int, should become float
        result = build_market_state_indicators("BTC", tf_1h_row=row_1h)
        assert isinstance(result["tf_1h_close_velocity_zscore"], float)
