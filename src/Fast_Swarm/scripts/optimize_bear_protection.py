"""
Optimize Bear Protection Thresholds.

Parameter sweep to find optimal exit/entry signal thresholds.
Tests different combinations on canonical crash periods.
"""

import polars as pl
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass
from itertools import product
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from Fast_Swarm.Infrastructure.Services.bear_protection_service import (
    BearProtectionService, MarketState, Regime, RegimeConfig
)

# Import canonical windows directly
import importlib.util
spec = importlib.util.spec_from_file_location(
    "canonical_windows",
    Path(__file__).parent.parent / "Tests" / "Fixtures" / "canonical_windows.py"
)
canonical_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(canonical_mod)
CANONICAL_WINDOWS = canonical_mod.CANONICAL_WINDOWS

DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")


def load_mtf_for_period(symbol: str, start: datetime, end: datetime):
    """Load MTF derivatives data for a specific time period."""
    base_path = DERIVATIVES_DIR / f"symbol={symbol}"

    df_1h = pl.read_parquet(base_path / "timeframe=1h").sort("time")
    df_4h = pl.read_parquet(base_path / "timeframe=4h").sort("time")
    df_1d = pl.read_parquet(base_path / "timeframe=1d").sort("time")

    start_tz = start.replace(tzinfo=timezone.utc)
    end_tz = end.replace(tzinfo=timezone.utc)

    df_1h = df_1h.filter(
        (pl.col("time") >= start_tz) & (pl.col("time") <= end_tz)
    )

    if len(df_1h) == 0:
        return None

    cols = ["close_velocity_zscore", "close_acceleration_zscore", "adx_14_jerk_zscore"]

    df_4h_join = df_4h.select(
        [pl.col("time").alias("tf_4h_time")]
        + [pl.col(c).alias(f"tf_4h_{c}") for c in cols if c in df_4h.columns]
    )
    df_1d_join = df_1d.select(
        [pl.col("time").alias("tf_1d_time")]
        + [pl.col(c).alias(f"tf_1d_{c}") for c in cols if c in df_1d.columns]
    )

    result = df_1h.join_asof(df_4h_join, left_on="time", right_on="tf_4h_time", strategy="backward")
    result = result.join_asof(df_1d_join, left_on="time", right_on="tf_1d_time", strategy="backward")

    for c in cols:
        if c in result.columns:
            result = result.rename({c: f"tf_1h_{c}"})

    return result


def row_to_market_state(row: dict, symbol: str) -> MarketState:
    """Convert dataframe row to MarketState."""
    return MarketState(
        time=row.get("time", datetime.now(timezone.utc)),
        symbol=symbol,
        tf_1h_vel=row.get("tf_1h_close_velocity_zscore"),
        tf_1h_acc=row.get("tf_1h_close_acceleration_zscore"),
        tf_1h_adx_jerk=row.get("tf_1h_adx_14_jerk_zscore"),
        tf_4h_vel=row.get("tf_4h_close_velocity_zscore"),
        tf_4h_acc=row.get("tf_4h_close_acceleration_zscore"),
        tf_4h_adx_jerk=row.get("tf_4h_adx_14_jerk_zscore"),
        tf_1d_vel=row.get("tf_1d_close_velocity_zscore"),
        tf_1d_acc=row.get("tf_1d_close_acceleration_zscore"),
        tf_1d_adx_jerk=row.get("tf_1d_adx_14_jerk_zscore"),
    )


def simulate_with_config(df, config: RegimeConfig):
    """
    Simulate Hold BTC strategy with given config.
    Returns metrics dict.
    """
    rows = df.to_dicts()
    service = BearProtectionService(config=config)

    btc_holdings = 1.0
    usd_holdings = 0.0
    start_price = rows[0].get("close", 1)

    peak = start_price
    max_dd = 0
    trades = 0
    last_regime = None

    for row in rows:
        price = row.get("close", 0)
        if price <= 0:
            continue

        state = row_to_market_state(row, "BTC")
        result = service.evaluate(state)
        regime = result.regime
        max_position = result.max_position

        if regime != last_regime:
            total_value = btc_holdings * price + usd_holdings
            target_btc_value = total_value * max_position
            target_btc = target_btc_value / price

            if regime == Regime.DEFENSIVE and last_regime != Regime.DEFENSIVE:
                btc_sold = btc_holdings - target_btc
                if btc_sold > 0:
                    usd_holdings += btc_sold * price
                    btc_holdings = target_btc
                    trades += 1

            elif regime == Regime.AGGRESSIVE and last_regime != Regime.AGGRESSIVE:
                if usd_holdings > 0:
                    btc_bought = usd_holdings / price
                    btc_holdings += btc_bought
                    usd_holdings = 0
                    trades += 1

            last_regime = regime

        # Track drawdown
        total_equity = btc_holdings * price + usd_holdings
        if total_equity > peak:
            peak = total_equity
        dd = (peak - total_equity) / peak
        if dd > max_dd:
            max_dd = dd

    end_price = rows[-1].get("close", start_price)
    end_equity = btc_holdings * end_price + usd_holdings

    bh_return = (end_price / start_price - 1) * 100
    strategy_return = (end_equity / start_price - 1) * 100

    return {
        "bh_return": bh_return,
        "strategy_return": strategy_return,
        "protection_value": strategy_return - bh_return,
        "max_dd": max_dd * 100,
        "trades": trades,
    }


def main():
    print("=" * 100)
    print("BEAR PROTECTION THRESHOLD OPTIMIZATION")
    print("=" * 100)

    # Load all crash period data
    crash_periods = [
        ("flash_crash_may2021", "Flash Crash"),
        ("luna_collapse", "Luna"),
        ("ftx_collapse", "FTX"),
        ("btc_2022_bear", "2022 Bear"),
    ]

    period_data = {}
    for period_key, period_name in crash_periods:
        window = CANONICAL_WINDOWS.get(period_key)
        if window:
            df = load_mtf_for_period("BTC", window.start, window.end)
            if df is not None and len(df) > 0:
                period_data[period_name] = df
                print(f"Loaded {period_name}: {len(df)} candles")

    if not period_data:
        print("No data loaded!")
        return

    # Parameter sweep ranges
    # Exit thresholds - "exiting further" means lower vel, higher acc (less negative)
    exit_vel_range = [0.0, 0.25, 0.5, 0.75, 1.0]  # Lower = exit earlier
    exit_acc_range = [-0.5, -1.0, -1.5, -2.0, -2.5]  # Higher (less negative) = exit earlier

    # Entry thresholds
    entry_vel_range = [-1.0, -1.5, -2.0]
    entry_acc_range = [2.0, 2.5, 3.0, 3.5]

    # Test all combinations
    results = []

    print(f"\nTesting {len(exit_vel_range) * len(exit_acc_range) * len(entry_vel_range) * len(entry_acc_range)} parameter combinations...")

    for exit_vel, exit_acc, entry_vel, entry_acc in product(
        exit_vel_range, exit_acc_range, entry_vel_range, entry_acc_range
    ):
        config = RegimeConfig(
            exit_vel_threshold=exit_vel,
            exit_acc_threshold=exit_acc,
            entry_vel_threshold=entry_vel,
            entry_acc_threshold=entry_acc,
        )

        total_protection = 0
        total_dd_saved = 0
        period_results = {}

        for name, df in period_data.items():
            metrics = simulate_with_config(df, config)
            period_results[name] = metrics
            total_protection += metrics["protection_value"]
            # Compare DD vs baseline (we'll compute baseline separately)

        results.append({
            "exit_vel": exit_vel,
            "exit_acc": exit_acc,
            "entry_vel": entry_vel,
            "entry_acc": entry_acc,
            "total_protection": total_protection,
            "periods": period_results,
        })

    # Sort by total protection value
    results.sort(key=lambda x: -x["total_protection"])

    # Show top 10
    print("\n" + "=" * 100)
    print("TOP 10 PARAMETER COMBINATIONS (by total protection across crash periods)")
    print("=" * 100)

    print(f"\n{'Rank':<5} {'Exit Vel':<10} {'Exit Acc':<10} {'Entry Vel':<10} {'Entry Acc':<10} {'Total Protection':>18}")
    print("-" * 70)

    for i, r in enumerate(results[:10], 1):
        print(f"{i:<5} {r['exit_vel']:<10.2f} {r['exit_acc']:<10.2f} {r['entry_vel']:<10.2f} {r['entry_acc']:<10.2f} {r['total_protection']:>+17.1f}%")

    # Show detailed breakdown for #1
    best = results[0]
    print("\n" + "=" * 100)
    print("BEST CONFIGURATION - DETAILED BREAKDOWN")
    print("=" * 100)

    print(f"\nExit Signal: vel > {best['exit_vel']} AND acc < {best['exit_acc']} AND adx_jerk < 0")
    print(f"Entry Signal: vel < {best['entry_vel']} AND acc > {best['entry_acc']}")

    print(f"\n{'Period':<15} {'B&H':>10} {'Strategy':>10} {'Protection':>12} {'Max DD':>10} {'Trades':>8}")
    print("-" * 70)

    for name, metrics in best["periods"].items():
        print(f"{name:<15} {metrics['bh_return']:>9.1f}% {metrics['strategy_return']:>9.1f}% {metrics['protection_value']:>+11.1f}% {metrics['max_dd']:>9.1f}% {metrics['trades']:>8}")

    # Compare to current baseline
    print("\n" + "=" * 100)
    print("COMPARISON: BEST vs CURRENT (vel>0.5, acc<-1.5)")
    print("=" * 100)

    current_config = RegimeConfig()  # Default values
    current_total = 0
    best_total = best["total_protection"]

    print(f"\n{'Period':<15} {'Current':>12} {'Best':>12} {'Improvement':>12}")
    print("-" * 55)

    for name, df in period_data.items():
        current = simulate_with_config(df, current_config)
        best_period = best["periods"][name]

        improvement = best_period["protection_value"] - current["protection_value"]
        current_total += current["protection_value"]

        print(f"{name:<15} {current['protection_value']:>+11.1f}% {best_period['protection_value']:>+11.1f}% {improvement:>+11.1f}%")

    print("-" * 55)
    print(f"{'TOTAL':<15} {current_total:>+11.1f}% {best_total:>+11.1f}% {best_total - current_total:>+11.1f}%")

    # Show worst (to understand the range)
    print("\n" + "=" * 100)
    print("WORST 5 CONFIGURATIONS (to show the range)")
    print("=" * 100)

    print(f"\n{'Rank':<5} {'Exit Vel':<10} {'Exit Acc':<10} {'Entry Vel':<10} {'Entry Acc':<10} {'Total Protection':>18}")
    print("-" * 70)

    for i, r in enumerate(results[-5:], len(results) - 4):
        print(f"{i:<5} {r['exit_vel']:<10.2f} {r['exit_acc']:<10.2f} {r['entry_vel']:<10.2f} {r['entry_acc']:<10.2f} {r['total_protection']:>+17.1f}%")

    # Recommendations
    print("\n" + "=" * 100)
    print("RECOMMENDATIONS")
    print("=" * 100)

    print(f"""
Current thresholds: exit_vel=0.5, exit_acc=-1.5
Best thresholds:    exit_vel={best['exit_vel']}, exit_acc={best['exit_acc']}

To apply the best thresholds, update RegimeConfig:

    config = RegimeConfig(
        exit_vel_threshold={best['exit_vel']},
        exit_acc_threshold={best['exit_acc']},
        entry_vel_threshold={best['entry_vel']},
        entry_acc_threshold={best['entry_acc']},
    )

Or update the defaults in bear_protection_service.py
""")


if __name__ == "__main__":
    main()
