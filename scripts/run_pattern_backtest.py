"""
Pattern backtest - test 500 random active patterns over same windows as agents.
"""

import asyncio
import os
import random
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
parent_of_project = os.path.dirname(project_root)

sys.path.insert(0, parent_of_project)
sys.path.insert(0, project_root)

from dotenv import load_dotenv

load_dotenv(os.path.join(project_root, "local-utilities", ".env"))

import logging
import statistics

import pandas as pd
from sqlmodel import select

from Fast_Swarm.Database import async_session_maker
from Fast_Swarm.Infrastructure.Models.market_data_models import EnhancedCandle
from Fast_Swarm.local_agents.backtest.engine import AIZoneMode, LocalBacktestEngine
from Fast_Swarm.local_agents.core.state import AgentRecord
from Fast_Swarm.local_agents.core.traits import AgentTraits
from Fast_Swarm.local_agents.run_evolution import EnhancedOHLCVLoader
from Fast_Swarm.Patterns.Models.pattern_models import Pattern

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("PATTERN_BACKTEST")


def window_weight(window_idx: int) -> float:
    weights = [0.30, 1.0, 1.0]
    return weights[window_idx]


def calculate_pattern_fitness(trades) -> float:
    if len(trades) < 2:
        return 0.0

    wins = sum(1 for t in trades if t.pnl_pct > 0)
    win_rate = wins / len(trades)

    returns = [t.pnl_pct for t in trades]
    mean_return = statistics.mean(returns)

    if len(returns) > 1:
        std_return = statistics.stdev(returns)
        sharpe_raw = (mean_return / std_return) if std_return > 0 else 0
        # Cap at ±6 to filter calculation anomalies while allowing exceptional strategies
        sharpe = max(-6.0, min(6.0, sharpe_raw))
    else:
        sharpe = 0

    fitness = win_rate * 40 + min(20, max(-20, sharpe * 10)) + 20
    return max(0, min(100, fitness))


async def load_patterns(limit: int = 500):
    async with async_session_maker() as session:
        result = await session.exec(
            select(Pattern).where(Pattern.is_active == True).where(Pattern.entry_conditions.isnot(None))
        )
        all_patterns = list(result.all())

        if len(all_patterns) > limit:
            patterns = random.sample(all_patterns, limit)
        else:
            patterns = all_patterns

        return patterns


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


def update_pattern_fitness_sync(updates: list):
    """
    Batch update pattern fitness using SYNC psycopg3 connection.

    Why sync? asyncpg pools are tied to event loops. After the first
    asyncio.run() closes, the pool connections become invalid on Windows.
    Using a fresh sync connection avoids this entirely.
    """
    import psycopg  # psycopg3 (modern)

    conn = psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "coinswarm"),
        user=os.getenv("POSTGRES_USER", "coinswarm"),
        password=os.getenv("POSTGRES_PASSWORD", "coinswarm_dev_2024"),
    )

    try:
        # psycopg3 uses executemany with prepared statements (fast!)
        sql = """
            UPDATE patterns
            SET fitness_score = %s,
                total_trades = COALESCE(total_trades, 0) + %s,
                total_runs = COALESCE(total_runs, 0) + 1
            WHERE pattern_id = %s
        """
        # Reformat: (pattern_id, fitness, trades) -> (fitness, trades, pattern_id)
        batch_data = [(fitness, trades, pid) for pid, fitness, trades in updates]
        with conn.cursor() as cursor:
            cursor.executemany(sql, batch_data)
        conn.commit()
        logger.info(f"[DB] Updated {len(updates)} patterns")
    finally:
        conn.close()


async def load_all_async(timeframe_config, assets, pattern_limit):
    """Load patterns and data in single async context."""
    patterns = await load_patterns(pattern_limit)
    all_data = await load_all_data(timeframe_config, assets)
    return patterns, all_data


def main():
    TIMEFRAME_CONFIG = [
        ("1h", [240, 800, 2880]),
        ("15m", [720, 2400, 8000]),
    ]
    assets = ["BTC", "ETH"]

    logger.info("[PATTERN BACKTEST] Loading patterns and candle data...")
    patterns, all_data = asyncio.run(load_all_async(TIMEFRAME_CONFIG, assets, 500))
    logger.info(f"[PATTERN BACKTEST] Loaded {len(patterns)} patterns")

    default_traits = AgentTraits()
    pattern_results = {p.pattern_id: {tf: [] for tf, _ in TIMEFRAME_CONFIG} for p in patterns}
    stats = {"total_trades": 0, "patterns_scored": set()}

    for timeframe, window_sizes in TIMEFRAME_CONFIG:
        logger.info(f"\n=== {timeframe} ===")
        dataset = {"assets": assets, "timeframe": timeframe}

        for win_idx, window_size in enumerate(window_sizes):
            preloaded = all_data[timeframe].get(win_idx, {})
            if not any(len(df) > 0 for df in preloaded.values()):
                continue

            window_trades = 0
            scored = 0

            for pattern in patterns:
                try:
                    pattern_dict = {
                        pattern.pattern_id: {
                            "pattern_id": pattern.pattern_id,
                            "entry_conditions": pattern.entry_conditions or [],
                            "exit_conditions": pattern.exit_conditions or {},
                        }
                    }

                    test_agent = AgentRecord(
                        agent_id=f"ptest_{pattern.pattern_id[:8]}",
                        agent_name="PatternTest",
                        traits=default_traits.__dict__,
                        pattern_ids=[pattern.pattern_id],
                        pattern_weights={pattern.pattern_id: 1.0},
                    )

                    engine = LocalBacktestEngine(
                        loader=EnhancedOHLCVLoader(),
                        patterns=pattern_dict,
                        ai_zone_mode=AIZoneMode.HEURISTIC,
                        preloaded_candles=preloaded,
                    )

                    trades = engine.run(test_agent, dataset)
                    window_trades += len(trades)

                    if len(trades) >= 2:
                        fitness = calculate_pattern_fitness(trades)
                        if fitness > 0:
                            weight = window_weight(win_idx)
                            pattern_results[pattern.pattern_id][timeframe].append(
                                (fitness, len(trades), win_idx, weight)
                            )
                            stats["patterns_scored"].add(pattern.pattern_id)
                            scored += 1

                except Exception:
                    pass

            stats["total_trades"] += window_trades
            wname = ["small", "medium", "large"][win_idx]
            logger.info(f"  {wname} ({window_size}): {window_trades} trades, {scored} patterns scored")

    logger.info("\n[PATTERN BACKTEST] Aggregating results...")
    results = []
    db_updates = []  # Collect updates for batch

    for pattern in patterns:
        tf_fitness = {}
        tf_trades = {}

        for timeframe, _ in TIMEFRAME_CONFIG:
            window_data = pattern_results[pattern.pattern_id][timeframe]
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

            db_updates.append((pattern.pattern_id, final_fitness, total_trades))

            results.append(
                {
                    "pattern_id": pattern.pattern_id,
                    "name": pattern.name,
                    "fitness": final_fitness,
                    "trades": total_trades,
                    "tf": tf_fitness,
                }
            )

    # Batch update DB using sync connection (avoids asyncpg pool issues)
    if db_updates:
        logger.info(f"[PATTERN BACKTEST] Updating {len(db_updates)} patterns in DB...")
        update_pattern_fitness_sync(db_updates)

    results.sort(key=lambda r: r["fitness"], reverse=True)

    logger.info("\n" + "=" * 60)
    logger.info("PATTERN BACKTEST RESULTS")
    logger.info("=" * 60)

    logger.info("\n--- SUMMARY ---")
    logger.info(f"Patterns tested: {len(patterns)}")
    logger.info(f"Patterns scored: {len(results)} ({100 * len(results) / len(patterns):.1f}%)")
    logger.info(f"Total trades: {stats['total_trades']:,}")

    pattern_window_counts = {}
    for pid in pattern_results:
        count = sum(len(pattern_results[pid][tf]) for tf, _ in TIMEFRAME_CONFIG)
        pattern_window_counts[pid] = count

    p_2plus = sum(1 for c in pattern_window_counts.values() if c >= 2)
    logger.info("\n*** WINDOW COVERAGE ***")
    logger.info(
        f"  1+ windows: {sum(1 for c in pattern_window_counts.values() if c >= 1)} ({100 * sum(1 for c in pattern_window_counts.values() if c >= 1) / len(patterns):.1f}%)"
    )
    logger.info(f"  2+ windows: {p_2plus} ({100 * p_2plus / len(patterns):.1f}%)")

    if results:
        fitnesses = [r["fitness"] for r in results]
        logger.info("\n--- FITNESS ---")
        logger.info(f"Mean: {statistics.mean(fitnesses):.2f}")
        logger.info(f"Median: {statistics.median(fitnesses):.2f}")
        if len(fitnesses) > 1:
            logger.info(f"Std Dev: {statistics.stdev(fitnesses):.2f}")
        logger.info(f"Min: {min(fitnesses):.2f}")
        logger.info(f"Max: {max(fitnesses):.2f}")

        logger.info("\n--- TOP 15 PATTERNS ---")
        for i, r in enumerate(results[:15], 1):
            tf_str = ", ".join(f"{k}={v:.1f}" for k, v in r["tf"].items())
            name = r["name"][:40] if r["name"] else r["pattern_id"][:40]
            logger.info(f"{i:2}. {name}: {r['fitness']:.1f} ({r['trades']} trades) [{tf_str}]")


if __name__ == "__main__":
    main()
