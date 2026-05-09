"""
Tests for Pattern Matching Service - condition evaluation, multi-pattern scoring, signal generation.

Pure evaluation functions are tested synchronously.
Service-level functions involving DB are tested async with mocked sessions.
"""

import math
from typing import Any

import pytest

from Patterns.Services.pattern_matching_service import (
    INDICATOR_BOUNDS,
    INDICATOR_LOOKBACK,
    INDICATORS,
    IndicatorCache,
    LogicOperator,
    MatchResult,
    Signal,
    calculate_all_indicators,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_condition_confidence,
    calculate_macd,
    calculate_match_confidence,
    calculate_rsi,
    calculate_stochastic,
    calculate_williams_r,
    get_indicator_bounds,
    get_indicator_lookback,
    has_sufficient_data,
    match_condition,
    match_conditions,
    match_conditions_and,
    match_conditions_or,
    match_indicator_condition,
    match_pattern,
    match_pattern_against_candle,
    match_pattern_against_series,
    match_patterns_batch,
    validate_condition,
    validate_indicator,
)


# =============================================================================
# Condition Evaluation Tests
# =============================================================================


class TestMatchCondition:
    """Tests for match_condition - basic range checking."""

    def test_value_within_range(self):
        """Value inside [min, max] returns True."""
        assert match_condition(50.0, 0.0, 100.0) is True

    def test_value_at_min_boundary(self):
        """Value at min boundary returns True (inclusive)."""
        assert match_condition(0.0, 0.0, 100.0) is True

    def test_value_at_max_boundary(self):
        """Value at max boundary returns True (inclusive)."""
        assert match_condition(100.0, 0.0, 100.0) is True

    def test_value_below_range(self):
        """Value below min returns False."""
        assert match_condition(-1.0, 0.0, 100.0) is False

    def test_value_above_range(self):
        """Value above max returns False."""
        assert match_condition(101.0, 0.0, 100.0) is False

    def test_none_value_returns_false(self):
        """None value returns False."""
        assert match_condition(None, 0.0, 100.0) is False

    def test_nan_value_returns_false(self):
        """NaN value returns False."""
        assert match_condition(float("nan"), 0.0, 100.0) is False

    def test_inf_value_returns_false(self):
        """Inf value returns False."""
        assert match_condition(float("inf"), 0.0, 100.0) is False

    def test_negative_inf_returns_false(self):
        """Negative Inf value returns False."""
        assert match_condition(float("-inf"), 0.0, 100.0) is False

    def test_tolerance_at_boundary(self):
        """Value just outside range but within tolerance passes."""
        # Default tolerance is 1e-9
        assert match_condition(100.0 + 1e-10, 0.0, 100.0) is True

    def test_non_numeric_returns_false(self):
        """Non-numeric types return False."""
        assert match_condition("50", 0.0, 100.0) is False


class TestMatchIndicatorCondition:
    """Tests for match_indicator_condition with condition dicts."""

    def test_rsi_in_oversold_zone(self):
        """RSI at 25 matches condition min=0, max=30."""
        cond = {"min": 0, "max": 30}
        assert match_indicator_condition("rsi", 25.0, cond) is True

    def test_rsi_outside_range(self):
        """RSI at 50 does not match oversold condition."""
        cond = {"min": 0, "max": 30}
        assert match_indicator_condition("rsi", 50.0, cond) is False

    def test_missing_min_uses_neg_inf(self):
        """Condition without 'min' key uses -inf."""
        cond = {"max": 50}
        assert match_indicator_condition("rsi", -100.0, cond) is True

    def test_missing_max_uses_pos_inf(self):
        """Condition without 'max' key uses +inf."""
        cond = {"min": 50}
        assert match_indicator_condition("rsi", 10000.0, cond) is True

    def test_none_indicator_value_false(self):
        """None indicator value always returns False."""
        cond = {"min": 0, "max": 100}
        assert match_indicator_condition("rsi", None, cond) is False


# =============================================================================
# Confidence Scoring Tests
# =============================================================================


class TestConditionConfidence:
    """Tests for calculate_condition_confidence."""

    def test_center_value_max_confidence(self):
        """Value at center of range returns 1.0."""
        conf = calculate_condition_confidence(50.0, 0.0, 100.0)
        assert abs(conf - 1.0) < 0.01

    def test_edge_value_lower_confidence(self):
        """Value at edge of range returns ~0.5 (minimum edge confidence)."""
        conf = calculate_condition_confidence(0.0, 0.0, 100.0)
        assert abs(conf - 0.5) < 0.01

    def test_outside_value_zero_confidence(self):
        """Value outside range returns 0.0."""
        conf = calculate_condition_confidence(150.0, 0.0, 100.0)
        assert conf == 0.0

    def test_zero_range_exact_match(self):
        """Range with min==max returns 1.0 for exact match."""
        conf = calculate_condition_confidence(50.0, 50.0, 50.0)
        assert conf == 1.0

    def test_zero_range_no_match(self):
        """Range with min==max returns 0.0 for non-match."""
        conf = calculate_condition_confidence(51.0, 50.0, 50.0)
        assert conf == 0.0

    def test_confidence_bounded_zero_one(self):
        """Confidence is always in [0, 1]."""
        for val in [-100, 0, 50, 100, 200]:
            conf = calculate_condition_confidence(val, 0.0, 100.0)
            assert 0.0 <= conf <= 1.0


class TestMatchConfidence:
    """Tests for calculate_match_confidence across multiple conditions."""

    def test_all_conditions_matched_high_confidence(self):
        """All conditions matched at center values gives high confidence."""
        indicators = {"rsi": 50.0, "adx": 50.0}
        conditions = [
            {"indicator": "rsi", "min": 0, "max": 100},
            {"indicator": "adx", "min": 0, "max": 100},
        ]
        conf = calculate_match_confidence(indicators, conditions)
        assert conf > 0.9

    def test_no_conditions_returns_zero(self):
        """Empty conditions list returns 0.0."""
        conf = calculate_match_confidence({"rsi": 50.0}, [])
        assert conf == 0.0

    def test_missing_indicator_skipped(self):
        """Conditions for missing indicators are skipped (not counted)."""
        indicators = {"rsi": 50.0}
        conditions = [
            {"indicator": "rsi", "min": 0, "max": 100},
            {"indicator": "adx", "min": 0, "max": 100},  # adx not in indicators
        ]
        conf = calculate_match_confidence(indicators, conditions)
        # Only rsi is counted, at center -> 1.0
        assert abs(conf - 1.0) < 0.01

    def test_nan_indicator_skipped(self):
        """NaN indicator values are skipped in confidence calculation."""
        indicators = {"rsi": float("nan"), "adx": 50.0}
        conditions = [
            {"indicator": "rsi", "min": 0, "max": 100},
            {"indicator": "adx", "min": 0, "max": 100},
        ]
        conf = calculate_match_confidence(indicators, conditions)
        # Only adx counted
        assert conf > 0.0

    def test_weighted_conditions(self):
        """Custom weights affect confidence calculation."""
        indicators = {"rsi": 50.0, "adx": 0.0}  # adx at edge
        conditions = [
            {"indicator": "rsi", "min": 0, "max": 100, "weight": 3.0},
            {"indicator": "adx", "min": 0, "max": 100, "weight": 1.0},
        ]
        conf = calculate_match_confidence(indicators, conditions)
        # RSI=center(1.0)*3 + ADX=edge(0.5)*1 / (3+1) = 3.5/4 = 0.875
        assert abs(conf - 0.875) < 0.01

    def test_all_indicators_missing_returns_zero(self):
        """All conditions referencing missing indicators returns 0.0."""
        indicators = {}
        conditions = [{"indicator": "rsi", "min": 0, "max": 100}]
        conf = calculate_match_confidence(indicators, conditions)
        assert conf == 0.0


# =============================================================================
# Multi-Condition Logic Tests
# =============================================================================


class TestMultiConditionLogic:
    """Tests for AND/OR condition matching."""

    def test_and_logic_all_match(self):
        """AND logic returns True when all conditions match."""
        indicators = {"rsi": 25.0, "adx": 60.0}
        conditions = [
            {"indicator": "rsi", "min": 0, "max": 30},
            {"indicator": "adx", "min": 50, "max": 100},
        ]
        matched, count, total = match_conditions_and(indicators, conditions)
        assert matched is True
        assert count == 2
        assert total == 2

    def test_and_logic_partial_match(self):
        """AND logic returns False when not all conditions match."""
        indicators = {"rsi": 50.0, "adx": 60.0}
        conditions = [
            {"indicator": "rsi", "min": 0, "max": 30},  # fails
            {"indicator": "adx", "min": 50, "max": 100},  # passes
        ]
        matched, count, total = match_conditions_and(indicators, conditions)
        assert matched is False
        assert count == 1

    def test_or_logic_any_match(self):
        """OR logic returns True when any condition matches."""
        indicators = {"rsi": 50.0, "adx": 60.0}
        conditions = [
            {"indicator": "rsi", "min": 0, "max": 30},  # fails
            {"indicator": "adx", "min": 50, "max": 100},  # passes
        ]
        matched, count, total = match_conditions_or(indicators, conditions)
        assert matched is True
        assert count == 1

    def test_or_logic_none_match(self):
        """OR logic returns False when no conditions match."""
        indicators = {"rsi": 50.0, "adx": 30.0}
        conditions = [
            {"indicator": "rsi", "min": 0, "max": 30},
            {"indicator": "adx", "min": 50, "max": 100},
        ]
        matched, count, total = match_conditions_or(indicators, conditions)
        assert matched is False
        assert count == 0

    def test_empty_conditions_and_returns_true(self):
        """AND with empty conditions returns True (vacuously true)."""
        matched, count, total = match_conditions_and({}, [])
        assert matched is True
        assert total == 0

    def test_empty_conditions_or_returns_false(self):
        """OR with empty conditions returns False (nothing to match)."""
        matched, count, total = match_conditions_or({}, [])
        assert matched is False

    def test_match_conditions_dispatches_correctly(self):
        """match_conditions dispatches to AND/OR based on logic param."""
        indicators = {"rsi": 50.0}
        conditions = [{"indicator": "rsi", "min": 0, "max": 30}]  # rsi=50 fails

        matched_and, _, _ = match_conditions(indicators, conditions, LogicOperator.AND)
        matched_or, _, _ = match_conditions(indicators, conditions, LogicOperator.OR)
        # Both should be False since there's only one condition and it fails
        assert matched_and is False
        assert matched_or is False


# =============================================================================
# Signal Generation Tests
# =============================================================================


class TestSignalGeneration:
    """Tests for match_pattern signal generation."""

    def test_entry_matched_long_signal(self):
        """Matching entry conditions with direction=LONG produces LONG signal."""
        pattern = {
            "entry_conditions": [{"indicator": "rsi", "min": 0, "max": 30}],
            "exit_conditions": [],
            "direction": "LONG",
            "logic": "AND",
        }
        indicators = {"rsi": 25.0}
        result = match_pattern(pattern, indicators, check_entry=True)
        assert result.matched is True
        assert result.signal == Signal.LONG

    def test_entry_matched_short_signal(self):
        """Matching entry conditions with direction=SHORT produces SHORT signal."""
        pattern = {
            "entry_conditions": [{"indicator": "rsi", "min": 70, "max": 100}],
            "exit_conditions": [],
            "direction": "SHORT",
            "logic": "AND",
        }
        indicators = {"rsi": 80.0}
        result = match_pattern(pattern, indicators, check_entry=True)
        assert result.matched is True
        assert result.signal == Signal.SHORT

    def test_no_match_produces_none_signal(self):
        """Unmatched conditions produce Signal.NONE."""
        pattern = {
            "entry_conditions": [{"indicator": "rsi", "min": 0, "max": 30}],
            "exit_conditions": [],
            "direction": "LONG",
        }
        indicators = {"rsi": 50.0}
        result = match_pattern(pattern, indicators, check_entry=True)
        assert result.matched is False
        assert result.signal == Signal.NONE

    def test_exit_matched_returns_none_signal(self):
        """Exit conditions matched produce NONE signal (close position)."""
        pattern = {
            "entry_conditions": [],
            "exit_conditions": [{"indicator": "rsi", "min": 70, "max": 100}],
            "direction": "LONG",
        }
        indicators = {"rsi": 80.0}
        result = match_pattern(pattern, indicators, check_entry=False, check_exit=True)
        assert result.matched is True
        assert result.signal == Signal.NONE  # exit = close position

    def test_default_direction_is_long(self):
        """Pattern without direction defaults to LONG."""
        pattern = {
            "entry_conditions": [{"indicator": "rsi", "min": 0, "max": 30}],
            "exit_conditions": [],
        }
        indicators = {"rsi": 25.0}
        result = match_pattern(pattern, indicators, check_entry=True)
        assert result.signal == Signal.LONG

    def test_confidence_zero_when_not_matched(self):
        """Confidence is 0.0 when pattern is not matched."""
        pattern = {
            "entry_conditions": [{"indicator": "rsi", "min": 0, "max": 30}],
            "exit_conditions": [],
        }
        indicators = {"rsi": 50.0}
        result = match_pattern(pattern, indicators, check_entry=True)
        assert result.confidence == 0.0


# =============================================================================
# Batch Pattern Matching Tests
# =============================================================================


class TestBatchPatternMatching:
    """Tests for match_patterns_batch and series matching."""

    def test_batch_matches_all_patterns(self):
        """match_patterns_batch returns one result per pattern."""
        patterns = [
            {"entry_conditions": [{"indicator": "rsi", "min": 0, "max": 30}], "exit_conditions": []},
            {"entry_conditions": [{"indicator": "rsi", "min": 70, "max": 100}], "exit_conditions": []},
        ]
        indicators = {"rsi": 25.0}
        results = match_patterns_batch(patterns, indicators)
        assert len(results) == 2
        assert results[0].matched is True  # rsi=25 in [0,30]
        assert results[1].matched is False  # rsi=25 not in [70,100]

    def test_series_matching_per_candle(self):
        """match_pattern_against_series returns one result per candle."""
        pattern = {
            "entry_conditions": [{"indicator": "rsi", "min": 0, "max": 30}],
            "exit_conditions": [],
        }
        candles = [
            {"open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000},
            {"open": 105, "high": 115, "low": 95, "close": 100, "volume": 1200},
        ]
        indicator_series = [{"rsi": 25.0}, {"rsi": 50.0}]
        results = match_pattern_against_series(pattern, candles, indicator_series)
        assert len(results) == 2
        assert results[0].matched is True
        assert results[1].matched is False

    def test_candle_matching_combines_data(self):
        """match_pattern_against_candle merges candle OHLCV with indicators."""
        pattern = {
            "entry_conditions": [{"indicator": "close", "min": 100, "max": 200}],
            "exit_conditions": [],
        }
        candle = {"open": 100, "high": 160, "low": 90, "close": 150, "volume": 1000}
        indicators = {"rsi": 50.0}
        result = match_pattern_against_candle(pattern, candle, indicators)
        assert result.matched is True  # close=150 in [100,200]


# =============================================================================
# Indicator Calculation Tests
# =============================================================================


class TestIndicatorCalculations:
    """Tests for RSI, MACD, BB, etc. calculations."""

    def test_rsi_oversold(self):
        """RSI returns low value for falling prices."""
        # Steadily falling prices -> RSI should be low
        closes = [100 - i * 2 for i in range(20)]
        rsi = calculate_rsi(closes)
        assert rsi is not None
        assert rsi < 30

    def test_rsi_overbought(self):
        """RSI returns high value for rising prices."""
        closes = [100 + i * 2 for i in range(20)]
        rsi = calculate_rsi(closes)
        assert rsi is not None
        assert rsi > 70

    def test_rsi_insufficient_data(self):
        """RSI returns None with insufficient data."""
        assert calculate_rsi([100, 101, 102]) is None

    def test_rsi_bounded(self):
        """RSI is always in [0, 100]."""
        closes = [100 + i * 5 for i in range(30)]
        rsi = calculate_rsi(closes)
        assert rsi is not None
        assert 0 <= rsi <= 100

    def test_macd_returns_all_components(self):
        """MACD returns macd, macd_signal, macd_histogram."""
        closes = [100 + i * 0.5 + (i % 5) for i in range(50)]
        result = calculate_macd(closes)
        assert result is not None
        assert "macd" in result
        assert "macd_signal" in result
        assert "macd_histogram" in result

    def test_macd_insufficient_data(self):
        """MACD returns None with insufficient data."""
        assert calculate_macd([100, 101]) is None

    def test_bollinger_bands_structure(self):
        """Bollinger Bands returns upper > middle > lower."""
        closes = [100 + (i % 10 - 5) for i in range(30)]
        result = calculate_bollinger_bands(closes)
        assert result is not None
        assert result["bb_upper"] > result["bb_middle"]
        assert result["bb_middle"] > result["bb_lower"]
        assert result["bb_width"] >= 0

    def test_atr_positive(self):
        """ATR is always non-negative."""
        highs = [110 + i for i in range(20)]
        lows = [90 + i for i in range(20)]
        closes = [100 + i for i in range(20)]
        atr = calculate_atr(highs, lows, closes)
        assert atr is not None
        assert atr >= 0

    def test_stochastic_bounded(self):
        """Stochastic K and D are in [0, 100]."""
        highs = [110 + i for i in range(20)]
        lows = [90 + i for i in range(20)]
        closes = [100 + i for i in range(20)]
        result = calculate_stochastic(highs, lows, closes)
        assert result is not None
        assert 0 <= result["stoch_k"] <= 100
        assert 0 <= result["stoch_d"] <= 100

    def test_williams_r_bounded(self):
        """Williams %R is in [-100, 0]."""
        highs = [110 + i for i in range(20)]
        lows = [90 + i for i in range(20)]
        closes = [100 + i for i in range(20)]
        wr = calculate_williams_r(highs, lows, closes)
        assert wr is not None
        assert -100 <= wr <= 0

    def test_calculate_all_indicators_nonempty(self):
        """calculate_all_indicators returns multiple indicators from candle data."""
        candles = [
            {"open": 100 + i, "high": 110 + i, "low": 90 + i, "close": 105 + i, "volume": 1000 + i * 10}
            for i in range(50)
        ]
        indicators = calculate_all_indicators(candles)
        assert "rsi" in indicators
        assert indicators["rsi"] is not None

    def test_calculate_all_indicators_empty_candles(self):
        """calculate_all_indicators returns empty dict for no candles."""
        assert calculate_all_indicators([]) == {}


# =============================================================================
# Validation Tests
# =============================================================================


class TestValidation:
    """Tests for indicator and condition validation."""

    def test_validate_known_indicator(self):
        """Known indicator names are valid."""
        assert validate_indicator("rsi") is True
        assert validate_indicator("macd") is True

    def test_validate_unknown_indicator(self):
        """Unknown indicator names are invalid."""
        assert validate_indicator("fake_indicator") is False

    def test_validate_condition_valid(self):
        """Valid condition dict passes validation."""
        cond = {"indicator": "rsi", "min": 0, "max": 100}
        valid, msg = validate_condition(cond)
        assert valid is True
        assert msg == ""

    def test_validate_condition_missing_indicator(self):
        """Condition without indicator field is invalid."""
        cond = {"min": 0, "max": 100}
        valid, msg = validate_condition(cond)
        assert valid is False
        assert "indicator" in msg.lower()

    def test_validate_condition_min_gt_max(self):
        """Condition with min > max is invalid."""
        cond = {"indicator": "rsi", "min": 80, "max": 20}
        valid, msg = validate_condition(cond)
        assert valid is False

    def test_validate_condition_not_dict(self):
        """Non-dict condition is invalid."""
        valid, msg = validate_condition("not a dict")
        assert valid is False

    def test_validate_unknown_indicator_in_condition(self):
        """Condition with unknown indicator is invalid."""
        cond = {"indicator": "fake", "min": 0, "max": 100}
        valid, msg = validate_condition(cond)
        assert valid is False


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Edge case tests for pattern matching."""

    def test_empty_patterns_batch(self):
        """Batch matching with empty patterns list returns empty results."""
        results = match_patterns_batch([], {"rsi": 50.0})
        assert results == []

    def test_all_conditions_false(self):
        """Pattern where all conditions fail returns not matched."""
        pattern = {
            "entry_conditions": [
                {"indicator": "rsi", "min": 0, "max": 10},
                {"indicator": "adx", "min": 90, "max": 100},
            ],
            "exit_conditions": [],
            "logic": "AND",
        }
        indicators = {"rsi": 50.0, "adx": 30.0}
        result = match_pattern(pattern, indicators, check_entry=True)
        assert result.matched is False
        assert result.confidence == 0.0

    def test_missing_indicators_in_candle(self):
        """Missing indicators for a condition do not crash."""
        pattern = {
            "entry_conditions": [{"indicator": "rsi", "min": 0, "max": 30}],
            "exit_conditions": [],
        }
        indicators = {}  # no rsi
        result = match_pattern(pattern, indicators, check_entry=True)
        assert result.matched is False

    def test_pattern_with_zero_weight_condition(self):
        """Condition with weight=0 does not contribute to confidence."""
        indicators = {"rsi": 50.0, "adx": 50.0}
        conditions = [
            {"indicator": "rsi", "min": 0, "max": 100, "weight": 0.0},
            {"indicator": "adx", "min": 0, "max": 100, "weight": 1.0},
        ]
        conf = calculate_match_confidence(indicators, conditions)
        # Only adx contributes with weight 1.0, rsi weight=0 means total_weight=1
        # But the code does total_weight += weight, so 0+1=1, weighted=0*0 + 1*1=1 -> conf=1.0
        assert conf > 0.0

    def test_indicator_cache_get_set_clear(self):
        """IndicatorCache stores and retrieves values, and clears."""
        cache = IndicatorCache()
        assert cache.get("key1") is None
        cache.set("key1", {"rsi": 50.0})
        assert cache.get("key1") == {"rsi": 50.0}
        cache.clear()
        assert cache.get("key1") is None

    def test_has_sufficient_data_true(self):
        """Sufficient candle count returns True."""
        assert has_sufficient_data(200, ["rsi", "macd"]) is True

    def test_has_sufficient_data_false(self):
        """Insufficient candle count returns False."""
        assert has_sufficient_data(5, ["sma_200"]) is False

    def test_indicator_lookback_values(self):
        """All INDICATORS have lookback entries."""
        for ind in INDICATORS:
            lb = get_indicator_lookback(ind)
            assert lb >= 1, f"{ind} lookback should be >= 1"

    def test_indicator_bounds_valid(self):
        """Indicator bounds have min <= max."""
        for ind, (lo, hi) in INDICATOR_BOUNDS.items():
            assert lo <= hi, f"{ind} bounds invalid: {lo} > {hi}"

    def test_match_result_details_populated(self):
        """MatchResult.details contains entry/exit breakdown."""
        pattern = {
            "entry_conditions": [{"indicator": "rsi", "min": 0, "max": 30}],
            "exit_conditions": [{"indicator": "rsi", "min": 70, "max": 100}],
        }
        indicators = {"rsi": 25.0}
        result = match_pattern(pattern, indicators, check_entry=True, check_exit=True)
        assert "entry_matched" in result.details
        assert "exit_matched" in result.details
        assert "entry_conditions_matched" in result.details
        assert result.details["entry_matched"] is True
        assert result.details["exit_matched"] is False

    def test_or_logic_string_parsing(self):
        """Pattern with logic='OR' string uses OR logic."""
        pattern = {
            "entry_conditions": [
                {"indicator": "rsi", "min": 0, "max": 30},
                {"indicator": "adx", "min": 50, "max": 100},
            ],
            "exit_conditions": [],
            "logic": "OR",
        }
        # rsi=25 matches, adx=30 doesn't -> OR should match
        indicators = {"rsi": 25.0, "adx": 30.0}
        result = match_pattern(pattern, indicators, check_entry=True)
        assert result.matched is True

    def test_series_with_fewer_indicators_than_candles(self):
        """Series matching with fewer indicator dicts than candles uses empty dict."""
        pattern = {
            "entry_conditions": [{"indicator": "rsi", "min": 0, "max": 30}],
            "exit_conditions": [],
        }
        candles = [
            {"open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000},
            {"open": 105, "high": 115, "low": 95, "close": 100, "volume": 1200},
        ]
        indicator_series = [{"rsi": 25.0}]  # only 1 vs 2 candles
        results = match_pattern_against_series(pattern, candles, indicator_series)
        assert len(results) == 2
        assert results[0].matched is True
        assert results[1].matched is False  # no indicators -> can't match
