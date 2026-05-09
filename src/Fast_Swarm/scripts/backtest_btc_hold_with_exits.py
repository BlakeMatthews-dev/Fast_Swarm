"""
BTC Hold with Smart Exits.

Strategy: Stay long BTC by default, exit to cash only when danger signals appear.
Re-enter when bullish divergence appears.

This captures BTC's uptrend while dodging major drawdowns.
"""

import polars as pl
import numpy as np
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")


@dataclass
class Config:
    """Strategy configuration."""
    initial_capital: float = 10000.0

    # EXIT signal (danger - get out)
    # Opposite of entry: velocity RISING + acceleration FALLING = momentum exhaustion at top
    exit_vel_threshold: float = 1.5   # vel > this = price rising fast
    exit_acc_threshold: float = -3.0  # acc < this = momentum fading
    exit_adx_threshold: float | None = 1.0  # adx_vel > this = trend strengthening (optional)

    # RE-ENTRY signal (safe to get back in)
    # Same as original: velocity FALLING + acceleration RISING = local bottom
    entry_vel_threshold: float = -1.5
    entry_acc_threshold: float = 3.0
    entry_adx_threshold: float | None = -1.0

    # Stop loss while in cash (opportunity cost limit)
    max_cash_days: int = 30  # Force re-entry after N days in cash


def load_and_align(symbol: str = "BTC") -> pl.DataFrame:
    """Load all 3 timeframes and align."""
    print("Loading data...")

    df_1h = pl.read_parquet(DERIVATIVES_DIR / f"symbol={symbol}" / "timeframe=1h").sort("time")
    df_4h = pl.read_parquet(DERIVATIVES_DIR / f"symbol={symbol}" / "timeframe=4h").sort("time")
    df_1d = pl.read_parquet(DERIVATIVES_DIR / f"symbol={symbol}" / "timeframe=1d").sort("time")

    print(f"  1h: {len(df_1h):,} rows")
    print(f"  4h: {len(df_4h):,} rows")
    print(f"  1d: {len(df_1d):,} rows")

    # Prepare for join
    df_4h_join = df_4h.select([
        pl.col("time").alias("tf_4h_time"),
        pl.col("close_velocity_zscore").alias("tf_4h_vel"),
        pl.col("close_acceleration_zscore").alias("tf_4h_acc"),
        pl.col("adx_14_velocity_zscore").alias("tf_4h_adx_vel"),
    ])

    df_1d_join = df_1d.select([
        pl.col("time").alias("tf_1d_time"),
        pl.col("close_velocity_zscore").alias("tf_1d_vel"),
        pl.col("close_acceleration_zscore").alias("tf_1d_acc"),
        pl.col("adx_14_velocity_zscore").alias("tf_1d_adx_vel"),
    ])

    result = df_1h.join_asof(df_4h_join, left_on="time", right_on="tf_4h_time", strategy="backward")
    result = result.join_asof(df_1d_join, left_on="time", right_on="tf_1d_time", strategy="backward")

    result = result.rename({
        "close_velocity_zscore": "tf_1h_vel",
        "close_acceleration_zscore": "tf_1h_acc",
        "adx_14_velocity_zscore": "tf_1h_adx_vel",
    })

    print(f"Aligned: {len(result):,} rows")
    return result


def check_exit_signal(row: dict, config: Config) -> int:
    """Count TFs showing exit (danger) signal."""
    count = 0

    for tf in ["1h", "4h", "1d"]:
        vel = row.get(f"tf_{tf}_vel")
        acc = row.get(f"tf_{tf}_acc")
        adx = row.get(f"tf_{tf}_adx_vel")

        if vel is None or acc is None:
            continue
        if np.isnan(vel) or np.isnan(acc):
            continue

        # Exit signal: momentum exhaustion at top
        if vel > config.exit_vel_threshold and acc < config.exit_acc_threshold:
            # Optional ADX confirmation
            if config.exit_adx_threshold is not None:
                if adx is not None and not np.isnan(adx) and adx > config.exit_adx_threshold:
                    count += 1
            else:
                count += 1

    return count


def check_entry_signal(row: dict, config: Config) -> int:
    """Count TFs showing entry (safe) signal."""
    count = 0

    for tf in ["1h", "4h", "1d"]:
        vel = row.get(f"tf_{tf}_vel")
        acc = row.get(f"tf_{tf}_acc")
        adx = row.get(f"tf_{tf}_adx_vel")

        if vel is None or acc is None:
            continue
        if np.isnan(vel) or np.isnan(acc):
            continue

        # Entry signal: local bottom
        if vel < config.entry_vel_threshold and acc > config.entry_acc_threshold:
            if config.entry_adx_threshold is not None:
                if adx is not None and not np.isnan(adx) and adx < config.entry_adx_threshold:
                    count += 1
            else:
                count += 1

    return count


def run_backtest(df: pl.DataFrame, config: Config, min_exit_conf: int = 1,
                 min_entry_conf: int = 1) -> dict:
    """Run hold-with-exits backtest."""
    rows = df.to_dicts()

    # Start LONG (holding BTC)
    initial_price = rows[0].get("close", 1)
    shares = config.initial_capital / initial_price
    cash = 0
    is_long = True

    equity = [config.initial_capital]
    exits = []
    entries = []
    cash_start_idx = None

    for i, row in enumerate(rows):
        price = row.get("close", 0)
        if price <= 0:
            continue

        time = row.get("time")

        if is_long:
            # Check for exit signal
            exit_conf = check_exit_signal(row, config)

            if exit_conf >= min_exit_conf:
                # EXIT to cash
                cash = shares * price
                shares = 0
                is_long = False
                cash_start_idx = i
                exits.append({
                    "time": time,
                    "price": price,
                    "conf": exit_conf,
                })

        else:
            # In cash - check for re-entry
            entry_conf = check_entry_signal(row, config)

            # Force re-entry after max_cash_days
            hours_in_cash = i - cash_start_idx if cash_start_idx else 0
            days_in_cash = hours_in_cash / 24
            force_entry = days_in_cash > config.max_cash_days

            if entry_conf >= min_entry_conf or force_entry:
                # RE-ENTER long
                shares = cash / price
                cash = 0
                is_long = True
                entries.append({
                    "time": time,
                    "price": price,
                    "conf": entry_conf,
                    "forced": force_entry,
                    "days_in_cash": days_in_cash,
                })

        # Track equity
        if is_long:
            equity.append(shares * price)
        else:
            equity.append(cash)

    # Final equity
    final_price = rows[-1].get("close", 1)
    if is_long:
        final_equity = shares * final_price
    else:
        final_equity = cash

    # Buy and hold comparison
    buy_hold_return = (final_price / initial_price - 1) * 100

    # Strategy metrics
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

    # Buy and hold max drawdown
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

    # Time in market
    time_in_market = sum(1 for i, row in enumerate(rows) if i < len(equity) - 1 and
                         (i == 0 or equity[i] != equity[i-1] or is_long)) / len(rows) * 100

    return {
        "strategy_return": strategy_return,
        "buy_hold_return": buy_hold_return,
        "alpha": strategy_return - buy_hold_return,
        "max_dd": max_dd,
        "bh_max_dd": bh_max_dd,
        "dd_reduction": bh_max_dd - max_dd,
        "exits": len(exits),
        "entries": len(entries),
        "final_equity": final_equity,
        "exit_details": exits[:10],  # First 10
        "entry_details": entries[:10],
    }


def main():
    print("=" * 70)
    print("BTC HOLD WITH SMART EXITS")
    print("Strategy: Stay long, exit only on danger signals")
    print("=" * 70)

    df = load_and_align("BTC")

    # Test configurations
    tests = [
        # (Name, Config, min_exit_conf, min_entry_conf)
        ("Strict (2TF exit, 2TF entry)", Config(), 2, 2),
        ("Moderate (1TF exit, 1TF entry)", Config(), 1, 1),
        ("Quick exit (1TF), slow entry (2TF)", Config(), 1, 2),
        ("Slow exit (2TF), quick entry (1TF)", Config(), 2, 1),

        # Lower thresholds with ADX
        ("ADX Lower thresholds", Config(
            exit_vel_threshold=1.0,
            exit_acc_threshold=-2.0,
            entry_vel_threshold=-1.0,
            entry_acc_threshold=2.0,
        ), 1, 1),

        # No ADX
        ("No ADX confirm", Config(
            exit_adx_threshold=None,
            entry_adx_threshold=None,
        ), 1, 1),

        # Aggressive exits
        ("Aggressive exits (vel>0.5)", Config(
            exit_vel_threshold=0.5,
            exit_acc_threshold=-1.5,
        ), 1, 1),
    ]

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    results = []
    for name, config, min_exit, min_entry in tests:
        print(f"\n{name}")
        print("-" * len(name))

        r = run_backtest(df, config, min_exit, min_entry)

        print(f"  Strategy Return: {r['strategy_return']:.1f}%")
        print(f"  Buy & Hold:      {r['buy_hold_return']:.1f}%")
        print(f"  Alpha:           {r['alpha']:+.1f}%")
        print(f"  Strategy MaxDD:  {r['max_dd']:.1f}%")
        print(f"  B&H MaxDD:       {r['bh_max_dd']:.1f}%")
        print(f"  DD Reduction:    {r['dd_reduction']:.1f}%")
        print(f"  Exits/Entries:   {r['exits']}/{r['entries']}")

        results.append((name, r))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"\n{'Strategy':<35} {'Return':>8} {'B&H':>8} {'Alpha':>8} {'MaxDD':>7} {'BH DD':>7}")
    print("-" * 80)
    for name, r in results:
        print(f"{name:<35} {r['strategy_return']:>7.1f}% {r['buy_hold_return']:>7.1f}% "
              f"{r['alpha']:>+7.1f}% {r['max_dd']:>6.1f}% {r['bh_max_dd']:>6.1f}%")


if __name__ == "__main__":
    main()
