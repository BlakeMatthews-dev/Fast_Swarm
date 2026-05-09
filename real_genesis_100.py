#!/usr/bin/env python3
"""
Real Local Agents Genesis - Spawn 100 agents with FULL AI trait generation.
This runs the actual spawn_agent function with LLM (or heuristic) pattern selection.
Expected time: 2-3 minutes (10-20 seconds per agent is normal).
Run: python real_genesis_100.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import time

from Fast_Swarm.local_agents.backtest.engine import BacktestConfig, ExitStrategy, LocalBacktestEngine
from Fast_Swarm.local_agents.core.genesis import spawn_agent

# =============================================================================
# Real Genesis Spawn & Backtest
# =============================================================================


def main():
    print("=" * 80)
    print("REAL LOCAL AGENTS GENESIS - 100 agents with full trait generation")
    print("Expected time: 2-3 minutes (full AI trait generation per agent)")
    print("=" * 80)

    # 1. Load patterns
    print("\n[1] Loading available patterns...")
    available_patterns = [
        {
            "pattern_id": f"pattern_{i:03d}",
            "name": f"Pattern {i}",
            "type": "momentum" if i % 2 == 0 else "reversion",
            "volatility": "high" if i % 3 == 0 else "medium",
            "win_rate_pct": 45 + (i % 10) * 2,
        }
        for i in range(50)
    ]
    print(f"    Loaded {len(available_patterns)} patterns")

    # 2. Spawn 100 agents - REAL GENESIS
    print("\n[2] Spawning 100 agents via REAL spawn_agent (full trait generation)...")
    print("    This will take 2-3 minutes (10-20s per agent is normal)...")
    print()

    start_spawn = time.time()
    agents = []

    for i in range(100):
        agent_start = time.time()

        try:
            # Call the REAL spawn_agent function
            # This includes:
            # - generate_traits() with seeded random
            # - derive_dependent_traits()
            # - derive_threshold_traits()
            # - generate_full_agent_name()
            # - select_patterns_heuristic()
            # - generate_philosophy_heuristic()
            agent = spawn_agent(
                seed=42 + i * 1000,
                available_patterns=available_patterns,
                generation=1,
                use_llm=False,  # Set to True if Ollama is running for LLM pattern selection
            )

            agents.append(agent)

            agent_time = time.time() - agent_start
            elapsed_total = time.time() - start_spawn

            if (i + 1) % 10 == 0:
                eta_remaining = (elapsed_total / (i + 1)) * (100 - (i + 1))
                print(
                    f"    Spawned {i + 1:3d}/100 agents  |  Last: {agent_time:.2f}s  |  Total: {elapsed_total:.1f}s  |  ETA: {eta_remaining:.0f}s"
                )

        except Exception as e:
            print(f"    ERROR spawning agent {i}: {type(e).__name__}: {e}")
            continue

    spawn_time = time.time() - start_spawn
    print(f"\n    [OK] Spawned {len(agents)} agents in {spawn_time:.1f}s")
    print(f"    Average: {spawn_time / len(agents):.2f}s per agent")

    # 3. Show agent samples
    print("\n[3] SAMPLE SPAWNED AGENTS (first 3):")
    for i, agent in enumerate(agents[:3]):
        print(f"    Agent {i + 1}: {agent.name}")
        print(f"      ID: {agent.agent_id}")
        print(f"      Generation: {agent.generation}")
        print(f"      Traits (22): {len(agent.traits)} keys")
        print(f"      Patterns selected: {len(agent.pattern_ids)}")
        print(f"      Philosophy: {agent.trading_philosophy[:70]}...")
        print()

    # 4. Generate synthetic OHLCV data
    print("[4] Generating synthetic OHLCV data (200 candles)...")
    import random

    random.seed(42)
    candles = []
    base_price = 50000.0
    base_ts = 1700000000

    for i in range(200):
        rsi = 50.0 + 25.0 * (i % 50) / 50.0 if i % 50 < 25 else 50.0 + 25.0 * (50 - i % 50) / 50.0
        price_change = 100.0 * (i % 20 - 10) / 10.0
        close = base_price + price_change

        candle = {
            "timestamp": base_ts + i * 3600,
            "open": close - 50,
            "high": close + 100,
            "low": close - 100,
            "close": close,
            "volume": 1000.0 + random.random() * 500,
        }
        candles.append(candle)
    print("    [OK] Generated 200 candles")

    # 5. Backtest all 100 agents
    print(f"\n[5] Running backtest on {len(agents)} agents...")
    start_backtest = time.time()

    backtest_results = []
    engine = LocalBacktestEngine()
    config = BacktestConfig(
        min_confidence=0.3,
        exit_strategy=ExitStrategy.TRAILING_2PCT,
        trailing_stop_pct=2.0,
    )

    for i, agent in enumerate(agents):
        if not agent.pattern_ids:
            continue

        pattern_id = agent.pattern_ids[0]
        pattern = {
            "pattern_id": pattern_id,
            "entry_conditions": [{"indicator": "rsi", "min": 30, "max": 70}],
            "exit_conditions": [{"indicator": "rsi", "min": 70, "max": 100}],
            "direction": "long",
        }

        try:
            result = engine.run(
                agent=agent,
                dataset={"assets": ["BTC"], "timeframe": "1h"},
            )

            total_trades = len(result)
            if total_trades == 0:
                continue

            # Simple fitness calculation from trades
            wins = sum(1 for t in result if t.pnl_pct > 0)
            win_rate = wins / total_trades if total_trades > 0 else 0
            avg_pnl = sum(t.pnl_pct for t in result) / total_trades if total_trades > 0 else 0

            fitness = (
                (win_rate * 50) + (max(-50, min(50, avg_pnl * 10)))  # Clip avg_pnl to [-50, 50]
            )
            fitness = max(0.0, min(100.0, fitness))

            backtest_results.append(
                {
                    "agent_id": agent.agent_id,
                    "agent_name": agent.name,
                    "trades": total_trades,
                    "fitness": fitness,
                    "win_rate": win_rate,
                    "roi": avg_pnl,
                }
            )
        except Exception:
            pass

        if (i + 1) % 20 == 0:
            print(f"    ... backtested {i + 1}/{len(agents)} agents")

    backtest_time = time.time() - start_backtest
    print(f"    [OK] Backtested {len(backtest_results)} agents in {backtest_time:.2f}s")

    # 6. Display results
    print("\n[6] BACKTEST RESULTS - TOP 10 agents:")
    print(f"\n    {'Agent Name':<35} {'Trades':>7} {'Fitness':>8} {'Win%':>7} {'Avg PnL%':>8}")
    print(f"    {'-' * 80}")

    backtest_results.sort(key=lambda x: x["fitness"], reverse=True)

    for res in backtest_results[:10]:
        print(
            f"    {res['agent_name']:<35} {res['trades']:>7} {res['fitness']:>8.1f} {res['win_rate']:>6.0%} {res['roi']:>7.2f}%"
        )

    # 7. Summary
    print("\n[7] SUMMARY STATISTICS:")
    total_trades = sum(r["trades"] for r in backtest_results)
    avg_fitness = sum(r["fitness"] for r in backtest_results) / len(backtest_results) if backtest_results else 0

    print(f"    Agents spawned: {len(agents)}")
    print(f"    Agents backtested: {len(backtest_results)}")
    print(f"    Total trades: {total_trades}")
    print(f"    Average fitness: {avg_fitness:.2f}")
    print(f"    Spawn time: {spawn_time:.1f}s ({spawn_time / len(agents):.2f}s per agent)")
    print(f"    Backtest time: {backtest_time:.2f}s")

    print("\n" + "=" * 80)
    print("GENESIS COMPLETE - 100 real agents with full trait generation!")
    print("=" * 80)


if __name__ == "__main__":
    main()
