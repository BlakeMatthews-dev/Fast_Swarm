"""
Threshold Grid Search: Find optimal DEFENSIVE signals per stock.

Tests multiple derivative combinations:
  - Velocity (1st derivative of price)
  - Acceleration (2nd derivative)
  - Jerk (3rd derivative)
  - Snap (4th derivative)
  - ADX Velocity
  - ADX Acceleration
  - ADX Jerk

Shows results per-stock to identify which signals work for which stocks.
"""

import sys
from pathlib import Path
from datetime import datetime
import statistics
from dataclasses import dataclass
from typing import Optional

import polars as pl

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from Fast_Swarm.Infrastructure.Services.bear_protection_service import (
    MarketState, Regime, RegimeConfig
)

DATA_DIR = PROJECT_ROOT / "data" / "test_data" / "SP50_DOW30"
CAPITAL = 1000

# Stock categories
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

# Threshold grid to test
VEL_THRESHOLDS = [0.5, 1.0, 1.5, 2.0]        # Higher = harder to trigger
ACC_THRESHOLDS = [-1.0, -1.5, -2.0, -2.5]    # More negative = harder to trigger
JERK_THRESHOLDS = [0.0, -0.5, -1.0]           # More negative = harder to trigger


class CustomBearProtection:
    """Bear protection with configurable thresholds."""

    def __init__(self, vel_thresh: float, acc_thresh: float, jerk_thresh: float):
        self.vel_thresh = vel_thresh
        self.acc_thresh = acc_thresh
        self.jerk_thresh = jerk_thresh
        self._current_regime = Regime.NEUTRAL

    def _check_exit_signal(self, vel, acc, jerk) -> bool:
        if vel is None or acc is None or jerk is None:
            return False
        return vel > self.vel_thresh and acc < self.acc_thresh and jerk < self.jerk_thresh

    def _check_entry_signal(self, vel, acc) -> bool:
        if vel is None or acc is None:
            return False
        return vel < -0.5 and acc > 1.5

    def evaluate(self, state: MarketState) -> Regime:
        exit_signals = 0
        entry_signals = 0

        for vel, acc, jerk in [
            (state.tf_1h_vel, state.tf_1h_acc, state.tf_1h_adx_jerk),
            (state.tf_4h_vel, state.tf_4h_acc, state.tf_4h_adx_jerk),
        ]:
            if self._check_exit_signal(vel, acc, jerk):
                exit_signals += 1
            if self._check_entry_signal(vel, acc):
                entry_signals += 1

        if exit_signals >= 2:
            self._current_regime = Regime.DEFENSIVE
        elif entry_signals >= 1:
            self._current_regime = Regime.AGGRESSIVE
        elif exit_signals == 0 and entry_signals == 0:
            self._current_regime = Regime.NEUTRAL

        return self._current_regime


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


def backtest_stock_with_thresholds(symbol: str, prices: list, rows_by_ts: dict,
                                    deriv_cols: list, common_ts: list,
                                    vel_t: float, acc_t: float, jerk_t: float) -> dict:
    """Run CTC v2 with custom thresholds."""
    service = CustomBearProtection(vel_t, acc_t, jerk_t)

    # B&H baseline
    bh_shares = CAPITAL / prices[0] if prices[0] > 0 else 0
    bh_equity = [CAPITAL]

    # CTC
    ctc_shares = CAPITAL / prices[0] if prices[0] > 0 else 0
    ctc_cash = 0.0
    ctc_in_cash = False
    ctc_equity = [CAPITAL]
    ctc_trades = 0

    warmup = 21
    for i in range(warmup, len(common_ts)):
        ts = common_ts[i]
        price = prices[i]

        bh_equity.append(bh_shares * price)

        row = rows_by_ts.get(ts, {})
        state = row_to_market_state(row, symbol, deriv_cols)
        regime = service.evaluate(state)

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

        ctc_equity.append(ctc_shares * price + ctc_cash)

    bh_roi = (bh_equity[-1] / CAPITAL - 1) * 100
    ctc_roi = (ctc_equity[-1] / CAPITAL - 1) * 100
    bh_dd = compute_max_drawdown(bh_equity)
    ctc_dd = compute_max_drawdown(ctc_equity)

    return {
        "bh_roi": bh_roi,
        "ctc_roi": ctc_roi,
        "roi_diff": ctc_roi - bh_roi,
        "bh_dd": bh_dd,
        "ctc_dd": ctc_dd,
        "dd_diff": ctc_dd - bh_dd,
        "trades": ctc_trades,
    }


def run_grid_search():
    print("="*100)
    print("THRESHOLD GRID SEARCH BY SECTOR")
    print("="*100)
    print()
    print("Testing different DEFENSIVE thresholds to find optimal settings per sector.")
    print()
    print(f"Velocity thresholds:     {VEL_THRESHOLDS}")
    print(f"Acceleration thresholds: {ACC_THRESHOLDS}")
    print(f"Jerk thresholds:         {JERK_THRESHOLDS}")
    print(f"Total combinations:      {len(VEL_THRESHOLDS) * len(ACC_THRESHOLDS) * len(JERK_THRESHOLDS)}")
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

    # Group by sector
    sectors = {}
    for sym in symbols:
        cat = CATEGORIES.get(sym, "Other")
        if cat not in sectors:
            sectors[cat] = []
        sectors[cat].append(sym)

    print(f"Sectors: {list(sectors.keys())}")
    print()

    # Grid search per sector
    sector_results = {}

    for sector, sector_symbols in sectors.items():
        print(f"Testing {sector} ({len(sector_symbols)} stocks)...", end=" ", flush=True)

        best_config = None
        best_avg_roi_diff = -999

        for vel_t in VEL_THRESHOLDS:
            for acc_t in ACC_THRESHOLDS:
                for jerk_t in JERK_THRESHOLDS:
                    roi_diffs = []
                    dd_diffs = []

                    for sym in sector_symbols:
                        r = backtest_stock_with_thresholds(
                            sym, prices[sym], rows_by_ts[sym],
                            data[sym]["deriv_cols"], common_ts,
                            vel_t, acc_t, jerk_t
                        )
                        roi_diffs.append(r["roi_diff"])
                        dd_diffs.append(r["dd_diff"])

                    avg_roi_diff = statistics.mean(roi_diffs)
                    avg_dd_diff = statistics.mean(dd_diffs)
                    win_pct = sum(1 for d in roi_diffs if d > 0) / len(roi_diffs) * 100

                    if avg_roi_diff > best_avg_roi_diff:
                        best_avg_roi_diff = avg_roi_diff
                        best_config = {
                            "vel": vel_t,
                            "acc": acc_t,
                            "jerk": jerk_t,
                            "avg_roi_diff": avg_roi_diff,
                            "avg_dd_diff": avg_dd_diff,
                            "win_pct": win_pct,
                        }

        sector_results[sector] = best_config
        print(f"Best: vel={best_config['vel']}, acc={best_config['acc']}, jerk={best_config['jerk']} -> {best_config['avg_roi_diff']:+.1f}% ROI")

    # Summary
    print()
    print("="*100)
    print("OPTIMAL THRESHOLDS BY SECTOR")
    print("="*100)
    print()
    print(f"{'Sector':<15} {'Vel':>8} {'Acc':>8} {'Jerk':>8} {'Avg ROI':>12} {'Avg DD':>12} {'Win%':>8}")
    print("-"*75)

    for sector in sorted(sector_results.keys()):
        r = sector_results[sector]
        print(f"{sector:<15} {r['vel']:>8.1f} {r['acc']:>8.1f} {r['jerk']:>8.1f} {r['avg_roi_diff']:>+11.1f}% {r['avg_dd_diff']:>+11.1f}% {r['win_pct']:>7.0f}%")

    # Compare to default crypto thresholds
    print()
    print("="*100)
    print("COMPARISON: Default Crypto Thresholds (vel=1.0, acc=-2.0, jerk=-0.5)")
    print("="*100)
    print()

    default_vel, default_acc, default_jerk = 1.0, -2.0, -0.5

    for sector, sector_symbols in sectors.items():
        roi_diffs = []
        for sym in sector_symbols:
            r = backtest_stock_with_thresholds(
                sym, prices[sym], rows_by_ts[sym],
                data[sym]["deriv_cols"], common_ts,
                default_vel, default_acc, default_jerk
            )
            roi_diffs.append(r["roi_diff"])

        default_roi = statistics.mean(roi_diffs)
        optimal = sector_results[sector]
        improvement = optimal["avg_roi_diff"] - default_roi

        print(f"{sector:<15}: Default {default_roi:>+6.1f}% -> Optimal {optimal['avg_roi_diff']:>+6.1f}% (improvement: {improvement:>+5.1f}%)")

    # High-growth vs value analysis
    print()
    print("="*100)
    print("INSIGHT: Sensitivity Patterns")
    print("="*100)
    print()

    # Group results by threshold characteristics
    tight_thresh = [s for s, r in sector_results.items() if r["vel"] >= 1.5]
    loose_thresh = [s for s, r in sector_results.items() if r["vel"] <= 0.5]

    print("Sectors needing TIGHT thresholds (less sensitive, fewer signals):")
    print(f"  {tight_thresh if tight_thresh else 'None'}")
    print()
    print("Sectors needing LOOSE thresholds (more sensitive, more signals):")
    print(f"  {loose_thresh if loose_thresh else 'None'}")


if __name__ == "__main__":
    run_grid_search()
