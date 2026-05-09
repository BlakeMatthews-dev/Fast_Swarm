"""
Smart Rotation Strategy

The insight: DEFENSIVE signal tells us WHICH assets are weak.
Instead of going to cash, rotate that capital to the STRONGEST asset.

Rules:
  1. Start with $1000 per asset
  2. When DEFENSIVE triggers on asset X:
     - Sell X completely
     - Buy the best momentum asset that's NOT in DEFENSIVE
  3. This compounds winners - strong assets get more capital

Compare to:
  - Buy & Hold (baseline)
  - CTC v2 (sell to cash, buy back when not defensive)
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
MOMENTUM_LOOKBACK = 20


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


def compute_momentum(prices: list, lookback: int = 20) -> float:
    if len(prices) < lookback + 1:
        return 0.0
    current = prices[-1]
    past = prices[-lookback - 1]
    if past <= 0:
        return 0.0
    return (current - past) / past


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
    print("="*90)
    print("SMART ROTATION STRATEGY")
    print("="*90)
    print()
    print("Logic: When DEFENSIVE triggers, rotate that capital to the BEST momentum asset")
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
    # STRATEGY 1: BUY & HOLD
    # ==========================================================================
    bh_shares = {sym: CAPITAL_PER_ASSET / prices[sym][0] if prices[sym][0] > 0 else 0 for sym in symbols}
    bh_equity = [total_capital]
    bh_returns = []

    # ==========================================================================
    # STRATEGY 2: CTC v2 (baseline crash-to-cash)
    # ==========================================================================
    ctc_shares = {sym: CAPITAL_PER_ASSET / prices[sym][0] if prices[sym][0] > 0 else 0 for sym in symbols}
    ctc_cash = {sym: 0.0 for sym in symbols}
    ctc_in_cash = {sym: False for sym in symbols}
    ctc_equity = [total_capital]
    ctc_returns = []

    # ==========================================================================
    # STRATEGY 3: SMART ROTATION (defensive -> rotate to best)
    # ==========================================================================
    sr_shares = {sym: CAPITAL_PER_ASSET / prices[sym][0] if prices[sym][0] > 0 else 0 for sym in symbols}
    sr_equity = [total_capital]
    sr_returns = []
    sr_rotations = 0
    sr_events = []

    # ==========================================================================
    # STRATEGY 4: SMART ROTATION + CONCENTRATION LIMIT (max 10% per asset)
    # ==========================================================================
    sr_lim_shares = {sym: CAPITAL_PER_ASSET / prices[sym][0] if prices[sym][0] > 0 else 0 for sym in symbols}
    sr_lim_cash = 0.0  # Overflow goes to cash
    sr_lim_equity = [total_capital]
    sr_lim_returns = []
    sr_lim_rotations = 0
    MAX_CONCENTRATION = 0.10  # Max 10% in any single asset

    warmup = MOMENTUM_LOOKBACK + 1
    print(f"\nBacktesting {len(common_ts) - warmup:,} days...")

    for i in range(warmup, len(common_ts)):
        ts = common_ts[i]

        # ---------------------------------------------------------------------
        # BUY & HOLD
        # ---------------------------------------------------------------------
        bh_value = sum(bh_shares[sym] * prices[sym][i] for sym in symbols)
        prev_bh = bh_equity[-1]
        bh_equity.append(bh_value)
        if prev_bh > 0:
            bh_returns.append((bh_value - prev_bh) / prev_bh)

        # Get regimes and momentum for all symbols
        regimes = {}
        momentum = {}
        for sym in symbols:
            row = rows_by_ts[sym].get(ts, {})
            state = row_to_market_state(row, sym, data[sym]["deriv_cols"])
            regimes[sym] = services[sym].evaluate(state).regime
            momentum[sym] = compute_momentum(prices[sym][:i+1], MOMENTUM_LOOKBACK)

        # Find best target (highest momentum, not DEFENSIVE)
        candidates = [(sym, momentum[sym]) for sym in symbols
                      if regimes[sym] != Regime.DEFENSIVE and momentum[sym] > 0]
        candidates.sort(key=lambda x: -x[1])
        best_target = candidates[0][0] if candidates else None

        # ---------------------------------------------------------------------
        # CTC v2 (cash strategy)
        # ---------------------------------------------------------------------
        for sym in symbols:
            if regimes[sym] == Regime.DEFENSIVE and ctc_shares[sym] > 0:
                ctc_cash[sym] = ctc_shares[sym] * prices[sym][i]
                ctc_shares[sym] = 0
                ctc_in_cash[sym] = True
            elif regimes[sym] != Regime.DEFENSIVE and ctc_in_cash[sym] and ctc_cash[sym] > 0:
                ctc_shares[sym] = ctc_cash[sym] / prices[sym][i] if prices[sym][i] > 0 else 0
                ctc_cash[sym] = 0
                ctc_in_cash[sym] = False

        ctc_value = sum(ctc_shares[sym] * prices[sym][i] for sym in symbols) + sum(ctc_cash.values())
        prev_ctc = ctc_equity[-1]
        ctc_equity.append(ctc_value)
        if prev_ctc > 0:
            ctc_returns.append((ctc_value - prev_ctc) / prev_ctc)

        # ---------------------------------------------------------------------
        # SMART ROTATION (no limit)
        # ---------------------------------------------------------------------
        for sym in symbols:
            if regimes[sym] == Regime.DEFENSIVE and sr_shares[sym] > 0 and best_target and best_target != sym:
                # Sell this asset
                sell_value = sr_shares[sym] * prices[sym][i]
                sr_shares[sym] = 0

                # Buy best target
                buy_shares = sell_value / prices[best_target][i] if prices[best_target][i] > 0 else 0
                sr_shares[best_target] += buy_shares

                sr_rotations += 1
                sr_events.append({
                    "date": ts.date(),
                    "from": sym,
                    "to": best_target,
                    "value": sell_value,
                    "momentum": momentum[best_target],
                })

        sr_value = sum(sr_shares[sym] * prices[sym][i] for sym in symbols)
        prev_sr = sr_equity[-1]
        sr_equity.append(sr_value)
        if prev_sr > 0:
            sr_returns.append((sr_value - prev_sr) / prev_sr)

        # ---------------------------------------------------------------------
        # SMART ROTATION WITH LIMIT (max 10% concentration)
        # ---------------------------------------------------------------------
        current_portfolio_value = sum(sr_lim_shares[sym] * prices[sym][i] for sym in symbols) + sr_lim_cash
        max_per_asset = current_portfolio_value * MAX_CONCENTRATION

        for sym in symbols:
            if regimes[sym] == Regime.DEFENSIVE and sr_lim_shares[sym] > 0 and best_target and best_target != sym:
                # Sell this asset
                sell_value = sr_lim_shares[sym] * prices[sym][i]
                sr_lim_shares[sym] = 0

                # Check if target is at concentration limit
                target_current_value = sr_lim_shares[best_target] * prices[best_target][i]
                room_to_add = max_per_asset - target_current_value

                if room_to_add > 0:
                    # Can add some to target
                    add_value = min(sell_value, room_to_add)
                    overflow = sell_value - add_value

                    buy_shares = add_value / prices[best_target][i] if prices[best_target][i] > 0 else 0
                    sr_lim_shares[best_target] += buy_shares
                    sr_lim_cash += overflow
                else:
                    # Target at limit, all goes to cash
                    sr_lim_cash += sell_value

                sr_lim_rotations += 1

        sr_lim_value = sum(sr_lim_shares[sym] * prices[sym][i] for sym in symbols) + sr_lim_cash
        prev_sr_lim = sr_lim_equity[-1]
        sr_lim_equity.append(sr_lim_value)
        if prev_sr_lim > 0:
            sr_lim_returns.append((sr_lim_value - prev_sr_lim) / prev_sr_lim)

    # ==========================================================================
    # RESULTS
    # ==========================================================================
    print()
    print("="*90)
    print("RESULTS")
    print("="*90)
    print()
    print(f"Starting capital: ${total_capital:,.0f} (${CAPITAL_PER_ASSET} x {len(symbols)} assets)")
    print()

    results = []
    for name, equity, returns, trades in [
        ("Buy & Hold", bh_equity, bh_returns, 0),
        ("CTC v2 (to cash)", ctc_equity, ctc_returns, 0),
        ("Smart Rotation", sr_equity, sr_returns, sr_rotations),
        ("Smart Rot + 10% Limit", sr_lim_equity, sr_lim_returns, sr_lim_rotations),
    ]:
        roi = (equity[-1] / total_capital - 1) * 100
        cagr = ((equity[-1] / total_capital) ** (1/years) - 1) * 100
        sortino = compute_sortino(returns)
        maxdd = compute_max_drawdown(equity)
        results.append({
            "name": name, "final": equity[-1], "roi": roi, "cagr": cagr,
            "sortino": sortino, "maxdd": maxdd, "trades": trades,
        })

    results.sort(key=lambda x: -x["roi"])

    print(f"{'RANK':<5} {'STRATEGY':<25} {'Final':>14} {'ROI':>10} {'CAGR':>8} {'Sortino':>9} {'MaxDD':>9} {'Rotations':>10}")
    print("-"*100)
    for i, r in enumerate(results):
        print(f"{i+1:<5} {r['name']:<25} ${r['final']:>12,.0f} {r['roi']:>+9.1f}% {r['cagr']:>+7.1f}% {r['sortino']:>8.2f} {r['maxdd']:>8.1f}% {r['trades']:>10}")

    # Show final holdings for smart rotation
    print()
    print("="*90)
    print("SMART ROTATION - FINAL HOLDINGS (Top 10)")
    print("="*90)
    holdings = [(sym, sr_shares[sym] * prices[sym][-1]) for sym in symbols if sr_shares[sym] > 0]
    holdings.sort(key=lambda x: -x[1])
    total_held = sum(h[1] for h in holdings)

    for sym, val in holdings[:10]:
        pct = (val / sr_equity[-1]) * 100
        print(f"  {sym:<6} ${val:>12,.0f}  ({pct:>5.1f}%)")

    if len(holdings) > 10:
        others = sum(h[1] for h in holdings[10:])
        print(f"  {'Others':<6} ${others:>12,.0f}  ({len(holdings)-10} more assets)")

    print()
    print(f"Total in {len(holdings)} assets: ${total_held:,.0f}")
    print(f"Concentration: Top asset is {holdings[0][1]/sr_equity[-1]*100:.1f}% of portfolio")

    # Sample rotations
    if sr_events:
        print()
        print("="*90)
        print("SAMPLE ROTATIONS")
        print("="*90)
        for e in sr_events[:15]:
            print(f"  {e['date']}: {e['from']:<6} -> {e['to']:<6} ${e['value']:>8,.0f} (mom: {e['momentum']:+.1%})")
        if len(sr_events) > 15:
            print(f"  ... and {len(sr_events) - 15} more rotations")

    # Analysis
    print()
    print("="*90)
    print("ANALYSIS")
    print("="*90)
    bh_r = next(r for r in results if r["name"] == "Buy & Hold")
    sr_r = next(r for r in results if r["name"] == "Smart Rotation")

    print()
    print(f"  Smart Rotation vs Buy & Hold:")
    print(f"    ROI:     {sr_r['roi'] - bh_r['roi']:+.1f}%")
    print(f"    MaxDD:   {sr_r['maxdd'] - bh_r['maxdd']:+.1f}%")
    print(f"    Sortino: {sr_r['sortino'] - bh_r['sortino']:+.2f}")
    print()

    if sr_r['roi'] > bh_r['roi']:
        print("  VERDICT: Smart Rotation WINS on ROI")
    else:
        print("  VERDICT: Buy & Hold WINS on ROI")

    if sr_r['maxdd'] < bh_r['maxdd']:
        print("  VERDICT: Smart Rotation WINS on Risk (lower drawdown)")


if __name__ == "__main__":
    run_backtest()
