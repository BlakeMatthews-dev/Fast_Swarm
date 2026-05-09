"""
Combined MTF + ADX Confirmation Backtest.

Tests whether adding ADX velocity confirmation to the MTF divergence strategy
allows us to either:
1. Use lower thresholds while maintaining quality (more signals)
2. Improve returns with the same thresholds (better signals)

Compares:
- Original MTF: vel < -1.5, acc > 3.0, 3TF super-Kelly
- New MTF+ADX: vel < -1.25, acc > 1.5, adx_vel < -1.0, 3TF super-Kelly
"""

import polars as pl
import numpy as np
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")


@dataclass
class MTFConfig:
    """Configuration for MTF divergence with optional ADX."""

    # Signal thresholds
    vel_threshold: float = -1.5
    acc_threshold: float = 3.0
    adx_vel_threshold: float | None = None  # None = don't use ADX

    # Kelly multipliers (NO LEVERAGE - max 1.0x total)
    kelly_1tf: float = 0.25   # 25% position on 1TF
    kelly_2tf: float = 0.50   # 50% position on 2TF
    kelly_3tf: float = 1.00   # 100% position on 3TF (max, no leverage)

    # Base position (multiplied by kelly)
    base_kelly: float = 0.50  # 50% base * 1.0x kelly = 50% max

    # Stop loss
    stop_loss_pct: float = 0.10  # 10% stop loss

    # Exit thresholds
    exit_vel_threshold: float = 1.5
    exit_acc_threshold: float = -3.0


def load_all_timeframes(symbol: str = "BTC") -> dict[str, pl.DataFrame]:
    """Load 1d, 4h, 1h data for a symbol."""
    data = {}
    for tf in ["1d", "4h", "1h"]:
        path = DERIVATIVES_DIR / f"symbol={symbol}" / f"timeframe={tf}"
        if path.exists():
            df = pl.read_parquet(path).sort("time")
            data[tf] = df
            print(f"  Loaded {tf}: {len(df):,} rows")
    return data


def check_divergence(row: dict, config: MTFConfig, check_adx: bool = True) -> bool:
    """Check if a single row shows divergence signal."""
    vel = row.get("close_velocity_zscore")
    acc = row.get("close_acceleration_zscore")

    if vel is None or acc is None:
        return False
    if np.isnan(vel) or np.isnan(acc):
        return False

    # Base divergence check
    if not (vel < config.vel_threshold and acc > config.acc_threshold):
        return False

    # Optional ADX confirmation
    if check_adx and config.adx_vel_threshold is not None:
        adx_vel = row.get("adx_14_velocity_zscore")
        if adx_vel is None or np.isnan(adx_vel):
            return False
        if not (adx_vel < config.adx_vel_threshold):
            return False

    return True


def check_exit(row: dict, config: MTFConfig) -> bool:
    """Check if exit signal triggered."""
    vel = row.get("close_velocity_zscore")
    acc = row.get("close_acceleration_zscore")

    if vel is None or acc is None:
        return False

    return vel > config.exit_vel_threshold and acc < config.exit_acc_threshold


def get_tf_row_at_time(df: pl.DataFrame, target_time: datetime) -> dict | None:
    """Get the most recent row at or before target_time."""
    filtered = df.filter(pl.col("time") <= target_time)
    if filtered.is_empty():
        return None
    return filtered.tail(1).to_dicts()[0]


def count_confirmations(
    data: dict[str, pl.DataFrame],
    target_time: datetime,
    config: MTFConfig,
) -> tuple[int, list[str]]:
    """Count how many timeframes confirm the signal."""
    confirming = []

    for tf in ["1d", "4h", "1h"]:
        if tf not in data:
            continue

        row = get_tf_row_at_time(data[tf], target_time)
        if row is None:
            continue

        if check_divergence(row, config, check_adx=True):
            confirming.append(tf)

    return len(confirming), confirming


def run_backtest(
    data: dict[str, pl.DataFrame],
    config: MTFConfig,
    initial_capital: float = 10000,
    min_confirmations: int = 1,
) -> dict:
    """Run MTF divergence backtest."""

    # Use 1h as primary timeframe for iteration
    primary = data.get("1h")
    if primary is None:
        return {"error": "No 1h data"}

    primary_rows = primary.to_dicts()

    capital = initial_capital
    position = None
    trades = []
    equity_curve = [capital]

    for i, row in enumerate(primary_rows):
        current_time = row.get("time")
        current_price = row.get("close", 0)

        if current_price <= 0:
            continue

        # Check for exit if in position
        if position is not None:
            entry_price = position["entry_price"]
            drawdown = (current_price / entry_price) - 1

            # Stop loss
            if drawdown <= -config.stop_loss_pct:
                pnl = position["size"] * drawdown
                capital += position["size"] + pnl
                trades.append({
                    "entry_time": position["entry_time"],
                    "exit_time": current_time,
                    "entry_price": entry_price,
                    "exit_price": current_price,
                    "return_pct": drawdown * 100,
                    "pnl": pnl,
                    "exit_reason": "STOP_LOSS",
                    "confirmations": position["confirmations"],
                })
                position = None

            # Exit signal
            elif check_exit(row, config):
                pnl = position["size"] * drawdown
                capital += position["size"] + pnl
                trades.append({
                    "entry_time": position["entry_time"],
                    "exit_time": current_time,
                    "entry_price": entry_price,
                    "exit_price": current_price,
                    "return_pct": drawdown * 100,
                    "pnl": pnl,
                    "exit_reason": "EXIT_SIGNAL",
                    "confirmations": position["confirmations"],
                })
                position = None

        # Check for entry if not in position
        if position is None:
            count, tfs = count_confirmations(data, current_time, config)

            if count >= min_confirmations:
                # Calculate position size based on confirmations
                if count >= 3:
                    kelly = config.kelly_3tf
                elif count == 2:
                    kelly = config.kelly_2tf
                else:
                    kelly = config.kelly_1tf

                position_pct = config.base_kelly * kelly
                position_size = capital * position_pct

                position = {
                    "entry_time": current_time,
                    "entry_price": current_price,
                    "size": position_size,
                    "confirmations": count,
                    "confirming_tfs": tfs,
                }
                capital -= position_size

        # Track equity
        if position is not None:
            mark_to_market = position["size"] * (current_price / position["entry_price"])
            equity_curve.append(capital + mark_to_market)
        else:
            equity_curve.append(capital)

    # Close any open position at end
    if position is not None:
        final_price = primary_rows[-1].get("close", position["entry_price"])
        drawdown = (final_price / position["entry_price"]) - 1
        pnl = position["size"] * drawdown
        capital += position["size"] + pnl
        trades.append({
            "entry_time": position["entry_time"],
            "exit_time": primary_rows[-1].get("time"),
            "entry_price": position["entry_price"],
            "exit_price": final_price,
            "return_pct": drawdown * 100,
            "pnl": pnl,
            "exit_reason": "END_OF_DATA",
            "confirmations": position["confirmations"],
        })

    # Calculate metrics
    if not trades:
        return {"error": "No trades"}

    returns = [t["return_pct"] / 100 for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]

    total_return = (equity_curve[-1] / initial_capital - 1) * 100
    max_equity = max(equity_curve)
    drawdowns = [(max_equity - e) / max_equity for e in equity_curve]
    max_dd = max(drawdowns) * 100

    # Sortino (downside deviation)
    neg_returns = [r for r in returns if r < 0]
    downside_std = np.std(neg_returns) if neg_returns else 0.001
    avg_return = np.mean(returns)
    sortino = (avg_return / downside_std) if downside_std > 0 else 0

    # By confirmation count
    by_conf = {}
    for conf in [1, 2, 3]:
        conf_trades = [t for t in trades if t["confirmations"] == conf]
        if conf_trades:
            conf_returns = [t["return_pct"] for t in conf_trades]
            by_conf[conf] = {
                "count": len(conf_trades),
                "avg_return": np.mean(conf_returns),
                "win_rate": len([r for r in conf_returns if r > 0]) / len(conf_returns) * 100,
            }

    return {
        "trades": len(trades),
        "total_return": total_return,
        "max_drawdown": max_dd,
        "sortino": sortino,
        "win_rate": len(wins) / len(returns) * 100 if returns else 0,
        "avg_win": np.mean(wins) * 100 if wins else 0,
        "avg_loss": np.mean(losses) * 100 if losses else 0,
        "profit_factor": abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else 0,
        "final_equity": equity_curve[-1],
        "by_confirmation": by_conf,
        "trade_details": trades,
    }


def main():
    print("=" * 60)
    print("MTF + ADX Confirmation Backtest")
    print("=" * 60)

    # Load data
    print("\nLoading BTC data...")
    data = load_all_timeframes("BTC")

    if len(data) < 3:
        print("Missing timeframe data!")
        return

    # Test configurations (ALL NO LEVERAGE - max 50% position)
    configs = [
        # Original MTF (no ADX) - strict thresholds
        ("Original MTF (vel<-1.5, acc>3.0)", MTFConfig(
            vel_threshold=-1.5,
            acc_threshold=3.0,
            adx_vel_threshold=None,  # No ADX
        )),

        # MTF + ADX with original thresholds
        ("MTF+ADX (vel<-1.5, acc>3.0, adx<-1.0)", MTFConfig(
            vel_threshold=-1.5,
            acc_threshold=3.0,
            adx_vel_threshold=-1.0,
        )),

        # MTF + ADX with lower thresholds (more signals)
        ("MTF+ADX Lower (vel<-1.25, acc>1.5, adx<-1.0)", MTFConfig(
            vel_threshold=-1.25,
            acc_threshold=1.5,
            adx_vel_threshold=-1.0,
        )),

        # MTF + ADX even lower (max signals)
        ("MTF+ADX Lowest (vel<-1.0, acc>1.0, adx<-0.5)", MTFConfig(
            vel_threshold=-1.0,
            acc_threshold=1.0,
            adx_vel_threshold=-0.5,
        )),

        # Single TF + ADX (no MTF requirement) for comparison
        ("Single TF+ADX (vel<-1.25, acc>1.5, adx<-1.0)", MTFConfig(
            vel_threshold=-1.25,
            acc_threshold=1.5,
            adx_vel_threshold=-1.0,
            kelly_1tf=0.50,  # Use same size regardless of TF count
            kelly_2tf=0.50,
            kelly_3tf=0.50,
        )),
    ]

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    results = []
    for name, config in configs:
        print(f"\n{name}")
        print("-" * len(name))

        result = run_backtest(data, config, min_confirmations=1)

        if "error" in result:
            print(f"  Error: {result['error']}")
            continue

        print(f"  Trades:      {result['trades']}")
        print(f"  Return:      {result['total_return']:.1f}%")
        print(f"  Max DD:      {result['max_drawdown']:.1f}%")
        print(f"  Sortino:     {result['sortino']:.2f}")
        print(f"  Win Rate:    {result['win_rate']:.1f}%")
        print(f"  Profit Factor: {result['profit_factor']:.2f}")
        print(f"  Final Equity: ${result['final_equity']:,.0f}")

        if result.get("by_confirmation"):
            print("\n  By Confirmation:")
            for conf, stats in sorted(result["by_confirmation"].items()):
                print(f"    {conf}TF: {stats['count']} trades, {stats['avg_return']:.2f}% avg, {stats['win_rate']:.1f}% win")

        results.append((name, result))

    # Summary comparison
    print("\n" + "=" * 60)
    print("COMPARISON SUMMARY")
    print("=" * 60)
    print(f"\n{'Config':<45} {'Trades':>7} {'Return':>8} {'MaxDD':>7} {'Sortino':>8}")
    print("-" * 80)
    for name, result in results:
        if "error" not in result:
            print(f"{name:<45} {result['trades']:>7} {result['total_return']:>7.1f}% {result['max_drawdown']:>6.1f}% {result['sortino']:>8.2f}")


if __name__ == "__main__":
    main()
