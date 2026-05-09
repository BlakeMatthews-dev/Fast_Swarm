"""
Parameter Jitter Test: Validate Bear Protection robustness.

Quant validation requirement: Thresholds should work within +/- 30-50% range.
If performance collapses with small parameter changes, we're likely overfitting.

Tests the AJ config (acc + ADX_jerk):
- Base: acc < -1.5, jerk < -0.5
- Jitter: +/- 30% and +/- 50%

Full metrics suite:
- ROI diff (vs B&H)
- Sharpe ratio
- Sortino ratio
- Calmar ratio (CAGR / max drawdown)
- Max drawdown
"""

import sys
from pathlib import Path
from datetime import datetime
import statistics
import math

import polars as pl

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

DATA_DIR = PROJECT_ROOT / "data" / "test_data" / "SP50_DOW30"
CAPITAL = 1000
TRADING_DAYS = 252  # For annualization

# Base thresholds (from AJ config)
BASE_ACC = -1.5
BASE_JERK = -0.5

# Jitter levels to test
JITTER_LEVELS = [
    ("base", 1.0),
    ("-30%", 0.7),
    ("+30%", 1.3),
    ("-50%", 0.5),
    ("+50%", 1.5),
]


def compute_daily_returns(equity_curve: list) -> list:
    """Compute daily returns from equity curve."""
    if len(equity_curve) < 2:
        return []
    returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i-1] > 0:
            ret = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
            returns.append(ret)
    return returns


def compute_sharpe(returns: list, risk_free: float = 0.0) -> float:
    """Annualized Sharpe ratio."""
    if len(returns) < 10:
        return 0.0
    mean_ret = statistics.mean(returns) - risk_free / TRADING_DAYS
    std_ret = statistics.stdev(returns)
    if std_ret == 0:
        return 0.0
    return (mean_ret / std_ret) * math.sqrt(TRADING_DAYS)


def compute_sortino(returns: list, risk_free: float = 0.0) -> float:
    """Annualized Sortino ratio (downside deviation only)."""
    if len(returns) < 10:
        return 0.0
    mean_ret = statistics.mean(returns) - risk_free / TRADING_DAYS
    downside = [r for r in returns if r < 0]
    if len(downside) < 2:
        return 0.0 if mean_ret <= 0 else 10.0  # Cap at 10 if no downside
    downside_std = statistics.stdev(downside)
    if downside_std == 0:
        return 0.0
    return (mean_ret / downside_std) * math.sqrt(TRADING_DAYS)


def compute_cagr(start_val: float, end_val: float, days: int) -> float:
    """Compound Annual Growth Rate."""
    if start_val <= 0 or days <= 0:
        return 0.0
    years = days / TRADING_DAYS
    if years <= 0:
        return 0.0
    return ((end_val / start_val) ** (1 / years) - 1) * 100


def compute_calmar(cagr: float, max_dd: float) -> float:
    """Calmar ratio = CAGR / Max Drawdown."""
    if max_dd <= 0:
        return 0.0 if cagr <= 0 else 10.0  # Cap at 10 if no drawdown
    return cagr / max_dd


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


def load_all_symbols() -> dict:
    data = {}
    files = list(DATA_DIR.glob("*_1d.parquet"))
    for f in files:
        symbol = f.stem.replace("_1d", "")
        try:
            df = pl.read_parquet(f).sort("timestamp")
            data[symbol] = {"rows": df.to_dicts()}
        except:
            pass
    return data


def check_defensive_aj(row: dict, acc_thresh: float, jerk_thresh: float) -> bool:
    """Check if AJ defensive signal fires."""
    acc = row.get("close_acceleration_zscore")
    jerk = row.get("ADX_14_jerk_zscore")

    if acc is None or jerk is None:
        return False

    return acc < acc_thresh and jerk < jerk_thresh


def backtest_with_thresholds(symbol: str, rows: list, acc_thresh: float, jerk_thresh: float) -> dict:
    """Run CTC with specific thresholds. Returns full metrics suite."""
    prices = [r.get("close", 0) for r in rows]
    if not prices or prices[0] <= 0:
        return None

    # B&H
    bh_shares = CAPITAL / prices[0]
    bh_equity = [CAPITAL]

    # CTC
    ctc_shares = CAPITAL / prices[0]
    ctc_cash = 0.0
    in_defensive = False
    ctc_equity = [CAPITAL]
    def_days = 0

    warmup = 21
    for i in range(warmup, len(rows)):
        price = prices[i]
        row = rows[i]

        bh_equity.append(bh_shares * price)

        is_def = check_defensive_aj(row, acc_thresh, jerk_thresh)
        if is_def:
            def_days += 1

        if is_def and ctc_shares > 0:
            ctc_cash = ctc_shares * price
            ctc_shares = 0
            in_defensive = True
        elif not is_def and in_defensive and ctc_cash > 0:
            ctc_shares = ctc_cash / price if price > 0 else 0
            ctc_cash = 0
            in_defensive = False

        ctc_equity.append(ctc_shares * price + ctc_cash)

    # Basic ROI
    bh_roi = (bh_equity[-1] / CAPITAL - 1) * 100
    ctc_roi = (ctc_equity[-1] / CAPITAL - 1) * 100

    # Max drawdown
    bh_dd = compute_max_drawdown(bh_equity)
    ctc_dd = compute_max_drawdown(ctc_equity)

    # Daily returns for ratio calculations
    bh_returns = compute_daily_returns(bh_equity)
    ctc_returns = compute_daily_returns(ctc_equity)

    # Sharpe ratio
    bh_sharpe = compute_sharpe(bh_returns)
    ctc_sharpe = compute_sharpe(ctc_returns)

    # Sortino ratio
    bh_sortino = compute_sortino(bh_returns)
    ctc_sortino = compute_sortino(ctc_returns)

    # CAGR and Calmar
    trading_days = len(rows) - warmup
    bh_cagr = compute_cagr(CAPITAL, bh_equity[-1], trading_days)
    ctc_cagr = compute_cagr(CAPITAL, ctc_equity[-1], trading_days)
    bh_calmar = compute_calmar(bh_cagr, bh_dd)
    ctc_calmar = compute_calmar(ctc_cagr, ctc_dd)

    return {
        "bh_roi": bh_roi,
        "ctc_roi": ctc_roi,
        "roi_diff": ctc_roi - bh_roi,
        "bh_dd": bh_dd,
        "ctc_dd": ctc_dd,
        "dd_diff": ctc_dd - bh_dd,
        "bh_sharpe": bh_sharpe,
        "ctc_sharpe": ctc_sharpe,
        "sharpe_diff": ctc_sharpe - bh_sharpe,
        "bh_sortino": bh_sortino,
        "ctc_sortino": ctc_sortino,
        "sortino_diff": ctc_sortino - bh_sortino,
        "bh_calmar": bh_calmar,
        "ctc_calmar": ctc_calmar,
        "calmar_diff": ctc_calmar - bh_calmar,
        "def_pct": def_days / trading_days * 100 if trading_days > 0 else 0,
    }


def run_jitter_test():
    print("="*100)
    print("PARAMETER JITTER TEST: Validating AJ Config Robustness")
    print("="*100)
    print()
    print("Base thresholds: acc < %.1f, jerk < %.1f" % (BASE_ACC, BASE_JERK))
    print("Testing +/- 30%% and +/- 50%% variations")
    print()

    data = load_all_symbols()
    symbols = list(data.keys())
    print(f"Testing on {len(symbols)} stocks")
    print()

    # Test each jitter level
    jitter_results = {}

    for jitter_name, multiplier in JITTER_LEVELS:
        # For thresholds, jittering means making them more/less sensitive
        # acc threshold: more negative = harder to trigger
        # jerk threshold: more negative = harder to trigger
        # So multiplier > 1 = tighter (harder), < 1 = looser (easier)
        acc_thresh = BASE_ACC * multiplier
        jerk_thresh = BASE_JERK * multiplier

        results = []
        for sym in symbols:
            r = backtest_with_thresholds(sym, data[sym]["rows"], acc_thresh, jerk_thresh)
            if r:
                results.append(r)

        if results:
            # Aggregate all metrics
            jitter_results[jitter_name] = {
                "acc": acc_thresh,
                "jerk": jerk_thresh,
                "n_stocks": len(results),
                # ROI metrics
                "avg_roi_diff": statistics.mean([r["roi_diff"] for r in results]),
                "roi_win_pct": sum(1 for r in results if r["roi_diff"] > 0) / len(results) * 100,
                # Drawdown metrics
                "avg_dd_diff": statistics.mean([r["dd_diff"] for r in results]),
                "avg_ctc_dd": statistics.mean([r["ctc_dd"] for r in results]),
                "avg_bh_dd": statistics.mean([r["bh_dd"] for r in results]),
                # Sharpe metrics
                "avg_sharpe_diff": statistics.mean([r["sharpe_diff"] for r in results]),
                "avg_ctc_sharpe": statistics.mean([r["ctc_sharpe"] for r in results]),
                "avg_bh_sharpe": statistics.mean([r["bh_sharpe"] for r in results]),
                "sharpe_win_pct": sum(1 for r in results if r["sharpe_diff"] > 0) / len(results) * 100,
                # Sortino metrics
                "avg_sortino_diff": statistics.mean([r["sortino_diff"] for r in results]),
                "avg_ctc_sortino": statistics.mean([r["ctc_sortino"] for r in results]),
                "avg_bh_sortino": statistics.mean([r["bh_sortino"] for r in results]),
                "sortino_win_pct": sum(1 for r in results if r["sortino_diff"] > 0) / len(results) * 100,
                # Calmar metrics
                "avg_calmar_diff": statistics.mean([r["calmar_diff"] for r in results]),
                "avg_ctc_calmar": statistics.mean([r["ctc_calmar"] for r in results]),
                "avg_bh_calmar": statistics.mean([r["bh_calmar"] for r in results]),
                "calmar_win_pct": sum(1 for r in results if r["calmar_diff"] > 0) / len(results) * 100,
                # Signal frequency
                "avg_def_pct": statistics.mean([r["def_pct"] for r in results]),
            }

    # Display results - ROI
    print("="*100)
    print("JITTER TEST RESULTS: ROI (Return on Investment)")
    print("="*100)
    print()
    print(f"{'Jitter':<10} {'Acc':>8} {'Jerk':>8} {'ROI Diff':>12} {'Win%':>8} {'Def%':>8}")
    print("-"*60)

    base_roi = jitter_results.get("base", {}).get("avg_roi_diff", 0)

    for jitter_name, _ in JITTER_LEVELS:
        if jitter_name in jitter_results:
            r = jitter_results[jitter_name]
            print(f"{jitter_name:<10} {r['acc']:>8.2f} {r['jerk']:>8.2f} {r['avg_roi_diff']:>+11.1f}% {r['roi_win_pct']:>7.0f}% {r['avg_def_pct']:>7.1f}%")

    # Display results - Sharpe
    print()
    print("="*100)
    print("JITTER TEST RESULTS: SHARPE RATIO")
    print("="*100)
    print()
    print(f"{'Jitter':<10} {'CTC Sharpe':>12} {'B&H Sharpe':>12} {'Sharpe Diff':>14} {'Win%':>8}")
    print("-"*60)

    for jitter_name, _ in JITTER_LEVELS:
        if jitter_name in jitter_results:
            r = jitter_results[jitter_name]
            print(f"{jitter_name:<10} {r['avg_ctc_sharpe']:>12.2f} {r['avg_bh_sharpe']:>12.2f} {r['avg_sharpe_diff']:>+13.2f} {r['sharpe_win_pct']:>7.0f}%")

    # Display results - Sortino
    print()
    print("="*100)
    print("JITTER TEST RESULTS: SORTINO RATIO (downside risk only)")
    print("="*100)
    print()
    print(f"{'Jitter':<10} {'CTC Sortino':>12} {'B&H Sortino':>12} {'Sortino Diff':>14} {'Win%':>8}")
    print("-"*60)

    for jitter_name, _ in JITTER_LEVELS:
        if jitter_name in jitter_results:
            r = jitter_results[jitter_name]
            print(f"{jitter_name:<10} {r['avg_ctc_sortino']:>12.2f} {r['avg_bh_sortino']:>12.2f} {r['avg_sortino_diff']:>+13.2f} {r['sortino_win_pct']:>7.0f}%")

    # Display results - Calmar
    print()
    print("="*100)
    print("JITTER TEST RESULTS: CALMAR RATIO (CAGR / Max Drawdown)")
    print("="*100)
    print()
    print(f"{'Jitter':<10} {'CTC Calmar':>12} {'B&H Calmar':>12} {'Calmar Diff':>14} {'Win%':>8}")
    print("-"*60)

    for jitter_name, _ in JITTER_LEVELS:
        if jitter_name in jitter_results:
            r = jitter_results[jitter_name]
            print(f"{jitter_name:<10} {r['avg_ctc_calmar']:>12.2f} {r['avg_bh_calmar']:>12.2f} {r['avg_calmar_diff']:>+13.2f} {r['calmar_win_pct']:>7.0f}%")

    # Display results - Drawdown
    print()
    print("="*100)
    print("JITTER TEST RESULTS: MAX DRAWDOWN")
    print("="*100)
    print()
    print(f"{'Jitter':<10} {'CTC DD':>12} {'B&H DD':>12} {'DD Diff':>14}")
    print("-"*55)

    for jitter_name, _ in JITTER_LEVELS:
        if jitter_name in jitter_results:
            r = jitter_results[jitter_name]
            print(f"{jitter_name:<10} {r['avg_ctc_dd']:>11.1f}% {r['avg_bh_dd']:>11.1f}% {r['avg_dd_diff']:>+13.1f}%")

    # Analysis
    print()
    print("="*100)
    print("MULTI-METRIC ROBUSTNESS ANALYSIS")
    print("="*100)
    print()

    # Helper to get 30% range values (use 0.31 to avoid floating point issues)
    def get_30pct_values(metric_key):
        return [jitter_results[n][metric_key] for n, m in JITTER_LEVELS
                if n in jitter_results and (n == "base" or abs(m - 1.0) <= 0.31)]

    # Check each metric for robustness
    metrics_to_check = [
        ("ROI Diff", "avg_roi_diff", True),       # True = positive is good
        ("Sharpe Diff", "avg_sharpe_diff", True),
        ("Sortino Diff", "avg_sortino_diff", True),
        ("Calmar Diff", "avg_calmar_diff", True),
        ("DD Diff", "avg_dd_diff", False),         # False = negative is good (less DD)
    ]

    print("Checking if CTC beats B&H across all +/-30% threshold variations:")
    print()
    print(f"{'Metric':<15} {'Min':>10} {'Max':>10} {'All >0?':>10} {'Status':>10}")
    print("-"*60)

    all_pass = True
    for metric_name, metric_key, positive_is_good in metrics_to_check:
        values_30 = get_30pct_values(metric_key)
        if values_30:
            min_val = min(values_30)
            max_val = max(values_30)
            # For DD, we want all negative (CTC has less drawdown)
            if positive_is_good:
                all_good = all(v > 0 for v in values_30)
            else:
                all_good = all(v < 0 for v in values_30)
            status = "PASS" if all_good else "FAIL"
            if not all_good:
                all_pass = False
            print(f"{metric_name:<15} {min_val:>+9.2f} {max_val:>+9.2f} {'Yes' if all_good else 'No':>10} {status:>10}")

    print()

    # Summary table comparing base to jittered
    print("="*100)
    print("SUMMARY: Base vs Jittered Performance")
    print("="*100)
    print()
    print(f"{'Jitter':<10} {'ROI':>10} {'Sharpe':>10} {'Sortino':>10} {'Calmar':>10} {'DD':>10}")
    print("-"*65)

    for jitter_name, _ in JITTER_LEVELS:
        if jitter_name in jitter_results:
            r = jitter_results[jitter_name]
            print(f"{jitter_name:<10} {r['avg_roi_diff']:>+9.1f}% {r['avg_sharpe_diff']:>+9.2f} {r['avg_sortino_diff']:>+9.2f} {r['avg_calmar_diff']:>+9.2f} {r['avg_dd_diff']:>+9.1f}%")

    # Final verdict
    print()
    print("="*100)
    print("FINAL VERDICT")
    print("="*100)
    print()

    if all_pass:
        print("ROBUST: All metrics (ROI, Sharpe, Sortino, Calmar, DD) beat B&H")
        print("        within +/-30% parameter range. Strategy is production-ready.")
    else:
        print("MIXED: Some metrics don't consistently beat B&H across jitter range.")
        print("       Review which metrics fail and whether that's acceptable.")

    # Sensitivity analysis
    print()
    print("="*100)
    print("SENSITIVITY ANALYSIS")
    print("="*100)
    print()

    # Compare looser vs tighter across all metrics
    looser_roi = [jitter_results[n]["avg_roi_diff"] for n, m in JITTER_LEVELS if m < 1 and n in jitter_results]
    tighter_roi = [jitter_results[n]["avg_roi_diff"] for n, m in JITTER_LEVELS if m > 1 and n in jitter_results]

    if looser_roi and tighter_roi:
        avg_looser = statistics.mean(looser_roi)
        avg_tighter = statistics.mean(tighter_roi)

        print(f"Looser thresholds (more signals):  {avg_looser:+.1f}% avg ROI diff")
        print(f"Tighter thresholds (fewer signals): {avg_tighter:+.1f}% avg ROI diff")
        print()

        if avg_looser > avg_tighter:
            print("Direction: Looser thresholds perform better")
            print("           Consider making base thresholds slightly more sensitive")
        else:
            print("Direction: Tighter thresholds perform better")
            print("           Current conservative approach is validated")

    # Optimal threshold suggestion
    print()
    best_jitter = max(jitter_results.items(), key=lambda x: x[1]["avg_roi_diff"])
    print(f"Best performing jitter: {best_jitter[0]}")
    print(f"  Thresholds: acc < {best_jitter[1]['acc']:.2f}, jerk < {best_jitter[1]['jerk']:.2f}")
    print(f"  ROI Diff: {best_jitter[1]['avg_roi_diff']:+.1f}%")


if __name__ == "__main__":
    run_jitter_test()
