"""
TSLA CSV to Test Parquet Converter

Converts TSLA CSV files to parquet format with ALL indicators computed:
1. BASE indicators (130+ via pandas_ta)
2. DERIVED indicators (enrichment service)
3. MOTION derivatives (velocity through pop) + z-scores

OUTPUT: data/test_data/TSLA_FORWARD_VALIDATION/  (CLEARLY LABELED AS TEST DATA)

This is for FORWARD VALIDATION of bear protection findings on out-of-sample TSLA data.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import polars as pl

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import from our infrastructure services
from Fast_Swarm.Infrastructure.Services.indicator_calculation_service import (
    calculate_indicators,
    compute_motion_derivatives,
    has_pandas_ta,
)
from Fast_Swarm.Infrastructure.Services.indicator_enrichment_service import (
    compute_derived_for_candle,
)


# =============================================================================
# OUTPUT DIRECTORY - CLEARLY LABELED AS TEST DATA
# =============================================================================

OUTPUT_DIR = PROJECT_ROOT / "data" / "test_data" / "TSLA_FORWARD_VALIDATION"


# =============================================================================
# ENRICHMENT SERVICE DERIVED INDICATORS
# =============================================================================

def compute_enrichment_derived(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute derived indicators using the existing library function.
    Maps pandas_ta column names to what compute_derived_for_candle expects.
    """
    result = df.copy()

    # Map pandas_ta column names to what the enrichment service expects
    column_mappings = {
        'EMA_9': 'ema_9',
        'EMA_21': 'ema_21',
        'SMA_50': 'sma_50',
        'SMA_200': 'sma_200',
        'RSI_14': 'rsi_14',
        'MACD_12_26_9': 'macd_line',
        'MACDs_12_26_9': 'macd_signal',
        'STOCHk_14_3_3': 'stoch_k',
        'STOCHd_14_3_3': 'stoch_d',
        'ADX_14': 'adx_14',
        'DMP_14': 'plus_di',
        'DMN_14': 'minus_di',
        'NATR_14': 'natr_14',
        'BBU_20_2.0': 'bb_upper',
        'BBM_20_2.0': 'bb_middle',
        'BBL_20_2.0': 'bb_lower',
        'BBB_20_2.0': 'bb_width',
    }

    # Create mapped columns for enrichment
    for ta_col, our_col in column_mappings.items():
        if ta_col in result.columns and our_col not in result.columns:
            result[our_col] = result[ta_col]

    # Compute derived indicators for each row
    derived_cols = []
    for idx in range(len(result)):
        row_dict = result.iloc[idx].to_dict()

        # Add 'time' key for session detection
        if 'timestamp' in row_dict:
            row_dict['time'] = row_dict['timestamp']

        derived = compute_derived_for_candle(row_dict)

        for col, val in derived.items():
            if col not in result.columns:
                result[col] = None
                derived_cols.append(col)
            result.at[idx, col] = val

    return result


# =============================================================================
# OHLCV RESAMPLING (1h -> 4h)
# =============================================================================

def resample_ohlcv(df: pd.DataFrame, source_tf: str, target_tf: str) -> pd.DataFrame:
    """
    Resample OHLCV data from source timeframe to target timeframe.

    Standard OHLCV rollup:
    - Open = first candle's open
    - High = max of all highs
    - Low = min of all lows
    - Close = last candle's close
    - Volume = sum of all volumes
    """
    # Determine resampling rule
    tf_to_pandas = {
        '1m': '1min', '5m': '5min', '15m': '15min', '30m': '30min',
        '1h': '1h', '4h': '4h', '6h': '6h', '1d': '1D'
    }

    if target_tf not in tf_to_pandas:
        raise ValueError(f"Unknown target timeframe: {target_tf}")

    resample_rule = tf_to_pandas[target_tf]

    # Set timestamp as index for resampling
    df_copy = df.copy()
    df_copy = df_copy.set_index('timestamp')

    # OHLCV resampling rules
    resampled = df_copy.resample(resample_rule).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()

    # Reset index to get timestamp back as column
    resampled = resampled.reset_index()
    resampled['timestamp_ms'] = resampled['timestamp'].apply(lambda x: int(x.timestamp() * 1000))

    return resampled


# =============================================================================
# CSV LOADING AND PROCESSING
# =============================================================================

def load_tsla_csv(csv_path: Path) -> pd.DataFrame:
    """Load a TSLA CSV file and standardize column names."""
    df = pd.read_csv(csv_path)

    # Standardize column names (lowercase)
    df.columns = df.columns.str.lower()

    # Parse timestamp
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    elif 'time' in df.columns:
        df['timestamp'] = pd.to_datetime(df['time'])

    # Convert to Unix milliseconds
    df['timestamp_ms'] = df['timestamp'].apply(lambda x: int(x.timestamp() * 1000))

    return df


def extract_timeframe_from_filename(filename: str) -> str:
    """Extract timeframe from filename like 'TSLA_1hour_sample.csv'."""
    name_lower = filename.lower()
    if '1min' in name_lower:
        return '1m'
    elif '5min' in name_lower:
        return '5m'
    elif '30min' in name_lower:
        return '30m'
    elif '1hour' in name_lower:
        return '1h'
    elif '1day' in name_lower:
        return '1d'
    else:
        return 'unknown'


def process_single_csv(csv_path: Path) -> tuple:
    """
    Process a single CSV file into fully enriched DataFrame.

    Steps:
    1. Load raw OHLCV from CSV
    2. Compute 130+ base indicators via pandas_ta
    3. Compute enrichment-service derived indicators
    4. Compute motion derivatives (velocity through pop) for ALL indicators
    """
    print(f"\n{'='*70}")
    print(f"Processing: {csv_path.name}")
    print('='*70)

    # Load CSV
    df = load_tsla_csv(csv_path)
    timeframe = extract_timeframe_from_filename(csv_path.name)
    print(f"  Timeframe: {timeframe}")
    print(f"  Rows: {len(df)}")
    print(f"  Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

    # Add metadata
    df['symbol'] = 'TSLA'
    df['timeframe'] = timeframe
    df['exchange'] = 'TEST'  # Clearly marked as test data

    # Step 1: Compute base indicators (130+ via pandas_ta)
    print(f"  [STEP 1/4] Computing base indicators (pandas_ta)...")
    df = calculate_indicators(df, verbose=True)
    print(f"    Result: {len(df.columns)} columns after base indicators")

    # Step 2: Compute enrichment-service derived indicators
    print(f"  [STEP 2/4] Computing enrichment derived indicators...")
    df = compute_enrichment_derived(df)

    # Step 3: Compute motion derivatives (THE KEY PART)
    print(f"  [STEP 3/4] Computing motion derivatives (velocity -> pop)...")
    df = compute_motion_derivatives(df, verbose=True)

    # Step 4: Clean up
    print(f"  [STEP 4/4] Final cleanup...")

    # Replace inf with NaN
    df = df.replace([np.inf, -np.inf], np.nan)

    # Convert to Polars for parquet output
    result = pl.from_pandas(df)

    print(f"  Final: {len(result.columns)} columns, {len(result)} rows")

    return result, timeframe


def find_tsla_csvs() -> list[Path]:
    """Find all TSLA CSV files in the project root."""
    csv_files = list(PROJECT_ROOT.glob("TSLA_*.csv"))
    return sorted(csv_files)


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("="*70)
    print("TSLA CSV TO TEST PARQUET CONVERTER")
    print("="*70)
    print()
    print("*** THIS IS TEST DATA FOR FORWARD VALIDATION ***")
    print(f"*** Output: {OUTPUT_DIR} ***")
    print()
    print("Features:")
    print("  - 130+ base indicators via pandas_ta")
    print("  - Derived indicators (enrichment service)")
    print("  - Motion derivatives: velocity, acceleration, jerk, snap, crackle, pop")
    print("  - Z-score normalized derivatives")
    print()

    # Check pandas_ta
    if not has_pandas_ta():
        print("WARNING: pandas_ta not installed!")
        print("  Install with: pip install pandas_ta")
        print("  Falling back to basic indicators...")
        print()

    # Find CSV files
    csv_files = find_tsla_csvs()

    if not csv_files:
        print("ERROR: No TSLA CSV files found in project root!")
        print(f"Looking in: {PROJECT_ROOT}")
        return

    print(f"Found {len(csv_files)} TSLA CSV files:")
    for f in csv_files:
        print(f"  - {f.name}")
    print()

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Process each CSV
    all_results = {}
    raw_1h_df = None  # Keep raw 1h data for resampling

    for csv_path in csv_files:
        try:
            df, timeframe = process_single_csv(csv_path)
            all_results[timeframe] = df

            # Keep raw 1h data for resampling to 4h, 6h
            if timeframe == '1h':
                raw_1h_df = load_tsla_csv(csv_path)

            # Save individual parquet file
            output_path = OUTPUT_DIR / f"TSLA_{timeframe}_test.parquet"
            df.write_parquet(output_path)
            print(f"  Saved: {output_path}")

        except Exception as e:
            print(f"  ERROR processing {csv_path.name}: {e}")
            import traceback
            traceback.print_exc()

    # ==========================================================================
    # RESAMPLE 1h -> 4h and 6h for multi-timeframe testing
    # ==========================================================================
    if raw_1h_df is not None:
        resample_targets = ['4h', '6h']

        for target_tf in resample_targets:
            try:
                print(f"\n{'='*70}")
                print(f"Resampling: 1h -> {target_tf}")
                print('='*70)

                # Resample raw OHLCV
                resampled_df = resample_ohlcv(raw_1h_df, '1h', target_tf)
                print(f"  Resampled to {len(resampled_df)} candles")

                # Add metadata
                resampled_df['symbol'] = 'TSLA'
                resampled_df['timeframe'] = target_tf
                resampled_df['exchange'] = 'TEST'

                # Compute indicators
                print(f"  [STEP 1/4] Computing base indicators...")
                resampled_df = calculate_indicators(resampled_df, verbose=True)
                print(f"    Result: {len(resampled_df.columns)} columns")

                # Compute enrichment derived
                print(f"  [STEP 2/4] Computing enrichment derived indicators...")
                resampled_df = compute_enrichment_derived(resampled_df)

                # Compute motion derivatives
                print(f"  [STEP 3/4] Computing motion derivatives...")
                resampled_df = compute_motion_derivatives(resampled_df, verbose=True)

                # Cleanup
                print(f"  [STEP 4/4] Final cleanup...")
                resampled_df = resampled_df.replace([np.inf, -np.inf], np.nan)

                # Convert to Polars and save
                result = pl.from_pandas(resampled_df)
                all_results[target_tf] = result

                output_path = OUTPUT_DIR / f"TSLA_{target_tf}_test.parquet"
                result.write_parquet(output_path)
                print(f"  Saved: {output_path}")
                print(f"  Final: {len(result.columns)} columns, {len(result)} rows")

            except Exception as e:
                print(f"  ERROR resampling to {target_tf}: {e}")
                import traceback
                traceback.print_exc()
    else:
        print("\nWARNING: No 1h data found - skipping 4h/6h resampling")

    # Write README
    readme_path = OUTPUT_DIR / "README_TEST_DATA.txt"
    readme_content = f"""
================================================================================
                    *** TEST DATA - FORWARD VALIDATION ***
================================================================================

This directory contains TEST DATA for forward validation of bear protection.

Source: TSLA CSV files (external data, not from production database)
Date processed: {datetime.now(timezone.utc).isoformat()}

Purpose: Forward validation testing of bear protection jerk threshold findings
         discovered on BTC/ETH crypto data.

WARNING: This is NOT production data. Do not use for production backtesting.

Indicators Computed:
  - 130+ base indicators via pandas_ta (momentum, trend, volatility, volume, etc.)
  - Derived indicators (MA crosses, RSI conditions, etc.)
  - Motion derivatives: velocity, acceleration, jerk, snap, crackle, pop
  - Z-score normalized derivatives for all indicators

Key Bear Protection Columns:
  - close_velocity, close_acceleration, close_jerk (+ _zscore versions)
  - rsi_14_jerk, macd_histogram_jerk, adx_14_jerk
  - All 6 derivative orders for every numeric indicator

Files:
"""
    for tf, df in all_results.items():
        readme_content += f"  - TSLA_{tf}_test.parquet ({len(df)} rows, {len(df.columns)} columns)\n"

    readme_content += """
================================================================================
"""

    with open(readme_path, 'w') as f:
        f.write(readme_content)

    print()
    print("="*70)
    print("CONVERSION COMPLETE")
    print("="*70)
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Files created: {len(all_results)}")
    for tf, df in all_results.items():
        deriv_cols = len([c for c in df.columns if '_jerk' in c or '_velocity' in c or '_acceleration' in c])
        print(f"  - TSLA_{tf}_test.parquet: {len(df)} rows, {len(df.columns)} cols ({deriv_cols} derivative cols)")
    print()
    print("Next step: Run forward validation test")


if __name__ == "__main__":
    main()
