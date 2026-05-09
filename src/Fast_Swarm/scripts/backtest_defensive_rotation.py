"""
Defensive Rotation Strategy Backtest

Simple Rules:
  1. Start with equal weight in all assets
  2. When DEFENSIVE triggers on an asset -> sell it, buy best performer
  3. Track vs pure buy & hold

This tests whether bear protection can improve returns by rotating
out of weak assets into strong ones.
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
TOTAL_CAPITAL = 70000
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
    print("="*80)
    print("DEFENSIVE ROTATION STRATEGY")
    print("="*80)
    print()
    print("Rules:")
    print("  1. Start with equal weight in all assets")
    print("  2. When DEFENSIVE triggers -> sell that asset, buy best performer")
    print("  3. Compare vs pure buy & hold")
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

    # ==========================================================================
    # BUY & HOLD: Equal weight, never sell
    # ==========================================================================
    per_stock = TOTAL_CAPITAL / len(symbols)
    bh_shares = {sym: per_stock / prices[sym][0] if prices[sym][0] > 0 else 0 for sym in symbols}
    bh_equity = [TOTAL_CAPITAL]
    bh_returns = []

    # ==========================================================================
    # DEFENSIVE ROTATION: Equal weight, but rotate out on DEFENSIVE
    # ==========================================================================
    dr_shares = {sym: per_stock / prices[sym][0] if prices[sym][0] > 0 else 0 for sym in symbols}
    dr_equity = [TOTAL_CAPITAL]
    dr_returns = []
    dr_trades = 0
    dr_rotations = []  # Log rotations

    warmup = MOMENTUM_LOOKBACK + 1
    print(f"\nBacktesting {len(common_ts) - warmup:,} days...")

    for i in range(warmup, len(common_ts)):
        ts = common_ts[i]

        # Buy & Hold equity
        bh_value = sum(bh_shares[sym] * prices[sym][i] for sym in symbols)
        prev_bh = bh_equity[-1]
        bh_equity.append(bh_value)
        if prev_bh > 0:
            bh_returns.append((bh_value - prev_bh) / prev_bh)

        # Get regimes and momentum for all
        regimes = {}
        momentum = {}
        for sym in symbols:
            row = rows_by_ts[sym].get(ts, {})
            state = row_to_market_state(row, sym, data[sym]["deriv_cols"])
            regimes[sym] = services[sym].evaluate(state).regime
            momentum[sym] = compute_momentum(prices[sym][:i+1], MOMENTUM_LOOKBACK)

        # Find best performer not in DEFENSIVE
        best_candidates = [(sym, momentum[sym]) for sym in symbols
                          if regimes[sym] != Regime.DEFENSIVE and momentum[sym] > 0]
        best_candidates.sort(key=lambda x: -x[1])
        best_sym = best_candidates[0][0] if best_candidates else None

        # Check each position - if DEFENSIVE, rotate to best
        for sym in symbols:
            if dr_shares[sym] > 0 and regimes[sym] == Regime.DEFENSIVE and best_sym and best_sym != sym:
                # Sell this position
                sell_value = dr_shares[sym] * prices[sym][i]
                dr_shares[sym] = 0

                # Buy best performer
                buy_shares = sell_value / prices[best_sym][i] if prices[best_sym][i] > 0 else 0
                dr_shares[best_sym] += buy_shares

                dr_trades += 1
                dr_rotations.append({
                    "date": ts.date(),
                    "from": sym,
                    "to": best_sym,
                    "value": sell_value,
                })

        # Defensive Rotation equity
        dr_value = sum(dr_shares[sym] * prices[sym][i] for sym in symbols)
        prev_dr = dr_equity[-1]
        dr_equity.append(dr_value)
        if prev_dr > 0:
            dr_returns.append((dr_value - prev_dr) / prev_dr)

    # ==========================================================================
    # RESULTS
    # ==========================================================================
    print()
    print("="*80)
    print("RESULTS")
    print("="*80)

    bh_roi = (bh_equity[-1] / TOTAL_CAPITAL - 1) * 100
    bh_cagr = ((bh_equity[-1] / TOTAL_CAPITAL) ** (1/years) - 1) * 100
    bh_sortino = compute_sortino(bh_returns)
    bh_maxdd = compute_max_drawdown(bh_equity)

    dr_roi = (dr_equity[-1] / TOTAL_CAPITAL - 1) * 100
    dr_cagr = ((dr_equity[-1] / TOTAL_CAPITAL) ** (1/years) - 1) * 100
    dr_sortino = compute_sortino(dr_returns)
    dr_maxdd = compute_max_drawdown(dr_equity)

    print()
    print(f"{'STRATEGY':<30} {'Final':>14} {'ROI':>10} {'CAGR':>8} {'Sortino':>9} {'MaxDD':>9}")
    print("-"*85)
    print(f"{'Buy & Hold (equal weight)':<30} ${bh_equity[-1]:>12,.0f} {bh_roi:>+9.1f}% {bh_cagr:>+7.1f}% {bh_sortino:>8.2f} {bh_maxdd:>8.1f}%")
    print(f"{'Defensive Rotation':<30} ${dr_equity[-1]:>12,.0f} {dr_roi:>+9.1f}% {dr_cagr:>+7.1f}% {dr_sortino:>8.2f} {dr_maxdd:>8.1f}%")

    print()
    print(f"Total rotations: {dr_trades}")
    print(f"ROI difference: {dr_roi - bh_roi:+.1f}%")
    print(f"MaxDD difference: {dr_maxdd - bh_maxdd:+.1f}%")

    # Show some rotations
    if dr_rotations:
        print()
        print("Sample rotations:")
        for r in dr_rotations[:10]:
            print(f"  {r['date']}: {r['from']} -> {r['to']} (${r['value']:,.0f})")
        if len(dr_rotations) > 10:
            print(f"  ... and {len(dr_rotations) - 10} more")

    # Final holdings
    print()
    print("Final holdings (top 10 by value):")
    holdings = [(sym, dr_shares[sym] * prices[sym][-1]) for sym in symbols if dr_shares[sym] > 0]
    holdings.sort(key=lambda x: -x[1])
    for sym, val in holdings[:10]:
        print(f"  {sym}: ${val:,.0f}")

    print()
    print("="*80)
    if dr_roi > bh_roi:
        print(f"DEFENSIVE ROTATION WINS by {dr_roi - bh_roi:.1f}%")
    else:
        print(f"BUY & HOLD WINS by {bh_roi - dr_roi:.1f}%")
    print("="*80)


if __name__ == "__main__":
    run_backtest()
