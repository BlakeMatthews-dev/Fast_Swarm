"""
Backtest: Triple Timeframe Divergence Signal

Uses 3 timeframes with tiered Kelly sizing:
- 1 TF confirms = 1/3 Kelly (low confidence)
- 2 TF confirm = 2/3 Kelly (medium confidence)
- 3 TF confirm = Full Kelly (high confidence)

Author: Coinswarm Research
"""

import polars as pl
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import json

DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")
RESULTS_DIR = Path("c:/fast_swarm/data/analysis_results")
RESULTS_DIR.mkdir(exist_ok=True)


@dataclass
class TripleTFConfig:
    """Triple timeframe backtest parameters."""
    initial_capital: float = 10000.0
    stop_loss_pct: float = 0.25

    # Tiered Kelly based on confirmation count
    kelly_1tf: float = 0.33    # 1/3 Kelly for single TF
    kelly_2tf: float = 0.66    # 2/3 Kelly for two TFs
    kelly_3tf: float = 1.0     # Full Kelly for all three

    # Signal thresholds
    entry_velocity_threshold: float = -1.5
    entry_accel_threshold: float = 3.0
    exit_velocity_threshold: float = 1.5
    exit_accel_threshold: float = -3.0

    # Risk management
    max_position_pct: float = 0.50
    min_position_pct: float = 0.05

    # Timeframes (highest to lowest)
    tf_high: str = "1d"
    tf_mid: str = "4h"
    tf_low: str = "1h"


@dataclass
class Trade:
    entry_time: datetime
    entry_price: float
    entry_reason: str
    position_size: float
    shares: float
    confirmation_count: int  # 1, 2, or 3

    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0

    def close(self, exit_time: datetime, exit_price: float, exit_reason: str):
        self.exit_time = exit_time
        self.exit_price = exit_price
        self.exit_reason = exit_reason
        self.pnl = (exit_price - self.entry_price) * self.shares
        self.pnl_pct = (exit_price / self.entry_price - 1) * 100


@dataclass
class BacktestState:
    capital: float
    position: Optional[Trade] = None
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)
    wins: int = 0
    losses: int = 0
    total_win_pct: float = 0.0
    total_loss_pct: float = 0.0


def load_timeframe_data(symbol: str, timeframe: str) -> pl.DataFrame:
    path = DERIVATIVES_DIR / f"symbol={symbol}" / f"timeframe={timeframe}"
    if not path.exists():
        raise FileNotFoundError(f"Data not found at {path}")
    df = pl.read_parquet(path)
    return df.sort("time")


def align_three_timeframes(df_primary: pl.DataFrame,
                           df_mid: pl.DataFrame,
                           df_high: pl.DataFrame) -> pl.DataFrame:
    """Align three timeframes to the primary (lowest) timeframe."""

    # Get columns from mid timeframe
    df_m = df_mid.select([
        pl.col("time").alias("mid_time"),
        pl.col("close_velocity_zscore").alias("mid_velocity_zscore"),
        pl.col("close_acceleration_zscore").alias("mid_accel_zscore"),
    ])

    # Get columns from high timeframe
    df_h = df_high.select([
        pl.col("time").alias("high_time"),
        pl.col("close_velocity_zscore").alias("high_velocity_zscore"),
        pl.col("close_acceleration_zscore").alias("high_accel_zscore"),
    ])

    # Join mid to primary
    result = df_primary.join_asof(
        df_m,
        left_on="time",
        right_on="mid_time",
        strategy="backward"
    )

    # Join high to result
    result = result.join_asof(
        df_h,
        left_on="time",
        right_on="high_time",
        strategy="backward"
    )

    return result


def detect_signal(vel, acc, config: TripleTFConfig, is_entry: bool = True) -> bool:
    """Check if a single timeframe shows the divergence signal."""
    if vel is None or acc is None:
        return False
    if np.isnan(vel) or np.isnan(acc):
        return False

    if is_entry:
        return vel < config.entry_velocity_threshold and acc > config.entry_accel_threshold
    else:
        return vel > config.exit_velocity_threshold and acc < config.exit_accel_threshold


def count_confirmations(row: dict, config: TripleTFConfig, is_entry: bool = True) -> int:
    """Count how many timeframes show the signal."""
    count = 0

    # Primary (low) timeframe
    if detect_signal(
        row.get("close_velocity_zscore"),
        row.get("close_acceleration_zscore"),
        config, is_entry
    ):
        count += 1

    # Mid timeframe
    if detect_signal(
        row.get("mid_velocity_zscore"),
        row.get("mid_accel_zscore"),
        config, is_entry
    ):
        count += 1

    # High timeframe
    if detect_signal(
        row.get("high_velocity_zscore"),
        row.get("high_accel_zscore"),
        config, is_entry
    ):
        count += 1

    return count


def get_kelly_for_confirmations(count: int, state: BacktestState,
                                 config: TripleTFConfig) -> float:
    """Get Kelly fraction based on confirmation count."""
    # Base Kelly from historical performance
    if state.wins + state.losses < 5:
        base_kelly = 0.10
    else:
        win_prob = state.wins / (state.wins + state.losses)

        if state.losses == 0:
            base_kelly = 0.30
        elif state.wins == 0:
            base_kelly = config.min_position_pct
        else:
            avg_win = state.total_win_pct / state.wins if state.wins > 0 else 0
            avg_loss = abs(state.total_loss_pct / state.losses) if state.losses > 0 else 1
            if avg_loss == 0:
                avg_loss = 1
            win_loss_ratio = avg_win / avg_loss
            base_kelly = win_prob - (1 - win_prob) / win_loss_ratio

    # Apply tiered multiplier
    if count == 3:
        multiplier = config.kelly_3tf
    elif count == 2:
        multiplier = config.kelly_2tf
    else:
        multiplier = config.kelly_1tf

    kelly = base_kelly * multiplier
    return max(config.min_position_pct, min(config.max_position_pct, kelly))


def run_triple_tf_backtest(df: pl.DataFrame, config: TripleTFConfig,
                           min_confirmations: int = 1,
                           verbose: bool = True) -> BacktestState:
    """Run backtest requiring minimum confirmations to enter."""
    state = BacktestState(capital=config.initial_capital)
    rows = df.to_dicts()
    n_rows = len(rows)

    if verbose:
        print(f"\nRunning Triple TF backtest on {n_rows:,} candles...")
        print(f"Timeframes: {config.tf_high} + {config.tf_mid} + {config.tf_low}")
        print(f"Min confirmations to enter: {min_confirmations}")
        print(f"Kelly tiers: 1TF={config.kelly_1tf}x, 2TF={config.kelly_2tf}x, 3TF={config.kelly_3tf}x")
        print("-" * 60)

    for i, row in enumerate(rows):
        current_time = row["time"]
        current_price = row["close"]

        if current_price is None or np.isnan(current_price) or current_price <= 0:
            continue

        # Record equity
        if state.position:
            unrealized = (current_price - state.position.entry_price) * state.position.shares
            equity = state.capital + unrealized
            dd = (current_price / state.position.entry_price - 1) * 100
            if dd < state.position.max_drawdown_pct:
                state.position.max_drawdown_pct = dd
        else:
            equity = state.capital

        state.equity_curve.append({"time": current_time, "equity": equity})

        # Check for exit if in position
        if state.position:
            exit_reason = None

            # Stop loss
            drawdown = (current_price / state.position.entry_price) - 1
            if drawdown <= -config.stop_loss_pct:
                exit_reason = "STOP_LOSS"
            # Exit signal on primary timeframe
            elif detect_signal(
                row.get("close_velocity_zscore"),
                row.get("close_acceleration_zscore"),
                config, is_entry=False
            ):
                exit_reason = "EXIT_SIGNAL"

            if exit_reason:
                state.position.close(current_time, current_price, exit_reason)
                state.capital += state.position.pnl

                if state.position.pnl >= 0:
                    state.wins += 1
                    state.total_win_pct += state.position.pnl_pct
                else:
                    state.losses += 1
                    state.total_loss_pct += state.position.pnl_pct

                state.trades.append(state.position)
                state.position = None

        # Check for entry
        else:
            confirmations = count_confirmations(row, config, is_entry=True)

            if confirmations >= min_confirmations:
                kelly_pct = get_kelly_for_confirmations(confirmations, state, config)
                position_size = state.capital * kelly_pct
                shares = position_size / current_price

                state.position = Trade(
                    entry_time=current_time,
                    entry_price=current_price,
                    entry_reason=f"DIVERGENCE_{confirmations}TF",
                    position_size=position_size,
                    shares=shares,
                    confirmation_count=confirmations
                )

                if verbose and len(state.trades) < 10:
                    print(f"  ENTRY ({confirmations}TF): {current_time.strftime('%Y-%m-%d')} @ "
                          f"${current_price:,.2f} | Size: ${position_size:,.0f} ({kelly_pct*100:.0f}%)")

    # Close any open position
    if state.position:
        final_row = rows[-1]
        state.position.close(final_row["time"], final_row["close"], "END_OF_DATA")
        state.capital += state.position.pnl
        if state.position.pnl >= 0:
            state.wins += 1
            state.total_win_pct += state.position.pnl_pct
        else:
            state.losses += 1
            state.total_loss_pct += state.position.pnl_pct
        state.trades.append(state.position)

    return state


def analyze_results(state: BacktestState, config: TripleTFConfig) -> dict:
    if not state.trades:
        return {"error": "No trades"}

    n_trades = len(state.trades)
    n_wins = sum(1 for t in state.trades if t.pnl >= 0)
    win_rate = n_wins / n_trades if n_trades > 0 else 0

    all_pnl_pct = [t.pnl_pct for t in state.trades]
    win_pnl = [t.pnl_pct for t in state.trades if t.pnl >= 0]
    loss_pnl = [t.pnl_pct for t in state.trades if t.pnl < 0]

    avg_win = np.mean(win_pnl) if win_pnl else 0
    avg_loss = np.mean(loss_pnl) if loss_pnl else 0

    # By confirmation count
    by_conf = {}
    for conf in [1, 2, 3]:
        trades = [t for t in state.trades if t.confirmation_count == conf]
        if trades:
            pnls = [t.pnl_pct for t in trades]
            wins = sum(1 for p in pnls if p >= 0)
            by_conf[conf] = {
                "trades": len(trades),
                "win_rate": wins / len(trades) * 100,
                "avg_return": np.mean(pnls),
            }

    # Time span
    if state.trades:
        first = state.trades[0]
        last = state.trades[-1]
        days = (last.exit_time - first.entry_time).days if last.exit_time else 0
        years = days / 365.25 if days > 0 else 1
    else:
        years = 1

    total_return = (state.capital / config.initial_capital) - 1
    cagr = (state.capital / config.initial_capital) ** (1/years) - 1 if years > 0 else 0

    gross_profit = sum(t.pnl for t in state.trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in state.trades if t.pnl < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

    return {
        "summary": {
            "final_capital": state.capital,
            "total_return_pct": total_return * 100,
            "cagr_pct": cagr * 100,
            "years": years,
        },
        "trades": {
            "total": n_trades,
            "wins": n_wins,
            "losses": n_trades - n_wins,
            "win_rate_pct": win_rate * 100,
        },
        "returns": {
            "avg_win_pct": avg_win,
            "avg_loss_pct": avg_loss,
            "expectancy_pct": expectancy,
        },
        "risk": {
            "profit_factor": profit_factor,
        },
        "by_confirmation": by_conf,
    }


def print_results(results: dict, label: str):
    s = results["summary"]
    t = results["trades"]
    r = results["returns"]
    by_conf = results.get("by_confirmation", {})

    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"{'='*60}")
    print(f"Final Capital:   ${s['final_capital']:>10,.2f}")
    print(f"Total Return:    {s['total_return_pct']:>10.1f}%")
    print(f"CAGR:            {s['cagr_pct']:>10.1f}%")
    print(f"Trades:          {t['total']:>10}")
    print(f"Win Rate:        {t['win_rate_pct']:>10.1f}%")
    print(f"Avg Win:         {r['avg_win_pct']:>10.1f}%")
    print(f"Avg Loss:        {r['avg_loss_pct']:>10.1f}%")
    print(f"Expectancy:      {r['expectancy_pct']:>10.2f}%")
    print(f"Profit Factor:   {results['risk']['profit_factor']:>10.2f}")

    if by_conf:
        print(f"\n--- By Confirmation Count ---")
        for conf in [1, 2, 3]:
            if conf in by_conf:
                c = by_conf[conf]
                print(f"  {conf} TF: {c['trades']:>4} trades | "
                      f"Win: {c['win_rate']:.0f}% | "
                      f"Avg: {c['avg_return']:+.1f}%")


def test_super_kelly_3tf(df_aligned: pl.DataFrame, base_config: TripleTFConfig) -> dict:
    """
    Test various Kelly multipliers when all 3 TFs confirm.
    Super-Kelly means using >1.0x position sizing for high-conviction trades.
    """
    print("\n" + "=" * 70)
    print("SUPER-KELLY TEST: What multiplier for 3TF confirmation?")
    print("Testing: 1TF=0.33x, 2TF=0.66x, 3TF=VARIABLE")
    print("=" * 70)

    # Test multipliers from 0.5x to 2.0x
    multipliers = [0.5, 0.75, 1.0, 1.2, 1.4, 1.5, 1.6, 1.8, 2.0]
    results = {}

    for mult in multipliers:
        config = TripleTFConfig(
            tf_high=base_config.tf_high,
            tf_mid=base_config.tf_mid,
            tf_low=base_config.tf_low,
            kelly_1tf=0.33,
            kelly_2tf=0.66,
            kelly_3tf=mult,
            # Allow larger positions for super-kelly
            max_position_pct=0.50 * mult if mult > 1.0 else 0.50,
        )

        state = run_triple_tf_backtest(df_aligned, config,
                                       min_confirmations=1,
                                       verbose=False)
        analysis = analyze_results(state, config)
        results[mult] = analysis

    # Print comparison
    print(f"\n{'3TF Kelly':<10} | {'Return':>8} | {'3TF Trades':>10} | {'3TF WinRate':>11} | {'Overall':>8}")
    print("-" * 70)

    for mult, r in results.items():
        if "error" in r:
            print(f"{mult}x         | ERROR")
            continue

        # Get 3TF specific stats
        by_conf = r.get("by_confirmation", {})
        tf3_stats = by_conf.get(3, {"trades": 0, "win_rate": 0, "avg_return": 0})

        print(f"{mult}x         | "
              f"{r['summary']['total_return_pct']:>7.1f}% | "
              f"{tf3_stats['trades']:>10} | "
              f"{tf3_stats['win_rate']:>10.0f}% | "
              f"{r['trades']['win_rate_pct']:>7.1f}%")

    return results


def test_tiered_super_kelly(df_aligned: pl.DataFrame, base_config: TripleTFConfig) -> dict:
    """
    Test BOTH 2TF and 3TF super-kelly scenarios.
    Maybe 2TF should also get a boost?
    """
    print("\n" + "=" * 70)
    print("TIERED SUPER-KELLY TEST")
    print("Testing various combinations of 2TF and 3TF multipliers")
    print("=" * 70)

    # Test matrix: 2TF and 3TF multipliers
    test_cases = [
        # Standard
        {"name": "Conservative", "k1": 0.33, "k2": 0.66, "k3": 1.0},
        # Moderate boost
        {"name": "2TF=0.8, 3TF=1.2", "k1": 0.33, "k2": 0.80, "k3": 1.2},
        {"name": "2TF=1.0, 3TF=1.5", "k1": 0.33, "k2": 1.00, "k3": 1.5},
        # Aggressive
        {"name": "2TF=1.2, 3TF=2.0", "k1": 0.33, "k2": 1.20, "k3": 2.0},
        {"name": "Full Leverage", "k1": 0.50, "k2": 1.50, "k3": 2.0},
        # SUPER AGGRESSIVE - 3TF goes YOLO
        {"name": "YOLO 2.5x", "k1": 0.50, "k2": 1.50, "k3": 2.5},
        {"name": "YOLO 3.0x", "k1": 0.50, "k2": 1.50, "k3": 3.0},
        {"name": "YOLO 3.5x", "k1": 0.50, "k2": 1.50, "k3": 3.5},
        {"name": "YOLO 4.0x", "k1": 0.50, "k2": 1.50, "k3": 4.0},
        # ULTRA - max 2TF too
        {"name": "ULTRA 2TF=2.0, 3TF=3.0", "k1": 0.50, "k2": 2.00, "k3": 3.0},
        {"name": "ULTRA 2TF=2.0, 3TF=4.0", "k1": 0.50, "k2": 2.00, "k3": 4.0},
        {"name": "ULTRA 2TF=2.5, 3TF=5.0", "k1": 0.50, "k2": 2.50, "k3": 5.0},
    ]

    results = []

    for case in test_cases:
        config = TripleTFConfig(
            tf_high=base_config.tf_high,
            tf_mid=base_config.tf_mid,
            tf_low=base_config.tf_low,
            kelly_1tf=case["k1"],
            kelly_2tf=case["k2"],
            kelly_3tf=case["k3"],
            # Allow larger positions
            max_position_pct=max(0.50, case["k3"] * 0.50),
        )

        state = run_triple_tf_backtest(df_aligned, config,
                                       min_confirmations=1,
                                       verbose=False)
        analysis = analyze_results(state, config)

        results.append({
            "name": case["name"],
            "k1": case["k1"],
            "k2": case["k2"],
            "k3": case["k3"],
            **analysis
        })

    # Print comparison
    print(f"\n{'Config':<20} | {'Return':>8} | {'Trades':>6} | {'WinRate':>7} | {'Expect':>7} | {'MaxDD':>6}")
    print("-" * 75)

    for r in results:
        if "error" in r:
            print(f"{r['name']:<20} | ERROR")
            continue

        # Compute max drawdown from equity curve
        max_dd = "N/A"

        print(f"{r['name']:<20} | "
              f"{r['summary']['total_return_pct']:>7.1f}% | "
              f"{r['trades']['total']:>6} | "
              f"{r['trades']['win_rate_pct']:>6.1f}% | "
              f"{r['returns']['expectancy_pct']:>6.2f}% | "
              f"{max_dd:>6}")

    return results


def main():
    print("=" * 70)
    print("TRIPLE TIMEFRAME DIVERGENCE BACKTEST")
    print("Testing: 1d + 4h + 1h with tiered Kelly sizing")
    print("=" * 70)

    config = TripleTFConfig(
        tf_high="1d",
        tf_mid="4h",
        tf_low="1h",
    )

    # Load data
    print(f"\nLoading BTC data for 3 timeframes...")
    try:
        df_low = load_timeframe_data("BTC", config.tf_low)
        print(f"  {config.tf_low}: {len(df_low):,} candles")

        df_mid = load_timeframe_data("BTC", config.tf_mid)
        print(f"  {config.tf_mid}: {len(df_mid):,} candles")

        df_high = load_timeframe_data("BTC", config.tf_high)
        print(f"  {config.tf_high}: {len(df_high):,} candles")
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return

    # Align timeframes
    print("\nAligning timeframes...")
    df_aligned = align_three_timeframes(df_low, df_mid, df_high)
    print(f"  Aligned dataset: {len(df_aligned):,} candles")

    # Test different minimum confirmation requirements
    all_results = {}

    for min_conf in [1, 2, 3]:
        label = f"MIN {min_conf} TF CONFIRMATION"
        state = run_triple_tf_backtest(df_aligned, config,
                                       min_confirmations=min_conf,
                                       verbose=False)
        results = analyze_results(state, config)
        all_results[min_conf] = results
        print_results(results, label)

    # Summary comparison
    print("\n" + "=" * 70)
    print("SUMMARY COMPARISON")
    print("=" * 70)
    print(f"{'Min Conf':<10} | {'Return':>8} | {'Trades':>6} | {'WinRate':>7} | {'Expect':>7} | {'PF':>6}")
    print("-" * 70)

    for min_conf, r in all_results.items():
        if "error" in r:
            continue
        print(f"{min_conf} TF       | "
              f"{r['summary']['total_return_pct']:>7.1f}% | "
              f"{r['trades']['total']:>6} | "
              f"{r['trades']['win_rate_pct']:>6.1f}% | "
              f"{r['returns']['expectancy_pct']:>6.2f}% | "
              f"{r['risk']['profit_factor']:>5.2f}")

    # Special analysis: What if we compare the "by confirmation" breakdown?
    print("\n" + "=" * 70)
    print("BREAKDOWN BY ACTUAL CONFIRMATION COUNT (from min=1 test)")
    print("=" * 70)

    if 1 in all_results and "by_confirmation" in all_results[1]:
        by_conf = all_results[1]["by_confirmation"]
        print(f"{'Confirmations':<15} | {'Trades':>6} | {'WinRate':>7} | {'Avg Return':>10}")
        print("-" * 50)
        for conf in [1, 2, 3]:
            if conf in by_conf:
                c = by_conf[conf]
                print(f"{conf} TF             | {c['trades']:>6} | "
                      f"{c['win_rate']:>6.0f}% | {c['avg_return']:>+9.1f}%")

    # ================================================================
    # SUPER-KELLY TESTS
    # ================================================================
    super_kelly_results = test_super_kelly_3tf(df_aligned, config)
    tiered_results = test_tiered_super_kelly(df_aligned, config)

    # Save results
    results_file = RESULTS_DIR / "triple_tf_backtest_results.json"
    with open(results_file, "w") as f:
        json.dump({
            "standard": all_results,
            "super_kelly_3tf": {str(k): v for k, v in super_kelly_results.items()},
            "tiered_super_kelly": tiered_results,
        }, f, indent=2, default=str)
    print(f"\nResults saved to: {results_file}")

    return all_results


if __name__ == "__main__":
    main()
