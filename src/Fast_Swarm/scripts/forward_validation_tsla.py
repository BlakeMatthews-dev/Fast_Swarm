"""
TSLA Forward Validation Test for Bear Protection

Tests bear protection jerk threshold findings (discovered on BTC/ETH crypto data)
on out-of-sample TSLA stock data.

Purpose: Validate that the AJ (Acceleration + Jerk) signal composition
generalizes to equity data, not just crypto.

Timeframe Combinations Tested:
  - TF1=1h, TF2=4h (primary)
  - TF1=1h, TF2=6h
  - TF1=1h, TF2=1d
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

import polars as pl

# Add src directory to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from Fast_Swarm.Infrastructure.Services.bear_protection_service import (
    BearProtectionService, MarketState, Regime
)


# =============================================================================
# CONFIGURATION
# =============================================================================

TSLA_DATA_DIR = PROJECT_ROOT / "data" / "test_data" / "TSLA_FORWARD_VALIDATION"

# Timeframe combinations to test (TF1, TF2)
TF_COMBINATIONS = [
    ("1h", "4h"),  # Primary: our discovered optimal
    ("1h", "6h"),  # Alternative
    ("1h", "1d"),  # Long-term confirmation
]


# =============================================================================
# DATA LOADING
# =============================================================================

def load_tsla_timeframe(tf: str) -> pl.DataFrame:
    """Load TSLA test parquet for a given timeframe."""
    path = TSLA_DATA_DIR / f"TSLA_{tf}_test.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing test data: {path}")

    df = pl.read_parquet(path)

    # Ensure we have timestamp column
    if "timestamp" not in df.columns and "time" in df.columns:
        df = df.rename({"time": "timestamp"})

    return df.sort("timestamp")


def load_mtf_tsla(tf1: str, tf2: str) -> pl.DataFrame:
    """
    Load and align multi-timeframe TSLA data.

    Returns TF1 data with TF2 columns joined via asof join.
    """
    print(f"  Loading {tf1} and {tf2} data...")

    df_tf1 = load_tsla_timeframe(tf1)
    df_tf2 = load_tsla_timeframe(tf2)

    # Columns we need for bear protection
    derivative_cols = [
        "close_velocity_zscore",
        "close_acceleration_zscore",
        "close_jerk_zscore",
        "adx_14_jerk_zscore",  # May not exist in all TFs
    ]

    # Filter to available columns
    tf1_deriv_cols = [c for c in derivative_cols if c in df_tf1.columns]
    tf2_deriv_cols = [c for c in derivative_cols if c in df_tf2.columns]

    # Prepare TF2 for join
    tf2_select = [pl.col("timestamp").alias(f"tf_{tf2}_time")]
    for c in tf2_deriv_cols:
        tf2_select.append(pl.col(c).alias(f"tf_{tf2}_{c}"))

    df_tf2_join = df_tf2.select(tf2_select)

    # Join TF2 onto TF1
    result = df_tf1.join_asof(
        df_tf2_join,
        left_on="timestamp",
        right_on=f"tf_{tf2}_time",
        strategy="backward"
    )

    # Rename TF1 columns for consistency
    for c in tf1_deriv_cols:
        if c in result.columns:
            result = result.rename({c: f"tf_{tf1}_{c}"})

    # Keep close price for analysis
    if "close" in result.columns:
        pass  # Keep it

    print(f"    Joined: {len(result):,} rows with {len(result.columns)} columns")
    print(f"    TF1 deriv cols: {tf1_deriv_cols}")
    print(f"    TF2 deriv cols: {tf2_deriv_cols}")

    return result


# =============================================================================
# MARKET STATE CONVERSION
# =============================================================================

def row_to_market_state(row: dict, tf1: str, tf2: str) -> MarketState:
    """Convert dataframe row to MarketState for bear protection evaluation."""

    # Get timestamp
    ts = row.get("timestamp")
    if ts is None:
        ts = datetime.now(timezone.utc)

    # TF1 values
    tf1_vel = row.get(f"tf_{tf1}_close_velocity_zscore")
    tf1_acc = row.get(f"tf_{tf1}_close_acceleration_zscore")
    tf1_jerk = row.get(f"tf_{tf1}_close_jerk_zscore")
    tf1_adx_jerk = row.get(f"tf_{tf1}_adx_14_jerk_zscore")

    # TF2 values
    tf2_vel = row.get(f"tf_{tf2}_close_velocity_zscore")
    tf2_acc = row.get(f"tf_{tf2}_close_acceleration_zscore")
    tf2_jerk = row.get(f"tf_{tf2}_close_jerk_zscore")
    tf2_adx_jerk = row.get(f"tf_{tf2}_adx_14_jerk_zscore")

    return MarketState(
        time=ts,
        symbol="TSLA",
        # TF1 -> tf_1h in the service
        tf_1h_vel=tf1_vel,
        tf_1h_acc=tf1_acc,
        tf_1h_adx_jerk=tf1_adx_jerk,
        # TF2 -> tf_4h in the service (we map our TF2 to this)
        tf_4h_vel=tf2_vel,
        tf_4h_acc=tf2_acc,
        tf_4h_adx_jerk=tf2_adx_jerk,
        # Daily not used in these tests
        tf_1d_vel=None,
        tf_1d_acc=None,
        tf_1d_adx_jerk=None,
    )


# =============================================================================
# VALIDATION TEST
# =============================================================================

def run_validation(tf1: str, tf2: str) -> dict:
    """
    Run bear protection validation for a single TF combination.

    Returns metrics about regime detection on TSLA data.
    """
    print(f"\n{'='*70}")
    print(f"TESTING: TF1={tf1}, TF2={tf2}")
    print("="*70)

    # Load data
    df = load_mtf_tsla(tf1, tf2)
    rows = df.to_dicts()

    if len(rows) < 10:
        print(f"  WARNING: Only {len(rows)} rows - insufficient for validation")
        return {"tf1": tf1, "tf2": tf2, "error": "insufficient_data"}

    # Create bear protection service
    service = BearProtectionService()

    # Track regime distribution
    regime_counts = {Regime.DEFENSIVE: 0, Regime.NEUTRAL: 0, Regime.AGGRESSIVE: 0}
    regime_changes = []
    last_regime = None

    # Track price performance by regime
    regime_returns = {Regime.DEFENSIVE: [], Regime.NEUTRAL: [], Regime.AGGRESSIVE: []}

    print(f"\n  Processing {len(rows):,} candles...")

    for i, row in enumerate(rows):
        state = row_to_market_state(row, tf1, tf2)
        result = service.evaluate(state)

        regime_counts[result.regime] += 1

        # Track return during this candle
        if i > 0 and "close" in row and "close" in rows[i-1]:
            prev_close = rows[i-1]["close"]
            curr_close = row["close"]
            if prev_close and curr_close and prev_close > 0:
                ret = (curr_close - prev_close) / prev_close
                regime_returns[last_regime or Regime.NEUTRAL].append(ret)

        # Track regime changes
        if result.regime != last_regime:
            price = row.get("close", 0)
            regime_changes.append({
                "time": row.get("timestamp"),
                "from": last_regime.value if last_regime else "INIT",
                "to": result.regime.value,
                "trigger": result.triggered_by,
                "price": price,
            })
            last_regime = result.regime

    # Calculate metrics
    total = sum(regime_counts.values())

    print("\n  REGIME DISTRIBUTION:")
    print("  " + "-"*50)
    for regime, count in sorted(regime_counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100 if total > 0 else 0
        print(f"    {regime.value:<12} {count:>6} candles ({pct:>5.1f}%)")

    print(f"\n  REGIME CHANGES: {len(regime_changes)} total")

    # Calculate regime switching frequency
    switches_per_day = len(regime_changes) / (total / 24) if total > 24 else len(regime_changes)

    # Calculate average returns by regime
    print("\n  RETURNS BY REGIME:")
    print("  " + "-"*50)
    regime_perf = {}
    for regime in [Regime.DEFENSIVE, Regime.NEUTRAL, Regime.AGGRESSIVE]:
        rets = regime_returns[regime]
        if rets:
            avg_ret = sum(rets) / len(rets) * 100
            total_ret = sum(rets) * 100
            regime_perf[regime.value] = {"avg": avg_ret, "total": total_ret, "n": len(rets)}
            print(f"    {regime.value:<12} avg={avg_ret:>7.3f}% total={total_ret:>7.2f}% (n={len(rets)})")
        else:
            regime_perf[regime.value] = {"avg": 0, "total": 0, "n": 0}
            print(f"    {regime.value:<12} (no data)")

    # Show recent regime changes
    if regime_changes:
        print("\n  RECENT REGIME CHANGES:")
        print("  " + "-"*50)
        for rc in regime_changes[-5:]:
            t = rc["time"]
            if hasattr(t, 'strftime'):
                t_str = t.strftime("%Y-%m-%d %H:%M")
            else:
                t_str = str(t)[:16]
            print(f"    {t_str} {rc['from']:<10} -> {rc['to']:<10} [{rc['trigger']}] ${rc['price']:.2f}")

    # Validation metrics
    # Good sign: DEFENSIVE regime has lower/negative returns (we avoided losses)
    # Good sign: AGGRESSIVE regime has positive returns
    defense_works = regime_perf["DEFENSIVE"]["avg"] < regime_perf["AGGRESSIVE"]["avg"]

    result = {
        "tf1": tf1,
        "tf2": tf2,
        "total_candles": total,
        "regime_counts": {r.value: c for r, c in regime_counts.items()},
        "regime_changes": len(regime_changes),
        "switches_per_day": switches_per_day,
        "regime_performance": regime_perf,
        "defense_works": defense_works,
    }

    return result


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("="*70)
    print("TSLA FORWARD VALIDATION - BEAR PROTECTION")
    print("="*70)
    print()
    print("*** THIS IS OUT-OF-SAMPLE VALIDATION ***")
    print("*** Testing BTC/ETH-discovered thresholds on equity data ***")
    print()
    print(f"Data directory: {TSLA_DATA_DIR}")
    print()

    # Check data exists
    if not TSLA_DATA_DIR.exists():
        print(f"ERROR: Test data directory not found!")
        print(f"       Run tsla_csv_to_test_parquet.py first")
        return

    # List available files
    parquet_files = list(TSLA_DATA_DIR.glob("*.parquet"))
    print(f"Available test data files: {len(parquet_files)}")
    for f in parquet_files:
        df = pl.read_parquet(f)
        print(f"  - {f.name}: {len(df):,} rows, {len(df.columns)} cols")
    print()

    # Run validation for each TF combination
    results = []

    for tf1, tf2 in TF_COMBINATIONS:
        try:
            result = run_validation(tf1, tf2)
            results.append(result)
        except FileNotFoundError as e:
            print(f"\n  SKIPPED: {e}")
            results.append({"tf1": tf1, "tf2": tf2, "error": str(e)})
        except Exception as e:
            print(f"\n  ERROR: {e}")
            import traceback
            traceback.print_exc()
            results.append({"tf1": tf1, "tf2": tf2, "error": str(e)})

    # Summary
    print("\n" + "="*70)
    print("FORWARD VALIDATION SUMMARY")
    print("="*70)
    print()
    print(f"{'TF Combo':<15} {'Candles':>8} {'Changes':>8} {'Sw/Day':>8} {'Defense':>10}")
    print("-"*55)

    for r in results:
        if "error" in r:
            print(f"{r['tf1']}/{r['tf2']:<10} ERROR: {r['error']}")
            continue

        combo = f"{r['tf1']}/{r['tf2']}"
        defense_str = "WORKS" if r["defense_works"] else "CHECK"
        print(f"{combo:<15} {r['total_candles']:>8} {r['regime_changes']:>8} {r['switches_per_day']:>8.2f} {defense_str:>10}")

    # Final verdict
    print("\n" + "="*70)
    print("VALIDATION VERDICT")
    print("="*70)

    working_combos = [r for r in results if r.get("defense_works", False)]

    if len(working_combos) == len(TF_COMBINATIONS):
        print("\n  [PASS] Bear protection generalizes to TSLA equity data!")
        print("         All timeframe combinations show defensive regime")
        print("         has lower returns than aggressive regime.")
    elif len(working_combos) > 0:
        print(f"\n  [PARTIAL] {len(working_combos)}/{len(TF_COMBINATIONS)} combos validated")
        print("            Some TF combinations may need tuning for equity data.")
    else:
        print("\n  [INVESTIGATE] Bear protection thresholds may need adjustment")
        print("                for equity data characteristics.")

    print()
    print("NOTE: TSLA is a high-volatility equity. Results may differ from")
    print("      more typical stocks. Consider testing on broader equity basket.")


if __name__ == "__main__":
    main()
