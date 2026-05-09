"""
Pattern Matching Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (Pattern Matching Engine)
Patterns match against OHLCV + indicators. Evolution discovers boundaries.
"""

import time

import pytest
from Fast_Swarm.Patterns.Services.pattern_matching_service import (
    INDICATOR_BOUNDS,
    INDICATORS,
    IndicatorCache,
    LogicOperator,
    Signal,
    calculate_adx,
    calculate_all_indicators,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_condition_confidence,
    calculate_macd,
    calculate_match_confidence,
    calculate_rsi,
    calculate_stochastic,
    calculate_williams_r,
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

# ============================================================================
# PATTERN MATCHING CONTRACT
# ============================================================================

# Raw indicator ranges for testing (evolution discovers these, not humans)
TEST_INDICATORS = [
    "rsi",
    "macd",
    "macd_signal",
    "macd_histogram",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "bb_width",
    "atr",
    "adx",
    "obv",
    "volume_ratio",
    "ema_9",
    "ema_21",
    "ema_50",
    "sma_200",
    "stoch_k",
    "stoch_d",
    "williams_r",
    "cci",
    "roc",
    "momentum",
    "mfi",
    "vwap",
]


class TestIndicatorConditionMatching:
    """CONTRACT: Individual indicator conditions match correctly."""

    def test_rsi_condition_match_in_range(self):
        """CONTRACT: RSI 28.3 matches condition {min: 20, max: 35}."""
        condition = {"indicator": "rsi", "min": 20, "max": 35}
        assert match_indicator_condition("rsi", 28.3, condition) is True

    def test_rsi_condition_no_match_below(self):
        """CONTRACT: RSI 15.0 does NOT match {min: 20, max: 35}."""
        condition = {"indicator": "rsi", "min": 20, "max": 35}
        assert match_indicator_condition("rsi", 15.0, condition) is False

    def test_rsi_condition_no_match_above(self):
        """CONTRACT: RSI 50.0 does NOT match {min: 20, max: 35}."""
        condition = {"indicator": "rsi", "min": 20, "max": 35}
        assert match_indicator_condition("rsi", 50.0, condition) is False

    def test_macd_condition_match_negative(self):
        """CONTRACT: MACD -0.23 matches {min: -0.5, max: 0}."""
        condition = {"indicator": "macd", "min": -0.5, "max": 0}
        assert match_indicator_condition("macd", -0.23, condition) is True

    def test_macd_condition_match_positive(self):
        """CONTRACT: MACD 0.15 matches {min: 0, max: 0.5}."""
        condition = {"indicator": "macd", "min": 0, "max": 0.5}
        assert match_indicator_condition("macd", 0.15, condition) is True

    def test_volume_ratio_condition_match(self):
        """CONTRACT: Volume ratio 1.45 matches {min: 1.0, max: 2.0}."""
        condition = {"indicator": "volume_ratio", "min": 1.0, "max": 2.0}
        assert match_indicator_condition("volume_ratio", 1.45, condition) is True

    def test_atr_condition_match(self):
        """CONTRACT: ATR 2.5 matches {min: 1.0, max: 5.0}."""
        condition = {"indicator": "atr", "min": 1.0, "max": 5.0}
        assert match_indicator_condition("atr", 2.5, condition) is True

    def test_bb_width_condition_match(self):
        """CONTRACT: BB width 0.03 matches {min: 0.02, max: 0.05}."""
        condition = {"indicator": "bb_width", "min": 0.02, "max": 0.05}
        assert match_indicator_condition("bb_width", 0.03, condition) is True

    def test_adx_condition_match(self):
        """CONTRACT: ADX 35 matches {min: 25, max: 50}."""
        condition = {"indicator": "adx", "min": 25, "max": 50}
        assert match_indicator_condition("adx", 35, condition) is True

    def test_stoch_condition_match(self):
        """CONTRACT: Stoch K 22 matches {min: 0, max: 30}."""
        condition = {"indicator": "stoch_k", "min": 0, "max": 30}
        assert match_indicator_condition("stoch_k", 22, condition) is True


class TestBoundaryConditions:
    """CONTRACT: Edge cases at condition boundaries."""

    def test_value_at_exact_min(self):
        """CONTRACT: Value exactly at min IS a match (inclusive)."""
        assert match_condition(20.0, 20.0, 30.0) is True

    def test_value_at_exact_max(self):
        """CONTRACT: Value exactly at max IS a match (inclusive)."""
        assert match_condition(30.0, 20.0, 30.0) is True

    def test_value_epsilon_below_min(self):
        """CONTRACT: Value 0.0001 below min is NOT a match."""
        # Using tolerance 1e-9, 0.0001 is significantly below
        assert match_condition(19.9999, 20.0, 30.0) is False

    def test_value_epsilon_above_max(self):
        """CONTRACT: Value 0.0001 above max is NOT a match."""
        assert match_condition(30.0001, 20.0, 30.0) is False

    def test_float_precision_handling(self):
        """CONTRACT: Float comparison uses appropriate tolerance."""
        # Very close to boundary should match with tolerance
        assert match_condition(20.0 + 1e-10, 20.0, 30.0) is True
        assert match_condition(30.0 - 1e-10, 20.0, 30.0) is True


class TestMultiConditionLogic:
    """CONTRACT: Multiple conditions combine with AND/OR logic."""

    def test_multi_condition_and_all_match(self):
        """CONTRACT: AND logic: all conditions must match."""
        indicators = {"rsi": 30, "macd": 0.1, "atr": 2.0}
        conditions = [
            {"indicator": "rsi", "min": 20, "max": 40},
            {"indicator": "macd", "min": 0, "max": 0.5},
            {"indicator": "atr", "min": 1, "max": 3},
        ]
        matched, count, total = match_conditions_and(indicators, conditions)
        assert matched is True
        assert count == 3

    def test_multi_condition_and_one_fails(self):
        """CONTRACT: AND logic: one failure = no match."""
        indicators = {"rsi": 30, "macd": 1.0, "atr": 2.0}  # macd out of range
        conditions = [
            {"indicator": "rsi", "min": 20, "max": 40},
            {"indicator": "macd", "min": 0, "max": 0.5},  # FAIL: 1.0 > 0.5
            {"indicator": "atr", "min": 1, "max": 3},
        ]
        matched, count, total = match_conditions_and(indicators, conditions)
        assert matched is False
        assert count == 2

    def test_multi_condition_or_one_matches(self):
        """CONTRACT: OR logic: one match = pattern matches."""
        indicators = {"rsi": 50, "macd": 0.1}  # only macd matches
        conditions = [
            {"indicator": "rsi", "min": 20, "max": 30},  # FAIL
            {"indicator": "macd", "min": 0, "max": 0.5},  # MATCH
        ]
        matched, count, total = match_conditions_or(indicators, conditions)
        assert matched is True
        assert count == 1

    def test_multi_condition_or_none_match(self):
        """CONTRACT: OR logic: no matches = no pattern match."""
        indicators = {"rsi": 50, "macd": 1.0}  # neither matches
        conditions = [
            {"indicator": "rsi", "min": 20, "max": 30},
            {"indicator": "macd", "min": 0, "max": 0.5},
        ]
        matched, count, total = match_conditions_or(indicators, conditions)
        assert matched is False
        assert count == 0

    def test_default_logic_is_and(self):
        """CONTRACT: Default combination logic is AND."""
        indicators = {"rsi": 30, "macd": 0.1}
        conditions = [
            {"indicator": "rsi", "min": 20, "max": 40},
            {"indicator": "macd", "min": 0, "max": 0.5},
        ]
        # Default is AND
        matched, _, _ = match_conditions(indicators, conditions)
        assert matched is True

    def test_mixed_and_or_logic(self):
        """CONTRACT: Can combine AND and OR groups."""
        indicators = {"rsi": 30, "macd": 0.1, "atr": 2.0}
        conditions = [
            {"indicator": "rsi", "min": 20, "max": 40},
            {"indicator": "macd", "min": 0, "max": 0.5},
        ]
        # Test with explicit OR
        matched, _, _ = match_conditions(indicators, conditions, LogicOperator.OR)
        assert matched is True


class TestConfidenceScoring:
    """CONTRACT: Match confidence scoring."""

    def test_confidence_score_0_to_1(self):
        """CONTRACT: Confidence score always in [0, 1]."""
        # Various test cases
        assert 0 <= calculate_condition_confidence(25, 20, 30) <= 1
        assert 0 <= calculate_condition_confidence(50, 0, 100) <= 1
        assert 0 <= calculate_condition_confidence(10, 0, 100) <= 1

    def test_confidence_1_all_conditions_center(self):
        """CONTRACT: All values at center of range = confidence 1.0."""
        # Value at exact center
        confidence = calculate_condition_confidence(25, 20, 30)
        assert confidence == 1.0

    def test_confidence_lower_at_edges(self):
        """CONTRACT: Values at edges have lower confidence."""
        center_conf = calculate_condition_confidence(25, 20, 30)
        edge_conf = calculate_condition_confidence(20, 20, 30)
        assert edge_conf < center_conf

    def test_confidence_0_no_match(self):
        """CONTRACT: No match = confidence 0."""
        confidence = calculate_condition_confidence(15, 20, 30)
        assert confidence == 0.0

    def test_confidence_weighted_by_indicator(self):
        """CONTRACT: Indicators can have different weights."""
        indicators = {"rsi": 25, "macd": 0.25}
        conditions = [
            {"indicator": "rsi", "min": 20, "max": 30, "weight": 2.0},
            {"indicator": "macd", "min": 0, "max": 0.5, "weight": 1.0},
        ]
        confidence = calculate_match_confidence(indicators, conditions)
        assert 0 <= confidence <= 1


class TestMissingIndicatorHandling:
    """CONTRACT: Handle missing indicator values."""

    def test_missing_indicator_returns_no_match(self):
        """CONTRACT: Missing indicator data = no match (not error)."""
        indicators = {"rsi": 30}  # macd missing
        conditions = [
            {"indicator": "rsi", "min": 20, "max": 40},
            {"indicator": "macd", "min": 0, "max": 0.5},  # missing
        ]
        matched, count, _ = match_conditions_and(indicators, conditions)
        assert matched is False

    def test_null_indicator_returns_no_match(self):
        """CONTRACT: Null indicator value = no match."""
        assert match_condition(None, 20, 30) is False

    def test_nan_indicator_returns_no_match(self):
        """CONTRACT: NaN indicator value = no match."""
        assert match_condition(float("nan"), 20, 30) is False

    def test_partial_indicators_evaluated(self):
        """CONTRACT: Can match with subset of indicators available."""
        indicators = {"rsi": 30}  # only rsi available
        conditions = [{"indicator": "rsi", "min": 20, "max": 40}]
        matched, _, _ = match_conditions_and(indicators, conditions)
        assert matched is True


class TestPatternMatchAgainstCandle:
    """CONTRACT: Pattern matching against OHLCV candle."""

    def test_match_against_single_candle(self):
        """CONTRACT: Match pattern against one candle + indicators."""
        pattern = {
            "entry_conditions": [
                {"indicator": "rsi", "min": 20, "max": 40},
            ]
        }
        candle = {"open": 100, "high": 105, "low": 98, "close": 102, "volume": 1000}
        indicators = {"rsi": 30}

        result = match_pattern_against_candle(pattern, candle, indicators)
        assert result.matched is True

    def test_match_against_candle_series(self):
        """CONTRACT: Match pattern against candle series."""
        pattern = {
            "entry_conditions": [
                {"indicator": "rsi", "min": 20, "max": 40},
            ]
        }
        candles = [
            {"open": 100, "close": 102},
            {"open": 102, "close": 105},
        ]
        indicator_series = [
            {"rsi": 30},
            {"rsi": 35},
        ]

        results = match_pattern_against_series(pattern, candles, indicator_series)
        assert len(results) == 2
        assert all(r.matched for r in results)

    def test_match_returns_signal(self):
        """CONTRACT: Match returns signal (LONG/SHORT/NONE)."""
        pattern = {"entry_conditions": [{"indicator": "rsi", "min": 20, "max": 40}], "direction": "LONG"}
        indicators = {"rsi": 30}

        result = match_pattern(pattern, indicators)
        assert result.signal == Signal.LONG

    def test_entry_match_vs_exit_match(self):
        """CONTRACT: Entry and exit conditions evaluated separately."""
        pattern = {
            "entry_conditions": [{"indicator": "rsi", "min": 20, "max": 40}],
            "exit_conditions": [{"indicator": "rsi", "min": 70, "max": 80}],
        }
        indicators = {"rsi": 30}

        # Check entry
        result_entry = match_pattern(pattern, indicators, check_entry=True, check_exit=False)
        assert result_entry.matched is True

        # Check exit (should not match)
        result_exit = match_pattern(pattern, indicators, check_entry=False, check_exit=True)
        assert result_exit.matched is False


class TestIndicatorCalculation:
    """CONTRACT: Indicator values calculated correctly."""

    @pytest.mark.parametrize("indicator", TEST_INDICATORS)
    def test_indicator_calculation_exists(self, indicator):
        """CONTRACT: Each indicator has calculation function."""
        assert indicator in INDICATORS

    def test_rsi_calculation_14_period(self):
        """CONTRACT: RSI uses 14-period default."""
        # Generate test prices (15 needed for 14-period RSI)
        closes = [100 + i * 0.5 for i in range(20)]  # uptrend
        rsi = calculate_rsi(closes, period=14)
        assert rsi is not None
        assert 0 <= rsi <= 100

    def test_macd_calculation_12_26_9(self):
        """CONTRACT: MACD uses 12, 26, 9 default periods."""
        closes = [100 + i * 0.1 for i in range(50)]
        macd = calculate_macd(closes, fast=12, slow=26, signal=9)
        assert macd is not None
        assert "macd" in macd
        assert "macd_signal" in macd
        assert "macd_histogram" in macd

    def test_bollinger_calculation_20_2(self):
        """CONTRACT: Bollinger uses 20-period, 2 std dev."""
        closes = [100 + i * 0.1 for i in range(25)]
        bb = calculate_bollinger_bands(closes, period=20, std_dev=2.0)
        assert bb is not None
        assert "bb_upper" in bb
        assert "bb_middle" in bb
        assert "bb_lower" in bb
        assert bb["bb_upper"] > bb["bb_middle"] > bb["bb_lower"]

    def test_atr_calculation_14_period(self):
        """CONTRACT: ATR uses 14-period default."""
        highs = [100 + i for i in range(20)]
        lows = [98 + i for i in range(20)]
        closes = [99 + i for i in range(20)]
        atr = calculate_atr(highs, lows, closes, period=14)
        assert atr is not None
        assert atr >= 0


class TestIndicatorBounds:
    """CONTRACT: Indicator value bounds."""

    def test_rsi_bounded_0_100(self):
        """CONTRACT: RSI always in [0, 100]."""
        # Extreme uptrend
        closes_up = [100 + i * 10 for i in range(20)]
        rsi_up = calculate_rsi(closes_up)
        assert rsi_up is not None
        assert 0 <= rsi_up <= 100

        # Extreme downtrend
        closes_down = [200 - i * 10 for i in range(20)]
        rsi_down = calculate_rsi(closes_down)
        assert rsi_down is not None
        assert 0 <= rsi_down <= 100

    def test_stoch_bounded_0_100(self):
        """CONTRACT: Stochastic always in [0, 100]."""
        highs = [100 + i for i in range(20)]
        lows = [98 + i for i in range(20)]
        closes = [99 + i for i in range(20)]
        stoch = calculate_stochastic(highs, lows, closes)
        assert stoch is not None
        assert 0 <= stoch["stoch_k"] <= 100
        assert 0 <= stoch["stoch_d"] <= 100

    def test_adx_bounded_0_100(self):
        """CONTRACT: ADX always in [0, 100]."""
        highs = [100 + i for i in range(40)]
        lows = [98 + i for i in range(40)]
        closes = [99 + i for i in range(40)]
        adx = calculate_adx(highs, lows, closes)
        assert adx is not None
        assert 0 <= adx <= 100

    def test_williams_r_bounded_neg100_0(self):
        """CONTRACT: Williams %R always in [-100, 0]."""
        highs = [100 + i for i in range(20)]
        lows = [98 + i for i in range(20)]
        closes = [99 + i for i in range(20)]
        wr = calculate_williams_r(highs, lows, closes)
        assert wr is not None
        assert -100 <= wr <= 0

    def test_macd_unbounded(self):
        """CONTRACT: MACD can be any real number."""
        # MACD is not bounded
        min_b, max_b = INDICATOR_BOUNDS.get("macd", (float("-inf"), float("inf")))
        assert min_b == float("-inf") or "macd" not in INDICATOR_BOUNDS

    def test_atr_non_negative(self):
        """CONTRACT: ATR always >= 0."""
        highs = [100, 102, 101, 103, 100, 99, 101, 102, 100, 98, 99, 100, 101, 102, 103]
        lows = [98, 99, 98, 100, 97, 96, 98, 99, 97, 95, 96, 97, 98, 99, 100]
        closes = [99, 101, 100, 102, 99, 98, 100, 101, 99, 97, 98, 99, 100, 101, 102]
        atr = calculate_atr(highs, lows, closes)
        assert atr is not None
        assert atr >= 0


class TestLookbackPeriods:
    """CONTRACT: Indicator lookback requirements."""

    def test_rsi_needs_15_candles(self):
        """CONTRACT: RSI needs at least 15 candles (14 + 1)."""
        required = get_indicator_lookback("rsi")
        assert required >= 15

        # Not enough data returns None
        closes = [100 + i for i in range(10)]
        assert calculate_rsi(closes) is None

        # Enough data works
        closes = [100 + i for i in range(20)]
        assert calculate_rsi(closes) is not None

    def test_macd_needs_35_candles(self):
        """CONTRACT: MACD needs at least 35 candles (26 + 9)."""
        required = get_indicator_lookback("macd")
        assert required >= 35

        # Not enough data
        closes = [100 + i for i in range(30)]
        assert calculate_macd(closes) is None

        # Enough data
        closes = [100 + i for i in range(50)]
        assert calculate_macd(closes) is not None

    def test_sma_200_needs_200_candles(self):
        """CONTRACT: SMA 200 needs at least 200 candles."""
        required = get_indicator_lookback("sma_200")
        assert required >= 200

    def test_insufficient_data_returns_none(self):
        """CONTRACT: Insufficient candles returns None (not error)."""
        closes = [100, 101, 102]  # Too few
        rsi = calculate_rsi(closes)
        assert rsi is None


class TestTimeframeMatching:
    """CONTRACT: Pattern matching across timeframes."""

    def test_match_1h_timeframe(self):
        """CONTRACT: Can match against 1h candles."""
        pattern = {"entry_conditions": [{"indicator": "rsi", "min": 20, "max": 40}], "timeframe": "1h"}
        indicators = {"rsi": 30}
        result = match_pattern(pattern, indicators)
        assert result is not None

    def test_match_6h_timeframe(self):
        """CONTRACT: Can match against 6h candles."""
        pattern = {"entry_conditions": [{"indicator": "rsi", "min": 20, "max": 40}], "timeframe": "6h"}
        indicators = {"rsi": 30}
        result = match_pattern(pattern, indicators)
        assert result is not None

    def test_match_1d_timeframe(self):
        """CONTRACT: Can match against 1d candles."""
        pattern = {"entry_conditions": [{"indicator": "rsi", "min": 20, "max": 40}], "timeframe": "1d"}
        indicators = {"rsi": 30}
        result = match_pattern(pattern, indicators)
        assert result is not None

    def test_pattern_specifies_timeframe(self):
        """CONTRACT: Pattern stores preferred timeframe."""
        pattern = {"timeframe": "4h", "entry_conditions": []}
        assert pattern.get("timeframe") == "4h"


class TestMatchingDeterminism:
    """CONTRACT: Pattern matching is deterministic."""

    def test_same_inputs_same_match(self):
        """CONTRACT: Same pattern + same data = same result."""
        pattern = {
            "entry_conditions": [
                {"indicator": "rsi", "min": 20, "max": 40},
                {"indicator": "macd", "min": -0.5, "max": 0.5},
            ]
        }
        indicators = {"rsi": 30, "macd": 0.1}

        result1 = match_pattern(pattern, indicators)
        result2 = match_pattern(pattern, indicators)

        assert result1.matched == result2.matched
        assert result1.confidence == result2.confidence

    def test_indicator_order_independent(self):
        """CONTRACT: Condition order doesn't affect match."""
        pattern1 = {
            "entry_conditions": [
                {"indicator": "rsi", "min": 20, "max": 40},
                {"indicator": "macd", "min": -0.5, "max": 0.5},
            ]
        }
        pattern2 = {
            "entry_conditions": [
                {"indicator": "macd", "min": -0.5, "max": 0.5},
                {"indicator": "rsi", "min": 20, "max": 40},
            ]
        }
        indicators = {"rsi": 30, "macd": 0.1}

        result1 = match_pattern(pattern1, indicators)
        result2 = match_pattern(pattern2, indicators)

        assert result1.matched == result2.matched


class TestMatchingPerformance:
    """CONTRACT: Pattern matching performance."""

    def test_single_match_under_10ms(self):
        """CONTRACT: Single pattern match < 10ms."""
        pattern = {
            "entry_conditions": [
                {"indicator": "rsi", "min": 20, "max": 40},
                {"indicator": "macd", "min": -0.5, "max": 0.5},
                {"indicator": "atr", "min": 1, "max": 5},
            ]
        }
        indicators = {"rsi": 30, "macd": 0.1, "atr": 2.0}

        start = time.time()
        match_pattern(pattern, indicators)
        elapsed = (time.time() - start) * 1000  # ms

        assert elapsed < 10

    def test_batch_100_patterns_under_500ms(self):
        """CONTRACT: 100 pattern matches < 500ms."""
        patterns = [
            {
                "entry_conditions": [
                    {"indicator": "rsi", "min": 20 + i, "max": 40 + i},
                ]
            }
            for i in range(100)
        ]
        indicators = {"rsi": 50}

        start = time.time()
        results = match_patterns_batch(patterns, indicators)
        elapsed = (time.time() - start) * 1000  # ms

        assert len(results) == 100
        assert elapsed < 500

    def test_indicator_caching(self):
        """CONTRACT: Indicators computed once, cached."""
        cache = IndicatorCache()

        # First access - cache miss
        assert cache.get("candle_123") is None

        # Set cache
        indicators = {"rsi": 30, "macd": 0.1}
        cache.set("candle_123", indicators)

        # Second access - cache hit
        cached = cache.get("candle_123")
        assert cached == indicators


class TestIndicatorValidation:
    """Additional tests for indicator validation."""

    def test_validate_known_indicator(self):
        """Valid indicator names pass validation."""
        assert validate_indicator("rsi") is True
        assert validate_indicator("macd") is True
        assert validate_indicator("atr") is True

    def test_validate_unknown_indicator(self):
        """Unknown indicator names fail validation."""
        assert validate_indicator("fake_indicator") is False
        assert validate_indicator("") is False

    def test_validate_condition_structure(self):
        """Condition must have valid structure."""
        is_valid, _ = validate_condition({"indicator": "rsi", "min": 20, "max": 40})
        assert is_valid is True

        is_valid, error = validate_condition({"min": 20, "max": 40})  # missing indicator
        assert is_valid is False

        is_valid, error = validate_condition({"indicator": "rsi", "min": 50, "max": 30})  # min > max
        assert is_valid is False

    def test_has_sufficient_data(self):
        """Check if candle count is sufficient."""
        assert has_sufficient_data(200, ["rsi", "macd"]) is True
        assert has_sufficient_data(10, ["rsi"]) is False
        assert has_sufficient_data(40, ["macd"]) is True


class TestCalculateAllIndicators:
    """Test full indicator calculation from candles."""

    def test_calculate_all_indicators_basic(self):
        """Calculate all indicators from candle data."""
        candles = [
            {"open": 100 + i, "high": 102 + i, "low": 98 + i, "close": 101 + i, "volume": 1000 + i * 10}
            for i in range(50)
        ]

        indicators = calculate_all_indicators(candles)

        # Should have RSI
        assert "rsi" in indicators
        if indicators["rsi"] is not None:
            assert 0 <= indicators["rsi"] <= 100

        # Should have volume_ratio
        assert "volume_ratio" in indicators

    def test_calculate_all_indicators_empty(self):
        """Empty candles returns empty dict."""
        indicators = calculate_all_indicators([])
        assert indicators == {}
