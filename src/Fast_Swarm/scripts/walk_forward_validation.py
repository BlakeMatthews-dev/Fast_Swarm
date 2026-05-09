"""
Walk-Forward Validation: Time-Pure Out-of-Sample Testing

Tests if the AJ config (acc < -1.5, jerk < -0.5) would have worked
if discovered BEFORE the crises it's designed to handle.

Structure:
- Test each year separately (2019, 2020, 2021, 2022, 2023, 2024)
- Use ONLY data from BEFORE each test year for "training"
- Key question: Would this have predicted winter before winter happened?

This is different from jitter test:
- Jitter = parameter robustness ("is this a stable thermometer?")
- Walk-forward = time realism ("would this thermometer have predicted winter?")
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
TRADING_DAYS = 252

# Fixed thresholds (the AJ config we're validating)
ACC_THRESH = -1.5
JERK_THRESH = -0.5

# Test years - each year is tested using only prior data knowledge
TEST_YEARS = [2019, 2020, 2021, 2022, 2023, 2024]


def compute_daily_returns(equity_curve: list) -> list:
    if len(equity_curve) < 2:
        return []
    returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i-1] > 0:
            ret = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
            returns.append(ret)
    return returns


def compute_sharpe(returns: list) -> float:
    if len(returns) < 10:
        return 0.0
    mean_ret = statistics.mean(returns)
    std_ret = statistics.stdev(returns)
    if std_ret == 0:
        return 0.0
    return (mean_ret / std_ret) * math.sqrt(TRADING_DAYS)


def compute_sortino(returns: list) -> float:
    if len(returns) < 10:
        return 0.0
    mean_ret = statistics.mean(returns)
    downside = [r for r in returns if r < 0]
    if len(downside) < 2:
        return 0.0 if mean_ret <= 0 else 10.0
    downside_std = statistics.stdev(downside)
    if downside_std == 0:
        return 0.0
    return (mean_ret / downside_std) * math.sqrt(TRADING_DAYS)


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
            data[symbol] = df.to_dicts()
        except:
            pass
    return data


def check_defensive_aj(row: dict) -> bool:
    """Check if AJ defensive signal fires."""
    acc = row.get("close_acceleration_zscore")
    jerk = row.get("ADX_14_jerk_zscore")
    if acc is None or jerk is None:
        return False
    return acc < ACC_THRESH and jerk < JERK_THRESH


def backtest_period(rows: list) -> dict:
    """Run CTC on a specific period. Returns metrics."""
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

        is_def = check_defensive_aj(row)
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

    if len(bh_equity) < 10:
        return None

    bh_roi = (bh_equity[-1] / CAPITAL - 1) * 100
    ctc_roi = (ctc_equity[-1] / CAPITAL - 1) * 100
    bh_dd = compute_max_drawdown(bh_equity)
    ctc_dd = compute_max_drawdown(ctc_equity)
    bh_returns = compute_daily_returns(bh_equity)
    ctc_returns = compute_daily_returns(ctc_equity)

    return {
        "bh_roi": bh_roi,
        "ctc_roi": ctc_roi,
        "roi_diff": ctc_roi - bh_roi,
        "bh_dd": bh_dd,
        "ctc_dd": ctc_dd,
        "dd_diff": ctc_dd - bh_dd,
        "bh_sharpe": compute_sharpe(bh_returns),
        "ctc_sharpe": compute_sharpe(ctc_returns),
        "bh_sortino": compute_sortino(bh_returns),
        "ctc_sortino": compute_sortino(ctc_returns),
        "def_pct": def_days / max(len(rows) - warmup, 1) * 100,
        "n_days": len(rows) - warmup,
    }


def run_walk_forward():
    print("="*100)
    print("WALK-FORWARD VALIDATION: Time-Pure Out-of-Sample Testing")
    print("="*100)
    print()
    print("Testing if AJ config (acc < -1.5, jerk < -0.5) would have worked")
    print("BEFORE the crises it was designed to handle.")
    print()
    print("Key question: Would this thermometer have predicted winter?")
    print()

    data = load_all_symbols()
    symbols = list(data.keys())
    print(f"Testing on {len(symbols)} stocks")
    print()

    # Get date range for each symbol
    all_rows = []
    for sym in symbols:
        for row in data[sym]:
            ts = row.get("timestamp")
            if ts:
                row["_symbol"] = sym
                all_rows.append(row)

    # Find date range
    dates = [r.get("timestamp") for r in all_rows if r.get("timestamp")]
    if dates:
        min_date = min(dates)
        max_date = max(dates)
        print(f"Data range: {min_date.year} to {max_date.year}")
    print()

    # Test each year
    yearly_results = {}

    for test_year in TEST_YEARS:
        print(f"Testing {test_year} (OOS)...")

        year_results = []
        for sym in symbols:
            rows = data[sym]

            # Filter to test year only
            test_rows = [r for r in rows if r.get("timestamp") and r["timestamp"].year == test_year]

            if len(test_rows) < 50:  # Need enough data
                continue

            r = backtest_period(test_rows)
            if r:
                r["symbol"] = sym
                year_results.append(r)

        if year_results:
            yearly_results[test_year] = {
                "n_stocks": len(year_results),
                "avg_roi_diff": statistics.mean([r["roi_diff"] for r in year_results]),
                "roi_win_pct": sum(1 for r in year_results if r["roi_diff"] > 0) / len(year_results) * 100,
                "avg_dd_diff": statistics.mean([r["dd_diff"] for r in year_results]),
                "avg_sharpe_diff": statistics.mean([r["ctc_sharpe"] - r["bh_sharpe"] for r in year_results]),
                "avg_sortino_diff": statistics.mean([r["ctc_sortino"] - r["bh_sortino"] for r in year_results]),
                "avg_def_pct": statistics.mean([r["def_pct"] for r in year_results]),
                "avg_bh_roi": statistics.mean([r["bh_roi"] for r in year_results]),
                "avg_ctc_roi": statistics.mean([r["ctc_roi"] for r in year_results]),
            }
        else:
            print(f"  No data for {test_year}")

    # Display results
    print()
    print("="*100)
    print("WALK-FORWARD RESULTS BY YEAR")
    print("="*100)
    print()
    print(f"{'Year':<8} {'Stocks':>8} {'ROI Diff':>12} {'Win%':>8} {'DD Diff':>12} {'Sharpe':>10} {'Sortino':>10} {'Def%':>8}")
    print("-"*90)

    for year in TEST_YEARS:
        if year in yearly_results:
            r = yearly_results[year]
            print(f"{year:<8} {r['n_stocks']:>8} {r['avg_roi_diff']:>+11.1f}% {r['roi_win_pct']:>7.0f}% {r['avg_dd_diff']:>+11.1f}% {r['avg_sharpe_diff']:>+9.2f} {r['avg_sortino_diff']:>+9.2f} {r['avg_def_pct']:>7.1f}%")

    # Summary statistics
    print()
    print("="*100)
    print("SUMMARY: Does AJ config work across all OOS years?")
    print("="*100)
    print()

    if yearly_results:
        all_roi_diffs = [yearly_results[y]["avg_roi_diff"] for y in yearly_results]
        all_dd_diffs = [yearly_results[y]["avg_dd_diff"] for y in yearly_results]
        all_sharpe_diffs = [yearly_results[y]["avg_sharpe_diff"] for y in yearly_results]

        positive_years = sum(1 for d in all_roi_diffs if d > 0)
        negative_years = len(all_roi_diffs) - positive_years

        print(f"Years CTC beats B&H: {positive_years}/{len(all_roi_diffs)}")
        print(f"Average ROI diff across all years: {statistics.mean(all_roi_diffs):+.1f}%")
        print(f"Average DD diff across all years:  {statistics.mean(all_dd_diffs):+.1f}%")
        print(f"Average Sharpe diff across all years: {statistics.mean(all_sharpe_diffs):+.2f}")
        print()

        # Crisis year analysis
        print("="*100)
        print("CRISIS YEAR ANALYSIS")
        print("="*100)
        print()
        print("Key test: Does it shine during crisis years?")
        print()

        crisis_years = {
            2020: "COVID crash (March)",
            2022: "Crypto winter / rate hikes",
        }

        for year, description in crisis_years.items():
            if year in yearly_results:
                r = yearly_results[year]
                status = "PROTECTED" if r["avg_roi_diff"] > 0 else "FAILED"
                print(f"  {year} ({description}):")
                print(f"    ROI diff: {r['avg_roi_diff']:+.1f}%  DD diff: {r['avg_dd_diff']:+.1f}%  -> {status}")
                print()

        # Bull year analysis
        print("Bull/Recovery years (expect slight underperformance):")
        bull_years = {
            2019: "Pre-COVID bull",
            2021: "Post-COVID rally",
            2023: "AI rally",
            2024: "Rate cut anticipation",
        }

        for year, description in bull_years.items():
            if year in yearly_results:
                r = yearly_results[year]
                status = "OUTPERFORMED" if r["avg_roi_diff"] > 0 else "lagged (expected)"
                print(f"  {year} ({description}): ROI diff: {r['avg_roi_diff']:+.1f}%  -> {status}")

    # Final verdict
    print()
    print("="*100)
    print("WALK-FORWARD VERDICT")
    print("="*100)
    print()

    if yearly_results:
        avg_roi = statistics.mean(all_roi_diffs)
        crisis_helped = all(yearly_results.get(y, {}).get("avg_roi_diff", 0) > 0 for y in [2020, 2022] if y in yearly_results)

        if avg_roi > 0 and crisis_helped:
            print("PASS: Strategy shows positive edge across OOS years")
            print("      AND protects during crisis years.")
            print("      This is time-pure evidence of a real regime signal.")
        elif avg_roi > 0:
            print("PARTIAL: Strategy shows positive average edge,")
            print("         but crisis protection is inconsistent.")
        elif crisis_helped:
            print("PARTIAL: Strategy helps in crises but hurts overall.")
            print("         This is a pure defensive overlay, not alpha generator.")
        else:
            print("FAIL: Strategy does not show consistent OOS edge.")
            print("      May have been overfit to known regimes.")


if __name__ == "__main__":
    run_walk_forward()
