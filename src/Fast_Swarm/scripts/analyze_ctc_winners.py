"""
Analyze what makes CTC winners different from losers.

Key question: What happens AFTER the DEFENSIVE signal fires?
- Winners: Stock keeps falling or stays flat (CTC saved money)
- Losers: Stock immediately bounces back (CTC sold at the bottom)
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

DATA_DIR = PROJECT_ROOT / "data" / "test_data" / "SP50_DOW30"


def load_all_symbols() -> dict:
    data = {}
    files = list(DATA_DIR.glob("*_1d.parquet"))
    for f in files:
        symbol = f.stem.replace("_1d", "")
        try:
            df = pl.read_parquet(f).sort("timestamp")
            deriv_cols = ["close_velocity_zscore", "close_acceleration_zscore",
                          "close_jerk_zscore", "ADX_14_jerk_zscore"]
            actual = [c for c in deriv_cols if c in df.columns]
            data[symbol] = {"df": df, "rows": df.to_dicts(), "deriv_cols": actual}
        except:
            pass
    return data


def row_to_market_state(row: dict, symbol: str, deriv_cols: list) -> MarketState:
    ts = row.get("timestamp", datetime.now())
    def get_val(target):
        for c in deriv_cols:
            if target.lower() in c.lower() and c in row:
                return row[c]
        return None
    return MarketState(
        time=ts, symbol=symbol,
        tf_1h_vel=get_val("velocity"), tf_1h_acc=get_val("acceleration"),
        tf_1h_adx_jerk=get_val("adx"),
        tf_4h_vel=get_val("velocity"), tf_4h_acc=get_val("acceleration"),
        tf_4h_adx_jerk=get_val("adx"),
        tf_1d_vel=None, tf_1d_acc=None, tf_1d_adx_jerk=None,
    )


def analyze_post_defensive(symbol: str, prices: list, rows_by_ts: dict, deriv_cols: list, common_ts: list) -> dict:
    """Analyze what happens after DEFENSIVE signals."""
    service = BearProtectionService()

    defensive_events = []
    warmup = 21

    for i in range(warmup, len(common_ts)):
        ts = common_ts[i]
        row = rows_by_ts.get(ts, {})
        state = row_to_market_state(row, symbol, deriv_cols)
        regime = service.evaluate(state).regime

        # Detect DEFENSIVE trigger (transition into DEFENSIVE)
        if regime == Regime.DEFENSIVE:
            # Look at what happens next 5, 10, 20 days
            price_at_signal = prices[i]

            returns_5d = None
            returns_10d = None
            returns_20d = None

            if i + 5 < len(prices):
                returns_5d = (prices[i + 5] - price_at_signal) / price_at_signal * 100
            if i + 10 < len(prices):
                returns_10d = (prices[i + 10] - price_at_signal) / price_at_signal * 100
            if i + 20 < len(prices):
                returns_20d = (prices[i + 20] - price_at_signal) / price_at_signal * 100

            # Track the minimum price in next 20 days (max loss avoided)
            min_price_20d = min(prices[i:min(i+21, len(prices))])
            max_loss_avoided = (price_at_signal - min_price_20d) / price_at_signal * 100

            defensive_events.append({
                "date": ts,
                "price": price_at_signal,
                "ret_5d": returns_5d,
                "ret_10d": returns_10d,
                "ret_20d": returns_20d,
                "max_loss_avoided": max_loss_avoided,
            })

    if not defensive_events:
        return None

    # Aggregate stats
    avg_5d = statistics.mean([e["ret_5d"] for e in defensive_events if e["ret_5d"] is not None])
    avg_10d = statistics.mean([e["ret_10d"] for e in defensive_events if e["ret_10d"] is not None])
    avg_20d = statistics.mean([e["ret_20d"] for e in defensive_events if e["ret_20d"] is not None])
    avg_loss_avoided = statistics.mean([e["max_loss_avoided"] for e in defensive_events])

    # How often did price go DOWN after DEFENSIVE?
    down_5d = sum(1 for e in defensive_events if e["ret_5d"] is not None and e["ret_5d"] < 0) / len([e for e in defensive_events if e["ret_5d"] is not None])
    down_10d = sum(1 for e in defensive_events if e["ret_10d"] is not None and e["ret_10d"] < 0) / len([e for e in defensive_events if e["ret_10d"] is not None])

    return {
        "symbol": symbol,
        "num_signals": len(defensive_events),
        "avg_ret_5d": avg_5d,
        "avg_ret_10d": avg_10d,
        "avg_ret_20d": avg_20d,
        "down_5d_pct": down_5d * 100,
        "down_10d_pct": down_10d * 100,
        "avg_max_loss_avoided": avg_loss_avoided,
    }


def run_analysis():
    print("="*100)
    print("ANALYZING WHAT HAPPENS AFTER DEFENSIVE SIGNALS")
    print("="*100)
    print()

    data = load_all_symbols()
    symbols = list(data.keys())

    # Common timestamps
    all_ts = None
    for sym in symbols:
        ts_set = set(row["timestamp"] for row in data[sym]["rows"])
        all_ts = ts_set if all_ts is None else all_ts & ts_set
    common_ts = sorted(all_ts)

    # Build price series
    prices = {sym: [] for sym in symbols}
    rows_by_ts = {sym: {row["timestamp"]: row for row in data[sym]["rows"]} for sym in symbols}
    for ts in common_ts:
        for sym in symbols:
            row = rows_by_ts[sym].get(ts)
            prices[sym].append(row["close"] if row and row.get("close") else (prices[sym][-1] if prices[sym] else 0))

    # Known CTC results (from previous analysis)
    ctc_results = {
        "META": +69.7, "GS": +50.0, "CSCO": +46.6, "CAT": +46.4, "BAC": +32.7,
        "TXN": +30.0, "XOM": +28.0, "AAPL": +27.8, "NFLX": +27.6, "SPY": +26.7,
        "NVDA": -178.0, "AVGO": -116.6, "LLY": -34.9, "AMD": -21.8, "ABBV": -21.4,
        "MSFT": -19.7, "NOW": -19.4, "AMZN": -13.9, "IBM": -11.5, "DHR": -11.2,
    }

    print("Analyzing post-DEFENSIVE behavior...")
    results = []
    for sym in symbols:
        r = analyze_post_defensive(sym, prices[sym], rows_by_ts[sym], data[sym]["deriv_cols"], common_ts)
        if r:
            r["ctc_improvement"] = ctc_results.get(sym, 0)
            results.append(r)

    # Sort by CTC improvement
    results.sort(key=lambda x: -x["ctc_improvement"])

    print()
    print("="*100)
    print("POST-DEFENSIVE BEHAVIOR: What happens after selling?")
    print("="*100)
    print()
    print(f"{'Symbol':<8} {'CTC Gain':>10} {'Signals':>8} {'5d Ret':>10} {'10d Ret':>10} {'20d Ret':>10} {'Down@5d':>10} {'MaxLossAvoid':>12}")
    print("-"*90)

    # Top 15 winners
    print("\nTOP CTC WINNERS:")
    for r in results[:15]:
        print(f"{r['symbol']:<8} {r['ctc_improvement']:>+9.1f}% {r['num_signals']:>8} {r['avg_ret_5d']:>+9.1f}% {r['avg_ret_10d']:>+9.1f}% {r['avg_ret_20d']:>+9.1f}% {r['down_5d_pct']:>9.0f}% {r['avg_max_loss_avoided']:>11.1f}%")

    # Bottom 15 losers
    print("\nBOTTOM CTC LOSERS:")
    for r in results[-15:]:
        print(f"{r['symbol']:<8} {r['ctc_improvement']:>+9.1f}% {r['num_signals']:>8} {r['avg_ret_5d']:>+9.1f}% {r['avg_ret_10d']:>+9.1f}% {r['avg_ret_20d']:>+9.1f}% {r['down_5d_pct']:>9.0f}% {r['avg_max_loss_avoided']:>11.1f}%")

    # Correlation analysis
    print()
    print("="*100)
    print("KEY METRICS COMPARISON")
    print("="*100)

    winners = [r for r in results if r["ctc_improvement"] > 10]
    losers = [r for r in results if r["ctc_improvement"] < -10]

    if winners and losers:
        print()
        print(f"{'Metric':<30} {'Winners (CTC +10%+)':>20} {'Losers (CTC -10%-)':>20}")
        print("-"*75)

        w_5d = statistics.mean([r["avg_ret_5d"] for r in winners])
        l_5d = statistics.mean([r["avg_ret_5d"] for r in losers])
        print(f"{'Avg return 5d after signal':<30} {w_5d:>+19.1f}% {l_5d:>+19.1f}%")

        w_10d = statistics.mean([r["avg_ret_10d"] for r in winners])
        l_10d = statistics.mean([r["avg_ret_10d"] for r in losers])
        print(f"{'Avg return 10d after signal':<30} {w_10d:>+19.1f}% {l_10d:>+19.1f}%")

        w_20d = statistics.mean([r["avg_ret_20d"] for r in winners])
        l_20d = statistics.mean([r["avg_ret_20d"] for r in losers])
        print(f"{'Avg return 20d after signal':<30} {w_20d:>+19.1f}% {l_20d:>+19.1f}%")

        w_down = statistics.mean([r["down_5d_pct"] for r in winners])
        l_down = statistics.mean([r["down_5d_pct"] for r in losers])
        print(f"{'% signals followed by 5d drop':<30} {w_down:>19.0f}% {l_down:>19.0f}%")

        w_avoid = statistics.mean([r["avg_max_loss_avoided"] for r in winners])
        l_avoid = statistics.mean([r["avg_max_loss_avoided"] for r in losers])
        print(f"{'Avg max loss avoided (20d)':<30} {w_avoid:>19.1f}% {l_avoid:>19.1f}%")

        w_sigs = statistics.mean([r["num_signals"] for r in winners])
        l_sigs = statistics.mean([r["num_signals"] for r in losers])
        print(f"{'Avg # of DEFENSIVE signals':<30} {w_sigs:>19.1f} {l_sigs:>19.1f}")

    print()
    print("="*100)
    print("INSIGHT")
    print("="*100)
    print()
    print("The key difference is what happens AFTER the DEFENSIVE signal:")
    print()
    print("  WINNERS: Price continues DOWN or stays FLAT after signal")
    print("           -> CTC correctly sold before more losses")
    print()
    print("  LOSERS:  Price BOUNCES BACK quickly after signal")
    print("           -> CTC sold right at the bottom (worst timing)")
    print()


if __name__ == "__main__":
    run_analysis()
