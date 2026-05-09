"""
Download 5+ Years of Daily Equity Data for Long-Term Backtest

Uses yfinance to get maximum daily history for rotation strategy testing.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from Fast_Swarm.Infrastructure.Services.indicator_calculation_service import (
    calculate_indicators,
    compute_motion_derivatives,
    has_pandas_ta,
)

OUTPUT_DIR = PROJECT_ROOT / "data" / "test_data" / "EQUITY_DAILY_5Y"

SYMBOLS = ["AAPL", "NVDA", "TSLA", "PLTR", "JPM", "XOM", "SPY"]


def download_and_process(symbol: str, period: str = "5y") -> pl.DataFrame:
    """Download and process a symbol."""
    print(f"  {symbol}...", end=" ", flush=True)

    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval="1d")

    if df.empty:
        print("NO DATA")
        return None

    # Standardize
    df = df.reset_index()
    df.columns = df.columns.str.lower()

    if 'date' in df.columns:
        df = df.rename(columns={'date': 'timestamp'})

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    if df['timestamp'].dt.tz is not None:
        df['timestamp'] = df['timestamp'].dt.tz_localize(None)

    df['timestamp_ms'] = df['timestamp'].apply(lambda x: int(x.timestamp() * 1000))
    df['symbol'] = symbol
    df['timeframe'] = '1d'

    # Keep OHLCV
    keep = ['timestamp', 'timestamp_ms', 'open', 'high', 'low', 'close', 'volume', 'symbol', 'timeframe']
    df = df[[c for c in keep if c in df.columns]]

    print(f"{len(df)} days from {df['timestamp'].min().date()} to {df['timestamp'].max().date()}...", end=" ")

    # Calculate indicators
    df = calculate_indicators(df, verbose=False)
    df = compute_motion_derivatives(df, verbose=False)
    df = df.replace([np.inf, -np.inf], np.nan)

    result = pl.from_pandas(df)
    print(f"OK ({len(result.columns)} cols)")

    return result


def main():
    print("="*70)
    print("DOWNLOAD 5-YEAR DAILY DATA")
    print("="*70)
    print()

    if not HAS_YFINANCE:
        print("ERROR: pip install yfinance")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Symbols: {', '.join(SYMBOLS)}")
    print(f"Output: {OUTPUT_DIR}")
    print()

    for symbol in SYMBOLS:
        try:
            result = download_and_process(symbol)
            if result is not None:
                path = OUTPUT_DIR / f"{symbol}_1d.parquet"
                result.write_parquet(path)
        except Exception as e:
            print(f"ERROR: {e}")

    print()
    print("Done! Files saved to:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
