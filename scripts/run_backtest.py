"""
Multi-timeframe backtest with normal distribution weighting.
"""

import asyncio
import os
import sys

# Add both parent (for Fast_Swarm module) and current (for local_agents)
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
parent_of_project = os.path.dirname(project_root)

sys.path.insert(0, parent_of_project)  # For Fast_Swarm imports
sys.path.insert(0, project_root)  # For local_agents imports

from dotenv import load_dotenv

load_dotenv(os.path.join(project_root, "local-utilities", ".env"))

import logging
import statistics

import pandas as pd
from sqlmodel import select

from Fast_Swarm.Database import async_session_maker
from Fast_Swarm.Infrastructure.Models.market_data_models import EnhancedCandle
from Fast_Swarm.local_agents.backtest.engine import AIZoneMode, LocalBacktestEngine
from Fast_Swarm.local_agents.core.evolution import evaluate_agent_fitness
from Fast_Swarm.local_agents.core.state import AgentDatabase
from Fast_Swarm.local_agents.run_evolution import EnhancedOHLCVLoader, get_initial_patterns

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("BACKTEST")


def window_weight(window_idx: int, total_windows: int = 3) -> float:
    """
    Asymmetric weighting: small=30%, medium=100%, large=100%
    Small windows have less data so less reliable.
    """
    if total_windows == 3:
        weights = [0.30, 1.0, 1.0]  # small, medium, large
        return weights[window_idx]
    return 1.0


async def load_all_data(timeframe_config, assets):
    all_data = {}
    async with async_session_maker() as session:
        for timeframe, window_sizes in timeframe_config:
            all_data[timeframe] = {}
            for win_idx, window_size in enumerate(window_sizes):
                all_data[timeframe][win_idx] = {}
                offset = sum(window_sizes[:win_idx])
                for asset in assets:
                    cache_key = f"{asset}_{timeframe}"
                    statement = (
                        select(EnhancedCandle)
                        .where(EnhancedCandle.symbol == asset)
                        .where(EnhancedCandle.timeframe == timeframe)
                        .order_by(EnhancedCandle.time.desc())
                        .offset(offset)
                        .limit(window_size)
                    )
                    result = await session.exec(statement)
                    candles = list(result.all())
                    if candles:
                        candles = candles[::-1]
                        data = [c.model_dump() for c in candles]
                        df = pd.DataFrame(data)
                        df["timestamp"] = df["time"].apply(lambda x: int(x.timestamp() * 1000) if x else None)
                        df["asset"] = asset
                        for col in ["open", "high", "low", "close", "volume"]:
                            if col in df.columns:
                                df[col] = pd.to_numeric(df[col], errors="coerce")
                        all_data[timeframe][win_idx][cache_key] = df
                total = sum(len(all_data[timeframe][win_idx].get(f"{a}_{timeframe}", pd.DataFrame())) for a in assets)
                logger.info(f"[LOAD] {timeframe} W{win_idx + 1} ({window_size}): {total} candles")
    return all_data


def main():
    agent_db = AgentDatabase()
    all_agents = agent_db.get_all_active_agents()
    agents = all_agents  # All agents
    logger.info(f"[BACKTEST] {len(agents)} agents (of {len(all_agents)} total)")

    patterns = get_initial_patterns(max_patterns=10000)
    patterns_dict = {p["pattern_id"]: p for p in patterns}
    logger.info(f"[BACKTEST] {len(patterns_dict)} patterns")

    # Window sizes: doubled again to get more trades per window
    TIMEFRAME_CONFIG = [
        ("1h", [240, 800, 2880]),  # 10d, 33d, 120d
        ("15m", [720, 2400, 8000]),  # 7.5d, 25d, 83d
    ]

    assets = ["BTC", "ETH"]

    logger.info("\n[WEIGHTS] Normal distribution around medium:")
    for i, name in enumerate(["small", "medium", "large"]):
        logger.info(f"  {name}: {window_weight(i, 3) * 100:.1f}%")

    logger.info("[BACKTEST] Loading data...")
    all_data = asyncio.run(load_all_data(TIMEFRAME_CONFIG, assets))

    agent_tf_results = {a.agent_id: {tf: [] for tf, _ in TIMEFRAME_CONFIG} for a in agents}
    stats = {"total_trades": 0, "trades_by_tf": {}, "agents_scored_by_tf": {}}

    for timeframe, window_sizes in TIMEFRAME_CONFIG:
        stats["trades_by_tf"][timeframe] = 0
        stats["agents_scored_by_tf"][timeframe] = set()
        logger.info(f"\n=== {timeframe} ===")
        dataset = {"assets": assets, "timeframe": timeframe}

        for win_idx, window_size in enumerate(window_sizes):
            preloaded = all_data[timeframe].get(win_idx, {})
            if not any(len(df) > 0 for df in preloaded.values()):
                continue

            engine = LocalBacktestEngine(
                loader=EnhancedOHLCVLoader(),
                patterns=patterns_dict,
                ai_zone_mode=AIZoneMode.HEURISTIC,
                preloaded_candles=preloaded,
            )

            window_trades = 0
            scored = 0
            for agent in agents:
                try:
                    trades = engine.run(agent, dataset)
                    window_trades += len(trades)
                    if len(trades) >= 2:  # Min trades per window
                        fitness = evaluate_agent_fitness(agent, trades)
                        if fitness > 0:
                            weight = window_weight(win_idx, len(window_sizes))
                            agent_tf_results[agent.agent_id][timeframe].append((fitness, len(trades), win_idx, weight))
                            stats["agents_scored_by_tf"][timeframe].add(agent.agent_id)
                            scored += 1
                except Exception:
                    pass

            stats["total_trades"] += window_trades
            stats["trades_by_tf"][timeframe] += window_trades
            wname = ["small", "medium", "large"][win_idx]
            logger.info(f"  {wname} ({window_size}): {window_trades} trades, {scored} scored")

    # Aggregate
    results = []
    for agent in agents:
        tf_fitness = {}
        tf_trades = {}

        for timeframe, window_sizes in TIMEFRAME_CONFIG:
            window_data = agent_tf_results[agent.agent_id][timeframe]
            if window_data:
                ws, tw, tt = 0.0, 0.0, 0
                for fitness, trade_count, win_idx, weight in window_data:
                    w = trade_count * weight
                    ws += fitness * w
                    tw += w
                    tt += trade_count
                tf_fitness[timeframe] = ws / tw if tw > 0 else 0.0
                tf_trades[timeframe] = tt

        if tf_fitness:
            ws, tw = 0.0, 0.0
            for tf in tf_fitness:
                ws += tf_fitness[tf] * tf_trades[tf]
                tw += tf_trades[tf]
            final_fitness = ws / tw if tw > 0 else 0.0
            total_trades = sum(tf_trades.values())
            agent_db.update_agent_fitness(agent.agent_id, final_fitness)
            results.append(
                {"agent": agent.agent_name, "fitness": final_fitness, "trades": total_trades, "tf": tf_fitness}
            )

    results.sort(key=lambda r: r["fitness"], reverse=True)

    # DESCRIPTIVE STATISTICS
    logger.info("\n" + "=" * 60)
    logger.info("DESCRIPTIVE STATISTICS")
    logger.info("=" * 60)

    logger.info("\n--- TRADES ---")
    logger.info(f"Total: {stats['total_trades']:,}")
    for tf, count in stats["trades_by_tf"].items():
        logger.info(f"  {tf}: {count:,}")

    # Count windows per agent (across all timeframes)
    agent_window_counts = {}
    for agent in agents:
        total_windows = 0
        for tf, _ in TIMEFRAME_CONFIG:
            total_windows += len(agent_tf_results[agent.agent_id][tf])
        agent_window_counts[agent.agent_id] = total_windows

    # Target: 50% of agents on 2+ windows
    agents_2plus = sum(1 for c in agent_window_counts.values() if c >= 2)
    agents_3plus = sum(1 for c in agent_window_counts.values() if c >= 3)
    total_windows_possible = len(TIMEFRAME_CONFIG) * 3  # 2 timeframes × 3 windows

    logger.info("\n--- AGENTS ---")
    logger.info(f"Total: {len(agents)}")
    logger.info(f"Scored: {len(results)} ({100 * len(results) / len(agents):.1f}%)")
    logger.info("")
    logger.info("*** WINDOW COVERAGE (target: 50% on 2+ windows) ***")
    logger.info(
        f"  1+ windows: {sum(1 for c in agent_window_counts.values() if c >= 1)} ({100 * sum(1 for c in agent_window_counts.values() if c >= 1) / len(agents):.1f}%)"
    )
    logger.info(
        f"  2+ windows: {agents_2plus} ({100 * agents_2plus / len(agents):.1f}%) {'<-- TARGET MET!' if agents_2plus >= len(agents) * 0.5 else '<-- BELOW TARGET'}"
    )
    logger.info(f"  3+ windows: {agents_3plus} ({100 * agents_3plus / len(agents):.1f}%)")
    logger.info("")
    for tf, agents_set in stats["agents_scored_by_tf"].items():
        logger.info(f"  {tf}: {len(agents_set)} agents")

    if results:
        fitnesses = [r["fitness"] for r in results]
        trades_list = [r["trades"] for r in results]

        logger.info("\n--- FITNESS ---")
        logger.info(f"Mean: {statistics.mean(fitnesses):.2f}")
        logger.info(f"Median: {statistics.median(fitnesses):.2f}")
        if len(fitnesses) > 1:
            logger.info(f"Std Dev: {statistics.stdev(fitnesses):.2f}")
        logger.info(f"Min: {min(fitnesses):.2f}")
        logger.info(f"Max: {max(fitnesses):.2f}")

        sorted_f = sorted(fitnesses)
        n = len(sorted_f)
        logger.info(f"Q1: {sorted_f[n // 4]:.2f}")
        logger.info(f"Q2: {sorted_f[n // 2]:.2f}")
        logger.info(f"Q3: {sorted_f[3 * n // 4]:.2f}")

        logger.info("\n--- TRADES PER AGENT ---")
        logger.info(f"Mean: {statistics.mean(trades_list):.1f}")
        logger.info(f"Max: {max(trades_list)}")

        logger.info("\n--- TOP 10 ---")
        for i, r in enumerate(results[:10], 1):
            tf_str = ", ".join(f"{k}={v:.1f}" for k, v in r["tf"].items())
            logger.info(f"{i:2}. {r['agent']}: {r['fitness']:.1f} ({r['trades']} trades) [{tf_str}]")


if __name__ == "__main__":
    main()
