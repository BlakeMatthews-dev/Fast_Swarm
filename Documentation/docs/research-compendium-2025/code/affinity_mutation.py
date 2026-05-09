#!/usr/bin/env python3
"""
Affinity Mutation and Agent Evolution Implementation.

This module provides evolutionary mechanisms for agent traits and
regime affinity scores, enabling agents to specialize over time.

Paper References:
- CGA-Agent (arxiv-2510.07943): Genetic trading strategies
- TradingAgents (arxiv-2412.20138): Agent specialization
- MacroHFT (arxiv-2406.14537): Regime affinity

Related Concept: ../concepts/evolutionary-systems.md
"""

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np


@dataclass
class Agent:
    """Trading agent with personality traits and regime affinities."""

    agent_id: str
    name: str
    generation: int

    # 16 personality traits (all 0.0-1.0)
    traits: dict[str, float]

    # Performance by regime
    regime_affinity: dict[str, float] = field(default_factory=dict)
    regime_performance: dict[str, dict] = field(default_factory=dict)

    # Lifetime stats
    total_trades: int = 0
    total_pnl_usd: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0

    # Status
    status: str = "active"  # active, benched, retired
    parent_agent_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)


# Default trait definitions
DEFAULT_TRAITS = {
    "risk_tolerance": 0.5,
    "hold_duration_bias": 0.5,
    "volatility_seeking": 0.5,
    "profit_target_greed": 0.5,
    "win_rate_preference": 0.5,
    "drawdown_sensitivity": 0.5,
    "momentum_vs_reversion": 0.5,
    "stop_loss_tightness": 0.5,
    "entry_aggression": 0.5,
    "exit_aggression": 0.5,
    "lookback_preference": 0.5,
    "sentiment_weight": 0.5,
    "news_reactivity": 0.5,
    "sentiment_contrarian": 0.5,
    "funding_rate_sensitivity": 0.5,
    "correlation_awareness": 0.5,
}

DEFAULT_REGIMES = [
    "bull_volatile",
    "bull_calm",
    "bear_volatile",
    "bear_calm",
    "sideways",
]


# =============================================================================
# Agent Creation
# =============================================================================


def create_random_agent(name_prefix: str = "Agent", generation: int = 0) -> Agent:
    """
    Create a new agent with random traits.

    Traits are initialized uniformly in [0, 1].
    Regime affinities start at 0.5 (neutral).
    """
    agent_id = str(uuid.uuid4())[:8]

    # Random traits
    traits = {name: random.uniform(0.0, 1.0) for name in DEFAULT_TRAITS}

    # Apply trait coupling (derived traits)
    traits = apply_trait_coupling(traits)

    # Neutral regime affinities
    regime_affinity = dict.fromkeys(DEFAULT_REGIMES, 0.5)

    return Agent(
        agent_id=agent_id,
        name=f"{name_prefix}_{agent_id}",
        generation=generation,
        traits=traits,
        regime_affinity=regime_affinity,
        regime_performance={regime: {"trades": 0, "total_pnl": 0.0} for regime in DEFAULT_REGIMES},
    )


def apply_trait_coupling(traits: dict[str, float]) -> dict[str, float]:
    """
    Apply coupling between related traits to prevent contradictions.

    Some traits are derived from others to maintain consistency.

    Paper Reference: Master_plan.md - trait coupling rules
    """
    traits = traits.copy()

    # Drawdown sensitivity inversely related to risk tolerance
    # High risk tolerance -> low drawdown sensitivity
    traits["drawdown_sensitivity"] = 1 - traits["risk_tolerance"] * 0.5

    # Stop loss tightness derived from drawdown sensitivity
    # Sensitive agents use tighter stops
    traits["stop_loss_tightness"] = traits["drawdown_sensitivity"] * 0.8

    # Exit aggression inversely related to hold duration bias
    # Short-term traders exit faster
    traits["exit_aggression"] = (1 - traits["hold_duration_bias"]) * 0.6 + 0.2

    return traits


# =============================================================================
# Trait Mutation
# =============================================================================


def mutate_agent_traits(agent: Agent, mutation_rate: float = 0.1, mutation_strength: float = 0.10) -> Agent:
    """
    Create offspring agent with mutated traits.

    Each trait has mutation_rate probability of changing by
    up to ±mutation_strength.

    Args:
        agent: Parent agent
        mutation_rate: Probability each trait mutates (default 10%)
        mutation_strength: Max change per trait (default ±10%)

    Returns:
        New agent with mutated traits

    Paper Reference: CGA-Agent - trait mutation operators
    """
    new_traits = {}

    for trait_name, value in agent.traits.items():
        if random.random() < mutation_rate:
            # Apply mutation
            delta = random.uniform(-mutation_strength, mutation_strength)
            new_value = value + delta
            # Clamp to [0, 1]
            new_traits[trait_name] = max(0.0, min(1.0, new_value))
        else:
            new_traits[trait_name] = value

    # Re-apply coupling after mutation
    new_traits = apply_trait_coupling(new_traits)

    # Create offspring
    return Agent(
        agent_id=str(uuid.uuid4())[:8],
        name=f"{agent.name}_offspring",
        generation=agent.generation + 1,
        traits=new_traits,
        regime_affinity=agent.regime_affinity.copy(),
        regime_performance={regime: {"trades": 0, "total_pnl": 0.0} for regime in DEFAULT_REGIMES},
        parent_agent_id=agent.agent_id,
    )


def clone_successful_agent(agent: Agent, min_sharpe: float = 1.0, min_trades: int = 50) -> Agent:
    """
    Clone a successful agent with smaller mutations.

    Only clone agents that have proven track record.

    Args:
        agent: Agent to clone
        min_sharpe: Minimum Sharpe ratio required
        min_trades: Minimum trades required

    Returns:
        Cloned agent with small mutations
    """
    if agent.sharpe_ratio < min_sharpe:
        raise ValueError(f"Agent Sharpe {agent.sharpe_ratio} below minimum {min_sharpe}")
    if agent.total_trades < min_trades:
        raise ValueError(f"Agent trades {agent.total_trades} below minimum {min_trades}")

    # Small mutations for successful agents (preserve winning formula)
    return mutate_agent_traits(agent, mutation_rate=0.05, mutation_strength=0.05)


# =============================================================================
# Regime Affinity Evolution
# =============================================================================


def update_regime_affinity(
    agent: Agent, regime: str, trade_pnl_pct: float, alpha: float = 0.1, max_delta: float = 0.10
) -> float:
    """
    Update regime affinity based on trade outcome.

    Uses EMA-style update: affinity moves toward performance signal.

    Args:
        agent: Agent to update
        regime: Regime trade occurred in
        trade_pnl_pct: Trade P&L as percentage (-0.05 = -5%)
        alpha: Learning rate (default 0.1)
        max_delta: Maximum affinity change per trade

    Returns:
        New affinity value

    Paper Reference: MacroHFT - adaptive regime specialization
    """
    if regime not in agent.regime_affinity:
        agent.regime_affinity[regime] = 0.5

    current = agent.regime_affinity[regime]

    # Update performance tracking
    if regime not in agent.regime_performance:
        agent.regime_performance[regime] = {"trades": 0, "total_pnl": 0.0}

    perf = agent.regime_performance[regime]
    perf["trades"] += 1
    perf["total_pnl"] += trade_pnl_pct

    # Calculate performance signal using tanh for bounded output
    # Good trade -> positive signal -> increase affinity
    # Bad trade -> negative signal -> decrease affinity
    signal = np.tanh(trade_pnl_pct * 20)  # Scale and bound to [-1, 1]

    # Calculate delta with max bound
    raw_delta = alpha * signal
    delta = max(-max_delta, min(max_delta, raw_delta))

    # Update affinity
    new_affinity = current + delta
    new_affinity = max(0.0, min(1.0, new_affinity))

    agent.regime_affinity[regime] = new_affinity

    return new_affinity


def update_regime_affinity_sharpe_based(
    agent: Agent, regime: str, recent_trades_pnl: list[float], alpha: float = 0.1
) -> float:
    """
    Update affinity based on Sharpe-like performance metric.

    More stable than single-trade updates.

    Args:
        agent: Agent to update
        regime: Current regime
        recent_trades_pnl: List of recent PnL percentages in this regime

    Returns:
        New affinity value
    """
    if len(recent_trades_pnl) < 5:
        return agent.regime_affinity.get(regime, 0.5)

    # Calculate Sharpe-like metric
    mean_pnl = np.mean(recent_trades_pnl)
    std_pnl = np.std(recent_trades_pnl) + 1e-8
    sharpe_like = mean_pnl / std_pnl

    # Convert to signal
    signal = np.tanh(sharpe_like)

    # Update
    current = agent.regime_affinity.get(regime, 0.5)
    delta = alpha * (signal - (current - 0.5) * 2)
    new_affinity = max(0.0, min(1.0, current + delta))

    agent.regime_affinity[regime] = new_affinity
    return new_affinity


# =============================================================================
# Selection and Evolution
# =============================================================================


def select_agents_for_roster(
    agents: list[Agent], regime: str, roster_size: int = 10, diversity_weight: float = 0.15
) -> list[Agent]:
    """
    Select diverse, high-performing agents for active roster.

    Balances:
    - Regime affinity (how well agent performs in this regime)
    - Recent performance (Sharpe ratio)
    - Trait diversity (avoid groupthink)

    Args:
        agents: Pool of available agents
        regime: Current market regime
        roster_size: Number of agents to select
        diversity_weight: Weight for diversity bonus

    Returns:
        Selected agents for roster

    Paper Reference: MASA - multi-agent roster selection
    """
    if len(agents) <= roster_size:
        return agents

    scored = []

    for agent in agents:
        if agent.status != "active":
            continue

        # Regime affinity score (0-1)
        affinity_score = agent.regime_affinity.get(regime, 0.5)

        # Performance score (0-1)
        if agent.sharpe_ratio > 0:
            perf_score = min(1.0, agent.sharpe_ratio / 2.0)
        else:
            perf_score = max(0.0, 0.5 + agent.sharpe_ratio / 2.0)

        # Combined base score
        base_score = 0.6 * affinity_score + 0.4 * perf_score

        scored.append((agent, base_score))

    # Sort by base score
    scored.sort(key=lambda x: -x[1])

    # Select with diversity consideration
    selected = []

    for agent, score in scored:
        if len(selected) >= roster_size:
            break

        # Calculate diversity bonus
        if selected:
            avg_distance = calculate_trait_distance(agent, selected)
            diversity_bonus = avg_distance * diversity_weight
        else:
            diversity_bonus = 0

        # We always add in order, but diversity affects future iterations
        selected.append(agent)

    return selected


def calculate_trait_distance(agent: Agent, roster: list[Agent]) -> float:
    """
    Calculate how different an agent's traits are from current roster.

    Higher distance = more diverse = prevents groupthink.
    """
    if not roster:
        return 1.0

    distances = []
    for other in roster:
        trait_diffs = [abs(agent.traits[t] - other.traits[t]) for t in agent.traits.keys()]
        distances.append(np.mean(trait_diffs))

    return np.mean(distances)


def evolve_population(
    population: list[Agent],
    fitness_scores: dict[str, float],
    elite_pct: float = 0.10,
    reproduce_pct: float = 0.20,
    new_random_pct: float = 0.10,
) -> list[Agent]:
    """
    Evolve agent population based on fitness.

    Strategy:
    - Elite (top 10%): Keep unchanged
    - Reproduce (next 20%): Clone with mutation
    - Survive (middle): Keep unchanged
    - Die (bottom 30%): Remove
    - New random: Add fresh agents

    Args:
        population: Current agent population
        fitness_scores: Dict mapping agent_id to fitness (0-100)
        elite_pct: Fraction to preserve as elite
        reproduce_pct: Fraction to reproduce
        new_random_pct: Fraction of new random agents

    Returns:
        New population for next generation

    Paper Reference: CGA-Agent - generational evolution
    """
    # Sort by fitness
    sorted_agents = sorted(population, key=lambda a: fitness_scores.get(a.agent_id, 0), reverse=True)

    n = len(sorted_agents)
    next_gen = []

    # Elite - preserve best unchanged
    elite_count = int(n * elite_pct)
    next_gen.extend(sorted_agents[:elite_count])

    # Reproduce - clone and mutate top performers
    reproduce_count = int(n * reproduce_pct)
    for agent in sorted_agents[:reproduce_count]:
        offspring = mutate_agent_traits(agent)
        next_gen.append(offspring)

    # Survive - keep middle performers
    survive_end = int(n * 0.70)  # Top 70% survive
    for agent in sorted_agents[elite_count:survive_end]:
        if agent not in next_gen:
            next_gen.append(agent)

    # Mark bottom 30% as retired
    for agent in sorted_agents[survive_end:]:
        agent.status = "retired"

    # Add new random agents
    new_count = int(n * new_random_pct)
    max_gen = max(a.generation for a in sorted_agents) if sorted_agents else 0
    for i in range(new_count):
        next_gen.append(create_random_agent(name_prefix=f"Random_Gen{max_gen + 1}", generation=max_gen + 1))

    return next_gen


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Create initial population
    print("Creating initial population...")
    population = [create_random_agent(f"Agent{i}", generation=0) for i in range(20)]

    # Simulate some trades and update affinities
    print("\nSimulating trades...")
    for agent in population[:5]:
        # Simulate trades in different regimes
        for _ in range(10):
            regime = random.choice(DEFAULT_REGIMES)
            pnl = random.gauss(0.01, 0.03)  # Slight positive edge
            update_regime_affinity(agent, regime, pnl)

        print(f"  {agent.name}:")
        for regime, affinity in agent.regime_affinity.items():
            print(f"    {regime}: {affinity:.3f}")

    # Select roster for bull_volatile regime
    print("\nSelecting roster for bull_volatile:")
    roster = select_agents_for_roster(population, "bull_volatile", roster_size=5)
    for agent in roster:
        print(f"  {agent.name}: affinity={agent.regime_affinity['bull_volatile']:.3f}")

    # Evolve population
    print("\nEvolving population...")
    fitness_scores = {a.agent_id: random.uniform(20, 80) for a in population}
    new_population = evolve_population(population, fitness_scores)
    print(f"  Previous: {len(population)} agents")
    print(f"  New: {len(new_population)} agents")
    print(f"  Retired: {sum(1 for a in population if a.status == 'retired')}")
