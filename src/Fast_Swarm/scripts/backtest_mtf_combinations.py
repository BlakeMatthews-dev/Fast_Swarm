"""
MTF Exit/Entry Combinations Backtest.

Tests all combinations of discovered filters with MTF base conditions.
"""

import polars as pl
import numpy as np
from pathlib import Path

DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")


def load_mtf():
    """Load and align 1h, 4h, 1d data."""
    df_1h = pl.read_parquet(DERIVATIVES_DIR / "symbol=BTC" / "timeframe=1h").sort("time")
    df_4h = pl.read_parquet(DERIVATIVES_DIR / "symbol=BTC" / "timeframe=4h").sort("time")
    df_1d = pl.read_parquet(DERIVATIVES_DIR / "symbol=BTC" / "timeframe=1d").sort("time")

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


# EXIT FILTERS
def adx_jerk_neg(row, tf):
    return safe_get(row, f"tf_{tf}_adx_14_jerk_zscore") < 0

def adx_vel_low(row, tf):
    return safe_get(row, f"tf_{tf}_adx_14_velocity_zscore") < -0.35

def macd_vel_low(row, tf):
    return safe_get(row, f"tf_{tf}_macd_histogram_velocity_zscore") < 1.05

def rsi_acc_low(row, tf):
    return safe_get(row, f"tf_{tf}_rsi_14_acceleration_zscore") < -1.94

def adx_jerk_and_rsi(row, tf):
    return adx_jerk_neg(row, tf) and rsi_acc_low(row, tf)

def adx_jerk_or_rsi(row, tf):
    return adx_jerk_neg(row, tf) or rsi_acc_low(row, tf)

def adx_jerk_and_macd(row, tf):
    return adx_jerk_neg(row, tf) and macd_vel_low(row, tf)

def all_three(row, tf):
    return adx_jerk_neg(row, tf) and macd_vel_low(row, tf) and rsi_acc_low(row, tf)

def adx_jerk_or_macd(row, tf):
    return adx_jerk_neg(row, tf) or macd_vel_low(row, tf)

def adx_vel_and_jerk(row, tf):
    return adx_vel_low(row, tf) and adx_jerk_neg(row, tf)


# ENTRY FILTERS
def entry_adx_acc_high(row, tf):
    return safe_get(row, f"tf_{tf}_adx_14_acceleration_zscore") > 0.67

def entry_adx_jerk_neg(row, tf):
    return safe_get(row, f"tf_{tf}_adx_14_jerk_zscore") < -0.32

def entry_both(row, tf):
    return entry_adx_acc_high(row, tf) and entry_adx_jerk_neg(row, tf)

def entry_either(row, tf):
    return entry_adx_acc_high(row, tf) or entry_adx_jerk_neg(row, tf)


def main():
    print("=" * 100)
    print("MTF EXIT/ENTRY COMBINATIONS BACKTEST")
    print("Hold BTC strategy - Exit on danger, Re-enter on opportunity")
    print("=" * 100)

    print("\nLoading MTF data...")
    df = load_mtf()
    print(f"Rows: {len(df):,}")

    # EXIT TESTS
    print("\n" + "=" * 100)
    print("EXIT FILTER COMBINATIONS")
    print("Base exit: vel > 0.5 AND acc < -1.5 (per timeframe)")
    print("=" * 100)
    print(f"{'Exit Filter':<50} {'Return':>10} {'Alpha':>10} {'MaxDD':>7} {'Sortino':>8} {'Exits':>6}")
    print("-" * 100)

    exit_tests = [
        ("No filter (1TF)", None, 1),
        ("No filter (2TF)", None, 2),
        ("+ adx_jerk < 0 (1TF)", adx_jerk_neg, 1),
        ("+ adx_jerk < 0 (2TF)", adx_jerk_neg, 2),
        ("+ adx_vel < -0.35 (1TF)", adx_vel_low, 1),
        ("+ macd_vel < 1.05 (1TF)", macd_vel_low, 1),
        ("+ rsi_acc < -1.94 (1TF)", rsi_acc_low, 1),
        ("+ adx_jerk AND rsi_acc (1TF)", adx_jerk_and_rsi, 1),
        ("+ adx_jerk OR rsi_acc (1TF)", adx_jerk_or_rsi, 1),
        ("+ adx_jerk AND macd (1TF)", adx_jerk_and_macd, 1),
        ("+ adx_jerk OR macd (1TF)", adx_jerk_or_macd, 1),
        ("+ adx_vel AND adx_jerk (1TF)", adx_vel_and_jerk, 1),
        ("+ ALL 3 (jerk AND macd AND rsi) (1TF)", all_three, 1),
    ]

    for name, filt, min_tf in exit_tests:
        r = run_backtest(df, exit_filter=filt, min_exit_tf=min_tf)
        print(f"{name:<50} {r['return']:>9.0f}% {r['alpha']:>+9.0f}% {r['max_dd']:>6.1f}% {r['sortino']:>8.2f} {r['exits']:>6}")

    # ENTRY TESTS with best exit
    print("\n" + "=" * 100)
    print("ENTRY FILTER COMBINATIONS (with best exit: adx_jerk < 0, 1TF)")
    print("Base entry: vel < -1.5 AND acc > 3.0")
    print("=" * 100)
    print(f"{'Entry Filter':<50} {'Return':>10} {'Alpha':>10} {'MaxDD':>7} {'Sortino':>8} {'Exits':>6}")
    print("-" * 100)

    entry_tests = [
        ("Base entry (1TF)", None, 1),
        ("Base entry (2TF)", None, 2),
        ("+ adx_acc > 0.67 (1TF)", entry_adx_acc_high, 1),
        ("+ adx_jerk < -0.32 (1TF)", entry_adx_jerk_neg, 1),
        ("+ adx_acc AND adx_jerk (1TF)", entry_both, 1),
        ("+ adx_acc OR adx_jerk (1TF)", entry_either, 1),
    ]

    for name, filt, min_tf in entry_tests:
        r = run_backtest(df, exit_filter=adx_jerk_neg, entry_filter=filt, min_exit_tf=1, min_entry_tf=min_tf)
        print(f"{name:<50} {r['return']:>9.0f}% {r['alpha']:>+9.0f}% {r['max_dd']:>6.1f}% {r['sortino']:>8.2f} {r['exits']:>6}")

    # FULL MATRIX: Best exits x Best entries
    print("\n" + "=" * 100)
    print("FULL MATRIX: Top Exit Filters x Entry Filters")
    print("=" * 100)

    best_exits = [
        ("adx_jerk<0", adx_jerk_neg),
        ("adx_jerk AND rsi", adx_jerk_and_rsi),
        ("adx_jerk AND macd", adx_jerk_and_macd),
    ]
    best_entries = [
        ("base", None),
        ("adx_acc>0.67", entry_adx_acc_high),
        ("adx_jerk<-0.32", entry_adx_jerk_neg),
    ]

    print(f"{'Exit \\ Entry':<25}", end="")
    for en, _ in best_entries:
        print(f"{en:>20}", end="")
    print()
    print("-" * 85)

    for ex_name, ex_filt in best_exits:
        print(f"{ex_name:<25}", end="")
        for en_name, en_filt in best_entries:
            r = run_backtest(df, exit_filter=ex_filt, entry_filter=en_filt, min_exit_tf=1, min_entry_tf=1)
            print(f"{r['return']:>15.0f}% {r['sortino']:>4.1f}", end="")
        print()


if __name__ == "__main__":
    main()
