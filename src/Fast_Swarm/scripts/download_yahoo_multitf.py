"""
Download Multi-Timeframe Stock Data from Yahoo Finance.

Downloads 1h data and resamples to 4h, 6h, 1d for grid search testing.
Computes required indicators: close_acceleration_zscore, adx_14_jerk_zscore.

Yahoo limitations:
- 1h data: max ~730 days of history
- We resample to higher TFs from 1h base
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import warnings

import yfinance as yf
import polars as pl
import numpy as np

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Output directory (same structure as crypto)
OUTPUT_DIR = PROJECT_ROOT / "data" / "derivatives"

# Stocks to download - major liquid symbols
SYMBOLS = [
    "AAPL", "MSFT", "GOOGL", "NVDA", "AMZN", "META", "TSLA", "BRK-B",
    "JPM", "V", "UNH", "XOM", "JNJ", "WMT", "MA", "PG", "HD", "CVX",
    "MRK", "ABBV", "KO", "PEP", "COST", "BAC", "AVGO", "TMO", "MCD",
    "CSCO", "ACN", "ABT", "LLY", "DHR", "NKE", "ORCL", "TXN", "NEE",
    "PM", "UPS", "MS", "RTX", "HON", "IBM", "QCOM", "LOW", "GS", "CAT"
]

# Timeframes to generate
TIMEFRAMES = {
    "1h": "1h",
    "4h": "4h",
    "6h": "6h",
    "1d": "1d",
}


def compute_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """Compute ADX indicator."""
    n = len(close)
    adx = np.full(n, np.nan)

    if n < period * 2:
        return adx

    # True Range
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i-1]),
            abs(low[i] - close[i-1])
        )

    # +DM and -DM
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    for i in range(1, n):
        up_move = high[i] - high[i-1]
        down_move = low[i-1] - low[i]
        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move

    # Smoothed averages (Wilder's smoothing)
    atr = np.zeros(n)
    plus_di = np.zeros(n)
    minus_di = np.zeros(n)

    # Initial values
    atr[period] = np.mean(tr[1:period+1])
    plus_di[period] = np.mean(plus_dm[1:period+1])
    minus_di[period] = np.mean(minus_dm[1:period+1])

    # Smoothed values
    for i in range(period + 1, n):
        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
        plus_di[i] = (plus_di[i-1] * (period - 1) + plus_dm[i]) / period
        minus_di[i] = (minus_di[i-1] * (period - 1) + minus_dm[i]) / period

    # DX
    dx = np.zeros(n)
    for i in range(period, n):
        if atr[i] > 0:
            plus_di_val = 100 * plus_di[i] / atr[i]
            minus_di_val = 100 * minus_di[i] / atr[i]
            di_sum = plus_di_val + minus_di_val
            if di_sum > 0:
                dx[i] = 100 * abs(plus_di_val - minus_di_val) / di_sum

    # ADX (smoothed DX)
    adx[period * 2 - 1] = np.mean(dx[period:period*2])
    for i in range(period * 2, n):
        adx[i] = (adx[i-1] * (period - 1) + dx[i]) / period

    return adx


def compute_indicators(df: pl.DataFrame) -> pl.DataFrame:
    """
    Compute required indicators for Bear Protection testing:
    - close_acceleration_zscore
    - adx_14_jerk_zscore (lowercase for consistency with crypto)
    """
    # Convert to numpy for calculations
    close = df["close"].to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    n = len(close)

    # Close velocity (first derivative)
    close_velocity = np.zeros(n)
    close_velocity[1:] = np.diff(close)

    # Close acceleration (second derivative)
    close_acceleration = np.zeros(n)
    close_acceleration[1:] = np.diff(close_velocity)

    # ADX
    adx_14 = compute_adx(high, low, close, period=14)

    # ADX jerk (third derivative of ADX)
    adx_velocity = np.zeros(n)
    adx_velocity[1:] = np.diff(adx_14)

    adx_acceleration = np.zeros(n)
    adx_acceleration[1:] = np.diff(adx_velocity)

    adx_jerk = np.zeros(n)
    adx_jerk[1:] = np.diff(adx_acceleration)

    # Z-score normalization (rolling 21-period window)
    window = 21
    close_acc_zscore = np.full(n, np.nan)
    adx_jerk_zscore = np.full(n, np.nan)

    for i in range(window, n):
        # Close acceleration zscore
        acc_window = close_acceleration[i-window:i]
        acc_mean = np.nanmean(acc_window)
        acc_std = np.nanstd(acc_window)
        if acc_std > 0:
            close_acc_zscore[i] = (close_acceleration[i] - acc_mean) / acc_std

        # ADX jerk zscore
        jerk_window = adx_jerk[i-window:i]
        jerk_mean = np.nanmean(jerk_window)
        jerk_std = np.nanstd(jerk_window)
        if jerk_std > 0:
            adx_jerk_zscore[i] = (adx_jerk[i] - jerk_mean) / jerk_std

    # Add to dataframe
    df = df.with_columns([
        pl.Series("close_acceleration_zscore", close_acc_zscore),
        pl.Series("adx_14_jerk_zscore", adx_jerk_zscore),  # lowercase to match crypto
        pl.Series("adx_14", adx_14),
    ])

    return df


def resample_to_timeframe(df_1h: pl.DataFrame, tf: str) -> pl.DataFrame:
    """
    Resample 1h data to higher timeframe.
    """
    if tf == "1h":
        return df_1h

    # Determine grouping
    if tf == "4h":
        hours = 4
    elif tf == "6h":
        hours = 6
    elif tf == "1d":
        hours = 24
    else:
        return df_1h

    # Add grouping column
    df = df_1h.with_columns([
        (pl.col("time").dt.epoch("s") // (hours * 3600) * (hours * 3600))
        .cast(pl.Int64)
        .alias("group_time")
    ])

    # Aggregate OHLCV
    resampled = df.group_by("group_time").agg([
        pl.col("time").first().alias("time"),
        pl.col("open").first(),
        pl.col("high").max(),
        pl.col("low").min(),
        pl.col("close").last(),
        pl.col("volume").sum(),
    ]).sort("time")

    # Remove group column
    resampled = resampled.drop("group_time")

    return resampled


def download_symbol(symbol: str) -> dict:
    """
    Download 1h data for a symbol and resample to all timeframes.
    Returns dict of {timeframe: dataframe}.
    """
    print(f"  Downloading {symbol}...", end=" ", flush=True)

    try:
        # Download 1h data (max ~730 days)
        ticker = yf.Ticker(symbol)
        df_raw = ticker.history(period="2y", interval="1h")

        if df_raw.empty or len(df_raw) < 100:
            print("insufficient data")
            return {}

        # Convert to polars
        df_raw = df_raw.reset_index()
        df_1h = pl.DataFrame({
            "time": df_raw["Datetime"].values,
            "open": df_raw["Open"].values,
            "high": df_raw["High"].values,
            "low": df_raw["Low"].values,
            "close": df_raw["Close"].values,
            "volume": df_raw["Volume"].values,
        })

        # Ensure time is datetime
        df_1h = df_1h.with_columns([
            pl.col("time").cast(pl.Datetime("us"))
        ])

        # Sort by time
        df_1h = df_1h.sort("time")

        results = {}
        for tf_name in TIMEFRAMES:
            # Resample
            df_tf = resample_to_timeframe(df_1h, tf_name)

            # Compute indicators
            df_tf = compute_indicators(df_tf)

            results[tf_name] = df_tf

        print(f"OK ({len(df_1h)} 1h rows)")
        return results

    except Exception as e:
        print(f"error: {e}")
        return {}


def save_symbol_data(symbol: str, tf_data: dict):
    """Save all timeframes for a symbol."""
    for tf_name, df in tf_data.items():
        # Create directory structure: data/derivatives/symbol=AAPL/timeframe=1h/
        symbol_dir = OUTPUT_DIR / f"symbol={symbol}" / f"timeframe={tf_name}"
        symbol_dir.mkdir(parents=True, exist_ok=True)

        # Save as parquet
        output_path = symbol_dir / "data.parquet"
        df.write_parquet(output_path)


def run_download():
    print("="*80)
    print("YAHOO FINANCE MULTI-TF STOCK DATA DOWNLOADER")
    print("="*80)
    print()
    print(f"Symbols to download: {len(SYMBOLS)}")
    print(f"Timeframes: {list(TIMEFRAMES.keys())}")
    print(f"Output directory: {OUTPUT_DIR}")
    print()

    success = 0
    failed = 0

    for symbol in SYMBOLS:
        tf_data = download_symbol(symbol)

        if tf_data:
            save_symbol_data(symbol, tf_data)
            success += 1
        else:
            failed += 1

    print()
    print("="*80)
    print("DOWNLOAD COMPLETE")
    print("="*80)
    print(f"  Success: {success}")
    print(f"  Failed: {failed}")
    print()
    print(f"Data saved to: {OUTPUT_DIR}")
    print()
    print("Run timeframe_grid_search.py with CRYPTO_DIR pointing to this data")
    print("to test the AJ config on stocks.")


if __name__ == "__main__":
    run_download()
