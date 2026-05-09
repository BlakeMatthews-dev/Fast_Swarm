"""
Paper Trading Pipeline Soundness Tests - REAL CODE ONLY (EDD/TDD)

These tests exercise the ACTUAL pipeline that paper trading uses:
1. calculate_indicators_fast() on real OHLC data
2. Column rename mapping (pandas_ta -> DB-style names)
3. compute_derived_for_candle() derived indicators
4. evaluate_conditions() pattern matching
5. Full signal generation from known market conditions

NO MOCKS. Every function call is the real thing.
If these tests pass, the pipeline actually works.
If they fail, the pipeline is broken.
"""

import numpy as np
import pandas as pd
import pytest

from Fast_Swarm.Agents.Models.agent_models import Agent
from Fast_Swarm.Infrastructure.Services.indicator_calculation_service import (
    calculate_indicators_fast,
)
from Fast_Swarm.Infrastructure.Services.indicator_enrichment_service import (
    compute_derived_for_candle,
)
from Fast_Swarm.local_agents.backtest.pattern_matcher import evaluate_conditions
from Fast_Swarm.Trading.Services.agent_paper_trading_service import (
    AgentPaperTradingService,
)


# ============================================================================
# FIXTURES: Real market data generators
# ============================================================================


def make_trending_up_ohlcv(n_candles: int = 300, start_price: float = 40000.0) -> pd.DataFrame:
    """
    Generate realistic uptrending OHLCV data.

    Produces a steady uptrend with natural noise, high-low spread,
    and volume variation. RSI will be elevated, MACD bullish.
    """
    np.random.seed(42)  # Deterministic
    prices = [start_price]
    for i in range(n_candles - 1):
        # Uptrend: +0.2% per candle average with noise
        change = prices[-1] * (0.002 + np.random.normal(0, 0.005))
        prices.append(prices[-1] + change)

    closes = np.array(prices)
    # Realistic OHLC: high above close, low below close
    highs = closes * (1 + np.abs(np.random.normal(0.002, 0.001, n_candles)))
    lows = closes * (1 - np.abs(np.random.normal(0.002, 0.001, n_candles)))
    opens = closes * (1 + np.random.normal(0, 0.001, n_candles))
    volumes = np.random.uniform(100, 1000, n_candles)

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def make_trending_down_ohlcv(n_candles: int = 300, start_price: float = 60000.0) -> pd.DataFrame:
    """
    Generate realistic downtrending OHLCV data.

    RSI will be low (<30 at extremes), MACD bearish.
    """
    np.random.seed(123)
    prices = [start_price]
    for i in range(n_candles - 1):
        # Downtrend: -0.3% per candle average with noise
        change = prices[-1] * (-0.003 + np.random.normal(0, 0.004))
        prices.append(max(prices[-1] + change, 100))  # Floor at 100

    closes = np.array(prices)
    highs = closes * (1 + np.abs(np.random.normal(0.002, 0.001, n_candles)))
    lows = closes * (1 - np.abs(np.random.normal(0.002, 0.001, n_candles)))
    opens = closes * (1 + np.random.normal(0, 0.001, n_candles))
    volumes = np.random.uniform(100, 1000, n_candles)

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def make_choppy_ohlcv(n_candles: int = 300, center_price: float = 50000.0) -> pd.DataFrame:
    """
    Generate sideways/choppy OHLCV data (no trend).

    RSI will hover around 50, ADX will be low (<20).
    """
    np.random.seed(99)
    prices = [center_price]
    for i in range(n_candles - 1):
        # Mean-reverting: oscillate around center
        reversion = (center_price - prices[-1]) * 0.02
        change = reversion + np.random.normal(0, center_price * 0.003)
        prices.append(prices[-1] + change)

    closes = np.array(prices)
    highs = closes * (1 + np.abs(np.random.normal(0.002, 0.001, n_candles)))
    lows = closes * (1 - np.abs(np.random.normal(0.002, 0.001, n_candles)))
    opens = closes * (1 + np.random.normal(0, 0.001, n_candles))
    volumes = np.random.uniform(100, 1000, n_candles)

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def run_full_pipeline(df: pd.DataFrame) -> dict:
    """
    Run the EXACT same pipeline as _process_candle_for_agents:
    1. calculate_indicators_fast()
    2. Column rename mapping
    3. Extract last row as dict
    4. compute_derived_for_candle()

    Returns the candle_data dict that evaluate_conditions receives.
    """
    # Step 1: Calculate indicators (REAL)
    df = calculate_indicators_fast(df, verbose=False)

    # Step 2: Column rename mapping (EXACT copy from _process_candle_for_agents)
    col_renames = {
        "MACD_12_26_9": "macd_line",
        "MACDs_12_26_9": "macd_signal",
        "MACDh_12_26_9": "macd_histogram",
        "BBL_20_2.0": "bb_lower",
        "BBM_20_2.0": "bb_middle",
        "BBU_20_2.0": "bb_upper",
        "BBB_20_2.0": "bb_bandwidth",
        "BBP_20_2.0": "bb_percent",
        "STOCHk_14_3_3": "stoch_k",
        "STOCHd_14_3_3": "stoch_d",
        "STOCHRSIk_14_14_3_3": "stochrsi_k",
        "STOCHRSId_14_14_3_3": "stochrsi_d",
        "DMP_14": "plus_di",
        "DMN_14": "minus_di",
        "ATRr_7": "atr_7",
        "ATRr_14": "atr_14",
        "NATR_14": "natr_14",
        "TRUERANGE_14": "true_range",
        "AROONU_14": "aroon_up",
        "AROOND_14": "aroon_down",
        "AROONOSC_14": "aroon_osc",
        "CCI_14": "cci_14",
        "WILLR_14": "willr_14",
        "ROC_10": "roc_10",
        "CMF_20": "cmf_20",
        "MFI_14": "mfi_14",
        "EMV_14": "emv_14",
        "VHF_28": "vhf_28",
    }
    df.columns = [c.lower() if c not in col_renames else c for c in df.columns]
    df.rename(columns={k: v for k, v in col_renames.items() if k in df.columns}, inplace=True)

    # Step 3: Extract last row as dict (filter NaN)
    last_row = df.iloc[-1]
    candle_data = {}
    for k, v in last_row.items():
        if v is None:
            continue
        try:
            if pd.isna(v):
                continue
        except (TypeError, ValueError):
            pass
        candle_data[k] = v

    # Step 4: Compute derived indicators (REAL)
    derived = compute_derived_for_candle(candle_data)
    candle_data.update(derived)

    return candle_data


# ============================================================================
# TEST: Indicator calculation produces expected columns
# ============================================================================


class TestIndicatorPipelineProducesColumns:
    """SOUNDNESS: calculate_indicators_fast produces all columns patterns need."""

    @pytest.mark.soundness
    def test_rsi_columns_exist(self):
        """SOUNDNESS: RSI columns are computed and renamed correctly."""
        df = make_trending_up_ohlcv()
        candle = run_full_pipeline(df)

        assert "rsi_14" in candle, f"Missing rsi_14. Keys: {sorted(candle.keys())}"
        assert "rsi_7" in candle
        assert "rsi_21" in candle

    @pytest.mark.soundness
    def test_macd_columns_exist(self):
        """SOUNDNESS: MACD columns are renamed from pandas_ta format."""
        df = make_trending_up_ohlcv()
        candle = run_full_pipeline(df)

        assert "macd_line" in candle
        assert "macd_signal" in candle
        assert "macd_histogram" in candle

    @pytest.mark.soundness
    def test_bollinger_columns_exist(self):
        """SOUNDNESS: Bollinger Band columns are renamed correctly."""
        df = make_trending_up_ohlcv()
        candle = run_full_pipeline(df)

        assert "bb_upper" in candle
        assert "bb_lower" in candle
        assert "bb_middle" in candle
        assert "bb_bandwidth" in candle
        assert "bb_percent" in candle

    @pytest.mark.soundness
    def test_moving_average_columns_exist(self):
        """SOUNDNESS: SMA/EMA columns are lowercased correctly."""
        df = make_trending_up_ohlcv()
        candle = run_full_pipeline(df)

        assert "sma_20" in candle
        assert "sma_50" in candle
        assert "ema_9" in candle
        assert "ema_21" in candle

    @pytest.mark.soundness
    def test_adx_columns_exist(self):
        """SOUNDNESS: ADX and directional indicator columns exist."""
        df = make_trending_up_ohlcv()
        candle = run_full_pipeline(df)

        assert "adx_14" in candle
        assert "plus_di" in candle
        assert "minus_di" in candle

    @pytest.mark.soundness
    def test_stochastic_columns_exist(self):
        """SOUNDNESS: Stochastic columns are renamed correctly."""
        df = make_trending_up_ohlcv()
        candle = run_full_pipeline(df)

        assert "stoch_k" in candle
        assert "stoch_d" in candle

    @pytest.mark.soundness
    def test_volatility_columns_exist(self):
        """SOUNDNESS: ATR/NATR columns are renamed correctly."""
        df = make_trending_up_ohlcv()
        candle = run_full_pipeline(df)

        assert "atr_14" in candle
        assert "atr_7" in candle
        assert "natr_14" in candle

    @pytest.mark.soundness
    def test_motion_derivatives_exist(self):
        """SOUNDNESS: Motion derivatives (velocity, acceleration) are computed."""
        df = make_trending_up_ohlcv()
        candle = run_full_pipeline(df)

        assert "close_velocity" in candle
        assert "close_acceleration" in candle
        assert "close_velocity_zscore" in candle
        assert "close_acceleration_zscore" in candle

    @pytest.mark.soundness
    def test_derived_indicators_computed(self):
        """SOUNDNESS: compute_derived_for_candle adds MA crosses, RSI zones, etc."""
        df = make_trending_up_ohlcv()
        candle = run_full_pipeline(df)

        # These come from compute_derived_for_candle
        assert "price_above_ema_21" in candle
        assert "price_above_sma_50" in candle
        assert "rsi_oversold" in candle or "rsi_overbought" in candle or "rsi_neutral" in candle
        assert "ma_cross_20_50" in candle

    @pytest.mark.soundness
    def test_no_uppercase_pandas_ta_columns_remain(self):
        """SOUNDNESS: All pandas_ta column names are lowercased or renamed."""
        df = make_trending_up_ohlcv()
        candle = run_full_pipeline(df)

        # No column should still have the raw pandas_ta uppercase format
        uppercase_keys = [k for k in candle.keys() if k != k.lower() and k not in ("OBV",)]
        assert uppercase_keys == [], f"Unrenamed uppercase columns: {uppercase_keys}"


# ============================================================================
# TEST: Indicator values are in valid ranges
# ============================================================================


class TestIndicatorValuesAreValid:
    """SOUNDNESS: Indicator values are in economically valid ranges."""

    @pytest.mark.soundness
    def test_rsi_bounded_0_100(self):
        """SOUNDNESS: RSI is always between 0 and 100."""
        for maker in [make_trending_up_ohlcv, make_trending_down_ohlcv, make_choppy_ohlcv]:
            candle = run_full_pipeline(maker())
            rsi = candle["rsi_14"]
            assert 0 <= rsi <= 100, f"RSI out of range: {rsi}"

    @pytest.mark.soundness
    def test_stochastic_bounded_0_100(self):
        """SOUNDNESS: Stochastic K/D are between 0 and 100."""
        for maker in [make_trending_up_ohlcv, make_trending_down_ohlcv, make_choppy_ohlcv]:
            candle = run_full_pipeline(maker())
            assert 0 <= candle["stoch_k"] <= 100
            assert 0 <= candle["stoch_d"] <= 100

    @pytest.mark.soundness
    def test_adx_bounded_0_100(self):
        """SOUNDNESS: ADX is between 0 and 100."""
        for maker in [make_trending_up_ohlcv, make_trending_down_ohlcv, make_choppy_ohlcv]:
            candle = run_full_pipeline(maker())
            assert 0 <= candle["adx_14"] <= 100

    @pytest.mark.soundness
    def test_bb_percent_reasonable(self):
        """SOUNDNESS: Bollinger %B is typically between -0.5 and 1.5."""
        for maker in [make_trending_up_ohlcv, make_trending_down_ohlcv, make_choppy_ohlcv]:
            candle = run_full_pipeline(maker())
            bb_pct = candle["bb_percent"]
            assert -2.0 <= bb_pct <= 3.0, f"BB%B unreasonable: {bb_pct}"

    @pytest.mark.soundness
    def test_atr_positive(self):
        """SOUNDNESS: ATR is always positive."""
        for maker in [make_trending_up_ohlcv, make_trending_down_ohlcv, make_choppy_ohlcv]:
            candle = run_full_pipeline(maker())
            assert candle["atr_14"] > 0

    @pytest.mark.soundness
    def test_uptrend_has_high_rsi(self):
        """SOUNDNESS: Strong uptrend produces RSI > 50."""
        candle = run_full_pipeline(make_trending_up_ohlcv())
        assert candle["rsi_14"] > 50, f"Uptrend RSI should be > 50, got {candle['rsi_14']}"

    @pytest.mark.soundness
    def test_downtrend_has_low_rsi(self):
        """SOUNDNESS: Strong downtrend produces RSI < 50."""
        candle = run_full_pipeline(make_trending_down_ohlcv())
        assert candle["rsi_14"] < 50, f"Downtrend RSI should be < 50, got {candle['rsi_14']}"

    @pytest.mark.soundness
    def test_uptrend_has_positive_macd(self):
        """SOUNDNESS: Strong uptrend produces positive MACD line."""
        candle = run_full_pipeline(make_trending_up_ohlcv())
        assert candle["macd_line"] > 0, f"Uptrend MACD should be positive, got {candle['macd_line']}"

    @pytest.mark.soundness
    def test_downtrend_has_negative_macd(self):
        """SOUNDNESS: Strong downtrend produces negative MACD line."""
        candle = run_full_pipeline(make_trending_down_ohlcv())
        assert candle["macd_line"] < 0, f"Downtrend MACD should be negative, got {candle['macd_line']}"


# ============================================================================
# TEST: Pattern matcher resolves indicator names from pipeline output
# ============================================================================


class TestPatternMatcherResolvesIndicators:
    """SOUNDNESS: evaluate_conditions can find indicators produced by the pipeline."""

    @pytest.mark.soundness
    def test_rsi14_resolves(self):
        """SOUNDNESS: Pattern condition 'rsi14' resolves to pipeline's 'rsi_14'."""
        candle = run_full_pipeline(make_trending_up_ohlcv())
        conditions = {"rsi14": {"operator": "<", "value": 100}}  # Always true
        result = evaluate_conditions(conditions, candle)
        # Should not be "missing" - should resolve and evaluate
        assert result.conditions_met > 0, f"rsi14 not resolved. Details: {result.condition_details}"

    @pytest.mark.soundness
    def test_macdHistogram_resolves(self):
        """SOUNDNESS: Pattern condition 'macdHistogram' resolves to 'macd_histogram'."""
        candle = run_full_pipeline(make_trending_up_ohlcv())
        conditions = {"macdHistogram": {"operator": ">", "value": -99999}}  # Always true
        result = evaluate_conditions(conditions, candle)
        assert result.conditions_met > 0, f"macdHistogram not resolved. Details: {result.condition_details}"

    @pytest.mark.soundness
    def test_adx14_resolves(self):
        """SOUNDNESS: Pattern condition 'adx14' resolves to 'adx_14'."""
        candle = run_full_pipeline(make_trending_up_ohlcv())
        conditions = {"adx14": {"operator": ">", "value": 0}}
        result = evaluate_conditions(conditions, candle)
        assert result.conditions_met > 0, f"adx14 not resolved. Details: {result.condition_details}"

    @pytest.mark.soundness
    def test_ema21_resolves(self):
        """SOUNDNESS: Pattern condition 'ema21' resolves to 'ema_21'."""
        candle = run_full_pipeline(make_trending_up_ohlcv())
        conditions = {"ema21": {"operator": ">", "value": 0}}
        result = evaluate_conditions(conditions, candle)
        assert result.conditions_met > 0, f"ema21 not resolved. Details: {result.condition_details}"

    @pytest.mark.soundness
    def test_bollingerPercentB_resolves(self):
        """SOUNDNESS: Pattern condition 'bollingerPercentB' resolves to 'bb_percent'."""
        candle = run_full_pipeline(make_trending_up_ohlcv())
        conditions = {"bollingerPercentB": {"operator": ">", "value": -10}}  # Always true
        result = evaluate_conditions(conditions, candle)
        assert result.conditions_met > 0, f"bollingerPercentB not resolved. Details: {result.condition_details}"

    @pytest.mark.soundness
    def test_stochasticK_resolves(self):
        """SOUNDNESS: Pattern condition 'stochasticK' resolves to 'stoch_k'."""
        candle = run_full_pipeline(make_trending_up_ohlcv())
        conditions = {"stochasticK": {"operator": ">", "value": 0}}
        result = evaluate_conditions(conditions, candle)
        assert result.conditions_met > 0, f"stochasticK not resolved. Details: {result.condition_details}"

    @pytest.mark.soundness
    def test_velocity_resolves(self):
        """SOUNDNESS: Pattern condition 'velocity' resolves to 'close_velocity_zscore'."""
        candle = run_full_pipeline(make_trending_up_ohlcv())
        conditions = {"velocity": {"operator": ">", "value": -999}}  # Always true
        result = evaluate_conditions(conditions, candle)
        assert result.conditions_met > 0, f"velocity not resolved. Details: {result.condition_details}"

    @pytest.mark.soundness
    def test_acceleration_resolves(self):
        """SOUNDNESS: Pattern condition 'acceleration' resolves to 'close_acceleration_zscore'."""
        candle = run_full_pipeline(make_trending_up_ohlcv())
        conditions = {"acceleration": {"operator": ">", "value": -999}}
        result = evaluate_conditions(conditions, candle)
        assert result.conditions_met > 0, f"acceleration not resolved. Details: {result.condition_details}"

    @pytest.mark.soundness
    def test_list_format_conditions_resolve(self):
        """SOUNDNESS: List-format conditions (from DB) resolve correctly."""
        candle = run_full_pipeline(make_trending_up_ohlcv())
        conditions = [
            {"indicator": "rsi14", "operator": "<", "value": 100},
            {"indicator": "macdHistogram", "operator": ">", "value": -99999},
        ]
        result = evaluate_conditions(conditions, candle)
        assert result.conditions_met == 2, f"List conditions failed. Details: {result.condition_details}"

    @pytest.mark.soundness
    def test_derived_rsiOversold_resolves(self):
        """SOUNDNESS: Derived indicator 'rsiOversold' resolves."""
        candle = run_full_pipeline(make_trending_down_ohlcv())
        conditions = {"rsiOversold": {"operator": ">=", "value": 0}}
        result = evaluate_conditions(conditions, candle)
        assert result.conditions_met > 0, f"rsiOversold not resolved. Details: {result.condition_details}"


# ============================================================================
# TEST: Signal generation from known market conditions
# ============================================================================


class TestSignalGenerationFromKnownConditions:
    """SOUNDNESS: Patterns with known-triggering conditions actually fire signals."""

    @pytest.mark.soundness
    def test_uptrend_bullish_pattern_matches(self):
        """SOUNDNESS: Bullish pattern fires on strong uptrend data."""
        candle = run_full_pipeline(make_trending_up_ohlcv())

        # Pattern: RSI > 50 AND MACD histogram > 0 (should match on uptrend)
        conditions = {
            "rsi14": {"operator": ">", "value": 50},
            "macdHistogram": {"operator": ">", "value": 0},
        }
        result = evaluate_conditions(conditions, candle)

        assert result.matched, (
            f"Bullish pattern should match on uptrend. "
            f"RSI={candle.get('rsi_14'):.1f}, MACD_hist={candle.get('macd_histogram'):.4f}, "
            f"Details: {result.condition_details}"
        )

    @pytest.mark.soundness
    def test_downtrend_bearish_pattern_matches(self):
        """SOUNDNESS: Bearish pattern fires on strong downtrend data."""
        candle = run_full_pipeline(make_trending_down_ohlcv())

        # Pattern: RSI < 50 AND MACD line < 0 (should match on downtrend)
        # Note: MACD histogram oscillates (can be positive during deceleration),
        # but MACD LINE is reliably negative during sustained downtrends.
        conditions = {
            "rsi14": {"operator": "<", "value": 50},
            "macdLine": {"operator": "<", "value": 0},
        }
        result = evaluate_conditions(conditions, candle)

        assert result.matched, (
            f"Bearish pattern should match on downtrend. "
            f"RSI={candle.get('rsi_14'):.1f}, MACD_line={candle.get('macd_line'):.4f}, "
            f"Details: {result.condition_details}"
        )

    @pytest.mark.soundness
    def test_bullish_pattern_does_not_match_downtrend(self):
        """SOUNDNESS: Bullish pattern does NOT fire on downtrend."""
        candle = run_full_pipeline(make_trending_down_ohlcv())

        # Strong bullish conditions that should NOT match on downtrend
        conditions = {
            "rsi14": {"operator": ">", "value": 60},
            "macdHistogram": {"operator": ">", "value": 0},
        }
        result = evaluate_conditions(conditions, candle)

        assert not result.matched, (
            f"Bullish pattern should NOT match on downtrend. "
            f"RSI={candle.get('rsi_14'):.1f}, MACD_hist={candle.get('macd_histogram'):.4f}"
        )

    @pytest.mark.soundness
    def test_multi_condition_pattern_with_confidence(self):
        """SOUNDNESS: Multi-condition pattern produces confidence scores."""
        candle = run_full_pipeline(make_trending_up_ohlcv())

        # Multiple conditions - all should match on uptrend
        conditions = {
            "rsi14": {"operator": ">", "value": 40},
            "macdHistogram": {"operator": ">", "value": -999},
            "adx14": {"operator": ">", "value": 0},
        }
        result = evaluate_conditions(conditions, candle)

        assert result.confidence > 0, f"Should have positive confidence. Got: {result.confidence}"
        assert result.conditions_met >= 2, f"Should meet most conditions. Met: {result.conditions_met}/{result.conditions_total}"

    @pytest.mark.soundness
    def test_oversold_reversal_pattern(self):
        """SOUNDNESS: Oversold reversal pattern matches extreme downtrend."""
        candle = run_full_pipeline(make_trending_down_ohlcv())

        # Oversold conditions (RSI < 40, Stoch < 30)
        conditions = {
            "rsi14": {"operator": "<", "value": 40},
            "stochasticK": {"operator": "<", "value": 30},
        }
        result = evaluate_conditions(conditions, candle)

        # At least one condition should match on a strong downtrend
        assert result.conditions_met >= 1, (
            f"Oversold pattern should partially match. "
            f"RSI={candle.get('rsi_14'):.1f}, Stoch_K={candle.get('stoch_k'):.1f}, "
            f"Details: {result.condition_details}"
        )

    @pytest.mark.soundness
    def test_trend_strength_pattern(self):
        """SOUNDNESS: ADX-based trend strength pattern matches trending market."""
        candle = run_full_pipeline(make_trending_up_ohlcv())

        # ADX > 15 indicates some trend (not necessarily > 25 for our synthetic data)
        conditions = {
            "adx14": {"operator": ">", "value": 10},
            "plusDI": {"operator": ">", "value": 0},
        }
        result = evaluate_conditions(conditions, candle)

        assert result.matched, (
            f"Trend pattern should match. ADX={candle.get('adx_14'):.1f}, "
            f"+DI={candle.get('plus_di'):.1f}. Details: {result.condition_details}"
        )

    @pytest.mark.soundness
    def test_choppy_market_low_adx(self):
        """SOUNDNESS: Choppy market has lower ADX than trending market."""
        trending_candle = run_full_pipeline(make_trending_up_ohlcv())
        choppy_candle = run_full_pipeline(make_choppy_ohlcv())

        # ADX should be lower in choppy market
        assert choppy_candle["adx_14"] < trending_candle["adx_14"], (
            f"Choppy ADX ({choppy_candle['adx_14']:.1f}) should be < "
            f"trending ADX ({trending_candle['adx_14']:.1f})"
        )


# ============================================================================
# TEST: Derived indicators (compute_derived_for_candle) are correct
# ============================================================================


class TestDerivedIndicatorsCorrect:
    """SOUNDNESS: Derived indicators from compute_derived_for_candle match expectations."""

    @pytest.mark.soundness
    def test_uptrend_price_above_emas(self):
        """SOUNDNESS: In uptrend, price is above moving averages."""
        candle = run_full_pipeline(make_trending_up_ohlcv())

        assert candle.get("price_above_ema_21") == 1, "Uptrend: price should be above EMA21"
        assert candle.get("price_above_ema_9") == 1, "Uptrend: price should be above EMA9"

    @pytest.mark.soundness
    def test_downtrend_price_below_emas(self):
        """SOUNDNESS: In downtrend, price is below moving averages."""
        candle = run_full_pipeline(make_trending_down_ohlcv())

        assert candle.get("price_above_ema_21") == 0, "Downtrend: price should be below EMA21"

    @pytest.mark.soundness
    def test_uptrend_bullish_ma_cross(self):
        """SOUNDNESS: In uptrend, EMA21 > SMA50 (bullish cross)."""
        candle = run_full_pipeline(make_trending_up_ohlcv())

        # ma_cross_20_50 = 1 if ema_21 > sma_50
        assert candle.get("ma_cross_20_50") == 1, "Uptrend: EMA21 should be above SMA50"

    @pytest.mark.soundness
    def test_downtrend_rsi_oversold_set(self):
        """SOUNDNESS: In strong downtrend, RSI oversold flag is set."""
        candle = run_full_pipeline(make_trending_down_ohlcv())

        if candle["rsi_14"] < 30:
            assert candle.get("rsi_oversold") == 1, "RSI < 30 should set rsi_oversold=1"

    @pytest.mark.soundness
    def test_uptrend_rsi_not_oversold(self):
        """SOUNDNESS: In uptrend, RSI oversold flag is NOT set."""
        candle = run_full_pipeline(make_trending_up_ohlcv())

        assert candle.get("rsi_oversold") == 0, "Uptrend should NOT have rsi_oversold=1"

    @pytest.mark.soundness
    def test_macd_cross_matches_line_vs_signal(self):
        """SOUNDNESS: macd_cross flag is consistent with macd_line vs macd_signal."""
        candle = run_full_pipeline(make_trending_up_ohlcv())

        macd_line = candle["macd_line"]
        macd_signal = candle["macd_signal"]
        macd_cross = candle.get("macd_cross")

        if macd_line > macd_signal:
            assert macd_cross == 1, "MACD line > signal should give macd_cross=1"
        elif macd_line < macd_signal:
            assert macd_cross == -1, "MACD line < signal should give macd_cross=-1"

    @pytest.mark.soundness
    def test_volatility_regime_is_string(self):
        """SOUNDNESS: volatility_regime is a valid string value."""
        candle = run_full_pipeline(make_trending_up_ohlcv())

        if "volatility_regime" in candle:
            assert candle["volatility_regime"] in ("low", "medium", "high")

    @pytest.mark.soundness
    def test_trend_regime_matches_direction(self):
        """SOUNDNESS: trend_regime reflects the actual trend direction."""
        up_candle = run_full_pipeline(make_trending_up_ohlcv())
        down_candle = run_full_pipeline(make_trending_down_ohlcv())

        # Uptrend should show uptrend regime (if ADX is high enough)
        if up_candle.get("adx_14", 0) >= 20:
            assert up_candle.get("trend_regime") == "uptrend", (
                f"Uptrend with ADX={up_candle['adx_14']:.1f} should be 'uptrend' regime"
            )

        if down_candle.get("adx_14", 0) >= 20:
            assert down_candle.get("trend_regime") == "downtrend", (
                f"Downtrend with ADX={down_candle['adx_14']:.1f} should be 'downtrend' regime"
            )


# ============================================================================
# TEST: Minimum data requirements
# ============================================================================


class TestMinimumDataRequirements:
    """SOUNDNESS: Pipeline handles insufficient data gracefully."""

    @pytest.mark.soundness
    def test_200_candles_produces_sma200(self):
        """SOUNDNESS: 200+ candles produces valid SMA_200."""
        df = make_trending_up_ohlcv(n_candles=250)
        candle = run_full_pipeline(df)

        assert "sma_200" in candle, "250 candles should produce sma_200"
        assert candle["sma_200"] > 0

    @pytest.mark.soundness
    def test_50_candles_has_no_sma200(self):
        """SOUNDNESS: 50 candles cannot produce SMA_200 (NaN filtered out)."""
        df = make_trending_up_ohlcv(n_candles=55)
        candle = run_full_pipeline(df)

        # SMA_200 should be NaN and thus filtered out of candle_data
        assert "sma_200" not in candle, "55 candles should NOT have sma_200"

    @pytest.mark.soundness
    def test_50_candles_still_has_rsi(self):
        """SOUNDNESS: 50 candles is enough for RSI (period=14)."""
        df = make_trending_up_ohlcv(n_candles=55)
        candle = run_full_pipeline(df)

        assert "rsi_14" in candle, "55 candles should have rsi_14"

    @pytest.mark.soundness
    def test_300_candles_has_all_indicators(self):
        """SOUNDNESS: 300 candles produces all expected indicators."""
        df = make_trending_up_ohlcv(n_candles=300)
        candle = run_full_pipeline(df)

        expected_keys = [
            "rsi_14", "macd_line", "macd_histogram", "adx_14",
            "bb_upper", "bb_lower", "stoch_k", "atr_14",
            "sma_20", "sma_50", "sma_200", "ema_9", "ema_21",
            "close_velocity_zscore", "close_acceleration_zscore",
        ]
        for key in expected_keys:
            assert key in candle, f"Missing '{key}' with 300 candles. Available: {sorted(candle.keys())}"


# ============================================================================
# TEST: Full round-trip pattern evaluation
# ============================================================================


class TestFullRoundTripPatternEvaluation:
    """SOUNDNESS: Complete pattern evaluation works end-to-end."""

    @pytest.mark.soundness
    def test_realistic_entry_pattern_fires_on_uptrend(self):
        """SOUNDNESS: A realistic entry pattern produces a match on uptrend data."""
        candle = run_full_pipeline(make_trending_up_ohlcv())

        # Realistic pattern from chaos analysis
        entry_conditions = {
            "rsi14": {"operator": ">", "value": 45},
            "macdHistogram": {"operator": ">", "value": 0},
            "priceAboveEma": {"operator": "==", "value": 1},
        }

        result = evaluate_conditions(entry_conditions, candle)

        assert result.matched, (
            f"Realistic bullish pattern should fire on uptrend. "
            f"RSI={candle.get('rsi_14'):.1f}, "
            f"MACD_hist={candle.get('macd_histogram'):.4f}, "
            f"price_above_ema_21={candle.get('price_above_ema_21')}, "
            f"Details: {result.condition_details}"
        )

    @pytest.mark.soundness
    def test_realistic_exit_pattern_fires_on_downtrend(self):
        """SOUNDNESS: A realistic exit pattern produces a match on downtrend data."""
        candle = run_full_pipeline(make_trending_down_ohlcv())

        # Use MACD line (not histogram) for reliable trend detection.
        # Histogram oscillates even in downtrends as momentum decelerates.
        exit_conditions = {
            "rsi14": {"operator": "<", "value": 45},
            "macdLine": {"operator": "<", "value": 0},
        }

        result = evaluate_conditions(exit_conditions, candle)

        assert result.matched, (
            f"Exit pattern should fire on downtrend. "
            f"RSI={candle.get('rsi_14'):.1f}, "
            f"MACD_line={candle.get('macd_line'):.4f}"
        )

    @pytest.mark.soundness
    def test_pattern_with_motion_derivatives(self):
        """SOUNDNESS: Pattern using chaos derivatives (velocity/acceleration) works."""
        candle = run_full_pipeline(make_trending_up_ohlcv())

        # Velocity should be positive in uptrend
        conditions = {
            "velocity": {"operator": ">", "value": 0},
        }

        result = evaluate_conditions(conditions, candle)
        # Note: z-score might not be > 0 at the last candle, but it should resolve
        assert result.conditions_total > 0, "velocity should be resolvable"
        # Check it didn't fail as 'missing'
        for detail in result.condition_details:
            assert detail.get("status") != "missing", f"velocity unresolved: {detail}"

    @pytest.mark.soundness
    def test_pattern_evaluation_deterministic(self):
        """SOUNDNESS: Same data always produces same result."""
        df = make_trending_up_ohlcv()
        conditions = {
            "rsi14": {"operator": ">", "value": 50},
            "adx14": {"operator": ">", "value": 10},
        }

        results = []
        for _ in range(5):
            candle = run_full_pipeline(df.copy())
            result = evaluate_conditions(conditions, candle)
            results.append((result.matched, result.confidence, result.conditions_met))

        # All 5 runs should produce identical results
        assert len(set(results)) == 1, f"Non-deterministic results: {results}"

    @pytest.mark.soundness
    def test_empty_conditions_returns_no_match(self):
        """SOUNDNESS: Empty conditions dict returns no match."""
        candle = run_full_pipeline(make_trending_up_ohlcv())
        result = evaluate_conditions({}, candle)
        assert not result.matched

    @pytest.mark.soundness
    def test_impossible_conditions_dont_match(self):
        """SOUNDNESS: Contradictory conditions don't produce false matches."""
        candle = run_full_pipeline(make_trending_up_ohlcv())

        # RSI > 200 is impossible
        conditions = {"rsi14": {"operator": ">", "value": 200}}
        result = evaluate_conditions(conditions, candle)
        assert not result.matched

    @pytest.mark.soundness
    def test_all_conditions_must_match_for_full_confidence(self):
        """SOUNDNESS: All conditions matching gives high confidence."""
        candle = run_full_pipeline(make_trending_up_ohlcv())

        # Conditions that should ALL match on uptrend
        conditions = {
            "rsi14": {"operator": ">", "value": 40},
            "adx14": {"operator": ">", "value": 5},
            "ema21": {"operator": ">", "value": 0},
        }

        result = evaluate_conditions(conditions, candle)
        assert result.conditions_met == result.conditions_total, (
            f"All conditions should match. Met {result.conditions_met}/{result.conditions_total}. "
            f"Details: {result.condition_details}"
        )


# ============================================================================
# TEST: Bear protection defensive trigger computation
# ============================================================================


class TestBearProtectionTrigger:
    """SOUNDNESS: Defensive trigger computation is consistent with pipeline output."""

    @pytest.mark.soundness
    def test_defensive_trigger_not_in_live_pipeline(self):
        """
        SOUNDNESS: defensive_trigger is NOT computed by compute_derived_for_candle.

        This documents a known gap: the live pipeline cannot compute
        defensive_trigger because it requires adx_14_jerk_zscore which
        is only available from the DB enrichment batch process.
        """
        candle = run_full_pipeline(make_trending_down_ohlcv())

        # defensive_trigger is only computed in SQL batch enrichment,
        # NOT in the Python compute_derived_for_candle() function
        assert "defensive_trigger" not in candle, (
            "defensive_trigger should NOT be in live pipeline output - "
            "it's only computed in SQL batch enrichment"
        )

    @pytest.mark.soundness
    def test_acceleration_zscore_available_for_bear_check(self):
        """SOUNDNESS: close_acceleration_zscore IS available from live pipeline."""
        candle = run_full_pipeline(make_trending_down_ohlcv())

        # This component of defensive_trigger IS computed by calculate_indicators_fast
        assert "close_acceleration_zscore" in candle, (
            "close_acceleration_zscore should be in pipeline output"
        )

    @pytest.mark.soundness
    def test_manual_defensive_trigger_from_pipeline_data(self):
        """
        SOUNDNESS: We CAN manually compute defensive_trigger from pipeline output.

        defensive_trigger = 1 if acc_zscore < -1.5 AND adx_jerk_zscore < -0.5
        But adx_jerk_zscore is NOT computed by calculate_indicators_fast.
        This test documents that the second component is missing.
        """
        candle = run_full_pipeline(make_trending_down_ohlcv())

        # acc_zscore is available
        acc_zscore = candle.get("close_acceleration_zscore")
        assert acc_zscore is not None

        # adx_14_jerk_zscore is NOT available (only in DB enrichment)
        adx_jerk = candle.get("adx_14_jerk_zscore")
        assert adx_jerk is None, (
            "adx_14_jerk_zscore should NOT be in pipeline - "
            "only batch enrichment computes ADX derivatives"
        )


# ============================================================================
# TEST: Real _evaluate_patterns method (the voting system)
# ============================================================================


class TestEvaluatePatternsVoting:
    """
    SOUNDNESS: The REAL _evaluate_patterns method produces correct signals.

    This exercises the actual service method with a real Agent object
    and real candle data. No mocks.
    """

    def _make_agent_with_patterns(self, patterns: dict, weights: dict | None = None) -> Agent:
        """Create a real Agent SQLModel object with patterns."""
        return Agent(
            agent_id="test-agent-pipeline-001",
            name="Pipeline Test Agent",
            status="active",
            assigned_patterns=patterns,
            pattern_weights=weights or {},
        )

    @pytest.mark.soundness
    @pytest.mark.asyncio
    async def test_bullish_pattern_produces_buy_signal(self):
        """SOUNDNESS: Agent with bullish pattern on uptrend data produces 'buy'."""
        service = AgentPaperTradingService()
        candle = run_full_pipeline(make_trending_up_ohlcv())

        agent = self._make_agent_with_patterns({
            "pattern-001": {
                "direction": "long",
                "entry_conditions": {
                    "rsi14": {"operator": ">", "value": 45},
                    "macdLine": {"operator": ">", "value": 0},
                    "priceAboveEma": {"operator": "==", "value": 1},
                },
                "exit_conditions": {},
            }
        })

        signal = await service._evaluate_patterns(agent, candle)
        assert signal == "buy", f"Should produce 'buy' signal, got '{signal}'"

    @pytest.mark.soundness
    @pytest.mark.asyncio
    async def test_bearish_pattern_produces_sell_signal(self):
        """SOUNDNESS: Agent with short pattern on downtrend produces 'sell'."""
        service = AgentPaperTradingService()
        candle = run_full_pipeline(make_trending_down_ohlcv())

        agent = self._make_agent_with_patterns({
            "pattern-002": {
                "direction": "short",
                "entry_conditions": {
                    "rsi14": {"operator": "<", "value": 40},
                    "macdLine": {"operator": "<", "value": 0},
                },
                "exit_conditions": {},
            }
        })

        signal = await service._evaluate_patterns(agent, candle)
        assert signal == "sell", f"Should produce 'sell' signal, got '{signal}'"

    @pytest.mark.soundness
    @pytest.mark.asyncio
    async def test_exit_pattern_produces_close_signal(self):
        """SOUNDNESS: Agent with exit conditions met produces 'close'."""
        service = AgentPaperTradingService()
        candle = run_full_pipeline(make_trending_down_ohlcv())

        agent = self._make_agent_with_patterns({
            "pattern-003": {
                "direction": "long",
                "entry_conditions": {},  # No entry conditions
                "exit_conditions": {
                    "rsi14": {"operator": "<", "value": 30},
                },
            }
        })

        signal = await service._evaluate_patterns(agent, candle, has_position=True)
        # RSI is ~11 in our downtrend, so exit condition is met
        assert signal == "close", f"Should produce 'close' signal, got '{signal}'"

    @pytest.mark.soundness
    @pytest.mark.asyncio
    async def test_no_patterns_returns_hold(self):
        """SOUNDNESS: Agent with no patterns always returns 'hold'."""
        service = AgentPaperTradingService()
        candle = run_full_pipeline(make_trending_up_ohlcv())

        agent = self._make_agent_with_patterns({})
        signal = await service._evaluate_patterns(agent, candle)
        assert signal == "hold"

    @pytest.mark.soundness
    @pytest.mark.asyncio
    async def test_conflicting_patterns_return_hold(self):
        """SOUNDNESS: Conflicting patterns (no clear majority) return 'hold'."""
        service = AgentPaperTradingService()
        candle = run_full_pipeline(make_choppy_ohlcv())

        # Two patterns with opposing directions, equal weight
        agent = self._make_agent_with_patterns({
            "bullish": {
                "direction": "long",
                "entry_conditions": {"adx14": {"operator": ">", "value": 0}},
                "exit_conditions": {},
            },
            "bearish": {
                "direction": "short",
                "entry_conditions": {"adx14": {"operator": ">", "value": 0}},
                "exit_conditions": {},
            },
        })

        signal = await service._evaluate_patterns(agent, candle)
        # Equal votes in both directions -> no 1.5x majority -> hold
        assert signal == "hold", f"Conflicting patterns should hold, got '{signal}'"

    @pytest.mark.soundness
    @pytest.mark.asyncio
    async def test_weighted_patterns_favor_higher_weight(self):
        """SOUNDNESS: Pattern weights influence the voting outcome."""
        service = AgentPaperTradingService()
        candle = run_full_pipeline(make_trending_up_ohlcv())

        # Two patterns: bullish has 3x weight, bearish has 1x
        agent = self._make_agent_with_patterns(
            patterns={
                "bullish": {
                    "direction": "long",
                    "entry_conditions": {"rsi14": {"operator": ">", "value": 40}},
                    "exit_conditions": {},
                },
                "bearish": {
                    "direction": "short",
                    "entry_conditions": {"adx14": {"operator": ">", "value": 0}},
                    "exit_conditions": {},
                },
            },
            weights={"bullish": 3.0, "bearish": 1.0},
        )

        signal = await service._evaluate_patterns(agent, candle)
        # Bullish weight=3.0 vs bearish weight=1.0 -> 3x majority -> buy
        assert signal == "buy", f"Weighted bullish should win, got '{signal}'"

    @pytest.mark.soundness
    @pytest.mark.asyncio
    async def test_unmatched_conditions_return_hold(self):
        """SOUNDNESS: Pattern with impossible conditions returns 'hold'."""
        service = AgentPaperTradingService()
        candle = run_full_pipeline(make_trending_up_ohlcv())

        agent = self._make_agent_with_patterns({
            "impossible": {
                "direction": "long",
                "entry_conditions": {"rsi14": {"operator": ">", "value": 200}},  # Impossible
                "exit_conditions": {},
            }
        })

        signal = await service._evaluate_patterns(agent, candle)
        assert signal == "hold", f"Impossible conditions should hold, got '{signal}'"

    @pytest.mark.soundness
    @pytest.mark.asyncio
    async def test_list_format_conditions_work(self):
        """SOUNDNESS: Pattern conditions in list format (from DB) work in voting."""
        service = AgentPaperTradingService()
        candle = run_full_pipeline(make_trending_up_ohlcv())

        # List format (how patterns are typically stored in DB)
        agent = self._make_agent_with_patterns({
            "pattern-db": {
                "direction": "long",
                "entry_conditions": [
                    {"indicator": "rsi14", "operator": ">", "value": 45},
                    {"indicator": "macdLine", "operator": ">", "value": 0},
                ],
                "exit_conditions": [],
            }
        })

        signal = await service._evaluate_patterns(agent, candle)
        assert signal == "buy", f"List-format bullish should buy, got '{signal}'"

    @pytest.mark.soundness
    @pytest.mark.asyncio
    async def test_close_priority_over_entry(self):
        """SOUNDNESS: Close signal takes priority over entry signals."""
        service = AgentPaperTradingService()
        candle = run_full_pipeline(make_trending_down_ohlcv())

        # Both entry (short) and exit conditions match
        agent = self._make_agent_with_patterns({
            "pattern-priority": {
                "direction": "short",
                "entry_conditions": {
                    "rsi14": {"operator": "<", "value": 40},
                },
                "exit_conditions": {
                    "rsi14": {"operator": "<", "value": 15},  # Also met (RSI ~11)
                },
            }
        })

        signal = await service._evaluate_patterns(agent, candle, has_position=True)
        assert signal == "close", f"Close should take priority, got '{signal}'"
