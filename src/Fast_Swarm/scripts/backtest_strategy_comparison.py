"""
Strategy Comparison Backtest

Compares multiple strategies on the same data:
  1. Buy & Hold (baseline)
  2. Crash-to-Cash v1 (sell DEFENSIVE, buy AGGRESSIVE)
  3. Crash-to-Cash v2 (sell DEFENSIVE, buy when NOT DEFENSIVE)
  4. SMA Crossover (50/200 golden/death cross)
  5. RSI Strategy (buy oversold, sell overbought)
  6. Trailing Stop (10% trailing stop, re-enter on recovery)

Each strategy starts with $1000 per asset.
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


def run_backtest():
    print("="*90)
    print("STRATEGY COMPARISON BACKTEST")
    print("="*90)
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
    # STRATEGY 2: CRASH-TO-CASH v1 (buy on AGGRESSIVE only)
    # ==========================================================================
    ctc1_shares = {sym: CAPITAL_PER_ASSET / prices[sym][0] if prices[sym][0] > 0 else 0 for sym in symbols}
    ctc1_cash = {sym: 0.0 for sym in symbols}
    ctc1_in_cash = {sym: False for sym in symbols}
    ctc1_equity = [total_capital]
    ctc1_returns = []
    ctc1_trades = 0

    # ==========================================================================
    # STRATEGY 3: CRASH-TO-CASH v2 (buy when NOT DEFENSIVE)
    # ==========================================================================
    ctc2_shares = {sym: CAPITAL_PER_ASSET / prices[sym][0] if prices[sym][0] > 0 else 0 for sym in symbols}
    ctc2_cash = {sym: 0.0 for sym in symbols}
    ctc2_in_cash = {sym: False for sym in symbols}
    ctc2_equity = [total_capital]
    ctc2_returns = []
    ctc2_trades = 0

    # ==========================================================================
    # STRATEGY 4: SMA CROSSOVER (50/200)
    # ==========================================================================
    sma_shares = {sym: CAPITAL_PER_ASSET / prices[sym][0] if prices[sym][0] > 0 else 0 for sym in symbols}
    sma_cash = {sym: 0.0 for sym in symbols}
    sma_in_cash = {sym: False for sym in symbols}
    sma_equity = [total_capital]
    sma_returns = []
    sma_trades = 0

    # ==========================================================================
    # STRATEGY 5: RSI (buy <30, sell >70)
    # ==========================================================================
    rsi_shares = {sym: CAPITAL_PER_ASSET / prices[sym][0] if prices[sym][0] > 0 else 0 for sym in symbols}
    rsi_cash = {sym: 0.0 for sym in symbols}
    rsi_in_cash = {sym: False for sym in symbols}
    rsi_equity = [total_capital]
    rsi_returns = []
    rsi_trades = 0

    # ==========================================================================
    # STRATEGY 6: TRAILING STOP (10% trailing, re-enter on 5% recovery)
    # ==========================================================================
    ts_shares = {sym: CAPITAL_PER_ASSET / prices[sym][0] if prices[sym][0] > 0 else 0 for sym in symbols}
    ts_cash = {sym: 0.0 for sym in symbols}
    ts_in_cash = {sym: False for sym in symbols}
    ts_peak = {sym: prices[sym][0] for sym in symbols}  # Track peak for trailing stop
    ts_exit_price = {sym: 0.0 for sym in symbols}  # Price we exited at
    ts_equity = [total_capital]
    ts_returns = []
    ts_trades = 0
    TRAILING_STOP_PCT = 0.10  # 10% trailing stop
    RECOVERY_PCT = 0.05  # 5% recovery to re-enter

    warmup = 201  # Need 200 days for SMA200
    print(f"\nBacktesting {len(common_ts) - warmup:,} days...")
    print("Strategies: B&H, CTC-v1, CTC-v2, SMA, RSI, TrailingStop")
    print()

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

        # Get regimes for all symbols (for CTC strategies)
        regimes = {}
        for sym in symbols:
            row = rows_by_ts[sym].get(ts, {})
            state = row_to_market_state(row, sym, data[sym]["deriv_cols"])
            regimes[sym] = services[sym].evaluate(state).regime

        # Process each symbol
        for sym in symbols:
            price = prices[sym][i]
            price_history = prices[sym][:i+1]
            regime = regimes[sym]

            # -----------------------------------------------------------------
            # CTC v1: Sell DEFENSIVE, Buy AGGRESSIVE
            # -----------------------------------------------------------------
            if regime == Regime.DEFENSIVE and ctc1_shares[sym] > 0:
                ctc1_cash[sym] = ctc1_shares[sym] * price
                ctc1_shares[sym] = 0
                ctc1_in_cash[sym] = True
                ctc1_trades += 1
            elif regime == Regime.AGGRESSIVE and ctc1_in_cash[sym] and ctc1_cash[sym] > 0:
                ctc1_shares[sym] = ctc1_cash[sym] / price if price > 0 else 0
                ctc1_cash[sym] = 0
                ctc1_in_cash[sym] = False
                ctc1_trades += 1

            # -----------------------------------------------------------------
            # CTC v2: Sell DEFENSIVE, Buy when NOT DEFENSIVE
            # -----------------------------------------------------------------
            if regime == Regime.DEFENSIVE and ctc2_shares[sym] > 0:
                ctc2_cash[sym] = ctc2_shares[sym] * price
                ctc2_shares[sym] = 0
                ctc2_in_cash[sym] = True
                ctc2_trades += 1
            elif regime != Regime.DEFENSIVE and ctc2_in_cash[sym] and ctc2_cash[sym] > 0:
                ctc2_shares[sym] = ctc2_cash[sym] / price if price > 0 else 0
                ctc2_cash[sym] = 0
                ctc2_in_cash[sym] = False
                ctc2_trades += 1

            # -----------------------------------------------------------------
            # SMA Crossover: 50 > 200 = buy, 50 < 200 = sell
            # -----------------------------------------------------------------
            sma50 = compute_sma(price_history, 50)
            sma200 = compute_sma(price_history, 200)
            if sma50 is not None and sma200 is not None:
                if sma50 < sma200 and sma_shares[sym] > 0:  # Death cross - sell
                    sma_cash[sym] = sma_shares[sym] * price
                    sma_shares[sym] = 0
                    sma_in_cash[sym] = True
                    sma_trades += 1
                elif sma50 > sma200 and sma_in_cash[sym] and sma_cash[sym] > 0:  # Golden cross - buy
                    sma_shares[sym] = sma_cash[sym] / price if price > 0 else 0
                    sma_cash[sym] = 0
                    sma_in_cash[sym] = False
                    sma_trades += 1

            # -----------------------------------------------------------------
            # RSI: < 30 = buy, > 70 = sell
            # -----------------------------------------------------------------
            rsi = compute_rsi(price_history, 14)
            if rsi is not None:
                if rsi > 70 and rsi_shares[sym] > 0:  # Overbought - sell
                    rsi_cash[sym] = rsi_shares[sym] * price
                    rsi_shares[sym] = 0
                    rsi_in_cash[sym] = True
                    rsi_trades += 1
                elif rsi < 30 and rsi_in_cash[sym] and rsi_cash[sym] > 0:  # Oversold - buy
                    rsi_shares[sym] = rsi_cash[sym] / price if price > 0 else 0
                    rsi_cash[sym] = 0
                    rsi_in_cash[sym] = False
                    rsi_trades += 1

            # -----------------------------------------------------------------
            # Trailing Stop: 10% from peak = sell, 5% recovery = buy
            # -----------------------------------------------------------------
            if ts_shares[sym] > 0:  # Currently holding
                # Update peak
                if price > ts_peak[sym]:
                    ts_peak[sym] = price
                # Check trailing stop
                stop_price = ts_peak[sym] * (1 - TRAILING_STOP_PCT)
                if price < stop_price:
                    ts_cash[sym] = ts_shares[sym] * price
                    ts_shares[sym] = 0
                    ts_in_cash[sym] = True
                    ts_exit_price[sym] = price
                    ts_trades += 1
            elif ts_in_cash[sym] and ts_cash[sym] > 0:  # In cash, waiting to re-enter
                # Check for recovery
                recovery_price = ts_exit_price[sym] * (1 + RECOVERY_PCT)
                if price > recovery_price:
                    ts_shares[sym] = ts_cash[sym] / price if price > 0 else 0
                    ts_cash[sym] = 0
                    ts_in_cash[sym] = False
                    ts_peak[sym] = price  # Reset peak
                    ts_trades += 1

        # Calculate equity for all strategies
        ctc1_value = sum(ctc1_shares[sym] * prices[sym][i] for sym in symbols) + sum(ctc1_cash.values())
        ctc2_value = sum(ctc2_shares[sym] * prices[sym][i] for sym in symbols) + sum(ctc2_cash.values())
        sma_value = sum(sma_shares[sym] * prices[sym][i] for sym in symbols) + sum(sma_cash.values())
        rsi_value = sum(rsi_shares[sym] * prices[sym][i] for sym in symbols) + sum(rsi_cash.values())
        ts_value = sum(ts_shares[sym] * prices[sym][i] for sym in symbols) + sum(ts_cash.values())

        for eq_list, val, ret_list in [
            (ctc1_equity, ctc1_value, ctc1_returns),
            (ctc2_equity, ctc2_value, ctc2_returns),
            (sma_equity, sma_value, sma_returns),
            (rsi_equity, rsi_value, rsi_returns),
            (ts_equity, ts_value, ts_returns),
        ]:
            prev = eq_list[-1]
            eq_list.append(val)
            if prev > 0:
                ret_list.append((val - prev) / prev)

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
        ("CTC v1 (AGGRESSIVE)", ctc1_equity, ctc1_returns, ctc1_trades),
        ("CTC v2 (non-DEFENSIVE)", ctc2_equity, ctc2_returns, ctc2_trades),
        ("SMA 50/200 Crossover", sma_equity, sma_returns, sma_trades),
        ("RSI 30/70", rsi_equity, rsi_returns, rsi_trades),
        ("Trailing Stop 10%", ts_equity, ts_returns, ts_trades),
    ]:
        roi = (equity[-1] / total_capital - 1) * 100
        cagr = ((equity[-1] / total_capital) ** (1/years) - 1) * 100
        sortino = compute_sortino(returns)
        maxdd = compute_max_drawdown(equity)
        results.append({
            "name": name,
            "final": equity[-1],
            "roi": roi,
            "cagr": cagr,
            "sortino": sortino,
            "maxdd": maxdd,
            "trades": trades,
        })

    # Sort by ROI
    results.sort(key=lambda x: -x["roi"])

    print(f"{'RANK':<5} {'STRATEGY':<25} {'Final':>14} {'ROI':>10} {'CAGR':>8} {'Sortino':>9} {'MaxDD':>9} {'Trades':>8}")
    print("-"*95)
    for i, r in enumerate(results):
        rank = i + 1
        print(f"{rank:<5} {r['name']:<25} ${r['final']:>12,.0f} {r['roi']:>+9.1f}% {r['cagr']:>+7.1f}% {r['sortino']:>8.2f} {r['maxdd']:>8.1f}% {r['trades']:>8}")

    # Best metrics
    print()
    print("="*90)
    print("BEST IN CLASS")
    print("="*90)
    best_roi = max(results, key=lambda x: x["roi"])
    best_sortino = max(results, key=lambda x: x["sortino"])
    best_dd = min(results, key=lambda x: x["maxdd"])

    print(f"  Best ROI:     {best_roi['name']} ({best_roi['roi']:+.1f}%)")
    print(f"  Best Sortino: {best_sortino['name']} ({best_sortino['sortino']:.2f})")
    print(f"  Best MaxDD:   {best_dd['name']} ({best_dd['maxdd']:.1f}%)")

    # Risk-adjusted comparison
    print()
    print("="*90)
    print("RISK-ADJUSTED ANALYSIS")
    print("="*90)
    bh_result = next(r for r in results if r["name"] == "Buy & Hold")
    print()
    for r in results:
        if r["name"] == "Buy & Hold":
            continue
        roi_diff = r["roi"] - bh_result["roi"]
        dd_diff = r["maxdd"] - bh_result["maxdd"]
        sortino_diff = r["sortino"] - bh_result["sortino"]

        wins = []
        if r["roi"] > bh_result["roi"]:
            wins.append("ROI")
        if r["maxdd"] < bh_result["maxdd"]:
            wins.append("DD")
        if r["sortino"] > bh_result["sortino"]:
            wins.append("Sortino")

        win_str = ", ".join(wins) if wins else "None"
        print(f"  {r['name']:<25} vs B&H: ROI {roi_diff:+.1f}%, DD {dd_diff:+.1f}%, Sortino {sortino_diff:+.2f}  [{win_str}]")

    print()
    print("="*90)


if __name__ == "__main__":
    run_backtest()
