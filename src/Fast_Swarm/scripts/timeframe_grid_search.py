"""
Timeframe Grid Search: Find optimal TF combinations for Bear Protection.

Tests different timeframe pairs for the AJ signal (acc + ADX_jerk):
- Current baseline: 1h + 4h
- Candidates: 1h/6h, 4h/6h, 6h/1d, 1h/1d, 4h/1d, 15m/1h, 15m/4h

For each combo, requires BOTH timeframes to show DEFENSIVE signal.
"""

import sys
from pathlib import Path
from datetime import datetime
import statistics
import math
from itertools import combinations

import polars as pl

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

CRYPTO_DIR = PROJECT_ROOT / "data" / "derivatives"
CAPITAL = 1000

# AJ config thresholds
ACC_THRESH = -1.5
JERK_THRESH = -0.5

# Available timeframes to test (ordered by duration)
TIMEFRAMES = ["15m", "1h", "4h", "6h", "1d"]

# Timeframe pairs to test (short_tf, long_tf)
# Note: 15m excluded - too many rows (317K) slows everything down
TF_PAIRS = [
    ("1h", "4h"),    # Current baseline
    ("1h", "6h"),    # Medium spread
    ("4h", "6h"),    # Close together
    ("4h", "1d"),    # Medium + slow
    ("6h", "1d"),    # Slow pair
    ("1h", "1d"),    # Wide spread
]

# Crypto symbols to test
SYMBOLS = ["BTC", "ETH", "SOL"]


def compute_max_drawdown(equity_curve: list) -> float:
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


def load_crypto_tf(symbol: str, timeframe: str) -> dict:
    """Load crypto data for a specific timeframe, indexed by time."""
    path = CRYPTO_DIR / f"symbol={symbol}" / f"timeframe={timeframe}" / "data.parquet"
    if not path.exists():
        return None
    df = pl.read_parquet(path).sort("time")
    rows = df.to_dicts()
    # Index by time for easy lookup
    return {r["time"]: r for r in rows}


def check_defensive_aj(row: dict) -> bool:
    """Check if AJ defensive signal fires for one row."""
    acc = row.get("close_acceleration_zscore")
    jerk = row.get("adx_14_jerk_zscore")  # lowercase in crypto
    if acc is None or jerk is None:
        return False
    return acc < ACC_THRESH and jerk < JERK_THRESH


def align_timeframes(tf1_data: dict, tf2_data: dict, base_tf: str) -> list:
    """
    Align two timeframes for comparison.
    Returns list of (time, tf1_row, tf2_row) tuples where both have data.

    For higher timeframes, we use the most recent candle that closed before each base time.
    Optimized O(n+m) algorithm using two pointers.
    """
    # Pre-sort both timeframes once
    base_times = sorted(tf1_data.keys())
    tf2_times = sorted(tf2_data.keys())

    if not base_times or not tf2_times:
        return []

    aligned = []
    tf2_idx = 0  # Pointer into tf2_times

    for t in base_times:
        tf1_row = tf1_data.get(t)
        if not tf1_row:
            continue

        # Advance tf2_idx while next tf2 time is still <= current base time
        while tf2_idx + 1 < len(tf2_times) and tf2_times[tf2_idx + 1] <= t:
            tf2_idx += 1

        # Check if current tf2 time is valid (at or before base time)
        if tf2_times[tf2_idx] <= t:
            tf2_row = tf2_data[tf2_times[tf2_idx]]
            aligned.append((t, tf1_row, tf2_row))

    return aligned


def backtest_tf_pair(symbol: str, tf1: str, tf2: str) -> dict:
    """Run CTC backtest with specific timeframe pair."""

    # Load both timeframes
    tf1_data = load_crypto_tf(symbol, tf1)
    tf2_data = load_crypto_tf(symbol, tf2)

    if not tf1_data or not tf2_data:
        return None

    # Align timeframes
    aligned = align_timeframes(tf1_data, tf2_data, tf1)

    if len(aligned) < 100:  # Need enough data
        return None

    # Use tf1 prices for trading (shorter timeframe)
    prices = [a[1].get("close", 0) for a in aligned]
    if not prices or prices[0] <= 0:
        return None

    # B&H
    bh_shares = CAPITAL / prices[0]
    bh_equity = [CAPITAL]

    # CTC with 2-TF confirmation
    ctc_shares = CAPITAL / prices[0]
    ctc_cash = 0.0
    in_defensive = False
    ctc_equity = [CAPITAL]
    def_count = 0

    warmup = 50  # Warmup for indicator calculation
    for i in range(warmup, len(aligned)):
        price = prices[i]
        _, tf1_row, tf2_row = aligned[i]

        bh_equity.append(bh_shares * price)

        # Check both TFs for defensive signal
        tf1_def = check_defensive_aj(tf1_row)
        tf2_def = check_defensive_aj(tf2_row)

        # Require BOTH timeframes to agree
        is_def = tf1_def and tf2_def
        if is_def:
            def_count += 1

        if is_def and ctc_shares > 0:
            ctc_cash = ctc_shares * price
            ctc_shares = 0
            in_defensive = True
        elif not is_def and in_defensive and ctc_cash > 0:
            ctc_shares = ctc_cash / price if price > 0 else 0
            ctc_cash = 0
            in_defensive = False

        ctc_equity.append(ctc_shares * price + ctc_cash)

    if len(bh_equity) < 10:
        return None

    bh_roi = (bh_equity[-1] / CAPITAL - 1) * 100
    ctc_roi = (ctc_equity[-1] / CAPITAL - 1) * 100
    bh_dd = compute_max_drawdown(bh_equity)
    ctc_dd = compute_max_drawdown(ctc_equity)

    trading_periods = len(aligned) - warmup

    return {
        "symbol": symbol,
        "tf_pair": f"{tf1}/{tf2}",
        "bh_roi": bh_roi,
        "ctc_roi": ctc_roi,
        "roi_diff": ctc_roi - bh_roi,
        "bh_dd": bh_dd,
        "ctc_dd": ctc_dd,
        "dd_diff": ctc_dd - bh_dd,
        "def_pct": def_count / trading_periods * 100 if trading_periods > 0 else 0,
        "n_periods": trading_periods,
    }


def run_timeframe_grid():
    print("="*100)
    print("TIMEFRAME GRID SEARCH: Finding Optimal TF Combinations")
    print("="*100)
    print()
    print("Testing AJ config (acc < -1.5, jerk < -0.5) across timeframe pairs")
    print("Requires BOTH timeframes to show DEFENSIVE for signal to fire")
    print()
    print(f"Timeframe pairs to test: {len(TF_PAIRS)}")
    print(f"Symbols: {SYMBOLS}")
    print()

    # Test each TF pair on each symbol
    all_results = []

    for tf1, tf2 in TF_PAIRS:
        pair_name = f"{tf1}/{tf2}"
        print(f"Testing {pair_name}...", end=" ", flush=True)

        pair_results = []
        for sym in SYMBOLS:
            r = backtest_tf_pair(sym, tf1, tf2)
            if r:
                pair_results.append(r)
                all_results.append(r)

        if pair_results:
            avg_roi = statistics.mean([r["roi_diff"] for r in pair_results])
            print(f"OK ({len(pair_results)} symbols, avg ROI diff: {avg_roi:+.1f}%)")
        else:
            print("No data")

    print()

    # Aggregate by TF pair
    print("="*100)
    print("RESULTS BY TIMEFRAME PAIR")
    print("="*100)
    print()
    print(f"{'TF Pair':<12} {'Avg ROI':>12} {'Win':>6} {'Avg DD':>12} {'Def%':>8} {'BTC':>10} {'ETH':>10} {'SOL':>10}")
    print("-"*95)

    tf_summaries = {}
    for tf1, tf2 in TF_PAIRS:
        pair_name = f"{tf1}/{tf2}"
        pair_results = [r for r in all_results if r["tf_pair"] == pair_name]

        if pair_results:
            avg_roi = statistics.mean([r["roi_diff"] for r in pair_results])
            win_count = sum(1 for r in pair_results if r["roi_diff"] > 0)
            avg_dd = statistics.mean([r["dd_diff"] for r in pair_results])
            avg_def = statistics.mean([r["def_pct"] for r in pair_results])

            # Per-symbol results
            btc_roi = next((r["roi_diff"] for r in pair_results if r["symbol"] == "BTC"), None)
            eth_roi = next((r["roi_diff"] for r in pair_results if r["symbol"] == "ETH"), None)
            sol_roi = next((r["roi_diff"] for r in pair_results if r["symbol"] == "SOL"), None)

            tf_summaries[pair_name] = {
                "avg_roi": avg_roi,
                "win_count": win_count,
                "total": len(pair_results),
                "avg_dd": avg_dd,
                "avg_def": avg_def,
                "btc": btc_roi,
                "eth": eth_roi,
                "sol": sol_roi,
            }

            btc_str = f"{btc_roi:+.1f}%" if btc_roi is not None else "N/A"
            eth_str = f"{eth_roi:+.1f}%" if eth_roi is not None else "N/A"
            sol_str = f"{sol_roi:+.1f}%" if sol_roi is not None else "N/A"

            print(f"{pair_name:<12} {avg_roi:>+11.1f}% {win_count:>3}/{len(pair_results):>2} {avg_dd:>+11.1f}% {avg_def:>7.1f}% {btc_str:>10} {eth_str:>10} {sol_str:>10}")

    # Sort by average ROI diff
    print()
    print("="*100)
    print("RANKING: Best to Worst TF Pairs")
    print("="*100)
    print()

    sorted_pairs = sorted(tf_summaries.items(), key=lambda x: x[1]["avg_roi"], reverse=True)

    for rank, (pair_name, summary) in enumerate(sorted_pairs, 1):
        status = "BEST" if rank == 1 else ("BASELINE" if pair_name == "1h/4h" else "")
        print(f"  {rank}. {pair_name:<10}: {summary['avg_roi']:>+6.1f}% avg ROI diff, {summary['avg_dd']:>+6.1f}% DD diff  {status}")

    # Compare to baseline
    print()
    print("="*100)
    print("COMPARISON TO BASELINE (1h/4h)")
    print("="*100)
    print()

    baseline = tf_summaries.get("1h/4h", {})
    baseline_roi = baseline.get("avg_roi", 0)

    for pair_name, summary in sorted_pairs:
        if pair_name != "1h/4h":
            diff = summary["avg_roi"] - baseline_roi
            status = "BETTER" if diff > 0 else "WORSE"
            print(f"  {pair_name}: {diff:>+6.1f}% vs baseline -> {status}")

    # Signal frequency analysis
    print()
    print("="*100)
    print("SIGNAL FREQUENCY ANALYSIS")
    print("="*100)
    print()
    print("Lower = fewer signals = more conservative")
    print()

    for pair_name, summary in sorted(tf_summaries.items(), key=lambda x: x[1]["avg_def"]):
        print(f"  {pair_name:<12}: {summary['avg_def']:>5.1f}% defensive periods")

    # Best for each symbol
    print()
    print("="*100)
    print("BEST TF PAIR PER SYMBOL")
    print("="*100)
    print()

    for sym in SYMBOLS:
        sym_results = [r for r in all_results if r["symbol"] == sym]
        if sym_results:
            best = max(sym_results, key=lambda x: x["roi_diff"])
            print(f"  {sym}: {best['tf_pair']} -> {best['roi_diff']:+.1f}% ROI diff")

    # Final recommendation
    print()
    print("="*100)
    print("RECOMMENDATION")
    print("="*100)
    print()

    if sorted_pairs:
        best_pair = sorted_pairs[0][0]
        best_summary = sorted_pairs[0][1]
        baseline_summary = tf_summaries.get("1h/4h", {})

        if best_pair == "1h/4h":
            print(f"KEEP BASELINE: 1h/4h is already optimal")
            print(f"  Avg ROI diff: {best_summary['avg_roi']:+.1f}%")
        elif best_summary["avg_roi"] > baseline_summary.get("avg_roi", 0) + 5:
            print(f"CONSIDER SWITCHING TO: {best_pair}")
            print(f"  Avg ROI diff: {best_summary['avg_roi']:+.1f}% (vs {baseline_summary.get('avg_roi', 0):+.1f}% baseline)")
            print(f"  Improvement: {best_summary['avg_roi'] - baseline_summary.get('avg_roi', 0):+.1f}%")
        else:
            print(f"MARGINAL IMPROVEMENT: {best_pair} slightly better but within noise")
            print(f"  Recommend sticking with 1h/4h for stability")


if __name__ == "__main__":
    run_timeframe_grid()
