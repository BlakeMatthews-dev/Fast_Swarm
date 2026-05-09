"""
Fast MTF + ADX Confirmation Backtest.

Uses join_asof for efficient timeframe alignment (like backtest_triple_timeframe.py).
Compares original MTF vs MTF+ADX at realistic position sizes (no leverage).
"""

import polars as pl
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")


@dataclass
class Config:
    """Backtest configuration."""
    initial_capital: float = 10000.0

    # Signal thresholds
    vel_threshold: float = -1.5
    acc_threshold: float = 3.0
    adx_vel_threshold: float | None = None  # None = don't use

    # Exit thresholds
    exit_vel_threshold: float = 1.5
    exit_acc_threshold: float = -3.0

    # Position sizing (NO LEVERAGE)
    kelly_1tf: float = 0.25   # 12.5% position
    kelly_2tf: float = 0.50   # 25% position
    kelly_3tf: float = 1.00   # 50% position (max)
    base_kelly: float = 0.50

    # Stop loss
    stop_loss_pct: float = 0.10


def load_and_align(symbol: str = "BTC") -> pl.DataFrame:
    """Load all 3 timeframes and align with asof join."""
    print("Loading data...")

    # Load each timeframe
    df_1h = pl.read_parquet(DERIVATIVES_DIR / f"symbol={symbol}" / "timeframe=1h").sort("time")
    df_4h = pl.read_parquet(DERIVATIVES_DIR / f"symbol={symbol}" / "timeframe=4h").sort("time")
    df_1d = pl.read_parquet(DERIVATIVES_DIR / f"symbol={symbol}" / "timeframe=1d").sort("time")

    print(f"  1h: {len(df_1h):,} rows")
    print(f"  4h: {len(df_4h):,} rows")
    print(f"  1d: {len(df_1d):,} rows")

    # Prepare columns for join
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

    # Asof join - align 4h and 1d to 1h candles
    result = df_1h.join_asof(
        df_4h_join,
        left_on="time",
        right_on="tf_4h_time",
        strategy="backward"
    )

    result = result.join_asof(
        df_1d_join,
        left_on="time",
        right_on="tf_1d_time",
        strategy="backward"
    )

    # Rename 1h columns for consistency
    result = result.rename({
        "close_velocity_zscore": "tf_1h_vel",
        "close_acceleration_zscore": "tf_1h_acc",
        "adx_14_velocity_zscore": "tf_1h_adx_vel",
    })

    print(f"Aligned: {len(result):,} rows")
    return result


def check_signal(vel, acc, adx_vel, config: Config, check_adx: bool) -> bool:
    """Check if single TF shows divergence (with optional ADX)."""
    if vel is None or acc is None:
        return False
    if np.isnan(vel) or np.isnan(acc):
        return False

    # Base divergence
    if not (vel < config.vel_threshold and acc > config.acc_threshold):
        return False

    # ADX confirmation
    if check_adx and config.adx_vel_threshold is not None:
        if adx_vel is None or np.isnan(adx_vel):
            return False
        if not (adx_vel < config.adx_vel_threshold):
            return False

    return True


def count_confirmations(row: dict, config: Config, check_adx: bool = True) -> int:
    """Count TFs confirming the signal."""
    count = 0

    # 1h
    if check_signal(row.get("tf_1h_vel"), row.get("tf_1h_acc"),
                    row.get("tf_1h_adx_vel"), config, check_adx):
        count += 1

    # 4h
    if check_signal(row.get("tf_4h_vel"), row.get("tf_4h_acc"),
                    row.get("tf_4h_adx_vel"), config, check_adx):
        count += 1

    # 1d
    if check_signal(row.get("tf_1d_vel"), row.get("tf_1d_acc"),
                    row.get("tf_1d_adx_vel"), config, check_adx):
        count += 1

    return count


def check_exit(row: dict, config: Config) -> bool:
    """Check exit signal on 1h."""
    vel = row.get("tf_1h_vel")
    acc = row.get("tf_1h_acc")

    if vel is None or acc is None:
        return False

    return vel > config.exit_vel_threshold and acc < config.exit_acc_threshold


def run_backtest(df: pl.DataFrame, config: Config, min_conf: int = 1,
                 check_adx: bool = True) -> dict:
    """Run backtest on aligned data."""
    rows = df.to_dicts()

    capital = config.initial_capital
    position = None
    trades = []
    equity = [capital]

    for row in rows:
        price = row.get("close", 0)
        if price <= 0:
            continue

        time = row.get("time")

        # Exit check
        if position is not None:
            entry_price = position["entry_price"]
            ret = (price / entry_price) - 1

            # Stop loss
            if ret <= -config.stop_loss_pct:
                pnl = position["size"] * ret
                capital += position["size"] + pnl
                trades.append({
                    "entry_time": position["entry_time"],
                    "exit_time": time,
                    "return_pct": ret * 100,
                    "reason": "STOP",
                    "conf": position["conf"],
                })
                position = None

            # Exit signal
            elif check_exit(row, config):
                pnl = position["size"] * ret
                capital += position["size"] + pnl
                trades.append({
                    "entry_time": position["entry_time"],
                    "exit_time": time,
                    "return_pct": ret * 100,
                    "reason": "SIGNAL",
                    "conf": position["conf"],
                })
                position = None

        # Entry check
        if position is None:
            conf = count_confirmations(row, config, check_adx)

            if conf >= min_conf:
                # Position size based on confirmations
                if conf >= 3:
                    kelly = config.kelly_3tf
                elif conf == 2:
                    kelly = config.kelly_2tf
                else:
                    kelly = config.kelly_1tf

                size = capital * config.base_kelly * kelly

                position = {
                    "entry_time": time,
                    "entry_price": price,
                    "size": size,
                    "conf": conf,
                }
                capital -= size

        # Track equity
        if position is not None:
            mtm = position["size"] * (price / position["entry_price"])
            equity.append(capital + mtm)
        else:
            equity.append(capital)

    # Close open position
    if position is not None:
        final_price = rows[-1].get("close", position["entry_price"])
        ret = (final_price / position["entry_price"]) - 1
        pnl = position["size"] * ret
        capital += position["size"] + pnl
        trades.append({
            "entry_time": position["entry_time"],
            "exit_time": rows[-1].get("time"),
            "return_pct": ret * 100,
            "reason": "END",
            "conf": position["conf"],
        })

    if not trades:
        return {"error": "No trades"}

    # Metrics
    returns = [t["return_pct"] / 100 for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]

    total_return = (equity[-1] / config.initial_capital - 1) * 100
    max_eq = max(equity)
    max_dd = max((max_eq - e) / max_eq for e in equity) * 100

    neg_rets = [r for r in returns if r < 0]
    down_std = np.std(neg_rets) if neg_rets else 0.001
    sortino = (np.mean(returns) / down_std) if down_std > 0 else 0

    # By confirmation
    by_conf = {}
    for c in [1, 2, 3]:
        ct = [t for t in trades if t["conf"] == c]
        if ct:
            cr = [t["return_pct"] for t in ct]
            by_conf[c] = {
                "count": len(ct),
                "avg": np.mean(cr),
                "win": len([r for r in cr if r > 0]) / len(cr) * 100,
            }

    return {
        "trades": len(trades),
        "return": total_return,
        "max_dd": max_dd,
        "sortino": sortino,
        "win_rate": len(wins) / len(returns) * 100 if returns else 0,
        "profit_factor": abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else 0,
        "final": equity[-1],
        "by_conf": by_conf,
    }


def main():
    print("=" * 70)
    print("MTF + ADX BACKTEST (No Leverage)")
    print("=" * 70)

    # Load aligned data
    df = load_and_align("BTC")

    # Test configurations
    tests = [
        # Name, Config, check_adx
        ("Original MTF (no ADX)", Config(vel_threshold=-1.5, acc_threshold=3.0), False),
        ("MTF + ADX strict", Config(vel_threshold=-1.5, acc_threshold=3.0, adx_vel_threshold=-1.0), True),
        ("MTF + ADX lower", Config(vel_threshold=-1.25, acc_threshold=1.5, adx_vel_threshold=-1.0), True),
        ("MTF + ADX lowest", Config(vel_threshold=-1.0, acc_threshold=1.0, adx_vel_threshold=-0.5), True),
    ]

    print("\n" + "=" * 70)
    print("RESULTS (Position: 12.5% 1TF, 25% 2TF, 50% 3TF)")
    print("=" * 70)

    results = []
    for name, config, use_adx in tests:
        print(f"\n{name}")
        print("-" * len(name))

        r = run_backtest(df, config, min_conf=1, check_adx=use_adx)

        if "error" in r:
            print(f"  Error: {r['error']}")
            continue

        print(f"  Trades:   {r['trades']}")
        print(f"  Return:   {r['return']:.1f}%")
        print(f"  Max DD:   {r['max_dd']:.1f}%")
        print(f"  Sortino:  {r['sortino']:.2f}")
        print(f"  Win Rate: {r['win_rate']:.1f}%")
        print(f"  Final:    ${r['final']:,.0f}")

        if r.get("by_conf"):
            print("  By TF confirmation:")
            for c, s in sorted(r["by_conf"].items()):
                print(f"    {c}TF: {s['count']} trades, {s['avg']:.2f}% avg, {s['win']:.0f}% win")

        results.append((name, r))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"\n{'Strategy':<30} {'Trades':>7} {'Return':>8} {'MaxDD':>7} {'Sortino':>8}")
    print("-" * 70)
    for name, r in results:
        if "error" not in r:
            print(f"{name:<30} {r['trades']:>7} {r['return']:>7.1f}% {r['max_dd']:>6.1f}% {r['sortino']:>8.2f}")


if __name__ == "__main__":
    main()
