"""
Backtest: Hold BTC with Smart Exits + ADX Jerk Neutral Filter.

Tests whether filtering exits by ADX jerk neutral (|j| < threshold)
improves the strategy from forward return analysis.
"""

import polars as pl
import numpy as np
from pathlib import Path
from dataclasses import dataclass

DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")


@dataclass
class Config:
    initial_capital: float = 10000.0
    exit_vel_threshold: float = 1.5
    exit_acc_threshold: float = -3.0
    entry_vel_threshold: float = -1.5
    entry_acc_threshold: float = 3.0
    max_cash_days: int = 30
    # ADX jerk neutral filter: only exit when |adx_jerk| < this
    adx_jerk_neutral_band: float | None = None


def load_and_align(symbol: str = "BTC") -> pl.DataFrame:
    """Load all 3 timeframes and align."""
    df_1h = pl.read_parquet(DERIVATIVES_DIR / f"symbol={symbol}" / "timeframe=1h").sort("time")
    df_4h = pl.read_parquet(DERIVATIVES_DIR / f"symbol={symbol}" / "timeframe=4h").sort("time")
    df_1d = pl.read_parquet(DERIVATIVES_DIR / f"symbol={symbol}" / "timeframe=1d").sort("time")

    df_4h_join = df_4h.select([
        pl.col("time").alias("tf_4h_time"),
        pl.col("close_velocity_zscore").alias("tf_4h_vel"),
        pl.col("close_acceleration_zscore").alias("tf_4h_acc"),
        pl.col("adx_14_jerk_zscore").alias("tf_4h_adx_jerk"),
    ])

    df_1d_join = df_1d.select([
        pl.col("time").alias("tf_1d_time"),
        pl.col("close_velocity_zscore").alias("tf_1d_vel"),
        pl.col("close_acceleration_zscore").alias("tf_1d_acc"),
        pl.col("adx_14_jerk_zscore").alias("tf_1d_adx_jerk"),
    ])

    result = df_1h.join_asof(df_4h_join, left_on="time", right_on="tf_4h_time", strategy="backward")
    result = result.join_asof(df_1d_join, left_on="time", right_on="tf_1d_time", strategy="backward")

    result = result.rename({
        "close_velocity_zscore": "tf_1h_vel",
        "close_acceleration_zscore": "tf_1h_acc",
        "adx_14_jerk_zscore": "tf_1h_adx_jerk",
    })

    return result


def check_exit_signal(row: dict, config: Config, min_conf: int = 1) -> bool:
    """Check exit signal with optional ADX jerk neutral filter."""
    count = 0
    for tf in ["1h", "4h", "1d"]:
        vel = row.get(f"tf_{tf}_vel")
        acc = row.get(f"tf_{tf}_acc")
        adx_jerk = row.get(f"tf_{tf}_adx_jerk")

        if vel is None or acc is None or np.isnan(vel) or np.isnan(acc):
            continue

        # Base exit: momentum exhaustion (price rising + acceleration falling)
        if vel > config.exit_vel_threshold and acc < config.exit_acc_threshold:
            # ADX jerk neutral filter (if enabled)
            if config.adx_jerk_neutral_band is not None:
                if adx_jerk is None or np.isnan(adx_jerk):
                    continue
                if abs(adx_jerk) >= config.adx_jerk_neutral_band:
                    continue  # Skip - ADX jerk too extreme
            count += 1

    return count >= min_conf


def check_entry_signal(row: dict, config: Config, min_conf: int = 1) -> bool:
    """Check entry signal (bullish divergence)."""
    count = 0
    for tf in ["1h", "4h", "1d"]:
        vel = row.get(f"tf_{tf}_vel")
        acc = row.get(f"tf_{tf}_acc")
        if vel is None or acc is None or np.isnan(vel) or np.isnan(acc):
            continue
        if vel < config.entry_vel_threshold and acc > config.entry_acc_threshold:
            count += 1
    return count >= min_conf


def run_backtest(df: pl.DataFrame, config: Config, min_exit_conf: int = 1, min_entry_conf: int = 1) -> dict:
    """Run hold-with-exits backtest."""
    rows = df.to_dicts()

    initial_price = rows[0].get("close", 1)
    shares = config.initial_capital / initial_price
    cash = 0
    is_long = True

    equity = [config.initial_capital]
    exits = []
    cash_start_idx = None

    for i, row in enumerate(rows):
        price = row.get("close", 0)
        if price <= 0:
            continue
        time = row.get("time")

        if is_long:
            if check_exit_signal(row, config, min_exit_conf):
                cash = shares * price
                shares = 0
                is_long = False
                cash_start_idx = i
                exits.append({"time": time, "price": price})
        else:
            hours_in_cash = i - cash_start_idx if cash_start_idx else 0
            days_in_cash = hours_in_cash / 24
            force_entry = days_in_cash > config.max_cash_days

            if check_entry_signal(row, config, min_entry_conf) or force_entry:
                shares = cash / price
                cash = 0
                is_long = True

        if is_long:
            equity.append(shares * price)
        else:
            equity.append(cash)

    final_price = rows[-1].get("close", 1)
    if is_long:
        final_equity = shares * final_price
    else:
        final_equity = cash

    buy_hold_return = (final_price / initial_price - 1) * 100
    strategy_return = (final_equity / config.initial_capital - 1) * 100

    # Max drawdown
    peak = equity[0]
    max_dd = 0
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak
        if dd > max_dd:
            max_dd = dd
    max_dd *= 100

    # B&H max drawdown
    bh_equity = [config.initial_capital * (rows[i].get("close", initial_price) / initial_price)
                 for i in range(len(rows))]
    bh_peak = bh_equity[0]
    bh_max_dd = 0
    for e in bh_equity:
        if e > bh_peak:
            bh_peak = e
        dd = (bh_peak - e) / bh_peak
        if dd > bh_max_dd:
            bh_max_dd = dd
    bh_max_dd *= 100

    # Sortino (daily returns)
    daily_returns = []
    for i in range(24, len(equity), 24):
        if equity[i-24] > 0:
            daily_returns.append(equity[i] / equity[i-24] - 1)

    neg_returns = [r for r in daily_returns if r < 0]
    downside_std = np.std(neg_returns) if neg_returns else 0.001
    avg_daily = np.mean(daily_returns) if daily_returns else 0
    sortino = (avg_daily / downside_std * np.sqrt(365)) if downside_std > 0 else 0

    return {
        "strategy_return": strategy_return,
        "buy_hold_return": buy_hold_return,
        "alpha": strategy_return - buy_hold_return,
        "max_dd": max_dd,
        "bh_max_dd": bh_max_dd,
        "dd_reduction": bh_max_dd - max_dd,
        "sortino": sortino,
        "exits": len(exits),
        "final_equity": final_equity,
    }


def main():
    print("=" * 85)
    print("BACKTEST: Hold BTC with Smart Exits + ADX Jerk Neutral Filter")
    print("=" * 85)

    print("\nLoading data...")
    df = load_and_align("BTC")
    print(f"Rows: {len(df):,}")

    tests = [
        # Baseline configs (no ADX filter)
        ("Baseline (vel>1.5, acc<-3)", Config(
            exit_vel_threshold=1.5,
            exit_acc_threshold=-3.0,
            adx_jerk_neutral_band=None,
        ), 1, 1),

        # ADX jerk neutral |j| < 0.5
        ("+ ADX jerk neutral |j|<0.5", Config(
            exit_vel_threshold=1.5,
            exit_acc_threshold=-3.0,
            adx_jerk_neutral_band=0.5,
        ), 1, 1),

        # ADX jerk neutral |j| < 1.0
        ("+ ADX jerk neutral |j|<1.0", Config(
            exit_vel_threshold=1.5,
            exit_acc_threshold=-3.0,
            adx_jerk_neutral_band=1.0,
        ), 1, 1),

        # Aggressive exits WITHOUT filter
        ("Aggressive (vel>0.5, acc<-1.5)", Config(
            exit_vel_threshold=0.5,
            exit_acc_threshold=-1.5,
            adx_jerk_neutral_band=None,
        ), 1, 1),

        # Aggressive + ADX jerk neutral
        ("Aggressive + ADX |j|<0.5", Config(
            exit_vel_threshold=0.5,
            exit_acc_threshold=-1.5,
            adx_jerk_neutral_band=0.5,
        ), 1, 1),

        # Aggressive + ADX jerk neutral (wider band)
        ("Aggressive + ADX |j|<1.0", Config(
            exit_vel_threshold=0.5,
            exit_acc_threshold=-1.5,
            adx_jerk_neutral_band=1.0,
        ), 1, 1),
    ]

    print("\n" + "=" * 85)
    print("RESULTS")
    print("=" * 85)

    print(f"\n{'Strategy':<35} {'Return':>9} {'Alpha':>9} {'MaxDD':>7} {'Sortino':>8} {'Exits':>6}")
    print("-" * 85)

    results = []
    for name, config, min_exit, min_entry in tests:
        r = run_backtest(df, config, min_exit, min_entry)
        results.append((name, r))
        print(f"{name:<35} {r['strategy_return']:>8.1f}% {r['alpha']:>+8.1f}% "
              f"{r['max_dd']:>6.1f}% {r['sortino']:>8.2f} {r['exits']:>6}")

    print(f"\n{'Buy & Hold':<35} {results[0][1]['buy_hold_return']:>8.1f}% {'---':>9} "
          f"{results[0][1]['bh_max_dd']:>6.1f}%")

    # Delta analysis
    print("\n" + "=" * 85)
    print("DELTA ANALYSIS")
    print("=" * 85)

    baseline = results[0][1]
    filtered = results[1][1]

    print(f"\nStrict + ADX Jerk Neutral Filter (|j|<0.5) vs Baseline:")
    print(f"  Return:  {baseline['strategy_return']:.1f}% -> {filtered['strategy_return']:.1f}% "
          f"(delta: {filtered['strategy_return'] - baseline['strategy_return']:+.1f}%)")
    print(f"  Alpha:   {baseline['alpha']:+.1f}% -> {filtered['alpha']:+.1f}% "
          f"(delta: {filtered['alpha'] - baseline['alpha']:+.1f}%)")
    print(f"  MaxDD:   {baseline['max_dd']:.1f}% -> {filtered['max_dd']:.1f}% "
          f"(delta: {filtered['max_dd'] - baseline['max_dd']:+.1f}%)")
    print(f"  Sortino: {baseline['sortino']:.2f} -> {filtered['sortino']:.2f} "
          f"(delta: {filtered['sortino'] - baseline['sortino']:+.2f})")
    print(f"  Exits:   {baseline['exits']} -> {filtered['exits']} "
          f"(delta: {filtered['exits'] - baseline['exits']:+d})")

    agg_base = results[3][1]
    agg_filt = results[4][1]
    print(f"\nAggressive + ADX Filter (|j|<0.5) vs Aggressive Baseline:")
    print(f"  Return:  {agg_base['strategy_return']:.1f}% -> {agg_filt['strategy_return']:.1f}% "
          f"(delta: {agg_filt['strategy_return'] - agg_base['strategy_return']:+.1f}%)")
    print(f"  MaxDD:   {agg_base['max_dd']:.1f}% -> {agg_filt['max_dd']:.1f}% "
          f"(delta: {agg_filt['max_dd'] - agg_base['max_dd']:+.1f}%)")
    print(f"  Sortino: {agg_base['sortino']:.2f} -> {agg_filt['sortino']:.2f} "
          f"(delta: {agg_filt['sortino'] - agg_base['sortino']:+.2f})")


if __name__ == "__main__":
    main()
