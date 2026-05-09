"""
Validate Top Agents Against Full Dataset.

Takes the top performers from a previous evolution run and validates them
against the full historical dataset (not just the canonical periods they
were trained on).

This script:
1. Loads top N agents from evolution_run.db
2. Tests each against ALL assets in enhanced_candles.db
3. Generates out-of-sample (OOS) metrics
4. Produces a validation report
"""

import json
import random
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from Fast_Swarm.local_agents.backtest.data import OHLCVLoader
from Fast_Swarm.local_agents.backtest.engine import BacktestConfig, LocalBacktestEngine
from Fast_Swarm.local_agents.core.evolution import evaluate_agent_fitness
from Fast_Swarm.local_agents.core.state import AgentRecord


@dataclass
class ValidationConfig:
    """Configuration for validation run."""

    # Source
    evolution_db: str = None
    top_n_agents: int = 20

    # Testing
    assets: list = None  # None = use all available
    timeframe: str = "1h"
    windows_per_asset: int = 5
    candles_per_window: int = 2000

    # Output
    output_report: str = None

    def __post_init__(self):
        if self.evolution_db is None:
            self.evolution_db = str(Path(__file__).parent.parent / "data" / "evolution_run.db")
        if self.output_report is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.output_report = str(Path(__file__).parent.parent / "data" / f"validation_report_{timestamp}.md")


def load_top_agents(db_path: str, top_n: int = 20) -> list[dict]:
    """Load top N agents from evolution database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    agents = conn.execute(
        """
        SELECT agent_id, agent_name, generation, fitness_score, traits, pattern_ids, pattern_weights
        FROM agents
        WHERE fitness_score IS NOT NULL
        ORDER BY fitness_score DESC
        LIMIT ?
    """,
        (top_n,),
    ).fetchall()

    result = []
    for a in agents:
        result.append(
            {
                "agent_id": a["agent_id"],
                "agent_name": a["agent_name"],
                "generation": a["generation"],
                "in_sample_fitness": a["fitness_score"],
                "traits": json.loads(a["traits"]),
                "pattern_ids": json.loads(a["pattern_ids"]) if a["pattern_ids"] else [],
                "pattern_weights": json.loads(a["pattern_weights"]) if a["pattern_weights"] else {},
            }
        )

    conn.close()
    return result


def generate_test_windows(loader: OHLCVLoader, config: ValidationConfig) -> list[dict]:
    """Generate random test windows across all available assets."""
    windows = []

    # Get available assets
    if config.assets:
        assets = config.assets
    else:
        assets = loader.get_available_assets(config.timeframe)

    print(f"Generating test windows for {len(assets)} assets...")

    for asset in assets:
        try:
            data_range = loader.get_date_range(asset, config.timeframe)
            if data_range == (0, 0):
                print(f"  WARNING: No data for {asset}, skipping")
                continue

            min_ts, max_ts = data_range
            range_ms = max_ts - min_ts
            window_ms = config.candles_per_window * 3600 * 1000  # 1h candles

            if range_ms < window_ms:
                print(f"  WARNING: {asset} insufficient data, skipping")
                continue

            for i in range(config.windows_per_asset):
                start_ts = min_ts + random.randint(0, range_ms - window_ms)
                end_ts = start_ts + window_ms

                windows.append(
                    {
                        "assets": [asset],
                        "timeframe": config.timeframe,
                        "start_ts": start_ts,
                        "end_ts": end_ts,
                        "window_id": f"oos-{asset}-{i}",
                    }
                )
        except Exception as e:
            print(f"  ERROR with {asset}: {e}")
            continue

    print(f"Created {len(windows)} test windows")
    return windows


def validate_agent(
    agent_data: dict,
    engine: LocalBacktestEngine,
    windows: list[dict],
    patterns: list[dict],
) -> dict:
    """Run OOS validation for a single agent."""

    # Create a minimal AgentRecord for backtesting
    agent = AgentRecord(
        agent_id=agent_data["agent_id"],
        agent_name=agent_data["agent_name"],
        generation=agent_data["generation"],
        traits=agent_data["traits"],
        pattern_ids=agent_data["pattern_ids"],
        pattern_weights=agent_data["pattern_weights"],
        status="active",
        fitness_score=agent_data["in_sample_fitness"],
    )

    # Run backtests
    all_trades = []
    for window in windows:
        trades = engine.run(agent, window)
        all_trades.extend(trades)

    # Calculate OOS fitness
    if len(all_trades) >= 10:
        oos_fitness = evaluate_agent_fitness(agent, all_trades)
    else:
        oos_fitness = 0.0

    # Calculate OOS metrics
    if all_trades:
        wins = [t for t in all_trades if t.pnl_pct > 0]
        total_pnl = sum(t.pnl_pct for t in all_trades)
        win_rate = len(wins) / len(all_trades) * 100
        avg_pnl = total_pnl / len(all_trades)
    else:
        total_pnl = 0
        win_rate = 0
        avg_pnl = 0

    return {
        "agent_id": agent_data["agent_id"],
        "agent_name": agent_data["agent_name"],
        "in_sample_fitness": agent_data["in_sample_fitness"],
        "oos_fitness": oos_fitness,
        "fitness_decay": agent_data["in_sample_fitness"] - oos_fitness if agent_data["in_sample_fitness"] else 0,
        "oos_trades": len(all_trades),
        "oos_win_rate": win_rate,
        "oos_total_pnl": total_pnl,
        "oos_avg_pnl": avg_pnl,
        "traits": agent_data["traits"],
    }


def generate_report(results: list[dict], config: ValidationConfig) -> str:
    """Generate markdown validation report."""

    # Sort by OOS fitness
    sorted_results = sorted(results, key=lambda x: x["oos_fitness"], reverse=True)

    report = f"""# Agent Validation Report

**Generated**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Source**: {config.evolution_db}
**Agents Tested**: {len(results)}
**Test Windows**: {config.windows_per_asset} per asset × {len(config.assets or [])} assets

---

## Summary Statistics

| Metric | Value |
|--------|-------|
| Avg In-Sample Fitness | {sum(r["in_sample_fitness"] for r in results) / len(results):.1f} |
| Avg OOS Fitness | {sum(r["oos_fitness"] for r in results) / len(results):.1f} |
| Avg Fitness Decay | {sum(r["fitness_decay"] for r in results) / len(results):.1f} |
| Agents with OOS > 50 | {sum(1 for r in results if r["oos_fitness"] > 50)} |
| Agents with < 20% decay | {sum(1 for r in results if r["fitness_decay"] < r["in_sample_fitness"] * 0.2)} |

---

## Top 10 OOS Performers

| Rank | Agent | Gen | In-Sample | OOS | Decay | Trades | Win% | Avg PnL |
|------|-------|-----|-----------|-----|-------|--------|------|---------|
"""

    for i, r in enumerate(sorted_results[:10], 1):
        report += f"| {i} | {r['agent_name'][:25]} | {r.get('generation', '?')} | {r['in_sample_fitness']:.1f} | {r['oos_fitness']:.1f} | {r['fitness_decay']:+.1f} | {r['oos_trades']} | {r['oos_win_rate']:.1f}% | {r['oos_avg_pnl']:+.3f}% |\n"

    report += """

---

## Decay Analysis

"""

    # Group by decay severity
    low_decay = [r for r in results if r["fitness_decay"] < 5]
    med_decay = [r for r in results if 5 <= r["fitness_decay"] < 15]
    high_decay = [r for r in results if r["fitness_decay"] >= 15]

    report += f"""| Decay Level | Count | Interpretation |
|-------------|-------|----------------|
| Low (< 5 pts) | {len(low_decay)} | Robust - generalizes well |
| Medium (5-15 pts) | {len(med_decay)} | Acceptable - some overfit |
| High (> 15 pts) | {len(high_decay)} | Overfit - poor OOS |

---

## Trait Correlation with OOS Success

"""

    # Calculate trait correlations
    trait_names = [
        "risk_tolerance",
        "hold_duration_bias",
        "volatility_seeking",
        "momentum_vs_reversion",
        "sentiment_weight",
        "exit_aggression",
        "lookback_preference",
    ]

    report += "| Trait | Top 5 OOS Avg | Bottom 5 OOS Avg | Diff |\n"
    report += "|-------|---------------|------------------|------|\n"

    top_5 = sorted_results[:5]
    bottom_5 = sorted_results[-5:]

    for trait in trait_names:
        top_avg = sum(r["traits"].get(trait, 0.5) for r in top_5) / 5
        bot_avg = sum(r["traits"].get(trait, 0.5) for r in bottom_5) / 5
        diff = top_avg - bot_avg
        marker = "***" if abs(diff) > 0.15 else "**" if abs(diff) > 0.10 else "*" if abs(diff) > 0.05 else ""
        report += f"| {trait} | {top_avg:.3f} | {bot_avg:.3f} | {diff:+.3f} {marker} |\n"

    report += """

---

## Recommendations

Based on OOS validation:

"""

    # Identify agents worth keeping
    robust_agents = [r for r in results if r["oos_fitness"] > 50 and r["fitness_decay"] < 10]

    if robust_agents:
        report += f"### Robust Agents ({len(robust_agents)} found)\n\n"
        report += "These agents generalized well and should be preserved:\n\n"
        for r in sorted(robust_agents, key=lambda x: x["oos_fitness"], reverse=True)[:5]:
            traits = r["traits"]
            report += f"- **{r['agent_name']}**: OOS {r['oos_fitness']:.1f}, risk={traits.get('risk_tolerance', 0):.2f}, hold={traits.get('hold_duration_bias', 0):.2f}\n"
    else:
        report += "### No Robust Agents Found\n\nAll agents showed significant decay. Consider:\n- Reducing training epochs\n- Increasing dataset diversity\n- Simplifying pattern conditions\n"

    return report


def main():
    """Run validation on top agents."""
    print("=" * 60)
    print("AGENT VALIDATION - Out of Sample Testing")
    print("=" * 60)

    config = ValidationConfig(
        top_n_agents=20,
        windows_per_asset=5,
        candles_per_window=2000,
    )

    # Load patterns
    from Fast_Swarm.local_agents.run_evolution import load_patterns_from_curated_json

    patterns = load_patterns_from_curated_json(500)
    print(f"Loaded {len(patterns)} patterns")

    # Initialize loader
    loader = OHLCVLoader()

    # Get all available assets
    all_assets = loader.get_available_assets(config.timeframe)
    config.assets = all_assets
    print(f"Found {len(all_assets)} assets in enhanced_candles.db")

    # Load top agents
    print(f"\nLoading top {config.top_n_agents} agents from {config.evolution_db}...")
    agents = load_top_agents(config.evolution_db, config.top_n_agents)
    print(f"Loaded {len(agents)} agents")

    for a in agents[:5]:
        print(f"  - {a['agent_name']}: fitness={a['in_sample_fitness']:.1f}")

    # Generate test windows
    print("\nGenerating OOS test windows...")
    windows = generate_test_windows(loader, config)

    if not windows:
        print("ERROR: No test windows generated!")
        return

    # Initialize engine
    engine = LocalBacktestEngine(
        config=BacktestConfig(
            initial_balance=10000,
            max_position_pct=0.10,
            default_stop_loss_pct=0.05,
            default_take_profit_pct=0.10,
        ),
        patterns=patterns,
        loader=loader,
    )

    # Validate each agent
    print("\nRunning OOS validation...")
    results = []

    for i, agent_data in enumerate(agents, 1):
        print(f"  [{i}/{len(agents)}] {agent_data['agent_name']}...", end=" ")
        result = validate_agent(agent_data, engine, windows, patterns)
        results.append(result)
        print(f"OOS fitness: {result['oos_fitness']:.1f} (decay: {result['fitness_decay']:+.1f})")

    # Generate report
    print("\nGenerating validation report...")
    report = generate_report(results, config)

    with open(config.output_report, "w") as f:
        f.write(report)

    print(f"\nReport saved to: {config.output_report}")

    # Quick summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    avg_decay = sum(r["fitness_decay"] for r in results) / len(results)
    robust = [r for r in results if r["oos_fitness"] > 50 and r["fitness_decay"] < 10]

    print(f"  Avg Fitness Decay: {avg_decay:.1f} pts")
    print(f"  Robust Agents: {len(robust)} / {len(results)}")

    if robust:
        best = max(robust, key=lambda x: x["oos_fitness"])
        print(f"  Best OOS Performer: {best['agent_name']} (OOS: {best['oos_fitness']:.1f})")


if __name__ == "__main__":
    main()
