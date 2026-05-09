"""
Multi-Agent Jerk Threshold Analysis

Tests jerk thresholds across 11 high-performing agents on volatile periods.
"""

import polars as pl
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict, Any
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
class JerkThresholdConfig:
    name: str
    jerk_threshold: float
    acc_threshold: float = -2.5
    tf_confirm: int = 2
    use_velocity: bool = False
    use_acceleration: bool = True
    use_jerk: bool = True
    entry_acc_threshold: float = 1.5
    defensive_max: float = 0.0
    neutral_max: float = 0.50
    aggressive_max: float = 0.85


class ConfigurableBearProtection:
    def __init__(self, config: JerkThresholdConfig):
        self.config = config
        self._current_regime = Regime.NEUTRAL

    def _check_exit_signal(self, vel: float, acc: float, jerk: float) -> bool:
        conditions_met = []
        if self.config.use_acceleration:
            if acc is None:
                return False
            conditions_met.append(acc < self.config.acc_threshold)
        if self.config.use_jerk:
            if jerk is None:
                return False
            conditions_met.append(jerk < self.config.jerk_threshold)
        return all(conditions_met) if conditions_met else False

    def _check_entry_signal(self, vel: float, acc: float) -> bool:
        if acc is None:
            return False
        return acc > self.config.entry_acc_threshold

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

        exit_confirmed = len(exit_signals) >= self.config.tf_confirm
        entry_confirmed = len(entry_signals) >= self.config.tf_confirm

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


# Jerk thresholds: 0.0 to -1.5 in 0.1 increments
JERK_THRESHOLDS = [round(x * 0.1, 1) for x in range(0, -16, -1)]


# Volatile test window - COVID crash has the most data
TEST_WINDOW = {
    "name": "COVID Crash Extended",
    "symbol": "BTC",
    "start": datetime(2020, 1, 15, 0, 0, 0),
    "end": datetime(2020, 5, 15, 0, 0, 0),
    "type": "volatile"
}


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


def get_agents_by_rank(ranks: List[int]) -> List[Dict]:
    """Get specific agents by their rank in the performance list."""
    import psycopg2

    conn = psycopg2.connect(
        host="localhost", port="5432", database="coinswarm",
        user="coinswarm", password="coinswarm_dev_2024"
    )
    cur = conn.cursor()

    cur.execute('''
        SELECT
            id,
            name,
            traits,
            assigned_patterns,
            sortino_ratio,
            total_pnl,
            total_trades
        FROM agents
        WHERE status = 'active'
        AND assigned_patterns IS NOT NULL
        AND total_trades > 0
        ORDER BY
            COALESCE(sortino_ratio, 0) DESC,
            COALESCE(total_pnl, 0) DESC
        LIMIT 20
    ''')

    rows = cur.fetchall()
    cur.close()
    conn.close()

    agents = []
    for i, row in enumerate(rows):
        rank = i + 1
        if rank in ranks:
            agent_id, name, traits, patterns, sortino, pnl, trades = row
            agents.append({
                "rank": rank,
                "id": agent_id,
                "name": name,
                "traits": traits or {},
                "patterns": (patterns or {}).get("base", []),
                "sortino": sortino or 0,
                "pnl": pnl or 0,
                "trades": trades or 0
            })

    return agents


def check_pattern_entry(pattern: dict, indicators: dict, min_confidence: float = 0.3) -> Tuple[bool, float]:
    matcher = PatternMatcher(pattern=pattern, min_confidence=min_confidence)
    return matcher.should_enter(indicators)


def simulate(df, traits, patterns, config: Optional[JerkThresholdConfig] = None) -> Dict[str, Any]:
    service = ConfigurableBearProtection(config) if config else None

    risk_tolerance = traits.get("risk_tolerance", 0.5)
    position_size = 0.10 + risk_tolerance * 0.40
    stop_loss_pct = 0.05
    take_profit_pct = 0.10

    capital = 10000.0
    initial_capital = capital
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
                exit_reason = "veto_exit"
                veto_exits += 1
            elif pnl_pct <= -stop_loss_pct:
                should_exit = True
                exit_reason = "stop_loss"
            elif pnl_pct >= take_profit_pct:
                should_exit = True
                exit_reason = "take_profit"

            if should_exit:
                pnl = position["size"] * pnl_pct
                capital += pnl
                trades.append({
                    "entry_price": entry_price,
                    "exit_price": price,
                    "pnl_pct": pnl_pct,
                    "pnl": pnl,
                    "reason": exit_reason
                })
                position = None

        if not position:
            for pattern in patterns:
                should_enter, confidence = check_pattern_entry(pattern, indicators)
                if should_enter:
                    if config and regime == Regime.DEFENSIVE:
                        blocked_entries += 1
                        break

                    size = capital * position_size
                    if config:
                        size = min(size, capital * max_pos)

                    if size > 0:
                        position = {
                            "entry_price": price,
                            "size": size
                        }
                    break

        if capital > peak:
            peak = capital
        dd = (peak - capital) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    if position and len(rows) > 0:
        final_price = rows[-1].get("close", position["entry_price"])
        pnl_pct = (final_price - position["entry_price"]) / position["entry_price"]
        pnl = position["size"] * pnl_pct
        capital += pnl
        trades.append({
            "entry_price": position["entry_price"],
            "exit_price": final_price,
            "pnl_pct": pnl_pct,
            "pnl": pnl,
            "reason": "end_of_period"
        })

    total_return = (capital - initial_capital) / initial_capital
    wins = len([t for t in trades if t["pnl"] > 0])
    win_rate = wins / len(trades) if trades else 0

    return {
        "total_return": total_return,
        "total_trades": len(trades),
        "win_rate": win_rate,
        "max_drawdown": max_dd,
        "regime_hours": regime_counts,
        "veto_exits": veto_exits,
        "blocked_entries": blocked_entries
    }


def run_multi_agent_test():
    """Run jerk threshold tests across multiple agents."""

    # Agent ranks to test: 1, 3, 4, 5, 7, 8, 9, 12, 13, 14, 15
    target_ranks = [1, 3, 4, 5, 7, 8, 9, 12, 13, 14, 15]

    print("=" * 80)
    print("MULTI-AGENT JERK THRESHOLD ANALYSIS")
    print("=" * 80)
    print(f"Window: {TEST_WINDOW['name']} ({TEST_WINDOW['start'].date()} to {TEST_WINDOW['end'].date()})")
    print(f"Testing {len(target_ranks)} agents across {len(JERK_THRESHOLDS)} jerk thresholds")
    print("=" * 80)

    # Load data
    df = load_mtf_for_period(TEST_WINDOW["symbol"], TEST_WINDOW["start"], TEST_WINDOW["end"])
    if df is None or len(df) == 0:
        print("ERROR: Could not load market data")
        return

    total_hours = len(df)
    print(f"\nMarket data loaded: {total_hours} hours")

    # Load agents
    agents = get_agents_by_rank(target_ranks)
    print(f"Loaded {len(agents)} agents")

    for agent in agents:
        print(f"  #{agent['rank']}: {agent['name'][:40]} ({len(agent['patterns'])} patterns, Sortino: {agent['sortino']:.2f})")

    all_results = {
        "metadata": {
            "run_date": datetime.now().isoformat(),
            "window": TEST_WINDOW["name"],
            "total_hours": total_hours,
            "jerk_thresholds": JERK_THRESHOLDS
        },
        "by_agent": {},
        "aggregate": {}
    }

    # Test each agent
    for agent in agents:
        agent_name = f"#{agent['rank']}_{agent['name'][:25]}"
        print(f"\n{'=' * 60}")
        print(f"Agent: {agent_name}")
        print("=" * 60)

        traits = agent["traits"]
        patterns = agent["patterns"]

        # Baseline
        baseline = simulate(df, traits, patterns, config=None)
        print(f"Baseline: {baseline['total_return']:+.2%} return, {baseline['total_trades']} trades")

        if baseline["total_trades"] == 0:
            print("  (No trades - skipping threshold tests)")
            all_results["by_agent"][agent_name] = {
                "baseline": baseline,
                "note": "No trades in this period"
            }
            continue

        all_results["by_agent"][agent_name] = {
            "baseline": baseline,
            "thresholds": {}
        }

        print(f"\n{'Jerk':<6} | {'Return':<9} | {'BP Delta':<9} | {'Trades':<6} | {'Vetoes':<6} | {'Blocked':<7}")
        print("-" * 55)

        for jerk_thresh in JERK_THRESHOLDS:
            config = JerkThresholdConfig(
                name=f"jerk_{abs(jerk_thresh):.1f}",
                jerk_threshold=jerk_thresh
            )

            result = simulate(df, traits, patterns, config)
            bp_delta = result["total_return"] - baseline["total_return"]

            print(f"{jerk_thresh:<6.1f} | {result['total_return']:>+7.2%} | {bp_delta:>+7.2%} | {result['total_trades']:>4} | {result['veto_exits']:>4} | {result['blocked_entries']:>5}")

            all_results["by_agent"][agent_name]["thresholds"][f"{jerk_thresh:.1f}"] = {
                "total_return": result["total_return"],
                "bp_delta": bp_delta,
                "total_trades": result["total_trades"],
                "veto_exits": result["veto_exits"],
                "blocked_entries": result["blocked_entries"]
            }

    # Aggregate analysis
    print("\n" + "=" * 80)
    print("AGGREGATE ANALYSIS ACROSS ALL AGENTS")
    print("=" * 80)

    print(f"\n{'Jerk':<6} | {'Avg BP Delta':<12} | {'Total Vetoes':<12} | {'Total Blocked':<13} | {'Agents Helped':<12}")
    print("-" * 70)

    aggregate_data = []
    for jerk_thresh in JERK_THRESHOLDS:
        bp_deltas = []
        total_vetoes = 0
        total_blocked = 0
        agents_helped = 0

        for agent_name, agent_data in all_results["by_agent"].items():
            if "thresholds" not in agent_data:
                continue
            thresh_data = agent_data["thresholds"].get(f"{jerk_thresh:.1f}")
            if thresh_data:
                bp_deltas.append(thresh_data["bp_delta"])
                total_vetoes += thresh_data["veto_exits"]
                total_blocked += thresh_data["blocked_entries"]
                if thresh_data["bp_delta"] > 0:
                    agents_helped += 1

        avg_bp_delta = sum(bp_deltas) / len(bp_deltas) if bp_deltas else 0

        aggregate_data.append({
            "threshold": jerk_thresh,
            "avg_bp_delta": avg_bp_delta,
            "total_vetoes": total_vetoes,
            "total_blocked": total_blocked,
            "agents_helped": agents_helped
        })

        print(f"{jerk_thresh:<6.1f} | {avg_bp_delta:>+10.2%} | {total_vetoes:>10} | {total_blocked:>11} | {agents_helped:>10}")

    all_results["aggregate"] = aggregate_data

    # Find optimal
    print("\n" + "=" * 80)
    print("OPTIMAL THRESHOLD")
    print("=" * 80)

    best = max(aggregate_data, key=lambda x: x["avg_bp_delta"])
    print(f"\nBest threshold: jerk < {best['threshold']:.1f}")
    print(f"  - Average BP Delta: {best['avg_bp_delta']:+.2%}")
    print(f"  - Total veto exits: {best['total_vetoes']}")
    print(f"  - Total blocked entries: {best['total_blocked']}")
    print(f"  - Agents helped: {best['agents_helped']}")

    # Find where protection drops off
    print("\n--- Protection Dropoff Analysis ---")
    prev_helped = None
    for agg in aggregate_data:
        if prev_helped is not None and agg["agents_helped"] < prev_helped:
            print(f"Protection drops at jerk < {agg['threshold']:.1f}: {prev_helped} -> {agg['agents_helped']} agents helped")
        prev_helped = agg["agents_helped"]

    # Save results
    output_path = Path(__file__).parent.parent.parent.parent.parent / "data" / "multi_agent_jerk_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\n\nResults saved to: {output_path}")


if __name__ == "__main__":
    run_multi_agent_test()
