"""
Equity Basket Forward Validation for Bear Protection

Tests bear protection thresholds (discovered on BTC/ETH crypto) across
a diverse equity basket to validate generalization.

Symbols:
  - AAPL, NVDA (Mag7 tech)
  - TSLA, PLTR (Growth/volatile)
  - JPM, XOM (Value)
  - SPY (Benchmark)
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

import polars as pl

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from Fast_Swarm.Infrastructure.Services.bear_protection_service import (
    BearProtectionService, MarketState, Regime
)


# =============================================================================
# CONFIGURATION
# =============================================================================

DATA_DIR = PROJECT_ROOT / "data" / "test_data" / "EQUITY_BASKET"

SYMBOLS = ["AAPL", "NVDA", "TSLA", "PLTR", "JPM", "XOM", "SPY"]

# Test with 1h/4h combination (our primary finding)
TF1, TF2 = "1h", "4h"


# =============================================================================
# DATA LOADING
# =============================================================================

def load_symbol_mtf(symbol: str) -> pl.DataFrame:
    """Load and join multi-timeframe data for a symbol."""
    path_tf1 = DATA_DIR / f"{symbol}_{TF1}.parquet"
    path_tf2 = DATA_DIR / f"{symbol}_{TF2}.parquet"

    if not path_tf1.exists() or not path_tf2.exists():
        raise FileNotFoundError(f"Missing data for {symbol}")

    df1 = pl.read_parquet(path_tf1).sort("timestamp")
    df2 = pl.read_parquet(path_tf2).sort("timestamp")

    # Columns for bear protection
    deriv_cols = [
        "close_velocity_zscore",
        "close_acceleration_zscore",
        "close_jerk_zscore",
        "ADX_14_jerk_zscore",  # pandas_ta naming
    ]

    # Map to lowercase for consistency
    deriv_cols_lower = [c.lower() for c in deriv_cols]

    # Find available columns (case-insensitive)
    tf1_cols = []
    for c in deriv_cols:
        if c in df1.columns:
            tf1_cols.append(c)
        elif c.lower() in df1.columns:
            tf1_cols.append(c.lower())

    tf2_cols = []
    for c in deriv_cols:
        if c in df2.columns:
            tf2_cols.append(c)
        elif c.lower() in df2.columns:
            tf2_cols.append(c.lower())

    # Prepare TF2 for join
    tf2_select = [pl.col("timestamp").alias(f"tf2_time")]
    for c in tf2_cols:
        tf2_select.append(pl.col(c).alias(f"tf2_{c}"))

    df2_join = df2.select(tf2_select)

    # Join
    result = df1.join_asof(df2_join, left_on="timestamp", right_on="tf2_time", strategy="backward")

    # Rename TF1 cols
    for c in tf1_cols:
        if c in result.columns:
            result = result.rename({c: f"tf1_{c}"})

    return result, tf1_cols, tf2_cols


def row_to_market_state(row: dict, symbol: str, tf1_cols: list, tf2_cols: list) -> MarketState:
    """Convert row to MarketState."""
    ts = row.get("timestamp", datetime.now(timezone.utc))

    # Try to get values with case-insensitive matching
    def get_val(prefix, col_list, target):
        for c in col_list:
            if target.lower() in c.lower():
                key = f"{prefix}_{c}"
                if key in row:
                    return row[key]
        return None

    return MarketState(
        time=ts,
        symbol=symbol,
        tf_1h_vel=get_val("tf1", tf1_cols, "velocity"),
        tf_1h_acc=get_val("tf1", tf1_cols, "acceleration"),
        tf_1h_adx_jerk=get_val("tf1", tf1_cols, "adx"),
        tf_4h_vel=get_val("tf2", tf2_cols, "velocity"),
        tf_4h_acc=get_val("tf2", tf2_cols, "acceleration"),
        tf_4h_adx_jerk=get_val("tf2", tf2_cols, "adx"),
        tf_1d_vel=None,
        tf_1d_acc=None,
        tf_1d_adx_jerk=None,
    )


# =============================================================================
# VALIDATION
# =============================================================================

def validate_symbol(symbol: str) -> dict:
    """Run bear protection validation for a single symbol."""
    print(f"\n  {symbol}...", end=" ", flush=True)

    try:
        df, tf1_cols, tf2_cols = load_symbol_mtf(symbol)
        rows = df.to_dicts()
    except Exception as e:
        print(f"ERROR: {e}")
        return {"symbol": symbol, "error": str(e)}

    if len(rows) < 100:
        print(f"SKIP (only {len(rows)} rows)")
        return {"symbol": symbol, "error": "insufficient_data"}

    service = BearProtectionService()

    # Track regimes
    regime_counts = {Regime.DEFENSIVE: 0, Regime.NEUTRAL: 0, Regime.AGGRESSIVE: 0}
    regime_returns = {Regime.DEFENSIVE: [], Regime.NEUTRAL: [], Regime.AGGRESSIVE: []}
    last_regime = Regime.NEUTRAL
    regime_changes = 0

    for i, row in enumerate(rows):
        state = row_to_market_state(row, symbol, tf1_cols, tf2_cols)
        result = service.evaluate(state)

        regime_counts[result.regime] += 1

        # Track returns
        if i > 0 and "close" in row and "close" in rows[i-1]:
            prev = rows[i-1]["close"]
            curr = row["close"]
            if prev and curr and prev > 0:
                ret = (curr - prev) / prev
                regime_returns[last_regime].append(ret)

        if result.regime != last_regime:
            regime_changes += 1
            last_regime = result.regime

    total = sum(regime_counts.values())

    # Calculate performance metrics
    def avg_ret(rets):
        return sum(rets) / len(rets) * 100 if rets else 0

    def total_ret(rets):
        return sum(rets) * 100 if rets else 0

    def sharpe_approx(rets):
        if len(rets) < 10:
            return 0
        import statistics
        mean = statistics.mean(rets)
        std = statistics.stdev(rets)
        return (mean / std) * (252 ** 0.5) if std > 0 else 0  # Annualized

    result = {
        "symbol": symbol,
        "candles": total,
        "regime_pct": {
            "DEF": regime_counts[Regime.DEFENSIVE] / total * 100,
            "NEU": regime_counts[Regime.NEUTRAL] / total * 100,
            "AGG": regime_counts[Regime.AGGRESSIVE] / total * 100,
        },
        "regime_changes": regime_changes,
        "switches_per_day": regime_changes / (total / 24) if total > 24 else 0,
        "returns": {
            "DEF_avg": avg_ret(regime_returns[Regime.DEFENSIVE]),
            "NEU_avg": avg_ret(regime_returns[Regime.NEUTRAL]),
            "AGG_avg": avg_ret(regime_returns[Regime.AGGRESSIVE]),
            "DEF_total": total_ret(regime_returns[Regime.DEFENSIVE]),
            "NEU_total": total_ret(regime_returns[Regime.NEUTRAL]),
            "AGG_total": total_ret(regime_returns[Regime.AGGRESSIVE]),
        },
        # Defense works if DEFENSIVE has lower avg return than AGGRESSIVE
        "defense_works": avg_ret(regime_returns[Regime.DEFENSIVE]) < avg_ret(regime_returns[Regime.AGGRESSIVE]),
    }

    status = "OK" if result["defense_works"] else "CHECK"
    print(f"{status} ({total:,} candles, {regime_changes} switches)")

    return result


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("="*70)
    print("EQUITY BASKET FORWARD VALIDATION")
    print("="*70)
    print()
    print("Testing bear protection thresholds on equity data")
    print(f"TF1={TF1}, TF2={TF2}")
    print(f"Symbols: {', '.join(SYMBOLS)}")
    print()

    if not DATA_DIR.exists():
        print(f"ERROR: Data directory not found: {DATA_DIR}")
        print("Run download_equity_basket.py first")
        return

    # Run validation for each symbol
    results = []
    print("Processing symbols:")

    for symbol in SYMBOLS:
        result = validate_symbol(symbol)
        results.append(result)

    # Summary table
    print("\n" + "="*70)
    print("RESULTS SUMMARY")
    print("="*70)
    print()
    print(f"{'Symbol':<8} {'Candles':>8} {'DEF%':>6} {'NEU%':>6} {'AGG%':>6} {'Sw/Day':>7} {'DEF_ret':>8} {'AGG_ret':>8} {'Status':>8}")
    print("-"*75)

    working = 0
    for r in results:
        if "error" in r:
            print(f"{r['symbol']:<8} ERROR: {r['error']}")
            continue

        status = "PASS" if r["defense_works"] else "FAIL"
        if r["defense_works"]:
            working += 1

        print(f"{r['symbol']:<8} {r['candles']:>8,} "
              f"{r['regime_pct']['DEF']:>5.1f}% {r['regime_pct']['NEU']:>5.1f}% {r['regime_pct']['AGG']:>5.1f}% "
              f"{r['switches_per_day']:>7.2f} "
              f"{r['returns']['DEF_avg']:>7.3f}% {r['returns']['AGG_avg']:>7.3f}% "
              f"{status:>8}")

    # Verdict
    print("\n" + "="*70)
    print("VALIDATION VERDICT")
    print("="*70)

    valid_results = [r for r in results if "error" not in r]
    total_valid = len(valid_results)

    if total_valid == 0:
        print("\n  [ERROR] No valid results to analyze")
    elif working == total_valid:
        print(f"\n  [PASS] Bear protection validates on ALL {total_valid} equities!")
        print("         Thresholds discovered on crypto generalize to stocks.")
    elif working >= total_valid * 0.7:
        print(f"\n  [PASS] {working}/{total_valid} equities validated ({working/total_valid*100:.0f}%)")
        print("         Strong evidence of generalization.")
    elif working >= total_valid * 0.5:
        print(f"\n  [PARTIAL] {working}/{total_valid} equities validated ({working/total_valid*100:.0f}%)")
        print("            Some tuning may be needed for equity characteristics.")
    else:
        print(f"\n  [INVESTIGATE] Only {working}/{total_valid} equities validated")
        print("                Thresholds may need recalibration for equities.")

    # Category breakdown
    print("\n  By Category:")
    categories = {
        "Mag7 Tech": ["AAPL", "NVDA"],
        "Growth/Vol": ["TSLA", "PLTR"],
        "Value": ["JPM", "XOM"],
        "Benchmark": ["SPY"],
    }

    for cat, syms in categories.items():
        cat_results = [r for r in valid_results if r["symbol"] in syms]
        cat_pass = sum(1 for r in cat_results if r.get("defense_works", False))
        print(f"    {cat:<12}: {cat_pass}/{len(cat_results)} pass")


if __name__ == "__main__":
    main()
