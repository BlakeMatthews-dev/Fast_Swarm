"""
Compare Price Jerk vs ADX Jerk on CRYPTO (BTC, ETH, SOL)

Same test as equities - which jerk signal works better?
"""

import sys
from pathlib import Path
from datetime import datetime
import statistics

import polars as pl

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

CRYPTO_DIR = PROJECT_ROOT / "data" / "derivatives"
CAPITAL = 1000

# Signal configs - crypto uses lowercase column names
CONFIGS = {
    "vel+acc+ADX_jerk": {
        "vel_col": "close_velocity_zscore",
        "acc_col": "close_acceleration_zscore",
        "jerk_col": "adx_14_jerk_zscore",  # lowercase in crypto
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
        "vel_col": None,
        "acc_col": "close_acceleration_zscore",
        "jerk_col": "close_jerk_zscore",
        "vel_thresh": None,
        "acc_thresh": -1.5,
        "jerk_thresh": -0.5,
    },
    "acc+ADX_jerk": {
        "vel_col": None,
        "acc_col": "close_acceleration_zscore",
        "jerk_col": "adx_14_jerk_zscore",  # lowercase in crypto
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


def load_crypto_data(symbol: str, timeframe: str = "1h") -> list:
    """Load crypto data from derivatives folder."""
    path = CRYPTO_DIR / f"symbol={symbol}" / f"timeframe={timeframe}" / "data.parquet"
    if not path.exists():
        return None
    df = pl.read_parquet(path).sort("time")  # crypto uses "time" not "timestamp"
    return df.to_dicts()


def check_defensive(row: dict, config: dict) -> bool:
    """Check if defensive signal fires."""
    signals = 0
    required = 0

    if config["vel_col"]:
        required += 1
        val = row.get(config["vel_col"])
        if val is not None and val > config["vel_thresh"]:
            signals += 1

    if config["acc_col"]:
        required += 1
        val = row.get(config["acc_col"])
        if val is not None and val < config["acc_thresh"]:
            signals += 1

    if config["jerk_col"]:
        required += 1
        val = row.get(config["jerk_col"])
        if val is not None and val < config["jerk_thresh"]:
            signals += 1

    return signals == required


def backtest_crypto(symbol: str, rows: list, config: dict) -> dict:
    """Run CTC v2 on crypto."""
    prices = [r.get("close", 0) for r in rows]
    if not prices or prices[0] <= 0:
        return None

    bh_shares = CAPITAL / prices[0]
    bh_equity = [CAPITAL]

    ctc_shares = CAPITAL / prices[0]
    ctc_cash = 0.0
    in_defensive = False
    ctc_equity = [CAPITAL]
    def_count = 0

    warmup = 100  # More warmup for 1h data
    for i in range(warmup, len(rows)):
        price = prices[i]
        row = rows[i]

        bh_equity.append(bh_shares * price)

        is_def = check_defensive(row, config)
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

    bh_roi = (bh_equity[-1] / CAPITAL - 1) * 100
    ctc_roi = (ctc_equity[-1] / CAPITAL - 1) * 100

    return {
        "bh_roi": bh_roi,
        "ctc_roi": ctc_roi,
        "roi_diff": ctc_roi - bh_roi,
        "bh_dd": compute_max_drawdown(bh_equity),
        "ctc_dd": compute_max_drawdown(ctc_equity),
        "def_pct": def_count / (len(rows) - warmup) * 100,
        "def_count": def_count,
    }


def run_comparison():
    print("="*100)
    print("JERK SIGNAL COMPARISON ON CRYPTO: Price Jerk vs ADX Jerk")
    print("="*100)
    print()

    symbols = ["BTC", "ETH", "SOL"]

    # Check what columns we have
    sample = load_crypto_data("BTC", "1h")
    if sample:
        jerk_cols = [c for c in sample[0].keys() if "jerk" in c.lower()]
        print(f"Available jerk columns: {len(jerk_cols)}")
        print(f"  close_jerk_zscore: {'close_jerk_zscore' in sample[0]}")
        print(f"  ADX_14_jerk_zscore: {'ADX_14_jerk_zscore' in sample[0]}")
        print(f"  Sample rows: {len(sample)}")
        print()

    # Test each config on each crypto
    results = []

    for sym in symbols:
        rows = load_crypto_data(sym, "1h")
        if not rows:
            print(f"  {sym}: No data")
            continue

        print(f"{sym} ({len(rows)} rows):")

        for config_name, config in CONFIGS.items():
            r = backtest_crypto(sym, rows, config)
            if r:
                r["symbol"] = sym
                r["config"] = config_name
                results.append(r)
                print(f"  {config_name:<25}: ROI diff {r['roi_diff']:>+8.1f}%, Def signals: {r['def_count']:>4} ({r['def_pct']:.1f}%)")

        print()

    # Summary
    print("="*100)
    print("SUMMARY BY CONFIG")
    print("="*100)
    print()

    configs_summary = {}
    for r in results:
        cfg = r["config"]
        if cfg not in configs_summary:
            configs_summary[cfg] = []
        configs_summary[cfg].append(r["roi_diff"])

    print(f"{'Config':<25} {'Avg ROI Diff':>14} {'BTC':>10} {'ETH':>10} {'SOL':>10}")
    print("-"*75)

    for cfg in CONFIGS.keys():
        if cfg in configs_summary:
            avg = statistics.mean(configs_summary[cfg])
            btc = next((r["roi_diff"] for r in results if r["symbol"]=="BTC" and r["config"]==cfg), 0)
            eth = next((r["roi_diff"] for r in results if r["symbol"]=="ETH" and r["config"]==cfg), 0)
            sol = next((r["roi_diff"] for r in results if r["symbol"]=="SOL" and r["config"]==cfg), 0)
            print(f"{cfg:<25} {avg:>+13.1f}% {btc:>+9.1f}% {eth:>+9.1f}% {sol:>+9.1f}%")

    # Head to head
    print()
    print("="*100)
    print("HEAD TO HEAD: Price Jerk vs ADX Jerk")
    print("="*100)
    print()

    for sym in symbols:
        adx = next((r for r in results if r["symbol"]==sym and r["config"]=="vel+acc+ADX_jerk"), None)
        price = next((r for r in results if r["symbol"]==sym and r["config"]=="vel+acc+price_jerk"), None)

        if adx and price:
            winner = "PRICE" if price["roi_diff"] > adx["roi_diff"] else "ADX"
            diff = abs(price["roi_diff"] - adx["roi_diff"])
            print(f"  {sym}: ADX {adx['roi_diff']:>+6.1f}% vs Price {price['roi_diff']:>+6.1f}%  ->  {winner} wins by {diff:.1f}%")


if __name__ == "__main__":
    run_comparison()
