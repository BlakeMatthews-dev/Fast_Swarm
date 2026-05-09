"""
Confidence Calculator Tests - V3 Math Parity.

Tests the log-scaled confidence scoring system.
Core formulas:
- Log scaling (inside): log1p(linear * 999) / log(1000)
- Decay (outside): 0.1 * pow(0.001, decay_ratio)
- Final: 0.1 + log_scaled * 0.9 for inside, decay for outside
"""


class TestLogScaling:
    """Core logarithmic scaling function."""

    # === HAPPY PATH ===

    def test_log_scaling_at_zero_returns_zero(self):
        """linear_position=0 -> 0.0 (at threshold edge)."""
        from Fast_Swarm.local_agents.shared.confidence import calculate_log_scaled_confidence

        result = calculate_log_scaled_confidence(0.0)
        assert result == 0.0

    def test_log_scaling_at_one_returns_one(self):
        """linear_position=1 -> 1.0 (at optimal)."""
        from Fast_Swarm.local_agents.shared.confidence import calculate_log_scaled_confidence

        result = calculate_log_scaled_confidence(1.0)
        assert result == 1.0

    def test_log_scaling_halfway_gives_high_confidence(self):
        """linear_position=0.5 -> ~0.9 (steep curve)."""
        from Fast_Swarm.local_agents.shared.confidence import calculate_log_scaled_confidence

        result = calculate_log_scaled_confidence(0.5)
        # V3: log1p(0.5 * 999) / log(1000) ≈ 0.8996
        assert 0.89 < result < 0.91, f"Expected ~0.90, got {result}"

    def test_log_scaling_quarter_still_decent(self):
        """linear_position=0.25 -> ~0.8."""
        from Fast_Swarm.local_agents.shared.confidence import calculate_log_scaled_confidence

        result = calculate_log_scaled_confidence(0.25)
        # V3: log1p(0.25 * 999) / log(1000) ≈ 0.7993
        assert 0.79 < result < 0.82, f"Expected ~0.80, got {result}"

    def test_log_scaling_is_monotonic(self):
        """Higher linear position = higher confidence."""
        from Fast_Swarm.local_agents.shared.confidence import calculate_log_scaled_confidence

        prev = 0.0
        for i in range(1, 101):
            linear = i / 100.0
            result = calculate_log_scaled_confidence(linear)
            assert result >= prev, f"Not monotonic at {linear}: {result} < {prev}"
            prev = result

    # === COMMON FAILURES ===

    def test_log_scaling_negative_clamps_to_zero(self):
        """Negative input should return 0, not error."""
        from Fast_Swarm.local_agents.shared.confidence import calculate_log_scaled_confidence

        result = calculate_log_scaled_confidence(-0.5)
        assert result == 0.0

    def test_log_scaling_above_one_clamps_to_one(self):
        """Input > 1 should return 1, not error."""
        from Fast_Swarm.local_agents.shared.confidence import calculate_log_scaled_confidence

        result = calculate_log_scaled_confidence(1.5)
        assert result == 1.0

    # === EDGE CASES ===

    def test_log_scaling_tiny_positive(self):
        """Very small positive -> small but non-zero."""
        from Fast_Swarm.local_agents.shared.confidence import calculate_log_scaled_confidence

        result = calculate_log_scaled_confidence(0.001)
        # V3: log1p(0.001 * 999) / log(1000) ≈ 0.333
        assert 0.0 < result < 0.4, f"Expected small value, got {result}"

    def test_log_scaling_nan_returns_zero(self):
        """NaN input -> 0.0 (safe default)."""
        from Fast_Swarm.local_agents.shared.confidence import calculate_log_scaled_confidence

        result = calculate_log_scaled_confidence(float("nan"))
        assert result == 0.0

    def test_log_scaling_inf_clamps(self):
        """Infinity -> clamp to 1.0."""
        from Fast_Swarm.local_agents.shared.confidence import calculate_log_scaled_confidence

        result = calculate_log_scaled_confidence(float("inf"))
        assert result == 1.0

    def test_log_scaling_negative_inf_clamps(self):
        """Negative infinity -> clamp to 0.0."""
        from Fast_Swarm.local_agents.shared.confidence import calculate_log_scaled_confidence

        result = calculate_log_scaled_confidence(float("-inf"))
        assert result == 0.0


class TestLessThanOperator:
    """Tests for < and <= operators."""

    # === HAPPY PATH ===

    def test_less_than_deep_inside_high_confidence(self):
        """RSI < 30, value=5 -> very high confidence (~0.95+)."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("<", 5, 30, 0, 100)
        assert conf is not None
        assert conf > 0.9, f"Expected high confidence, got {conf}"

    def test_less_than_at_threshold_edge_low_confidence(self):
        """RSI < 30, value=29 -> inside but close to threshold.

        V3 formula: linear_position = 1 - (value - min) / (threshold - min)
        = 1 - (29 - 0) / (30 - 0) = 1 - 29/30 = 0.0333
        log_scaled = log1p(0.0333 * 999) / log(1000) ≈ 0.51
        result = 0.1 + 0.51 * 0.9 ≈ 0.56
        """
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("<", 29, 30, 0, 100)
        assert conf is not None
        # V3 log scaling makes even edge positions have decent confidence
        assert 0.50 < conf < 0.70, f"Expected ~0.55-0.60, got {conf}"

    def test_less_than_outside_decays_to_near_zero(self):
        """RSI < 30, value=70 -> near zero (decay)."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("<", 70, 30, 0, 100)
        # Far outside, should decay to near zero or None
        assert conf is None or conf < 0.01, f"Expected near zero or None, got {conf}"

    def test_less_than_or_equal_at_threshold(self):
        """RSI <= 30, value=30 -> should pass (low conf, at edge)."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("<=", 30, 30, 0, 100)
        assert conf is not None
        # At exact threshold with <=, it's inside but at edge
        assert conf >= 0.1, f"Expected at least base confidence, got {conf}"

    # === COMMON FAILURES ===

    def test_less_than_exactly_at_threshold_fails(self):
        """RSI < 30, value=30 -> outside (decay starts at 0.1).

        V3 formula for outside: decay_ratio = (value - threshold) / (max - threshold)
        = (30 - 30) / (100 - 30) = 0
        result = 0.1 * 0.001^0 = 0.1 * 1 = 0.1
        """
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("<", 30, 30, 0, 100)
        # With strict <, value=30 is outside but at decay start point
        assert conf is not None
        assert conf == 0.1, f"Expected decay start (0.1), got {conf}"

    def test_less_than_nan_value_returns_zero(self):
        """NaN value -> 0.0 (safe fallback, not None)."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("<", float("nan"), 30, 0, 100)
        # V3 returns 0.0 for NaN values as a safe default
        assert conf == 0.0

    def test_less_than_nan_threshold_still_works(self):
        """NaN threshold -> still evaluates (goes to decay)."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("<", 20, float("nan"), 0, 100)
        # With NaN threshold, condition check may fail unpredictably
        # V3 handles this by going to decay path, returning small value
        assert conf is not None  # Returns some value, doesn't crash

    # === EDGE CASES ===

    def test_less_than_value_at_indicator_min(self):
        """Value at absolute minimum -> max confidence."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("<", 0, 30, 0, 100)
        assert conf is not None
        assert conf == 1.0, f"Expected 1.0 at min, got {conf}"

    def test_less_than_threshold_at_min(self):
        """Threshold = min -> edge case (zero range).

        With < operator: value=0 < threshold=0 is FALSE
        So this goes to decay zone: distance_outside = 0, result = 0.1
        """
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("<", 0, 0, 0, 100)
        # value=0 is NOT < threshold=0, so it's in decay zone
        assert conf is not None
        assert conf == 0.1  # Decay start point

    def test_less_than_value_beyond_max(self):
        """Value beyond indicator max -> deep in decay."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("<", 150, 30, 0, 100)
        # Value is beyond max, should be None or very small
        assert conf is None or conf < 0.001


class TestGreaterThanOperator:
    """Tests for > and >= operators."""

    # === HAPPY PATH ===

    def test_greater_than_deep_inside_high_confidence(self):
        """RSI > 70, value=95 -> very high confidence."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence(">", 95, 70, 0, 100)
        assert conf is not None
        assert conf > 0.9, f"Expected high confidence, got {conf}"

    def test_greater_than_at_edge_low_confidence(self):
        """RSI > 70, value=71 -> inside but close to threshold.

        V3 formula: linear_position = (value - threshold) / (max - threshold)
        = (71 - 70) / (100 - 70) = 1/30 = 0.0333
        log_scaled = log1p(0.0333 * 999) / log(1000) ≈ 0.51
        result = 0.1 + 0.51 * 0.9 ≈ 0.56
        """
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence(">", 71, 70, 0, 100)
        assert conf is not None
        # V3 log scaling gives decent confidence even at edge
        assert 0.50 < conf < 0.70, f"Expected ~0.55-0.60, got {conf}"

    def test_greater_than_outside_decays(self):
        """RSI > 70, value=30 -> near zero."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence(">", 30, 70, 0, 100)
        assert conf is None or conf < 0.01, f"Expected near zero or None, got {conf}"

    def test_greater_than_or_equal_at_threshold(self):
        """RSI >= 70, value=70 -> should pass (at edge)."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence(">=", 70, 70, 0, 100)
        assert conf is not None
        assert conf >= 0.1, f"Expected at least base confidence, got {conf}"

    # === EDGE CASES ===

    def test_greater_than_at_indicator_max(self):
        """Value at absolute maximum -> max confidence."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence(">", 100, 70, 0, 100)
        assert conf is not None
        assert conf == 1.0, f"Expected 1.0 at max, got {conf}"

    def test_greater_than_exactly_at_threshold_fails(self):
        """RSI > 70, value=70 -> outside (decay starts at 0.1).

        V3 formula for outside: decay_ratio = (threshold - value) / (threshold - min)
        = (70 - 70) / (70 - 0) = 0
        result = 0.1 * 0.001^0 = 0.1 * 1 = 0.1
        """
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence(">", 70, 70, 0, 100)
        assert conf is not None
        assert conf == 0.1, f"Expected decay start (0.1), got {conf}"


class TestBetweenOperator:
    """Tests for 'between' operator (center-based log scaling)."""

    # === HAPPY PATH ===

    def test_between_at_center_max_confidence(self):
        """RSI between 30-70, value=50 -> ~1.0 (center)."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("between", 50, (30, 70), 0, 100)
        assert conf is not None
        assert conf > 0.95, f"Expected near 1.0 at center, got {conf}"

    def test_between_at_edge_low_confidence(self):
        """RSI between 30-70, value=30 -> ~0.1 (edge)."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("between", 30, (30, 70), 0, 100)
        assert conf is not None
        assert 0.09 < conf < 0.20, f"Expected ~0.1-0.15 at edge, got {conf}"

    def test_between_at_other_edge(self):
        """RSI between 30-70, value=70 -> ~0.1 (other edge)."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("between", 70, (30, 70), 0, 100)
        assert conf is not None
        assert 0.09 < conf < 0.20, f"Expected ~0.1-0.15 at edge, got {conf}"

    def test_between_outside_decays(self):
        """RSI between 30-70, value=10 -> decay."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("between", 10, (30, 70), 0, 100)
        assert conf is None or conf < 0.1, f"Expected decay, got {conf}"

    def test_between_outside_high_decays(self):
        """RSI between 30-70, value=90 -> decay."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("between", 90, (30, 70), 0, 100)
        assert conf is None or conf < 0.1, f"Expected decay, got {conf}"

    # === COMMON FAILURES ===

    def test_between_inverted_bounds_handled(self):
        """Bounds given as (70, 30) instead of (30, 70) -> should normalize."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("between", 50, (70, 30), 0, 100)
        assert conf is not None
        assert conf > 0.9, f"Should handle inverted bounds, got {conf}"

    # === EDGE CASES ===

    def test_between_zero_width_range(self):
        """between (50, 50) -> exact match only."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf_exact = evaluate_condition_confidence("between", 50, (50, 50), 0, 100)
        conf_off = evaluate_condition_confidence("between", 51, (50, 50), 0, 100)

        assert conf_exact is not None
        assert conf_exact == 1.0, f"Exact match should be 1.0, got {conf_exact}"
        assert conf_off is None or conf_off < 0.5, f"Off by 1 should be low, got {conf_off}"


class TestEqualsOperator:
    """Tests for == operator."""

    # === HAPPY PATH ===

    def test_equals_exact_match(self):
        """Exact value -> 1.0."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("==", 50, 50, 0, 100)
        assert conf is not None
        assert conf == 1.0

    def test_equals_within_5_percent_high_conf(self):
        """Within 5% of range -> 0.5-1.0."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        # 100 range, 5% = 5 units. Value 52 is 2 off from 50.
        conf = evaluate_condition_confidence("==", 52, 50, 0, 100)
        assert conf is not None
        assert 0.5 < conf < 1.0, f"Expected 0.5-1.0, got {conf}"

    def test_equals_beyond_5_percent_decays(self):
        """Beyond 5% -> decays from 0.5."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        # Value 60 is 10 off from 50 on a 100 range (10%)
        conf = evaluate_condition_confidence("==", 60, 50, 0, 100)
        assert conf is not None
        assert conf < 0.5, f"Expected < 0.5, got {conf}"

    # === EDGE CASES ===

    def test_equals_at_boundary(self):
        """Value at indicator boundary."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("==", 0, 0, 0, 100)
        assert conf == 1.0


class TestInOperator:
    """Tests for 'in' operator (discrete values)."""

    # === HAPPY PATH ===

    def test_in_value_present(self):
        """Value in list -> 1.0."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("in", 5, [1, 3, 5, 7], 0, 10)
        assert conf is not None
        assert conf == 1.0

    def test_in_value_absent(self):
        """Value not in list -> None or near zero."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("in", 4, [1, 3, 5, 7], 0, 10)
        assert conf is None or conf < 0.01

    # === EDGE CASES ===

    def test_in_empty_list(self):
        """Empty list -> always None."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("in", 5, [], 0, 10)
        assert conf is None

    def test_in_single_item_list_match(self):
        """Single item list, value matches -> 1.0."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("in", 5, [5], 0, 10)
        assert conf == 1.0

    def test_in_single_item_list_no_match(self):
        """Single item list, no match -> None."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        conf = evaluate_condition_confidence("in", 4, [5], 0, 10)
        assert conf is None or conf < 0.01


class TestPatternConfidence:
    """Tests for multi-condition pattern evaluation."""

    # === HAPPY PATH ===

    def test_all_conditions_pass_averages(self):
        """Multiple passing conditions -> average confidence."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_pattern_confidence

        conditions = {
            "rsi14": {"operator": "<", "value": 30},
            "macdLine": {"operator": ">", "value": 0},
        }
        indicators = {"rsi14": 20, "macdLine": 0.5}
        bounds = {"rsi14": (0, 100), "macdLine": (-5, 5)}

        result = evaluate_pattern_confidence(conditions, indicators, bounds)

        assert result is not None
        assert 0.5 < result["overall_confidence"] < 1.0

    def test_one_condition_far_outside_lowers_average(self):
        """One condition far outside -> average still computed, lower confidence.

        RSI=20 < 30: inside, high confidence (~0.77)
        MACD=-4.0 > 0: outside (decay_ratio = 4/5 = 0.8), very low (~0.0004)
        Average ≈ (0.77 + 0.0004) / 2 ≈ 0.39

        Note: V3 doesn't return None for pattern unless an indicator is missing.
        """
        from Fast_Swarm.local_agents.shared.confidence import evaluate_pattern_confidence

        conditions = {
            "rsi14": {"operator": "<", "value": 30},
            "macdLine": {"operator": ">", "value": 0},
        }
        indicators = {"rsi14": 20, "macdLine": -4.0}  # MACD far outside
        bounds = {"rsi14": (0, 100), "macdLine": (-5, 5)}

        result = evaluate_pattern_confidence(conditions, indicators, bounds)

        # Pattern still evaluates but with lower confidence due to averaging
        assert result is not None
        # Average of one high + one very low = moderate
        assert result["overall_confidence"] < 0.5, f"Expected low average, got {result['overall_confidence']}"

    # === COMMON FAILURES ===

    def test_missing_indicator_returns_none(self):
        """Required indicator missing -> None."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_pattern_confidence

        conditions = {"rsi14": {"operator": "<", "value": 30}}
        indicators = {"macdLine": 0.5}  # No rsi14!
        bounds = {"rsi14": (0, 100)}

        result = evaluate_pattern_confidence(conditions, indicators, bounds)
        assert result is None

    # === EDGE CASES ===

    def test_empty_conditions_returns_none(self):
        """No conditions -> None (invalid pattern)."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_pattern_confidence

        result = evaluate_pattern_confidence({}, {"rsi14": 50}, {})
        assert result is None

    def test_single_condition_pattern(self):
        """Single condition pattern works."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_pattern_confidence

        conditions = {"rsi14": {"operator": "<", "value": 30}}
        indicators = {"rsi14": 15}
        bounds = {"rsi14": (0, 100)}

        result = evaluate_pattern_confidence(conditions, indicators, bounds)
        assert result is not None
        assert result["overall_confidence"] > 0.5


class TestTruncation:
    """Tests for 2-decimal truncation and null threshold."""

    def test_truncation_function_floors(self):
        """truncate_confidence floors to 2 decimals."""
        from Fast_Swarm.local_agents.shared.confidence import truncate_confidence

        # 0.156 -> 0.15 (floor, not round)
        assert truncate_confidence(0.156) == 0.15
        assert truncate_confidence(0.999) == 0.99
        assert truncate_confidence(0.50) == 0.50

    def test_truncation_returns_none_below_threshold(self):
        """truncate_confidence returns None for < 0.01."""
        from Fast_Swarm.local_agents.shared.confidence import truncate_confidence

        assert truncate_confidence(0.009) is None
        assert truncate_confidence(0.001) is None
        assert truncate_confidence(0.0) is None

    def test_evaluate_condition_returns_full_precision(self):
        """evaluate_condition_confidence returns full precision floats."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        # Raw confidence values are NOT truncated
        conf = evaluate_condition_confidence("<", 28, 30, 0, 100)
        assert conf is not None
        # Value is a float, not necessarily 2 decimal places
        assert isinstance(conf, float)

    def test_below_threshold_returns_near_zero(self):
        """Far outside threshold -> very small decay value."""
        from Fast_Swarm.local_agents.shared.confidence import evaluate_condition_confidence

        # Value far outside threshold (decay)
        conf = evaluate_condition_confidence("<", 99, 30, 0, 100)
        # Should be very small but not None
        assert conf is not None
        assert conf < 0.01
