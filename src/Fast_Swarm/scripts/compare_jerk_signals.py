"""
Quick comparison: Price Jerk vs ADX Jerk

We validated price jerk on crypto but the service uses ADX jerk.
Let's see which actually works better on equities.
"""

import sys
from pathlib import Path
from datetime import datetime
import statistics

import polars as pl

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

DATA_DIR = PROJECT_ROOT / "data" / "test_data" / "SP50_DOW30"
CAPITAL = 1000

# Categories for grouping
CATEGORIES = {
    "AAPL": "Tech", "MSFT": "Tech", "NVDA": "Tech", "GOOGL": "Tech", "META": "Tech",
    "AMZN": "Tech", "TSLA": "Tech", "NFLX": "Tech", "AMD": "Tech", "INTC": "Tech",
    "ORCL": "Tech", "CRM": "Tech", "ADBE": "Tech", "NOW": "Tech", "QCOM": "Tech",
    "TXN": "Tech", "AVGO": "Tech", "CSCO": "Tech", "IBM": "Tech", "INTU": "Tech",
    "JPM": "Financial", "BAC": "Financial", "WFC": "Financial", "GS": "Financial",
    "V": "Financial", "MA": "Financial", "AXP": "Financial",
    "UNH": "Healthcare", "JNJ": "Healthcare", "LLY": "Healthcare", "ABBV": "Healthcare",
    "MRK": "Healthcare", "TMO": "Healthcare", "ABT": "Healthcare", "DHR": "Healthcare",
    "AMGN": "Healthcare", "ISRG": "Healthcare",
    "WMT": "Consumer", "COST": "Consumer", "HD": "Consumer", "PG": "Consumer",
    "KO": "Consumer", "PEP": "Consumer", "MCD": "Consumer", "NKE": "Consumer",
    "DIS": "Consumer", "CMCSA": "Consumer", "PM": "Consumer",
    "XOM": "Energy", "CVX": "Energy",
    "CAT": "Industrial", "GE": "Industrial", "HON": "Industrial", "BA": "Industrial",
    "MMM": "Industrial", "LIN": "Industrial", "ACN": "Industrial",
    "SPY": "ETF", "QQQ": "ETF", "DIA": "ETF", "IWM": "ETF",
}

# Signal configs to test
CONFIGS = {
    "vel+acc+ADX_jerk": {
        "vel_col": "close_velocity_zscore",
        "acc_col": "close_acceleration_zscore",
        "jerk_col": "ADX_14_jerk_zscore",
        "vel_thresh": 1.0,
        "acc_thresh": -2.0,
        "jerk_thresh": -0.5,
    },
    "vel+acc+price_jerk": {
        "vel_col": "close_velocity_zscore",
        "acc_col": "close_acceleration_zscore",
        "jerk_col": "close_jerk_zscore",
        "vel_thresh": 1.0,
        "acc_thresh": -2.0,
        "jerk_thresh": -0.5,
    },
    "acc+price_jerk (AJ)": {
        "vel_col": None,  # No velocity
        "acc_col": "close_acceleration_zscore",
        "jerk_col": "close_jerk_zscore",
        "vel_thresh": None,
        "acc_thresh": -1.5,
        "jerk_thresh": -0.5,
    },
    "acc+ADX_jerk": {
        "vel_col": None,
        "acc_col": "close_acceleration_zscore",
        "jerk_col": "ADX_14_jerk_zscore",
        "vel_thresh": None,
        "acc_thresh": -1.5,
        "jerk_thresh": -0.5,
    },
}


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


def check_defensive(row: dict, config: dict) -> bool:
    """Check if defensive signal fires."""
    signals = 0
    required = 0

    # Velocity check (if configured)
    if config["vel_col"]:
        required += 1
        val = row.get(config["vel_col"])
        if val is not None and val > config["vel_thresh"]:
            signals += 1

    # Acceleration check
    if config["acc_col"]:
        required += 1
        val = row.get(config["acc_col"])
        if val is not None and val < config["acc_thresh"]:
            signals += 1

    # Jerk check
    if config["jerk_col"]:
        required += 1
        val = row.get(config["jerk_col"])
        if val is not None and val < config["jerk_thresh"]:
            signals += 1

    return signals == required


def backtest_stock(symbol: str, rows: list, config: dict) -> dict:
    """Run CTC v2 with specific config."""
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

        is_def = check_defensive(row, config)
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

    bh_roi = (bh_equity[-1] / CAPITAL - 1) * 100
    ctc_roi = (ctc_equity[-1] / CAPITAL - 1) * 100

    return {
        "bh_roi": bh_roi,
        "ctc_roi": ctc_roi,
        "roi_diff": ctc_roi - bh_roi,
        "bh_dd": compute_max_drawdown(bh_equity),
        "ctc_dd": compute_max_drawdown(ctc_equity),
        "def_pct": def_days / (len(rows) - warmup) * 100,
    }


def run_comparison():
    print("="*100)
    print("JERK SIGNAL COMPARISON: Price Jerk vs ADX Jerk")
    print("="*100)
    print()

    data = load_all_symbols()
    symbols = list(data.keys())
    print(f"Testing on {len(symbols)} stocks")
    print()

    # Test each config
    config_results = {name: [] for name in CONFIGS}

    for sym in symbols:
        for config_name, config in CONFIGS.items():
            r = backtest_stock(sym, data[sym]["rows"], config)
            if r:
                r["symbol"] = sym
                r["category"] = CATEGORIES.get(sym, "Other")
                config_results[config_name].append(r)

    # Summary per config
    print("="*100)
    print("OVERALL RESULTS")
    print("="*100)
    print()
    print(f"{'Config':<25} {'Avg ROI Diff':>14} {'Win%':>10} {'Avg DD Diff':>14} {'Avg Def%':>12}")
    print("-"*80)

    for config_name, results in config_results.items():
        if not results:
            continue
        avg_roi = statistics.mean([r["roi_diff"] for r in results])
        win_pct = sum(1 for r in results if r["roi_diff"] > 0) / len(results) * 100
        avg_dd = statistics.mean([r["ctc_dd"] - r["bh_dd"] for r in results])
        avg_def = statistics.mean([r["def_pct"] for r in results])
        print(f"{config_name:<25} {avg_roi:>+13.1f}% {win_pct:>9.0f}% {avg_dd:>+13.1f}% {avg_def:>11.1f}%")

    # Per-stock comparison: price jerk vs ADX jerk
    print()
    print("="*100)
    print("PER-STOCK: Price Jerk vs ADX Jerk (using vel+acc+jerk config)")
    print("="*100)
    print()

    adx_results = {r["symbol"]: r for r in config_results["vel+acc+ADX_jerk"]}
    price_results = {r["symbol"]: r for r in config_results["vel+acc+price_jerk"]}

    comparisons = []
    for sym in symbols:
        if sym in adx_results and sym in price_results:
            adx_r = adx_results[sym]
            price_r = price_results[sym]
            comparisons.append({
                "symbol": sym,
                "category": CATEGORIES.get(sym, "Other"),
                "adx_roi_diff": adx_r["roi_diff"],
                "price_roi_diff": price_r["roi_diff"],
                "winner": "price" if price_r["roi_diff"] > adx_r["roi_diff"] else "adx",
                "diff": price_r["roi_diff"] - adx_r["roi_diff"],
            })

    # Sort by difference
    comparisons.sort(key=lambda x: -x["diff"])

    print(f"{'Symbol':<8} {'Category':<12} {'ADX Jerk':>12} {'Price Jerk':>12} {'Winner':>10} {'Diff':>10}")
    print("-"*70)
    for c in comparisons:
        print(f"{c['symbol']:<8} {c['category']:<12} {c['adx_roi_diff']:>+11.1f}% {c['price_roi_diff']:>+11.1f}% {c['winner']:>10} {c['diff']:>+9.1f}%")

    # Summary
    price_wins = sum(1 for c in comparisons if c["winner"] == "price")
    adx_wins = len(comparisons) - price_wins

    print()
    print("="*100)
    print("VERDICT")
    print("="*100)
    print()
    print(f"  Price Jerk wins: {price_wins}/{len(comparisons)} stocks")
    print(f"  ADX Jerk wins:   {adx_wins}/{len(comparisons)} stocks")
    print()

    # By sector
    print("By Sector:")
    sectors = {}
    for c in comparisons:
        cat = c["category"]
        if cat not in sectors:
            sectors[cat] = {"price": 0, "adx": 0}
        sectors[cat][c["winner"]] += 1

    for sector in sorted(sectors.keys()):
        s = sectors[sector]
        total = s["price"] + s["adx"]
        winner = "PRICE" if s["price"] > s["adx"] else "ADX" if s["adx"] > s["price"] else "TIE"
        print(f"  {sector:<15}: Price {s['price']}/{total}, ADX {s['adx']}/{total} -> {winner}")

    # AJ comparison
    print()
    print("="*100)
    print("AJ CONFIG: acc+price_jerk vs acc+ADX_jerk")
    print("="*100)

    aj_price = config_results["acc+price_jerk (AJ)"]
    aj_adx = config_results["acc+ADX_jerk"]

    aj_price_avg = statistics.mean([r["roi_diff"] for r in aj_price])
    aj_adx_avg = statistics.mean([r["roi_diff"] for r in aj_adx])

    print()
    print(f"  acc+price_jerk: {aj_price_avg:+.1f}% avg ROI diff")
    print(f"  acc+ADX_jerk:   {aj_adx_avg:+.1f}% avg ROI diff")
    print()
    print(f"  WINNER: {'PRICE JERK' if aj_price_avg > aj_adx_avg else 'ADX JERK'} by {abs(aj_price_avg - aj_adx_avg):.1f}%")


if __name__ == "__main__":
    run_comparison()
