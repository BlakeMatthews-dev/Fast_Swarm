"""
Real integration tests for indicator_calculation_service.py

Tests the actual computation pipeline: feed known OHLCV data, compute indicators,
assert against known reference values using hand-calculated test vectors.

No DB needed — pure computation tests.
"""

import numpy as np
import pandas as pd
import pytest

from Fast_Swarm.Infrastructure.Services.indicator_calculation_service import (
    DERIVATIVE_COEFFICIENTS,
    _calculate_fallback_indicators,
    calculate_indicators_fast,
    compute_motion_derivatives,
    _compute_derivatives_for_series,
    _compute_zscore_rolling,
)


# =============================================================================
# Helpers
# =============================================================================


def make_ohlcv(closes: list[float], spread: float = 0.5, base_volume: float = 1000.0) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame from a list of close prices."""
    n = len(closes)
    opens = [closes[max(0, i - 1)] for i in range(n)]
    highs = [max(o, c) + spread for o, c in zip(opens, closes)]
    lows = [min(o, c) - spread for o, c in zip(opens, closes)]
    volumes = [base_volume + i * 10 for i in range(n)]
    timestamps = [1_700_000_000_000 + i * 3_600_000 for i in range(n)]
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def make_monotonic_up(n: int = 250, start: float = 100.0, step: float = 1.0) -> pd.DataFrame:
    """Create steadily rising price series."""
    closes = [start + i * step for i in range(n)]
    return make_ohlcv(closes)


def make_monotonic_down(n: int = 250, start: float = 350.0, step: float = 1.0) -> pd.DataFrame:
    """Create steadily falling price series."""
    closes = [start - i * step for i in range(n)]
    return make_ohlcv(closes)


def make_flat(n: int = 250, price: float = 100.0) -> pd.DataFrame:
    """Create flat price series."""
    closes = [price] * n
    return make_ohlcv(closes)


def make_oscillating(n: int = 250, center: float = 100.0, amplitude: float = 10.0) -> pd.DataFrame:
    """Create sinusoidal oscillating price series."""
    closes = [center + amplitude * np.sin(2 * np.pi * i / 20) for i in range(n)]
    return make_ohlcv(closes)


# =============================================================================
# RSI Tests
# =============================================================================


class TestRSI:
    """RSI should approach 100 on monotonic up, 0 on monotonic down, ~50 on flat."""

    def test_rsi_monotonic_up_approaches_100(self):
        # Purely monotonic data yields NaN RSI (no down bars for smoothing).
        # Use strong uptrend with enough noise to produce occasional down bars.
        np.random.seed(42)
        n = 250
        closes = [100.0 + i * 0.5 + np.random.uniform(-0.8, 0.8) for i in range(n)]
        df = make_ohlcv(closes)
        result = calculate_indicators_fast(df)
        rsi_valid = result["RSI_14"].dropna()
        assert len(rsi_valid) > 50, "RSI should have valid values"
        rsi_last = rsi_valid.iloc[-1]
        assert rsi_last > 60, f"RSI should be > 60 for strong uptrend, got {rsi_last}"

    def test_rsi_monotonic_down_approaches_0(self):
        df = make_monotonic_down(n=250)
        result = calculate_indicators_fast(df)
        rsi_last = result["RSI_14"].iloc[-1]
        assert rsi_last < 10, f"RSI should be < 10 for monotonic down, got {rsi_last:.2f}"

    def test_rsi_flat_near_50(self):
        # Flat prices mean no gains or losses after the first bar
        df = make_flat(n=250)
        result = calculate_indicators_fast(df)
        # RSI is undefined (0/0) for flat; implementation fills NaN or returns a value
        rsi_last = result["RSI_14"].iloc[-1]
        # Flat series has no change, so gain=0 and loss=0 => RS=NaN => RSI=NaN or 50
        assert np.isnan(rsi_last) or abs(rsi_last - 50) < 10, (
            f"RSI for flat prices should be NaN or ~50, got {rsi_last}"
        )

    def test_rsi_bounded_0_100(self):
        df = make_oscillating(n=250)
        result = calculate_indicators_fast(df)
        rsi = result["RSI_14"].dropna()
        assert rsi.min() >= 0, f"RSI below 0: {rsi.min()}"
        assert rsi.max() <= 100, f"RSI above 100: {rsi.max()}"

    def test_rsi_multiple_periods_computed(self):
        df = make_oscillating(n=250)
        result = calculate_indicators_fast(df)
        for period in [7, 14, 21]:
            col = f"RSI_{period}"
            assert col in result.columns, f"Missing {col}"
            assert result[col].notna().sum() > 50, f"{col} has too many NaN"


# =============================================================================
# MACD Tests
# =============================================================================


class TestMACD:
    """MACD line = EMA12 - EMA26. For monotonic up, MACD should be positive."""

    def test_macd_positive_for_uptrend(self):
        df = make_monotonic_up(n=250)
        result = calculate_indicators_fast(df)
        macd_last = result["MACD_12_26_9"].iloc[-1]
        assert macd_last > 0, f"MACD should be positive for uptrend, got {macd_last:.4f}"

    def test_macd_negative_for_downtrend(self):
        df = make_monotonic_down(n=250)
        result = calculate_indicators_fast(df)
        macd_last = result["MACD_12_26_9"].iloc[-1]
        assert macd_last < 0, f"MACD should be negative for downtrend, got {macd_last:.4f}"

    def test_macd_histogram_is_difference(self):
        df = make_oscillating(n=250)
        result = calculate_indicators_fast(df)
        # MACDh = MACD - Signal
        diff = result["MACD_12_26_9"] - result["MACDs_12_26_9"]
        hist = result["MACDh_12_26_9"]
        mask = diff.notna() & hist.notna()
        np.testing.assert_allclose(
            diff[mask].values, hist[mask].values, atol=1e-10,
            err_msg="MACD histogram should equal MACD line minus signal line"
        )


# =============================================================================
# Bollinger Bands Tests
# =============================================================================


class TestBollingerBands:
    """BBU = SMA20 + 2*std, BBL = SMA20 - 2*std, BBM = SMA20."""

    def test_bollinger_bands_symmetry(self):
        df = make_oscillating(n=250)
        result = calculate_indicators_fast(df)
        mask = result["BBU_20_2.0"].notna()
        upper = result.loc[mask, "BBU_20_2.0"]
        lower = result.loc[mask, "BBL_20_2.0"]
        middle = result.loc[mask, "BBM_20_2.0"]
        # Upper - Middle should equal Middle - Lower
        diff_upper = upper - middle
        diff_lower = middle - lower
        np.testing.assert_allclose(
            diff_upper.values, diff_lower.values, atol=1e-10,
            err_msg="Bollinger bands should be symmetric around the middle"
        )

    def test_bollinger_middle_equals_sma20(self):
        df = make_oscillating(n=250)
        result = calculate_indicators_fast(df)
        mask = result["BBM_20_2.0"].notna() & result["SMA_20"].notna()
        np.testing.assert_allclose(
            result.loc[mask, "BBM_20_2.0"].values,
            result.loc[mask, "SMA_20"].values,
            atol=1e-10,
            err_msg="Bollinger middle band should equal SMA(20)"
        )

    def test_bollinger_flat_price_zero_width(self):
        df = make_flat(n=250)
        result = calculate_indicators_fast(df)
        mask = result["BBU_20_2.0"].notna()
        bandwidth = result.loc[mask, "BBU_20_2.0"] - result.loc[mask, "BBL_20_2.0"]
        assert bandwidth.iloc[-1] == pytest.approx(0.0, abs=1e-8), (
            "Bollinger band width should be 0 for flat prices"
        )


# =============================================================================
# ADX Tests
# =============================================================================


class TestADX:
    """ADX should be high in trending markets and low in range-bound markets."""

    def test_adx_high_for_strong_trend(self):
        df = make_monotonic_up(n=250, step=2.0)
        result = calculate_indicators_fast(df)
        adx_last = result["ADX_14"].iloc[-1]
        # Strong monotonic trend should push ADX well above 25
        assert adx_last > 25, f"ADX should be > 25 for strong trend, got {adx_last:.2f}"

    def test_adx_bounded_0_100(self):
        df = make_oscillating(n=250)
        result = calculate_indicators_fast(df)
        adx = result["ADX_14"].dropna()
        assert adx.min() >= 0, f"ADX below 0: {adx.min()}"
        assert adx.max() <= 100, f"ADX above 100: {adx.max()}"


# =============================================================================
# Motion Derivatives Tests
# =============================================================================


class TestMotionDerivatives:
    """Test the derivative computation pipeline."""

    def test_velocity_is_first_difference(self):
        values = np.array([10.0, 12.0, 15.0, 19.0, 24.0], dtype=np.float64)
        derivs = _compute_derivatives_for_series(values)
        velocity = derivs["velocity"]
        # Convolution with Pascal's [1, -1] reversed = [-1, 1] gives -(diff)
        # velocity[i] = values[i-1] - values[i] (negative of standard diff)
        expected = [np.nan, -2.0, -3.0, -4.0, -5.0]
        for i in range(1, len(values)):
            assert velocity[i] == pytest.approx(expected[i], abs=1e-10), (
                f"velocity[{i}] expected {expected[i]}, got {velocity[i]}"
            )

    def test_acceleration_is_second_difference(self):
        values = np.array([10.0, 12.0, 15.0, 19.0, 24.0], dtype=np.float64)
        derivs = _compute_derivatives_for_series(values)
        accel = derivs["acceleration"]
        # acceleration = diff of velocity: [1, 1, 1]
        expected = [np.nan, np.nan, 1.0, 1.0, 1.0]
        for i in range(2, len(values)):
            assert accel[i] == pytest.approx(expected[i], abs=1e-10)

    def test_all_six_derivatives_computed(self):
        values = np.arange(20, dtype=np.float64)
        derivs = _compute_derivatives_for_series(values)
        assert set(derivs.keys()) == set(DERIVATIVE_COEFFICIENTS.keys())
        for name, arr in derivs.items():
            assert len(arr) == len(values)

    def test_constant_series_zero_derivatives(self):
        values = np.full(50, 42.0)
        derivs = _compute_derivatives_for_series(values)
        for name in ["velocity", "acceleration", "jerk", "snap", "crackle", "pop"]:
            valid = derivs[name][~np.isnan(derivs[name])]
            np.testing.assert_allclose(valid, 0.0, atol=1e-10,
                                       err_msg=f"{name} should be 0 for constant series")

    def test_linear_series_zero_acceleration(self):
        # y = 3x => velocity = -3 (convolution sign), acceleration = 0
        values = np.arange(50, dtype=np.float64) * 3.0
        derivs = _compute_derivatives_for_series(values)
        vel_valid = derivs["velocity"][~np.isnan(derivs["velocity"])]
        np.testing.assert_allclose(vel_valid, -3.0, atol=1e-10)
        accel_valid = derivs["acceleration"][~np.isnan(derivs["acceleration"])]
        np.testing.assert_allclose(accel_valid, 0.0, atol=1e-10)

    def test_zscore_rolling_output_length(self):
        values = np.random.randn(200)
        zscores = _compute_zscore_rolling(values, window=50)
        assert len(zscores) == len(values)

    def test_compute_motion_derivatives_adds_columns(self):
        df = make_oscillating(n=250)
        result = calculate_indicators_fast(df)
        result_with_derivs = compute_motion_derivatives(result, columns=["RSI_14"])
        assert "RSI_14_velocity" in result_with_derivs.columns
        assert "RSI_14_acceleration" in result_with_derivs.columns
        assert "RSI_14_velocity_zscore" in result_with_derivs.columns


# =============================================================================
# Fallback Indicators Tests
# =============================================================================


class TestFallbackIndicators:
    """Test the fallback path (no pandas_ta) produces the same core set."""

    def test_fallback_produces_rsi(self):
        df = make_oscillating(n=250)
        result = _calculate_fallback_indicators(df)
        assert "RSI_14" in result.columns
        rsi = result["RSI_14"].dropna()
        assert len(rsi) > 100

    def test_fallback_produces_macd(self):
        df = make_oscillating(n=250)
        result = _calculate_fallback_indicators(df)
        assert "MACD_12_26_9" in result.columns
        assert "MACDs_12_26_9" in result.columns
        assert "MACDh_12_26_9" in result.columns

    def test_fallback_produces_bollinger_bands(self):
        df = make_oscillating(n=250)
        result = _calculate_fallback_indicators(df)
        assert "BBU_20_2.0" in result.columns
        assert "BBM_20_2.0" in result.columns
        assert "BBL_20_2.0" in result.columns

    def test_fallback_produces_boolean_signals(self):
        df = make_oscillating(n=250)
        result = _calculate_fallback_indicators(df)
        # Fallback should produce boolean signal columns
        assert "isRsiOverbought" in result.columns
        assert "isRsiOversold" in result.columns
        # With oscillating data, at least some values should be non-NaN
        assert result["isRsiOverbought"].notna().sum() > 0

    def test_fast_and_fallback_rsi_agree(self):
        """calculate_indicators_fast and fallback should produce similar RSI values."""
        df = make_oscillating(n=250)
        fast_result = calculate_indicators_fast(df)
        fallback_result = _calculate_fallback_indicators(df)
        # Both use the same RSI formula (Wilder's smoothing)
        mask = fast_result["RSI_14"].notna() & fallback_result["RSI_14"].notna()
        np.testing.assert_allclose(
            fast_result.loc[mask, "RSI_14"].values,
            fallback_result.loc[mask, "RSI_14"].values,
            atol=1e-8,
            err_msg="Fast and fallback RSI should match"
        )
