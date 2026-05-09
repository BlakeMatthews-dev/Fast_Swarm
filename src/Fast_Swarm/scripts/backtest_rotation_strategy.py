"""
Momentum Rotation + Bear Protection Strategy Backtest

Compares:
  1. Buy & Hold: $70k split 7 ways ($10k each)
  2. Rotation Strategy: $35k in top 2 momentum assets, rotate on bear signals

Momentum Ranking: 20-period ROC (Rate of Change) z-scored
Rotation Rule: When bear protection triggers DEFENSIVE, rotate to next best

"""

import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import statistics

import polars as pl

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from Fast_Swarm.Infrastructure.Services.bear_protection_service import (
    BearProtectionService, MarketState, Regime
)


# =============================================================================
# CONFIGURATION
# =============================================================================

DATA_DIR = PROJECT_ROOT / "data" / "test_data" / "EQUITY_BASKET"
SYMBOLS = ["AAPL", "NVDA", "TSLA", "PLTR", "JPM", "XOM", "SPY"]
TF1, TF2 = "1h", "4h"

# Capital allocation
TOTAL_CAPITAL = 70000
BH_PER_ASSET = TOTAL_CAPITAL / len(SYMBOLS)  # $10k each
ROTATION_CAPITAL = 35000
ROTATION_SLOTS = 2  # Hold top 2 momentum assets
ROTATION_PER_SLOT = ROTATION_CAPITAL / ROTATION_SLOTS  # $17.5k each

# Momentum lookback (periods)
MOMENTUM_LOOKBACK = 20  # 20 hourly candles for momentum calc


# =============================================================================
# DATA LOADING
# =============================================================================

def load_all_symbols() -> dict:
    """Load all symbol data aligned by timestamp."""
    data = {}

    for symbol in SYMBOLS:
        path_tf1 = DATA_DIR / f"{symbol}_{TF1}.parquet"
        path_tf2 = DATA_DIR / f"{symbol}_{TF2}.parquet"

        if not path_tf1.exists():
            print(f"  WARNING: Missing {symbol} data")
            continue

        df1 = pl.read_parquet(path_tf1).sort("timestamp")
        df2 = pl.read_parquet(path_tf2).sort("timestamp") if path_tf2.exists() else None

        # Get derivative columns
        deriv_cols = ["close_velocity_zscore", "close_acceleration_zscore",
                      "close_jerk_zscore", "ADX_14_jerk_zscore"]

        tf1_cols = [c for c in deriv_cols if c in df1.columns or c.lower() in df1.columns]
        tf1_actual = [c if c in df1.columns else c.lower() for c in tf1_cols if c in df1.columns or c.lower() in df1.columns]

        tf2_cols = []
        tf2_actual = []
        if df2 is not None:
            tf2_cols = [c for c in deriv_cols if c in df2.columns or c.lower() in df2.columns]
            tf2_actual = [c if c in df2.columns else c.lower() for c in tf2_cols if c in df2.columns or c.lower() in df2.columns]

            # Join TF2
            tf2_select = [pl.col("timestamp").alias("tf2_time")]
            for c in tf2_actual:
                tf2_select.append(pl.col(c).alias(f"tf2_{c}"))
            df2_join = df2.select(tf2_select)
            df1 = df1.join_asof(df2_join, left_on="timestamp", right_on="tf2_time", strategy="backward")

        # Rename TF1 cols
        for c in tf1_actual:
            if c in df1.columns:
                df1 = df1.rename({c: f"tf1_{c}"})

        data[symbol] = {
            "df": df1,
            "rows": df1.to_dicts(),
            "tf1_cols": tf1_actual,
            "tf2_cols": tf2_actual,
        }

    return data


def compute_momentum(prices: list, lookback: int = 20) -> float:
    """Compute momentum as ROC (rate of change)."""
    if len(prices) < lookback + 1:
        return 0.0
    current = prices[-1]
    past = prices[-lookback - 1]
    if past <= 0:
        return 0.0
    return (current - past) / past


def row_to_market_state(row: dict, symbol: str, tf1_cols: list, tf2_cols: list) -> MarketState:
    """Convert row to MarketState."""
    ts = row.get("timestamp", datetime.now())

    def get_val(prefix, col_list, target):
        for c in col_list:
            if target.lower() in c.lower():
                key = f"{prefix}_{c}"
                if key in row:
                    return row[key]
        return None

    return MarketState(
        time=ts, symbol=symbol,
        tf_1h_vel=get_val("tf1", tf1_cols, "velocity"),
        tf_1h_acc=get_val("tf1", tf1_cols, "acceleration"),
        tf_1h_adx_jerk=get_val("tf1", tf1_cols, "adx"),
        tf_4h_vel=get_val("tf2", tf2_cols, "velocity"),
        tf_4h_acc=get_val("tf2", tf2_cols, "acceleration"),
        tf_4h_adx_jerk=get_val("tf2", tf2_cols, "adx"),
        tf_1d_vel=None, tf_1d_acc=None, tf_1d_adx_jerk=None,
    )


# =============================================================================
# METRICS
# =============================================================================

def compute_sortino(returns: list) -> float:
    if len(returns) < 10:
        return 0.0
    mean_ret = statistics.mean(returns)
    downside = [min(0, r) ** 2 for r in returns]
    downside_std = (sum(downside) / len(downside)) ** 0.5
    if downside_std == 0:
        return 0.0
    return (mean_ret / downside_std) * ((24 * 252) ** 0.5)


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


# =============================================================================
# BACKTEST
# =============================================================================

def run_backtest():
    """Run the full comparison backtest."""
    print("Loading data...")
    data = load_all_symbols()

    if len(data) < 2:
        print("ERROR: Need at least 2 symbols")
        return

    # Find common timestamps
    all_timestamps = None
    for symbol, sdata in data.items():
        ts_set = set(row["timestamp"] for row in sdata["rows"])
        if all_timestamps is None:
            all_timestamps = ts_set
        else:
            all_timestamps &= ts_set

    common_ts = sorted(all_timestamps)
    print(f"Common timestamps: {len(common_ts):,}")

    # Build aligned price series
    prices = {sym: [] for sym in data.keys()}
    rows_by_ts = {sym: {row["timestamp"]: row for row in data[sym]["rows"]} for sym in data.keys()}

    for ts in common_ts:
        for sym in data.keys():
            row = rows_by_ts[sym].get(ts)
            if row and row.get("close"):
                prices[sym].append(row["close"])
            else:
                prices[sym].append(prices[sym][-1] if prices[sym] else 0)

    # Initialize bear protection services
    services = {sym: BearProtectionService() for sym in data.keys()}

    # =========================================================================
    # BUY & HOLD STRATEGY
    # =========================================================================
    bh_shares = {sym: BH_PER_ASSET / prices[sym][0] if prices[sym][0] > 0 else 0 for sym in data.keys()}
    bh_equity = [TOTAL_CAPITAL]
    bh_returns = []

    # =========================================================================
    # ROTATION STRATEGY
    # =========================================================================
    rotation_equity = [ROTATION_CAPITAL]
    rotation_returns = []
    rotation_holdings = []  # List of (symbol, shares) tuples
    rotation_trades = 0

    # Initialize with top 2 momentum (use first MOMENTUM_LOOKBACK periods to warm up)
    warmup_end = MOMENTUM_LOOKBACK + 1

    print(f"\nRunning backtest over {len(common_ts):,} periods...")
    print(f"  Warmup period: {warmup_end} candles")
    print()

    for i in range(warmup_end, len(common_ts)):
        ts = common_ts[i]

        # ---------------------------------------------------------------------
        # BUY & HOLD: simple equity update
        # ---------------------------------------------------------------------
        bh_value = sum(bh_shares[sym] * prices[sym][i] for sym in data.keys())
        prev_bh = bh_equity[-1]
        bh_equity.append(bh_value)
        if prev_bh > 0:
            bh_returns.append((bh_value - prev_bh) / prev_bh)

        # ---------------------------------------------------------------------
        # ROTATION: momentum ranking + bear protection
        # ---------------------------------------------------------------------

        # 1. Compute momentum for each symbol
        momentum = {}
        for sym in data.keys():
            mom = compute_momentum(prices[sym][:i+1], MOMENTUM_LOOKBACK)
            momentum[sym] = mom

        # 2. Get bear protection regime for each symbol
        regimes = {}
        for sym in data.keys():
            row = rows_by_ts[sym].get(ts, {})
            state = row_to_market_state(row, sym, data[sym]["tf1_cols"], data[sym]["tf2_cols"])
            result = services[sym].evaluate(state)
            regimes[sym] = result.regime

        # 3. Rank by momentum (excluding DEFENSIVE assets)
        ranked = sorted(
            [(sym, mom) for sym, mom in momentum.items() if regimes[sym] != Regime.DEFENSIVE],
            key=lambda x: -x[1]  # Descending by momentum
        )

        # If not enough non-defensive assets, include neutrals
        if len(ranked) < ROTATION_SLOTS:
            # Add any remaining assets
            remaining = [sym for sym in data.keys() if sym not in [r[0] for r in ranked]]
            for sym in remaining:
                ranked.append((sym, momentum[sym]))

        # 4. Determine target holdings (top N by momentum, not DEFENSIVE)
        target_symbols = [sym for sym, _ in ranked[:ROTATION_SLOTS]]

        # 5. Check if we need to rotate
        current_symbols = [h[0] for h in rotation_holdings]

        need_rotation = False
        # Rotate if current holding goes DEFENSIVE
        for sym, shares in rotation_holdings:
            if regimes[sym] == Regime.DEFENSIVE:
                need_rotation = True
                break

        # Also rotate if significantly better momentum elsewhere (optional)
        # For now, just rotate on DEFENSIVE signal

        # 6. Execute rotation if needed
        if not rotation_holdings or need_rotation:
            # Liquidate current holdings
            current_value = sum(shares * prices[sym][i] for sym, shares in rotation_holdings) if rotation_holdings else ROTATION_CAPITAL

            # Buy new holdings
            new_holdings = []
            per_slot = current_value / ROTATION_SLOTS
            for sym in target_symbols:
                shares = per_slot / prices[sym][i] if prices[sym][i] > 0 else 0
                new_holdings.append((sym, shares))

            if rotation_holdings and set(current_symbols) != set(target_symbols):
                rotation_trades += 1

            rotation_holdings = new_holdings

        # 7. Calculate rotation equity
        rot_value = sum(shares * prices[sym][i] for sym, shares in rotation_holdings)
        prev_rot = rotation_equity[-1]
        rotation_equity.append(rot_value)
        if prev_rot > 0:
            rotation_returns.append((rot_value - prev_rot) / prev_rot)

    # =========================================================================
    # RESULTS
    # =========================================================================
    print("="*80)
    print("BACKTEST RESULTS")
    print("="*80)
    print()
    print(f"Period: {len(common_ts):,} hourly candles (~{len(common_ts)/24/30:.1f} months)")
    print(f"Rotation trades: {rotation_trades}")
    print()

    # Buy & Hold metrics
    bh_roi = (bh_equity[-1] / TOTAL_CAPITAL - 1) * 100
    bh_sortino = compute_sortino(bh_returns)
    bh_maxdd = compute_max_drawdown(bh_equity)

    # Rotation metrics
    rot_roi = (rotation_equity[-1] / ROTATION_CAPITAL - 1) * 100
    rot_sortino = compute_sortino(rotation_returns)
    rot_maxdd = compute_max_drawdown(rotation_equity)

    print(f"{'STRATEGY':<25} {'Capital':>12} {'Final':>12} {'ROI':>10} {'Sortino':>10} {'MaxDD':>10}")
    print("-"*80)
    print(f"{'Buy & Hold (7 assets)':<25} ${TOTAL_CAPITAL:>10,.0f} ${bh_equity[-1]:>10,.0f} {bh_roi:>+9.1f}% {bh_sortino:>9.2f} {bh_maxdd:>9.1f}%")
    print(f"{'Rotation (top 2 + BP)':<25} ${ROTATION_CAPITAL:>10,.0f} ${rotation_equity[-1]:>10,.0f} {rot_roi:>+9.1f}% {rot_sortino:>9.2f} {rot_maxdd:>9.1f}%")

    # Normalize to same capital for fair comparison
    print()
    print("NORMALIZED COMPARISON (same starting capital):")
    print("-"*80)
    bh_norm_final = TOTAL_CAPITAL * (1 + bh_roi/100)
    rot_norm_final = TOTAL_CAPITAL * (1 + rot_roi/100)  # Scale up rotation

    print(f"{'Buy & Hold (7 assets)':<25} ${TOTAL_CAPITAL:>10,.0f} ${bh_norm_final:>10,.0f} {bh_roi:>+9.1f}%")
    print(f"{'Rotation (scaled to 70k)':<25} ${TOTAL_CAPITAL:>10,.0f} ${rot_norm_final:>10,.0f} {rot_roi:>+9.1f}%")

    print()
    print("="*80)
    print("VERDICT")
    print("="*80)
    print()

    if rot_roi > bh_roi:
        print(f"  [ROTATION WINS] +{rot_roi - bh_roi:.1f}% more ROI")
    else:
        print(f"  [BUY & HOLD WINS] +{bh_roi - rot_roi:.1f}% more ROI")

    if rot_maxdd < bh_maxdd:
        print(f"  [ROTATION WINS] {bh_maxdd - rot_maxdd:.1f}% less drawdown")
    else:
        print(f"  [BUY & HOLD WINS] {rot_maxdd - bh_maxdd:.1f}% less drawdown")

    if rot_sortino > bh_sortino:
        print(f"  [ROTATION WINS] Better risk-adjusted returns (Sortino {rot_sortino:.2f} vs {bh_sortino:.2f})")
    else:
        print(f"  [BUY & HOLD WINS] Better risk-adjusted returns (Sortino {bh_sortino:.2f} vs {rot_sortino:.2f})")

    # Final holdings
    print()
    print("Final rotation holdings:")
    for sym, shares in rotation_holdings:
        value = shares * prices[sym][-1]
        print(f"  {sym}: {shares:.2f} shares = ${value:,.0f}")


if __name__ == "__main__":
    run_backtest()
