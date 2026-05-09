"""
Motion Derivatives Analysis Script

Computes 6 orders of motion derivatives (velocity, acceleration, jerk, snap, crackle, pop)
for every indicator across all assets and timeframes in the enhanced_candles table.

Uses Pascal's triangle with alternating signs for finite difference coefficients:
- Velocity:     [1, -1]                         (2 candles) - Rate of change
- Acceleration: [1, -2, 1]                      (3 candles) - Change in velocity
- Jerk:         [1, -3, 3, -1]                  (4 candles) - Change in acceleration
- Snap:         [1, -4, 6, -4, 1]               (5 candles) - Change in jerk
- Crackle:      [1, -5, 10, -10, 5, -1]         (6 candles) - Change in snap
- Pop:          [1, -6, 15, -20, 15, -6, 1]     (7 candles) - Change in crackle

HIGHER-ORDER DERIVATIVES (Snap, Crackle, Pop) - THE NOVEL PART:

Jerk (3rd derivative) already exists as the "Rate of Change" indicator in TradingView.
But snap, crackle, and pop (4th-6th derivatives) are UNEXPLORED in trading.

Physical meaning:
- SNAP: How quickly is jerk changing? If jerk detects regime shifts,
        snap detects when those shifts are ACCELERATING. A positive snap
        when jerk is positive means the momentum change is strengthening.

- CRACKLE: The "second derivative of jerk". Detects inflection points in
           regime changes. When crackle flips sign, snap is at an extremum.
           This is 2 steps ahead of where most traders are looking.

- POP: The subtlest signal. Detects changes in the rate of crackle.
       Highly sensitive but also noisier. Best used as confirmation
       or for detecting structural shifts in market microstructure.

Hypothesis: Higher-order derivatives may detect regime changes BEFORE
they become visible in price, like ripples on water before a wave arrives.

Output: Partitioned Parquet files in data/derivatives/symbol=X/timeframe=Y/
Checkpoint: JSONL file for restart capability

Author: Coinswarm Research
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


# =============================================================================
# CONFIGURATION
# =============================================================================

# Pascal's triangle coefficients with alternating signs
DERIVATIVE_COEFFICIENTS = {
    "velocity": [1, -1],
    "acceleration": [1, -2, 1],
    "jerk": [1, -3, 3, -1],
    "snap": [1, -4, 6, -4, 1],
    "crackle": [1, -5, 10, -10, 5, -1],
    "pop": [1, -6, 15, -20, 15, -6, 1],
}

# Order matters - process smallest timeframes first
TIMEFRAME_ORDER = ["1m", "5m", "15m", "1h", "4h", "1d"]

# All numeric indicator columns to analyze
NUMERIC_INDICATORS = [
    # Price & Volume (Core)
    "open", "high", "low", "close", "volume",
    # Moving Averages
    "sma_20", "sma_50", "sma_200",
    "ema_9", "ema_12", "ema_21", "ema_26",
    # RSI Family
    "rsi_7", "rsi_14", "rsi_21",
    # MACD
    "macd_line", "macd_signal", "macd_histogram",
    # Bollinger Bands
    "bb_upper", "bb_middle", "bb_lower", "bb_width", "bb_pct",
    # ATR/Volatility
    "atr_7", "atr_14", "natr_14", "true_range",
    # Stochastic
    "stoch_k", "stoch_d", "stochrsi_k", "stochrsi_d",
    # ADX/Trend
    "adx_14", "plus_di", "minus_di",
    # Volume Indicators
    "obv", "volume_sma_20", "cmf_20", "mfi_14",
    # Cross-Asset Metrics
    "btc_eth_correlation_14d", "eth_btc_ratio", "alt_dominance_pct",
    # Tick/Orderbook Aggregates
    "tick_cvd_ratio", "tick_trade_imbalance", "tick_buy_volume_pct",
    "tick_volatility", "tick_momentum",
    "book_avg_spread_bps", "book_avg_imbalance", "book_depth_ratio",
    # Derived Percentages
    "price_vs_ema_9_pct", "price_vs_ema_20_pct", "price_vs_ema_21_pct",
    "price_vs_sma_50_pct", "price_vs_sma_200_pct",
]

# Processing settings
BATCH_SIZE = 10000
ZSCORE_WINDOW = 100  # Rolling window for z-score normalization

# Paths
CHECKPOINT_FILE = PROJECT_ROOT / "logs" / "motion_derivatives_checkpoint.jsonl"
OUTPUT_DIR = PROJECT_ROOT / "data" / "derivatives"


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

def get_database_url() -> str:
    """Get async database URL from environment."""
    user = os.getenv("POSTGRES_USER", "coinswarm")
    password = os.getenv("POSTGRES_PASSWORD", "coinswarm_dev_2024")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "coinswarm")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


async def get_engine():
    """Create async database engine."""
    return create_async_engine(get_database_url(), echo=False)


# =============================================================================
# CHECKPOINT SYSTEM
# =============================================================================

def load_checkpoint() -> dict[str, dict[str, datetime]]:
    """Load last processed time per (symbol, timeframe) from checkpoint file.

    Returns datetime objects (not strings) for asyncpg compatibility.
    """
    checkpoint = {}
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    # Parse ISO string to datetime for asyncpg compatibility
                    last_time_str = rec["last_time"]
                    if isinstance(last_time_str, str):
                        # Handle ISO format with timezone
                        last_time = datetime.fromisoformat(last_time_str.replace("Z", "+00:00"))
                    else:
                        last_time = last_time_str
                    checkpoint.setdefault(rec["symbol"], {})[rec["timeframe"]] = last_time
    return checkpoint


def save_checkpoint(symbol: str, timeframe: str, last_time: datetime, rows: int):
    """Append checkpoint entry (atomic append)."""
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_FILE, "a") as f:
        f.write(json.dumps({
            "symbol": symbol,
            "timeframe": timeframe,
            "last_time": last_time.isoformat() if isinstance(last_time, datetime) else str(last_time),
            "rows": rows,
            "ts": datetime.now(timezone.utc).isoformat(),
        }) + "\n")


def get_last_checkpoint_time(checkpoint: dict, symbol: str, timeframe: str) -> datetime | None:
    """Get last processed time for symbol/timeframe, or None if not processed."""
    return checkpoint.get(symbol, {}).get(timeframe)


# =============================================================================
# DERIVATIVE COMPUTATION
# =============================================================================

def compute_derivatives_for_series(values: np.ndarray) -> dict[str, np.ndarray]:
    """
    Compute all 6 derivative orders for a single indicator series.

    Uses convolution with Pascal's triangle coefficients.
    Returns arrays with NaN padding at the start (where insufficient history).
    """
    results = {}
    n = len(values)

    for deriv_name, coeffs in DERIVATIVE_COEFFICIENTS.items():
        order = len(coeffs)
        if n < order:
            # Not enough data points
            results[deriv_name] = np.full(n, np.nan)
            continue

        # Convolve with coefficients (valid mode = no padding)
        # We need to reverse coeffs because np.convolve does correlation, not convolution
        deriv = np.convolve(values, coeffs[::-1], mode='valid')

        # Pad with NaN at the start
        padded = np.full(n, np.nan)
        padded[order - 1:] = deriv
        results[deriv_name] = padded

    return results


def compute_zscore_rolling(values: np.ndarray, window: int = ZSCORE_WINDOW) -> np.ndarray:
    """
    Compute rolling z-score normalization.

    Note: This is O(n × window) - the slowest part of the computation.
    For 300K candles this takes ~1-2 seconds per derivative column.
    """
    n = len(values)
    result = np.full(n, np.nan)

    # Use vectorized rolling mean/std for speed
    # pandas rolling is much faster than manual loop
    import pandas as pd
    series = pd.Series(values)
    rolling_mean = series.rolling(window=window, min_periods=2).mean()
    rolling_std = series.rolling(window=window, min_periods=2).std()

    # Compute z-score where std > 0
    mask = rolling_std > 0
    result[mask] = (series[mask] - rolling_mean[mask]) / rolling_std[mask]

    return result


def compute_divergence_flags(derivs: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """
    Compute divergence flags between derivative orders.

    Key insight: When acceleration and jerk have opposite signs,
    a regime change is likely imminent.
    """
    n = len(derivs.get("velocity", []))
    flags = {}

    # Accel-Jerk divergence (opposite signs)
    if "acceleration" in derivs and "jerk" in derivs:
        accel = derivs["acceleration"]
        jerk = derivs["jerk"]
        flags["accel_jerk_div"] = (np.sign(accel) != np.sign(jerk)).astype(float)
        flags["accel_jerk_div"][np.isnan(accel) | np.isnan(jerk)] = np.nan

    # Velocity-Acceleration sign relationship
    if "velocity" in derivs and "acceleration" in derivs:
        vel = derivs["velocity"]
        accel = derivs["acceleration"]
        # 1 = same sign (momentum), -1 = opposite (reversal brewing)
        flags["vel_accel_sign"] = np.where(
            np.sign(vel) == np.sign(accel), 1.0, -1.0
        )
        flags["vel_accel_sign"][np.isnan(vel) | np.isnan(accel)] = np.nan

    # Jerk-Snap sign relationship
    if "jerk" in derivs and "snap" in derivs:
        jerk = derivs["jerk"]
        snap = derivs["snap"]
        flags["jerk_snap_sign"] = np.where(
            np.sign(jerk) == np.sign(snap), 1.0, -1.0
        )
        flags["jerk_snap_sign"][np.isnan(jerk) | np.isnan(snap)] = np.nan

    return flags


def compute_signal_flags(
    derivs: dict[str, np.ndarray],
    prev_derivs: dict[str, np.ndarray] | None = None
) -> dict[str, np.ndarray]:
    """Compute signal flags for regime detection."""
    n = len(derivs.get("velocity", []))
    signals = {}

    # Jerk spike detection (|jerk| in top 5% historically)
    if "jerk" in derivs:
        jerk = derivs["jerk"]
        valid_jerk = jerk[~np.isnan(jerk)]
        if len(valid_jerk) > 0:
            threshold = np.percentile(np.abs(valid_jerk), 95)
            signals["jerk_spike"] = (np.abs(jerk) > threshold).astype(float)
            signals["jerk_spike"][np.isnan(jerk)] = np.nan

    # Acceleration reversal (sign flip from previous)
    if "acceleration" in derivs and prev_derivs and "acceleration" in prev_derivs:
        curr_accel = derivs["acceleration"]
        prev_accel = prev_derivs["acceleration"]
        signals["accel_reversal"] = (np.sign(curr_accel) != np.sign(prev_accel)).astype(float)
        signals["accel_reversal"][np.isnan(curr_accel) | np.isnan(prev_accel)] = np.nan

    return signals


# =============================================================================
# DATA PROCESSING
# =============================================================================

async def get_distinct_symbol_timeframes(engine) -> list[tuple[str, str]]:
    """Get all distinct (symbol, timeframe) combinations from database."""
    async with AsyncSession(engine) as session:
        result = await session.execute(text("""
            SELECT DISTINCT symbol, timeframe
            FROM enhanced_candles
            ORDER BY symbol, timeframe
        """))
        return [(row[0], row[1]) for row in result.fetchall()]


async def get_candle_count(engine, symbol: str, timeframe: str) -> int:
    """Get count of candles for a symbol/timeframe."""
    async with AsyncSession(engine) as session:
        result = await session.execute(text("""
            SELECT COUNT(*) FROM enhanced_candles
            WHERE symbol = :symbol AND timeframe = :timeframe
        """), {"symbol": symbol, "timeframe": timeframe})
        return result.scalar() or 0


async def fetch_candles_batch(
    engine,
    symbol: str,
    timeframe: str,
    offset: int,
    limit: int,
    after_time: str | None = None
) -> list[dict]:
    """Fetch a batch of candles ordered by time."""
    async with AsyncSession(engine) as session:
        # Build column list
        columns = ["time", "symbol", "timeframe"] + NUMERIC_INDICATORS
        columns_str = ", ".join(columns)

        if after_time:
            result = await session.execute(text(f"""
                SELECT {columns_str}
                FROM enhanced_candles
                WHERE symbol = :symbol
                  AND timeframe = :timeframe
                  AND time > :after_time
                ORDER BY time ASC
                LIMIT :limit
            """), {
                "symbol": symbol,
                "timeframe": timeframe,
                "after_time": after_time,
                "limit": limit,
            })
        else:
            result = await session.execute(text(f"""
                SELECT {columns_str}
                FROM enhanced_candles
                WHERE symbol = :symbol AND timeframe = :timeframe
                ORDER BY time ASC
                LIMIT :limit OFFSET :offset
            """), {
                "symbol": symbol,
                "timeframe": timeframe,
                "limit": limit,
                "offset": offset,
            })

        rows = result.fetchall()
        return [dict(zip(columns, row)) for row in rows]


def process_candles_to_derivatives(candles: list[dict], verbose: bool = True) -> pl.DataFrame:
    """
    Process a batch of candles into a DataFrame with all derivatives.

    Returns a Polars DataFrame with:
    - Identity columns (time, symbol, timeframe)
    - Raw indicator values
    - Derivatives for each indicator (velocity through pop)
    - Z-score normalized derivatives
    - Divergence flags
    - Signal flags
    """
    if not candles:
        return pl.DataFrame()

    n = len(candles)
    total_indicators = len(NUMERIC_INDICATORS)

    # Start building the result dict
    result = {
        "time": [c["time"] for c in candles],
        "symbol": [c["symbol"] for c in candles],
        "timeframe": [c["timeframe"] for c in candles],
    }

    # Process each indicator with progress reporting
    for idx, indicator in enumerate(NUMERIC_INDICATORS, 1):
        # Get raw values, converting Decimal to float
        raw_values = []
        for c in candles:
            val = c.get(indicator)
            if val is None:
                raw_values.append(np.nan)
            elif isinstance(val, Decimal):
                raw_values.append(float(val))
            else:
                raw_values.append(float(val))

        values = np.array(raw_values, dtype=np.float64)

        # Store raw value
        result[indicator] = values.tolist()

        # Progress reporting every 10 indicators or for key indicators
        if verbose and (idx % 10 == 0 or indicator in ["close", "rsi_14", "macd_histogram"]):
            print(f"      [{idx}/{total_indicators}] {indicator}: computing derivatives...", end="", flush=True)

        # Skip derivative computation if all NaN
        if np.all(np.isnan(values)):
            for deriv_name in DERIVATIVE_COEFFICIENTS.keys():
                result[f"{indicator}_{deriv_name}"] = [np.nan] * n
                result[f"{indicator}_{deriv_name}_zscore"] = [np.nan] * n
            if verbose and (idx % 10 == 0 or indicator in ["close", "rsi_14", "macd_histogram"]):
                print(" (all NaN, skipped)")
            continue

        # Compute derivatives
        derivs = compute_derivatives_for_series(values)

        for deriv_name, deriv_values in derivs.items():
            result[f"{indicator}_{deriv_name}"] = deriv_values.tolist()

            # Compute z-score
            zscore = compute_zscore_rolling(deriv_values)
            result[f"{indicator}_{deriv_name}_zscore"] = zscore.tolist()

        # Compute divergence flags for this indicator
        div_flags = compute_divergence_flags(derivs)
        for flag_name, flag_values in div_flags.items():
            result[f"{indicator}_{flag_name}"] = flag_values.tolist()

        # Close progress line
        if verbose and (idx % 10 == 0 or indicator in ["close", "rsi_14", "macd_histogram"]):
            print(" done")

    # Cross-indicator divergences (price vs momentum indicators)
    # Price velocity vs RSI velocity
    if "close_velocity" in result and "rsi_14_velocity" in result:
        close_vel = np.array(result["close_velocity"])
        rsi_vel = np.array(result["rsi_14_velocity"])
        price_vs_rsi_div = (np.sign(close_vel) != np.sign(rsi_vel)).astype(float)
        price_vs_rsi_div[np.isnan(close_vel) | np.isnan(rsi_vel)] = np.nan
        result["price_vs_rsi_vel_div"] = price_vs_rsi_div.tolist()

    # Price velocity vs MACD velocity
    if "close_velocity" in result and "macd_histogram_velocity" in result:
        close_vel = np.array(result["close_velocity"])
        macd_vel = np.array(result["macd_histogram_velocity"])
        price_vs_macd_div = (np.sign(close_vel) != np.sign(macd_vel)).astype(float)
        price_vs_macd_div[np.isnan(close_vel) | np.isnan(macd_vel)] = np.nan
        result["price_vs_macd_vel_div"] = price_vs_macd_div.tolist()

    # Add metadata
    valid_counts = []
    for i in range(n):
        count = sum(1 for ind in NUMERIC_INDICATORS if not np.isnan(result.get(ind, [np.nan])[i] if i < len(result.get(ind, [])) else np.nan))
        valid_counts.append(count)
    result["indicators_valid"] = valid_counts
    result["indicators_total"] = [len(NUMERIC_INDICATORS)] * n

    # Convert to Polars DataFrame
    return pl.DataFrame(result)


def save_parquet_partitioned(df: pl.DataFrame, symbol: str, timeframe: str):
    """Save DataFrame to partitioned Parquet file."""
    if df.is_empty():
        return

    # Create partition directory
    partition_dir = OUTPUT_DIR / f"symbol={symbol}" / f"timeframe={timeframe}"
    partition_dir.mkdir(parents=True, exist_ok=True)

    # Save to parquet (append mode - write new file if exists)
    output_path = partition_dir / "data.parquet"

    if output_path.exists():
        # Append to existing
        existing = pl.read_parquet(output_path)
        combined = pl.concat([existing, df])
        combined.write_parquet(output_path)
    else:
        df.write_parquet(output_path)


# =============================================================================
# MAIN PROCESSING LOOP
# =============================================================================

async def process_symbol_timeframe(
    engine,
    symbol: str,
    timeframe: str,
    checkpoint: dict,
    verbose: bool = True
):
    """Process all candles for a single symbol/timeframe combination."""
    last_time = get_last_checkpoint_time(checkpoint, symbol, timeframe)

    total_count = await get_candle_count(engine, symbol, timeframe)
    if total_count == 0:
        if verbose:
            print(f"  [{symbol}/{timeframe}] No candles found, skipping")
        return

    if verbose:
        resume_msg = f" (resuming from {last_time})" if last_time else ""
        print(f"  [{symbol}/{timeframe}] Processing {total_count:,} candles{resume_msg}")

    processed = 0
    offset = 0
    all_candles = []

    # Fetch all candles for this symbol/timeframe (needed for proper derivative calculation)
    while True:
        batch = await fetch_candles_batch(
            engine, symbol, timeframe,
            offset=offset if not last_time else 0,
            limit=BATCH_SIZE,
            after_time=last_time if offset == 0 else None
        )

        if not batch:
            break

        all_candles.extend(batch)
        offset += len(batch)

        if verbose and offset % (BATCH_SIZE * 5) == 0:
            print(f"    Fetched {offset:,} candles...")

    if not all_candles:
        if verbose:
            print(f"  [{symbol}/{timeframe}] No new candles to process")
        return

    if verbose:
        print(f"    Computing derivatives for {len(all_candles):,} candles...")
        print(f"    Processing {len(NUMERIC_INDICATORS)} indicators × 6 derivative orders × z-scores...")
        import time
        start_time = time.time()

    # Process all candles together (derivatives need sequential data)
    df = process_candles_to_derivatives(all_candles, verbose=verbose)

    if df.is_empty():
        return

    if verbose:
        elapsed = time.time() - start_time
        print(f"    Derivatives computed in {elapsed:.1f}s ({len(all_candles)/elapsed:.0f} candles/sec)")

        # Summary of higher-order derivatives (snap, crackle, pop) - the novel ones
        snap_cols = [c for c in df.columns if "_snap" in c and "_zscore" not in c]
        crackle_cols = [c for c in df.columns if "_crackle" in c and "_zscore" not in c]
        pop_cols = [c for c in df.columns if "_pop" in c and "_zscore" not in c]
        print(f"    Higher-order derivatives: {len(snap_cols)} snap, {len(crackle_cols)} crackle, {len(pop_cols)} pop columns")

    # Save to parquet
    if verbose:
        print(f"    Saving to Parquet ({df.shape[0]:,} rows, {df.shape[1]} columns)...")
    save_parquet_partitioned(df, symbol, timeframe)

    # Save checkpoint
    last_candle_time = all_candles[-1]["time"]
    save_checkpoint(symbol, timeframe, last_candle_time, len(all_candles))

    if verbose:
        print(f"  [{symbol}/{timeframe}] Complete! Saved {len(all_candles):,} rows")


async def main(
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    verbose: bool = True
):
    """Main entry point for motion derivatives analysis."""
    print("=" * 60)
    print("MOTION DERIVATIVES ANALYSIS")
    print("Computing velocity, acceleration, jerk, snap, crackle, pop")
    print("=" * 60)
    print()

    # Load checkpoint
    checkpoint = load_checkpoint()
    if checkpoint:
        print(f"Loaded checkpoint with {sum(len(v) for v in checkpoint.values())} processed combinations")

    # Connect to database
    engine = await get_engine()

    # Get all symbol/timeframe combinations
    all_combinations = await get_distinct_symbol_timeframes(engine)
    print(f"Found {len(all_combinations)} symbol/timeframe combinations in database")

    # Filter if requested
    if symbols:
        all_combinations = [(s, t) for s, t in all_combinations if s in symbols]
    if timeframes:
        all_combinations = [(s, t) for s, t in all_combinations if t in timeframes]

    # Sort by timeframe order, then symbol
    def sort_key(item):
        s, t = item
        tf_order = TIMEFRAME_ORDER.index(t) if t in TIMEFRAME_ORDER else 999
        return (tf_order, s)

    all_combinations.sort(key=sort_key)

    print(f"Processing {len(all_combinations)} combinations")
    print()

    # Process each combination
    for i, (symbol, timeframe) in enumerate(all_combinations, 1):
        print(f"[{i}/{len(all_combinations)}] Processing {symbol}/{timeframe}")
        try:
            await process_symbol_timeframe(engine, symbol, timeframe, checkpoint, verbose)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            continue
        print()

    await engine.dispose()

    print("=" * 60)
    print("ANALYSIS COMPLETE")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Checkpoint: {CHECKPOINT_FILE}")
    print("=" * 60)


# =============================================================================
# CLI INTERFACE
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Compute motion derivatives for all indicators"
    )
    parser.add_argument(
        "--symbols", "-s",
        nargs="+",
        help="Filter to specific symbols (e.g., BTC ETH)"
    )
    parser.add_argument(
        "--timeframes", "-t",
        nargs="+",
        help="Filter to specific timeframes (e.g., 1h 4h)"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Reduce output verbosity"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear checkpoint and reprocess everything"
    )

    args = parser.parse_args()

    if args.reset and CHECKPOINT_FILE.exists():
        print("Clearing checkpoint file...")
        CHECKPOINT_FILE.unlink()

    asyncio.run(main(
        symbols=args.symbols,
        timeframes=args.timeframes,
        verbose=not args.quiet
    ))
