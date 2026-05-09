"""
Momentum Rotation + Bear Protection - DAILY (5 Year Backtest)

Same strategy as hourly but on daily data for longer history:
  1. Buy & Hold: $70k split 7 ways
  2. Rotation: $35k in top 2 momentum assets, rotate on bear signals

Uses 1d timeframe with 1w (weekly) as confirmation TF.
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

DATA_DIR = PROJECT_ROOT / "data" / "test_data" / "EQUITY_DAILY_5Y"
SYMBOLS = ["AAPL", "NVDA", "TSLA", "PLTR", "JPM", "XOM", "SPY"]

TOTAL_CAPITAL = 70000
ROTATION_CAPITAL = 35000
ROTATION_SLOTS = 2
MOMENTUM_LOOKBACK = 20  # 20 trading days ~ 1 month


def compute_sortino(returns: list) -> float:
    if len(returns) < 10:
        return 0.0
    mean_ret = statistics.mean(returns)
    downside = [min(0, r) ** 2 for r in returns]
    downside_std = (sum(downside) / len(downside)) ** 0.5
    if downside_std == 0:
        return 0.0
    return (mean_ret / downside_std) * (252 ** 0.5)  # Annualized for daily


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
    """Load all daily data."""
    data = {}
    for symbol in SYMBOLS:
        path = DATA_DIR / f"{symbol}_1d.parquet"
        if not path.exists():
            print(f"  WARNING: Missing {symbol}")
            continue

        df = pl.read_parquet(path).sort("timestamp")

        # Get derivative columns
        deriv_cols = ["close_velocity_zscore", "close_acceleration_zscore",
                      "close_jerk_zscore", "ADX_14_jerk_zscore"]
        actual_cols = [c for c in deriv_cols if c in df.columns or c.lower() in df.columns]
        actual_cols = [c if c in df.columns else c.lower() for c in actual_cols if c in df.columns or c.lower() in df.columns]

        data[symbol] = {
            "df": df,
            "rows": df.to_dicts(),
            "deriv_cols": actual_cols,
        }
    return data


def compute_momentum(prices: list, lookback: int = 20) -> float:
    if len(prices) < lookback + 1:
        return 0.0
    current = prices[-1]
    past = prices[-lookback - 1]
    if past <= 0:
        return 0.0
    return (current - past) / past


def row_to_market_state(row: dict, symbol: str, deriv_cols: list) -> MarketState:
    ts = row.get("timestamp", datetime.now())

    def get_val(target):
        for c in deriv_cols:
            if target.lower() in c.lower():
                if c in row:
                    return row[c]
        return None

    # For daily, we use the daily derivatives directly (no MTF for simplicity)
    return MarketState(
        time=ts, symbol=symbol,
        tf_1h_vel=get_val("velocity"),
        tf_1h_acc=get_val("acceleration"),
        tf_1h_adx_jerk=get_val("adx"),
        tf_4h_vel=get_val("velocity"),  # Use same values (single TF)
        tf_4h_acc=get_val("acceleration"),
        tf_4h_adx_jerk=get_val("adx"),
        tf_1d_vel=None, tf_1d_acc=None, tf_1d_adx_jerk=None,
    )


def run_backtest():
    print("="*80)
    print("ROTATION STRATEGY BACKTEST - 5 YEAR DAILY")
    print("="*80)
    print()

    if not DATA_DIR.exists():
        print(f"ERROR: Data not found at {DATA_DIR}")
        print("Run download_equity_daily_5y.py first")
        return

    print("Loading data...")
    data = load_all_symbols()

    if len(data) < 2:
        print("ERROR: Need at least 2 symbols")
        return

    # Find common timestamps
    all_ts = None
    for sym, sdata in data.items():
        ts_set = set(row["timestamp"] for row in sdata["rows"])
        if all_ts is None:
            all_ts = ts_set
        else:
            all_ts &= ts_set

    common_ts = sorted(all_ts)
    print(f"Common trading days: {len(common_ts):,} (~{len(common_ts)/252:.1f} years)")

    # Build price series
    prices = {sym: [] for sym in data.keys()}
    rows_by_ts = {sym: {row["timestamp"]: row for row in data[sym]["rows"]} for sym in data.keys()}

    for ts in common_ts:
        for sym in data.keys():
            row = rows_by_ts[sym].get(ts)
            if row and row.get("close"):
                prices[sym].append(row["close"])
            else:
                prices[sym].append(prices[sym][-1] if prices[sym] else 0)

    services = {sym: BearProtectionService() for sym in data.keys()}

    # BUY & HOLD
    bh_per_asset = TOTAL_CAPITAL / len(data)
    bh_shares = {sym: bh_per_asset / prices[sym][0] if prices[sym][0] > 0 else 0 for sym in data.keys()}
    bh_equity = [TOTAL_CAPITAL]
    bh_returns = []

    # ROTATION
    rotation_equity = [ROTATION_CAPITAL]
    rotation_returns = []
    rotation_holdings = []
    rotation_trades = 0

    warmup = MOMENTUM_LOOKBACK + 1

    print(f"\nBacktesting {len(common_ts) - warmup:,} days...")

    for i in range(warmup, len(common_ts)):
        ts = common_ts[i]

        # BUY & HOLD
        bh_value = sum(bh_shares[sym] * prices[sym][i] for sym in data.keys())
        prev_bh = bh_equity[-1]
        bh_equity.append(bh_value)
        if prev_bh > 0:
            bh_returns.append((bh_value - prev_bh) / prev_bh)

        # ROTATION
        momentum = {}
        regimes = {}
        for sym in data.keys():
            momentum[sym] = compute_momentum(prices[sym][:i+1], MOMENTUM_LOOKBACK)
            row = rows_by_ts[sym].get(ts, {})
            state = row_to_market_state(row, sym, data[sym]["deriv_cols"])
            regimes[sym] = services[sym].evaluate(state).regime

        # Rank by momentum (exclude DEFENSIVE)
        ranked = sorted(
            [(sym, mom) for sym, mom in momentum.items() if regimes[sym] != Regime.DEFENSIVE],
            key=lambda x: -x[1]
        )
        if len(ranked) < ROTATION_SLOTS:
            remaining = [sym for sym in data.keys() if sym not in [r[0] for r in ranked]]
            for sym in remaining:
                ranked.append((sym, momentum[sym]))

        target_symbols = [sym for sym, _ in ranked[:ROTATION_SLOTS]]

        # Check rotation
        need_rotation = not rotation_holdings
        for sym, shares in rotation_holdings:
            if regimes[sym] == Regime.DEFENSIVE:
                need_rotation = True
                break

        if need_rotation:
            current_value = sum(shares * prices[sym][i] for sym, shares in rotation_holdings) if rotation_holdings else ROTATION_CAPITAL
            new_holdings = []
            per_slot = current_value / ROTATION_SLOTS
            for sym in target_symbols:
                shares = per_slot / prices[sym][i] if prices[sym][i] > 0 else 0
                new_holdings.append((sym, shares))

            current_symbols = [h[0] for h in rotation_holdings]
            if rotation_holdings and set(current_symbols) != set(target_symbols):
                rotation_trades += 1

            rotation_holdings = new_holdings

        rot_value = sum(shares * prices[sym][i] for sym, shares in rotation_holdings)
        prev_rot = rotation_equity[-1]
        rotation_equity.append(rot_value)
        if prev_rot > 0:
            rotation_returns.append((rot_value - prev_rot) / prev_rot)

    # RESULTS
    print()
    print("="*80)
    print("RESULTS")
    print("="*80)
    print()

    years = len(common_ts) / 252
    print(f"Period: {len(common_ts):,} days ({years:.1f} years)")
    print(f"Date range: {common_ts[0]} to {common_ts[-1]}")
    print(f"Rotation trades: {rotation_trades}")
    print()

    bh_roi = (bh_equity[-1] / TOTAL_CAPITAL - 1) * 100
    bh_sortino = compute_sortino(bh_returns)
    bh_maxdd = compute_max_drawdown(bh_equity)

    rot_roi = (rotation_equity[-1] / ROTATION_CAPITAL - 1) * 100
    rot_sortino = compute_sortino(rotation_returns)
    rot_maxdd = compute_max_drawdown(rotation_equity)

    print(f"{'STRATEGY':<30} {'Capital':>12} {'Final':>14} {'ROI':>10} {'Sortino':>10} {'MaxDD':>10}")
    print("-"*90)
    print(f"{'Buy & Hold (7 assets)':<30} ${TOTAL_CAPITAL:>10,.0f} ${bh_equity[-1]:>12,.0f} {bh_roi:>+9.1f}% {bh_sortino:>9.2f} {bh_maxdd:>9.1f}%")
    print(f"{'Rotation (top 2 + BP)':<30} ${ROTATION_CAPITAL:>10,.0f} ${rotation_equity[-1]:>12,.0f} {rot_roi:>+9.1f}% {rot_sortino:>9.2f} {rot_maxdd:>9.1f}%")

    # Normalize comparison
    print()
    print("NORMALIZED (same $70k capital):")
    print("-"*90)
    rot_norm_final = TOTAL_CAPITAL * (1 + rot_roi/100)
    print(f"{'Buy & Hold':<30} ${TOTAL_CAPITAL:>10,.0f} ${bh_equity[-1]:>12,.0f} {bh_roi:>+9.1f}%")
    print(f"{'Rotation (scaled)':<30} ${TOTAL_CAPITAL:>10,.0f} ${rot_norm_final:>12,.0f} {rot_roi:>+9.1f}%")

    # CAGR
    bh_cagr = ((bh_equity[-1] / TOTAL_CAPITAL) ** (1/years) - 1) * 100
    rot_cagr = ((rotation_equity[-1] / ROTATION_CAPITAL) ** (1/years) - 1) * 100

    print()
    print(f"CAGR (Compound Annual Growth Rate):")
    print(f"  Buy & Hold:  {bh_cagr:+.1f}% per year")
    print(f"  Rotation:    {rot_cagr:+.1f}% per year")

    print()
    print("="*80)
    print("VERDICT")
    print("="*80)
    print()
    print(f"  ROI:      {'ROTATION' if rot_roi > bh_roi else 'BUY & HOLD'} wins by {abs(rot_roi - bh_roi):.1f}%")
    print(f"  MaxDD:    {'ROTATION' if rot_maxdd < bh_maxdd else 'BUY & HOLD'} wins ({min(rot_maxdd, bh_maxdd):.1f}% vs {max(rot_maxdd, bh_maxdd):.1f}%)")
    print(f"  Sortino:  {'ROTATION' if rot_sortino > bh_sortino else 'BUY & HOLD'} wins ({max(rot_sortino, bh_sortino):.2f} vs {min(rot_sortino, bh_sortino):.2f})")

    print()
    print("Final holdings:", [h[0] for h in rotation_holdings])


if __name__ == "__main__":
    run_backtest()
