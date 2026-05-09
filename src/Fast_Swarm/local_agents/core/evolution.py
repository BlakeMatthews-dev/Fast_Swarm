"""
Agent Evolution - The Main Evolution Loop.

Phases:
1. BACKTEST - Run agents against dataset
2. EVALUATE - Calculate fitness scores
3. SELECT - Top 10% elite, top 70% survive
4. REPRODUCE - Crossover + mutation + memory inheritance
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from Fast_Swarm.local_agents.config import Config
from Fast_Swarm.local_agents.core.genesis import spawn_child
from Fast_Swarm.local_agents.core.memory import (
    Memory,
    apply_inheritance_decay,
    create_memory,
    select_for_inheritance,
)
from Fast_Swarm.local_agents.core.state import AgentDatabase, AgentRecord, TradeRecord
from Fast_Swarm.local_agents.core.traits import AgentTraits
from Fast_Swarm.local_agents.shared.fitness import calculate_agent_fitness
from Fast_Swarm.local_agents.shared.metrics import Trade, calculate_all_metrics
from Fast_Swarm.local_agents.shared.rng import seeded_random

# =============================================================================
# Protocols
# =============================================================================


class BacktestEngine(Protocol):
    """Protocol for backtest engine."""

    def run(
        self,
        agent: AgentRecord,
        dataset: any,
    ) -> list[TradeRecord]:
        """Run backtest and return trades."""
        ...


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class EvolutionConfig:
    """Configuration for evolution cycle."""

    population_size: int = 20
    elite_percent: float = 0.10
    survival_percent: float = 0.70
    mutation_rate: float = 0.10
    max_generations: int = 100
    convergence_threshold: float = 0.01
    min_trades_for_fitness: int = 30

    @classmethod
    def from_config(cls) -> "EvolutionConfig":
        """Load from Config class."""
        return cls(
            population_size=Config.POPULATION_SIZE,
            elite_percent=Config.ELITE_PERCENT,
            survival_percent=Config.SURVIVAL_PERCENT,
            mutation_rate=Config.MUTATION_RATE,
            max_generations=Config.MAX_GENERATIONS,
            convergence_threshold=Config.CONVERGENCE_THRESHOLD,
            min_trades_for_fitness=Config.MIN_TRADES_FOR_SIGNIFICANCE,
        )


@dataclass
class EvolutionResult:
    """Result of an evolution cycle."""

    generation: int
    survivors: list[AgentRecord]
    children: list[AgentRecord]
    retired: list[str]  # Agent IDs
    avg_fitness: float
    best_fitness: float
    best_agent_id: str
    elapsed_ms: int


@dataclass
class PopulationStats:
    """Statistics for the current population."""

    total: int
    active: int
    avg_fitness: float
    best_fitness: float
    worst_fitness: float
    avg_generation: float


# =============================================================================
# Fitness Evaluation
# =============================================================================


def evaluate_agent_fitness(
    agent: AgentRecord,
    trades: list[TradeRecord],
    benchmark_returns: list[float] | None = None,
) -> float:
    """
    Evaluate agent fitness from trade results.

    Args:
        agent: Agent record.
        trades: List of trades.
        benchmark_returns: Optional benchmark for alpha calculation.

    Returns:
        Fitness score 0-100.

    Note:
        AI consultation rate is tracked per-agent (via TradeRecord.ai_consulted).
        AI accuracy (correct decisions among AI-consulted trades) contributes
        to fitness via the ai_accuracy_score component.
    """
    if len(trades) < Config.MIN_TRADES_FOR_SIGNIFICANCE:
        return 0.0  # Not enough trades

    # Convert TradeRecords to Trade objects for metrics
    metric_trades = [
        Trade(
            trade_id=t.trade_id,
            pnl_pct=t.pnl_pct,
            entry_confidence=t.entry_confidence,
            mfe_pct=t.mfe_pct,
            mae_pct=t.mae_pct,
            position_size_pct=t.position_size_pct,
            won=t.pnl_pct > 0,
        )
        for t in trades
    ]

    # Calculate all metrics
    metrics = calculate_all_metrics(metric_trades, benchmark_returns)

    # Count AI zone decisions (agent-level, not pattern-level)
    ai_trades = [t for t in trades if t.ai_consulted]
    ai_correct_count = sum(1 for t in ai_trades if t.pnl_pct > 0)
    ai_usage = len(ai_trades) / len(trades) if trades else 0

    # Create metrics object for fitness calculation
    class AgentMetrics:
        expectancy_pct = metrics.expectancy_pct
        alpha_pct = metrics.alpha_pct
        calibration_score = metrics.calibration_score
        win_rate_pct = metrics.win_rate_pct
        sortino_ratio = metrics.sortino_ratio
        max_drawdown_pct = metrics.max_drawdown_pct
        exit_efficiency = metrics.exit_efficiency
        loss_sizing_ratio = metrics.loss_sizing_ratio
        ai_decisions = len(ai_trades)
        ai_correct = ai_correct_count
        ai_usage_rate = ai_usage  # Available for future penalty

    # Calculate fitness
    result = calculate_agent_fitness(AgentMetrics())
    base_fitness = result.final_fitness

    # Apply AI usage penalty with accuracy consideration
    # - All AI usage has a base cost (time + compute)
    # - 50% accuracy = coin toss = the fail line
    # - Below 50% = heavy punishment (worse than random)

    ai_accuracy = ai_correct_count / len(ai_trades) if ai_trades else 0.5
    base_cost = ai_usage * 0.05  # Max 5% penalty just for using AI

    accuracy_vs_coinflip = ai_accuracy - 0.5  # Range: -0.5 to +0.5

    if accuracy_vs_coinflip >= 0:
        # Better than random: just pay the base cost (slightly reduced by accuracy)
        penalty = base_cost * (1 - accuracy_vs_coinflip)
    else:
        # WORSE than random: heavy punishment
        badness = abs(accuracy_vs_coinflip) * 2  # Scale to 0→1
        penalty = base_cost + (ai_usage**1.5 * badness * 0.6)

    ai_multiplier = 1.0 - penalty
    return base_fitness * ai_multiplier


# =============================================================================
# Selection
# =============================================================================

# CRITICAL: TOP 10 agents (FIXED number) breed, not top percentage.
# This is separate from cloning (which uses top N%).
BREEDING_POOL_SIZE = 10  # FIXED number for breeding


def select_for_breeding(population: list[AgentRecord]) -> list[AgentRecord]:
    """
    Select agents for breeding (crossover).

    CRITICAL: Uses TOP 10 FIXED, not a percentage.

    This is the elite pool from which parent pairs are selected for crossover.
    Exactly 10 agents (or all if fewer than 10) are selected.

    Args:
        population: Current population of agents.

    Returns:
        List of top 10 agents by fitness (breeding pool).
    """
    # Sort by fitness descending
    ranked = sorted(population, key=lambda a: a.fitness_score or 0, reverse=True)

    # FIXED: Top 10 agents, not percentage
    breeding_count = min(BREEDING_POOL_SIZE, len(ranked))
    return ranked[:breeding_count]


def select_for_cloning(
    population: list[AgentRecord],
    config: EvolutionConfig,
) -> list[AgentRecord]:
    """
    Select agents for cloning (with mutation).

    Uses top N% (elite_percent from config), SEPARATE from breeding.

    Args:
        population: Current population of agents.
        config: Evolution configuration with elite_percent.

    Returns:
        List of agents to clone.
    """
    # Sort by fitness descending
    ranked = sorted(population, key=lambda a: a.fitness_score or 0, reverse=True)

    # Top N% for cloning
    clone_count = max(1, int(len(ranked) * config.elite_percent))
    return ranked[:clone_count]


def select_survivors(
    population: list[AgentRecord],
    config: EvolutionConfig,
) -> tuple[list[AgentRecord], list[AgentRecord], list[AgentRecord]]:
    """
    Select survivors from population.

    Note: This function returns 'elite' for backward compatibility,
    but the breeding pool should use select_for_breeding() instead.

    Returns:
        Tuple of (elite, survivors, retired).
        - elite: Top agents (for backward compat, use select_for_breeding for breeding)
        - survivors: Agents that survive to next generation
        - retired: Agents that are culled
    """
    # Sort by fitness
    ranked = sorted(population, key=lambda a: a.fitness_score or 0, reverse=True)

    # For survivors/retired: use percentage-based selection
    survive_count = max(1, int(len(ranked) * config.survival_percent))

    # Elite for backward compatibility (but breeding uses select_for_breeding)
    elite_count = max(1, int(len(ranked) * config.elite_percent))
    elite = ranked[:elite_count]

    survivors = ranked[:survive_count]
    retired = ranked[survive_count:]

    return elite, survivors, retired


def select_parents(
    elite: list[AgentRecord],
    seed: int,
) -> tuple[AgentRecord, AgentRecord]:
    """
    Select two parents from elite pool.

    Uses fitness-weighted selection.
    """
    if len(elite) < 2:
        return elite[0], elite[0]

    rng = seeded_random(seed)

    # Calculate selection weights
    total_fitness = sum(a.fitness_score or 1 for a in elite)
    weights = [(a.fitness_score or 1) / total_fitness for a in elite]

    # Weighted random selection
    def pick():
        r = rng()
        cumsum = 0
        for i, w in enumerate(weights):
            cumsum += w
            if r <= cumsum:
                return elite[i]
        return elite[-1]

    parent_a = pick()
    parent_b = pick()

    # Ensure different parents if possible
    attempts = 0
    while parent_b.agent_id == parent_a.agent_id and len(elite) > 1 and attempts < 10:
        parent_b = pick()
        attempts += 1

    return parent_a, parent_b


# =============================================================================
# Memory Inheritance
# =============================================================================


def inherit_memories(
    parent_a: AgentRecord,
    parent_b: AgentRecord,
    child_id: str,
    child_traits: AgentTraits,
    db: AgentDatabase,
) -> list[Memory]:
    """
    Inherit memories from parents to child.

    Uses trait-based condensation and priority selection.
    """
    # Get parent memories
    memories_a = db.get_agent_memories(parent_a.agent_id)
    memories_b = db.get_agent_memories(parent_b.agent_id)

    all_memories = memories_a + memories_b

    if not all_memories:
        return []

    # Select based on condensation rate
    condensation = child_traits.memory_condensation
    selected = select_for_inheritance(all_memories, condensation)

    # Apply decay
    decay_rate = child_traits.inheritance_decay
    inherited = []

    for mem in selected:
        # Create new memory for child
        child_mem = create_memory(
            agent_id=child_id,
            memory_type=mem.memory_type,
            content=mem.content,
            weight=mem.weight,
            confidence=mem.confidence,
            context_snapshot=mem.context_snapshot,
        )

        # Apply decay
        child_mem = apply_inheritance_decay(child_mem, decay_rate)

        # Mark as inherited
        child_mem.spawned_from = mem.memory_id

        # Save to database
        db.create_memory(child_mem)
        inherited.append(child_mem)

    return inherited


# =============================================================================
# Evolution Cycle
# =============================================================================


def run_evolution_cycle(
    population: list[AgentRecord],
    available_patterns: list[dict],
    backtest_engine: BacktestEngine,
    dataset: any,
    generation: int,
    config: EvolutionConfig | None = None,
    seed: int = 42,
    use_llm: bool = False,
    llm_call: Callable[[str], str] | None = None,
    db: AgentDatabase | None = None,
) -> EvolutionResult:
    """
    Run one generation of evolution.

    Args:
        population: Current population.
        available_patterns: Available patterns.
        backtest_engine: Backtest engine.
        dataset: Dataset for backtesting.
        generation: Current generation number.
        config: Evolution configuration.
        seed: Random seed.
        use_llm: Use LLM for child spawning.
        llm_call: LLM call function.
        db: Database instance.

    Returns:
        EvolutionResult with new population.
    """
    start_time = time.time()

    if config is None:
        config = EvolutionConfig.from_config()

    if db is None:
        db = AgentDatabase()

    # Phase 1: BACKTEST
    # Handle both single dataset and list of datasets
    datasets = dataset if isinstance(dataset, list) else [dataset]

    for agent in population:
        all_trades = []
        for ds in datasets:
            trades = backtest_engine.run(agent, ds)
            all_trades.extend(trades)

        # Store trades
        for trade in all_trades:
            db.create_trade(trade)

        # Update backtest count
        db.update_agent_fitness(agent.agent_id, agent.fitness_score or 0, (agent.backtest_count or 0) + len(datasets))

    # Phase 2: EVALUATE
    for agent in population:
        trades = db.get_agent_trades(agent.agent_id)
        fitness = evaluate_agent_fitness(agent, trades)
        db.update_agent_fitness(agent.agent_id, fitness)
        agent.fitness_score = fitness

    # Phase 3: SELECT
    # Get breeding pool (TOP 10 FIXED) and cloning pool (top N%) SEPARATELY
    breeding_pool = select_for_breeding(population)  # TOP 10 FIXED
    cloning_pool = select_for_cloning(population, config)  # Top N%

    # Also get survivors/retired for population management
    elite, survivors, retired = select_survivors(population, config)

    # Mark retired agents
    for agent in retired:
        if agent.fitness_score < Config.FITNESS_DEATH_THRESHOLD:
            db.update_agent_status(agent.agent_id, "dead")
        else:
            db.update_agent_status(agent.agent_id, "retired")

    # Phase 4: REPRODUCE
    children = []
    children_needed = config.population_size - len(survivors)

    # CRITICAL: Use breeding_pool (TOP 10 FIXED), not elite (percentage-based)
    for i in range(children_needed):
        parent_a, parent_b = select_parents(breeding_pool, seed + i * 100)

        child = spawn_child(
            parent_a=parent_a,
            parent_b=parent_b,
            seed=seed + i * 1000 + generation * 10000,
            available_patterns=available_patterns,
            mutation_rate=config.mutation_rate,
            use_llm=use_llm,
            llm_call=llm_call,
            db=db,
        )

        # Inherit memories
        child_traits = AgentTraits(**child.traits)
        inherit_memories(parent_a, parent_b, child.agent_id, child_traits, db)

        children.append(child)

    # Calculate stats
    all_agents = survivors + children
    avg_fitness = sum(a.fitness_score or 0 for a in all_agents) / len(all_agents) if all_agents else 0
    best_agent = max(all_agents, key=lambda a: a.fitness_score or 0) if all_agents else None

    elapsed_ms = int((time.time() - start_time) * 1000)

    return EvolutionResult(
        generation=generation,
        survivors=survivors,
        children=children,
        retired=[a.agent_id for a in retired],
        avg_fitness=avg_fitness,
        best_fitness=best_agent.fitness_score if best_agent else 0,
        best_agent_id=best_agent.agent_id if best_agent else "",
        elapsed_ms=elapsed_ms,
    )


# =============================================================================
# Full Evolution Run
# =============================================================================


def run_evolution(
    available_patterns: list[dict],
    backtest_engine: BacktestEngine,
    dataset: any,
    config: EvolutionConfig | None = None,
    base_seed: int = 42,
    use_llm: bool = False,
    llm_call: Callable[[str], str] | None = None,
    db: AgentDatabase | None = None,
    on_generation: Callable[[EvolutionResult], None] | None = None,
) -> list[EvolutionResult]:
    """
    Run full evolution across multiple generations.

    Args:
        available_patterns: Available patterns.
        backtest_engine: Backtest engine.
        dataset: Dataset for backtesting.
        config: Evolution configuration.
        base_seed: Base random seed.
        use_llm: Use LLM for spawning.
        llm_call: LLM call function.
        db: Database instance.
        on_generation: Callback after each generation.

    Returns:
        List of EvolutionResults.
    """
    if config is None:
        config = EvolutionConfig.from_config()

    if db is None:
        db = AgentDatabase()

    # Initialize population
    from Fast_Swarm.local_agents.core.genesis import initialize_population

    population = initialize_population(
        population_size=config.population_size,
        available_patterns=available_patterns,
        base_seed=base_seed,
        use_llm=use_llm,
        llm_call=llm_call,
        db=db,
    )

    results = []
    prev_avg_fitness = 0

    for gen in range(1, config.max_generations + 1):
        result = run_evolution_cycle(
            population=[db.get_agent(a.agent_id) for a in population if a],
            available_patterns=available_patterns,
            backtest_engine=backtest_engine,
            dataset=dataset,
            generation=gen,
            config=config,
            seed=base_seed + gen * 100000,
            use_llm=use_llm,
            llm_call=llm_call,
            db=db,
        )

        results.append(result)
        population = result.survivors + result.children

        if on_generation:
            on_generation(result)

        # Check convergence
        fitness_improvement = abs(result.avg_fitness - prev_avg_fitness)
        if fitness_improvement < config.convergence_threshold and gen > 5:
            break

        prev_avg_fitness = result.avg_fitness

    return results


# =============================================================================
# Utility Functions
# =============================================================================


def get_population_stats(db: AgentDatabase) -> PopulationStats:
    """Get statistics for current population."""
    agents = db.get_all_active_agents()

    if not agents:
        return PopulationStats(
            total=0,
            active=0,
            avg_fitness=0,
            best_fitness=0,
            worst_fitness=0,
            avg_generation=0,
        )

    fitnesses = [a.fitness_score or 0 for a in agents]
    generations = [a.generation for a in agents]

    return PopulationStats(
        total=len(agents),
        active=len(agents),
        avg_fitness=sum(fitnesses) / len(fitnesses),
        best_fitness=max(fitnesses),
        worst_fitness=min(fitnesses),
        avg_generation=sum(generations) / len(generations),
    )
