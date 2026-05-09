# Evolutionary Systems

> **Genetic Algorithms for Pattern and Agent Evolution**
>
> How trading strategies evolve through competition and selection.

---

## Overview

Coinswarm uses evolutionary principles at multiple levels:
1. **Pattern Evolution**: Trading rules compete and evolve
2. **Agent Evolution**: Personality traits mutate and propagate
3. **Roster Evolution**: Team compositions adapt to regimes

---

## Source Papers

| Paper | Key Contribution | Path |
|-------|------------------|------|
| CGA-Agent | Genetic trading strategies | [../papers/arxiv-2510.07943-cga-agent.md](../papers/arxiv-2510.07943-cga-agent.md) |
| TradingAgents | Agent specialization | [../papers/arxiv-2412.20138-trading-agents.md](../papers/arxiv-2412.20138-trading-agents.md) |

---

## Core Evolutionary Concepts

### Selection Pressure

```
┌─────────────────────────────────────────────────────────────────┐
│                    SELECTION PRESSURE                            │
│                                                                  │
│   High Fitness                                                   │
│   ────────────►  REPRODUCE (clone + mutate)                     │
│   (Top 20%)                                                     │
│                                                                  │
│   Medium Fitness                                                 │
│   ────────────►  SURVIVE (continue trading)                     │
│   (Middle 50%)                                                   │
│                                                                  │
│   Low Fitness                                                    │
│   ────────────►  DIE (remove from pool)                         │
│   (Bottom 30%)                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Fitness Function

```python
def calculate_fitness(
    pattern: Pattern,
    min_trades: int = 30
) -> float:
    """
    Calculate fitness score for selection.

    Fitness considers multiple objectives:
    - Risk-adjusted returns (Sharpe)
    - Consistency (win rate)
    - Robustness (number of trades)
    - Drawdown control

    Paper Reference: CGA-Agent
    "Multi-objective fitness enables discovery of robust strategies"
    """
    if pattern.number_of_runs < min_trades:
        return 0.0  # Not enough data

    # Component scores (each 0-100)
    sharpe_score = min(100, max(0, pattern.sharpe_ratio * 30 + 50))
    roi_score = min(100, max(0, pattern.total_roi_pct * 2 + 50))
    winrate_score = pattern.win_rate * 100
    drawdown_score = max(0, 100 - pattern.max_drawdown_pct * 200)

    # Trade count bonus (reward statistical significance)
    trade_bonus = min(20, pattern.number_of_runs / 10)

    # Weighted combination
    fitness = (
        0.30 * sharpe_score +
        0.25 * roi_score +
        0.20 * winrate_score +
        0.15 * drawdown_score +
        0.10 * trade_bonus
    )

    return float(np.clip(fitness, 0, 100))
```

---

## Pattern Evolution

### Genetic Representation

Patterns are encoded as chromosome-like structures:

```python
@dataclass
class PatternGenome:
    """
    Genetic representation of a trading pattern.

    Each gene represents a condition parameter that can mutate.
    """
    genes: dict[str, GeneValue]
    # Example:
    # {
    #     'rsi_min': GeneValue(22.0, bounds=(0, 50)),
    #     'rsi_max': GeneValue(35.0, bounds=(20, 70)),
    #     'macd_min': GeneValue(-0.5, bounds=(-2, 0)),
    #     'volume_ratio_min': GeneValue(1.2, bounds=(0.5, 3.0)),
    #     'hold_hours_max': GeneValue(48, bounds=(1, 168)),
    # }

    fitness: float = 0.0
    generation: int = 0
    parent_id: Optional[str] = None


@dataclass
class GeneValue:
    """Single gene with value and mutation bounds."""
    value: float
    bounds: tuple[float, float]
    mutation_rate: float = 0.1  # Max 10% change per generation
```

### Mutation Operator

```python
def mutate_pattern(
    genome: PatternGenome,
    mutation_rate: float = 0.1,
    mutation_strength: float = 0.1
) -> PatternGenome:
    """
    Apply random mutations to pattern genome.

    Paper Reference: CGA-Agent
    "Small random mutations enable local search around good solutions"

    Args:
        mutation_rate: Probability each gene mutates (0.1 = 10%)
        mutation_strength: Max relative change (0.1 = ±10%)
    """
    new_genes = {}

    for gene_name, gene in genome.genes.items():
        if random.random() < mutation_rate:
            # Apply mutation
            range_size = gene.bounds[1] - gene.bounds[0]
            max_delta = range_size * mutation_strength

            delta = random.uniform(-max_delta, max_delta)
            new_value = gene.value + delta

            # Enforce bounds
            new_value = max(gene.bounds[0], min(gene.bounds[1], new_value))

            new_genes[gene_name] = GeneValue(
                value=new_value,
                bounds=gene.bounds,
                mutation_rate=gene.mutation_rate
            )
        else:
            new_genes[gene_name] = gene

    return PatternGenome(
        genes=new_genes,
        fitness=0.0,  # Reset - needs re-evaluation
        generation=genome.generation + 1,
        parent_id=genome.pattern_id
    )
```

### Crossover Operator

```python
def crossover_patterns(
    parent_a: PatternGenome,
    parent_b: PatternGenome
) -> PatternGenome:
    """
    Combine two parent patterns into offspring.

    Uses uniform crossover: each gene randomly selected from either parent.

    Paper Reference: CGA-Agent
    "Crossover combines beneficial traits from multiple strategies"
    """
    child_genes = {}

    all_genes = set(parent_a.genes.keys()) | set(parent_b.genes.keys())

    for gene_name in all_genes:
        # Randomly select from parent A or B
        if random.random() < 0.5:
            if gene_name in parent_a.genes:
                child_genes[gene_name] = parent_a.genes[gene_name]
            else:
                child_genes[gene_name] = parent_b.genes[gene_name]
        else:
            if gene_name in parent_b.genes:
                child_genes[gene_name] = parent_b.genes[gene_name]
            else:
                child_genes[gene_name] = parent_a.genes[gene_name]

    return PatternGenome(
        genes=child_genes,
        fitness=0.0,
        generation=max(parent_a.generation, parent_b.generation) + 1,
        parent_id=f"{parent_a.pattern_id}+{parent_b.pattern_id}"
    )
```

### Selection Algorithm

```python
def select_next_generation(
    population: list[PatternGenome],
    elite_pct: float = 0.10,
    reproduce_pct: float = 0.20,
    survive_pct: float = 0.50,
    new_random_pct: float = 0.10
) -> list[PatternGenome]:
    """
    Select patterns for next generation.

    Strategy:
    - Elite (top 10%): Copy directly (no mutation)
    - Reproduce (next 20%): Clone with mutation
    - Survive (next 50%): Keep as-is
    - Die (bottom 30%): Remove
    - Add new random patterns (10%)

    Paper Reference: CGA-Agent - generational evolution
    """
    # Sort by fitness
    population.sort(key=lambda p: p.fitness, reverse=True)
    n = len(population)

    next_gen = []

    # Elite - preserve best
    elite_count = int(n * elite_pct)
    next_gen.extend(population[:elite_count])

    # Reproduce - clone and mutate top performers
    reproduce_count = int(n * reproduce_pct)
    for pattern in population[:reproduce_count]:
        offspring = mutate_pattern(pattern)
        next_gen.append(offspring)

    # Occasionally crossover top patterns
    if len(population) >= 2:
        for _ in range(reproduce_count // 4):
            parent_a = random.choice(population[:reproduce_count])
            parent_b = random.choice(population[:reproduce_count])
            if parent_a != parent_b:
                offspring = crossover_patterns(parent_a, parent_b)
                offspring = mutate_pattern(offspring)
                next_gen.append(offspring)

    # Survive - keep middle performers
    survive_count = int(n * survive_pct)
    survive_end = elite_count + reproduce_count + survive_count
    next_gen.extend(population[elite_count:survive_end])

    # New random - inject fresh genetic material
    new_count = int(n * new_random_pct)
    for _ in range(new_count):
        next_gen.append(generate_random_pattern())

    return next_gen
```

---

## Agent Evolution

### Trait Mutation

```python
def mutate_agent_traits(
    agent: Agent,
    mutation_strength: float = 0.10
) -> Agent:
    """
    Apply ±10% mutation to agent traits.

    Paper Reference: TradingAgents - agent specialization
    """
    new_traits = {}

    for trait_name, value in agent.traits.items():
        # Apply bounded mutation
        delta = random.uniform(-mutation_strength, mutation_strength)
        new_value = value + delta

        # Keep in [0, 1] range
        new_traits[trait_name] = max(0.0, min(1.0, new_value))

    return Agent(
        agent_id=generate_uuid(),
        name=f"{agent.name}_offspring",
        generation=agent.generation + 1,
        traits=new_traits,
        regime_affinity=agent.regime_affinity.copy(),
        status='active',
        parent_agent_id=agent.agent_id,
        # Reset performance metrics
        total_trades=0,
        total_pnl_usd=0.0,
        sharpe_ratio=0.0,
        win_rate=0.0,
    )


def clone_successful_agent(agent: Agent) -> Agent:
    """
    Clone a successful agent with small mutations.

    Called when agent achieves high fitness over sustained period.
    """
    if agent.sharpe_ratio < 1.0 or agent.total_trades < 50:
        raise ValueError("Agent not successful enough to clone")

    return mutate_agent_traits(agent, mutation_strength=0.05)  # Smaller mutations
```

### Agent Selection

```python
def select_agents_for_roster(
    agents: list[Agent],
    regime: str,
    roster_size: int = 10,
    diversity_weight: float = 0.15
) -> list[Agent]:
    """
    Select diverse, high-performing agents for active roster.

    Balances:
    - Performance in current regime
    - Trait diversity (avoid groupthink)
    - Recent performance trend

    Paper Reference: MASA - multi-agent roster selection
    """
    scored = []

    for agent in agents:
        # Regime affinity score
        regime_score = agent.regime_affinity.get(regime, 0.5)

        # Recent performance score
        perf_score = min(1.0, agent.sharpe_ratio / 2.0) if agent.sharpe_ratio > 0 else 0.0

        # Combined base score
        base_score = 0.6 * regime_score + 0.4 * perf_score

        scored.append((agent, base_score))

    # Sort by base score
    scored.sort(key=lambda x: -x[1])

    # Select with diversity bonus
    selected = []
    for agent, score in scored:
        if len(selected) >= roster_size:
            break

        # Calculate diversity bonus
        if selected:
            avg_distance = calculate_trait_distance(agent, selected)
            diversity_bonus = avg_distance * diversity_weight
            adjusted_score = score + diversity_bonus
        else:
            adjusted_score = score

        # Add to roster
        selected.append(agent)

    return selected


def calculate_trait_distance(agent: Agent, roster: list[Agent]) -> float:
    """
    Calculate how different an agent is from current roster.

    Higher = more diverse = good for avoiding groupthink.
    """
    if not roster:
        return 1.0

    distances = []
    for other in roster:
        trait_diffs = [
            abs(agent.traits[t] - other.traits[t])
            for t in agent.traits.keys()
        ]
        distances.append(np.mean(trait_diffs))

    return np.mean(distances)
```

---

## Affinity Evolution

Regime affinity evolves based on performance:

```python
def update_regime_affinity_ema(
    agent: Agent,
    regime: str,
    trade_pnl_pct: float,
    alpha: float = 0.1
) -> None:
    """
    Update regime affinity using exponential moving average.

    Good performance in a regime increases affinity.
    Bad performance decreases it.

    This creates specialization over time.
    """
    current = agent.regime_affinity.get(regime, 0.5)

    # Convert PnL to affinity update signal
    # Positive PnL -> increase affinity
    # Negative PnL -> decrease affinity
    signal = np.tanh(trade_pnl_pct * 10)  # Normalize to [-1, 1]

    # EMA update
    delta = alpha * (signal - (current - 0.5) * 2)

    new_affinity = current + delta
    new_affinity = max(0.0, min(1.0, new_affinity))

    agent.regime_affinity[regime] = new_affinity
```

---

## Evolution Cycle

```
┌──────────────────────────────────────────────────────────────────┐
│                    GENERATION N                                  │
│                                                                  │
│  Population: 100 patterns, 50 agents                             │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                    EVALUATION                                    │
│                                                                  │
│  Run backtests on all patterns                                   │
│  Calculate fitness scores                                        │
│  Track agent performance                                         │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                    SELECTION                                     │
│                                                                  │
│  Patterns:                    Agents:                            │
│  - Top 10% elite             - Top 20% clone                     │
│  - Next 20% reproduce        - Middle 60% survive                │
│  - Middle 50% survive        - Bottom 20% retire                 │
│  - Bottom 30% die            - Add new random agents             │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                    REPRODUCTION                                  │
│                                                                  │
│  Patterns:                    Agents:                            │
│  - Clone with mutation       - Clone with trait mutation         │
│  - Crossover pairs           - (No crossover for agents)         │
│  - Generate random           - Generate random                   │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                    GENERATION N+1                                │
│                                                                  │
│  New population ready for evaluation                             │
└──────────────────────────────────────────────────────────────────┘
```

---

## Implementation Code

See [../code/affinity_mutation.py](../code/affinity_mutation.py) for production implementation.

---

## Related Files

- [../architecture/5-layer-hierarchy.md](../architecture/5-layer-hierarchy.md) - Patterns and agents in hierarchy
- [../papers/arxiv-2510.07943-cga-agent.md](../papers/arxiv-2510.07943-cga-agent.md) - CGA-Agent paper
- [../meta/traits.md](../meta/traits.md) - 16 agent traits

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-28 | Initial concept document |
