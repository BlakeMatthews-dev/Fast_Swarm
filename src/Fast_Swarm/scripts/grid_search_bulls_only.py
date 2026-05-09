"""
Grid Search: Bear Protection - BULL WINDOWS ONLY.

Tests all 28 signal composition configs on bull market periods.
"""

import polars as pl
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional, List, Tuple
from enum import Enum
import sys
import json

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from Fast_Swarm.local_agents.backtest.pattern_matcher import PatternMatcher

DERIVATIVES_DIR = Path("c:/fast_swarm/data/derivatives")


class Regime(Enum):
    DEFENSIVE = "DEFENSIVE"
    NEUTRAL = "NEUTRAL"
    AGGRESSIVE = "AGGRESSIVE"


@dataclass
class GridSearchConfig:
    name: str
    use_velocity: bool = True
    use_acceleration: bool = True
    use_jerk: bool = True
    exit_vel_threshold: float = 0.5
    exit_acc_threshold: float = -1.5
    exit_jerk_threshold: float = 0.0
    entry_vel_threshold: float = -1.5
    entry_acc_threshold: float = 3.0
    defensive_tf_confirm: int = 1
    aggressive_tf_confirm: int = 1
    defensive_max: float = 0.0
    neutral_max: float = 0.50
    aggressive_max: float = 0.85


class ConfigurableBearProtection:
    def __init__(self, config: GridSearchConfig):
        self.config = config
        self._current_regime = Regime.NEUTRAL

    def _check_exit_signal(self, vel: float, acc: float, jerk: float) -> bool:
        conditions_met = []
        if self.config.use_velocity:
            if vel is None:
                return False
            conditions_met.append(vel > self.config.exit_vel_threshold)
        if self.config.use_acceleration:
            if acc is None:
                return False
            conditions_met.append(acc < self.config.exit_acc_threshold)
        if self.config.use_jerk:
            if jerk is None:
                return False
            conditions_met.append(jerk < self.config.exit_jerk_threshold)
        return all(conditions_met) if conditions_met else False

    def _check_entry_signal(self, vel: float, acc: float) -> bool:
        conditions_met = []
        if self.config.use_velocity:
            if vel is None:
                return False
            conditions_met.append(vel < self.config.entry_vel_threshold)
        if self.config.use_acceleration:
            if acc is None:
                return False
            conditions_met.append(acc > self.config.entry_acc_threshold)
        return all(conditions_met) if conditions_met else False

    def evaluate(self, row: dict) -> Tuple[Regime, float]:
        exit_signals = []
        entry_signals = []

        for tf in ["1h", "4h", "1d"]:
            vel = row.get(f"tf_{tf}_close_velocity_zscore")
            acc = row.get(f"tf_{tf}_close_acceleration_zscore")
            jerk = row.get(f"tf_{tf}_adx_14_jerk_zscore")

            if self._check_exit_signal(vel, acc, jerk):
                exit_signals.append(tf)
            if self._check_entry_signal(vel, acc):
                entry_signals.append(tf)

        exit_confirmed = len(exit_signals) >= self.config.defensive_tf_confirm
        entry_confirmed = len(entry_signals) >= self.config.aggressive_tf_confirm

        if exit_confirmed:
            new_regime = Regime.DEFENSIVE
        elif entry_confirmed:
            new_regime = Regime.AGGRESSIVE
        elif len(exit_signals) == 0 and len(entry_signals) == 0:
            new_regime = Regime.NEUTRAL
        else:
            new_regime = self._current_regime

        self._current_regime = new_regime

        if new_regime == Regime.DEFENSIVE:
            return new_regime, self.config.defensive_max
        elif new_regime == Regime.AGGRESSIVE:
            return new_regime, self.config.aggressive_max
        return new_regime, self.config.neutral_max


def generate_all_configs() -> List[GridSearchConfig]:
    configs = []
    compositions = [
        ("V", True, False, False),
        ("A", False, True, False),
        ("J", False, False, True),
        ("VA", True, True, False),
        ("AJ", False, True, True),
        ("VJ", True, False, True),
        ("VAJ", True, True, True),
    ]
    thresholds = [
        ("tight", 0.5, -1.5, 0.0, -1.5, 3.0),
        ("loose", 1.0, -2.5, -0.5, -0.5, 1.5),
    ]
    tf_confirms = [1, 2]

    for comp_name, use_v, use_a, use_j in compositions:
        for thresh_name, exit_v, exit_a, exit_j, entry_v, entry_a in thresholds:
            for tf_conf in tf_confirms:
                name = f"{comp_name}_{thresh_name}_TF{tf_conf}"
                configs.append(GridSearchConfig(
                    name=name,
                    use_velocity=use_v,
                    use_acceleration=use_a,
                    use_jerk=use_j,
                    exit_vel_threshold=exit_v,
                    exit_acc_threshold=exit_a,
                    exit_jerk_threshold=exit_j,
                    entry_vel_threshold=entry_v,
                    entry_acc_threshold=entry_a,
                    defensive_tf_confirm=tf_conf,
                ))

    return configs


# BULL WINDOWS ONLY
BULL_WINDOWS = [
    {
        "name": "BTC 2021 Bull",
        "symbol": "BTC",
        "start": datetime(2021, 1, 1, 0, 0, 0),
        "end": datetime(2021, 4, 14, 23, 59, 59),
    },
    {
        "name": "BTC 2020-2021 Recovery",
        "symbol": "BTC",
        "start": datetime(2020, 10, 1, 0, 0, 0),
        "end": datetime(2021, 1, 1, 0, 0, 0),
    },
    {
        "name": "ETH 2021 Bull",
        "symbol": "ETH",
        "start": datetime(2021, 1, 1, 0, 0, 0),
        "end": datetime(2021, 5, 12, 23, 59, 59),
    },
    {
        "name": "BTC 2023 Recovery",
        "symbol": "BTC",
        "start": datetime(2023, 1, 1, 0, 0, 0),
        "end": datetime(2023, 7, 1, 0, 0, 0),
    },
    {
        "name": "BTC 2024 ETF Rally",
        "symbol": "BTC",
        "start": datetime(2024, 1, 1, 0, 0, 0),
        "end": datetime(2024, 3, 15, 0, 0, 0),
    },
]


def load_mtf_for_period(symbol: str, start: datetime, end: datetime):
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

    df_1h = df_1h.filter((pl.col("time") >= start_tz) & (pl.col("time") <= end_tz))

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


def get_agent_from_db():
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


def check_pattern_entry(pattern: dict, indicators: dict, min_confidence: float = 0.3) -> Tuple[bool, float]:
    matcher = PatternMatcher(pattern=pattern, min_confidence=min_confidence)
    return matcher.should_enter(indicators)


def simulate(df, traits, patterns, config: Optional[GridSearchConfig] = None):
    service = ConfigurableBearProtection(config) if config else None

    risk_tolerance = traits.get("risk_tolerance", 0.5)
    position_size = 0.10 + risk_tolerance * 0.40
    stop_loss_pct = 0.05
    take_profit_pct = 0.10

    capital = 10000.0
    position = None
    trades = []
    peak = capital
    max_dd = 0

    regime_counts = {"DEFENSIVE": 0, "NEUTRAL": 0, "AGGRESSIVE": 0}
    veto_exits = 0
    blocked_entries = 0

    rows = df.to_dicts()

    for row in rows:
        price = row.get("close", 0)
        if price <= 0:
            continue

        indicators = {k: v for k, v in row.items() if isinstance(v, (int, float))}

        if config:
            regime, max_pos = service.evaluate(row)
            regime_counts[regime.value] += 1
        else:
            regime = None
            max_pos = 1.0

        if position:
            entry_price = position["entry_price"]
            pnl_pct = (price - entry_price) / entry_price

            should_exit = False
            exit_reason = None

            if config and regime == Regime.DEFENSIVE:
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

        if position is None:
            if config and regime == Regime.DEFENSIVE:
                # Check if pattern would have entered
                for pattern in patterns:
                    should_enter, _ = check_pattern_entry(pattern, indicators)
                    if should_enter:
                        blocked_entries += 1
                        break
            else:
                for pattern in patterns:
                    should_enter, confidence = check_pattern_entry(pattern, indicators)
                    if should_enter:
                        size = capital * position_size * max_pos
                        if size > 0:
                            position = {"entry_price": price, "size": size}
                            break

        current_equity = capital
        if position:
            pnl_pct = (price - position["entry_price"]) / position["entry_price"]
            current_equity = capital - position["size"] + position["size"] * (1 + pnl_pct)

        if current_equity > peak:
            peak = current_equity
        dd = (peak - current_equity) / peak
        if dd > max_dd:
            max_dd = dd

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
        "regime_counts": regime_counts if config else None,
        "veto_exits": veto_exits if config else 0,
        "blocked_entries": blocked_entries if config else 0,
    }


def calculate_buy_and_hold(df) -> dict:
    rows = df.to_dicts()
    first_price = rows[0].get("close", 0)
    last_price = rows[-1].get("close", 0)

    if first_price <= 0:
        return {"return": 0, "max_dd": 0}

    peak = first_price
    max_dd = 0

    for row in rows:
        price = row.get("close", 0)
        if price > peak:
            peak = price
        dd = (peak - price) / peak
        if dd > max_dd:
            max_dd = dd

    return {
        "return": (last_price / first_price - 1) * 100,
        "max_dd": max_dd * 100,
    }


def main():
    print("=" * 120)
    print("GRID SEARCH: BEAR PROTECTION - BULL WINDOWS ONLY")
    print("=" * 120)

    configs = generate_all_configs()
    print(f"\nGenerated {len(configs)} configurations")
    print(f"Testing on {len(BULL_WINDOWS)} bull windows")

    agent = get_agent_from_db()
    if not agent:
        print("Agent not found!")
        return

    print(f"\nUsing agent: Fade_Bold_Switch")
    print(f"Patterns: {len(agent['patterns'])}")

    config_results = {c.name: {"bp_deltas": [], "dd_saved": [], "blocked": [], "windows": 0} for c in configs}
    window_results = []

    for window in BULL_WINDOWS:
        print(f"\n{'='*120}")
        print(f"Window: {window['name']}")
        print(f"Period: {window['start'].date()} to {window['end'].date()}")
        print("=" * 120)

        df = load_mtf_for_period(window['symbol'], window['start'], window['end'])

        if df is None or len(df) == 0:
            print(f"  [!] No data available")
            continue

        print(f"  Loaded {len(df):,} candles for {window['symbol']}")

        # Baseline (no bear protection)
        result_no_bp = simulate(df, agent["traits"], agent["patterns"], config=None)
        bh = calculate_buy_and_hold(df)

        print(f"\n  BASELINE (No BP): Return={result_no_bp['return']:+.1f}%, DD={result_no_bp['max_dd']:.1f}%, Trades={result_no_bp['trades']}")
        print(f"  Buy & Hold:       Return={bh['return']:+.1f}%, DD={bh['max_dd']:.1f}%")

        if result_no_bp['trades'] == 0:
            print(f"  [!] NO TRADES in baseline - pattern conditions not met during bull")
            # Still test configs to see regime behavior

        window_config_results = []

        for config in configs:
            result = simulate(df, agent["traits"], agent["patterns"], config=config)

            bp_delta = result["return"] - result_no_bp["return"]
            dd_saved = result_no_bp["max_dd"] - result["max_dd"]

            config_results[config.name]["bp_deltas"].append(bp_delta)
            config_results[config.name]["dd_saved"].append(dd_saved)
            config_results[config.name]["blocked"].append(result["blocked_entries"])
            config_results[config.name]["windows"] += 1

            window_config_results.append({
                "config": config.name,
                "return": result["return"],
                "bp_delta": bp_delta,
                "dd_saved": dd_saved,
                "trades": result["trades"],
                "blocked": result["blocked_entries"],
                "veto_exits": result["veto_exits"],
                "regimes": result["regime_counts"],
            })

        # Sort by return (best performance in bulls)
        sorted_results = sorted(window_config_results, key=lambda x: x["return"], reverse=True)

        print(f"\n  Top 5 configs (by RETURN - best for bulls):")
        print(f"  {'Config':<25} {'Return':>10} {'BP Delta':>10} {'Trades':>8} {'Blocked':>8} {'Veto':>6}")
        print("  " + "-" * 75)
        for r in sorted_results[:5]:
            print(f"  {r['config']:<25} {r['return']:>+9.1f}% {r['bp_delta']:>+9.1f}% {r['trades']:>8} {r['blocked']:>8} {r['veto_exits']:>6}")

        # Also show WORST for bulls (most restrictive)
        print(f"\n  Bottom 5 configs (WORST for bulls - most restrictive):")
        print(f"  {'Config':<25} {'Return':>10} {'BP Delta':>10} {'Trades':>8} {'Blocked':>8} {'Veto':>6}")
        print("  " + "-" * 75)
        for r in sorted_results[-5:]:
            print(f"  {r['config']:<25} {r['return']:>+9.1f}% {r['bp_delta']:>+9.1f}% {r['trades']:>8} {r['blocked']:>8} {r['veto_exits']:>6}")

        # Show regime distribution for best config
        if sorted_results:
            best = sorted_results[0]
            regimes = best["regimes"]
            total = sum(regimes.values())
            print(f"\n  Regime distribution for {best['config']}:")
            for regime, count in regimes.items():
                pct = count / total * 100 if total > 0 else 0
                print(f"    {regime}: {count} ({pct:.1f}%)")

        window_results.append({
            "window": window["name"],
            "bh_return": bh["return"],
            "no_bp_return": result_no_bp["return"],
            "no_bp_trades": result_no_bp["trades"],
            "results": sorted_results,
        })

    # AGGREGATE
    print("\n" + "=" * 120)
    print("AGGREGATE: BEST CONFIGS FOR BULL MARKETS")
    print("=" * 120)

    aggregate_scores = []
    for config in configs:
        name = config.name
        data = config_results[name]
        if data["windows"] == 0:
            continue

        total_bp_delta = sum(data["bp_deltas"])
        total_blocked = sum(data["blocked"])
        avg_bp_delta = total_bp_delta / len(data["bp_deltas"])

        # For bulls, we want HIGHEST return (least restrictive)
        # Score = total_bp_delta (higher = better for bulls)
        aggregate_scores.append({
            "config": name,
            "total_bp_delta": total_bp_delta,
            "avg_bp_delta": avg_bp_delta,
            "total_blocked": total_blocked,
            "windows": data["windows"],
        })

    # Sort by BP delta (highest = best for bulls)
    aggregate_scores.sort(key=lambda x: x["total_bp_delta"], reverse=True)

    print(f"\n{'Rank':<5} {'Config':<25} {'Total BP Delta':>15} {'Avg BP Delta':>12} {'Blocked':>10}")
    print("-" * 70)

    for i, r in enumerate(aggregate_scores, 1):
        marker = "*** BEST FOR BULLS" if i <= 3 else ""
        print(f"{i:<5} {r['config']:<25} {r['total_bp_delta']:>+14.1f}% {r['avg_bp_delta']:>+11.1f}% {r['total_blocked']:>10} {marker}")
        if i == 10:
            print("-" * 70)

    # Analysis by composition
    print("\n" + "=" * 120)
    print("ANALYSIS BY SIGNAL COMPOSITION (FOR BULLS)")
    print("=" * 120)

    for comp in ["V", "A", "J", "VA", "AJ", "VJ", "VAJ"]:
        comp_configs = [r for r in aggregate_scores if r["config"].startswith(f"{comp}_")]
        if comp_configs:
            avg_delta = sum(c["total_bp_delta"] for c in comp_configs) / len(comp_configs)
            avg_blocked = sum(c["total_blocked"] for c in comp_configs) / len(comp_configs)
            best = max(comp_configs, key=lambda x: x["total_bp_delta"])
            print(f"\n{comp:>5}: Avg BP Delta={avg_delta:+.1f}%, Avg Blocked={avg_blocked:.0f}")
            print(f"       Best for bulls: {best['config']} (Delta: {best['total_bp_delta']:+.1f}%)")

    # Save results
    output_path = Path("c:/fast_swarm/data/grid_search_bulls_results.json")
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "focus": "BULL_WINDOWS_ONLY",
        "total_configs": len(configs),
        "windows_tested": len(window_results),
        "aggregate_scores": aggregate_scores,
        "window_results": window_results,
    }

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2, default=str)

    print(f"\n\nResults saved to: {output_path}")

    # Final recommendation
    print("\n" + "=" * 120)
    print("RECOMMENDATION FOR BULL MARKETS")
    print("=" * 120)

    if aggregate_scores:
        best = aggregate_scores[0]
        worst = aggregate_scores[-1]
        print(f"\nBEST for bulls (least restrictive): {best['config']}")
        print(f"  - BP Delta: {best['total_bp_delta']:+.1f}%")
        print(f"  - Blocked entries: {best['total_blocked']}")
        print(f"\nWORST for bulls (most restrictive): {worst['config']}")
        print(f"  - BP Delta: {worst['total_bp_delta']:+.1f}%")
        print(f"  - Blocked entries: {worst['total_blocked']}")


if __name__ == "__main__":
    main()
