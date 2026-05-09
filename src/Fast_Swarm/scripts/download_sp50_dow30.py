"""
Download S&P 50 (top 50 by market cap) + Dow 30 + Indices

Full dataset for comprehensive rotation strategy testing.
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
)

OUTPUT_DIR = PROJECT_ROOT / "data" / "test_data" / "SP50_DOW30"

# S&P 500 Top 50 by market cap (as of 2024)
SP50 = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "BRK-B", "LLY", "AVGO", "TSLA",
    "JPM", "WMT", "V", "UNH", "XOM", "MA", "COST", "HD", "PG", "JNJ",
    "ORCL", "NFLX", "BAC", "CRM", "ABBV", "CVX", "MRK", "KO", "AMD", "PEP",
    "TMO", "ADBE", "WFC", "ACN", "LIN", "MCD", "CSCO", "ABT", "DHR", "INTU",
    "IBM", "GE", "CAT", "VZ", "CMCSA", "TXN", "PM", "ISRG", "NOW", "QCOM",
]

# Dow Jones 30 Components
DOW30 = [
    "AAPL", "AMGN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS", "DOW",
    "GS", "HD", "HON", "IBM", "INTC", "JNJ", "JPM", "KO", "MCD", "MMM",
    "MRK", "MSFT", "NKE", "PG", "TRV", "UNH", "V", "VZ", "WBA", "WMT",
]

# Indices
INDICES = [
    "SPY",   # S&P 500 ETF
    "DIA",   # Dow Jones ETF
    "QQQ",   # Nasdaq 100 ETF
    "IWM",   # Russell 2000 ETF
]

# Combine all unique symbols
ALL_SYMBOLS = list(set(SP50 + DOW30 + INDICES))
ALL_SYMBOLS.sort()


def download_and_process(symbol: str, period: str = "5y") -> pl.DataFrame:
    """Download and process a symbol."""
    print(f"  {symbol}...", end=" ", flush=True)

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval="1d")
    except Exception as e:
        print(f"FAIL: {e}")
        return None

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

    keep = ['timestamp', 'timestamp_ms', 'open', 'high', 'low', 'close', 'volume', 'symbol', 'timeframe']
    df = df[[c for c in keep if c in df.columns]]

    days = len(df)
    start = df['timestamp'].min().date()
    end = df['timestamp'].max().date()

    # Calculate indicators
    df = calculate_indicators(df, verbose=False)
    df = compute_motion_derivatives(df, verbose=False)
    df = df.replace([np.inf, -np.inf], np.nan)

    result = pl.from_pandas(df)
    print(f"{days} days ({start} to {end}) - {len(result.columns)} cols")

    return result


def main():
    print("="*70)
    print("DOWNLOAD S&P 50 + DOW 30 + INDICES (5 YEAR DAILY)")
    print("="*70)
    print()

    if not HAS_YFINANCE:
        print("ERROR: pip install yfinance")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Total unique symbols: {len(ALL_SYMBOLS)}")
    print(f"  - S&P Top 50: {len(SP50)}")
    print(f"  - Dow 30: {len(DOW30)}")
    print(f"  - Indices: {len(INDICES)}")
    print(f"Output: {OUTPUT_DIR}")
    print()

    success = 0
    failed = []

    for symbol in ALL_SYMBOLS:
        try:
            result = download_and_process(symbol)
            if result is not None:
                path = OUTPUT_DIR / f"{symbol}_1d.parquet"
                result.write_parquet(path)
                success += 1
            else:
                failed.append(symbol)
        except Exception as e:
            print(f"ERROR: {e}")
            failed.append(symbol)

    print()
    print("="*70)
    print(f"COMPLETE: {success}/{len(ALL_SYMBOLS)} symbols downloaded")
    if failed:
        print(f"Failed: {', '.join(failed)}")
    print("="*70)


if __name__ == "__main__":
    main()
