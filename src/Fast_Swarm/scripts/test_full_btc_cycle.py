"""
Test Bear Protection on FULL BTC CYCLE (2020-2023).

4 years covering:
- COVID crash (March 2020)
- Bull run to 64K (2021)
- Bear market / Luna / FTX (2022)
- Recovery (2023)
"""

import polars as pl
from pathlib import Path
from datetime import datetime, timezone
import sys
import os

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from Fast_Swarm.Infrastructure.Services.bear_protection_service import (
    BearProtectionService, MarketState, Regime
)

DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")


def get_agent_from_db():
    """Get Fade_Bold_Switch agent."""
    import psycopg2

    conn = psycopg2.connect(
        host="localhost", port="5432", database="coinswarm",
        user="coinswarm", password="coinswarm_dev_2024"
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT traits, assigned_patterns FROM agents
        WHERE name LIKE '%Fade_Bold_Switch%' LIMIT 1
    """)
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row:
        return {
            "traits": row[0] or {},
            "patterns": (row[1] or {}).get("base", [])
        }
    return None


def load_full_cycle():
    """Load full BTC cycle data (2020-2023)."""
    start = datetime(2020, 1, 1, 0, 0, 0)
    end = datetime(2023, 12, 31, 23, 59, 59)

    base_path = DERIVATIVES_DIR / "symbol=BTC"
    df_1h = pl.read_parquet(base_path / "timeframe=1h").sort("time")
    df_4h = pl.read_parquet(base_path / "timeframe=4h").sort("time")
    df_1d = pl.read_parquet(base_path / "timeframe=1d").sort("time")

    start_tz = start.replace(tzinfo=timezone.utc)
    end_tz = end.replace(tzinfo=timezone.utc)

    df_1h = df_1h.filter((pl.col("time") >= start_tz) & (pl.col("time") <= end_tz))

    cols = ["close_velocity_zscore", "close_acceleration_zscore", "adx_14_jerk_zscore"]

    df_4h_join = df_4h.select(
        [pl.col("time").alias("tf_4h_time")]
        + [pl.col(c).alias(f"tf_4h_{c}") for c in cols if c in df_4h.columns]
    )
    df_1d_join = df_1d.select(
        [pl.col("time").alias("tf_1d_time")]
        + [pl.col(c).alias(f"tf_1d_{c}") for c in cols if c in df_1d.columns]
    )

    df = df_1h.join_asof(df_4h_join, left_on="time", right_on="tf_4h_time", strategy="backward")
    df = df.join_asof(df_1d_join, left_on="time", right_on="tf_1d_time", strategy="backward")

    for c in cols:
        if c in df.columns:
            df = df.rename({c: f"tf_1h_{c}"})

    return df


def evaluate_conditions(indicators, conditions):
    """Evaluate pattern entry conditions with indicator name mapping."""
    if not conditions:
        return False

    # Map pattern indicator names to actual column names
    INDICATOR_MAP = {
        "rsi": "rsi_14",
        "rsi_14": "rsi_14",
        "bollingerBandwidth": "bb_width",
        "bollingerbandwidth": "bb_width",
        "bb_bandwidth": "bb_width",
        "bollingerPercentB": "bb_pct",
        "bollingerpercentb": "bb_pct",
        "bb_percent_b": "bb_pct",
        "macdHistogram": "macd_histogram",
        "macdhistogram": "macd_histogram",
        "minusDI": "minus_di",
        "minusdi": "minus_di",
        "plusDI": "plus_di",
        "plusdi": "plus_di",
        "adx": "adx_14",
        "stochK": "stoch_k",
        "stochD": "stoch_d",
        "atr": "atr_14",
        "ema": "ema_21",
        "sma": "sma_20",
    }

    matches = 0
    evaluated = 0

    for cond in conditions:
        indicator = cond.get("indicator", "")
        operator = cond.get("operator", "")
        threshold = cond.get("value")

        # Try direct mapping first
        mapped = INDICATOR_MAP.get(indicator) or INDICATOR_MAP.get(indicator.lower())

        ind_value = None
        if mapped and mapped in indicators:
            ind_value = indicators[mapped]
        elif indicator in indicators:
            ind_value = indicators[indicator]
        else:
            # Fuzzy match
            for key in indicators:
                if indicator.lower().replace("_", "") in key.lower().replace("_", ""):
                    ind_value = indicators[key]
                    break

        if ind_value is None:
            continue  # Skip unavailable indicators

        evaluated += 1

        try:
            if operator == "between" and isinstance(threshold, list):
                if threshold[0] <= ind_value <= threshold[1]:
                    matches += 1
            elif operator == ">" and ind_value > threshold:
                matches += 1
            elif operator == "<" and ind_value < threshold:
                matches += 1
            elif operator == ">=" and ind_value >= threshold:
                matches += 1
            elif operator == "<=" and ind_value <= threshold:
                matches += 1
            elif operator == "==" and abs(ind_value - threshold) < 0.01:
                matches += 1
        except:
            continue

    # Need at least 1 condition evaluated and 50% match rate
    return evaluated > 0 and matches >= evaluated * 0.5


def simulate(df, traits, patterns, use_bp):
    """Simulate agent trading with or without bear protection."""
    service = BearProtectionService() if use_bp else None

    risk_tolerance = traits.get("risk_tolerance", 0.5)
    position_size = 0.10 + risk_tolerance * 0.40
    stop_loss_pct = 0.05
    take_profit_pct = 0.10

    capital = 10000.0
    position = None
    trades = []
    peak = capital
    max_dd = 0

    # Track regime stats
    regime_counts = {"DEFENSIVE": 0, "NEUTRAL": 0, "AGGRESSIVE": 0}
    veto_exits = 0

    rows = df.to_dicts()

    for row in rows:
        price = row.get("close", 0)
        if price <= 0:
            continue

        indicators = {k: v for k, v in row.items() if isinstance(v, (int, float))}

        # Check regime
        if use_bp:
            state = MarketState(
                time=row.get("time", datetime.now(timezone.utc)),
                symbol="BTC",
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
            result = service.evaluate(state)
            regime = result.regime
            max_pos = result.max_position
            regime_counts[regime.value] += 1
        else:
            regime = None
            max_pos = 1.0

        # If in position
        if position:
            entry_price = position["entry_price"]
            pnl_pct = (price - entry_price) / entry_price

            should_exit = False
            exit_reason = None

            if use_bp and regime == Regime.DEFENSIVE:
                should_exit = True
                exit_reason = "bear_veto"
                veto_exits += 1
            elif pnl_pct < -stop_loss_pct:
                should_exit = True
                exit_reason = "stop_loss"
            elif pnl_pct > take_profit_pct:
                should_exit = True
                exit_reason = "take_profit"

            if should_exit:
                position_value = position["size"] * (1 + pnl_pct)
                capital = capital - position["size"] + position_value
                trades.append({"pnl_pct": pnl_pct * 100, "reason": exit_reason})
                position = None

        # Look for entry
        if position is None:
            if use_bp and regime == Regime.DEFENSIVE:
                pass  # Block entries
            else:
                for pattern in patterns:
                    entry_conditions = pattern.get("entry_conditions", [])
                    if evaluate_conditions(indicators, entry_conditions):
                        size = capital * position_size * max_pos
                        if size > 0:
                            position = {"entry_price": price, "size": size}
                            break

        # Track equity
        current_equity = capital
        if position:
            pnl_pct = (price - position["entry_price"]) / position["entry_price"]
            current_equity = capital - position["size"] + position["size"] * (1 + pnl_pct)

        if current_equity > peak:
            peak = current_equity
        dd = (peak - current_equity) / peak
        if dd > max_dd:
            max_dd = dd

    # Close final position
    if position:
        price = rows[-1].get("close", position["entry_price"])
        pnl_pct = (price - position["entry_price"]) / position["entry_price"]
        position_value = position["size"] * (1 + pnl_pct)
        capital = capital - position["size"] + position_value
        trades.append({"pnl_pct": pnl_pct * 100, "reason": "end"})

    winning = [t for t in trades if t["pnl_pct"] > 0]
    win_rate = len(winning) / len(trades) * 100 if trades else 0

    return {
        "return": (capital / 10000.0 - 1) * 100,
        "max_dd": max_dd * 100,
        "trades": len(trades),
        "win_rate": win_rate,
        "final": capital,
        "regime_counts": regime_counts if use_bp else None,
        "veto_exits": veto_exits if use_bp else 0,
    }


def main():
    print("=" * 100)
    print("FULL BTC CYCLE: 2020-2023")
    print("COVID Crash -> Bull Run to 64K -> Bear Market -> Recovery")
    print("=" * 100)

    # Load data
    print("\nLoading 4 years of hourly data...")
    df = load_full_cycle()
    print(f"Loaded {len(df):,} hourly candles")

    first_price = df["close"][0]
    last_price = df["close"][-1]
    min_time = df["time"].min()
    max_time = df["time"].max()

    print(f"Period: {min_time} to {max_time}")
    print(f"Price: ${first_price:,.0f} -> ${last_price:,.0f}")

    # Get agent
    agent = get_agent_from_db()
    if not agent:
        print("Agent not found!")
        return

    print(f"\nAgent: Fade_Bold_Switch_G1")
    print(f"Patterns: {len(agent['patterns'])}")

    # Run simulations
    print("\n" + "-" * 50)
    print("Running simulation WITHOUT bear protection...")
    result_no_bp = simulate(df, agent["traits"], agent["patterns"], use_bp=False)

    print("Running simulation WITH bear protection...")
    result_with_bp = simulate(df, agent["traits"], agent["patterns"], use_bp=True)

    # Results
    delta_return = result_with_bp["return"] - result_no_bp["return"]
    delta_dd = result_no_bp["max_dd"] - result_with_bp["max_dd"]

    print("\n" + "=" * 100)
    print("RESULTS: FULL 4-YEAR BTC CYCLE")
    print("=" * 100)

    print(f"\n{'Metric':<25} {'WITHOUT BP':>15} {'WITH BP':>15} {'DELTA':>15}")
    print("-" * 75)
    print(f"{'Total Return':<25} {result_no_bp['return']:>14.1f}% {result_with_bp['return']:>14.1f}% {delta_return:>+14.1f}%")
    print(f"{'Max Drawdown':<25} {result_no_bp['max_dd']:>14.1f}% {result_with_bp['max_dd']:>14.1f}% {-delta_dd:>+14.1f}%")
    print(f"{'Trades':<25} {result_no_bp['trades']:>15} {result_with_bp['trades']:>15}")
    print(f"{'Win Rate':<25} {result_no_bp['win_rate']:>14.1f}% {result_with_bp['win_rate']:>14.1f}%")
    print(f"{'Final Capital':<25} ${result_no_bp['final']:>13,.0f} ${result_with_bp['final']:>13,.0f}")

    # Regime breakdown
    if result_with_bp["regime_counts"]:
        print("\n" + "-" * 50)
        print("REGIME BREAKDOWN (with Bear Protection):")
        total_candles = sum(result_with_bp["regime_counts"].values())
        for regime, count in result_with_bp["regime_counts"].items():
            pct = count / total_candles * 100
            print(f"  {regime:<12}: {count:>6,} candles ({pct:>5.1f}%)")
        print(f"  Bear Veto Exits: {result_with_bp['veto_exits']}")

    # Buy-and-hold comparison
    bh_return = (last_price / first_price - 1) * 100

    print("\n" + "=" * 100)
    print("COMPARISON vs BUY-AND-HOLD")
    print("=" * 100)
    print(f"\n{'Strategy':<25} {'Return':>15} {'vs B&H':>15}")
    print("-" * 55)
    print(f"{'BTC Buy & Hold':<25} {bh_return:>+14.1f}%")
    print(f"{'Agent (no BP)':<25} {result_no_bp['return']:>+14.1f}% {result_no_bp['return'] - bh_return:>+14.1f}%")
    print(f"{'Agent (WITH BP)':<25} {result_with_bp['return']:>+14.1f}% {result_with_bp['return'] - bh_return:>+14.1f}%")

    # Conclusion
    print("\n" + "=" * 100)
    print("CONCLUSION")
    print("=" * 100)

    if delta_return > 0:
        print(f"\n[OK] Bear Protection IMPROVED agent by {delta_return:+.1f}% over 4 years")
        print(f"     Drawdown reduced by {delta_dd:+.1f}%")
        if result_with_bp["return"] > bh_return:
            alpha = result_with_bp["return"] - bh_return
            print(f"     Agent BEAT buy-and-hold by {alpha:+.1f}%!")
    else:
        print(f"\n[!!] Bear Protection reduced returns by {delta_return:.1f}%")
        print(f"     But saved {delta_dd:+.1f}% in drawdown")


if __name__ == "__main__":
    main()
