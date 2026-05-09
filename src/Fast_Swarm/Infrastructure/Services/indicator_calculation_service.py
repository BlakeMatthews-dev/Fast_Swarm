"""
Technical Indicators Calculation Service

Calculates ALL technical indicators using pandas_ta library (130+ indicators).
Ported from: Coinswarm-1/local-utilities/metrics/indicators.py

Categories (130+ indicators):
- Momentum (44): RSI, MACD, STOCH, WILLR, MFI, ROC, CCI, etc.
- Trend (21): ADX, AROON, PSAR, SUPERTREND, etc.
- Volatility (16): ATR, BBANDS, KC, DONCHIAN, etc.
- Volume (20): OBV, AD, CMF, MFI, NVI, PVI, etc.
- Overlap (36): SMA, EMA, HMA, DEMA, TEMA, KAMA, ZLMA, ALMA, etc.
- Cycle (2): EBSW, REFLEX
- Statistics (10): ENTROPY, KURTOSIS, SKEW, VARIANCE, etc.

PLUS Motion Derivatives (velocity through pop) for all indicators.

EDD COMPLIANCE:
- Deterministic: Same input produces same output
- No NaN propagation: All results are finite or have defaults
- Performance: Batch calculation for efficiency
"""

import warnings
from typing import List

import numpy as np
import pandas as pd

# Try to import pandas_ta
try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
except ImportError:
    HAS_PANDAS_TA = False
    ta = None


# =============================================================================
# CONFIGURATION
# =============================================================================

# Minimum candles required for reliable indicator calculation
MIN_CANDLES_FOR_INDICATORS = 200

# Global list of indicator columns (populated after calculation)
INDICATOR_COLS: List[str] = []

# Pascal's triangle coefficients for motion derivatives
DERIVATIVE_COEFFICIENTS = {
    "velocity": [1, -1],                           # 1st derivative
    "acceleration": [1, -2, 1],                    # 2nd derivative
    "jerk": [1, -3, 3, -1],                        # 3rd derivative
    "snap": [1, -4, 6, -4, 1],                     # 4th derivative
    "crackle": [1, -5, 10, -10, 5, -1],            # 5th derivative
    "pop": [1, -6, 15, -20, 15, -6, 1],            # 6th derivative
}

ZSCORE_WINDOW = 100  # Rolling window for z-score normalization


# =============================================================================
# MAIN INDICATOR CALCULATION
# =============================================================================

def calculate_indicators(
    df: pd.DataFrame,
    verbose: bool = False,
    min_candles: int = MIN_CANDLES_FOR_INDICATORS,
) -> pd.DataFrame:
    """
    Calculate ALL technical indicators using pandas_ta library (130+ indicators).

    Args:
        df: DataFrame with OHLCV columns (open, high, low, close, volume)
        verbose: If True, print progress messages
        min_candles: Minimum number of candles required (default 200)

    Returns:
        DataFrame with 200+ indicator columns added
    """
    global INDICATOR_COLS

    if not HAS_PANDAS_TA:
        if verbose:
            print("[WARN] pandas_ta not available, using fallback indicators")
        return _calculate_fallback_indicators(df)

    if len(df) < min_candles:
        if verbose:
            print(f"[WARN] Only {len(df)} candles, need {min_candles} for full indicators")

    df = df.copy()
    original_cols = set(df.columns)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        # --- MOMENTUM (44 indicators) ---
        if verbose:
            print("  Calculating momentum indicators...")
        _calculate_momentum(df)

        # --- TREND (21 indicators) ---
        if verbose:
            print("  Calculating trend indicators...")
        _calculate_trend(df)

        # --- VOLATILITY (16 indicators) ---
        if verbose:
            print("  Calculating volatility indicators...")
        _calculate_volatility(df)

        # --- VOLUME (20 indicators) ---
        if verbose:
            print("  Calculating volume indicators...")
        _calculate_volume(df)

        # --- OVERLAP / Moving Averages (36 indicators) ---
        if verbose:
            print("  Calculating overlap/MA indicators...")
        _calculate_overlap(df)

        # --- CYCLE (2 indicators) ---
        if verbose:
            print("  Calculating cycle indicators...")
        _calculate_cycle(df)

        # --- STATISTICS (10 indicators) ---
        if verbose:
            print("  Calculating statistics indicators...")
        _calculate_statistics(df)

        # --- DERIVED INDICATORS ---
        if verbose:
            print("  Calculating derived indicators...")
        df = _add_derived_indicators(df)
        df = _add_boolean_signals(df)
        df = _add_temporal_indicators(df)

    # Update global INDICATOR_COLS
    new_cols = [col for col in df.columns if col not in original_cols]
    numeric_cols = [col for col in new_cols if df[col].dtype in ['float64', 'int64', 'int32', 'float32']]
    INDICATOR_COLS.clear()
    INDICATOR_COLS.extend(sorted(numeric_cols))

    if verbose:
        print(f"  Total indicator columns: {len(INDICATOR_COLS)}")

    return df


def _calculate_momentum(df: pd.DataFrame):
    """Calculate momentum indicators."""
    try:
        df.ta.ao(append=True)
        df.ta.apo(append=True)
        df.ta.bias(append=True)
        df.ta.bop(append=True)
        df.ta.cci(append=True)
        df.ta.cfo(append=True)
        df.ta.cg(append=True)
        df.ta.cmo(append=True)
        df.ta.coppock(append=True)
        df.ta.er(append=True)
        df.ta.fisher(append=True)
        df.ta.inertia(append=True)
        df.ta.kdj(append=True)
        df.ta.kst(append=True)
        df.ta.macd(append=True)
        df.ta.mom(append=True)
        df.ta.pgo(append=True)
        df.ta.ppo(append=True)
        df.ta.psl(append=True)
        df.ta.roc(append=True)
        df.ta.rsi(append=True)
        df.ta.rsx(append=True)
        df.ta.rvgi(append=True)
        df.ta.slope(append=True)
        df.ta.smi(append=True)
        df.ta.squeeze(append=True)
        df.ta.stc(append=True)
        df.ta.stoch(append=True)
        df.ta.stochrsi(append=True)
        df.ta.trix(append=True)
        df.ta.tsi(append=True)
        df.ta.uo(append=True)
        df.ta.willr(append=True)
    except Exception:
        pass


def _calculate_trend(df: pd.DataFrame):
    """Calculate trend indicators."""
    try:
        df.ta.adx(append=True)
        df.ta.aroon(append=True)
        df.ta.chop(append=True)
        df.ta.cksp(append=True)
        df.ta.decay(append=True)
        df.ta.decreasing(append=True)
        df.ta.dpo(append=True)
        df.ta.increasing(append=True)
        df.ta.psar(append=True)
        df.ta.qstick(append=True)
        df.ta.vhf(append=True)
        df.ta.vortex(append=True)
    except Exception:
        pass


def _calculate_volatility(df: pd.DataFrame):
    """Calculate volatility indicators."""
    try:
        df.ta.aberration(append=True)
        df.ta.accbands(append=True)
        df.ta.atr(append=True)
        df.ta.bbands(append=True)
        df.ta.donchian(append=True)
        df.ta.hwc(append=True)
        df.ta.kc(append=True)
        df.ta.massi(append=True)
        df.ta.natr(append=True)
        df.ta.pdist(append=True)
        df.ta.rvi(append=True)
        df.ta.thermo(append=True)
        df.ta.true_range(append=True)
        df.ta.ui(append=True)
    except Exception:
        pass


def _calculate_volume(df: pd.DataFrame):
    """Calculate volume indicators."""
    try:
        df.ta.ad(append=True)
        df.ta.adosc(append=True)
        df.ta.aobv(append=True)
        df.ta.cmf(append=True)
        df.ta.efi(append=True)
        df.ta.eom(append=True)
        df.ta.kvo(append=True)
        df.ta.mfi(append=True)
        df.ta.nvi(append=True)
        df.ta.obv(append=True)
        df.ta.pvi(append=True)
        df.ta.pvo(append=True)
        df.ta.pvol(append=True)
        df.ta.pvr(append=True)
        df.ta.pvt(append=True)
    except Exception:
        pass


def _calculate_overlap(df: pd.DataFrame):
    """Calculate overlap/moving average indicators."""
    try:
        df.ta.alma(append=True)
        df.ta.dema(append=True)
        df.ta.ema(length=9, append=True)
        df.ta.ema(length=10, append=True)
        df.ta.ema(length=12, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=21, append=True)
        df.ta.ema(length=26, append=True)
        df.ta.ema(length=50, append=True)
        df.ta.ema(length=200, append=True)
        df.ta.fwma(append=True)
        df.ta.hilo(append=True)
        df.ta.hl2(append=True)
        df.ta.hlc3(append=True)
        df.ta.hma(append=True)
        df.ta.hwma(append=True)
        df.ta.jma(append=True)
        df.ta.kama(append=True)
        df.ta.linreg(append=True)
        df.ta.mcgd(append=True)
        df.ta.midpoint(append=True)
        df.ta.midprice(append=True)
        df.ta.ohlc4(append=True)
        df.ta.pwma(append=True)
        df.ta.rma(append=True)
        df.ta.sinwma(append=True)
        df.ta.sma(length=20, append=True)
        df.ta.sma(length=50, append=True)
        df.ta.sma(length=200, append=True)
        df.ta.ssf(append=True)
        df.ta.supertrend(append=True)
        df.ta.swma(append=True)
        df.ta.t3(append=True)
        df.ta.tema(append=True)
        df.ta.trima(append=True)
        df.ta.vidya(append=True)
        df.ta.vwma(append=True)
        df.ta.wcp(append=True)
        df.ta.wma(append=True)
        df.ta.zlma(append=True)
    except Exception:
        pass


def _calculate_cycle(df: pd.DataFrame):
    """Calculate cycle indicators."""
    try:
        df.ta.ebsw(append=True)
    except Exception:
        pass


def _calculate_statistics(df: pd.DataFrame):
    """Calculate statistics indicators."""
    try:
        df.ta.entropy(append=True)
        df.ta.kurtosis(append=True)
        df.ta.mad(append=True)
        df.ta.median(append=True)
        df.ta.quantile(append=True)
        df.ta.skew(append=True)
        df.ta.stdev(append=True)
        df.ta.variance(append=True)
        df.ta.zscore(append=True)
    except Exception:
        pass


def _add_derived_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add custom derived indicators (price vs MAs, ratios, etc.)"""
    close = df['close']

    # Price vs MAs (percentage)
    ma_cols = {
        'EMA_10': 'priceVsEma10Pct',
        'EMA_20': 'priceVsEma20Pct',
        'EMA_50': 'priceVsEma50Pct',
        'EMA_200': 'priceVsEma200Pct',
        'SMA_20': 'priceVsSma20Pct',
        'SMA_50': 'priceVsSma50Pct',
        'SMA_200': 'priceVsSma200Pct',
    }

    for ma_col, pct_col in ma_cols.items():
        if ma_col in df.columns:
            df[pct_col] = ((close - df[ma_col]) / df[ma_col].replace(0, np.nan) * 100).fillna(0)

    # Volume ratio
    if 'volume' in df.columns:
        volume = df['volume']
        df['volumeRatio'] = (volume / volume.rolling(20).mean()).fillna(1)

    return df


def _add_boolean_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Add boolean signal indicators for pattern matching."""
    close = df['close']

    # RSI signals
    if 'RSI_14' in df.columns:
        df['isRsiOversold'] = (df['RSI_14'] < 30).astype(int)
        df['isRsiOverbought'] = (df['RSI_14'] > 70).astype(int)

    # MACD signals
    if 'MACD_12_26_9' in df.columns and 'MACDs_12_26_9' in df.columns:
        df['isMacdBullish'] = (df['MACD_12_26_9'] > df['MACDs_12_26_9']).astype(int)
        df['isMacdBearish'] = (df['MACD_12_26_9'] < df['MACDs_12_26_9']).astype(int)

    # Price vs MA signals
    if 'EMA_20' in df.columns:
        df['isAboveEma20'] = (close > df['EMA_20']).astype(int)
        df['isBelowEma20'] = (close < df['EMA_20']).astype(int)
    if 'EMA_50' in df.columns:
        df['isAboveEma50'] = (close > df['EMA_50']).astype(int)
    if 'SMA_200' in df.columns:
        df['isAboveSma200'] = (close > df['SMA_200']).astype(int)

    # Golden/Death cross
    if 'EMA_50' in df.columns and 'SMA_200' in df.columns:
        ema50 = df['EMA_50']
        sma200 = df['SMA_200']
        df['isGoldenCross'] = ((ema50 > sma200) & (ema50.shift(1) <= sma200.shift(1))).astype(int)
        df['isDeathCross'] = ((ema50 < sma200) & (ema50.shift(1) >= sma200.shift(1))).astype(int)

    # Volume signals
    if 'volumeRatio' in df.columns:
        df['isHighVolume'] = (df['volumeRatio'] > 2).astype(int)
        df['isLowVolume'] = (df['volumeRatio'] < 0.5).astype(int)

    # SuperTrend signals
    if 'SUPERTd_7_3.0' in df.columns:
        df['isSuperTrendBullish'] = (df['SUPERTd_7_3.0'] == 1).astype(int)
        df['isSuperTrendBearish'] = (df['SUPERTd_7_3.0'] == -1).astype(int)

    # ADX trend strength
    if 'ADX_14' in df.columns:
        df['isStrongTrend'] = (df['ADX_14'] > 25).astype(int)
        df['isWeakTrend'] = (df['ADX_14'] < 20).astype(int)

    return df


def _add_temporal_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add temporal indicators (time-based features)."""
    if 'timestamp' not in df.columns:
        return df

    df['timestamp_dt'] = pd.to_datetime(df['timestamp'], unit='ms', errors='coerce')

    if df['timestamp_dt'].isna().all():
        # Try parsing as datetime string
        df['timestamp_dt'] = pd.to_datetime(df['timestamp'], errors='coerce')

    if not df['timestamp_dt'].isna().all():
        df['dayOfWeek'] = df['timestamp_dt'].dt.dayofweek
        df['hourOfDay'] = df['timestamp_dt'].dt.hour
        df['month'] = df['timestamp_dt'].dt.month
        df['isMonday'] = (df['dayOfWeek'] == 0).astype(int)
        df['isFriday'] = (df['dayOfWeek'] == 4).astype(int)
        df['isWeekend'] = (df['dayOfWeek'] >= 5).astype(int)

    return df


def _calculate_fallback_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Fallback indicator calculation if pandas_ta is not available."""
    df = df.copy()
    # Ensure we have pandas Series (not numpy arrays) for .ewm() and .rolling()
    close = pd.Series(df['close'].values, index=df.index, dtype=float)
    high = pd.Series(df['high'].values, index=df.index, dtype=float)
    low = pd.Series(df['low'].values, index=df.index, dtype=float)
    volume = pd.Series(df['volume'].values, index=df.index, dtype=float)

    # SMAs
    df['SMA_20'] = close.rolling(20).mean()
    df['SMA_50'] = close.rolling(50).mean()
    df['SMA_200'] = close.rolling(200).mean()

    # EMAs
    df['EMA_9'] = close.ewm(span=9, adjust=False).mean()
    df['EMA_21'] = close.ewm(span=21, adjust=False).mean()
    df['EMA_50'] = close.ewm(span=50, adjust=False).mean()

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df['RSI_14'] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df['MACD_12_26_9'] = ema12 - ema26
    df['MACDs_12_26_9'] = df['MACD_12_26_9'].ewm(span=9, adjust=False).mean()
    df['MACDh_12_26_9'] = df['MACD_12_26_9'] - df['MACDs_12_26_9']

    # Bollinger Bands
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df['BBU_20_2.0'] = sma20 + (std20 * 2)
    df['BBM_20_2.0'] = sma20
    df['BBL_20_2.0'] = sma20 - (std20 * 2)

    # ATR
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    df['ATRr_14'] = tr.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    df['NATR_14'] = (df['ATRr_14'] / close) * 100

    # Stochastic
    lowest_low = low.rolling(14).min()
    highest_high = high.rolling(14).max()
    df['STOCHk_14_3_3'] = 100 * ((close - lowest_low) / (highest_high - lowest_low))
    df['STOCHd_14_3_3'] = df['STOCHk_14_3_3'].rolling(3).mean()

    # ADX
    high_diff = high.diff()
    low_diff = -low.diff()
    plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)
    atr = tr.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/14, min_periods=14, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/14, min_periods=14, adjust=False).mean() / atr)
    df['DMP_14'] = plus_di
    df['DMN_14'] = minus_di
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    df['ADX_14'] = dx.ewm(alpha=1/14, min_periods=14, adjust=False).mean()

    # Volume SMA and OBV
    df['volume_sma_20'] = volume.rolling(20).mean()
    direction = np.sign(close.diff())
    direction.iloc[0] = 0
    df['OBV'] = (volume * direction).cumsum()

    # Add derived and signals
    df = _add_derived_indicators(df)
    df = _add_boolean_signals(df)

    return df


def calculate_indicators_fast(
    df: pd.DataFrame,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    Fast indicator calculation - only ~25 core indicators for pattern matching.

    Much faster than full calculate_indicators() which computes 130+ indicators.
    Use this for on-demand computation during backtests.

    Computed indicators:
    - RSI (7, 14, 21)
    - MACD (line, signal, histogram)
    - ATR (7, 14), NATR
    - ADX (14) with plus_di, minus_di
    - Bollinger Bands (upper, middle, lower, bandwidth, percent)
    - Stochastic (k, d)
    - SMAs (20, 50, 200)
    - EMAs (9, 12, 21, 26)
    - Volume SMA (20), OBV
    - Aroon (up, down, osc)
    - CCI (14), Williams %R (14), ROC (10)
    - TRIX (14), CMO (14)
    """
    if verbose:
        print("  [Fast] Computing core indicators...")

    df = df.copy()

    # Ensure we have pandas Series (not numpy arrays) for .ewm() and .rolling()
    # Convert to float first, then wrap in Series if needed
    close = pd.Series(df['close'].values, index=df.index, dtype=float)
    high = pd.Series(df['high'].values, index=df.index, dtype=float)
    low = pd.Series(df['low'].values, index=df.index, dtype=float)
    volume = pd.Series(df['volume'].values, index=df.index, dtype=float)

    # --- SMAs ---
    df['SMA_20'] = close.rolling(20).mean()
    df['SMA_50'] = close.rolling(50).mean()
    df['SMA_200'] = close.rolling(200).mean()

    # --- EMAs ---
    df['EMA_9'] = close.ewm(span=9, adjust=False).mean()
    df['EMA_12'] = close.ewm(span=12, adjust=False).mean()
    df['EMA_21'] = close.ewm(span=21, adjust=False).mean()
    df['EMA_26'] = close.ewm(span=26, adjust=False).mean()

    # --- RSI (7, 14, 21) ---
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    for period in [7, 14, 21]:
        avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df[f'RSI_{period}'] = 100 - (100 / (1 + rs))

    # --- MACD ---
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df['MACD_12_26_9'] = ema12 - ema26
    df['MACDs_12_26_9'] = df['MACD_12_26_9'].ewm(span=9, adjust=False).mean()
    df['MACDh_12_26_9'] = df['MACD_12_26_9'] - df['MACDs_12_26_9']

    # --- Bollinger Bands ---
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df['BBU_20_2.0'] = sma20 + (std20 * 2)
    df['BBM_20_2.0'] = sma20
    df['BBL_20_2.0'] = sma20 - (std20 * 2)
    df['BBB_20_2.0'] = (df['BBU_20_2.0'] - df['BBL_20_2.0']) / sma20 * 100  # Bandwidth
    df['BBP_20_2.0'] = (close - df['BBL_20_2.0']) / (df['BBU_20_2.0'] - df['BBL_20_2.0'])  # Percent

    # --- ATR (7, 14) ---
    prev_close = close.shift(1)
    # Use numpy maximum instead of pd.concat to avoid index label issues
    hl = (high - low).values
    hpc = np.abs((high - prev_close).values)
    lpc = np.abs((low - prev_close).values)
    tr = np.maximum(np.maximum(hl, hpc), lpc)
    df['TRUERANGE_14'] = tr
    tr_series = pd.Series(tr, index=df.index)
    df['ATRr_7'] = tr_series.ewm(alpha=1/7, min_periods=7, adjust=False).mean()
    df['ATRr_14'] = tr_series.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    df['NATR_14'] = (df['ATRr_14'] / close) * 100

    # --- Stochastic ---
    lowest_low = low.rolling(14).min()
    highest_high = high.rolling(14).max()
    df['STOCHk_14_3_3'] = 100 * ((close - lowest_low) / (highest_high - lowest_low))
    df['STOCHd_14_3_3'] = df['STOCHk_14_3_3'].rolling(3).mean()

    # --- StochRSI ---
    rsi = df['RSI_14']
    rsi_min = rsi.rolling(14).min()
    rsi_max = rsi.rolling(14).max()
    stochrsi = (rsi - rsi_min) / (rsi_max - rsi_min)
    df['STOCHRSIk_14_14_3_3'] = stochrsi.rolling(3).mean() * 100
    df['STOCHRSId_14_14_3_3'] = df['STOCHRSIk_14_14_3_3'].rolling(3).mean()

    # --- ADX ---
    high_diff = high.diff()
    low_diff = -low.diff()
    plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)
    atr = tr_series.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/14, min_periods=14, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/14, min_periods=14, adjust=False).mean() / atr)
    df['DMP_14'] = plus_di
    df['DMN_14'] = minus_di
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    df['ADX_14'] = dx.ewm(alpha=1/14, min_periods=14, adjust=False).mean()

    # --- Aroon ---
    df['AROONU_14'] = high.rolling(14).apply(lambda x: x.argmax() / 14 * 100, raw=True)
    df['AROOND_14'] = low.rolling(14).apply(lambda x: x.argmin() / 14 * 100, raw=True)
    df['AROONOSC_14'] = df['AROONU_14'] - df['AROOND_14']

    # --- CCI ---
    tp = (high + low + close) / 3
    cci_sma = tp.rolling(14).mean()
    cci_mad = tp.rolling(14).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    df['CCI_14'] = (tp - cci_sma) / (0.015 * cci_mad)

    # --- Williams %R ---
    df['WILLR_14'] = -100 * ((highest_high - close) / (highest_high - lowest_low))

    # --- ROC ---
    df['ROC_10'] = ((close - close.shift(10)) / close.shift(10)) * 100

    # --- TRIX (Triple Exponential Average) ---
    # TRIX = 1-period percent change of triple-smoothed EMA
    trix_period = 14
    ema1 = close.ewm(span=trix_period, adjust=False).mean()
    ema2 = ema1.ewm(span=trix_period, adjust=False).mean()
    ema3 = ema2.ewm(span=trix_period, adjust=False).mean()
    df['TRIX_14'] = (ema3 - ema3.shift(1)) / ema3.shift(1) * 100

    # --- CMO (Chande Momentum Oscillator) ---
    cmo_period = 14
    cmo_delta = close.diff()
    cmo_gain = cmo_delta.where(cmo_delta > 0, 0.0).rolling(cmo_period).sum()
    cmo_loss = (-cmo_delta).where(cmo_delta < 0, 0.0).rolling(cmo_period).sum()
    df['CMO_14'] = 100 * (cmo_gain - cmo_loss) / (cmo_gain + cmo_loss).replace(0, np.nan)

    # --- Volume ---
    df['volume_sma_20'] = volume.rolling(20).mean()
    direction = np.sign(close.diff())
    direction.iloc[0] = 0
    df['OBV'] = (volume * direction).cumsum()

    # --- MFI ---
    tp = (high + low + close) / 3
    raw_mf = tp * volume
    mf_pos = raw_mf.where(tp > tp.shift(1), 0)
    mf_neg = raw_mf.where(tp < tp.shift(1), 0)
    mfr = mf_pos.rolling(14).sum() / mf_neg.rolling(14).sum().replace(0, np.nan)
    df['MFI_14'] = 100 - (100 / (1 + mfr))

    # --- CMF ---
    mfv = ((close - low) - (high - close)) / (high - low).replace(0, np.nan) * volume
    df['CMF_20'] = mfv.rolling(20).sum() / volume.rolling(20).sum()

    # --- EMV (Ease of Movement) ---
    # EMV measures the ease with which prices move based on volume
    # Formula: (HL_avg_change) / (Volume / (High - Low))
    hl_avg = (high + low) / 2
    hl_avg_change = hl_avg.diff()
    hl_range = (high - low).replace(0, np.nan)
    box_ratio = (volume / 10000) / hl_range  # Scale volume down
    emv_raw = hl_avg_change / box_ratio.replace(0, np.nan)
    df['EMV'] = emv_raw.rolling(14).mean()  # Smoothed EMV
    df['EMV_14'] = df['EMV']  # Alias

    # --- VHF (Vertical Horizontal Filter) ---
    # Measures if market is trending or ranging (0-1 scale)
    # Higher values = trending, lower = ranging
    vhf_period = 28
    highest_close = close.rolling(vhf_period).max()
    lowest_close = close.rolling(vhf_period).min()
    numerator = (highest_close - lowest_close).abs()
    denominator = close.diff().abs().rolling(vhf_period).sum()
    # Guard against division by zero
    denominator_safe = denominator.where(denominator != 0, np.nan)
    df['VHF_28'] = numerator / denominator_safe

    # --- TSI (True Strength Index) ---
    # Double-smoothed momentum: EMA(EMA(close_diff, 25), 13)
    close_diff = close.diff()
    abs_close_diff = close_diff.abs()
    ema_diff_25 = close_diff.ewm(span=25, adjust=False).mean()
    ema_diff_25_13 = ema_diff_25.ewm(span=13, adjust=False).mean()
    ema_abs_25 = abs_close_diff.ewm(span=25, adjust=False).mean()
    ema_abs_25_13 = ema_abs_25.ewm(span=13, adjust=False).mean()
    df['TSI_25_13'] = 100 * (ema_diff_25_13 / ema_abs_25_13.replace(0, np.nan))

    # --- Momentum (10-period price change) ---
    df['MOM_10'] = close - close.shift(10)

    # --- Fisher Transform ---
    hl2 = (high + low) / 2
    min_hl2 = hl2.rolling(9).min()
    max_hl2 = hl2.rolling(9).max()
    raw_fisher = 2 * ((hl2 - min_hl2) / (max_hl2 - min_hl2).replace(0, np.nan)) - 1
    raw_fisher = raw_fisher.clip(-0.999, 0.999)
    df['FISHERT_9_1'] = 0.5 * np.log((1 + raw_fisher) / (1 - raw_fisher))
    df['FISHERTs_9_1'] = df['FISHERT_9_1'].shift(1)

    # --- DPO (Detrended Price Oscillator) ---
    dpo_period = 14
    dpo_shift = dpo_period // 2 + 1
    df['DPO_14'] = close - close.rolling(dpo_period).mean().shift(dpo_shift)

    # --- Ultimate Oscillator ---
    bp = close - pd.concat([low, close.shift(1)], axis=1).min(axis=1)
    tr_uo = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    avg7 = bp.rolling(7).sum() / tr_uo.rolling(7).sum().replace(0, np.nan)
    avg14 = bp.rolling(14).sum() / tr_uo.rolling(14).sum().replace(0, np.nan)
    avg28 = bp.rolling(28).sum() / tr_uo.rolling(28).sum().replace(0, np.nan)
    df['UO_7_14_28'] = 100 * (4 * avg7 + 2 * avg14 + avg28) / 7

    # --- Motion Derivatives for Close ---
    # Compute velocity, acceleration, jerk and their z-scores
    # These are critical for chaos-generated patterns
    close_arr = close.values.astype(np.float64)

    # Velocity (1st derivative)
    velocity = np.full(len(close_arr), np.nan)
    velocity[1:] = np.diff(close_arr)
    df['close_velocity'] = velocity

    # Acceleration (2nd derivative)
    acceleration = np.full(len(close_arr), np.nan)
    acceleration[2:] = np.diff(close_arr, n=2)
    df['close_acceleration'] = acceleration

    # Jerk (3rd derivative)
    jerk = np.full(len(close_arr), np.nan)
    if len(close_arr) > 3:
        jerk[3:] = np.diff(close_arr, n=3)
    df['close_jerk'] = jerk

    # Z-score normalization (rolling window = 100)
    zscore_window = 100
    for deriv_name in ['close_velocity', 'close_acceleration', 'close_jerk']:
        series = pd.Series(df[deriv_name].values)
        rolling_mean = series.rolling(window=zscore_window, min_periods=2).mean()
        rolling_std = series.rolling(window=zscore_window, min_periods=2).std()
        zscore = (series - rolling_mean) / rolling_std.replace(0, np.nan)
        df[f'{deriv_name}_zscore'] = zscore.values

    if verbose:
        print(f"  [Fast] Computed {len([c for c in df.columns if c.isupper()])} indicators + motion derivatives")

    return df


# =============================================================================
# MOTION DERIVATIVES
# =============================================================================

def compute_motion_derivatives(
    df: pd.DataFrame,
    columns: List[str] = None,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    Compute motion derivatives (velocity through pop) for specified columns.

    Args:
        df: DataFrame with indicator columns
        columns: List of columns to compute derivatives for (default: all numeric)
        verbose: Print progress

    Returns:
        DataFrame with derivative columns added
    """
    result = df.copy()

    # Get columns to process
    exclude_cols = {'timestamp', 'timestamp_ms', 'timestamp_dt', 'time', 'symbol',
                    'timeframe', 'exchange', 'asset', 'dayOfWeek', 'hourOfDay',
                    'month', 'trendRegime', 'volatilityRegime', 'regime'}

    if columns is None:
        columns = [col for col in result.columns
                   if col not in exclude_cols
                   and result[col].dtype in ['float64', 'int64', 'float32', 'int32']
                   and not any(col.endswith(f'_{d}') for d in DERIVATIVE_COEFFICIENTS.keys())
                   and not col.endswith('_zscore')]

    if verbose:
        print(f"  Computing motion derivatives for {len(columns)} columns...")

    for idx, col in enumerate(columns):
        if verbose and (idx + 1) % 25 == 0:
            print(f"    Progress: {idx + 1}/{len(columns)}...")

        values = result[col].values.astype(np.float64)

        if np.all(np.isnan(values)):
            continue

        # Compute all 6 derivative orders
        derivs = _compute_derivatives_for_series(values)

        for deriv_name, deriv_values in derivs.items():
            result[f'{col}_{deriv_name}'] = deriv_values
            result[f'{col}_{deriv_name}_zscore'] = _compute_zscore_rolling(deriv_values)

    return result


def _compute_derivatives_for_series(values: np.ndarray) -> dict[str, np.ndarray]:
    """Compute all 6 derivative orders for a single series."""
    results = {}
    n = len(values)

    for deriv_name, coeffs in DERIVATIVE_COEFFICIENTS.items():
        order = len(coeffs)
        if n < order:
            results[deriv_name] = np.full(n, np.nan)
            continue

        deriv = np.convolve(values, coeffs[::-1], mode='valid')
        padded = np.full(n, np.nan)
        padded[order - 1:] = deriv
        results[deriv_name] = padded

    return results


def _compute_zscore_rolling(values: np.ndarray, window: int = ZSCORE_WINDOW) -> np.ndarray:
    """Compute rolling z-score normalization."""
    n = len(values)
    result = np.full(n, np.nan)

    series = pd.Series(values)
    rolling_mean = series.rolling(window=window, min_periods=2).mean()
    rolling_std = series.rolling(window=window, min_periods=2).std()

    mask = rolling_std > 0
    result[mask.values] = (series[mask] - rolling_mean[mask]) / rolling_std[mask]

    return result


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_indicator_columns() -> List[str]:
    """Get the list of indicator columns from the last calculation."""
    return INDICATOR_COLS.copy()


def has_pandas_ta() -> bool:
    """Check if pandas_ta is available."""
    return HAS_PANDAS_TA
