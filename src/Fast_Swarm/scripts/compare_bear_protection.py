"""
Compare Agent Performance WITH vs WITHOUT Bear Protection.

Tests an aggressive long-only agent on canonical crash periods:
- Flash Crash May 2021 (50% drop in 48 hours)
- Luna Collapse (UST death spiral)
- FTX Collapse (exchange run)
- 2022 Bear Market (full bear cycle)

Key: Agent DEFAULTS TO HOLDING BTC (not USD).
Bear protection forces exits during crashes, then re-enters on opportunity.
"""

import polars as pl
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from Fast_Swarm.Infrastructure.Services.bear_protection_service import (
    BearProtectionService, MarketState, Regime
)

# Import canonical windows directly to avoid __init__.py import issues
import importlib.util
spec = importlib.util.spec_from_file_location(
    "canonical_windows",
    Path(__file__).parent.parent / "Tests" / "Fixtures" / "canonical_windows.py"
)
canonical_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(canonical_mod)
CANONICAL_WINDOWS = canonical_mod.CANONICAL_WINDOWS
get_stress_windows = canonical_mod.get_stress_windows

DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")


def load_mtf_for_period(symbol: str, start: datetime, end: datetime):
    """Load MTF derivatives data for a specific time period."""
    base_path = DERIVATIVES_DIR / f"symbol={symbol}"

    df_1h = pl.read_parquet(base_path / "timeframe=1h").sort("time")
    df_4h = pl.read_parquet(base_path / "timeframe=4h").sort("time")
    df_1d = pl.read_parquet(base_path / "timeframe=1d").sort("time")

    # Filter to period
    start_tz = start.replace(tzinfo=timezone.utc)
    end_tz = end.replace(tzinfo=timezone.utc)

    df_1h = df_1h.filter(
        (pl.col("time") >= start_tz) & (pl.col("time") <= end_tz)
    )

    if len(df_1h) == 0:
        return None

    # Join MTF data
    cols = ["close_velocity_zscore", "close_acceleration_zscore", "adx_14_jerk_zscore"]

    df_4h_join = df_4h.select(
        [pl.col("time").alias("tf_4h_time")]
        + [pl.col(c).alias(f"tf_4h_{c}") for c in cols if c in df_4h.columns]
    )
    df_1d_join = df_1d.select(
        [pl.col("time").alias("tf_1d_time")]
        + [pl.col(c).alias(f"tf_1d_{c}") for c in cols if c in df_1d.columns]
    )

    result = df_1h.join_asof(df_4h_join, left_on="time", right_on="tf_4h_time", strategy="backward")
    result = result.join_asof(df_1d_join, left_on="time", right_on="tf_1d_time", strategy="backward")

    for c in cols:
        if c in result.columns:
            result = result.rename({c: f"tf_1h_{c}"})

    return result


def row_to_market_state(row: dict, symbol: str) -> MarketState:
    """Convert dataframe row to MarketState."""
    return MarketState(
        time=row.get("time", datetime.now(timezone.utc)),
        symbol=symbol,
        tf_1h_vel=row.get("tf_1h_close_velocity_zscore"),
        tf_1h_acc=row.get("tf_1h_close_acceleration_zscore"),
        tf_1h_adx_jerk=row.get("tf_1h_adx_14_jerk_zscore"),
        tf_4h_vel=row.get("tf_4h_close_velocity_zscore"),
        tf_4h_acc=row.get("tf_4h_close_acceleration_zscore"),
        tf_4h_adx_jerk=row.get("tf_4h_adx_14_jerk_zscore"),
        tf_1d_vel=row.get("tf_1d_close_velocity_zscore"),
        tf_1d_acc=row.get("tf_1d_close_acceleration_zscore"),
        tf_1d_adx_jerk=row.get("tf_1d_adx_14_jerk_zscore"),
    )


def simulate_hold_btc(df, use_bear_protection: bool = False):
    """
    Simulate an agent that DEFAULTS TO HOLDING BTC.

    WITHOUT bear protection:
        - Always 100% in BTC
        - Takes full crash damage

    WITH bear protection:
        - 100% in BTC during AGGRESSIVE
        - 50% in BTC during NEUTRAL
        - 25% in BTC during DEFENSIVE (75% in USD)
        - Re-enters fully on AGGRESSIVE signal
    """
    rows = df.to_dicts()

    if use_bear_protection:
        service = BearProtectionService()

    # Track equity
    btc_holdings = 1.0  # Start with 1 BTC worth
    usd_holdings = 0.0
    start_price = rows[0].get("close", 1)

    equity_curve = []
    regime_history = []
    trades = []
    last_regime = None

    for i, row in enumerate(rows):
        price = row.get("close", 0)
        if price <= 0:
            continue

        if use_bear_protection:
            state = row_to_market_state(row, "BTC")
            result = service.evaluate(state)
            regime = result.regime
            max_position = result.max_position

            # Regime change - adjust position
            if regime != last_regime:
                total_value = btc_holdings * price + usd_holdings

                # Target BTC allocation based on regime
                target_btc_value = total_value * max_position
                target_btc = target_btc_value / price

                if regime == Regime.DEFENSIVE and last_regime != Regime.DEFENSIVE:
                    # Entering DEFENSIVE - sell BTC for USD
                    btc_sold = btc_holdings - target_btc
                    if btc_sold > 0:
                        usd_holdings += btc_sold * price
                        btc_holdings = target_btc
                        trades.append({
                            "time": row.get("time"),
                            "action": "SELL",
                            "amount": btc_sold,
                            "price": price,
                            "reason": "bear_protection_defensive",
                        })

                elif regime == Regime.AGGRESSIVE and last_regime != Regime.AGGRESSIVE:
                    # Entering AGGRESSIVE - buy BTC with USD
                    if usd_holdings > 0:
                        btc_bought = usd_holdings / price
                        btc_holdings += btc_bought
                        trades.append({
                            "time": row.get("time"),
                            "action": "BUY",
                            "amount": btc_bought,
                            "price": price,
                            "reason": "bear_protection_aggressive",
                        })
                        usd_holdings = 0

                last_regime = regime
                regime_history.append({"time": row.get("time"), "regime": regime.value})
        else:
            regime = None
            max_position = 1.0  # Always 100% BTC

        # Calculate equity
        total_equity = btc_holdings * price + usd_holdings
        equity_curve.append({
            "time": row.get("time"),
            "price": price,
            "equity": total_equity,
            "btc_holdings": btc_holdings,
            "usd_holdings": usd_holdings,
            "regime": regime.value if regime else "HOLD_BTC",
        })

    # Calculate metrics
    if not equity_curve:
        return None

    start_equity = start_price  # Started with 1 BTC worth
    end_equity = equity_curve[-1]["equity"]

    # Buy and hold comparison
    end_price = rows[-1].get("close", start_price)
    bh_return = (end_price / start_price - 1) * 100

    strategy_return = (end_equity / start_equity - 1) * 100

    # Max drawdown
    peak = start_equity
    max_dd = 0
    for eq in equity_curve:
        if eq["equity"] > peak:
            peak = eq["equity"]
        dd = (peak - eq["equity"]) / peak
        if dd > max_dd:
            max_dd = dd

    return {
        "start_price": start_price,
        "end_price": end_price,
        "bh_return": bh_return,
        "strategy_return": strategy_return,
        "max_dd": max_dd * 100,
        "trades": len(trades),
        "regime_changes": len(regime_history),
        "final_btc": btc_holdings,
        "final_usd": usd_holdings,
        "equity_curve": equity_curve,
    }


def main():
    print("=" * 100)
    print("BEAR PROTECTION COMPARISON: Hold BTC Strategy")
    print("Agent defaults to HOLDING BTC - bear protection forces exits during crashes")
    print("=" * 100)

    # Test periods - focus on crashes
    test_periods = [
        ("flash_crash_may2021", "Flash Crash May 2021", "50% drop in 48 hours"),
        ("luna_collapse", "Luna Collapse", "UST death spiral"),
        ("ftx_collapse", "FTX Collapse", "Exchange run"),
        ("btc_2022_bear", "2022 Bear Market", "Full bear cycle"),
        ("btc_2021_bull", "2021 Bull Run", "Control - should underperform"),
    ]

    results = []

    for period_key, period_name, description in test_periods:
        window = CANONICAL_WINDOWS.get(period_key)
        if not window:
            print(f"\nSkipping {period_key} - not found")
            continue

        print(f"\n{'=' * 100}")
        print(f"{period_name}: {description}")
        print(f"Period: {window.start} to {window.end}")
        print("=" * 100)

        # Load data
        symbol = "BTC" if "btc" in period_key.lower() or period_key in ["flash_crash_may2021", "luna_collapse", "ftx_collapse"] else "ETH"
        df = load_mtf_for_period(symbol, window.start, window.end)

        if df is None or len(df) == 0:
            print(f"  No data for period")
            continue

        print(f"  Loaded {len(df):,} hourly candles")

        # Run WITHOUT bear protection
        result_no_bp = simulate_hold_btc(df, use_bear_protection=False)

        # Run WITH bear protection
        result_with_bp = simulate_hold_btc(df, use_bear_protection=True)

        if result_no_bp and result_with_bp:
            print(f"\n  {'Metric':<25} {'No Protection':>15} {'With Protection':>15} {'Delta':>15}")
            print("  " + "-" * 75)
            print(f"  {'Buy & Hold Return':<25} {result_no_bp['bh_return']:>14.1f}% {result_with_bp['bh_return']:>14.1f}%")
            print(f"  {'Strategy Return':<25} {result_no_bp['strategy_return']:>14.1f}% {result_with_bp['strategy_return']:>14.1f}% {result_with_bp['strategy_return'] - result_no_bp['strategy_return']:>+14.1f}%")
            print(f"  {'Max Drawdown':<25} {result_no_bp['max_dd']:>14.1f}% {result_with_bp['max_dd']:>14.1f}% {result_with_bp['max_dd'] - result_no_bp['max_dd']:>+14.1f}%")
            print(f"  {'Trades':<25} {result_no_bp['trades']:>15} {result_with_bp['trades']:>15}")
            print(f"  {'Regime Changes':<25} {result_no_bp['regime_changes']:>15} {result_with_bp['regime_changes']:>15}")

            # Calculate protection value
            protection_value = result_with_bp['strategy_return'] - result_no_bp['strategy_return']
            dd_reduction = result_no_bp['max_dd'] - result_with_bp['max_dd']

            print(f"\n  PROTECTION VALUE: {protection_value:+.1f}% return improvement")
            print(f"  DRAWDOWN REDUCTION: {dd_reduction:+.1f}% less drawdown")

            results.append({
                "period": period_name,
                "bh_return": result_no_bp['bh_return'],
                "no_bp_return": result_no_bp['strategy_return'],
                "with_bp_return": result_with_bp['strategy_return'],
                "no_bp_dd": result_no_bp['max_dd'],
                "with_bp_dd": result_with_bp['max_dd'],
                "protection_value": protection_value,
                "dd_reduction": dd_reduction,
            })

    # Summary
    print("\n" + "=" * 100)
    print("SUMMARY: Bear Protection Impact Across All Periods")
    print("=" * 100)

    if results:
        print(f"\n{'Period':<25} {'B&H':>10} {'No BP':>10} {'With BP':>10} {'Protection':>12} {'DD Saved':>10}")
        print("-" * 85)

        total_protection = 0
        total_dd_saved = 0
        crash_protection = 0
        crash_dd_saved = 0
        crash_count = 0

        for r in results:
            is_crash = "bull" not in r["period"].lower()
            marker = "*" if is_crash else " "
            print(f"{marker}{r['period']:<24} {r['bh_return']:>9.1f}% {r['no_bp_return']:>9.1f}% {r['with_bp_return']:>9.1f}% {r['protection_value']:>+11.1f}% {r['dd_reduction']:>+9.1f}%")

            total_protection += r['protection_value']
            total_dd_saved += r['dd_reduction']

            if is_crash:
                crash_protection += r['protection_value']
                crash_dd_saved += r['dd_reduction']
                crash_count += 1

        print("-" * 85)
        print(f"{'TOTAL':<25} {'':<10} {'':<10} {'':<10} {total_protection:>+11.1f}% {total_dd_saved:>+9.1f}%")

        if crash_count > 0:
            print(f"\n* = Crash period")
            print(f"\nCRASH PERIODS ONLY ({crash_count}):")
            print(f"  Average Protection Value: {crash_protection/crash_count:+.1f}%")
            print(f"  Average DD Reduction: {crash_dd_saved/crash_count:+.1f}%")

        print("\n" + "=" * 100)
        print("CONCLUSION")
        print("=" * 100)

        if crash_protection > 0:
            print(f"\nBear protection SAVED {crash_protection:.1f}% during crash periods!")
            print(f"Drawdown reduced by {crash_dd_saved:.1f}% on average.")
            print("\nThe VETO EXIT POWER works as designed:")
            print("  - Detects momentum exhaustion (vel>0.5, acc<-1.5, adx_jerk<0)")
            print("  - Forces exit to 25% BTC position")
            print("  - Re-enters on opportunity signal (vel<-1.5, acc>3.0)")
        else:
            print("\nBear protection did not improve crash performance.")
            print("Review signal thresholds or period data.")


if __name__ == "__main__":
    main()
