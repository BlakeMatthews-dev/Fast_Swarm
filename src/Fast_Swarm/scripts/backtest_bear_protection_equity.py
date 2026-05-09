"""
Backtest Bear Protection on Equity Basket

Compares Buy & Hold vs Bear Protection Strategy with proper metrics:
  - Total ROI
  - Sortino Ratio
  - Max Drawdown
  - Win Rate

Strategy Rules:
  - AGGRESSIVE: 100% invested
  - NEUTRAL: 50% invested
  - DEFENSIVE: 0% invested (cash)
"""

import sys
from pathlib import Path
from datetime import datetime
import statistics

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
TF1, TF2 = "1h", "4h"

# Position sizing by regime
POSITION_SIZE = {
    Regime.AGGRESSIVE: 1.0,   # 100% invested
    Regime.NEUTRAL: 0.5,      # 50% invested
    Regime.DEFENSIVE: 0.0,    # 0% - cash
}


# =============================================================================
# METRICS
# =============================================================================

def compute_sortino(returns: list, target: float = 0) -> float:
    """Compute Sortino ratio (annualized for hourly data)."""
    if len(returns) < 10:
        return 0.0

    mean_ret = statistics.mean(returns)
    downside = [min(0, r - target) ** 2 for r in returns]
    downside_std = (sum(downside) / len(downside)) ** 0.5

    if downside_std == 0:
        return 0.0

    # Annualize: sqrt(24 * 252) for hourly data
    annualization = (24 * 252) ** 0.5
    return (mean_ret / downside_std) * annualization


def compute_max_drawdown(equity_curve: list) -> float:
    """Compute maximum drawdown as percentage."""
    if not equity_curve:
        return 0.0

    peak = equity_curve[0]
    max_dd = 0.0

    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

    return max_dd * 100


def compute_win_rate(returns: list) -> float:
    """Compute win rate (% of positive returns)."""
    if not returns:
        return 0.0
    wins = sum(1 for r in returns if r > 0)
    return wins / len(returns) * 100


# =============================================================================
# DATA LOADING
# =============================================================================

def load_symbol_mtf(symbol: str) -> pl.DataFrame:
    """Load and join MTF data."""
    path_tf1 = DATA_DIR / f"{symbol}_{TF1}.parquet"
    path_tf2 = DATA_DIR / f"{symbol}_{TF2}.parquet"

    df1 = pl.read_parquet(path_tf1).sort("timestamp")
    df2 = pl.read_parquet(path_tf2).sort("timestamp")

    deriv_cols = ["close_velocity_zscore", "close_acceleration_zscore",
                  "close_jerk_zscore", "ADX_14_jerk_zscore"]

    tf1_cols = [c for c in deriv_cols if c in df1.columns or c.lower() in df1.columns]
    tf2_cols = [c for c in deriv_cols if c in df2.columns or c.lower() in df2.columns]

    # Use actual column names
    tf1_actual = []
    for c in tf1_cols:
        if c in df1.columns:
            tf1_actual.append(c)
        elif c.lower() in df1.columns:
            tf1_actual.append(c.lower())

    tf2_actual = []
    for c in tf2_cols:
        if c in df2.columns:
            tf2_actual.append(c)
        elif c.lower() in df2.columns:
            tf2_actual.append(c.lower())

    # Prepare join
    tf2_select = [pl.col("timestamp").alias("tf2_time")]
    for c in tf2_actual:
        tf2_select.append(pl.col(c).alias(f"tf2_{c}"))

    df2_join = df2.select(tf2_select)
    result = df1.join_asof(df2_join, left_on="timestamp", right_on="tf2_time", strategy="backward")

    for c in tf1_actual:
        if c in result.columns:
            result = result.rename({c: f"tf1_{c}"})

    return result, tf1_actual, tf2_actual


def row_to_market_state(row: dict, symbol: str, tf1_cols: list, tf2_cols: list) -> MarketState:
    """Convert row to MarketState."""
    ts = row.get("timestamp", datetime.now())

    def get_val(prefix, col_list, target):
        for c in col_list:
            if target.lower() in c.lower():
                key = f"{prefix}_{c}"
                if key in row:
                    return row[key]
        return None

    return MarketState(
        time=ts, symbol=symbol,
        tf_1h_vel=get_val("tf1", tf1_cols, "velocity"),
        tf_1h_acc=get_val("tf1", tf1_cols, "acceleration"),
        tf_1h_adx_jerk=get_val("tf1", tf1_cols, "adx"),
        tf_4h_vel=get_val("tf2", tf2_cols, "velocity"),
        tf_4h_acc=get_val("tf2", tf2_cols, "acceleration"),
        tf_4h_adx_jerk=get_val("tf2", tf2_cols, "adx"),
        tf_1d_vel=None, tf_1d_acc=None, tf_1d_adx_jerk=None,
    )


# =============================================================================
# BACKTEST
# =============================================================================

def backtest_symbol(symbol: str) -> dict:
    """Run backtest for a single symbol."""
    try:
        df, tf1_cols, tf2_cols = load_symbol_mtf(symbol)
        rows = df.to_dicts()
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}

    if len(rows) < 100:
        return {"symbol": symbol, "error": "insufficient_data"}

    service = BearProtectionService()

    # Track equity curves
    bh_equity = [1.0]      # Buy & Hold starts at 1.0
    bp_equity = [1.0]      # Bear Protection starts at 1.0

    bh_returns = []
    bp_returns = []

    last_regime = Regime.NEUTRAL
    regime_counts = {Regime.DEFENSIVE: 0, Regime.NEUTRAL: 0, Regime.AGGRESSIVE: 0}

    for i in range(1, len(rows)):
        prev_row = rows[i - 1]
        curr_row = rows[i]

        prev_close = prev_row.get("close")
        curr_close = curr_row.get("close")

        if not prev_close or not curr_close or prev_close <= 0:
            continue

        # Calculate return for this period
        period_return = (curr_close - prev_close) / prev_close

        # Buy & Hold: always 100% invested
        bh_returns.append(period_return)
        bh_equity.append(bh_equity[-1] * (1 + period_return))

        # Bear Protection: position based on regime
        state = row_to_market_state(curr_row, symbol, tf1_cols, tf2_cols)
        result = service.evaluate(state)

        regime_counts[result.regime] += 1
        position = POSITION_SIZE[last_regime]  # Use LAST regime (signal comes after close)

        bp_return = period_return * position
        bp_returns.append(bp_return)
        bp_equity.append(bp_equity[-1] * (1 + bp_return))

        last_regime = result.regime

    # Calculate metrics
    total = sum(regime_counts.values())

    return {
        "symbol": symbol,
        "candles": len(rows),
        # Buy & Hold metrics
        "bh_roi": (bh_equity[-1] - 1) * 100,
        "bh_sortino": compute_sortino(bh_returns),
        "bh_max_dd": compute_max_drawdown(bh_equity),
        "bh_win_rate": compute_win_rate(bh_returns),
        # Bear Protection metrics
        "bp_roi": (bp_equity[-1] - 1) * 100,
        "bp_sortino": compute_sortino(bp_returns),
        "bp_max_dd": compute_max_drawdown(bp_equity),
        "bp_win_rate": compute_win_rate(bp_returns),
        # Comparison
        "roi_diff": (bp_equity[-1] - 1) * 100 - (bh_equity[-1] - 1) * 100,
        "dd_reduction": compute_max_drawdown(bh_equity) - compute_max_drawdown(bp_equity),
        # Regime distribution
        "regime_pct": {
            "DEF": regime_counts[Regime.DEFENSIVE] / total * 100 if total else 0,
            "NEU": regime_counts[Regime.NEUTRAL] / total * 100 if total else 0,
            "AGG": regime_counts[Regime.AGGRESSIVE] / total * 100 if total else 0,
        },
    }


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("="*80)
    print("BEAR PROTECTION BACKTEST - EQUITY BASKET")
    print("="*80)
    print()
    print(f"Strategy: AGGRESSIVE=100%, NEUTRAL=50%, DEFENSIVE=0%")
    print(f"Timeframes: TF1={TF1}, TF2={TF2}")
    print(f"Symbols: {', '.join(SYMBOLS)}")
    print()

    if not DATA_DIR.exists():
        print(f"ERROR: Data not found at {DATA_DIR}")
        print("Run download_equity_basket.py first")
        return

    results = []
    print("Running backtests...")
    print()

    for symbol in SYMBOLS:
        print(f"  {symbol}...", end=" ", flush=True)
        result = backtest_symbol(symbol)
        results.append(result)

        if "error" in result:
            print(f"ERROR: {result['error']}")
        else:
            better = "BETTER" if result["roi_diff"] > 0 else "WORSE"
            print(f"BH={result['bh_roi']:+.1f}%  BP={result['bp_roi']:+.1f}%  ({better})")

    # Summary table
    print()
    print("="*80)
    print("RESULTS COMPARISON")
    print("="*80)
    print()
    print(f"{'Symbol':<8} |{'--- BUY & HOLD ---':^30}|{'--- BEAR PROTECTION ---':^30}| {'Diff':>8}")
    print(f"{'':8} |{'ROI':>8} {'Sortino':>8} {'MaxDD':>8} |{'ROI':>8} {'Sortino':>8} {'MaxDD':>8} | {'ROI':>8}")
    print("-"*90)

    valid_results = [r for r in results if "error" not in r]

    for r in results:
        if "error" in r:
            print(f"{r['symbol']:<8} | ERROR: {r['error']}")
            continue

        print(f"{r['symbol']:<8} |"
              f"{r['bh_roi']:>+7.1f}% {r['bh_sortino']:>7.2f} {r['bh_max_dd']:>7.1f}% |"
              f"{r['bp_roi']:>+7.1f}% {r['bp_sortino']:>7.2f} {r['bp_max_dd']:>7.1f}% |"
              f"{r['roi_diff']:>+7.1f}%")

    # Averages
    if valid_results:
        print("-"*90)
        avg_bh_roi = sum(r["bh_roi"] for r in valid_results) / len(valid_results)
        avg_bh_sortino = sum(r["bh_sortino"] for r in valid_results) / len(valid_results)
        avg_bh_dd = sum(r["bh_max_dd"] for r in valid_results) / len(valid_results)
        avg_bp_roi = sum(r["bp_roi"] for r in valid_results) / len(valid_results)
        avg_bp_sortino = sum(r["bp_sortino"] for r in valid_results) / len(valid_results)
        avg_bp_dd = sum(r["bp_max_dd"] for r in valid_results) / len(valid_results)
        avg_diff = sum(r["roi_diff"] for r in valid_results) / len(valid_results)

        print(f"{'AVERAGE':<8} |"
              f"{avg_bh_roi:>+7.1f}% {avg_bh_sortino:>7.2f} {avg_bh_dd:>7.1f}% |"
              f"{avg_bp_roi:>+7.1f}% {avg_bp_sortino:>7.2f} {avg_bp_dd:>7.1f}% |"
              f"{avg_diff:>+7.1f}%")

    # Verdict
    print()
    print("="*80)
    print("VERDICT")
    print("="*80)

    if not valid_results:
        print("\n  [ERROR] No valid results")
        return

    # Count wins
    roi_wins = sum(1 for r in valid_results if r["roi_diff"] > 0)
    dd_wins = sum(1 for r in valid_results if r["dd_reduction"] > 0)
    sortino_wins = sum(1 for r in valid_results if r["bp_sortino"] > r["bh_sortino"])

    print()
    print(f"  ROI Improvement:      {roi_wins}/{len(valid_results)} symbols beat buy & hold")
    print(f"  Drawdown Reduction:   {dd_wins}/{len(valid_results)} symbols have lower max DD")
    print(f"  Sortino Improvement:  {sortino_wins}/{len(valid_results)} symbols have better Sortino")
    print()

    avg_dd_reduction = sum(r["dd_reduction"] for r in valid_results) / len(valid_results)
    print(f"  Average DD Reduction: {avg_dd_reduction:+.1f}%")
    print(f"  Average ROI Diff:     {avg_diff:+.1f}%")

    # Overall assessment
    print()
    if dd_wins >= len(valid_results) * 0.7:
        print("  [PASS] Bear protection successfully reduces drawdowns across equities")
    elif dd_wins >= len(valid_results) * 0.5:
        print("  [PARTIAL] Bear protection shows mixed results on equities")
    else:
        print("  [INVESTIGATE] Bear protection may need tuning for equity characteristics")


if __name__ == "__main__":
    main()
