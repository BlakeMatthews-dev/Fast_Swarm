"""
Evolution Runner - Initialize and evolve a population of trading agents.

This script:
1. Creates 15 initial agents with diverse traits
2. Backtests them across canonical historical periods (multiple regimes)
3. Evolves through generations with cloning and reproduction
4. Tracks fitness progression
"""

import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))
# Add local-utilities for canonical_periods
sys.path.insert(0, str(Path(__file__).parent.parent / "local-utilities"))

from Fast_Swarm.local_agents.backtest.data import OHLCVLoader
from Fast_Swarm.local_agents.backtest.engine import AIZoneMode, LocalBacktestEngine
from Fast_Swarm.local_agents.core.evolution import (
    EvolutionConfig,
    evaluate_agent_fitness,
    get_population_stats,
    run_evolution_cycle,
)
from Fast_Swarm.local_agents.core.genesis import initialize_population
from Fast_Swarm.local_agents.core.state import AgentDatabase
from Fast_Swarm.local_agents.core.traits import AgentTraits

# =============================================================================
# Configuration
# =============================================================================


@dataclass
class EvolutionRunConfig:
    """Configuration for evolution run."""

    # Population
    initial_population: int = 15

    # Evolution
    generations: int = 10
    elite_percent: float = 0.20  # Top 20% are elite parents
    survival_percent: float = 0.60  # Top 60% survive
    mutation_rate: float = 0.15  # 15% mutation per trait

    # Backtesting - HYBRID MODE
    assets: list = None
    timeframe: str = "1h"
    use_canonical_for_context: bool = True  # Show regime labels during spawning
    use_full_history: bool = True  # Test on ALL data, not just canonical periods
    canonical_regimes: list = None  # Which regimes to include for context
    candles_per_backtest: int = 2000  # Candles per backtest window (full history mode)
    windows_per_asset: int = 10  # Number of random windows per asset

    # AI Zone Mode for backtest decisions
    # SKIP: Fast backtesting, AI_REFLECT zone treated as skip
    # HEURISTIC: Use entry_aggression trait for AI zone decisions
    # LLM: Real Ollama calls for AI zone decisions (slower but smarter)
    ai_zone_mode: str = "heuristic"  # "skip", "heuristic", or "llm"

    # Trait seeding from learnings
    seed_from_winners: bool = True  # Bias traits toward winning profiles
    winner_trait_bias: dict = None  # Trait adjustments from learnings

    # Database
    db_path: str = None

    def __post_init__(self):
        if self.assets is None:
            # Use all available assets from enhanced_candles.db
            self.assets = [
                "BTC",
                "ETH",
                "SOL",
                "ADA",
                "AVAX",
                "DOT",
                "LINK",
                "MATIC",
                "ATOM",
                "UNI",
                "AAVE",
                "XRP",
                "BNB",
                "DOGE",
                "LTC",
            ]
        if self.canonical_regimes is None:
            # Default: all major regime types for spawn context
            self.canonical_regimes = ["crash", "bull", "bear", "sideways", "recovery", "volatile"]
        if self.winner_trait_bias is None:
            # Learnings from Run 1: Top 50 vs Bottom 50 differences
            self.winner_trait_bias = {
                "risk_tolerance": (0.7, 1.0),  # High risk wins (+0.46 diff)
                "hold_duration_bias": (0.6, 1.0),  # Patient holds win (+0.34 diff)
                "exit_aggression": (0.0, 0.4),  # LOW exit aggression wins (-0.34 diff)
                "lookback_preference": (0.1, 0.5),  # Short lookback wins (-0.25 diff)
                "sentiment_weight": (0.5, 0.9),  # High sentiment weight (+0.20 diff)
                "profit_target_greed": (0.5, 0.9),  # Greedy targets (+0.18 diff)
                "sentiment_contrarian": (0.4, 0.8),  # Contrarian wins (+0.17 diff)
            }
        if self.db_path is None:
            self.db_path = str(Path(__file__).parent.parent / "data" / "evolution_run.db")


# =============================================================================
# Pattern Library - Load from PostgreSQL database
# =============================================================================


def load_patterns_from_db(
    max_patterns: int = 1000,
    min_fitness: float = 40.0,
    require_entry_conditions: bool = True,
) -> list[dict]:
    """
    Load patterns from PostgreSQL database.

    Args:
        max_patterns: Maximum number of patterns to load.
        min_fitness: Minimum fitness score (default 40 = proven patterns).
        require_entry_conditions: Only include patterns with entry conditions (default True).

    Returns:
        List of pattern dicts in engine-compatible format.
    """
    import os

    from sqlalchemy import create_engine, text

    # Get PostgreSQL connection from environment
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        # Build from components
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        user = os.getenv("POSTGRES_USER", "coinswarm")
        password = os.getenv("POSTGRES_PASSWORD", "coinswarm_dev_2024")
        database = os.getenv("POSTGRES_DB", "coinswarm")
        db_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"

    engine = create_engine(db_url)

    # Query proven patterns from PostgreSQL
    query = text("""
        SELECT pattern_id, name, origin, entry_conditions, exit_conditions,
               fitness_score, win_rate, sortino_ratio, calmar_ratio,
               expectancy_pct, alpha_pct, exit_efficiency, max_drawdown_pct
        FROM patterns
        WHERE entry_conditions IS NOT NULL
        AND is_active = true
        AND fitness_score >= :min_fitness
        ORDER BY fitness_score DESC
        LIMIT :limit
    """)

    raw_patterns = []
    with engine.connect() as conn:
        result = conn.execute(query, {"min_fitness": min_fitness, "limit": max_patterns * 2})
        for row in result:
            # JSONB columns are already parsed by psycopg2/SQLAlchemy
            entry_conds = row[3] if row[3] else []
            exit_conds = row[4] if row[4] else {}

            if require_entry_conditions and not entry_conds:
                continue

            # Columns: pattern_id, name, origin, entry_conditions, exit_conditions,
            #          fitness_score, win_rate, sortino_ratio, calmar_ratio,
            #          expectancy_pct, alpha_pct, exit_efficiency, max_drawdown_pct
            raw_patterns.append(
                {
                    "pattern_id": row[0],
                    "name": row[1],
                    "origin": row[2],
                    "entry_conditions": entry_conds,
                    "exit_conditions": exit_conds,
                    "fitness_score": row[5] or 0,
                    "win_rate_pct": row[6] or 0,
                    "sortino_ratio": row[7] or 0,
                    "calmar_ratio": row[8] or 0,
                    "expectancy_pct": row[9] or 0,
                    "alpha_pct": row[10] or 0,
                    "exit_efficiency": row[11] or 0.5,
                    "max_drawdown_pct": row[12] or 0,
                }
            )

    print(f"  Loaded {len(raw_patterns)} patterns from PostgreSQL")

    # Convert to engine-compatible format
    converted = []
    for p in raw_patterns:
        pattern = convert_pattern_format(p)
        if pattern and pattern.get("entry_conditions"):
            converted.append(pattern)

        if len(converted) >= max_patterns:
            break

    print(f"  Converted {len(converted)} patterns to engine format")
    return converted


def convert_pattern_format(raw: dict) -> dict | None:
    """
    Convert a pattern from list-format conditions to dict-format.

    Input format:
        entry_conditions: [
            {'indicator': 'rsi14', 'operator': '<', 'value': 30},
            ...
        ]

    Output format:
        entry_conditions: {
            'rsi14': {'operator': '<', 'value': 30},
            ...
        }
    """
    pattern_id = raw.get("pattern_id", raw.get("id", "unknown"))

    # Get conditions - can be list or dict
    raw_entry = raw.get("entry_conditions", raw.get("conditions", []))
    raw_exit = raw.get("exit_conditions", [])

    # Convert list format to dict format (for indicator conditions)
    def convert_conditions(conditions):
        if isinstance(conditions, dict):
            # Check if it's already indicator conditions (has operator/value)
            # or if it's exit params (stop_loss_pct, take_profit_pct)
            if any(k in conditions for k in ["stop_loss_pct", "take_profit_pct", "max_hold_periods"]):
                return conditions  # Exit params - pass through
            return conditions  # Already in correct format

        if not isinstance(conditions, list):
            return {}

        result = {}
        for cond in conditions:
            if not isinstance(cond, dict):
                continue
            indicator = cond.get("indicator")
            if not indicator:
                continue

            result[indicator] = {
                "operator": cond.get("operator", ">"),
                "value": cond.get("value", 0),
            }
        return result

    entry_conditions = convert_conditions(raw_entry)
    exit_conditions = convert_conditions(raw_exit) if raw_exit else {}

    if not entry_conditions:
        return None

    # Determine direction from conditions or existing field
    direction = raw.get("direction")
    if not direction:
        # Infer from condition types
        for ind, cond in entry_conditions.items():
            op = cond.get("operator", "")
            if "oversold" in ind.lower() or (op == "<" and "rsi" in ind.lower()):
                direction = "long"
                break
            if "overbought" in ind.lower() or (op == ">" and "rsi" in ind.lower() and cond.get("value", 0) > 50):
                direction = "short"
                break
        direction = direction or "long"  # Default to long

    return {
        "pattern_id": pattern_id,
        "name": raw.get("name", pattern_id),
        "description": raw.get("description", ""),
        "direction": direction,
        "entry_conditions": entry_conditions,
        "exit_conditions": exit_conditions,
        "origin": raw.get("origin", "unknown"),
        "fitness_score": raw.get("fitness_score", 0),
        "win_rate_pct": raw.get("win_rate_pct", 50),
    }


# Lazy-loaded patterns (loaded on first access)
_LOADED_PATTERNS = None


def get_initial_patterns(max_patterns: int = 500, min_fitness: float = 40.0) -> list[dict]:
    """
    Get initial patterns for agent evolution from PostgreSQL.

    Args:
        max_patterns: Maximum patterns to load.
        min_fitness: Minimum fitness score (default 40 = proven patterns).

    Returns:
        List of pattern dicts in engine-compatible format.
    """
    global _LOADED_PATTERNS
    if _LOADED_PATTERNS is None:
        print(f"\n[Patterns] Loading proven patterns (fitness >= {min_fitness}) from PostgreSQL...")
        _LOADED_PATTERNS = load_patterns_from_db(
            max_patterns=max_patterns,
            min_fitness=min_fitness,
        )
        print(f"[Patterns] Loaded {len(_LOADED_PATTERNS)} patterns")
    return _LOADED_PATTERNS


# =============================================================================
# Data Loading
# =============================================================================


class EnhancedOHLCVLoader(OHLCVLoader):
    """OHLCV Loader that uses PostgreSQL enhanced_candles table.

    Note: This now inherits from the PostgreSQL-based OHLCVLoader.
    The load_candles method is inherited and loads from PostgreSQL.
    """

    def __init__(self):
        # Parent class uses PostgreSQL - no SQLite path needed
        super().__init__()


# =============================================================================
# Evolution Runner
# =============================================================================


def run_evolution(config: EvolutionRunConfig):
    """Run the full evolution process."""

    print("=" * 60)
    print("AGENT EVOLUTION SYSTEM")
    print("=" * 60)
    print(f"Initial Population: {config.initial_population}")
    print(f"Generations: {config.generations}")
    print(f"Assets: {config.assets}")
    print(f"Candles per backtest: {config.candles_per_backtest}")
    print("=" * 60)

    # Initialize database
    Path(config.db_path).parent.mkdir(parents=True, exist_ok=True)
    db = AgentDatabase(config.db_path)

    # Initialize data loader
    loader = EnhancedOHLCVLoader()

    # Load patterns from database
    patterns = get_initial_patterns(max_patterns=500)
    patterns_dict = {p["pattern_id"]: p for p in patterns}

    # Initialize backtest engine with AI zone mode
    ai_mode = AIZoneMode(config.ai_zone_mode.lower())
    print(f"AI Zone Mode: {ai_mode.value}")
    engine = LocalBacktestEngine(loader=loader, patterns=patterns_dict, ai_zone_mode=ai_mode)

    # Create evolution config
    evo_config = EvolutionConfig(
        population_size=config.initial_population,
        elite_percent=config.elite_percent,
        survival_percent=config.survival_percent,
        mutation_rate=config.mutation_rate,
        min_trades_for_fitness=10,  # Lower threshold for testing
    )

    # Initialize population (with trait bias from learnings if configured)
    print("\n[1/4] Initializing population...")
    trait_bias = getattr(config, "winner_trait_bias", None) if getattr(config, "seed_from_winners", False) else None
    if trait_bias:
        print(f"  Applying trait bias from Run 1 learnings: {len(trait_bias)} traits biased")

    population = initialize_population(
        population_size=config.initial_population,
        available_patterns=patterns,
        base_seed=int(time.time()),
        db=db,
        trait_bias=trait_bias,
    )

    print(f"Created {len(population)} agents:")
    for agent in population:
        traits = AgentTraits(**agent.traits)
        print(
            f"  - {agent.agent_name}: risk={traits.risk_tolerance:.2f}, "
            f"momentum={traits.momentum_vs_reversion:.2f}, "
            f"patterns={agent.pattern_ids}"
        )

    # Build dataset - HYBRID MODE
    print("\n[2/4] Running initial backtests...")

    datasets = []

    if config.use_full_history:
        # HYBRID MODE: Test on full history across all assets
        # Generate random windows across the entire dataset
        import random

        from Fast_Swarm.local_agents.backtest.data import OHLCVLoader

        print(f"  HYBRID MODE: Testing on full history across {len(config.assets)} assets")
        print(
            f"  Generating {config.windows_per_asset} random windows per asset ({config.candles_per_backtest} candles each)"
        )

        loader = OHLCVLoader()
        total_windows = 0

        for asset in config.assets:
            try:
                # Get data range for this asset
                data_range = loader.get_date_range(asset, config.timeframe)
                if data_range is None or data_range == (0, 0):
                    print(f"    WARNING: No data for {asset}, skipping")
                    continue

                min_ts, max_ts = data_range
                range_ms = max_ts - min_ts
                window_ms = config.candles_per_backtest * 3600 * 1000  # 1h candles in ms

                if range_ms < window_ms:
                    print(f"    WARNING: {asset} has insufficient data ({range_ms / 86400000:.0f} days), skipping")
                    continue

                # Generate random starting points
                for i in range(config.windows_per_asset):
                    start_ts = min_ts + random.randint(0, range_ms - window_ms)
                    end_ts = start_ts + window_ms

                    datasets.append(
                        {
                            "assets": [asset],
                            "timeframe": config.timeframe,
                            "start_ts": start_ts,
                            "end_ts": end_ts,
                            "window_id": f"{asset}-window-{i}",
                        }
                    )
                    total_windows += 1

            except Exception as e:
                print(f"    ERROR loading {asset}: {e}")
                continue

        print(f"  Created {total_windows} test windows across {len(config.assets)} assets")

        # Optionally add canonical periods for context labels (spawn context)
        if config.use_canonical_for_context:
            from canonical_periods import CANONICAL_PERIODS

            DATA_AVAILABLE_FROM = "2019-09-23"

            context_periods = [
                p for p in CANONICAL_PERIODS if p.regime in config.canonical_regimes and p.start >= DATA_AVAILABLE_FROM
            ]
            print(f"  Also loaded {len(context_periods)} canonical periods for spawn context (regime labels)")
            # Store for reference during spawning (not for testing)
            # This is just informational - the actual testing uses the random windows

    elif hasattr(config, "use_canonical_periods") and config.use_canonical_periods:
        # LEGACY MODE: Only test on canonical periods (limited)
        from canonical_periods import CANONICAL_PERIODS

        DATA_AVAILABLE_FROM = "2019-09-23"

        periods = [
            p
            for p in CANONICAL_PERIODS
            if p.regime in config.canonical_regimes and p.asset in config.assets and p.start >= DATA_AVAILABLE_FROM
        ]
        print(f"  LEGACY MODE: Using {len(periods)} canonical periods across {config.canonical_regimes}")

        for period in periods:
            start_ts, end_ts = period.to_timestamps()
            datasets.append(
                {
                    "assets": [period.asset],
                    "timeframe": config.timeframe,
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                    "period_id": period.period_id,
                    "regime": period.regime,
                }
            )
    else:
        # Fallback: single window per asset
        datasets = [
            {
                "assets": config.assets,
                "timeframe": config.timeframe,
                "limit": config.candles_per_backtest,
            }
        ]

    for i, agent in enumerate(population):
        print(f"  Backtesting agent {i + 1}/{len(population)}: {agent.agent_name}...", end=" ")

        all_trades = []
        for ds in datasets:
            trades = engine.run(agent, ds)
            all_trades.extend(trades)

        # Store trades
        for trade in all_trades:
            db.create_trade(trade)

        # Calculate fitness (AI usage rate already tracked per-agent in trades)
        if all_trades:
            fitness = evaluate_agent_fitness(agent, all_trades)
            db.update_agent_fitness(agent.agent_id, fitness, backtest_count=len(datasets))

            # Report AI usage rate for visibility
            ai_trades = sum(1 for t in all_trades if t.ai_consulted)
            ai_rate = ai_trades / len(all_trades) if all_trades else 0
            print(f"{len(all_trades)} trades, fitness={fitness:.1f} (AI: {ai_rate * 100:.0f}%)")
        else:
            print("0 trades")

    # Get initial stats
    stats = get_population_stats(db)
    print("\nInitial Population Stats:")
    print(f"  Avg Fitness: {stats.avg_fitness:.1f}")
    print(f"  Best Fitness: {stats.best_fitness:.1f}")
    print(f"  Worst Fitness: {stats.worst_fitness:.1f}")

    # Evolution loop
    print("\n[3/4] Running evolution cycles...")

    generation_results = []

    for gen in range(1, config.generations + 1):
        print(f"\n--- Generation {gen}/{config.generations} ---")

        # Refresh population from DB
        population = [db.get_agent(a.agent_id) for a in population if a]
        population = [a for a in population if a and a.status == "active"]

        # Run evolution cycle (use first dataset or all)
        # For evolution, we use all canonical periods
        result = run_evolution_cycle(
            population=population,
            available_patterns=patterns,
            backtest_engine=engine,
            dataset=datasets,  # Pass list of datasets
            generation=gen,
            config=evo_config,
            seed=int(time.time()) + gen * 1000,
            db=db,
        )

        generation_results.append(result)

        # Update population
        population = result.survivors + result.children

        print(f"  Survivors: {len(result.survivors)}")
        print(f"  New Children: {len(result.children)}")
        print(f"  Retired: {len(result.retired)}")
        print(f"  Avg Fitness: {result.avg_fitness:.1f}")
        print(f"  Best Fitness: {result.best_fitness:.1f}")
        print(f"  Best Agent: {result.best_agent_id[:8]}...")
        print(f"  Elapsed: {result.elapsed_ms}ms")

    # Final summary
    print("\n[4/4] Evolution Complete!")
    print("=" * 60)

    # AI Zone stats
    if hasattr(engine, "ai_zone_handler") and engine.ai_zone_handler.decision_count > 0:
        print("\nAI Zone Stats:")
        print(f"  Total LLM decisions: {engine.ai_zone_handler.decision_count}")
        print(f"  Avg latency: {engine.ai_zone_handler.avg_latency_ms:.0f}ms")

    # Get final population
    final_stats = get_population_stats(db)

    print("\nFinal Population Stats:")
    print(f"  Total Agents (all time): {final_stats.total}")
    print(f"  Active Agents: {final_stats.active}")
    print(f"  Avg Fitness: {final_stats.avg_fitness:.1f}")
    print(f"  Best Fitness: {final_stats.best_fitness:.1f}")
    print(f"  Avg Generation: {final_stats.avg_generation:.1f}")

    # Fitness progression
    print("\nFitness Progression:")
    print("Gen | Avg Fitness | Best Fitness | Best Agent")
    print("-" * 50)
    for i, result in enumerate(generation_results, 1):
        print(
            f" {i:2} |    {result.avg_fitness:5.1f}    |    {result.best_fitness:5.1f}     | {result.best_agent_id[:8]}..."
        )

    # Top agents
    print("\nTop 5 Agents:")
    all_agents = db.get_all_active_agents()
    top_agents = sorted(all_agents, key=lambda a: a.fitness_score or 0, reverse=True)[:5]

    for i, agent in enumerate(top_agents, 1):
        traits = AgentTraits(**agent.traits)
        trade_count = len(db.get_agent_trades(agent.agent_id))
        print(f"  {i}. {agent.agent_name}")
        print(f"     Fitness: {agent.fitness_score:.1f}, Trades: {trade_count}, Gen: {agent.generation}")
        print(f"     Risk: {traits.risk_tolerance:.2f}, Momentum: {traits.momentum_vs_reversion:.2f}")

    return generation_results, db


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    # RUN 2: HYBRID MODE - Full history testing with learnings from Run 1
    # Uses trait biases discovered from analyzing 2,789 agents and 1.9M trades

    # Get all assets from enhanced_candles.db
    from Fast_Swarm.local_agents.backtest.data import OHLCVLoader

    loader = OHLCVLoader()
    ALL_ASSETS = loader.get_available_assets("1h")
    print(f"Found {len(ALL_ASSETS)} assets in enhanced_candles.db")

    # Create fresh database for Run 2
    run2_db = str(Path(__file__).parent.parent / "data" / "evolution_run_v2.db")

    config = EvolutionRunConfig(
        initial_population=100,  # Start smaller, scale up
        generations=50,  # 50 generations
        elite_percent=0.10,  # Top 10% are elite
        survival_percent=0.40,  # Top 40% survive (less aggressive)
        mutation_rate=0.15,  # 15% mutation
        # HYBRID MODE: Full history testing
        assets=ALL_ASSETS[:30],  # Top 30 most liquid
        timeframe="1h",
        use_full_history=True,  # Test on ALL data, not just canonical
        use_canonical_for_context=True,  # Use canonical for spawn context labels
        candles_per_backtest=2000,  # 2000 candles per window (~83 days)
        windows_per_asset=5,  # 5 random windows per asset
        # AI Zone Mode - Use LLM for AI_REFLECT decisions
        ai_zone_mode="llm",  # Real Ollama calls for uncertain trades
        # Apply learnings from Run 1
        seed_from_winners=True,
        winner_trait_bias={
            "risk_tolerance": (0.7, 1.0),  # High risk wins (+0.46 diff)
            "hold_duration_bias": (0.6, 1.0),  # Patient holds win (+0.34 diff)
            "exit_aggression": (0.0, 0.4),  # LOW exit aggression wins (-0.34 diff)
            "lookback_preference": (0.1, 0.5),  # Short lookback wins (-0.25 diff)
            "sentiment_weight": (0.5, 0.9),  # High sentiment weight (+0.20 diff)
            "profit_target_greed": (0.5, 0.9),  # Greedy targets (+0.18 diff)
            "sentiment_contrarian": (0.4, 0.8),  # Contrarian wins (+0.17 diff)
        },
        # Database for Run 2
        db_path=run2_db,
    )

    print("\n" + "=" * 60)
    print("EVOLUTION RUN 2 - HYBRID MODE + AI")
    print("=" * 60)
    print(f"  Population: {config.initial_population}")
    print(f"  Generations: {config.generations}")
    print(f"  Assets: {len(config.assets)}")
    print(f"  Windows per asset: {config.windows_per_asset}")
    print(f"  Candles per window: {config.candles_per_backtest}")
    print(f"  Total test windows: ~{len(config.assets) * config.windows_per_asset}")
    print(f"  AI Zone Mode: {config.ai_zone_mode.upper()} (Ollama phi4:14b)")
    print("  Trait bias: ENABLED (from Run 1 learnings)")
    print(f"  Database: {run2_db}")
    print("=" * 60)

    results, db = run_evolution(config)

    print("\n✓ Evolution Run 2 complete!")
    print(f"  Database: {config.db_path}")
