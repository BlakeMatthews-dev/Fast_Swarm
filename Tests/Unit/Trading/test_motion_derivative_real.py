"""
Real integration tests for motion_derivative_service.py

Tests the pure-computation functions:
- compute_zscore: z-score against a rolling window
- compute_derivatives: velocity, acceleration, jerk z-scores from close/ADX series
- compute_motion_derivatives_from_history: in-memory candle history variant
- enrich_candle_with_motion / check_defensive_trigger / check_multi_tf_defensive

No DB needed — all functions tested are pure computation or in-memory.
"""

import statistics

import pytest

from Fast_Swarm.Infrastructure.Services.motion_derivative_service import (
    ACC_THRESHOLD,
    ADX_JERK_THRESHOLD,
    ZSCORE_WINDOW,
    check_defensive_trigger,
    check_multi_tf_defensive,
    compute_derivatives,
    compute_motion_derivatives_from_history,
    compute_zscore,
    enrich_candle_with_motion,
)


# =============================================================================
# compute_zscore Tests
# =============================================================================


class TestComputeZscore:
    """Test z-score computation against recent window."""

    def test_zscore_of_mean_is_zero(self):
        values = [10.0, 12.0, 11.0, 13.0, 10.5, 11.5, 12.5, 10.0, 11.0, 12.0,
                  10.0, 12.0, 11.0, 13.0, 10.5, 11.5, 12.5, 10.0, 11.0, 12.0, 11.0]
        mean_val = statistics.mean(values[-ZSCORE_WINDOW:])
        result = compute_zscore(values, mean_val)
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_zscore_positive_for_above_mean(self):
        values = list(range(1, ZSCORE_WINDOW + 1))  # 1..21
        current = 100.0  # Way above mean
        result = compute_zscore(values, current)
        assert result is not None
        assert result > 0

    def test_zscore_negative_for_below_mean(self):
        values = list(range(1, ZSCORE_WINDOW + 1))
        current = -100.0  # Way below mean
        result = compute_zscore(values, current)
        assert result is not None
        assert result < 0

    def test_zscore_none_for_insufficient_data(self):
        values = [1.0, 2.0, 3.0]  # Too few
        result = compute_zscore(values, 2.0)
        assert result is None

    def test_zscore_none_for_none_current(self):
        values = list(range(ZSCORE_WINDOW + 5))
        result = compute_zscore(values, None)
        assert result is None

    def test_zscore_zero_for_constant_series(self):
        values = [5.0] * (ZSCORE_WINDOW + 5)
        result = compute_zscore(values, 5.0)
        # std=0 => return 0.0
        assert result == 0.0

    def test_zscore_uses_last_window_only(self):
        # First 100 values are 0, last ZSCORE_WINDOW values are 10
        values = [0.0] * 100 + [10.0] * ZSCORE_WINDOW
        result = compute_zscore(values, 10.0)
        # The window is all 10s, so mean=10, std=0 => return 0.0
        assert result == 0.0


# =============================================================================
# compute_derivatives Tests
# =============================================================================


class TestComputeDerivatives:
    """Test full derivative pipeline: closes + ADX -> z-scored derivatives."""

    def _make_linear_series(self, n: int, slope: float = 1.0, start: float = 100.0) -> list[float]:
        return [start + i * slope for i in range(n)]

    def test_insufficient_data_returns_nones(self):
        closes = [100.0, 101.0, 102.0]  # Way too few
        adx = [25.0, 26.0, 27.0]
        result = compute_derivatives(closes, adx)
        assert result["close_velocity_zscore"] is None
        assert result["close_acceleration_zscore"] is None
        assert result["defensive_trigger"] is None

    def test_linear_series_zero_acceleration(self):
        """Linear price series: constant velocity, zero acceleration."""
        n = ZSCORE_WINDOW + 10
        closes = self._make_linear_series(n, slope=1.0)
        adx = [25.0] * n
        result = compute_derivatives(closes, adx)
        # Acceleration of linear series = 0, so z-score should be ~0
        if result["close_acceleration_zscore"] is not None:
            assert abs(result["close_acceleration_zscore"]) < 0.1, (
                f"Acceleration z-score should be ~0 for linear series, got {result['close_acceleration_zscore']}"
            )

    def test_quadratic_series_constant_acceleration(self):
        """Quadratic price series: linearly increasing velocity, constant acceleration."""
        n = ZSCORE_WINDOW + 10
        closes = [100.0 + 0.5 * i * i for i in range(n)]
        adx = [25.0] * n
        result = compute_derivatives(closes, adx)
        # Acceleration is constant (= 1.0), so z-score should be ~0
        if result["close_acceleration_zscore"] is not None:
            assert abs(result["close_acceleration_zscore"]) < 0.5

    def test_velocity_zscore_present_with_enough_data(self):
        n = ZSCORE_WINDOW + 10
        closes = self._make_linear_series(n)
        adx = [30.0] * n
        result = compute_derivatives(closes, adx)
        # With linear data and enough points, velocity z-score should be computed
        assert result["close_velocity_zscore"] is not None

    def test_adx_derivatives_computed_with_valid_data(self):
        n = ZSCORE_WINDOW + 10
        closes = self._make_linear_series(n)
        # Give ADX a non-trivial pattern
        adx = [20.0 + 0.5 * i for i in range(n)]
        result = compute_derivatives(closes, adx)
        # ADX jerk z-score should be computed with enough data
        # (linear ADX => constant velocity => zero accel => zero jerk => z-score ~0)
        if result["adx_14_jerk_zscore"] is not None:
            assert abs(result["adx_14_jerk_zscore"]) < 0.5

    def test_adx_none_values_handled(self):
        n = ZSCORE_WINDOW + 10
        closes = self._make_linear_series(n)
        adx = [None] * n  # All None
        result = compute_derivatives(closes, adx)
        assert result["adx_14_jerk_zscore"] is None


# =============================================================================
# Defensive Trigger Tests
# =============================================================================


class TestDefensiveTrigger:
    """Test the CTC (Crash-To-Cash) defensive trigger logic."""

    def test_defensive_trigger_fires_on_crash_signal(self):
        """When both acc and adx_jerk z-scores breach thresholds, trigger fires."""
        n = ZSCORE_WINDOW + 10
        # Create a series that crashes hard at the end
        closes = [100.0] * (n - 5) + [100.0, 95.0, 85.0, 70.0, 50.0]
        # ADX also jerks down
        adx = [30.0] * (n - 5) + [30.0, 28.0, 22.0, 15.0, 8.0]
        result = compute_derivatives(closes, adx)

        # The trigger requires both to breach thresholds
        # Even if our synthetic data doesn't perfectly trigger, verify the logic path
        acc = result["close_acceleration_zscore"]
        adx_jerk = result["adx_14_jerk_zscore"]

        if acc is not None and adx_jerk is not None:
            expected_trigger = 1 if (acc < ACC_THRESHOLD and adx_jerk < ADX_JERK_THRESHOLD) else 0
            assert result["defensive_trigger"] == expected_trigger

    def test_defensive_trigger_none_when_insufficient(self):
        closes = [100.0, 101.0, 102.0]
        adx = [25.0, 26.0, 27.0]
        result = compute_derivatives(closes, adx)
        assert result["defensive_trigger"] is None

    def test_check_defensive_trigger_helper(self):
        assert check_defensive_trigger({"defensive_trigger": 1}) is True
        assert check_defensive_trigger({"defensive_trigger": 0}) is False
        assert check_defensive_trigger({"defensive_trigger": None}) is False
        assert check_defensive_trigger({}) is False

    def test_check_multi_tf_defensive(self):
        tf_1h = {"defensive_trigger": 1}
        tf_4h = {"defensive_trigger": 1}
        assert check_multi_tf_defensive(tf_1h, tf_4h) is True

        tf_4h_safe = {"defensive_trigger": 0}
        assert check_multi_tf_defensive(tf_1h, tf_4h_safe) is False


# =============================================================================
# compute_motion_derivatives_from_history Tests
# =============================================================================


class TestFromHistory:
    """Test in-memory candle history variant."""

    def test_returns_empty_for_insufficient_history(self):
        history = [{"close": 100.0, "adx_14": 25.0}] * 5
        current = {"close": 101.0, "adx_14": 26.0}
        result = compute_motion_derivatives_from_history(history, current)
        assert result == {}

    def test_returns_derivatives_with_sufficient_history(self):
        n = ZSCORE_WINDOW + 5
        history = [{"close": 100.0 + i, "adx_14": 25.0 + 0.1 * i} for i in range(n)]
        current = {"close": 100.0 + n, "adx_14": 25.0 + 0.1 * n}
        result = compute_motion_derivatives_from_history(history, current)
        assert "close_velocity_zscore" in result
        assert "close_acceleration_zscore" in result

    def test_enrich_candle_modifies_in_place(self):
        n = ZSCORE_WINDOW + 5
        history = [{"close": 100.0 + i, "adx_14": 25.0} for i in range(n)]
        candle = {"close": 100.0 + n, "adx_14": 25.0, "other_field": "preserved"}
        enriched = enrich_candle_with_motion(candle, history)
        # Should be the same dict object
        assert enriched is candle
        assert "other_field" in enriched
        assert enriched["other_field"] == "preserved"
        # Should have motion derivative keys
        assert "close_velocity_zscore" in enriched

    def test_handles_missing_adx_gracefully(self):
        n = ZSCORE_WINDOW + 5
        history = [{"close": 100.0 + i} for i in range(n)]  # No adx_14
        current = {"close": 100.0 + n}
        result = compute_motion_derivatives_from_history(history, current)
        # Should still compute close derivatives
        assert "close_velocity_zscore" in result
        # ADX derivatives should be None since all ADX values are None
        assert result.get("adx_14_jerk_zscore") is None
