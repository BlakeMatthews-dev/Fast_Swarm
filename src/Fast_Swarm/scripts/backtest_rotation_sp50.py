"""
Large-Scale Rotation Backtest - S&P 50 + Dow 30

Tests momentum rotation + bear protection on 63 stocks over 5 years.

Strategies:
  1. Buy & Hold SPY (benchmark)
  2. Buy & Hold equal-weight all stocks
  3. Rotation: Top N momentum + bear protection

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

# Config
TOTAL_CAPITAL = 70000
ROTATION_SLOTS = 5  # Hold top 5 momentum stocks
MOMENTUM_LOOKBACK = 20  # 20 trading days


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
    """Load all available symbols."""
    data = {}
    files = list(DATA_DIR.glob("*_1d.parquet"))

    for f in files:
        symbol = f.stem.replace("_1d", "")
        try:
            df = pl.read_parquet(f).sort("timestamp")
            deriv_cols = ["close_velocity_zscore", "close_acceleration_zscore",
                          "close_jerk_zscore", "ADX_14_jerk_zscore"]
            actual = [c for c in deriv_cols if c in df.columns or c.lower() in df.columns]

            data[symbol] = {
                "df": df,
                "rows": df.to_dicts(),
                "deriv_cols": actual,
            }
        except Exception as e:
            print(f"  Skip {symbol}: {e}")

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

    return MarketState(
        time=ts, symbol=symbol,
        tf_1h_vel=get_val("velocity"),
        tf_1h_acc=get_val("acceleration"),
        tf_1h_adx_jerk=get_val("adx"),
        tf_4h_vel=get_val("velocity"),
        tf_4h_acc=get_val("acceleration"),
        tf_4h_adx_jerk=get_val("adx"),
        tf_1d_vel=None, tf_1d_acc=None, tf_1d_adx_jerk=None,
    )


def run_backtest():
    print("="*80)
    print("LARGE-SCALE ROTATION BACKTEST - S&P 50 + DOW 30")
    print("="*80)
    print()

    if not DATA_DIR.exists():
        print(f"ERROR: Data not found at {DATA_DIR}")
        print("Run download_sp50_dow30.py first")
        return

    print("Loading data...")
    data = load_all_symbols()
    print(f"Loaded {len(data)} symbols")

    if len(data) < 10:
        print("ERROR: Need more symbols")
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
    years = len(common_ts) / 252
    print(f"Common trading days: {len(common_ts):,} ({years:.1f} years)")
    print(f"Date range: {common_ts[0]} to {common_ts[-1]}")

    # Build price series
    symbols = list(data.keys())
    prices = {sym: [] for sym in symbols}
    rows_by_ts = {sym: {row["timestamp"]: row for row in data[sym]["rows"]} for sym in symbols}

    for ts in common_ts:
        for sym in symbols:
            row = rows_by_ts[sym].get(ts)
            if row and row.get("close"):
                prices[sym].append(row["close"])
            else:
                prices[sym].append(prices[sym][-1] if prices[sym] else 0)

    services = {sym: BearProtectionService() for sym in symbols}

    # =========================================================================
    # STRATEGY 1: SPY Buy & Hold
    # =========================================================================
    if "SPY" in prices and prices["SPY"][0] > 0:
        spy_shares = TOTAL_CAPITAL / prices["SPY"][0]
        spy_equity = [TOTAL_CAPITAL]
        spy_returns = []
    else:
        spy_equity = None

    # =========================================================================
    # STRATEGY 2: Equal Weight Buy & Hold
    # =========================================================================
    ew_per_stock = TOTAL_CAPITAL / len(symbols)
    ew_shares = {sym: ew_per_stock / prices[sym][0] if prices[sym][0] > 0 else 0 for sym in symbols}
    ew_equity = [TOTAL_CAPITAL]
    ew_returns = []

    # =========================================================================
    # STRATEGY 3: Rotation (Top N momentum + bear protection)
    # =========================================================================
    rot_equity = [TOTAL_CAPITAL]
    rot_returns = []
    rot_holdings = []
    rot_trades = 0

    warmup = MOMENTUM_LOOKBACK + 1
    print(f"\nBacktesting {len(common_ts) - warmup:,} days with {ROTATION_SLOTS} rotation slots...")

    for i in range(warmup, len(common_ts)):
        ts = common_ts[i]

        # SPY
        if spy_equity is not None:
            spy_value = spy_shares * prices["SPY"][i]
            prev = spy_equity[-1]
            spy_equity.append(spy_value)
            if prev > 0:
                spy_returns.append((spy_value - prev) / prev)

        # Equal Weight
        ew_value = sum(ew_shares[sym] * prices[sym][i] for sym in symbols)
        prev = ew_equity[-1]
        ew_equity.append(ew_value)
        if prev > 0:
            ew_returns.append((ew_value - prev) / prev)

        # Rotation
        momentum = {}
        regimes = {}
        for sym in symbols:
            momentum[sym] = compute_momentum(prices[sym][:i+1], MOMENTUM_LOOKBACK)
            row = rows_by_ts[sym].get(ts, {})
            state = row_to_market_state(row, sym, data[sym]["deriv_cols"])
            regimes[sym] = services[sym].evaluate(state).regime

        # Rank by momentum, exclude DEFENSIVE
        ranked = sorted(
            [(sym, mom) for sym, mom in momentum.items() if regimes[sym] != Regime.DEFENSIVE],
            key=lambda x: -x[1]
        )

        target_symbols = [sym for sym, _ in ranked[:ROTATION_SLOTS]]

        # Check rotation needed
        need_rotation = not rot_holdings
        for sym, shares in rot_holdings:
            if regimes[sym] == Regime.DEFENSIVE:
                need_rotation = True
                break

        if need_rotation:
            current_value = sum(shares * prices[sym][i] for sym, shares in rot_holdings) if rot_holdings else TOTAL_CAPITAL
            new_holdings = []
            per_slot = current_value / ROTATION_SLOTS
            for sym in target_symbols:
                shares = per_slot / prices[sym][i] if prices[sym][i] > 0 else 0
                new_holdings.append((sym, shares))

            current_symbols = [h[0] for h in rot_holdings]
            if rot_holdings and set(current_symbols) != set(target_symbols):
                rot_trades += 1

            rot_holdings = new_holdings

        rot_value = sum(shares * prices[sym][i] for sym, shares in rot_holdings)
        prev = rot_equity[-1]
        rot_equity.append(rot_value)
        if prev > 0:
            rot_returns.append((rot_value - prev) / prev)

    # =========================================================================
    # RESULTS
    # =========================================================================
    print()
    print("="*80)
    print("RESULTS")
    print("="*80)
    print()

    print(f"{'STRATEGY':<35} {'Final':>14} {'ROI':>10} {'CAGR':>8} {'Sortino':>9} {'MaxDD':>9}")
    print("-"*90)

    # SPY
    if spy_equity:
        spy_roi = (spy_equity[-1] / TOTAL_CAPITAL - 1) * 100
        spy_cagr = ((spy_equity[-1] / TOTAL_CAPITAL) ** (1/years) - 1) * 100
        spy_sortino = compute_sortino(spy_returns)
        spy_maxdd = compute_max_drawdown(spy_equity)
        print(f"{'SPY Buy & Hold':<35} ${spy_equity[-1]:>12,.0f} {spy_roi:>+9.1f}% {spy_cagr:>+7.1f}% {spy_sortino:>8.2f} {spy_maxdd:>8.1f}%")

    # Equal Weight
    ew_roi = (ew_equity[-1] / TOTAL_CAPITAL - 1) * 100
    ew_cagr = ((ew_equity[-1] / TOTAL_CAPITAL) ** (1/years) - 1) * 100
    ew_sortino = compute_sortino(ew_returns)
    ew_maxdd = compute_max_drawdown(ew_equity)
    print(f"{'Equal Weight ({0} stocks)':<35} ${ew_equity[-1]:>12,.0f} {ew_roi:>+9.1f}% {ew_cagr:>+7.1f}% {ew_sortino:>8.2f} {ew_maxdd:>8.1f}%".format(len(symbols)))

    # Rotation
    rot_roi = (rot_equity[-1] / TOTAL_CAPITAL - 1) * 100
    rot_cagr = ((rot_equity[-1] / TOTAL_CAPITAL) ** (1/years) - 1) * 100
    rot_sortino = compute_sortino(rot_returns)
    rot_maxdd = compute_max_drawdown(rot_equity)
    print(f"{'Rotation (Top {0} + BP)':<35} ${rot_equity[-1]:>12,.0f} {rot_roi:>+9.1f}% {rot_cagr:>+7.1f}% {rot_sortino:>8.2f} {rot_maxdd:>8.1f}%".format(ROTATION_SLOTS))

    print()
    print(f"Rotation trades: {rot_trades}")
    print(f"Current holdings: {[h[0] for h in rot_holdings]}")

    # Verdict
    print()
    print("="*80)
    print("VERDICT")
    print("="*80)
    best_roi = max(spy_roi if spy_equity else 0, ew_roi, rot_roi)
    best_dd = min(spy_maxdd if spy_equity else 100, ew_maxdd, rot_maxdd)

    if rot_roi == best_roi:
        print(f"\n  [ROTATION WINS ROI] +{rot_roi:.1f}% vs SPY {spy_roi:.1f}%")
    if rot_maxdd == best_dd:
        print(f"  [ROTATION WINS RISK] {rot_maxdd:.1f}% max DD vs SPY {spy_maxdd:.1f}%")


if __name__ == "__main__":
    run_backtest()
