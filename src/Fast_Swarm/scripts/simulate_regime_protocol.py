"""
Regime-Based Position Protocol Simulation.

Uses the discovered exit/entry signals as a position sizing overlay
for ALL pattern trades.

Exit Signal: vel>0.5 AND acc<-1.5 AND adx_jerk<0 -> DEFENSIVE (25%)
Entry Signal: vel<-1.5 AND acc>3.0 -> AGGRESSIVE (75%)
Default: NEUTRAL (50%)
"""

import polars as pl
import numpy as np
from pathlib import Path

DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")

# Position levels
DEFENSIVE = 0.25   # 25% position when exit signal fires
NEUTRAL = 0.50     # 50% position default
AGGRESSIVE = 0.75  # 75% position when entry signal fires


def load_mtf(symbol):
    base_path = DERIVATIVES_DIR / f"symbol={symbol}"
    try:
        df_1h = pl.read_parquet(base_path / "timeframe=1h").sort("time")
        df_4h = pl.read_parquet(base_path / "timeframe=4h").sort("time")
        df_1d = pl.read_parquet(base_path / "timeframe=1d").sort("time")
    except:
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


def safe_get(row, col, default=0):
    v = row.get(col)
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return default
    return v


def check_exit(row):
    """Check if DEFENSIVE regime (exit signal fires)."""
    for tf in ["1h", "4h", "1d"]:
        vel = safe_get(row, f"tf_{tf}_close_velocity_zscore")
        acc = safe_get(row, f"tf_{tf}_close_acceleration_zscore")
        jerk = safe_get(row, f"tf_{tf}_adx_14_jerk_zscore")
        if vel > 0.5 and acc < -1.5 and jerk < 0:
            return True
    return False


def check_entry(row):
    """Check if AGGRESSIVE regime (entry signal fires)."""
    for tf in ["1h", "4h", "1d"]:
        vel = safe_get(row, f"tf_{tf}_close_velocity_zscore")
        acc = safe_get(row, f"tf_{tf}_close_acceleration_zscore")
        if vel < -1.5 and acc > 3.0:
            return True
    return False


def get_regime(row):
    """Get current regime and position multiplier."""
    if check_exit(row):
        return "DEFENSIVE", DEFENSIVE
    elif check_entry(row):
        return "AGGRESSIVE", AGGRESSIVE
    else:
        return "NEUTRAL", NEUTRAL


def simulate_pattern_trades(df, use_regime=True, hold_hours=24):
    """Simulate random pattern trades with optional regime-based sizing."""
    rows = df.to_dicts()
    capital = 10000.0
    equity = [capital]
    trades = []

    # Generate random pattern signals (~1% chance per hour)
    pattern_signals = np.random.random(len(rows)) < 0.01

    position = None

    for i, row in enumerate(rows):
        price = row.get("close", 0)
        if price <= 0:
            continue

        regime, position_mult = get_regime(row)

        # Close position after hold period
        if position and i - position["entry_idx"] >= hold_hours:
            ret = (price / position["entry_price"] - 1)
            pnl = position["size"] * ret
            capital += position["size"] + pnl
            trades.append({
                "entry_regime": position["regime"],
                "exit_regime": regime,
                "return": ret * 100,
                "size_pct": position["size"] / 10000 * 100,
            })
            position = None

        # Open new position on pattern signal
        if position is None and pattern_signals[i]:
            if use_regime:
                size = capital * position_mult * 0.5  # 50% of allowed
            else:
                size = capital * NEUTRAL * 0.5  # Fixed 25%

            position = {
                "entry_idx": i,
                "entry_price": price,
                "size": size,
                "regime": regime,
            }
            capital -= size

        # Track equity
        if position:
            mtm = position["size"] * (price / position["entry_price"])
            equity.append(capital + mtm)
        else:
            equity.append(capital)

    # Close final position
    if position:
        price = rows[-1].get("close", position["entry_price"])
        ret = (price / position["entry_price"] - 1)
        pnl = position["size"] * ret
        capital += position["size"] + pnl

    final_ret = (equity[-1] / 10000 - 1) * 100

    # Max drawdown
    peak = equity[0]
    max_dd = 0
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak
        if dd > max_dd:
            max_dd = dd

    # Analyze by entry regime
    regime_stats = {}
    for regime in ["DEFENSIVE", "NEUTRAL", "AGGRESSIVE"]:
        rt = [t for t in trades if t["entry_regime"] == regime]
        if rt:
            regime_stats[regime] = {
                "count": len(rt),
                "avg_ret": np.mean([t["return"] for t in rt]),
                "win_rate": len([t for t in rt if t["return"] > 0]) / len(rt) * 100,
                "avg_size": np.mean([t["size_pct"] for t in rt]),
            }

    return {
        "return": final_ret,
        "max_dd": max_dd * 100,
        "trades": len(trades),
        "regime_stats": regime_stats,
    }


def main():
    print("=" * 100)
    print("REGIME-BASED POSITION PROTOCOL SIMULATION")
    print("=" * 100)
    print("\nPosition Levels:")
    print(f"  DEFENSIVE (exit signal):  {DEFENSIVE*100:.0f}%")
    print(f"  NEUTRAL (default):        {NEUTRAL*100:.0f}%")
    print(f"  AGGRESSIVE (entry signal): {AGGRESSIVE*100:.0f}%")

    df = load_mtf("BTC")
    rows = df.to_dicts()
    print(f"\nData: {len(df):,} hourly candles")

    # Analyze regime distribution
    print("\n" + "=" * 100)
    print("REGIME DISTRIBUTION OVER HISTORY")
    print("=" * 100)

    regime_hours = {"DEFENSIVE": 0, "NEUTRAL": 0, "AGGRESSIVE": 0}
    last_regime = "NEUTRAL"

    for row in rows:
        regime, _ = get_regime(row)
        # Sticky regime (stays until opposite signal)
        if regime == "NEUTRAL":
            regime = last_regime
        regime_hours[regime] += 1
        last_regime = regime

    total = sum(regime_hours.values())
    print(f"\n{'Regime':<15} {'Hours':>10} {'Pct':>8} {'Equiv Days':>12}")
    print("-" * 50)
    for regime, hours in sorted(regime_hours.items()):
        print(f"{regime:<15} {hours:>10,} {hours/total*100:>7.1f}% {hours/24:>11.0f}")

    # Monte Carlo simulation
    print("\n" + "=" * 100)
    print("MONTE CARLO: 500 SIMULATIONS OF RANDOM PATTERN TRADES")
    print("=" * 100)

    regime_results = []
    static_results = []

    for i in range(500):
        np.random.seed(None)
        r_regime = simulate_pattern_trades(df, use_regime=True)
        r_static = simulate_pattern_trades(df, use_regime=False)
        regime_results.append(r_regime)
        static_results.append(r_static)

    regime_rets = [r["return"] for r in regime_results]
    static_rets = [r["return"] for r in static_results]
    regime_dds = [r["max_dd"] for r in regime_results]
    static_dds = [r["max_dd"] for r in static_results]

    print(f"\n{'Metric':<25} {'Regime-Based':>15} {'Static 50%':>15} {'Delta':>15}")
    print("-" * 75)
    print(f"{'Mean Return':<25} {np.mean(regime_rets):>14.1f}% {np.mean(static_rets):>14.1f}% {np.mean(regime_rets)-np.mean(static_rets):>+14.1f}%")
    print(f"{'Median Return':<25} {np.median(regime_rets):>14.1f}% {np.median(static_rets):>14.1f}% {np.median(regime_rets)-np.median(static_rets):>+14.1f}%")
    print(f"{'Std Dev':<25} {np.std(regime_rets):>14.1f}% {np.std(static_rets):>14.1f}%")
    print(f"{'Mean Max DD':<25} {np.mean(regime_dds):>14.1f}% {np.mean(static_dds):>14.1f}% {np.mean(regime_dds)-np.mean(static_dds):>+14.1f}%")
    print(f"{'Best Case':<25} {np.max(regime_rets):>14.1f}% {np.max(static_rets):>14.1f}%")
    print(f"{'Worst Case':<25} {np.min(regime_rets):>14.1f}% {np.min(static_rets):>14.1f}%")
    print(f"{'Win Rate (>0%)':<25} {len([r for r in regime_rets if r>0])/5:>13.1f}% {len([r for r in static_rets if r>0])/5:>13.1f}%")

    # Detailed breakdown
    print("\n" + "=" * 100)
    print("TRADE PERFORMANCE BY ENTRY REGIME (aggregated over all simulations)")
    print("=" * 100)

    all_def = []
    all_neu = []
    all_agg = []

    for r in regime_results:
        if "DEFENSIVE" in r["regime_stats"]:
            all_def.append(r["regime_stats"]["DEFENSIVE"]["avg_ret"])
        if "NEUTRAL" in r["regime_stats"]:
            all_neu.append(r["regime_stats"]["NEUTRAL"]["avg_ret"])
        if "AGGRESSIVE" in r["regime_stats"]:
            all_agg.append(r["regime_stats"]["AGGRESSIVE"]["avg_ret"])

    print(f"\n{'Entry Regime':<15} {'Avg Trade Return':>18} {'Observations':>15}")
    print("-" * 55)
    if all_def:
        print(f"{'DEFENSIVE':<15} {np.mean(all_def):>17.2f}% {len(all_def):>15}")
    if all_neu:
        print(f"{'NEUTRAL':<15} {np.mean(all_neu):>17.2f}% {len(all_neu):>15}")
    if all_agg:
        print(f"{'AGGRESSIVE':<15} {np.mean(all_agg):>17.2f}% {len(all_agg):>15}")

    print("\n" + "=" * 100)
    print("CONCLUSION")
    print("=" * 100)
    improvement = np.mean(regime_rets) - np.mean(static_rets)
    dd_improvement = np.mean(static_dds) - np.mean(regime_dds)
    print(f"\nRegime-based sizing vs static 50%:")
    print(f"  Return improvement: {improvement:+.1f}%")
    print(f"  Drawdown reduction: {dd_improvement:+.1f}%")
    print(f"\nThe regime protocol {'IMPROVES' if improvement > 0 else 'HURTS'} random pattern performance!")


if __name__ == "__main__":
    main()
