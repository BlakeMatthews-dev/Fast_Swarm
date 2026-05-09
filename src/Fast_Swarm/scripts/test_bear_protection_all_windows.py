"""
Test Bear Protection on ALL 10 Canonical Windows.

Comprehensive comparison of Hold strategy WITH vs WITHOUT bear protection
across every defined test period.
"""

import polars as pl
from pathlib import Path
from datetime import datetime, timezone
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from Fast_Swarm.Infrastructure.Services.bear_protection_service import (
    BearProtectionService, MarketState, Regime
)

# Import canonical windows directly
import importlib.util
spec = importlib.util.spec_from_file_location(
    "canonical_windows",
    Path(__file__).parent.parent / "Tests" / "Fixtures" / "canonical_windows.py"
)
canonical_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(canonical_mod)
CANONICAL_WINDOWS = canonical_mod.CANONICAL_WINDOWS

DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")


def load_mtf_for_period(symbol: str, start: datetime, end: datetime):
    """Load MTF derivatives data for a specific time period."""
    base_path = DERIVATIVES_DIR / f"symbol={symbol}"

    if not base_path.exists():
        return None

    try:
        df_1h = pl.read_parquet(base_path / "timeframe=1h").sort("time")
        df_4h = pl.read_parquet(base_path / "timeframe=4h").sort("time")
        df_1d = pl.read_parquet(base_path / "timeframe=1d").sort("time")
    except Exception as e:
        print(f"  Error loading data for {symbol}: {e}")
        return None

    start_tz = start.replace(tzinfo=timezone.utc)
    end_tz = end.replace(tzinfo=timezone.utc)

    df_1h = df_1h.filter(
        (pl.col("time") >= start_tz) & (pl.col("time") <= end_tz)
    )

    if len(df_1h) == 0:
        return None

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


def simulate_hold(df, symbol: str, use_bear_protection: bool = False):
    """
    Simulate holding asset WITH or WITHOUT bear protection.

    WITHOUT bear protection:
        - Always 100% in asset

    WITH bear protection:
        - DEFENSIVE: 0% (full exit to USD)
        - NEUTRAL: 50% in asset
        - AGGRESSIVE: 85% in asset
    """
    rows = df.to_dicts()

    if use_bear_protection:
        service = BearProtectionService()

    # Start with 1 unit of asset
    asset_holdings = 1.0
    usd_holdings = 0.0
    start_price = rows[0].get("close", 1)

    equity_curve = []
    trades = 0
    last_regime = None

    # Track drawdown
    peak = start_price
    max_dd = 0

    for row in rows:
        price = row.get("close", 0)
        if price <= 0:
            continue

        if use_bear_protection:
            state = row_to_market_state(row, symbol)
            result = service.evaluate(state)
            regime = result.regime
            max_position = result.max_position

            # Regime change - adjust position
            if regime != last_regime:
                total_value = asset_holdings * price + usd_holdings
                target_asset_value = total_value * max_position
                target_asset = target_asset_value / price

                if regime == Regime.DEFENSIVE and last_regime != Regime.DEFENSIVE:
                    # Sell asset for USD
                    asset_sold = asset_holdings - target_asset
                    if asset_sold > 0:
                        usd_holdings += asset_sold * price
                        asset_holdings = target_asset
                        trades += 1

                elif regime == Regime.AGGRESSIVE and last_regime != Regime.AGGRESSIVE:
                    # Buy asset with USD
                    if usd_holdings > 0:
                        asset_bought = usd_holdings / price
                        asset_holdings += asset_bought
                        usd_holdings = 0
                        trades += 1

                elif regime == Regime.NEUTRAL and last_regime == Regime.DEFENSIVE:
                    # Partial re-entry
                    if usd_holdings > 0:
                        target_usd = total_value * (1 - max_position)
                        usd_to_spend = usd_holdings - target_usd
                        if usd_to_spend > 0:
                            asset_bought = usd_to_spend / price
                            asset_holdings += asset_bought
                            usd_holdings = target_usd
                            trades += 1

                last_regime = regime

        # Calculate equity
        total_equity = asset_holdings * price + usd_holdings

        # Track drawdown
        if total_equity > peak:
            peak = total_equity
        dd = (peak - total_equity) / peak
        if dd > max_dd:
            max_dd = dd

        equity_curve.append(total_equity)

    if not equity_curve:
        return None

    start_equity = start_price
    end_equity = equity_curve[-1]
    end_price = rows[-1].get("close", start_price)

    bh_return = (end_price / start_price - 1) * 100
    strategy_return = (end_equity / start_equity - 1) * 100

    return {
        "bh_return": bh_return,
        "strategy_return": strategy_return,
        "max_dd": max_dd * 100,
        "trades": trades,
    }


def main():
    print("=" * 100)
    print("BEAR PROTECTION TEST: ALL 10 CANONICAL WINDOWS")
    print("=" * 100)
    print("\nRegime Limits: DEFENSIVE=0%, NEUTRAL=50%, AGGRESSIVE=85%")
    print("Exit Signal: vel>0.5 AND acc<-1.5 AND adx_jerk<0")
    print("Entry Signal: vel<-1.5 AND acc>3.0")

    results = []

    for window_key, window in CANONICAL_WINDOWS.items():
        print(f"\n{'='*100}")
        print(f"{window.name}")
        print(f"  {window.description}")
        print(f"  Period: {window.start.date()} to {window.end.date()}")
        print("=" * 100)

        # Determine symbol
        if window.asset == "*":
            symbol = "BTC"  # Default for multi-asset
        else:
            symbol = window.asset.split("/")[0]  # "BTC/USDT" -> "BTC"

        # Load data
        df = load_mtf_for_period(symbol, window.start, window.end)

        if df is None or len(df) == 0:
            print(f"  [!] No data available for this period")
            continue

        print(f"  Loaded {len(df):,} candles for {symbol}")

        # Run WITHOUT bear protection
        result_no_bp = simulate_hold(df, symbol, use_bear_protection=False)

        # Run WITH bear protection
        result_with_bp = simulate_hold(df, symbol, use_bear_protection=True)

        if result_no_bp and result_with_bp:
            protection_value = result_with_bp['strategy_return'] - result_no_bp['strategy_return']
            dd_reduction = result_no_bp['max_dd'] - result_with_bp['max_dd']

            print(f"\n  {'Metric':<20} {'No Protection':>15} {'With Protection':>15} {'Delta':>15}")
            print("  " + "-" * 70)
            print(f"  {'Buy & Hold'::<20} {result_no_bp['bh_return']:>14.1f}%")
            print(f"  {'Strategy Return':<20} {result_no_bp['strategy_return']:>14.1f}% {result_with_bp['strategy_return']:>14.1f}% {protection_value:>+14.1f}%")
            print(f"  {'Max Drawdown':<20} {result_no_bp['max_dd']:>14.1f}% {result_with_bp['max_dd']:>14.1f}% {-dd_reduction:>+14.1f}%")
            print(f"  {'Trades':<20} {result_no_bp['trades']:>15} {result_with_bp['trades']:>15}")

            # Classify window type
            is_crash = any(x in window_key for x in ["crash", "collapse", "bear"])
            is_bull = "bull" in window_key

            results.append({
                "window": window_key,
                "name": window.name,
                "symbol": symbol,
                "type": "crash" if is_crash else ("bull" if is_bull else "neutral"),
                "candles": len(df),
                "bh_return": result_no_bp['bh_return'],
                "no_bp_return": result_no_bp['strategy_return'],
                "with_bp_return": result_with_bp['strategy_return'],
                "no_bp_dd": result_no_bp['max_dd'],
                "with_bp_dd": result_with_bp['max_dd'],
                "protection_value": protection_value,
                "dd_reduction": dd_reduction,
                "trades": result_with_bp['trades'],
            })

    # Summary
    print("\n" + "=" * 100)
    print("SUMMARY: All 10 Canonical Windows")
    print("=" * 100)

    if results:
        print(f"\n{'Window':<25} {'Type':<8} {'B&H':>10} {'No BP':>10} {'With BP':>10} {'Protection':>12} {'DD Saved':>10}")
        print("-" * 95)

        total_protection = 0
        total_dd_saved = 0
        crash_protection = 0
        crash_dd_saved = 0
        crash_count = 0
        bull_protection = 0
        bull_count = 0

        for r in results:
            marker = "[C]" if r["type"] == "crash" else ("[B]" if r["type"] == "bull" else "[ ]")
            print(f"{marker} {r['window']:<22} {r['type']:<8} {r['bh_return']:>9.1f}% {r['no_bp_return']:>9.1f}% {r['with_bp_return']:>9.1f}% {r['protection_value']:>+11.1f}% {r['dd_reduction']:>+9.1f}%")

            total_protection += r['protection_value']
            total_dd_saved += r['dd_reduction']

            if r['type'] == 'crash':
                crash_protection += r['protection_value']
                crash_dd_saved += r['dd_reduction']
                crash_count += 1
            elif r['type'] == 'bull':
                bull_protection += r['protection_value']
                bull_count += 1

        print("-" * 95)
        print(f"{'TOTAL':<35} {'':<8} {'':<10} {'':<10} {total_protection:>+11.1f}% {total_dd_saved:>+9.1f}%")

        print("\n" + "=" * 100)
        print("BREAKDOWN BY MARKET TYPE")
        print("=" * 100)

        if crash_count > 0:
            print(f"\n[C] CRASH PERIODS ({crash_count}):")
            print(f"    Total Protection Value: {crash_protection:+.1f}%")
            print(f"    Average Protection: {crash_protection/crash_count:+.1f}%")
            print(f"    Total Drawdown Saved: {crash_dd_saved:+.1f}%")

        if bull_count > 0:
            print(f"\n[B] BULL PERIODS ({bull_count}):")
            print(f"    Total Protection Value: {bull_protection:+.1f}%")
            print(f"    Average: {bull_protection/bull_count:+.1f}%")

        neutral_count = len(results) - crash_count - bull_count
        if neutral_count > 0:
            neutral_protection = total_protection - crash_protection - bull_protection
            print(f"\n[ ] NEUTRAL/MIXED PERIODS ({neutral_count}):")
            print(f"    Total Protection Value: {neutral_protection:+.1f}%")

        print("\n" + "=" * 100)
        print("CONCLUSION")
        print("=" * 100)

        if total_protection > 0:
            print(f"\n[OK] Bear Protection provided NET POSITIVE value: {total_protection:+.1f}%")
            print(f"     Total drawdown reduction: {total_dd_saved:+.1f}%")
            if crash_count > 0 and crash_protection > 0:
                print(f"\n     Especially effective during crashes:")
                print(f"       - Saved {crash_protection:.1f}% during {crash_count} crash periods")
                print(f"       - Reduced drawdowns by {crash_dd_saved:.1f}% average")
        else:
            print(f"\n[!!] Bear Protection had NET NEGATIVE value: {total_protection:+.1f}%")
            print("     Consider adjusting thresholds.")


if __name__ == "__main__":
    main()
