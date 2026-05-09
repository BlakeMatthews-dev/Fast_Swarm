"""
Download Equity Basket for Bear Protection Forward Validation

Downloads a diverse basket of stocks via yfinance and computes all indicators.
Uses 2 years of hourly data (yfinance max for intraday).

Basket Diversity:
  - Mag7 Tech: AAPL, NVDA
  - Growth/Volatile: TSLA, PLTR
  - Value: JPM, XOM
  - Benchmark: SPY

Output: data/test_data/EQUITY_BASKET/
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import polars as pl

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from Fast_Swarm.Infrastructure.Services.indicator_calculation_service import (
    calculate_indicators,
    compute_motion_derivatives,
    has_pandas_ta,
)


# =============================================================================
# CONFIGURATION
# =============================================================================

OUTPUT_DIR = PROJECT_ROOT / "data" / "test_data" / "EQUITY_BASKET"

# Diverse stock basket
SYMBOLS = [
    "AAPL",   # Mag7, large cap quality tech
    "NVDA",   # Mag7, AI/growth leader
    "TSLA",   # Growth, high volatility
    "PLTR",   # Startup-ish, volatile
    "JPM",    # Value, financials
    "XOM",    # Value, energy
    "SPY",    # Benchmark ETF
]

# Timeframes to download/generate
TIMEFRAMES = {
    "1h": {"period": "2y", "interval": "1h"},      # 2 years hourly
    "1d": {"period": "5y", "interval": "1d"},      # 5 years daily
}

# Resampling targets (from 1h)
RESAMPLE_TARGETS = ["4h", "6h"]


# =============================================================================
# DOWNLOAD FUNCTIONS
# =============================================================================

def download_symbol(symbol: str, period: str, interval: str) -> pd.DataFrame:
    """Download OHLCV data for a symbol from Yahoo Finance."""
    print(f"    Downloading {symbol} {interval} ({period})...")

    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)

    if df.empty:
        raise ValueError(f"No data returned for {symbol}")

    # Standardize columns
    df = df.reset_index()
    df.columns = df.columns.str.lower()

    # Rename 'date' or 'datetime' to 'timestamp'
    if 'date' in df.columns:
        df = df.rename(columns={'date': 'timestamp'})
    elif 'datetime' in df.columns:
        df = df.rename(columns={'datetime': 'timestamp'})

    # Ensure timestamp is datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Remove timezone info for consistency
    if df['timestamp'].dt.tz is not None:
        df['timestamp'] = df['timestamp'].dt.tz_localize(None)

    # Add timestamp_ms
    df['timestamp_ms'] = df['timestamp'].apply(lambda x: int(x.timestamp() * 1000))

    # Keep only OHLCV columns
    keep_cols = ['timestamp', 'timestamp_ms', 'open', 'high', 'low', 'close', 'volume']
    df = df[[c for c in keep_cols if c in df.columns]]

    print(f"      Got {len(df):,} candles from {df['timestamp'].min()} to {df['timestamp'].max()}")

    return df


def resample_ohlcv(df: pd.DataFrame, target_tf: str) -> pd.DataFrame:
    """Resample OHLCV data to target timeframe."""
    tf_to_pandas = {
        '4h': '4h',
        '6h': '6h',
    }

    if target_tf not in tf_to_pandas:
        raise ValueError(f"Unknown target timeframe: {target_tf}")

    resample_rule = tf_to_pandas[target_tf]

    df_copy = df.copy()
    df_copy = df_copy.set_index('timestamp')

    resampled = df_copy.resample(resample_rule).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()

    resampled = resampled.reset_index()
    resampled['timestamp_ms'] = resampled['timestamp'].apply(lambda x: int(x.timestamp() * 1000))

    return resampled


# =============================================================================
# PROCESSING FUNCTIONS
# =============================================================================

def process_dataframe(df: pd.DataFrame, symbol: str, timeframe: str, verbose: bool = True) -> pl.DataFrame:
    """
    Process a DataFrame through the full indicator pipeline.

    Steps:
    1. Calculate 130+ base indicators (pandas_ta)
    2. Compute motion derivatives (velocity through pop)
    3. Clean up inf values
    4. Convert to Polars
    """
    if verbose:
        print(f"    Processing {symbol} {timeframe} ({len(df):,} rows)...")

    # Add metadata
    df = df.copy()
    df['symbol'] = symbol
    df['timeframe'] = timeframe
    df['exchange'] = 'EQUITY'

    # Step 1: Base indicators
    if verbose:
        print(f"      [1/3] Computing base indicators...")
    df = calculate_indicators(df, verbose=False)

    # Step 2: Motion derivatives
    if verbose:
        print(f"      [2/3] Computing motion derivatives...")
    df = compute_motion_derivatives(df, verbose=False)

    # Step 3: Cleanup
    if verbose:
        print(f"      [3/3] Cleanup...")
    df = df.replace([np.inf, -np.inf], np.nan)

    # Convert to Polars
    result = pl.from_pandas(df)

    if verbose:
        deriv_cols = len([c for c in result.columns if '_jerk' in c or '_velocity' in c])
        print(f"      Done: {len(result.columns)} cols ({deriv_cols} derivative cols)")

    return result


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("="*70)
    print("EQUITY BASKET DOWNLOADER")
    print("="*70)
    print()
    print("*** FORWARD VALIDATION DATA FOR BEAR PROTECTION ***")
    print()

    # Check dependencies
    if not HAS_YFINANCE:
        print("ERROR: yfinance not installed!")
        print("  Install with: pip install yfinance")
        return

    if not has_pandas_ta():
        print("WARNING: pandas_ta not installed - using basic indicators")

    print(f"Symbols: {', '.join(SYMBOLS)}")
    print(f"Timeframes: {', '.join(TIMEFRAMES.keys())} + resampled {', '.join(RESAMPLE_TARGETS)}")
    print(f"Output: {OUTPUT_DIR}")
    print()

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Track results
    all_results = {}

    # Process each symbol
    for symbol in SYMBOLS:
        print(f"\n{'='*70}")
        print(f"PROCESSING: {symbol}")
        print("="*70)

        symbol_results = {}
        raw_1h_df = None

        # Download each timeframe
        for tf, params in TIMEFRAMES.items():
            try:
                df = download_symbol(symbol, params["period"], params["interval"])

                if len(df) < 100:
                    print(f"      WARNING: Only {len(df)} candles - skipping")
                    continue

                # Keep raw 1h for resampling
                if tf == "1h":
                    raw_1h_df = df.copy()

                # Process through indicator pipeline
                result = process_dataframe(df, symbol, tf)
                symbol_results[tf] = result

                # Save parquet
                output_path = OUTPUT_DIR / f"{symbol}_{tf}.parquet"
                result.write_parquet(output_path)
                print(f"      Saved: {output_path.name}")

            except Exception as e:
                print(f"      ERROR: {e}")

        # Resample 1h to 4h, 6h
        if raw_1h_df is not None:
            for target_tf in RESAMPLE_TARGETS:
                try:
                    print(f"    Resampling 1h -> {target_tf}...")
                    resampled_df = resample_ohlcv(raw_1h_df, target_tf)

                    if len(resampled_df) < 50:
                        print(f"      WARNING: Only {len(resampled_df)} candles - skipping")
                        continue

                    result = process_dataframe(resampled_df, symbol, target_tf)
                    symbol_results[target_tf] = result

                    output_path = OUTPUT_DIR / f"{symbol}_{target_tf}.parquet"
                    result.write_parquet(output_path)
                    print(f"      Saved: {output_path.name}")

                except Exception as e:
                    print(f"      ERROR resampling to {target_tf}: {e}")

        all_results[symbol] = symbol_results

    # Summary
    print("\n" + "="*70)
    print("DOWNLOAD COMPLETE")
    print("="*70)
    print(f"\nOutput directory: {OUTPUT_DIR}")
    print(f"\nFiles created:")

    total_files = 0
    for symbol, tfs in all_results.items():
        for tf, df in tfs.items():
            print(f"  - {symbol}_{tf}.parquet: {len(df):,} rows, {len(df.columns)} cols")
            total_files += 1

    print(f"\nTotal: {total_files} parquet files")
    print("\nNext step: Run forward_validation_equity.py")


if __name__ == "__main__":
    main()
