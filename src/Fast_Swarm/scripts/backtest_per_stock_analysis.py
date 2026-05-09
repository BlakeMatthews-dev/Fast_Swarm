"""
Per-Stock Analysis: Which stocks benefit from which strategies?

For each stock individually, run ALL strategies:
  1. Buy & Hold (baseline)
  2. CTC v1 (sell DEFENSIVE, buy AGGRESSIVE only)
  3. CTC v2 (sell DEFENSIVE, buy when NOT DEFENSIVE)
  4. SMA 50/200 Crossover (golden/death cross)
  5. RSI 30/70 (oversold/overbought)
  6. Trailing Stop 10% (with 5% recovery re-entry)

Goal: Learn which TYPE of stocks benefit from which strategy.
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
CAPITAL_PER_ASSET = 1000

# Stock categories (rough classification)
CATEGORIES = {
    # Tech - Growth
    "AAPL": "Tech", "MSFT": "Tech", "NVDA": "Tech", "GOOGL": "Tech", "META": "Tech",
    "AMZN": "Tech", "TSLA": "Tech", "NFLX": "Tech", "AMD": "Tech", "INTC": "Tech",
    "ORCL": "Tech", "CRM": "Tech", "ADBE": "Tech", "NOW": "Tech", "QCOM": "Tech",
    "TXN": "Tech", "AVGO": "Tech", "CSCO": "Tech", "IBM": "Tech", "INTU": "Tech",

    # Financials
    "JPM": "Financial", "BAC": "Financial", "WFC": "Financial", "GS": "Financial",
    "V": "Financial", "MA": "Financial", "AXP": "Financial",

    # Healthcare
    "UNH": "Healthcare", "JNJ": "Healthcare", "LLY": "Healthcare", "ABBV": "Healthcare",
    "MRK": "Healthcare", "PFE": "Healthcare", "TMO": "Healthcare", "ABT": "Healthcare",
    "DHR": "Healthcare", "AMGN": "Healthcare", "ISRG": "Healthcare",

    # Consumer
    "WMT": "Consumer", "COST": "Consumer", "HD": "Consumer", "PG": "Consumer",
    "KO": "Consumer", "PEP": "Consumer", "MCD": "Consumer", "NKE": "Consumer",
    "DIS": "Consumer", "CMCSA": "Consumer",

    # Energy
    "XOM": "Energy", "CVX": "Energy",

    # Industrial
    "CAT": "Industrial", "GE": "Industrial", "HON": "Industrial", "BA": "Industrial",
    "MMM": "Industrial", "UPS": "Industrial", "LIN": "Industrial", "ACN": "Industrial",

    # Other
    "BRK-B": "Conglomerate", "PM": "Consumer", "VZ": "Telecom", "T": "Telecom",
    "DOW": "Materials", "TRV": "Insurance", "WBA": "Retail",

    # ETFs
    "SPY": "ETF-SP500", "QQQ": "ETF-Nasdaq", "DIA": "ETF-Dow", "IWM": "ETF-Russell",
}


def compute_sortino(returns: list) -> float:
    if len(returns) < 10:
        return 0.0
    mean_ret = statistics.mean(returns)
    downside = [min(0, r) ** 2 for r in returns]
    downside_std = (sum(downside) / len(downside)) ** 0.5
    if downside_std == 0:
        return 0.0
    return (mean_ret / downside_std) * (252 ** 0.5)


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


def compute_volatility(returns: list) -> float:
    if len(returns) < 10:
        return 0.0
    return statistics.stdev(returns) * (252 ** 0.5)  # Annualized


def compute_sma(prices: list, period: int) -> float:
    """Simple moving average of last N prices."""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def compute_rsi(prices: list, period: int = 14) -> float:
    """Relative Strength Index."""
    if len(prices) < period + 1:
        return None

    gains = []
    losses = []
    for i in range(-period, 0):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def load_all_symbols() -> dict:
    data = {}
    files = list(DATA_DIR.glob("*_1d.parquet"))
    for f in files:
        symbol = f.stem.replace("_1d", "")
        try:
            df = pl.read_parquet(f).sort("timestamp")
            deriv_cols = ["close_velocity_zscore", "close_acceleration_zscore",
                          "close_jerk_zscore", "ADX_14_jerk_zscore"]
            actual = [c for c in deriv_cols if c in df.columns or c.lower() in df.columns]
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


def backtest_single_stock(symbol: str, prices: list, rows_by_ts: dict, deriv_cols: list, common_ts: list) -> dict:
    """Run both strategies on a single stock."""
    service = BearProtectionService()

    # BUY & HOLD
    bh_shares = CAPITAL_PER_ASSET / prices[0] if prices[0] > 0 else 0
    bh_equity = [CAPITAL_PER_ASSET]
    bh_returns = []

    # CTC v2
    ctc_shares = CAPITAL_PER_ASSET / prices[0] if prices[0] > 0 else 0
    ctc_cash = 0.0
    ctc_in_cash = False
    ctc_equity = [CAPITAL_PER_ASSET]
    ctc_returns = []
    ctc_trades = 0
    defensive_days = 0

    warmup = 21

    for i in range(warmup, len(common_ts)):
        ts = common_ts[i]
        price = prices[i]

        # B&H
        bh_value = bh_shares * price
        prev_bh = bh_equity[-1]
        bh_equity.append(bh_value)
        if prev_bh > 0:
            bh_returns.append((bh_value - prev_bh) / prev_bh)

        # Get regime
        row = rows_by_ts.get(ts, {})
        state = row_to_market_state(row, symbol, deriv_cols)
        regime = service.evaluate(state).regime

        if regime == Regime.DEFENSIVE:
            defensive_days += 1

        # CTC v2
        if regime == Regime.DEFENSIVE and ctc_shares > 0:
            ctc_cash = ctc_shares * price
            ctc_shares = 0
            ctc_in_cash = True
            ctc_trades += 1
        elif regime != Regime.DEFENSIVE and ctc_in_cash and ctc_cash > 0:
            ctc_shares = ctc_cash / price if price > 0 else 0
            ctc_cash = 0
            ctc_in_cash = False
            ctc_trades += 1

        ctc_value = ctc_shares * price + ctc_cash
        prev_ctc = ctc_equity[-1]
        ctc_equity.append(ctc_value)
        if prev_ctc > 0:
            ctc_returns.append((ctc_value - prev_ctc) / prev_ctc)

    years = len(common_ts) / 252

    bh_roi = (bh_equity[-1] / CAPITAL_PER_ASSET - 1) * 100
    bh_maxdd = compute_max_drawdown(bh_equity)
    bh_sortino = compute_sortino(bh_returns)
    bh_vol = compute_volatility(bh_returns)

    ctc_roi = (ctc_equity[-1] / CAPITAL_PER_ASSET - 1) * 100
    ctc_maxdd = compute_max_drawdown(ctc_equity)
    ctc_sortino = compute_sortino(ctc_returns)

    return {
        "symbol": symbol,
        "category": CATEGORIES.get(symbol, "Unknown"),
        "bh_roi": bh_roi,
        "bh_maxdd": bh_maxdd,
        "bh_sortino": bh_sortino,
        "bh_volatility": bh_vol,
        "ctc_roi": ctc_roi,
        "ctc_maxdd": ctc_maxdd,
        "ctc_sortino": ctc_sortino,
        "roi_diff": ctc_roi - bh_roi,
        "dd_diff": ctc_maxdd - bh_maxdd,
        "sortino_diff": ctc_sortino - bh_sortino,
        "trades": ctc_trades,
        "defensive_days": defensive_days,
        "defensive_pct": defensive_days / (len(common_ts) - warmup) * 100,
        "ctc_wins_roi": ctc_roi > bh_roi,
        "ctc_wins_dd": ctc_maxdd < bh_maxdd,
        "ctc_wins_sortino": ctc_sortino > bh_sortino,
    }


def run_analysis():
    print("="*100)
    print("PER-STOCK ANALYSIS: Which Stocks Benefit from Crash-to-Cash?")
    print("="*100)
    print()

    if not DATA_DIR.exists():
        print(f"ERROR: Run download_sp50_dow30.py first")
        return

    print("Loading data...")
    data = load_all_symbols()
    symbols = list(data.keys())
    print(f"Loaded {len(symbols)} symbols")

    # Common timestamps
    all_ts = None
    for sym in symbols:
        ts_set = set(row["timestamp"] for row in data[sym]["rows"])
        all_ts = ts_set if all_ts is None else all_ts & ts_set
    common_ts = sorted(all_ts)
    years = len(common_ts) / 252

    print(f"Period: {len(common_ts):,} days ({years:.1f} years)")
    print()

    # Build price series
    prices = {sym: [] for sym in symbols}
    rows_by_ts = {sym: {row["timestamp"]: row for row in data[sym]["rows"]} for sym in symbols}
    for ts in common_ts:
        for sym in symbols:
            row = rows_by_ts[sym].get(ts)
            prices[sym].append(row["close"] if row and row.get("close") else (prices[sym][-1] if prices[sym] else 0))

    # Run backtest for each stock
    print("Running per-stock backtests...")
    results = []
    for sym in symbols:
        r = backtest_single_stock(
            sym, prices[sym], rows_by_ts[sym],
            data[sym]["deriv_cols"], common_ts
        )
        results.append(r)

    # ==========================================================================
    # WINNERS: CTC beats B&H on ROI
    # ==========================================================================
    print()
    print("="*100)
    print("STOCKS WHERE CTC BEATS BUY & HOLD (by ROI)")
    print("="*100)
    winners = [r for r in results if r["ctc_wins_roi"]]
    winners.sort(key=lambda x: -x["roi_diff"])

    print()
    print(f"{'Symbol':<8} {'Category':<12} {'B&H ROI':>10} {'CTC ROI':>10} {'Diff':>10} {'B&H DD':>10} {'CTC DD':>10} {'Def%':>8}")
    print("-"*90)
    for r in winners:
        print(f"{r['symbol']:<8} {r['category']:<12} {r['bh_roi']:>+9.1f}% {r['ctc_roi']:>+9.1f}% {r['roi_diff']:>+9.1f}% {r['bh_maxdd']:>9.1f}% {r['ctc_maxdd']:>9.1f}% {r['defensive_pct']:>7.1f}%")

    print(f"\nTotal winners: {len(winners)}/{len(results)} ({len(winners)/len(results)*100:.0f}%)")

    # ==========================================================================
    # LOSERS: B&H beats CTC on ROI
    # ==========================================================================
    print()
    print("="*100)
    print("STOCKS WHERE BUY & HOLD WINS (by ROI)")
    print("="*100)
    losers = [r for r in results if not r["ctc_wins_roi"]]
    losers.sort(key=lambda x: x["roi_diff"])

    print()
    print(f"{'Symbol':<8} {'Category':<12} {'B&H ROI':>10} {'CTC ROI':>10} {'Diff':>10} {'B&H DD':>10} {'CTC DD':>10} {'Def%':>8}")
    print("-"*90)
    for r in losers[:20]:  # Show worst 20
        print(f"{r['symbol']:<8} {r['category']:<12} {r['bh_roi']:>+9.1f}% {r['ctc_roi']:>+9.1f}% {r['roi_diff']:>+9.1f}% {r['bh_maxdd']:>9.1f}% {r['ctc_maxdd']:>9.1f}% {r['defensive_pct']:>7.1f}%")

    if len(losers) > 20:
        print(f"  ... and {len(losers) - 20} more")

    # ==========================================================================
    # ANALYSIS BY CATEGORY
    # ==========================================================================
    print()
    print("="*100)
    print("ANALYSIS BY SECTOR")
    print("="*100)

    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"wins": 0, "total": 0, "roi_diffs": [], "dd_diffs": [], "vol": []}
        categories[cat]["total"] += 1
        categories[cat]["roi_diffs"].append(r["roi_diff"])
        categories[cat]["dd_diffs"].append(r["dd_diff"])
        categories[cat]["vol"].append(r["bh_volatility"])
        if r["ctc_wins_roi"]:
            categories[cat]["wins"] += 1

    print()
    print(f"{'Category':<15} {'Win%':>8} {'Wins':>6} {'Avg ROI Diff':>14} {'Avg DD Diff':>14} {'Avg Vol':>10}")
    print("-"*75)
    cat_summary = []
    for cat, stats in categories.items():
        win_pct = stats["wins"] / stats["total"] * 100
        avg_roi = statistics.mean(stats["roi_diffs"])
        avg_dd = statistics.mean(stats["dd_diffs"])
        avg_vol = statistics.mean(stats["vol"]) * 100
        cat_summary.append((cat, win_pct, stats["wins"], stats["total"], avg_roi, avg_dd, avg_vol))

    cat_summary.sort(key=lambda x: -x[1])  # Sort by win%
    for cat, win_pct, wins, total, avg_roi, avg_dd, avg_vol in cat_summary:
        print(f"{cat:<15} {win_pct:>7.0f}% {wins:>3}/{total:<2} {avg_roi:>+13.1f}% {avg_dd:>+13.1f}% {avg_vol:>9.1f}%")

    # ==========================================================================
    # ANALYSIS BY VOLATILITY
    # ==========================================================================
    print()
    print("="*100)
    print("ANALYSIS BY VOLATILITY (B&H)")
    print("="*100)

    # Sort by volatility
    results.sort(key=lambda x: x["bh_volatility"])

    # Split into terciles
    n = len(results)
    low_vol = results[:n//3]
    mid_vol = results[n//3:2*n//3]
    high_vol = results[2*n//3:]

    for label, group in [("Low Volatility", low_vol), ("Medium Volatility", mid_vol), ("High Volatility", high_vol)]:
        wins = sum(1 for r in group if r["ctc_wins_roi"])
        avg_roi_diff = statistics.mean([r["roi_diff"] for r in group])
        avg_dd_diff = statistics.mean([r["dd_diff"] for r in group])
        avg_vol = statistics.mean([r["bh_volatility"] for r in group]) * 100
        symbols_in_group = [r["symbol"] for r in group]

        print()
        print(f"{label} (avg vol: {avg_vol:.1f}%):")
        print(f"  CTC wins: {wins}/{len(group)} ({wins/len(group)*100:.0f}%)")
        print(f"  Avg ROI diff: {avg_roi_diff:+.1f}%")
        print(f"  Avg DD diff: {avg_dd_diff:+.1f}%")
        print(f"  Stocks: {', '.join(symbols_in_group[:10])}{'...' if len(symbols_in_group) > 10 else ''}")

    # ==========================================================================
    # ANALYSIS BY DEFENSIVE FREQUENCY
    # ==========================================================================
    print()
    print("="*100)
    print("ANALYSIS BY DEFENSIVE SIGNAL FREQUENCY")
    print("="*100)

    # Sort by defensive %
    results.sort(key=lambda x: x["defensive_pct"])

    # Split into terciles
    low_def = results[:n//3]
    mid_def = results[n//3:2*n//3]
    high_def = results[2*n//3:]

    for label, group in [("Rarely Defensive", low_def), ("Sometimes Defensive", mid_def), ("Often Defensive", high_def)]:
        wins = sum(1 for r in group if r["ctc_wins_roi"])
        avg_roi_diff = statistics.mean([r["roi_diff"] for r in group])
        avg_dd_diff = statistics.mean([r["dd_diff"] for r in group])
        avg_def = statistics.mean([r["defensive_pct"] for r in group])

        print()
        print(f"{label} (avg {avg_def:.1f}% days in DEFENSIVE):")
        print(f"  CTC wins: {wins}/{len(group)} ({wins/len(group)*100:.0f}%)")
        print(f"  Avg ROI diff: {avg_roi_diff:+.1f}%")
        print(f"  Avg DD diff: {avg_dd_diff:+.1f}%")

    # ==========================================================================
    # KEY INSIGHTS
    # ==========================================================================
    print()
    print("="*100)
    print("KEY INSIGHTS")
    print("="*100)

    # Best candidates for CTC
    results.sort(key=lambda x: -x["roi_diff"])
    print()
    print("TOP 10 CANDIDATES FOR CRASH-TO-CASH:")
    for r in results[:10]:
        print(f"  {r['symbol']:<6} ({r['category']:<12}): +{r['roi_diff']:.1f}% ROI, {r['dd_diff']:+.1f}% DD, {r['bh_volatility']*100:.1f}% vol")

    # Worst candidates
    print()
    print("BOTTOM 10 (AVOID CTC, JUST B&H):")
    for r in results[-10:]:
        print(f"  {r['symbol']:<6} ({r['category']:<12}): {r['roi_diff']:.1f}% ROI, {r['dd_diff']:+.1f}% DD, {r['bh_volatility']*100:.1f}% vol")

    # Drawdown winners (even if ROI is lower)
    dd_winners = [r for r in results if r["ctc_wins_dd"]]
    print()
    print(f"DRAWDOWN PROTECTION: CTC reduced MaxDD for {len(dd_winners)}/{len(results)} stocks ({len(dd_winners)/len(results)*100:.0f}%)")

    best_dd_protection = sorted(results, key=lambda x: x["dd_diff"])[:10]
    print("Best DD protection:")
    for r in best_dd_protection:
        print(f"  {r['symbol']:<6}: B&H DD {r['bh_maxdd']:.1f}% -> CTC DD {r['ctc_maxdd']:.1f}% ({r['dd_diff']:+.1f}%)")


if __name__ == "__main__":
    run_analysis()
