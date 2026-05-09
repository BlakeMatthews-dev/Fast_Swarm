"""
Granular Jerk Threshold Analysis

Tests jerk thresholds from 0.0 to -2.0 in 0.1 increments
while holding acceleration at -2.5 (optimal) and TF confirm at 2.

This isolates the effect of jerk threshold on bear protection performance.
Uses AJ (Acceleration + Jerk) signal composition only.
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
    """Config for testing a specific jerk threshold with AJ signals."""
    name: str
    jerk_threshold: float
    # Fixed parameters (optimal from grid search)
    acc_threshold: float = -2.5
    tf_confirm: int = 2
    # AJ only - no velocity
    use_velocity: bool = False
    use_acceleration: bool = True
    use_jerk: bool = True
    # Entry thresholds (for AGGRESSIVE)
    entry_vel_threshold: float = -0.5
    entry_acc_threshold: float = 1.5
    # Position limits
    defensive_max: float = 0.0
    neutral_max: float = 0.50
    aggressive_max: float = 0.85


class ConfigurableBearProtection:
    def __init__(self, config: JerkThresholdConfig):
        self.config = config
        self._current_regime = Regime.NEUTRAL

    def _check_exit_signal(self, vel: float, acc: float, jerk: float) -> bool:
        """AJ exit: acceleration AND jerk must both be below thresholds."""
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
        """Entry signal for AGGRESSIVE regime."""
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


# Jerk thresholds to test: 0.0 to -2.0 in 0.1 increments (21 values)
JERK_THRESHOLDS = [round(x * 0.1, 1) for x in range(0, -21, -1)]
# [0.0, -0.1, -0.2, ..., -1.9, -2.0]


# Test windows - mix of bulls and crashes
TEST_WINDOWS = [
    # BULL MARKETS
    {
        "name": "BTC 2021 Bull",
        "symbol": "BTC",
        "start": datetime(2021, 1, 1, 0, 0, 0),
        "end": datetime(2021, 4, 14, 23, 59, 59),
        "type": "bull"
    },
    {
        "name": "BTC 2020-2021 Recovery",
        "symbol": "BTC",
        "start": datetime(2020, 10, 1, 0, 0, 0),
        "end": datetime(2021, 1, 1, 0, 0, 0),
        "type": "bull"
    },
    {
        "name": "BTC 2023 Recovery",
        "symbol": "BTC",
        "start": datetime(2023, 1, 1, 0, 0, 0),
        "end": datetime(2023, 7, 1, 0, 0, 0),
        "type": "bull"
    },
    {
        "name": "BTC 2024 ETF Rally",
        "symbol": "BTC",
        "start": datetime(2024, 1, 1, 0, 0, 0),
        "end": datetime(2024, 3, 15, 0, 0, 0),
        "type": "bull"
    },
    # CRASH MARKETS
    {
        "name": "COVID Crash",
        "symbol": "BTC",
        "start": datetime(2020, 2, 1, 0, 0, 0),
        "end": datetime(2020, 4, 1, 0, 0, 0),
        "type": "crash"
    },
    {
        "name": "May 2021 Crash",
        "symbol": "BTC",
        "start": datetime(2021, 5, 1, 0, 0, 0),
        "end": datetime(2021, 6, 30, 0, 0, 0),
        "type": "crash"
    },
    {
        "name": "Nov 2021 Top",
        "symbol": "BTC",
        "start": datetime(2021, 11, 1, 0, 0, 0),
        "end": datetime(2021, 12, 31, 0, 0, 0),
        "type": "crash"
    },
    {
        "name": "Luna Collapse",
        "symbol": "BTC",
        "start": datetime(2022, 5, 1, 0, 0, 0),
        "end": datetime(2022, 6, 30, 0, 0, 0),
        "type": "crash"
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


def simulate(df, traits, patterns, config: Optional[JerkThresholdConfig] = None) -> Dict[str, Any]:
    """Run backtest simulation with given config."""
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

    # Close any open position at end
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
        "blocked_entries": blocked_entries,
        "trades": trades
    }


def run_granular_jerk_tests():
    """Run all jerk threshold tests."""

    print("=" * 70)
    print("GRANULAR JERK THRESHOLD ANALYSIS")
    print("=" * 70)
    print("Fixed parameters:")
    print("  - Signals: Acceleration + Jerk (AJ) only")
    print("  - Acceleration threshold: -2.5 (optimal from grid search)")
    print("  - TF confirmation: 2 (multi-timeframe)")
    print(f"  - Jerk thresholds to test: {len(JERK_THRESHOLDS)} values from 0.0 to -2.0")
    print("=" * 70)

    # Get agent
    agent = get_agent_from_db()
    if not agent:
        print("ERROR: Could not load agent from database")
        return

    traits = agent["traits"]
    patterns = agent["patterns"]
    print(f"\nAgent loaded: {len(patterns)} patterns")

    all_results = {
        "metadata": {
            "run_date": datetime.now().isoformat(),
            "fixed_params": {
                "signals": "AJ (Acceleration + Jerk)",
                "acceleration_threshold": -2.5,
                "tf_confirm": 2
            },
            "jerk_thresholds_tested": JERK_THRESHOLDS,
            "windows_tested": [w["name"] for w in TEST_WINDOWS]
        },
        "by_window": {},
        "by_threshold": {}
    }

    # Process each window
    for window in TEST_WINDOWS:
        window_name = window["name"]
        window_type = window["type"]
        print(f"\n{'=' * 50}")
        print(f"Window: {window_name} ({window_type})")
        print("=" * 50)

        df = load_mtf_for_period(window["symbol"], window["start"], window["end"])
        if df is None or len(df) == 0:
            print(f"  No data available")
            continue

        total_hours = len(df)
        print(f"  Data loaded: {total_hours} hours")

        # First run baseline (no bear protection)
        baseline_result = simulate(df, traits, patterns, config=None)
        baseline_return = baseline_result["total_return"]
        print(f"  Baseline (no BP): {baseline_return:+.2%} return, {baseline_result['total_trades']} trades")

        all_results["by_window"][window_name] = {
            "type": window_type,
            "total_hours": total_hours,
            "baseline": baseline_result,
            "thresholds": {}
        }

        # Test each jerk threshold
        print(f"\n  {'Jerk':<8} | {'Return':<10} | {'BP Delta':<10} | {'DEFENS %':<10} | {'Trades':<8} | {'Vetoes':<8}")
        print(f"  {'-' * 65}")

        for jerk_thresh in JERK_THRESHOLDS:
            config = JerkThresholdConfig(
                name=f"jerk_{abs(jerk_thresh):.1f}",
                jerk_threshold=jerk_thresh
            )

            result = simulate(df, traits, patterns, config)
            bp_delta = result["total_return"] - baseline_return

            defensive_hours = result["regime_hours"]["DEFENSIVE"]
            defensive_pct = defensive_hours / total_hours * 100 if total_hours > 0 else 0

            print(f"  {jerk_thresh:<8.1f} | {result['total_return']:>+8.2%} | {bp_delta:>+8.2%} | {defensive_pct:>8.1f}% | {result['total_trades']:>6} | {result['veto_exits']:>6}")

            all_results["by_window"][window_name]["thresholds"][f"{jerk_thresh:.1f}"] = {
                "total_return": result["total_return"],
                "bp_delta": bp_delta,
                "total_trades": result["total_trades"],
                "defensive_pct": defensive_pct,
                "veto_exits": result["veto_exits"],
                "blocked_entries": result["blocked_entries"],
                "regime_hours": result["regime_hours"]
            }

    # Aggregate by threshold
    print("\n" + "=" * 70)
    print("AGGREGATE ANALYSIS BY JERK THRESHOLD")
    print("=" * 70)

    bull_windows = [w["name"] for w in TEST_WINDOWS if w["type"] == "bull"]
    crash_windows = [w["name"] for w in TEST_WINDOWS if w["type"] == "crash"]

    print(f"\n--- BULL MARKETS (minimize drag) ---")
    print(f"{'Jerk':<8} | {'Avg BP Delta':<12} | {'Avg DEFENS %':<12} | {'Avg Trades':<10}")
    print("-" * 50)

    bull_analysis = []
    for jerk_thresh in JERK_THRESHOLDS:
        bp_deltas = []
        defensive_pcts = []
        trades = []

        for window_name in bull_windows:
            if window_name in all_results["by_window"]:
                thresh_data = all_results["by_window"][window_name]["thresholds"].get(f"{jerk_thresh:.1f}")
                if thresh_data:
                    bp_deltas.append(thresh_data["bp_delta"])
                    defensive_pcts.append(thresh_data["defensive_pct"])
                    trades.append(thresh_data["total_trades"])

        avg_bp_delta = sum(bp_deltas) / len(bp_deltas) if bp_deltas else 0
        avg_defensive = sum(defensive_pcts) / len(defensive_pcts) if defensive_pcts else 0
        avg_trades = sum(trades) / len(trades) if trades else 0

        bull_analysis.append({
            "threshold": jerk_thresh,
            "avg_bp_delta": avg_bp_delta,
            "avg_defensive_pct": avg_defensive,
            "avg_trades": avg_trades
        })

        print(f"{jerk_thresh:<8.1f} | {avg_bp_delta:>+10.2%} | {avg_defensive:>10.1f}% | {avg_trades:>8.1f}")

    print(f"\n--- CRASH MARKETS (maximize protection) ---")
    print(f"{'Jerk':<8} | {'Avg BP Delta':<12} | {'Avg DEFENS %':<12} | {'Avg Vetoes':<10}")
    print("-" * 50)

    crash_analysis = []
    for jerk_thresh in JERK_THRESHOLDS:
        bp_deltas = []
        defensive_pcts = []
        vetoes = []

        for window_name in crash_windows:
            if window_name in all_results["by_window"]:
                thresh_data = all_results["by_window"][window_name]["thresholds"].get(f"{jerk_thresh:.1f}")
                if thresh_data:
                    bp_deltas.append(thresh_data["bp_delta"])
                    defensive_pcts.append(thresh_data["defensive_pct"])
                    vetoes.append(thresh_data["veto_exits"])

        avg_bp_delta = sum(bp_deltas) / len(bp_deltas) if bp_deltas else 0
        avg_defensive = sum(defensive_pcts) / len(defensive_pcts) if defensive_pcts else 0
        avg_vetoes = sum(vetoes) / len(vetoes) if vetoes else 0

        crash_analysis.append({
            "threshold": jerk_thresh,
            "avg_bp_delta": avg_bp_delta,
            "avg_defensive_pct": avg_defensive,
            "avg_vetoes": avg_vetoes
        })

        print(f"{jerk_thresh:<8.1f} | {avg_bp_delta:>+10.2%} | {avg_defensive:>10.1f}% | {avg_vetoes:>8.1f}")

    # Find optimal thresholds
    print("\n" + "=" * 70)
    print("OPTIMAL THRESHOLD ANALYSIS")
    print("=" * 70)

    # Best for bulls (closest to 0 BP delta)
    best_bull = min(bull_analysis, key=lambda x: abs(x["avg_bp_delta"]))
    print(f"\nBest for Bulls: jerk < {best_bull['threshold']:.1f}")
    print(f"  - Average BP Delta: {best_bull['avg_bp_delta']:+.2%}")
    print(f"  - Average DEFENSIVE time: {best_bull['avg_defensive_pct']:.1f}%")

    # Best for crashes (highest positive BP delta)
    best_crash = max(crash_analysis, key=lambda x: x["avg_bp_delta"])
    print(f"\nBest for Crashes: jerk < {best_crash['threshold']:.1f}")
    print(f"  - Average BP Delta: {best_crash['avg_bp_delta']:+.2%}")
    print(f"  - Average DEFENSIVE time: {best_crash['avg_defensive_pct']:.1f}%")

    # Find sweet spot
    print("\n--- FINDING SWEET SPOT (Bull drag < 2% AND positive crash protection) ---")
    candidates = []
    for bull, crash in zip(bull_analysis, crash_analysis):
        net = bull["avg_bp_delta"] + crash["avg_bp_delta"]
        is_candidate = bull["avg_bp_delta"] > -0.02 and crash["avg_bp_delta"] > 0
        marker = " <-- CANDIDATE" if is_candidate else ""
        if is_candidate:
            candidates.append(bull["threshold"])
        print(f"jerk < {bull['threshold']:.1f}: Bull {bull['avg_bp_delta']:+.2%} + Crash {crash['avg_bp_delta']:+.2%} = Net {net:+.2%}{marker}")

    if candidates:
        print(f"\nRECOMMENDED: jerk < {candidates[0]:.1f} (first threshold meeting criteria)")

    # Save results
    all_results["analysis"] = {
        "bull": bull_analysis,
        "crash": crash_analysis,
        "best_for_bulls": best_bull,
        "best_for_crashes": best_crash,
        "sweet_spot_candidates": candidates
    }

    output_path = Path(__file__).parent.parent.parent.parent.parent / "data" / "granular_jerk_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\n\nResults saved to: {output_path}")


if __name__ == "__main__":
    run_granular_jerk_tests()
