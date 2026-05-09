"""
Deep Analysis of Motion Derivatives

This script analyzes the computed derivatives to find predictive signals.
Focus areas:
1. Accel-Jerk divergence (the core hypothesis)
2. Higher-order derivatives (snap, crackle, pop) - the novel part
3. Multiple indicators beyond just price
4. Forward return prediction at multiple horizons

Author: Coinswarm Research
"""

import polars as pl
import numpy as np
from pathlib import Path
from datetime import datetime
import json

# Paths
DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")
RESULTS_DIR = Path("c:/fast_swarm/data/analysis_results")
RESULTS_DIR.mkdir(exist_ok=True)


def load_derivatives(
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    sample_frac: float | None = None
) -> pl.DataFrame:
    """
    Load derivatives from partitioned Parquet files.

    Args:
        symbols: Filter to specific symbols (None = all)
        timeframes: Filter to specific timeframes (None = all)
        sample_frac: Random sample fraction (None = all data)
    """
    print("Loading derivatives data...")

    # Build path pattern
    if symbols and timeframes:
        # Load specific combinations
        dfs = []
        for sym in symbols:
            for tf in timeframes:
                path = DERIVATIVES_DIR / f"symbol={sym}" / f"timeframe={tf}"
                if path.exists():
                    df = pl.read_parquet(path)
                    dfs.append(df)
                    print(f"  Loaded {sym}/{tf}: {len(df):,} rows")
        if not dfs:
            raise ValueError("No data found for specified symbols/timeframes")
        df = pl.concat(dfs)
    else:
        # Load all data
        df = pl.read_parquet(DERIVATIVES_DIR)

    print(f"  Total: {len(df):,} rows, {len(df.columns)} columns")

    if sample_frac:
        df = df.sample(fraction=sample_frac, seed=42)
        print(f"  Sampled to: {len(df):,} rows")

    return df


def add_forward_returns(df: pl.DataFrame, horizons: list[int] = [1, 5, 10, 30, 60]) -> pl.DataFrame:
    """
    Add forward return columns for multiple horizons.

    Forward return = (future_close - current_close) / current_close
    """
    print(f"Adding forward returns for horizons: {horizons}")

    for h in horizons:
        df = df.with_columns([
            # Percentage return
            ((pl.col("close").shift(-h) - pl.col("close")) / pl.col("close") * 100)
            .alias(f"fwd_return_{h}"),

            # Binary direction (1 = up, 0 = down)
            (pl.col("close").shift(-h) > pl.col("close"))
            .cast(pl.Int8)
            .alias(f"fwd_up_{h}"),
        ])

    return df


def get_derivative_columns(df: pl.DataFrame, order: str | None = None) -> list[str]:
    """
    Get derivative column names.

    Args:
        order: Filter to specific order ("velocity", "acceleration", "jerk", "snap", "crackle", "pop")
               None = all derivatives
    """
    all_derivs = ["velocity", "acceleration", "jerk", "snap", "crackle", "pop"]

    if order:
        orders = [order]
    else:
        orders = all_derivs

    cols = []
    for col in df.columns:
        for o in orders:
            if f"_{o}" in col and "_zscore" not in col and "_div" not in col:
                cols.append(col)
                break

    return cols


def get_zscore_columns(df: pl.DataFrame, order: str | None = None) -> list[str]:
    """Get z-score normalized derivative columns."""
    all_derivs = ["velocity", "acceleration", "jerk", "snap", "crackle", "pop"]

    if order:
        orders = [order]
    else:
        orders = all_derivs

    cols = []
    for col in df.columns:
        if "_zscore" in col:
            for o in orders:
                if f"_{o}_zscore" in col:
                    cols.append(col)
                    break

    return cols


def analyze_forward_correlation(
    df: pl.DataFrame,
    horizons: list[int] = [1, 5, 10, 30],
    top_n: int = 30
) -> dict:
    """
    Find which derivatives correlate with future returns.

    This is THE most important analysis - directly answers
    "what predicts price movement?"
    """
    print("\n" + "="*60)
    print("FORWARD RETURN CORRELATION ANALYSIS")
    print("="*60)

    # Get all derivative columns (use z-scores for comparability)
    deriv_cols = get_zscore_columns(df)
    print(f"Analyzing {len(deriv_cols)} derivative features...")

    results = {}

    for horizon in horizons:
        target = f"fwd_return_{horizon}"
        print(f"\n--- Horizon: {horizon} candles ---")

        # Filter to rows with valid target
        valid_df = df.filter(pl.col(target).is_not_null())
        n_valid = len(valid_df)
        print(f"  Valid samples: {n_valid:,}")

        correlations = []

        for col in deriv_cols:
            # Get non-null pairs
            pair_df = valid_df.select([col, target]).drop_nulls()

            if len(pair_df) < 100:
                continue

            # Compute correlation
            corr = pair_df.select(pl.corr(col, target)).item()

            if corr is not None and not np.isnan(corr):
                correlations.append({
                    "feature": col,
                    "correlation": corr,
                    "abs_corr": abs(corr),
                    "n_samples": len(pair_df),
                    "direction": "positive" if corr > 0 else "negative"
                })

        # Sort by absolute correlation
        correlations.sort(key=lambda x: -x["abs_corr"])

        # Print top results
        print(f"  Top {min(top_n, len(correlations))} predictors:")
        for i, c in enumerate(correlations[:top_n]):
            sign = "+" if c["correlation"] > 0 else ""
            print(f"    {i+1:2}. {c['feature'][:50]:50} {sign}{c['correlation']:.4f} (n={c['n_samples']:,})")

        results[horizon] = correlations[:top_n]

    return results


def analyze_accel_jerk_divergence(
    df: pl.DataFrame,
    indicators: list[str] = ["close", "rsi_14", "macd_histogram", "obv"]
) -> dict:
    """
    Analyze the core hypothesis: accel-jerk divergence predicts regime change.

    Divergence = when acceleration and jerk have opposite signs.
    Theory: This indicates the rate of change is slowing, predicting reversal.
    """
    print("\n" + "="*60)
    print("ACCEL-JERK DIVERGENCE ANALYSIS")
    print("="*60)
    print("Hypothesis: When accel and jerk have opposite signs, regime change is imminent")

    results = {}

    for indicator in indicators:
        accel_col = f"{indicator}_acceleration"
        jerk_col = f"{indicator}_jerk"

        if accel_col not in df.columns or jerk_col not in df.columns:
            print(f"\n  Skipping {indicator} (columns not found)")
            continue

        print(f"\n--- Indicator: {indicator} ---")

        # Create divergence flag
        df_analysis = df.with_columns([
            # Divergence: opposite signs
            ((pl.col(accel_col) > 0) != (pl.col(jerk_col) > 0))
            .alias("divergent"),

            # Sign of each
            pl.when(pl.col(accel_col) > 0).then(1).otherwise(-1).alias("accel_sign"),
            pl.when(pl.col(jerk_col) > 0).then(1).otherwise(-1).alias("jerk_sign"),
        ])

        # Filter to valid rows
        valid_df = df_analysis.filter(
            pl.col(accel_col).is_not_null() &
            pl.col(jerk_col).is_not_null() &
            pl.col("fwd_return_10").is_not_null()
        )

        n_total = len(valid_df)
        n_divergent = valid_df.filter(pl.col("divergent")).height
        n_aligned = n_total - n_divergent

        print(f"  Total valid samples: {n_total:,}")
        print(f"  Divergent (opposite signs): {n_divergent:,} ({n_divergent/n_total*100:.1f}%)")
        print(f"  Aligned (same signs): {n_aligned:,} ({n_aligned/n_total*100:.1f}%)")

        # Compare outcomes
        for horizon in [5, 10, 30]:
            target = f"fwd_return_{horizon}"
            target_up = f"fwd_up_{horizon}"

            if target not in df.columns:
                continue

            div_stats = valid_df.filter(pl.col("divergent")).select([
                pl.col(target).mean().alias("mean_return"),
                pl.col(target).std().alias("std_return"),
                pl.col(target_up).mean().alias("p_up"),
                pl.len().alias("n")
            ]).to_dicts()[0] if n_divergent > 0 else {}

            align_stats = valid_df.filter(~pl.col("divergent")).select([
                pl.col(target).mean().alias("mean_return"),
                pl.col(target).std().alias("std_return"),
                pl.col(target_up).mean().alias("p_up"),
                pl.len().alias("n")
            ]).to_dicts()[0] if n_aligned > 0 else {}

            print(f"\n  Forward {horizon} candles:")
            if div_stats:
                print(f"    Divergent: mean={div_stats['mean_return']:.4f}%, p(up)={div_stats['p_up']*100:.1f}%")
            if align_stats:
                print(f"    Aligned:   mean={align_stats['mean_return']:.4f}%, p(up)={align_stats['p_up']*100:.1f}%")

            if div_stats and align_stats:
                edge = div_stats['p_up'] - align_stats['p_up']
                print(f"    Edge (divergent vs aligned): {edge*100:+.2f}%")

        # Detailed breakdown by divergence type
        print(f"\n  Divergence type breakdown (10-candle horizon):")

        # Type 1: Accel positive, Jerk negative (slowing up-move)
        type1 = valid_df.filter(
            (pl.col("accel_sign") == 1) & (pl.col("jerk_sign") == -1)
        )
        if len(type1) > 0:
            stats = type1.select([pl.col("fwd_up_10").mean()]).item()
            print(f"    Accel+ Jerk- (slowing uptrend): n={len(type1):,}, p(up)={stats*100:.1f}%")

        # Type 2: Accel negative, Jerk positive (slowing down-move)
        type2 = valid_df.filter(
            (pl.col("accel_sign") == -1) & (pl.col("jerk_sign") == 1)
        )
        if len(type2) > 0:
            stats = type2.select([pl.col("fwd_up_10").mean()]).item()
            print(f"    Accel- Jerk+ (slowing downtrend): n={len(type2):,}, p(up)={stats*100:.1f}%")

        results[indicator] = {
            "n_total": n_total,
            "n_divergent": n_divergent,
            "pct_divergent": n_divergent / n_total * 100 if n_total > 0 else 0,
        }

    return results


def analyze_higher_order_derivatives(
    df: pl.DataFrame,
    horizons: list[int] = [5, 10, 30]
) -> dict:
    """
    Analyze snap, crackle, and pop - the NOVEL part of this research.

    These are 4th, 5th, and 6th order derivatives that aren't used
    in traditional technical analysis.
    """
    print("\n" + "="*60)
    print("HIGHER-ORDER DERIVATIVES ANALYSIS (SNAP, CRACKLE, POP)")
    print("="*60)
    print("These are 4th-6th order derivatives - largely unexplored in trading")

    results = {}

    for order in ["snap", "crackle", "pop"]:
        print(f"\n{'='*40}")
        print(f"  {order.upper()} (derivative order: {['snap','crackle','pop'].index(order) + 4})")
        print(f"{'='*40}")

        # Get all columns for this order
        order_cols = [c for c in df.columns if f"_{order}_zscore" in c]
        print(f"  Found {len(order_cols)} {order} columns")

        if not order_cols:
            continue

        # Find best predictors for each horizon
        for horizon in horizons:
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

            print(f"\n  Top {order} predictors for {horizon}-candle return:")
            for col, corr in correlations[:5]:
                indicator = col.replace(f"_{order}_zscore", "")
                sign = "+" if corr > 0 else ""
                print(f"    {indicator:30} {sign}{corr:.4f}")

        results[order] = {
            "n_columns": len(order_cols),
            "columns": order_cols[:10]  # Sample
        }

    return results


def analyze_extreme_values(
    df: pl.DataFrame,
    percentile: float = 95,
    horizons: list[int] = [5, 10, 30]
) -> dict:
    """
    What happens after extreme derivative values?

    When jerk/snap/crackle/pop is in the extreme percentile,
    does it predict reversal or continuation?
    """
    print("\n" + "="*60)
    print(f"EXTREME VALUE ANALYSIS (>{percentile}th percentile)")
    print("="*60)

    results = {}

    # Key derivatives to analyze
    key_cols = [
        "close_jerk_zscore",
        "close_snap_zscore",
        "close_crackle_zscore",
        "close_pop_zscore",
        "rsi_14_jerk_zscore",
        "macd_histogram_jerk_zscore",
    ]

    key_cols = [c for c in key_cols if c in df.columns]

    for col in key_cols:
        print(f"\n--- {col} ---")

        # Get threshold
        valid_df = df.filter(pl.col(col).is_not_null())
        high_thresh = valid_df.select(pl.col(col).quantile(percentile/100)).item()
        low_thresh = valid_df.select(pl.col(col).quantile((100-percentile)/100)).item()

        print(f"  Thresholds: low={low_thresh:.2f}, high={high_thresh:.2f}")

        for horizon in horizons:
            target = f"fwd_return_{horizon}"
            target_up = f"fwd_up_{horizon}"

            # Extreme high
            high_df = valid_df.filter(pl.col(col) > high_thresh)
            # Extreme low
            low_df = valid_df.filter(pl.col(col) < low_thresh)
            # Normal
            normal_df = valid_df.filter(
                (pl.col(col) >= low_thresh) & (pl.col(col) <= high_thresh)
            )

            def get_stats(subset):
                if len(subset) == 0:
                    return None
                return subset.select([
                    pl.col(target).mean().alias("mean"),
                    pl.col(target_up).mean().alias("p_up"),
                    pl.len().alias("n")
                ]).to_dicts()[0]

            high_stats = get_stats(high_df)
            low_stats = get_stats(low_df)
            normal_stats = get_stats(normal_df)

            print(f"\n  {horizon}-candle forward:")
            if high_stats:
                print(f"    Extreme HIGH (>{percentile}%ile): n={high_stats['n']:,}, p(up)={high_stats['p_up']*100:.1f}%, mean={high_stats['mean']:.3f}%")
            if low_stats:
                print(f"    Extreme LOW  (<{100-percentile}%ile): n={low_stats['n']:,}, p(up)={low_stats['p_up']*100:.1f}%, mean={low_stats['mean']:.3f}%")
            if normal_stats:
                print(f"    Normal:                   n={normal_stats['n']:,}, p(up)={normal_stats['p_up']*100:.1f}%, mean={normal_stats['mean']:.3f}%")

        results[col] = {
            "high_threshold": high_thresh,
            "low_threshold": low_thresh,
        }

    return results


def analyze_cross_indicator_divergence(
    df: pl.DataFrame,
    horizons: list[int] = [5, 10, 30]
) -> dict:
    """
    Do price derivatives diverging from momentum indicator derivatives predict moves?

    E.g., price jerk positive but RSI jerk negative = bearish divergence?
    """
    print("\n" + "="*60)
    print("CROSS-INDICATOR DIVERGENCE ANALYSIS")
    print("="*60)
    print("When price derivatives diverge from momentum indicators...")

    results = {}

    pairs = [
        ("close_jerk", "rsi_14_jerk", "Price vs RSI"),
        ("close_jerk", "macd_histogram_jerk", "Price vs MACD"),
        ("close_acceleration", "rsi_14_acceleration", "Price Accel vs RSI Accel"),
        ("close_snap", "rsi_14_snap", "Price Snap vs RSI Snap"),
    ]

    for col1, col2, name in pairs:
        if col1 not in df.columns or col2 not in df.columns:
            print(f"\n  Skipping {name} (columns not found)")
            continue

        print(f"\n--- {name} ---")

        # Create divergence
        valid_df = df.filter(
            pl.col(col1).is_not_null() &
            pl.col(col2).is_not_null() &
            pl.col("fwd_return_10").is_not_null()
        ).with_columns([
            ((pl.col(col1) > 0) != (pl.col(col2) > 0)).alias("divergent")
        ])

        n_total = len(valid_df)
        n_div = valid_df.filter(pl.col("divergent")).height

        print(f"  Total: {n_total:,}, Divergent: {n_div:,} ({n_div/n_total*100:.1f}%)")

        for horizon in horizons:
            target_up = f"fwd_up_{horizon}"

            div_p = valid_df.filter(pl.col("divergent")).select(pl.col(target_up).mean()).item()
            align_p = valid_df.filter(~pl.col("divergent")).select(pl.col(target_up).mean()).item()

            edge = (div_p - align_p) * 100 if div_p and align_p else 0
            print(f"  {horizon}-candle: Divergent p(up)={div_p*100:.1f}%, Aligned p(up)={align_p*100:.1f}%, Edge={edge:+.2f}%")

        results[name] = {"n_divergent": n_div, "pct": n_div/n_total*100}

    return results


def generate_summary_report(all_results: dict) -> str:
    """Generate a human-readable summary report."""

    lines = [
        "=" * 70,
        "MOTION DERIVATIVES ANALYSIS - SUMMARY REPORT",
        f"Generated: {datetime.now().isoformat()}",
        "=" * 70,
        "",
    ]

    # Forward correlation highlights
    if "forward_correlation" in all_results:
        lines.append("TOP PREDICTIVE FEATURES (by forward correlation):")
        lines.append("-" * 50)
        for horizon, corrs in all_results["forward_correlation"].items():
            if corrs:
                top = corrs[0]
                lines.append(f"  {horizon}-candle: {top['feature'][:40]} (r={top['correlation']:.4f})")
        lines.append("")

    # Accel-jerk divergence
    if "accel_jerk" in all_results:
        lines.append("ACCEL-JERK DIVERGENCE RATES:")
        lines.append("-" * 50)
        for indicator, stats in all_results["accel_jerk"].items():
            lines.append(f"  {indicator}: {stats['pct_divergent']:.1f}% divergent")
        lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)


def main(
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    sample_frac: float | None = None
):
    """Run all analyses."""

    print("=" * 70)
    print("MOTION DERIVATIVES DEEP ANALYSIS")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)

    # Load data
    df = load_derivatives(symbols=symbols, timeframes=timeframes, sample_frac=sample_frac)

    # Add forward returns
    df = add_forward_returns(df, horizons=[1, 5, 10, 30, 60])

    all_results = {}

    # Run analyses
    all_results["forward_correlation"] = analyze_forward_correlation(df)
    all_results["accel_jerk"] = analyze_accel_jerk_divergence(df)
    all_results["higher_order"] = analyze_higher_order_derivatives(df)
    all_results["extreme_values"] = analyze_extreme_values(df)
    all_results["cross_indicator"] = analyze_cross_indicator_divergence(df)

    # Generate summary
    summary = generate_summary_report(all_results)
    print("\n" + summary)

    # Save results
    results_file = RESULTS_DIR / f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, "w") as f:
        # Convert to JSON-serializable format
        json_results = {}
        for k, v in all_results.items():
            if isinstance(v, dict):
                json_results[k] = {str(kk): vv for kk, vv in v.items()}
            else:
                json_results[k] = v
        json.dump(json_results, f, indent=2, default=str)
    print(f"\nResults saved to: {results_file}")

    print(f"\nCompleted: {datetime.now().isoformat()}")

    return all_results, df


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Analyze motion derivatives")
    parser.add_argument("--symbols", nargs="+", help="Filter to specific symbols")
    parser.add_argument("--timeframes", nargs="+", help="Filter to specific timeframes")
    parser.add_argument("--sample", type=float, help="Sample fraction (0-1)")

    args = parser.parse_args()

    main(
        symbols=args.symbols,
        timeframes=args.timeframes,
        sample_frac=args.sample
    )
