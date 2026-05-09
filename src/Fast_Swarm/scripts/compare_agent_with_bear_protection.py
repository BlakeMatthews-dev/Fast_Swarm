"""
Compare Agent Performance WITH vs WITHOUT Bear Protection.

Takes an actual agent from the database, runs backtests on canonical windows,
and compares performance with bear protection enabled vs disabled.
"""

import polars as pl
from pathlib import Path
from datetime import datetime, timezone
import sys
import os

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from Fast_Swarm.Infrastructure.Services.bear_protection_service import (
    BearProtectionService, MarketState, Regime, RegimeConfig
)

# Use PRODUCTION pattern matcher - not a simplified version
from Fast_Swarm.local_agents.backtest.pattern_matcher import (
    PatternMatcher,
    evaluate_conditions,
    resolve_indicator,
    INDICATOR_ALIASES,
)

# Import canonical windows
import importlib.util
spec = importlib.util.spec_from_file_location(
    "canonical_windows",
    Path(__file__).parent.parent / "Tests" / "Fixtures" / "canonical_windows.py"
)
canonical_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(canonical_mod)
CANONICAL_WINDOWS = canonical_mod.CANONICAL_WINDOWS

DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")


def get_agent_from_db(agent_id: str = None, agent_name: str = None):
    """Get an agent and its patterns from the database (sync)."""
    import psycopg2
    import json

    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        database=os.getenv("POSTGRES_DB", "coinswarm"),
        user=os.getenv("POSTGRES_USER", "coinswarm"),
        password=os.getenv("POSTGRES_PASSWORD", "coinswarm_dev_2024"),
    )
    cur = conn.cursor()

    try:
        if agent_id:
            cur.execute("""
                SELECT agent_id, name, traits, assigned_patterns, pattern_weights,
                       fitness_score, total_trades, win_rate, fitness_by_regime
                FROM agents
                WHERE agent_id = %s AND status = 'active'
            """, (agent_id,))
        elif agent_name:
            cur.execute("""
                SELECT agent_id, name, traits, assigned_patterns, pattern_weights,
                       fitness_score, total_trades, win_rate, fitness_by_regime
                FROM agents
                WHERE name LIKE %s AND status = 'active'
                LIMIT 1
            """, (f"%{agent_name}%",))
        else:
            # Find agent with patterns in assigned_patterns.base array
            cur.execute("""
                SELECT agent_id, name, traits, assigned_patterns, pattern_weights,
                       fitness_score, total_trades, win_rate, fitness_by_regime
                FROM agents
                WHERE status = 'active'
                  AND assigned_patterns IS NOT NULL
                  AND assigned_patterns->'base' IS NOT NULL
                  AND jsonb_array_length(assigned_patterns->'base') > 0
                ORDER BY fitness_score DESC
                LIMIT 1
            """)

        row = cur.fetchone()
        if row:
            # Patterns are in assigned_patterns.base array
            assigned = row[3] or {}
            patterns = assigned.get("base", [])

            return {
                "agent_id": row[0],
                "name": row[1],
                "traits": row[2] or {},
                "patterns": patterns,
                "pattern_weights": row[4] or {},
                "fitness_score": float(row[5]) if row[5] else 0,
                "total_trades": row[6] or 0,
                "win_rate": float(row[7]) if row[7] else 0,
                "fitness_by_regime": row[8] or {},
            }
        return None
    finally:
        cur.close()
        conn.close()


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


def check_pattern_entry(pattern: dict, indicators: dict, min_confidence: float = 0.3) -> tuple[bool, float]:
    """
    Check if pattern entry conditions are met using PRODUCTION PatternMatcher.

    Uses the canonical indicator mapping and confidence-based evaluation
    from local_agents/backtest/pattern_matcher.py.

    Returns:
        (should_enter, confidence)
    """
    # Create production matcher for this pattern
    matcher = PatternMatcher(
        pattern=pattern,
        min_confidence=min_confidence,
    )
    return matcher.should_enter(indicators)


def calculate_buy_and_hold(df) -> dict:
    """Calculate simple buy-and-hold return for comparison."""
    rows = df.to_dicts()
    if not rows:
        return {"return": 0, "max_dd": 0}

    start_price = rows[0].get("close", 1)
    end_price = rows[-1].get("close", 1)

    # Track drawdown
    peak = start_price
    max_dd = 0
    for row in rows:
        price = row.get("close", 0)
        if price > peak:
            peak = price
        dd = (peak - price) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    return {
        "return": (end_price / start_price - 1) * 100,
        "max_dd": max_dd * 100,
    }


def simulate_agent(
    df,
    symbol: str,
    patterns: list,
    traits: dict,
    use_bear_protection: bool = False,
):
    """
    Simulate an agent's pattern-based trading.

    - Evaluates pattern entry conditions
    - Uses stop loss / take profit from traits
    - With bear protection: exits positions and blocks entries in DEFENSIVE
    """
    rows = df.to_dicts()

    if use_bear_protection:
        service = BearProtectionService()

    # Extract traits
    risk_tolerance = traits.get("risk_tolerance", 0.5)
    stop_loss_tightness = traits.get("stop_loss_tightness", 0.5)
    profit_target_greed = traits.get("profit_target_greed", 0.5)

    # Calculate position parameters from traits
    position_size = 0.10 + risk_tolerance * 0.40  # 10-50% position
    stop_loss_pct = 0.01 + (1 - stop_loss_tightness) * 0.09  # 1-10% stop
    take_profit_pct = 0.02 + profit_target_greed * 0.18  # 2-20% take profit

    # State
    capital = 10000.0
    position = None  # {entry_price, size, pattern_id, direction}
    trades = []
    equity_curve = [capital]

    # Track metrics
    peak = capital
    max_dd = 0

    for i, row in enumerate(rows):
        price = row.get("close", 0)
        if price <= 0:
            continue

        indicators = {k: v for k, v in row.items() if isinstance(v, (int, float))}

        # Check bear protection regime
        if use_bear_protection:
            state = row_to_market_state(row, symbol)
            result = service.evaluate(state)
            regime = result.regime
            max_position_allowed = result.max_position
        else:
            regime = None
            max_position_allowed = 1.0

        # If in position
        if position:
            entry_price = position["entry_price"]
            direction = position["direction"]

            # Calculate P&L
            if direction == "long":
                pnl_pct = (price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - price) / entry_price

            should_exit = False
            exit_reason = None

            # Bear protection VETO - force exit in DEFENSIVE
            if use_bear_protection and regime == Regime.DEFENSIVE:
                should_exit = True
                exit_reason = "bear_protection_veto"
            # Stop loss
            elif pnl_pct < -stop_loss_pct:
                should_exit = True
                exit_reason = "stop_loss"
            # Take profit
            elif pnl_pct > take_profit_pct:
                should_exit = True
                exit_reason = "take_profit"

            if should_exit:
                # Close position
                position_value = position["size"] * (1 + pnl_pct)
                capital = capital - position["size"] + position_value

                trades.append({
                    "entry_price": entry_price,
                    "exit_price": price,
                    "pnl_pct": pnl_pct * 100,
                    "reason": exit_reason,
                    "direction": direction,
                })
                position = None

        # If no position, look for entry
        if position is None:
            # Skip entries in DEFENSIVE regime with bear protection
            if use_bear_protection and regime == Regime.DEFENSIVE:
                pass  # Block entries
            else:
                # Check patterns using PRODUCTION PatternMatcher
                for pattern in patterns:
                    direction = pattern.get("direction", "long")

                    # Use production pattern matcher with confidence scoring
                    should_enter, confidence = check_pattern_entry(pattern, indicators)

                    if should_enter:
                        # Entry signal - open position
                        size = capital * position_size * max_position_allowed
                        if size > 0:
                            position = {
                                "entry_price": price,
                                "size": size,
                                "pattern_id": pattern.get("pattern_id", "unknown"),
                                "direction": direction,
                                "confidence": confidence,
                            }
                            break  # Only one position at a time

        # Update equity
        current_equity = capital
        if position:
            entry_price = position["entry_price"]
            direction = position["direction"]
            if direction == "long":
                pnl_pct = (price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - price) / entry_price
            current_equity = capital - position["size"] + position["size"] * (1 + pnl_pct)

        equity_curve.append(current_equity)

        # Track drawdown
        if current_equity > peak:
            peak = current_equity
        dd = (peak - current_equity) / peak
        if dd > max_dd:
            max_dd = dd

    # Close any open position at end
    if position:
        price = rows[-1].get("close", position["entry_price"])
        entry_price = position["entry_price"]
        direction = position["direction"]
        if direction == "long":
            pnl_pct = (price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - price) / entry_price

        position_value = position["size"] * (1 + pnl_pct)
        capital = capital - position["size"] + position_value
        trades.append({
            "entry_price": entry_price,
            "exit_price": price,
            "pnl_pct": pnl_pct * 100,
            "reason": "end_of_data",
            "direction": direction,
        })

    # Calculate stats
    final_equity = capital
    total_return = (final_equity / 10000.0 - 1) * 100

    winning = [t for t in trades if t["pnl_pct"] > 0]
    win_rate = len(winning) / len(trades) * 100 if trades else 0

    return {
        "total_return": total_return,
        "max_dd": max_dd * 100,
        "trades": len(trades),
        "win_rate": win_rate,
        "final_equity": final_equity,
    }


def main():
    print("=" * 100)
    print("AGENT PERFORMANCE: WITH vs WITHOUT BEAR PROTECTION")
    print("=" * 100)

    # Get agent from database - try Fade_Bold_Switch first
    print("\nLoading agent from database...")
    agent = get_agent_from_db(agent_name="Fade_Bold_Switch")

    if not agent:
        # Fallback to any agent with patterns
        agent = get_agent_from_db()

    if not agent:
        print("No suitable agent found!")
        return

    print(f"\nAgent: {agent['name']} ({agent['agent_id'][:8]}...)")
    print(f"  Patterns: {len(agent['patterns'])}")
    for i, p in enumerate(agent['patterns'][:3]):  # Show first 3 patterns
        print(f"    [{i+1}] {p.get('name', 'unknown')} ({len(p.get('entry_conditions', []))} conditions)")
    print(f"  DB Fitness: {agent['fitness_score']:.1f}")
    print(f"  DB Win Rate: {agent['win_rate']*100:.1f}%")
    print(f"  DB Trades: {agent['total_trades']}")
    if agent.get('fitness_by_regime'):
        print(f"  Fitness by Regime: {agent['fitness_by_regime']}")

    # Test windows - focus on crash periods + full cycle
    test_windows = [
        ("btc_2022_bear", "BTC 2022 Bear"),
        ("btc_2021_bull", "BTC 2021 Bull"),
        ("flash_crash_may2021", "Flash Crash"),
        ("luna_collapse", "Luna Collapse"),
        ("ftx_collapse", "FTX Collapse"),
        ("btc_2023_h1", "BTC 2023 H1"),
        ("btc_full_cycle_daily", "Full 4-Year Cycle"),
    ]

    results = []

    for window_key, window_name in test_windows:
        window = CANONICAL_WINDOWS.get(window_key)
        if not window:
            continue

        symbol = window.asset.split("/")[0] if "/" in window.asset else "BTC"
        df = load_mtf_for_period(symbol, window.start, window.end)

        if df is None or len(df) == 0:
            print(f"\n{window_name}: No data")
            continue

        print(f"\n{'='*80}")
        print(f"{window_name} ({len(df):,} candles)")
        print("=" * 80)

        # Calculate buy-and-hold baseline
        bh = calculate_buy_and_hold(df)

        # Run WITHOUT bear protection
        result_no_bp = simulate_agent(
            df, symbol, agent['patterns'], agent['traits'],
            use_bear_protection=False
        )

        # Run WITH bear protection
        result_with_bp = simulate_agent(
            df, symbol, agent['patterns'], agent['traits'],
            use_bear_protection=True
        )

        delta_return = result_with_bp['total_return'] - result_no_bp['total_return']
        delta_dd = result_no_bp['max_dd'] - result_with_bp['max_dd']

        # Alpha vs buy-and-hold
        alpha_no_bp = result_no_bp['total_return'] - bh['return']
        alpha_with_bp = result_with_bp['total_return'] - bh['return']

        print(f"\n  {'Metric':<20} {'Buy&Hold':>12} {'Agent':>12} {'Agent+BP':>12} {'BP Delta':>12}")
        print("  " + "-" * 70)
        print(f"  {'Total Return':<20} {bh['return']:>11.1f}% {result_no_bp['total_return']:>11.1f}% {result_with_bp['total_return']:>11.1f}% {delta_return:>+11.1f}%")
        print(f"  {'Max Drawdown':<20} {bh['max_dd']:>11.1f}% {result_no_bp['max_dd']:>11.1f}% {result_with_bp['max_dd']:>11.1f}% {-delta_dd:>+11.1f}%")
        print(f"  {'Trades':<20} {'--':>12} {result_no_bp['trades']:>12} {result_with_bp['trades']:>12}")
        print(f"  {'Win Rate':<20} {'--':>12} {result_no_bp['win_rate']:>11.1f}% {result_with_bp['win_rate']:>11.1f}%")
        print(f"  {'Alpha vs B&H':<20} {'--':>12} {alpha_no_bp:>+11.1f}% {alpha_with_bp:>+11.1f}%")

        is_crash = any(x in window_key for x in ["crash", "collapse", "bear"])

        results.append({
            "window": window_name,
            "type": "crash" if is_crash else "bull",
            "bh_return": bh['return'],
            "bh_dd": bh['max_dd'],
            "no_bp_return": result_no_bp['total_return'],
            "with_bp_return": result_with_bp['total_return'],
            "no_bp_dd": result_no_bp['max_dd'],
            "with_bp_dd": result_with_bp['max_dd'],
            "delta_return": delta_return,
            "delta_dd": delta_dd,
            "alpha_no_bp": alpha_no_bp,
            "alpha_with_bp": alpha_with_bp,
        })

    # Summary
    print("\n" + "=" * 110)
    print("SUMMARY: ALL STRATEGIES COMPARED")
    print("=" * 110)

    print(f"\n{'Window':<22} {'Type':<7} {'Buy&Hold':>10} {'Agent':>10} {'Agent+BP':>10} {'BP Delta':>10} {'Alpha':>10}")
    print("-" * 110)

    total_delta = 0
    total_dd_saved = 0
    total_alpha = 0

    for r in results:
        marker = "[C]" if r['type'] == 'crash' else "[B]"
        print(f"{marker} {r['window']:<20} {r['type']:<7} {r['bh_return']:>9.1f}% {r['no_bp_return']:>9.1f}% {r['with_bp_return']:>9.1f}% {r['delta_return']:>+9.1f}% {r['alpha_with_bp']:>+9.1f}%")
        total_delta += r['delta_return']
        total_dd_saved += r['delta_dd']
        total_alpha += r['alpha_with_bp']

    print("-" * 110)
    print(f"{'TOTAL':<32} {'':<7} {'':<10} {'':<10} {'':<10} {total_delta:>+9.1f}% {total_alpha:>+9.1f}%")

    # Drawdown comparison
    print("\n" + "=" * 110)
    print("DRAWDOWN COMPARISON")
    print("=" * 110)

    print(f"\n{'Window':<22} {'Type':<7} {'B&H DD':>10} {'Agent DD':>10} {'Agent+BP DD':>10} {'DD Saved':>10}")
    print("-" * 90)

    for r in results:
        marker = "[C]" if r['type'] == 'crash' else "[B]"
        print(f"{marker} {r['window']:<20} {r['type']:<7} {r['bh_dd']:>9.1f}% {r['no_bp_dd']:>9.1f}% {r['with_bp_dd']:>9.1f}% {r['delta_dd']:>+9.1f}%")

    print("-" * 90)
    print(f"{'TOTAL DD SAVED':<42} {'':<7} {'':<10} {'':<10} {total_dd_saved:>+9.1f}%")

    print("\n" + "=" * 110)
    print("CONCLUSION")
    print("=" * 110)

    if total_delta > 0:
        print(f"\n[OK] Bear Protection IMPROVED agent performance by {total_delta:+.1f}%")
        print(f"     Total drawdown reduced by {total_dd_saved:+.1f}%")
        if total_alpha > 0:
            print(f"     Agent+BP generated {total_alpha:+.1f}% ALPHA over buy-and-hold!")
        else:
            print(f"     Agent+BP underperformed buy-and-hold by {total_alpha:.1f}%")
    else:
        print(f"\n[!!] Bear Protection REDUCED agent performance by {total_delta:.1f}%")
        print(f"     (but saved {total_dd_saved:+.1f}% in drawdown)")


if __name__ == "__main__":
    main()
