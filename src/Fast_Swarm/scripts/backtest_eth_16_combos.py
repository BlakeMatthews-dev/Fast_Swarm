"""
ETH 16-Combination Backtest.

Tests top 4 exit filters × top 4 entry filters on ETH data.
Based on discoveries from BTC MTF analysis.
"""

import polars as pl
import numpy as np
from pathlib import Path

DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")


def load_mtf(symbol: str = "ETH"):
    """Load and align 1h, 4h, 1d data for given symbol."""
    base_path = DERIVATIVES_DIR / f"symbol={symbol}"

    df_1h = pl.read_parquet(base_path / "timeframe=1h").sort("time")
    df_4h = pl.read_parquet(base_path / "timeframe=4h").sort("time")
    df_1d = pl.read_parquet(base_path / "timeframe=1d").sort("time")

    cols_to_join = [
        "close_velocity_zscore", "close_acceleration_zscore",
        "adx_14_jerk_zscore", "adx_14_velocity_zscore", "adx_14_acceleration_zscore",
        "macd_histogram_velocity_zscore", "rsi_14_acceleration_zscore"
    ]

    df_4h_join = df_4h.select(
        [pl.col("time").alias("tf_4h_time")] +
        [pl.col(c).alias(f"tf_4h_{c}") for c in cols_to_join if c in df_4h.columns]
    )
    df_1d_join = df_1d.select(
        [pl.col("time").alias("tf_1d_time")] +
        [pl.col(c).alias(f"tf_1d_{c}") for c in cols_to_join if c in df_1d.columns]
    )

    result = df_1h.join_asof(df_4h_join, left_on="time", right_on="tf_4h_time", strategy="backward")
    result = result.join_asof(df_1d_join, left_on="time", right_on="tf_1d_time", strategy="backward")

    for c in cols_to_join:
        if c in result.columns:
            result = result.rename({c: f"tf_1h_{c}"})

    return result


def safe_get(row, col, default=0):
    v = row.get(col)
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return default
    return v


def count_tf_exit(row, extra_filter=None):
    """Count TFs where exit signal fires."""
    count = 0
    for tf in ["1h", "4h", "1d"]:
        vel = safe_get(row, f"tf_{tf}_close_velocity_zscore")
        acc = safe_get(row, f"tf_{tf}_close_acceleration_zscore")

        if vel > 0.5 and acc < -1.5:
            if extra_filter:
                if extra_filter(row, tf):
                    count += 1
            else:
                count += 1
    return count


def count_tf_entry(row, extra_filter=None):
    """Count TFs where entry signal fires."""
    count = 0
    for tf in ["1h", "4h", "1d"]:
        vel = safe_get(row, f"tf_{tf}_close_velocity_zscore")
        acc = safe_get(row, f"tf_{tf}_close_acceleration_zscore")

        if vel < -1.5 and acc > 3.0:
            if extra_filter:
                if extra_filter(row, tf):
                    count += 1
            else:
                count += 1
    return count


def run_backtest(df, exit_filter=None, entry_filter=None, min_exit_tf=1, min_entry_tf=1, max_cash_days=30):
    rows = df.to_dicts()
    initial_price = rows[0].get("close", 1)
    capital = 10000.0
    shares = capital / initial_price
    cash = 0
    is_long = True
    equity = [capital]
    exits = 0
    cash_start_idx = None

    for i, row in enumerate(rows):
        price = row.get("close", 0)
        if price <= 0:
            continue

        if is_long:
            exit_count = count_tf_exit(row, exit_filter)
            if exit_count >= min_exit_tf:
                cash = shares * price
                shares = 0
                is_long = False
                cash_start_idx = i
                exits += 1
        else:
            hours_in_cash = i - cash_start_idx if cash_start_idx else 0
            days_in_cash = hours_in_cash / 24
            force = days_in_cash > max_cash_days

            entry_count = count_tf_entry(row, entry_filter)
            if entry_count >= min_entry_tf or force:
                shares = cash / price
                cash = 0
                is_long = True

        equity.append(shares * price if is_long else cash)

    final_price = rows[-1].get("close", 1)
    final_eq = shares * final_price if is_long else cash
    ret = (final_eq / capital - 1) * 100
    bh_ret = (final_price / initial_price - 1) * 100

    peak = equity[0]
    max_dd = 0
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak
        if dd > max_dd:
            max_dd = dd

    daily_rets = [equity[i] / equity[i - 24] - 1 for i in range(24, len(equity), 24) if equity[i - 24] > 0]
    neg = [r for r in daily_rets if r < 0]
    ds = np.std(neg) if neg else 0.001
    sortino = (np.mean(daily_rets) / ds * np.sqrt(365)) if ds > 0 else 0

    return {"return": ret, "alpha": ret - bh_ret, "max_dd": max_dd * 100, "sortino": sortino, "exits": exits}


# ============================================================
# EXIT FILTERS (Top 4 from BTC analysis)
# ============================================================

def exit_adx_jerk_neg(row, tf):
    """adx_jerk < 0 - Best single filter"""
    return safe_get(row, f"tf_{tf}_adx_14_jerk_zscore") < 0

def exit_adx_jerk_and_rsi(row, tf):
    """adx_jerk < 0 AND rsi_acc < -1.94"""
    jerk = safe_get(row, f"tf_{tf}_adx_14_jerk_zscore") < 0
    rsi = safe_get(row, f"tf_{tf}_rsi_14_acceleration_zscore") < -1.94
    return jerk and rsi

def exit_adx_jerk_or_macd(row, tf):
    """adx_jerk < 0 OR macd_vel < 1.05 - Best risk-adjusted"""
    jerk = safe_get(row, f"tf_{tf}_adx_14_jerk_zscore") < 0
    macd = safe_get(row, f"tf_{tf}_macd_histogram_velocity_zscore") < 1.05
    return jerk or macd

# No extra filter (base exit only)
def exit_none(row, tf):
    return True


# ============================================================
# ENTRY FILTERS (Top 4 from BTC analysis)
# ============================================================

def entry_adx_acc_high(row, tf):
    """adx_acc > 0.67"""
    return safe_get(row, f"tf_{tf}_adx_14_acceleration_zscore") > 0.67

def entry_adx_jerk_neg(row, tf):
    """adx_jerk < -0.32"""
    return safe_get(row, f"tf_{tf}_adx_14_jerk_zscore") < -0.32

def entry_either(row, tf):
    """adx_acc > 0.67 OR adx_jerk < -0.32"""
    return entry_adx_acc_high(row, tf) or entry_adx_jerk_neg(row, tf)

# No extra filter (base entry only)
# entry_filter=None


def main(symbol: str = "ETH"):
    print("=" * 100)
    print(f"{symbol} 16-COMBINATION BACKTEST")
    print("Top 4 Exit Filters x Top 4 Entry Filters")
    print("=" * 100)

    print(f"\nLoading {symbol} MTF data...")
    df = load_mtf(symbol)
    print(f"Rows: {len(df):,}")

    # Get time range
    times = df.select("time").to_series()
    print(f"Date range: {times.min()} to {times.max()}")

    # Define exit and entry options
    exit_options = [
        ("no_filter", None),
        ("adx_jerk<0", exit_adx_jerk_neg),
        ("jerk AND rsi", exit_adx_jerk_and_rsi),
        ("jerk OR macd", exit_adx_jerk_or_macd),
    ]

    entry_options = [
        ("base", None),
        ("adx_acc>0.67", entry_adx_acc_high),
        ("adx_jerk<-0.32", entry_adx_jerk_neg),
        ("acc OR jerk", entry_either),
    ]

    # Run all 16 combinations
    print("\n" + "=" * 100)
    print("FULL 16-COMBINATION MATRIX")
    print("=" * 100)

    results = {}

    # Header
    print(f"\n{'Exit \\ Entry':<20}", end="")
    for en_name, _ in entry_options:
        print(f"{en_name:>18}", end="")
    print()
    print("-" * 92)

    for ex_name, ex_filt in exit_options:
        print(f"{ex_name:<20}", end="")
        for en_name, en_filt in entry_options:
            r = run_backtest(df, exit_filter=ex_filt, entry_filter=en_filt, min_exit_tf=1, min_entry_tf=1)
            key = f"{ex_name} × {en_name}"
            results[key] = r
            print(f"{r['return']:>12.0f}% {r['sortino']:>4.1f}", end="")
        print()

    # Detailed results sorted by return
    print("\n" + "=" * 100)
    print("DETAILED RESULTS (Sorted by Return)")
    print("=" * 100)
    print(f"\n{'Combination':<40} {'Return':>10} {'Alpha':>10} {'MaxDD':>8} {'Sortino':>8} {'Exits':>6}")
    print("-" * 100)

    sorted_results = sorted(results.items(), key=lambda x: -x[1]["return"])
    for name, r in sorted_results:
        print(f"{name:<40} {r['return']:>9.0f}% {r['alpha']:>+9.0f}% {r['max_dd']:>7.1f}% {r['sortino']:>8.2f} {r['exits']:>6}")

    # Best by different metrics
    print("\n" + "=" * 100)
    print("BEST BY METRIC")
    print("=" * 100)

    best_return = max(results.items(), key=lambda x: x[1]["return"])
    best_sortino = max(results.items(), key=lambda x: x[1]["sortino"])
    best_alpha = max(results.items(), key=lambda x: x[1]["alpha"])
    lowest_dd = min(results.items(), key=lambda x: x[1]["max_dd"])

    print(f"\nBest Return:  {best_return[0]} -> {best_return[1]['return']:.0f}%")
    print(f"Best Sortino: {best_sortino[0]} -> {best_sortino[1]['sortino']:.2f}")
    print(f"Best Alpha:   {best_alpha[0]} -> {best_alpha[1]['alpha']:+.0f}%")
    print(f"Lowest MaxDD: {lowest_dd[0]} -> {lowest_dd[1]['max_dd']:.1f}%")

    # Compare to BTC
    print("\n" + "=" * 100)
    print(f"BTC vs {symbol} COMPARISON (same strategy)")
    print("=" * 100)

    print("\nLoading BTC for comparison...")
    df_btc = load_mtf("BTC")

    # Run best ETH strategy on BTC
    best_ex_name, best_ex_filt = None, None
    best_en_name, best_en_filt = None, None

    # Parse best strategy
    best_combo = best_return[0]
    ex_part, en_part = best_combo.split(" × ")

    for name, filt in exit_options:
        if name == ex_part:
            best_ex_name, best_ex_filt = name, filt
    for name, filt in entry_options:
        if name == en_part:
            best_en_name, best_en_filt = name, filt

    btc_result = run_backtest(df_btc, exit_filter=best_ex_filt, entry_filter=best_en_filt, min_exit_tf=1, min_entry_tf=1)
    sym_result = best_return[1]

    print(f"\nStrategy: {best_combo}")
    print(f"{'Metric':<15} {'BTC':>12} {symbol:>12}")
    print("-" * 42)
    print(f"{'Return':<15} {btc_result['return']:>11.0f}% {sym_result['return']:>11.0f}%")
    print(f"{'Alpha':<15} {btc_result['alpha']:>+11.0f}% {sym_result['alpha']:>+11.0f}%")
    print(f"{'Max DD':<15} {btc_result['max_dd']:>11.1f}% {sym_result['max_dd']:>11.1f}%")
    print(f"{'Sortino':<15} {btc_result['sortino']:>12.2f} {sym_result['sortino']:>12.2f}")
    print(f"{'Exits':<15} {btc_result['exits']:>12} {sym_result['exits']:>12}")


if __name__ == "__main__":
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else "ETH"
    main(symbol)
