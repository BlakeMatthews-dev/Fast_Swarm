"""
Real integration tests for pattern_matcher.py (backtest pattern matching).

Tests the canonical pattern matcher:
- evaluate_conditions: match entry/exit conditions against indicator values
- resolve_indicator: alias resolution (camelCase, snake_case, fuzzy period)
- compute_derived_indicator: on-the-fly computed indicators
- MatchResult confidence scoring

No DB needed — pure computation tests.
"""

import pytest

from Fast_Swarm.local_agents.backtest.pattern_matcher import (
    MatchResult,
    compute_derived_indicator,
    evaluate_conditions,
    get_indicator_bounds,
    resolve_indicator,
)


# =============================================================================
# resolve_indicator Tests
# =============================================================================


class TestResolveIndicator:
    """Test indicator name resolution across alias styles."""

    def test_direct_match(self):
        available = {"rsi_14", "sma_20", "close"}
        assert resolve_indicator("rsi_14", available) == "rsi_14"

    def test_alias_lookup(self):
        available = {"rsi_14", "close"}
        # "RSI" is an alias for "rsi_14" in INDICATOR_ALIASES
        result = resolve_indicator("RSI", available)
        assert result == "rsi_14"

    def test_case_insensitive(self):
        available = {"RSI_14", "close"}
        result = resolve_indicator("rsi_14", available)
        assert result == "RSI_14"

    def test_camelcase_to_snake_case(self):
        available = {"aroon_osc", "close"}
        result = resolve_indicator("aroonOsc", available)
        assert result is not None
        assert "aroon" in result.lower()

    def test_fuzzy_period_match(self):
        available = {"ema_21", "close"}
        # ema_20 should find ema_21 via fuzzy period matching
        result = resolve_indicator("ema_20", available)
        assert result == "ema_21"

    def test_returns_none_for_unknown(self):
        available = {"rsi_14", "close"}
        result = resolve_indicator("totally_unknown_indicator_xyz", available)
        assert result is None


# =============================================================================
# compute_derived_indicator Tests
# =============================================================================


class TestComputeDerivedIndicator:
    """Test on-the-fly computed indicators."""

    def test_rsi_oversold(self):
        indicators = {"rsi_14": 25.0, "close": 100.0}
        result = compute_derived_indicator("rsiOversold", indicators)
        assert result == 1  # RSI < 30

    def test_rsi_not_oversold(self):
        indicators = {"rsi_14": 55.0, "close": 100.0}
        result = compute_derived_indicator("rsiOversold", indicators)
        assert result == 0

    def test_rsi_overbought(self):
        indicators = {"rsi_14": 75.0, "close": 100.0}
        result = compute_derived_indicator("rsiOverbought", indicators)
        assert result == 1  # RSI > 70

    def test_golden_cross(self):
        indicators = {"sma_50": 105.0, "sma_200": 100.0, "close": 110.0}
        result = compute_derived_indicator("goldenCross", indicators)
        assert result == 1  # SMA50 > SMA200

    def test_death_cross(self):
        indicators = {"sma_50": 95.0, "sma_200": 100.0, "close": 90.0}
        result = compute_derived_indicator("deathCross", indicators)
        assert result == 1  # SMA50 < SMA200

    def test_macd_bullish_cross(self):
        indicators = {"macd_line": 0.5, "macd_signal": -0.2, "close": 100.0}
        result = compute_derived_indicator("macdBullishCross", indicators)
        assert result == 1

    def test_macd_bearish_cross(self):
        indicators = {"macd_line": -0.5, "macd_signal": 0.2, "close": 100.0}
        result = compute_derived_indicator("macdBearishCross", indicators)
        assert result == 1

    def test_price_above_ema(self):
        indicators = {"ema_21": 95.0, "close": 100.0}
        result = compute_derived_indicator("priceAboveEma", indicators)
        assert result == 1

    def test_volume_spike(self):
        indicators = {"volume": 5000.0, "volume_sma_20": 2000.0, "close": 100.0}
        result = compute_derived_indicator("volumeSpike", indicators)
        assert result == 1  # volume > 2 * volume_sma

    def test_volume_dry(self):
        indicators = {"volume": 800.0, "volume_sma_20": 2000.0, "close": 100.0}
        result = compute_derived_indicator("volumeDry", indicators)
        assert result == 1  # volume < 0.5 * volume_sma

    def test_strong_trend(self):
        indicators = {"adx_14": 30.0, "close": 100.0}
        result = compute_derived_indicator("strongTrend", indicators)
        assert result == 1

    def test_weak_trend(self):
        indicators = {"adx_14": 15.0, "close": 100.0}
        result = compute_derived_indicator("weakTrend", indicators)
        assert result == 1

    def test_unknown_indicator_returns_none(self):
        indicators = {"close": 100.0}
        result = compute_derived_indicator("totallyFakeIndicator", indicators)
        assert result is None


# =============================================================================
# evaluate_conditions Tests
# =============================================================================


class TestEvaluateConditions:
    """Test the main condition evaluation pipeline."""

    def test_single_condition_met(self):
        conditions = [
            {"indicator": "rsi_14", "operator": "<", "value": 30},
        ]
        indicators = {"rsi_14": 25.0}
        result = evaluate_conditions(conditions, indicators)
        assert result.matched is True
        assert result.conditions_met == 1
        assert result.conditions_total == 1
        assert result.confidence > 0

    def test_single_condition_not_met(self):
        conditions = [
            {"indicator": "rsi_14", "operator": "<", "value": 30},
        ]
        indicators = {"rsi_14": 55.0}
        result = evaluate_conditions(conditions, indicators)
        assert result.matched is False

    def test_multiple_conditions_all_met(self):
        conditions = [
            {"indicator": "rsi_14", "operator": "<", "value": 30},
            {"indicator": "adx_14", "operator": ">", "value": 25},
        ]
        indicators = {"rsi_14": 20.0, "adx_14": 35.0}
        result = evaluate_conditions(conditions, indicators)
        assert result.matched is True
        assert result.conditions_met == 2

    def test_multiple_conditions_partial_met(self):
        conditions = [
            {"indicator": "rsi_14", "operator": "<", "value": 30},
            {"indicator": "adx_14", "operator": ">", "value": 25},
        ]
        indicators = {"rsi_14": 20.0, "adx_14": 15.0}  # ADX not met
        result = evaluate_conditions(conditions, indicators)
        assert result.matched is False
        assert result.conditions_met == 1

    def test_missing_indicator_does_not_block_match(self):
        """Missing indicators are skipped (status='missing'), remaining checked."""
        conditions = [
            {"indicator": "rsi_14", "operator": "<", "value": 30},
            {"indicator": "nonexistent_indicator_xyz", "operator": ">", "value": 0},
        ]
        indicators = {"rsi_14": 20.0}
        result = evaluate_conditions(conditions, indicators)
        # Only 1 resolvable condition, and it's met
        assert result.matched is True
        assert result.conditions_met == 1

    def test_empty_conditions_not_matched(self):
        result = evaluate_conditions([], {"rsi_14": 50.0})
        assert result.matched is False
        assert result.conditions_total == 0

    def test_dict_format_conditions(self):
        conditions = {
            "rsi_14": {"operator": "<", "value": 30},
            "adx_14": {"operator": ">", "value": 25},
        }
        indicators = {"rsi_14": 20.0, "adx_14": 35.0}
        result = evaluate_conditions(conditions, indicators)
        assert result.matched is True
        assert result.conditions_met == 2

    def test_computed_indicator_condition(self):
        """Test that computed/derived indicators (rsiOversold) work in conditions."""
        conditions = [
            {"indicator": "rsiOversold", "operator": ">", "value": 0},
        ]
        indicators = {"rsi_14": 25.0, "close": 100.0}
        result = evaluate_conditions(conditions, indicators)
        # rsiOversold computes to 1 (since rsi < 30), and 1 > 0
        assert result.matched is True

    def test_alias_resolution_in_conditions(self):
        """Indicator aliases (RSI -> rsi_14) should resolve."""
        conditions = [
            {"indicator": "RSI", "operator": "<", "value": 30},
        ]
        indicators = {"rsi_14": 22.0}
        result = evaluate_conditions(conditions, indicators)
        assert result.matched is True

    def test_confidence_higher_further_from_threshold(self):
        """Confidence should be higher when value is further from the threshold."""
        conditions = [
            {"indicator": "rsi_14", "operator": "<", "value": 30},
        ]
        result_close = evaluate_conditions(conditions, {"rsi_14": 29.0})
        result_far = evaluate_conditions(conditions, {"rsi_14": 10.0})

        if result_close.matched and result_far.matched:
            assert result_far.confidence >= result_close.confidence, (
                "Confidence should be higher when further from threshold"
            )


# =============================================================================
# MatchResult Tests
# =============================================================================


class TestMatchResult:
    """Test MatchResult dataclass and aliases."""

    def test_passed_alias(self):
        mr = MatchResult(matched=True, confidence=0.8, conditions_met=2, conditions_total=2, condition_details=[])
        assert mr.passed is True

    def test_overall_confidence_alias(self):
        mr = MatchResult(matched=True, confidence=0.75, conditions_met=1, conditions_total=1, condition_details=[])
        assert mr.overall_confidence == 0.75


# =============================================================================
# get_indicator_bounds Tests
# =============================================================================


class TestGetIndicatorBounds:
    """Test indicator bounds lookup."""

    def test_known_indicator(self):
        low, high = get_indicator_bounds("rsi_14")
        assert low == 0
        assert high == 100

    def test_unknown_indicator_gets_default(self):
        low, high = get_indicator_bounds("totally_unknown_thing")
        assert low == -100
        assert high == 100

    def test_motion_derivative_bounds(self):
        low, high = get_indicator_bounds("close_velocity_zscore")
        assert low == -5
        assert high == 5
