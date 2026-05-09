"""
Test Bear Protection Service with real data.

Shows regime changes over time and validates the service logic.
"""

import polars as pl
from pathlib import Path
from datetime import datetime, timezone
import sys

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from Fast_Swarm.Infrastructure.Services.bear_protection_service import (
    BearProtectionService, MarketState, Regime
)

DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")


def load_mtf(symbol: str = "BTC"):
    """Load and align MTF data."""
    base_path = DERIVATIVES_DIR / f"symbol={symbol}"

    df_1h = pl.read_parquet(base_path / "timeframe=1h").sort("time")
    df_4h = pl.read_parquet(base_path / "timeframe=4h").sort("time")
    df_1d = pl.read_parquet(base_path / "timeframe=1d").sort("time")

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


def main():
    print("=" * 80)
    print("BEAR PROTECTION SERVICE TEST")
    print("=" * 80)

    # Load BTC data
    print("\nLoading BTC data...")
    df = load_mtf("BTC")
    rows = df.to_dicts()
    print(f"Loaded {len(rows):,} hourly candles")

    # Create service
    service = BearProtectionService()

    # Track regime changes
    regime_changes = []
    regime_counts = {Regime.DEFENSIVE: 0, Regime.NEUTRAL: 0, Regime.AGGRESSIVE: 0}
    last_regime = None

    print("\nProcessing all candles...")
    for row in rows:
        state = row_to_market_state(row, "BTC")
        result = service.evaluate(state)

        regime_counts[result.regime] += 1

        if result.regime != last_regime:
            price = row.get("close", 0)
            regime_changes.append({
                "time": row.get("time"),
                "from": last_regime.value if last_regime else "INIT",
                "to": result.regime.value,
                "trigger": result.triggered_by,
                "price": price,
            })
            last_regime = result.regime

    # Summary
    total = sum(regime_counts.values())
    print("\n" + "=" * 80)
    print("REGIME DISTRIBUTION")
    print("=" * 80)
    for regime, count in sorted(regime_counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        hours = count
        days = hours / 24
        print(f"  {regime.value:<12} {count:>8,} hours ({pct:>5.1f}%) = {days:>6.0f} days")

    print("\n" + "=" * 80)
    print(f"REGIME CHANGES ({len(regime_changes)} total)")
    print("=" * 80)

    # Show first 10 and last 10
    print("\nFirst 10:")
    print(f"{'Time':<25} {'From':<12} {'To':<12} {'Trigger':<20} {'Price':>12}")
    print("-" * 85)
    for rc in regime_changes[:10]:
        t = rc["time"].strftime("%Y-%m-%d %H:%M") if rc["time"] else "?"
        print(f"{t:<25} {rc['from']:<12} {rc['to']:<12} {rc['trigger']:<20} ${rc['price']:>10,.0f}")

    print("\nLast 10:")
    print(f"{'Time':<25} {'From':<12} {'To':<12} {'Trigger':<20} {'Price':>12}")
    print("-" * 85)
    for rc in regime_changes[-10:]:
        t = rc["time"].strftime("%Y-%m-%d %H:%M") if rc["time"] else "?"
        print(f"{t:<25} {rc['from']:<12} {rc['to']:<12} {rc['trigger']:<20} ${rc['price']:>10,.0f}")

    # Analyze regime transitions
    print("\n" + "=" * 80)
    print("TRANSITION ANALYSIS")
    print("=" * 80)

    transitions = {}
    for rc in regime_changes[1:]:  # Skip INIT
        key = f"{rc['from']} -> {rc['to']}"
        transitions[key] = transitions.get(key, 0) + 1

    for trans, count in sorted(transitions.items(), key=lambda x: -x[1]):
        print(f"  {trans:<30} {count:>5} times")

    # Current state
    print("\n" + "=" * 80)
    print("CURRENT STATE")
    print("=" * 80)
    last_row = rows[-1]
    last_state = row_to_market_state(last_row, "BTC")
    current = service.evaluate(last_state)

    print(f"\n  Time:          {last_row.get('time')}")
    print(f"  Price:         ${last_row.get('close'):,.0f}")
    print(f"  Regime:        {current.regime.value}")
    print(f"  Max Position:  {current.max_position*100:.0f}%")
    print(f"  Exit Active:   {current.exit_signal_active}")
    print(f"  Entry Active:  {current.entry_signal_active}")
    print(f"  Trigger:       {current.triggered_by}")


if __name__ == "__main__":
    main()
