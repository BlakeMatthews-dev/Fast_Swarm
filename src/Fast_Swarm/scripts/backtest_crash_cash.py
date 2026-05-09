"""
Crash-to-Cash Strategy Backtest

Simple Rules:
  1. Start with $1000 per asset (equal weight)
  2. When DEFENSIVE triggers -> sell that asset to CASH
  3. When AGGRESSIVE triggers AND we have cash -> buy back in
  4. Compare vs pure buy & hold

This tests whether bear protection can improve returns by going to cash
during crashes and re-entering on strength.
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


def run_backtest():
    print("="*80)
    print("CRASH-TO-CASH STRATEGY")
    print("="*80)
    print()
    print("Rules:")
    print("  1. Start with $1000 per asset")
    print("  2. DEFENSIVE signal -> sell to CASH")
    print("  3. AGGRESSIVE signal + have cash -> buy back in")
    print("  4. Compare vs pure buy & hold")
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
    print(f"Range: {common_ts[0].date()} to {common_ts[-1].date()}")

    # Build price series
    prices = {sym: [] for sym in symbols}
    rows_by_ts = {sym: {row["timestamp"]: row for row in data[sym]["rows"]} for sym in symbols}
    for ts in common_ts:
        for sym in symbols:
            row = rows_by_ts[sym].get(ts)
            prices[sym].append(row["close"] if row and row.get("close") else (prices[sym][-1] if prices[sym] else 0))

    services = {sym: BearProtectionService() for sym in symbols}

    total_capital = CAPITAL_PER_ASSET * len(symbols)

    # ==========================================================================
    # BUY & HOLD: $1000 per asset, never sell
    # ==========================================================================
    bh_shares = {sym: CAPITAL_PER_ASSET / prices[sym][0] if prices[sym][0] > 0 else 0 for sym in symbols}
    bh_equity = [total_capital]
    bh_returns = []

    # ==========================================================================
    # CRASH-TO-CASH: Sell to cash on DEFENSIVE, buy on AGGRESSIVE
    # ==========================================================================
    ctc_shares = {sym: CAPITAL_PER_ASSET / prices[sym][0] if prices[sym][0] > 0 else 0 for sym in symbols}
    ctc_cash = 0.0  # Cash from selling
    ctc_equity = [total_capital]
    ctc_returns = []
    ctc_sells = 0
    ctc_buys = 0
    ctc_events = []  # Log events

    # Track which symbols are "in cash" (sold but waiting to re-buy)
    in_cash = {sym: False for sym in symbols}
    cash_per_symbol = {sym: 0.0 for sym in symbols}  # Track cash from each symbol sale

    warmup = 21  # Need some data for signals
    print(f"\nBacktesting {len(common_ts) - warmup:,} days...")

    for i in range(warmup, len(common_ts)):
        ts = common_ts[i]

        # Buy & Hold equity
        bh_value = sum(bh_shares[sym] * prices[sym][i] for sym in symbols)
        prev_bh = bh_equity[-1]
        bh_equity.append(bh_value)
        if prev_bh > 0:
            bh_returns.append((bh_value - prev_bh) / prev_bh)

        # Get regimes for all symbols
        regimes = {}
        for sym in symbols:
            row = rows_by_ts[sym].get(ts, {})
            state = row_to_market_state(row, sym, data[sym]["deriv_cols"])
            regimes[sym] = services[sym].evaluate(state).regime

        # Process each symbol
        for sym in symbols:
            regime = regimes[sym]

            # Rule 2: DEFENSIVE and holding shares -> sell to cash
            if regime == Regime.DEFENSIVE and ctc_shares[sym] > 0:
                sell_value = ctc_shares[sym] * prices[sym][i]
                cash_per_symbol[sym] = sell_value
                ctc_shares[sym] = 0
                in_cash[sym] = True
                ctc_sells += 1
                ctc_events.append({
                    "date": ts.date(),
                    "action": "SELL",
                    "symbol": sym,
                    "value": sell_value,
                    "regime": "DEFENSIVE"
                })

            # Rule 3: AGGRESSIVE and we have cash for this symbol -> buy back
            elif regime == Regime.AGGRESSIVE and in_cash[sym] and cash_per_symbol[sym] > 0:
                buy_shares = cash_per_symbol[sym] / prices[sym][i] if prices[sym][i] > 0 else 0
                ctc_shares[sym] = buy_shares
                cash_per_symbol[sym] = 0
                in_cash[sym] = False
                ctc_buys += 1
                ctc_events.append({
                    "date": ts.date(),
                    "action": "BUY",
                    "symbol": sym,
                    "shares": buy_shares,
                    "regime": "AGGRESSIVE"
                })

        # Calculate total equity (shares + cash)
        shares_value = sum(ctc_shares[sym] * prices[sym][i] for sym in symbols)
        total_cash = sum(cash_per_symbol.values())
        ctc_value = shares_value + total_cash

        prev_ctc = ctc_equity[-1]
        ctc_equity.append(ctc_value)
        if prev_ctc > 0:
            ctc_returns.append((ctc_value - prev_ctc) / prev_ctc)

    # ==========================================================================
    # RESULTS
    # ==========================================================================
    print()
    print("="*80)
    print("RESULTS")
    print("="*80)

    bh_roi = (bh_equity[-1] / total_capital - 1) * 100
    bh_cagr = ((bh_equity[-1] / total_capital) ** (1/years) - 1) * 100
    bh_sortino = compute_sortino(bh_returns)
    bh_maxdd = compute_max_drawdown(bh_equity)

    ctc_roi = (ctc_equity[-1] / total_capital - 1) * 100
    ctc_cagr = ((ctc_equity[-1] / total_capital) ** (1/years) - 1) * 100
    ctc_sortino = compute_sortino(ctc_returns)
    ctc_maxdd = compute_max_drawdown(ctc_equity)

    print()
    print(f"Starting capital: ${total_capital:,.0f} (${CAPITAL_PER_ASSET} x {len(symbols)} assets)")
    print()
    print(f"{'STRATEGY':<30} {'Final':>14} {'ROI':>10} {'CAGR':>8} {'Sortino':>9} {'MaxDD':>9}")
    print("-"*85)
    print(f"{'Buy & Hold':<30} ${bh_equity[-1]:>12,.0f} {bh_roi:>+9.1f}% {bh_cagr:>+7.1f}% {bh_sortino:>8.2f} {bh_maxdd:>8.1f}%")
    print(f"{'Crash-to-Cash':<30} ${ctc_equity[-1]:>12,.0f} {ctc_roi:>+9.1f}% {ctc_cagr:>+7.1f}% {ctc_sortino:>8.2f} {ctc_maxdd:>8.1f}%")

    print()
    print(f"Total sells (DEFENSIVE): {ctc_sells}")
    print(f"Total buys (AGGRESSIVE): {ctc_buys}")
    print(f"Pending re-buys: {sum(1 for sym in symbols if in_cash[sym])}")
    print(f"Cash still held: ${sum(cash_per_symbol.values()):,.0f}")

    # Show some events
    if ctc_events:
        print()
        print("Sample events:")
        for e in ctc_events[:15]:
            if e["action"] == "SELL":
                print(f"  {e['date']}: SELL {e['symbol']} -> ${e['value']:,.0f} cash")
            else:
                print(f"  {e['date']}: BUY {e['symbol']} ({e['shares']:.2f} shares)")
        if len(ctc_events) > 15:
            print(f"  ... and {len(ctc_events) - 15} more events")

    # Summary
    print()
    print("="*80)
    print("COMPARISON")
    print("="*80)
    print()
    print(f"  ROI:     {'+' if ctc_roi > bh_roi else ''}{ctc_roi - bh_roi:.1f}% vs B&H")
    print(f"  MaxDD:   {'+' if ctc_maxdd > bh_maxdd else ''}{ctc_maxdd - bh_maxdd:.1f}% vs B&H")
    print(f"  Sortino: {'+' if ctc_sortino > bh_sortino else ''}{ctc_sortino - bh_sortino:.2f} vs B&H")
    print()

    if ctc_maxdd < bh_maxdd:
        print(f"  [WIN] Crash-to-Cash reduced max drawdown by {bh_maxdd - ctc_maxdd:.1f}%")
    if ctc_roi > bh_roi:
        print(f"  [WIN] Crash-to-Cash increased ROI by {ctc_roi - bh_roi:.1f}%")
    if ctc_sortino > bh_sortino:
        print(f"  [WIN] Crash-to-Cash improved Sortino by {ctc_sortino - bh_sortino:.2f}")

    print()
    winner = "CRASH-TO-CASH" if ctc_roi > bh_roi else "BUY & HOLD"
    print(f"OVERALL: {winner} wins on ROI")
    print("="*80)


if __name__ == "__main__":
    run_backtest()
