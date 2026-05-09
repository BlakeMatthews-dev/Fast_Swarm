"""
Focused analysis on SNAP, CRACKLE, POP - the 4th, 5th, 6th order derivatives.

Key questions:
1. Do snap/crackle/pop predict future returns?
2. Do they LEAD lower-order derivatives (velocity, acceleration, jerk)?
3. Do indicator snap/crackle/pop lead price movements?
4. What happens after extreme values?
"""

import polars as pl
from pathlib import Path
import numpy as np
from datetime import datetime

DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")
RESULTS_DIR = Path("c:/fast_swarm/data/analysis_results")
RESULTS_DIR.mkdir(exist_ok=True)


def main():
    # Load BTC 1h data (cleanest, most complete)
    path = DERIVATIVES_DIR / "symbol=BTC" / "timeframe=1h"
    df = pl.read_parquet(path)
    print(f"Loaded BTC 1h: {len(df):,} rows, {len(df.columns)} columns")

    results = []
    results.append("=" * 80)
    results.append("SNAP/CRACKLE/POP ANALYSIS: ARE THEY LEADING INDICATORS?")
    results.append(f"Generated: {datetime.now().isoformat()}")
    results.append(f"Data: BTC 1h, {len(df):,} rows")
    results.append("=" * 80)

    # Get column names by category
    snap_cols = [c for c in df.columns if "_snap_zscore" in c]
    crackle_cols = [c for c in df.columns if "_crackle_zscore" in c]
    pop_cols = [c for c in df.columns if "_pop_zscore" in c]
    velocity_cols = [c for c in df.columns if "_velocity_zscore" in c]
    accel_cols = [c for c in df.columns if "_acceleration_zscore" in c]
    jerk_cols = [c for c in df.columns if "_jerk_zscore" in c]

    results.append("")
    results.append(f"Column counts: snap={len(snap_cols)}, crackle={len(crackle_cols)}, pop={len(pop_cols)}")
    results.append(f"               velocity={len(velocity_cols)}, accel={len(accel_cols)}, jerk={len(jerk_cols)}")

    # Add forward returns
    for h in [1, 5, 10, 30, 60]:
        df = df.with_columns([
            ((pl.col("close").shift(-h) - pl.col("close")) / pl.col("close") * 100).alias(f"fwd_return_{h}")
        ])

    # ======================================================================
    # PART 1: DO SNAP/CRACKLE/POP PREDICT FUTURE RETURNS?
    # ======================================================================
    results.append("")
    results.append("=" * 80)
    results.append("PART 1: DO SNAP/CRACKLE/POP PREDICT FUTURE RETURNS?")
    results.append("=" * 80)

    for order_name, order_cols in [("SNAP", snap_cols), ("CRACKLE", crackle_cols), ("POP", pop_cols)]:
        results.append("")
        results.append(f"--- {order_name} correlations with forward returns ---")

        for horizon in [10, 30, 60]:
            target = f"fwd_return_{horizon}"
            correlations = []

            for col in order_cols:
                pair_df = df.select([col, target]).drop_nulls()
                if len(pair_df) < 100:
                    continue
                corr = pair_df.select(pl.corr(col, target)).item()
                if corr is not None and not np.isnan(corr):
                    correlations.append((col, corr))

            correlations.sort(key=lambda x: -abs(x[1]))

            results.append("")
            results.append(f"Top {order_name} predictors for {horizon}-hour return:")
            for col, corr in correlations[:10]:
                indicator = col.replace(f"_{order_name.lower()}_zscore", "")
                sign = "+" if corr > 0 else ""
                results.append(f"  {indicator:40} {sign}{corr:.6f}")

    # ======================================================================
    # PART 2: DO SNAP/CRACKLE/POP LEAD LOWER-ORDER DERIVATIVES?
    # ======================================================================
    results.append("")
    results.append("=" * 80)
    results.append("PART 2: DO SNAP/CRACKLE/POP LEAD LOWER-ORDER DERIVATIVES?")
    results.append("(i.e., does current pop predict future velocity?)")
    results.append("=" * 80)

    lags = [1, 3, 5, 10]  # hours ahead

    results.append("")
    results.append("--- CLOSE price derivatives lead-lag ---")

    for high_order, high_col in [
        ("pop", "close_pop_zscore"),
        ("crackle", "close_crackle_zscore"),
        ("snap", "close_snap_zscore"),
    ]:
        if high_col not in df.columns:
            continue

        results.append("")
        results.append(f"{high_order.upper()} leading other derivatives:")

        for low_order, low_col in [
            ("velocity", "close_velocity_zscore"),
            ("acceleration", "close_acceleration_zscore"),
            ("jerk", "close_jerk_zscore"),
        ]:
            if low_col not in df.columns:
                continue

            results.append(f"  {high_order} -> {low_order}:")
            for lag in lags:
                df_lag = df.with_columns([pl.col(low_col).shift(-lag).alias("future_low")])
                pair_df = df_lag.select([high_col, "future_low"]).drop_nulls()
                if len(pair_df) < 100:
                    continue
                corr = pair_df.select(pl.corr(high_col, "future_low")).item()
                if corr is not None and not np.isnan(corr):
                    sign = "+" if corr > 0 else ""
                    results.append(f"    lag={lag}h: {sign}{corr:.4f}")

    # ======================================================================
    # PART 3: DO HIGHER DERIVATIVES OF INDICATORS LEAD PRICE?
    # ======================================================================
    results.append("")
    results.append("=" * 80)
    results.append("PART 3: DO HIGHER DERIVATIVES OF INDICATORS LEAD PRICE?")
    results.append("(i.e., does RSI snap predict close velocity?)")
    results.append("=" * 80)

    indicator_list = ["rsi_14", "macd_histogram", "obv", "atr_14"]
    close_vel = "close_velocity_zscore"

    for ind in indicator_list:
        ind_snap = f"{ind}_snap_zscore"
        ind_crackle = f"{ind}_crackle_zscore"
        ind_pop = f"{ind}_pop_zscore"

        if ind_snap not in df.columns:
            continue

        results.append("")
        results.append(f"{ind.upper()} higher derivatives leading CLOSE velocity:")

        for high_col, name in [(ind_snap, "snap"), (ind_crackle, "crackle"), (ind_pop, "pop")]:
            if high_col not in df.columns or close_vel not in df.columns:
                continue

            results.append(f"  {name}:")
            for lag in lags:
                df_lag = df.with_columns([pl.col(close_vel).shift(-lag).alias("future_close_vel")])
                pair_df = df_lag.select([high_col, "future_close_vel"]).drop_nulls()
                if len(pair_df) < 100:
                    continue
                corr = pair_df.select(pl.corr(high_col, "future_close_vel")).item()
                if corr is not None and not np.isnan(corr):
                    sign = "+" if corr > 0 else ""
                    results.append(f"    lag={lag}h: {sign}{corr:.4f}")

    # ======================================================================
    # PART 4: EXTREME VALUE PREDICTION
    # ======================================================================
    results.append("")
    results.append("=" * 80)
    results.append("PART 4: EXTREME VALUE PREDICTION")
    results.append("What happens when snap/crackle/pop are extreme?")
    results.append("=" * 80)

    for high_col, name in [
        ("close_snap_zscore", "SNAP"),
        ("close_crackle_zscore", "CRACKLE"),
        ("close_pop_zscore", "POP"),
    ]:
        if high_col not in df.columns:
            continue

        results.append("")
        results.append(f"{name} extreme values (z-score > 2 or < -2):")

        extreme_high = df.filter(pl.col(high_col) > 2)
        extreme_low = df.filter(pl.col(high_col) < -2)
        normal = df.filter((pl.col(high_col) >= -2) & (pl.col(high_col) <= 2))

        for horizon in [10, 30]:
            target = f"fwd_return_{horizon}"

            high_mean = extreme_high.select(pl.col(target).mean()).item() if len(extreme_high) > 0 else None
            low_mean = extreme_low.select(pl.col(target).mean()).item() if len(extreme_low) > 0 else None
            normal_mean = normal.select(pl.col(target).mean()).item() if len(normal) > 0 else None

            results.append(f"  {horizon}h forward return:")
            if high_mean is not None:
                results.append(f"    Extreme HIGH (z>2):  n={len(extreme_high):5}, mean={high_mean:.4f}%")
            else:
                results.append(f"    Extreme HIGH: n={len(extreme_high)}")
            if low_mean is not None:
                results.append(f"    Extreme LOW (z<-2):  n={len(extreme_low):5}, mean={low_mean:.4f}%")
            else:
                results.append(f"    Extreme LOW: n={len(extreme_low)}")
            if normal_mean is not None:
                results.append(f"    Normal (-2<z<2):     n={len(normal):5}, mean={normal_mean:.4f}%")
            else:
                results.append(f"    Normal: n={len(normal)}")

    # ======================================================================
    # PART 5: CROSS-TIMEFRAME ANALYSIS (if data available)
    # ======================================================================
    results.append("")
    results.append("=" * 80)
    results.append("PART 5: COMPARISON ACROSS DERIVATIVES")
    results.append("Which derivative order is most predictive?")
    results.append("=" * 80)

    # Compare all orders for close price
    orders = [
        ("velocity", "close_velocity_zscore"),
        ("acceleration", "close_acceleration_zscore"),
        ("jerk", "close_jerk_zscore"),
        ("snap", "close_snap_zscore"),
        ("crackle", "close_crackle_zscore"),
        ("pop", "close_pop_zscore"),
    ]

    for horizon in [10, 30]:
        target = f"fwd_return_{horizon}"
        results.append("")
        results.append(f"Close derivatives -> {horizon}h forward return:")

        for order_name, col in orders:
            if col not in df.columns:
                continue
            pair_df = df.select([col, target]).drop_nulls()
            if len(pair_df) < 100:
                continue
            corr = pair_df.select(pl.corr(col, target)).item()
            if corr is not None and not np.isnan(corr):
                sign = "+" if corr > 0 else ""
                bar = "#" * int(abs(corr) * 200)  # Visual bar
                results.append(f"  {order_name:15} {sign}{corr:.4f} {bar}")

    # Write results
    results_file = RESULTS_DIR / "snap_crackle_pop_analysis.txt"
    with open(results_file, "w") as f:
        f.write("\n".join(results))

    print(f"\nResults written to: {results_file}")
    print(f"Total lines: {len(results)}")

    # Also print to stdout
    print("\n" + "\n".join(results))


if __name__ == "__main__":
    main()
