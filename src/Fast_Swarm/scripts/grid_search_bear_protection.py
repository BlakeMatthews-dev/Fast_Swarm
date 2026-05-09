"""
Grid Search: Bear Protection Signal Compositions.

Tests 52 combinations of:
- Signal Compositions (7): V, A, J, VA, AJ, VJ, VAJ
- Thresholds (2): Tight vs Loose
- TF Confirmation (2): 1 or 2 timeframes required

Plus baseline (no bear protection) for comparison.
"""

import polars as pl
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
from enum import Enum
import sys
import json
from itertools import product

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from Fast_Swarm.local_agents.backtest.pattern_matcher import PatternMatcher

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


# ============================================================================
# CONFIGURABLE BEAR PROTECTION WITH SIGNAL COMPOSITION
# ============================================================================

class Regime(Enum):
    DEFENSIVE = "DEFENSIVE"
    NEUTRAL = "NEUTRAL"
    AGGRESSIVE = "AGGRESSIVE"


@dataclass
class GridSearchConfig:
    """Configuration for a single grid search variant."""
    name: str

    # Which signals to use (composition)
    use_velocity: bool = True
    use_acceleration: bool = True
    use_jerk: bool = True

    # Threshold values
    exit_vel_threshold: float = 0.5      # Tight: 0.5, Loose: 1.0
    exit_acc_threshold: float = -1.5     # Tight: -1.5, Loose: -2.5
    exit_jerk_threshold: float = 0.0     # Tight: 0.0, Loose: -0.5

    entry_vel_threshold: float = -1.5    # Tight: -1.5, Loose: -0.5
    entry_acc_threshold: float = 3.0     # Tight: 3.0, Loose: 1.5

    # Multi-TF confirmation
    defensive_tf_confirm: int = 1        # 1 or 2
    aggressive_tf_confirm: int = 1

    # Position limits
    defensive_max: float = 0.0
    neutral_max: float = 0.50
    aggressive_max: float = 0.85


class ConfigurableBearProtection:
    """Bear protection with configurable signal composition."""

    def __init__(self, config: GridSearchConfig):
        self.config = config
        self._current_regime = Regime.NEUTRAL
        self._regime_since = datetime.now(timezone.utc)

    def _check_exit_signal(self, vel: float, acc: float, jerk: float) -> bool:
        """Check if exit signal fires based on configured composition."""
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

        # All enabled conditions must be met
        return all(conditions_met) if conditions_met else False

    def _check_entry_signal(self, vel: float, acc: float) -> bool:
        """Check if entry signal fires."""
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
        """Evaluate market state and return regime + max position."""
        exit_signals = []
        entry_signals = []

        # Check all timeframes
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

        # Determine regime
        if exit_confirmed:
            new_regime = Regime.DEFENSIVE
        elif entry_confirmed:
            new_regime = Regime.AGGRESSIVE
        elif len(exit_signals) == 0 and len(entry_signals) == 0:
            new_regime = Regime.NEUTRAL
        else:
            new_regime = self._current_regime

        self._current_regime = new_regime

        # Get position limit
        if new_regime == Regime.DEFENSIVE:
            return new_regime, self.config.defensive_max
        elif new_regime == Regime.AGGRESSIVE:
            return new_regime, self.config.aggressive_max
        return new_regime, self.config.neutral_max


# ============================================================================
# GRID SEARCH CONFIGURATIONS
# ============================================================================

def generate_all_configs() -> List[GridSearchConfig]:
    """Generate all 52 grid search configurations."""
    configs = []

    # Signal compositions
    compositions = [
        ("V", True, False, False),      # Velocity only
        ("A", False, True, False),      # Acceleration only
        ("J", False, False, True),      # Jerk only
        ("VA", True, True, False),      # Velocity + Acceleration
        ("AJ", False, True, True),      # Acceleration + Jerk
        ("VJ", True, False, True),      # Velocity + Jerk
        ("VAJ", True, True, True),      # All three
    ]

    # Threshold presets
    thresholds = [
        ("tight", 0.5, -1.5, 0.0, -1.5, 3.0),    # Original tight
        ("loose", 1.0, -2.5, -0.5, -0.5, 1.5),   # Looser thresholds
    ]

    # TF confirmation
    tf_confirms = [1, 2]

    # Generate all combinations
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


# ============================================================================
# DATA LOADING
# ============================================================================

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


# ============================================================================
# SIMULATION
# ============================================================================

def check_pattern_entry(pattern: dict, indicators: dict, min_confidence: float = 0.3) -> Tuple[bool, float]:
    """Use production PatternMatcher."""
    matcher = PatternMatcher(pattern=pattern, min_confidence=min_confidence)
    return matcher.should_enter(indicators)


def simulate(df, traits, patterns, config: Optional[GridSearchConfig] = None):
    """Simulate agent trading with optional bear protection config."""
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

    rows = df.to_dicts()

    for row in rows:
        price = row.get("close", 0)
        if price <= 0:
            continue

        indicators = {k: v for k, v in row.items() if isinstance(v, (int, float))}

        # Check regime
        if config:
            regime, max_pos = service.evaluate(row)
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

        # Look for entry
        if position is None:
            if config and regime == Regime.DEFENSIVE:
                pass  # Block entries
            else:
                for pattern in patterns:
                    should_enter, confidence = check_pattern_entry(pattern, indicators)
                    if should_enter:
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
        "regime_counts": regime_counts if config else None,
        "veto_exits": veto_exits if config else 0,
    }


def calculate_buy_and_hold(df) -> dict:
    """Calculate simple buy-and-hold return."""
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


# ============================================================================
# MAIN GRID SEARCH
# ============================================================================

def main():
    print("=" * 120)
    print("GRID SEARCH: BEAR PROTECTION SIGNAL COMPOSITIONS")
    print("=" * 120)
    print("\nTesting 52 configurations across canonical windows...")
    print("\nSignal Compositions: V, A, J, VA, AJ, VJ, VAJ")
    print("Thresholds: Tight vs Loose")
    print("TF Confirmation: 1 vs 2")

    # Generate all configs
    configs = generate_all_configs()
    print(f"\nGenerated {len(configs)} configurations")

    # Get agent
    agent = get_agent_from_db()
    if not agent:
        print("Agent not found!")
        return

    print(f"\nUsing agent: Fade_Bold_Switch")
    print(f"Patterns: {len(agent['patterns'])}")

    # Track results per config across all windows
    config_results = {c.name: {"bp_deltas": [], "dd_saved": [], "windows": 0} for c in configs}
    config_results["NO_BP"] = {"returns": [], "max_dds": [], "windows": 0}

    # Track per-window results for detailed output
    window_results = []

    # Process each canonical window
    for window_key, window in CANONICAL_WINDOWS.items():
        # Skip if not a crash or bull window (focus on key periods)
        is_crash = any(x in window_key for x in ["crash", "collapse", "bear"])
        is_bull = "bull" in window_key

        print(f"\n{'='*120}")
        print(f"Window: {window.name}")
        print(f"Type: {'CRASH' if is_crash else 'BULL' if is_bull else 'OTHER'}")
        print(f"Period: {window.start.date()} to {window.end.date()}")
        print("=" * 120)

        # Determine symbol
        if window.asset == "*":
            symbol = "BTC"
        else:
            symbol = window.asset.split("/")[0]

        # Load data
        df = load_mtf_for_period(symbol, window.start, window.end)

        if df is None or len(df) == 0:
            print(f"  [!] No data available")
            continue

        print(f"  Loaded {len(df):,} candles for {symbol}")

        # Get baseline (no bear protection)
        result_no_bp = simulate(df, agent["traits"], agent["patterns"], config=None)
        bh = calculate_buy_and_hold(df)

        config_results["NO_BP"]["returns"].append(result_no_bp["return"])
        config_results["NO_BP"]["max_dds"].append(result_no_bp["max_dd"])
        config_results["NO_BP"]["windows"] += 1

        print(f"\n  BASELINE (No BP): Return={result_no_bp['return']:+.1f}%, DD={result_no_bp['max_dd']:.1f}%")
        print(f"  Buy & Hold:       Return={bh['return']:+.1f}%, DD={bh['max_dd']:.1f}%")

        # Test each config
        window_config_results = []

        for config in configs:
            result = simulate(df, agent["traits"], agent["patterns"], config=config)

            bp_delta = result["return"] - result_no_bp["return"]
            dd_saved = result_no_bp["max_dd"] - result["max_dd"]

            config_results[config.name]["bp_deltas"].append(bp_delta)
            config_results[config.name]["dd_saved"].append(dd_saved)
            config_results[config.name]["windows"] += 1

            window_config_results.append({
                "config": config.name,
                "return": result["return"],
                "bp_delta": bp_delta,
                "dd_saved": dd_saved,
                "veto_exits": result["veto_exits"],
            })

        # Show top 5 for this window
        sorted_results = sorted(window_config_results, key=lambda x: x["bp_delta"], reverse=True)
        print(f"\n  Top 5 configs for this window:")
        print(f"  {'Config':<25} {'Return':>10} {'BP Delta':>12} {'DD Saved':>10}")
        print("  " + "-" * 60)
        for r in sorted_results[:5]:
            print(f"  {r['config']:<25} {r['return']:>+9.1f}% {r['bp_delta']:>+11.1f}% {r['dd_saved']:>+9.1f}%")

        window_results.append({
            "window": window_key,
            "type": "crash" if is_crash else "bull" if is_bull else "other",
            "bh_return": bh["return"],
            "no_bp_return": result_no_bp["return"],
            "results": sorted_results,
        })

    # ========================================================================
    # AGGREGATE RESULTS
    # ========================================================================

    print("\n" + "=" * 120)
    print("AGGREGATE RESULTS ACROSS ALL WINDOWS")
    print("=" * 120)

    # Calculate aggregate scores for each config
    aggregate_scores = []

    for config in configs:
        name = config.name
        data = config_results[name]

        if data["windows"] == 0:
            continue

        avg_bp_delta = sum(data["bp_deltas"]) / len(data["bp_deltas"])
        total_bp_delta = sum(data["bp_deltas"])
        avg_dd_saved = sum(data["dd_saved"]) / len(data["dd_saved"])
        total_dd_saved = sum(data["dd_saved"])

        # Score: weighted combination of returns and risk reduction
        # Prioritize protecting capital (DD saved) slightly more than returns
        score = total_bp_delta + (total_dd_saved * 0.5)

        aggregate_scores.append({
            "config": name,
            "avg_bp_delta": avg_bp_delta,
            "total_bp_delta": total_bp_delta,
            "avg_dd_saved": avg_dd_saved,
            "total_dd_saved": total_dd_saved,
            "score": score,
            "windows": data["windows"],
        })

    # Sort by score (best first)
    aggregate_scores.sort(key=lambda x: x["score"], reverse=True)

    print(f"\n{'Rank':<5} {'Config':<25} {'Avg BP Delta':>12} {'Total BP':>12} {'DD Saved':>12} {'Score':>10}")
    print("-" * 80)

    for i, r in enumerate(aggregate_scores, 1):
        marker = "***" if i <= 3 else ""
        print(f"{i:<5} {r['config']:<25} {r['avg_bp_delta']:>+11.1f}% {r['total_bp_delta']:>+11.1f}% {r['total_dd_saved']:>+11.1f}% {r['score']:>9.1f} {marker}")
        if i == 10:
            print("-" * 80)

    # ========================================================================
    # ANALYSIS BY COMPOSITION
    # ========================================================================

    print("\n" + "=" * 120)
    print("ANALYSIS BY SIGNAL COMPOSITION")
    print("=" * 120)

    compositions = ["V", "A", "J", "VA", "AJ", "VJ", "VAJ"]

    for comp in compositions:
        comp_configs = [r for r in aggregate_scores if r["config"].startswith(f"{comp}_")]
        if comp_configs:
            avg_delta = sum(c["total_bp_delta"] for c in comp_configs) / len(comp_configs)
            avg_dd = sum(c["total_dd_saved"] for c in comp_configs) / len(comp_configs)
            best = max(comp_configs, key=lambda x: x["score"])
            print(f"\n{comp:>5}: Avg BP Delta={avg_delta:+.1f}%, Avg DD Saved={avg_dd:+.1f}%")
            print(f"       Best: {best['config']} (Score: {best['score']:.1f})")

    # ========================================================================
    # ANALYSIS BY THRESHOLD
    # ========================================================================

    print("\n" + "=" * 120)
    print("ANALYSIS BY THRESHOLD SETTING")
    print("=" * 120)

    tight_configs = [r for r in aggregate_scores if "_tight_" in r["config"]]
    loose_configs = [r for r in aggregate_scores if "_loose_" in r["config"]]

    if tight_configs:
        avg_tight = sum(c["total_bp_delta"] for c in tight_configs) / len(tight_configs)
        avg_tight_dd = sum(c["total_dd_saved"] for c in tight_configs) / len(tight_configs)
        print(f"\nTIGHT thresholds: Avg BP Delta={avg_tight:+.1f}%, Avg DD Saved={avg_tight_dd:+.1f}%")

    if loose_configs:
        avg_loose = sum(c["total_bp_delta"] for c in loose_configs) / len(loose_configs)
        avg_loose_dd = sum(c["total_dd_saved"] for c in loose_configs) / len(loose_configs)
        print(f"LOOSE thresholds: Avg BP Delta={avg_loose:+.1f}%, Avg DD Saved={avg_loose_dd:+.1f}%")

    # ========================================================================
    # ANALYSIS BY TF CONFIRMATION
    # ========================================================================

    print("\n" + "=" * 120)
    print("ANALYSIS BY TF CONFIRMATION")
    print("=" * 120)

    tf1_configs = [r for r in aggregate_scores if "_TF1" in r["config"]]
    tf2_configs = [r for r in aggregate_scores if "_TF2" in r["config"]]

    if tf1_configs:
        avg_tf1 = sum(c["total_bp_delta"] for c in tf1_configs) / len(tf1_configs)
        avg_tf1_dd = sum(c["total_dd_saved"] for c in tf1_configs) / len(tf1_configs)
        print(f"\nTF1 (1 timeframe): Avg BP Delta={avg_tf1:+.1f}%, Avg DD Saved={avg_tf1_dd:+.1f}%")

    if tf2_configs:
        avg_tf2 = sum(c["total_bp_delta"] for c in tf2_configs) / len(tf2_configs)
        avg_tf2_dd = sum(c["total_dd_saved"] for c in tf2_configs) / len(tf2_configs)
        print(f"TF2 (2 timeframes): Avg BP Delta={avg_tf2:+.1f}%, Avg DD Saved={avg_tf2_dd:+.1f}%")

    # ========================================================================
    # TOP 10 RECOMMENDATIONS
    # ========================================================================

    print("\n" + "=" * 120)
    print("TOP 10 CONFIGURATIONS (RECOMMENDED)")
    print("=" * 120)

    for i, r in enumerate(aggregate_scores[:10], 1):
        print(f"\n{i}. {r['config']}")
        print(f"   Total BP Delta: {r['total_bp_delta']:+.1f}%")
        print(f"   Total DD Saved: {r['total_dd_saved']:+.1f}%")
        print(f"   Composite Score: {r['score']:.1f}")

        # Parse config name to show settings
        parts = r['config'].split('_')
        comp = parts[0]
        thresh = parts[1]
        tf = parts[2]

        signals = []
        if 'V' in comp:
            signals.append("Velocity")
        if 'A' in comp:
            signals.append("Acceleration")
        if 'J' in comp:
            signals.append("Jerk")

        print(f"   Signals: {', '.join(signals)}")
        print(f"   Thresholds: {thresh.upper()}")
        print(f"   TF Confirm: {tf}")

    # ========================================================================
    # SAVE RESULTS
    # ========================================================================

    output_path = Path("c:/fast_swarm/data/grid_search_results.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        "timestamp": datetime.now().isoformat(),
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
    print("FINAL RECOMMENDATION")
    print("=" * 120)

    if aggregate_scores:
        best = aggregate_scores[0]
        print(f"\nBest configuration: {best['config']}")
        print(f"  - BP Delta: {best['total_bp_delta']:+.1f}% (avg {best['avg_bp_delta']:+.1f}% per window)")
        print(f"  - DD Saved: {best['total_dd_saved']:+.1f}% (avg {best['avg_dd_saved']:+.1f}% per window)")
        print(f"  - Score: {best['score']:.1f}")


if __name__ == "__main__":
    main()
