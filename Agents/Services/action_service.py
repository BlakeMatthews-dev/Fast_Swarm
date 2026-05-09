import asyncio
import logging
import os
import random
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..Models.agent_models import Agent

# Setup logging for visibility
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ActionService")

# Centralized DB service - no more raw psycopg2
from Fast_Swarm.db_service import db
from Fast_Swarm.Patterns.Services.pattern_service import get_tiers_by_quintile, is_spawn_eligible

# Track backtest progress globally
_backtest_status = {
    "running": False,
    "started_at": None,
    "current_agent": None,
    "progress": 0,
    "total": 0,
    "completed": [],
    "errors": [],
}

# AI-powered agent spawning via Ollama
from Fast_Swarm.llm_service import check_ollama_available, ollama_call_sync

# Ensure local_agents is reachable
project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


# Load env vars for local_agents sync code
def _ensure_env():
    """Load env vars from .env if not already set."""
    if not os.getenv("POSTGRES_PASSWORD"):
        try:
            from dotenv import load_dotenv

            env_path = project_root / "local-utilities" / ".env"
            if env_path.exists():
                load_dotenv(env_path)
        except ImportError:
            pass


from Fast_Swarm.local_agents.backtest.data import preload_candles_for_windows
from Fast_Swarm.local_agents.backtest.engine import LocalBacktestEngine
from Fast_Swarm.local_agents.backtest.windows import get_windows
from Fast_Swarm.local_agents.backtest.windows import is_initialized as windows_initialized
from Fast_Swarm.local_agents.core.genesis import initialize_population
from Fast_Swarm.local_agents.core.state import AgentDatabase
from Fast_Swarm.local_agents.run_evolution import EnhancedOHLCVLoader, get_initial_patterns


def _spawn_agents_sync_with_patterns(
    count: int,
    pattern_index: list,
    use_llm: bool = True,
):
    """
    Synchronous spawn operation - runs in thread pool.

    Args:
        count: Number of agents to spawn.
        pattern_index: Available patterns (already filtered by fitness).
        use_llm: Use AI for pattern selection (default True - we're an AI swarm!).
    """
    agent_db = AgentDatabase()
    new_agents = initialize_population(
        population_size=count,
        available_patterns=pattern_index,
        db=agent_db,
        use_llm=use_llm,
        llm_call=ollama_call_sync if use_llm else None,
    )
    return [a.agent_id for a in new_agents]


async def spawn_agents(count: int):
    """
    Spawn 'count' new agents using the standard genesis process.

    Uses centralized DatabaseService for pattern loading (async SQLModel).
    Runs sync genesis code in thread pool to avoid blocking the event loop.

    AI Pattern Selection (REQUIRED):
    - Uses Ollama LLM to select patterns that match agent personality
    - Agents get personalized pattern portfolios based on their traits
    - NO HEURISTIC FALLBACK - AI is required for spawn decisions

    Args:
        count: Number of agents to spawn.

    Raises:
        ValueError: If Ollama is not available (AI is required for spawn)
    """
    # Ensure env vars loaded for local_agents sync code
    _ensure_env()

    # Check if Ollama is available - AI is REQUIRED, no fallback
    ollama_available = await check_ollama_available()
    if not ollama_available:
        raise ValueError(
            "Ollama LLM is REQUIRED for agent spawning but is not available. Start Ollama with: ollama serve"
        )

    use_llm = True  # AI is always required

    # Get all active patterns via async SQLModel
    all_patterns = await db.get_active_patterns()

    if not all_patterns:
        raise ValueError("No active patterns in PostgreSQL. Create or import patterns first.")

    # Apply quintile-based tier system and spawn eligibility filtering
    # Convert patterns to dicts for tier calculation
    pattern_dicts = [
        {
            "pattern_id": p.get("pattern_id") or p.get("id", ""),
            "fitness_score": p.get("fitness_score") or p.get("fitness", 0),
            "backtest_count": p.get("backtest_count", 0),
            "assets_tested": p.get("assets_tested", []),
            "timeframes_tested": p.get("timeframes_tested", []),
        }
        for p in all_patterns
    ]

    # Calculate quintile-based tiers
    tiers = get_tiers_by_quintile(pattern_dicts)

    # Filter by spawn eligibility (Tier 1-2, 100+ backtests, 3+ assets, 4 timeframes)
    # Note: For early-stage systems, we relax requirements - just check tier
    pattern_index = []
    for p in all_patterns:
        pid = p.get("pattern_id") or p.get("id", "")
        tier = tiers.get(pid, 5)
        # Use simple tier check (full eligibility requires 100+ backtests which new systems won't have)
        if is_spawn_eligible(tier=tier):
            pattern_index.append(p)

    if not pattern_index:
        # Fallback: if no spawn-eligible patterns, use top 40% by fitness
        logger.warning("[ActionService] No spawn-eligible patterns (Tier 1-2). Using top 40% fallback.")
        sorted_patterns = sorted(all_patterns, key=lambda p: p.get("fitness_score", 0) or 0, reverse=True)
        pattern_index = sorted_patterns[: max(1, int(len(sorted_patterns) * 0.4))]

    logger.info(
        f"[ActionService] Filtered to {len(pattern_index)} spawn-eligible patterns (of {len(all_patterns)} total)"
    )

    print(f"[ActionService] Spawning {count} agents with {len(pattern_index)} quality patterns")
    print(f"[ActionService] AI Selection: {'ENABLED' if use_llm else 'DISABLED (heuristic)'}")

    # genesis still sync, run in thread pool
    agent_ids = await asyncio.to_thread(_spawn_agents_sync_with_patterns, count, pattern_index, use_llm)

    return {
        "message": f"Spawned {len(agent_ids)} new agents",
        "agents": agent_ids,
        "ai_selection": use_llm,
        "patterns_available": len(pattern_index),
    }


# Exit strategy comparison spawn
EXIT_STRATEGIES = [
    "dynamic_trail",  # Logarithmic trailing (2%→12%)
    "atr_trail",  # ATR-based trailing (volatility adaptive)
    "scaled_out",  # 25% exit at each milestone
    "breakeven_trail",  # Move to breakeven after +5%
    "trailing_2pct",  # 2% trailing stop
    "trailing_3pct",  # 3% trailing stop
    "trailing_5pct",  # 5% trailing stop
]


def _spawn_exit_strategy_comparison(pattern_index: list, use_llm: bool = True):
    """
    Spawn one agent per exit strategy - identical traits/patterns, different exits.
    Perfect for A/B testing exit strategies!
    """
    from Fast_Swarm.local_agents.core.genesis import generate_exit_conditions
    from Fast_Swarm.local_agents.core.traits import derive_dependent_traits, generate_traits

    agent_db = AgentDatabase()

    # Generate ONE set of traits (shared by all agents)
    base_seed = 42  # Fixed seed for reproducibility
    base_traits = generate_traits(base_seed)
    base_traits = derive_dependent_traits(base_traits, base_seed + 1)

    # Select patterns ONCE via LLM (shared by all agents)
    from Fast_Swarm.local_agents.core.genesis import select_patterns_heuristic, select_patterns_llm

    if use_llm:
        selections, philosophy = select_patterns_llm(
            base_traits, pattern_index, "ExitStrategyTestAgent", ollama_call_sync
        )
    else:
        selections = select_patterns_heuristic(base_traits, pattern_index, base_seed + 2)
        philosophy = "Exit strategy comparison agent"

    pattern_ids = [s["pattern_id"] for s in selections]
    patterns_by_id = {p["pattern_id"]: p for p in pattern_index}

    agents = []
    for exit_strategy in EXIT_STRATEGIES:
        # Create pattern copies with THIS exit strategy
        pattern_copies = []
        for sel in selections:
            pid = sel["pattern_id"]
            if pid not in patterns_by_id:
                continue
            original = patterns_by_id[pid]
            entry_conds = original.get("entry_conditions", [])

            # Force this specific exit strategy
            exit_conds = [
                {
                    "exit_strategy": exit_strategy,
                    "description": f"Testing {exit_strategy}",
                }
            ]
            # Add indicator exits too
            indicator_exits = generate_exit_conditions(entry_conds, base_traits, hash(pid))
            # Keep only indicator conditions, not strategy
            for ec in indicator_exits:
                if "indicator" in ec:
                    exit_conds.append(ec)

            pattern_copies.append(
                {
                    "pattern_id": pid,
                    "name": original.get("name", pid),
                    "entry_conditions": entry_conds,
                    "exit_conditions": exit_conds,
                    "weight": sel.get("weight", 1.0),
                }
            )

        # Create agent with this exit strategy
        agent_name = f"ExitTest_{exit_strategy}_Gen1"
        record = agent_db.create_agent(
            agent_name=agent_name,
            traits=base_traits,
            pattern_ids=pattern_ids,
            pattern_copies=pattern_copies,
            generation=1,
            trading_philosophy=f"{philosophy} | Exit: {exit_strategy}",
        )
        agents.append(record)
        print(f"[ActionService] Spawned {agent_name}")

    return [a.agent_id for a in agents]


async def spawn_exit_strategy_comparison():
    """
    Spawn 7 agents - one per exit strategy - with identical everything else.
    Perfect for comparing exit strategies in backtest!
    """
    _ensure_env()

    ollama_available = await check_ollama_available()
    if not ollama_available:
        raise ValueError("Ollama LLM is REQUIRED")

    all_patterns = await db.get_active_patterns()
    if not all_patterns:
        raise ValueError("No active patterns")

    # Filter patterns
    pattern_dicts = [
        {"pattern_id": p.get("pattern_id"), "fitness_score": p.get("fitness_score", 0)} for p in all_patterns
    ]
    tiers = get_tiers_by_quintile(pattern_dicts)
    pattern_index = [p for p in all_patterns if is_spawn_eligible(tier=tiers.get(p.get("pattern_id"), 5))]

    if not pattern_index:
        sorted_patterns = sorted(all_patterns, key=lambda p: p.get("fitness_score", 0) or 0, reverse=True)
        pattern_index = sorted_patterns[: max(1, int(len(sorted_patterns) * 0.4))]

    print("[ActionService] Spawning EXIT STRATEGY COMPARISON: 7 agents, same traits, different exits")

    agent_ids = await asyncio.to_thread(_spawn_exit_strategy_comparison, pattern_index, True)

    return {
        "message": f"Spawned {len(agent_ids)} exit strategy comparison agents",
        "agents": agent_ids,
        "strategies": EXIT_STRATEGIES,
        "comparison_mode": True,
    }


async def cull_agents(session: AsyncSession, survival_rate: float = 0.6):
    """
    Cull the bottom % of agents based on fitness.
    """
    # Fetch all active agents
    statement = select(Agent).where(Agent.status == "active")
    result = await session.scalars(statement)
    agents = list(result.all())

    if not agents:
        return {"message": "No active agents to cull"}

    # Sort by fitness (descending)
    # Treat None as -1
    agents.sort(key=lambda a: a.fitness_score or -1.0, reverse=True)

    total = len(agents)
    survivors_count = int(total * survival_rate)
    cull_count = total - survivors_count

    if cull_count <= 0:
        return {"message": "No agents culled (survival rate too high or population too small)"}

    # Cull the bottom ones
    culled_agents = agents[survivors_count:]

    for agent in culled_agents:
        agent.status = "retired"
        session.add(agent)

    await session.commit()

    return {
        "message": f"Culled {len(culled_agents)} agents",
        "survivors_count": survivors_count,
        "culled_ids": [a.agent_id for a in culled_agents],
    }


def get_backtest_status():
    """Get current backtest progress."""
    return _backtest_status.copy()


def perform_backtest_sync(agent_ids: list[str] = None, limit: int = None):
    """
    Sync wrapper to run backtest on specific agents or all active ones.

    Args:
        agent_ids: Specific agents to backtest (None = all active)
        limit: Max agents to backtest (None = all)
    """
    global _backtest_status

    _backtest_status["running"] = True
    _backtest_status["started_at"] = datetime.now().isoformat()
    _backtest_status["completed"] = []
    _backtest_status["errors"] = []

    logger.info("=" * 60)
    logger.info("[BACKTEST] Starting agent backtest...")

    agent_db = AgentDatabase()

    # Get agents
    if agent_ids:
        all_agents = agent_db.get_all_active_agents()
        agents = [a for a in all_agents if a.agent_id in agent_ids]
    else:
        agents = agent_db.get_all_active_agents()

    # Apply limit
    if limit and len(agents) > limit:
        agents = agents[:limit]

    if not agents:
        logger.warning("[BACKTEST] No agents to backtest")
        _backtest_status["running"] = False
        return {"agents_tested": 0, "message": "No agents found"}

    _backtest_status["total"] = len(agents)
    logger.info(f"[BACKTEST] Found {len(agents)} agents to test")

    # Setup Engine
    logger.info("[BACKTEST] Loading OHLCV data and patterns...")
    loader = EnhancedOHLCVLoader()
    patterns = get_initial_patterns(max_patterns=500)
    patterns_dict = {p["pattern_id"]: p for p in patterns}
    logger.info(f"[BACKTEST] Loaded {len(patterns_dict)} patterns")

    # Get diverse windows from pre-generated pool
    if not windows_initialized():
        logger.error("[BACKTEST] Window pool not initialized! Call windows.initialize() at startup.")
        _backtest_status["running"] = False
        return {"agents_tested": 0, "error": "Window pool not initialized"}

    raw_windows = get_windows(count=16)
    logger.info(f"[BACKTEST] Using {len(raw_windows)} windows from pool")

    # OPTIMIZATION: Preload candle data ONCE for all windows (avoids repeated DB queries)
    logger.info("[BACKTEST] Preloading candle data for all windows...")
    preloaded_candles = preload_candles_for_windows(raw_windows, loader)
    logger.info(f"[BACKTEST] Preloaded {len(preloaded_candles)} asset/timeframe pairs")

    # Create engine with preloaded data
    engine = LocalBacktestEngine(
        loader=loader,
        patterns=patterns_dict,
        preloaded_candles=preloaded_candles,
        use_fast_inference=True,  # 0.001ms per AI decision (heuristic mode)
    )

    # Convert windows to datasets for backtest loop
    backtest_windows = [w.to_dataset() for w in raw_windows]

    results = []
    for i, agent in enumerate(agents):
        _backtest_status["progress"] = i + 1
        _backtest_status["current_agent"] = agent.agent_name

        logger.info(f"[BACKTEST] ({i + 1}/{len(agents)}) Testing {agent.agent_name}...")

        try:
            all_trades = []
            for dataset in backtest_windows:
                trades = engine.run(agent, dataset)
                all_trades.extend(trades)
            trades = all_trades

            # Save trades
            for trade in trades:
                agent_db.create_trade(trade)

            # Update fitness
            from Fast_Swarm.local_agents.core.evolution import evaluate_agent_fitness

            fitness = evaluate_agent_fitness(agent, trades)
            agent_db.update_agent_fitness(agent.agent_id, fitness)

            result = {"agent": agent.agent_name, "trades": len(trades), "fitness": round(fitness, 2)}
            results.append(result)
            _backtest_status["completed"].append(result)

            logger.info(f"[BACKTEST]   → {len(trades)} trades, fitness: {fitness:.2f}")

        except Exception as e:
            error = {"agent": agent.agent_name, "error": str(e)}
            _backtest_status["errors"].append(error)
            logger.error(f"[BACKTEST]   → ERROR: {e}")

    _backtest_status["running"] = False
    _backtest_status["current_agent"] = None

    logger.info("=" * 60)
    logger.info(f"[BACKTEST] Complete! Tested {len(results)} agents")
    logger.info("=" * 60)

    return {"agents_tested": len(results), "results": results, "errors": _backtest_status["errors"]}


async def trigger_backtest(background_tasks, agent_ids: list[str] = None):
    start_func = lambda: perform_backtest_sync(agent_ids)
    background_tasks.add_task(start_func)
    return {"message": "Backtest started in background"}


def perform_backtest_canonical_sync(agent_ids: list[str] = None, regimes: list[str] = None, limit: int = None):
    """
    Run backtest on CANONICAL PERIODS ONLY (historical market events).

    Tests agents against known periods like crashes, bulls, bears, etc.
    No random windows - pure regime-specific testing.
    """
    global _backtest_status
    from Fast_Swarm.local_agents.core.canonical_periods import get_canonical_periods_for_backtesting

    _backtest_status["running"] = True
    _backtest_status["started_at"] = datetime.now().isoformat()
    _backtest_status["completed"] = []
    _backtest_status["errors"] = []

    logger.info("=" * 60)
    logger.info("[BACKTEST:CANONICAL] Starting canonical-only backtest...")

    agent_db = AgentDatabase()

    # Get agents
    if agent_ids:
        all_agents = agent_db.get_all_active_agents()
        agents = [a for a in all_agents if a.agent_id in agent_ids]
    else:
        agents = agent_db.get_all_active_agents()

    if limit and len(agents) > limit:
        agents = agents[:limit]

    if not agents:
        logger.warning("[BACKTEST:CANONICAL] No agents to backtest")
        _backtest_status["running"] = False
        return {"agents_tested": 0, "message": "No agents found"}

    _backtest_status["total"] = len(agents)

    # Get canonical periods (filter by regime if specified)
    # Use major assets with good historical coverage for regime testing
    canonical_assets = ["BTC", "ETH", "SOL", "ADA", "AVAX", "DOT", "LINK", "ATOM"]
    target_regimes = regimes if regimes else None
    canonical_periods = get_canonical_periods_for_backtesting(
        assets=canonical_assets,
        timeframes=["1h", "4h", "1d"],
        regimes=target_regimes,
    )
    logger.info(f"[BACKTEST:CANONICAL] Testing {len(agents)} agents across {len(canonical_periods)} canonical periods")

    # Setup engine with data preloading
    loader = EnhancedOHLCVLoader()
    patterns = get_initial_patterns(max_patterns=500)
    patterns_dict = {p["pattern_id"]: p for p in patterns}

    # OPTIMIZATION: Preload candle data ONCE for all canonical periods
    from dataclasses import dataclass

    @dataclass
    class PeriodAdapter:
        """Adapter to make canonical periods work with preload_candles_for_windows."""

        symbol: str
        timeframe: str
        start_ts: int
        end_ts: int

    period_adapters = [
        PeriodAdapter(
            symbol=p["asset"],
            timeframe=p["timeframe"],
            start_ts=p["start_ts"],
            end_ts=p["end_ts"],
        )
        for p in canonical_periods
    ]

    logger.info("[BACKTEST:CANONICAL] Preloading candle data for all periods...")
    preloaded_candles = preload_candles_for_windows(period_adapters, loader)
    logger.info(f"[BACKTEST:CANONICAL] Preloaded {len(preloaded_candles)} asset/timeframe pairs")

    engine = LocalBacktestEngine(
        loader=loader,
        patterns=patterns_dict,
        preloaded_candles=preloaded_candles,
        use_fast_inference=True,  # 0.001ms per AI decision (heuristic mode)
    )

    results = []
    for i, agent in enumerate(agents):
        _backtest_status["progress"] = i + 1
        _backtest_status["current_agent"] = agent.agent_name

        logger.info(f"[BACKTEST:CANONICAL] ({i + 1}/{len(agents)}) Testing {agent.agent_name}...")

        try:
            regime_trades = {}
            all_trades = []

            for period in canonical_periods:
                regime = period["regime"]
                if regime not in regime_trades:
                    regime_trades[regime] = []

                dataset = {
                    "assets": [period["asset"]],
                    "timeframe": period["timeframe"],
                    "start_ts": period["start_ts"],
                    "end_ts": period["end_ts"],
                }
                trades = engine.run(agent, dataset)
                all_trades.extend(trades)
                regime_trades[regime].extend(trades)

            # Save trades
            for trade in all_trades:
                agent_db.create_trade(trade)

            # Update fitness
            from Fast_Swarm.local_agents.core.evolution import evaluate_agent_fitness

            fitness = evaluate_agent_fitness(agent, all_trades)
            agent_db.update_agent_fitness(agent.agent_id, fitness)

            # Calculate per-regime fitness
            fitness_by_regime = {}
            for regime, trades in regime_trades.items():
                if trades:
                    regime_fitness = evaluate_agent_fitness(agent, trades)
                    fitness_by_regime[regime] = {
                        "fitness": round(regime_fitness, 2),
                        "trades": len(trades),
                    }

            result = {
                "agent": agent.agent_name,
                "trades": len(all_trades),
                "fitness": round(fitness, 2),
                "fitness_by_regime": fitness_by_regime,
                "mode": "canonical",
            }
            results.append(result)
            _backtest_status["completed"].append(result)
            logger.info(f"[BACKTEST:CANONICAL]   → {len(all_trades)} trades, fitness: {fitness:.2f}")

        except Exception as e:
            error = {"agent": agent.agent_name, "error": str(e)}
            _backtest_status["errors"].append(error)
            logger.error(f"[BACKTEST:CANONICAL]   → ERROR: {e}")

    _backtest_status["running"] = False
    _backtest_status["current_agent"] = None

    logger.info("=" * 60)
    logger.info(f"[BACKTEST:CANONICAL] Complete! Tested {len(results)} agents")

    return {
        "agents_tested": len(results),
        "mode": "canonical",
        "periods_tested": len(canonical_periods),
        "results": results,
        "errors": _backtest_status["errors"],
    }


def perform_backtest_random_sync(
    agent_ids: list[str] = None, timeframes: list[str] = None, windows_per_asset: int = 20, limit: int = None
):
    """
    Run backtest on RANDOM WINDOWS ONLY (diverse market conditions).

    Generates random time windows across multiple timeframes.
    No canonical periods - pure random window testing.
    """
    global _backtest_status

    _backtest_status["running"] = True
    _backtest_status["started_at"] = datetime.now().isoformat()
    _backtest_status["completed"] = []
    _backtest_status["errors"] = []

    logger.info("=" * 60)
    logger.info("[BACKTEST:RANDOM] Starting random-window-only backtest...")

    agent_db = AgentDatabase()

    # Get agents
    if agent_ids:
        all_agents = agent_db.get_all_active_agents()
        agents = [a for a in all_agents if a.agent_id in agent_ids]
    else:
        agents = agent_db.get_all_active_agents()

    if limit and len(agents) > limit:
        agents = agents[:limit]

    if not agents:
        logger.warning("[BACKTEST:RANDOM] No agents to backtest")
        _backtest_status["running"] = False
        return {"agents_tested": 0, "message": "No agents found"}

    _backtest_status["total"] = len(agents)

    # Get windows from pre-generated pool (no DB queries needed)
    active_tfs = set(timeframes) if timeframes else {"1m", "5m", "15m", "1h", "4h", "1d"}

    if not windows_initialized():
        logger.error("[BACKTEST:RANDOM] Window pool not initialized")
        _backtest_status["running"] = False
        return {"error": "Window pool not initialized. Call windows.initialize() at startup."}

    # Get more windows than needed, then filter by timeframe
    pool_windows = get_windows(count=500)

    # Filter by requested timeframes (keep raw Window objects for preloading)
    filtered_windows = [w for w in pool_windows if w.timeframe in active_tfs]

    # Limit to reasonable number per timeframe
    max_windows = windows_per_asset * len(active_tfs) * 10 if windows_per_asset else len(filtered_windows)
    if len(filtered_windows) > max_windows:
        filtered_windows = random.sample(filtered_windows, max_windows)

    # Convert to dict format for backtest loop (after filtering/sampling)
    windows = [
        {
            "asset": w.symbol,
            "timeframe": w.timeframe,
            "start_ts": w.start_ts,
            "end_ts": w.end_ts,
            "regime": f"random_{w.timeframe}",
        }
        for w in filtered_windows
    ]

    logger.info(f"[BACKTEST:RANDOM] Using {len(windows)} windows from pool across {len(active_tfs)} timeframes")
    logger.info(f"[BACKTEST:RANDOM] Testing {len(agents)} agents...")

    # Setup engine with data preloading
    loader = EnhancedOHLCVLoader()
    patterns = get_initial_patterns(max_patterns=500)
    patterns_dict = {p["pattern_id"]: p for p in patterns}

    # OPTIMIZATION: Preload candle data ONCE for all windows (avoids repeated DB queries)
    logger.info("[BACKTEST:RANDOM] Preloading candle data for all windows...")
    preloaded_candles = preload_candles_for_windows(filtered_windows, loader)
    logger.info(f"[BACKTEST:RANDOM] Preloaded {len(preloaded_candles)} asset/timeframe pairs")

    engine = LocalBacktestEngine(
        loader=loader,
        patterns=patterns_dict,
        preloaded_candles=preloaded_candles,
        use_fast_inference=True,  # 0.001ms per AI decision (heuristic mode)
    )

    results = []
    for i, agent in enumerate(agents):
        _backtest_status["progress"] = i + 1
        _backtest_status["current_agent"] = agent.agent_name

        logger.info(f"[BACKTEST:RANDOM] ({i + 1}/{len(agents)}) Testing {agent.agent_name}...")

        try:
            regime_trades = {}
            all_trades = []

            for window in windows:
                regime = window["regime"]
                if regime not in regime_trades:
                    regime_trades[regime] = []

                dataset = {
                    "assets": [window["asset"]],
                    "timeframe": window["timeframe"],
                    "start_ts": window["start_ts"],
                    "end_ts": window["end_ts"],
                }
                trades = engine.run(agent, dataset)
                all_trades.extend(trades)
                regime_trades[regime].extend(trades)

            # Save trades
            for trade in all_trades:
                agent_db.create_trade(trade)

            # Update fitness
            from Fast_Swarm.local_agents.core.evolution import evaluate_agent_fitness

            fitness = evaluate_agent_fitness(agent, all_trades)
            agent_db.update_agent_fitness(agent.agent_id, fitness)

            # Per-regime (per-timeframe) fitness
            fitness_by_regime = {}
            for regime, trades in regime_trades.items():
                if trades:
                    regime_fitness = evaluate_agent_fitness(agent, trades)
                    fitness_by_regime[regime] = {
                        "fitness": round(regime_fitness, 2),
                        "trades": len(trades),
                    }

            result = {
                "agent": agent.agent_name,
                "trades": len(all_trades),
                "fitness": round(fitness, 2),
                "fitness_by_regime": fitness_by_regime,
                "mode": "random",
            }
            results.append(result)
            _backtest_status["completed"].append(result)
            logger.info(f"[BACKTEST:RANDOM]   → {len(all_trades)} trades, fitness: {fitness:.2f}")

        except Exception as e:
            error = {"agent": agent.agent_name, "error": str(e)}
            _backtest_status["errors"].append(error)
            logger.error(f"[BACKTEST:RANDOM]   → ERROR: {e}")

    _backtest_status["running"] = False
    _backtest_status["current_agent"] = None

    logger.info("=" * 60)
    logger.info(f"[BACKTEST:RANDOM] Complete! Tested {len(results)} agents")

    return {
        "agents_tested": len(results),
        "mode": "random",
        "windows_generated": len(windows),
        "timeframes": active_tfs,
        "results": results,
        "errors": _backtest_status["errors"],
    }
