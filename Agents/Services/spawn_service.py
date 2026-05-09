"""
Spawn Service for Fast_Swarm.

Handles agent spawning: genesis, crossover, cloning, and philosophy generation.
All spawned agents have 22 traits, unique IDs, and proper naming.
"""

import random
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


def _convert_decimals(obj: Any) -> Any:
    """Recursively convert Decimal objects to floats for JSON serialization."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_decimals(item) for item in obj]
    return obj


from .trait_service import (
    crossover_and_mutate,
    generate_all_traits,
    mutate_traits,
    validate_all_traits,
)

# =============================================================================
# Constants
# =============================================================================

MAX_SPAWN_COUNT = 1000  # Safety limit
DEFAULT_MAX_PATTERNS = 10
DEFAULT_MIN_PATTERNS = 1

# Trait descriptors for naming
TRAIT_DESCRIPTORS = {
    "risk_tolerance": {"high": "Bold", "low": "Cautious"},
    "volatility_seeking": {"high": "Volatile", "low": "Stable"},
    "momentum_vs_reversion": {"high": "Momentum", "low": "Reversion"},
    "hold_duration_bias": {"high": "Patient", "low": "Quick"},
    "profit_target_greed": {"high": "Greedy", "low": "Conservative"},
    "win_rate_preference": {"high": "WinSeeker", "low": "RiskTaker"},
    "entry_aggression": {"high": "Aggressive", "low": "Measured"},
    "sentiment_weight": {"high": "Sentiment", "low": "Technical"},
}

# Agent name suffixes for uniqueness
NAME_POOL = [
    "Alpha",
    "Beta",
    "Gamma",
    "Delta",
    "Epsilon",
    "Zeta",
    "Eta",
    "Theta",
    "Iota",
    "Kappa",
    "Lambda",
    "Mu",
    "Nu",
    "Xi",
    "Omicron",
    "Pi",
    "Rho",
    "Sigma",
    "Tau",
    "Upsilon",
    "Phi",
    "Chi",
    "Psi",
    "Omega",
    "Apex",
    "Nova",
    "Pulse",
    "Flux",
    "Vex",
    "Zenith",
    "Nexus",
    "Cipher",
]


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class SpawnConfig:
    """Configuration for agent spawning."""

    min_patterns: int = DEFAULT_MIN_PATTERNS
    max_patterns: int = DEFAULT_MAX_PATTERNS
    mutation_rate: float = 0.10
    seed: int | None = None


@dataclass
class SpawnedAgent:
    """Result of agent spawning."""

    agent_id: str
    name: str
    generation: int
    traits: dict[str, float]
    assigned_patterns: list[dict[str, Any]]  # Full pattern dicts with entry_conditions
    trading_philosophy: str
    parent_a_id: str | None = None
    parent_b_id: str | None = None


# =============================================================================
# ID Generation
# =============================================================================


def generate_agent_id() -> str:
    """Generate a unique agent ID."""
    return f"agent-{uuid.uuid4().hex[:12]}"


# =============================================================================
# Naming
# =============================================================================


def get_dominant_traits(traits: dict[str, float], top_n: int = 2) -> list[tuple[str, str]]:
    """Get the most extreme traits and their descriptors."""
    extremes = []
    for trait_name in TRAIT_DESCRIPTORS:
        if trait_name in traits:
            value = traits[trait_name]
            extremity = abs(value - 0.5)
            is_high = value > 0.5
            descriptor = TRAIT_DESCRIPTORS[trait_name]["high" if is_high else "low"]
            extremes.append((extremity, trait_name, descriptor))
    extremes.sort(reverse=True)
    return [(name, desc) for _, name, desc in extremes[:top_n]]


def generate_agent_name(traits: dict[str, float], generation: int, seed: int | None = None) -> str:
    """Generate agent name. Format: {Trait1}_{Trait2}_{Name}_G{generation}"""
    if seed is not None:
        random.seed(seed)
    dominant = get_dominant_traits(traits, top_n=2)
    if len(dominant) >= 2:
        trait1_desc, trait2_desc = dominant[0][1], dominant[1][1]
    elif len(dominant) == 1:
        trait1_desc, trait2_desc = dominant[0][1], "Balanced"
    else:
        trait1_desc, trait2_desc = "Neutral", "Balanced"
    name = random.choice(NAME_POOL)
    return f"{trait1_desc}_{trait2_desc}_{name}_G{generation}"


# =============================================================================
# Philosophy Generation
# =============================================================================


def generate_trading_philosophy(traits: dict[str, float]) -> str:
    """Generate trading philosophy text based on traits."""
    parts = []
    risk = traits.get("risk_tolerance", 0.5)
    if risk > 0.7:
        parts.append("I embrace risk and seek high-reward opportunities.")
    elif risk < 0.3:
        parts.append("I prioritize capital preservation over aggressive gains.")
    else:
        parts.append("I balance risk and reward in my trading approach.")

    mom = traits.get("momentum_vs_reversion", 0.5)
    if mom > 0.7:
        parts.append("I follow trends and ride momentum.")
    elif mom < 0.3:
        parts.append("I look for mean reversion and fade extremes.")
    else:
        parts.append("I adapt between momentum and reversion strategies.")

    hold = traits.get("hold_duration_bias", 0.5)
    if hold > 0.7:
        parts.append("I hold positions patiently for larger moves.")
    elif hold < 0.3:
        parts.append("I prefer quick trades and rapid position turnover.")
    else:
        parts.append("I adjust hold times based on market conditions.")

    sent = traits.get("sentiment_weight", 0.5)
    if sent > 0.7:
        parts.append("Market sentiment heavily influences my decisions.")
    elif sent < 0.3:
        parts.append("I rely primarily on technical signals.")
    else:
        parts.append("I blend technical and sentiment analysis.")
    return " ".join(parts)


# =============================================================================
# Pattern Assignment
# =============================================================================


def select_patterns_for_agent(
    traits: dict[str, float],
    available_patterns: list[dict[str, Any]],
    min_patterns: int = DEFAULT_MIN_PATTERNS,
    max_patterns: int = DEFAULT_MAX_PATTERNS,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """
    Select patterns for an agent based on traits (heuristic matching).

    Returns FULL pattern dicts (with entry_conditions/exit_conditions),
    not just pattern IDs. This is critical for backtesting.
    """
    if seed is not None:
        random.seed(seed)
    if not available_patterns:
        return []

    # Score patterns by trait affinity, keeping full pattern dict
    scored = [(calculate_pattern_affinity(traits, p), p) for p in available_patterns]
    scored.sort(reverse=True, key=lambda x: x[0])

    count = random.randint(min_patterns, min(max_patterns, len(scored)))
    candidates = scored[: max(count * 2, 5)]
    random.shuffle(candidates)

    # Return full pattern dicts (with entry_conditions, exit_conditions, etc.)
    selected = [pattern for _, pattern in candidates[:count]]
    if not selected and scored:
        selected = [scored[0][1]]
    return selected


def calculate_pattern_affinity(traits: dict[str, float], pattern: dict[str, Any]) -> float:
    """Calculate affinity score between agent traits and pattern."""
    score = 1.0
    mom = traits.get("momentum_vs_reversion", 0.5)
    pt = pattern.get("type", "").lower()
    if "momentum" in pt or "trend" in pt:
        score *= 0.5 + mom
    elif "reversion" in pt or "mean" in pt:
        score *= 1.5 - mom
    risk = traits.get("risk_tolerance", 0.5)
    score *= 1.0 - abs(risk - pattern.get("volatility", 0.5))
    if traits.get("win_rate_preference", 0.5) > 0.6 and pattern.get("win_rate", 0.5) > 0.55:
        score *= 1.2
    return score


def initialize_pattern_weights(pattern_ids: list[str]) -> dict[str, float]:
    """Initialize pattern weights (all start at 1.0)."""
    return dict.fromkeys(pattern_ids, 1.0)


# =============================================================================
# Spawn Functions (Non-DB)
# =============================================================================


def spawn_agent(
    generation: int = 1,
    seed: int | None = None,
    available_patterns: list[dict] | None = None,
    config: SpawnConfig | None = None,
) -> SpawnedAgent:
    """Spawn a single new agent (genesis)."""
    if config is None:
        config = SpawnConfig(seed=seed)
    if seed is not None:
        random.seed(seed)
    agent_id = generate_agent_id()
    traits = generate_all_traits(seed=seed)
    name = generate_agent_name(traits, generation, seed=seed)
    patterns = []
    if available_patterns:
        patterns = select_patterns_for_agent(
            traits,
            available_patterns,
            min_patterns=config.min_patterns,
            max_patterns=config.max_patterns,
            seed=seed,
        )
    philosophy = generate_trading_philosophy(traits)
    return SpawnedAgent(
        agent_id=agent_id,
        name=name,
        generation=generation,
        traits=traits,
        assigned_patterns=patterns,
        trading_philosophy=philosophy,
    )


def spawn_agents(
    count: int,
    generation: int = 1,
    seed: int | None = None,
    available_patterns: list[dict] | None = None,
    config: SpawnConfig | None = None,
) -> list[SpawnedAgent]:
    """Spawn multiple agents."""
    if count <= 0:
        raise ValueError(f"Count must be positive, got {count}")
    if count > MAX_SPAWN_COUNT:
        raise ValueError(f"Count exceeds maximum ({MAX_SPAWN_COUNT}), got {count}")
    agents = []
    for i in range(count):
        agent_seed = (seed + i) if seed is not None else None
        agent = spawn_agent(
            generation=generation, seed=agent_seed, available_patterns=available_patterns, config=config
        )
        agents.append(agent)
    return agents


def spawn_child(
    parent_a: dict[str, Any],
    parent_b: dict[str, Any],
    mutation_rate: float = 0.10,
    seed: int | None = None,
    available_patterns: list[dict] | None = None,
) -> SpawnedAgent:
    """Spawn a child agent from two parents via crossover."""
    if seed is not None:
        random.seed(seed)
    traits_a = parent_a.get("traits", {})
    traits_b = parent_b.get("traits", {})
    child_traits = crossover_and_mutate(traits_a, traits_b, mutation_rate, seed)
    gen_a = parent_a.get("generation", 1)
    gen_b = parent_b.get("generation", 1)
    child_generation = max(gen_a, gen_b) + 1
    agent_id = generate_agent_id()
    name = generate_agent_name(child_traits, child_generation, seed)

    # Merge parent patterns by pattern_id (avoiding duplicates)
    # Patterns are now full dicts, so we can't use set()
    patterns_by_id = {}
    for p in parent_a.get("assigned_patterns", []):
        if isinstance(p, dict):
            pid = p.get("pattern_id", p.get("id", ""))
            if pid:
                patterns_by_id[pid] = p
        elif isinstance(p, str):
            # Legacy: if just ID, wrap in minimal dict
            patterns_by_id[p] = {"pattern_id": p}
    for p in parent_b.get("assigned_patterns", []):
        if isinstance(p, dict):
            pid = p.get("pattern_id", p.get("id", ""))
            if pid and pid not in patterns_by_id:
                patterns_by_id[pid] = p
        elif isinstance(p, str):
            if p not in patterns_by_id:
                patterns_by_id[p] = {"pattern_id": p}

    patterns = list(patterns_by_id.values())
    philosophy = generate_trading_philosophy(child_traits)
    return SpawnedAgent(
        agent_id=agent_id,
        name=name,
        generation=child_generation,
        traits=child_traits,
        assigned_patterns=patterns,
        trading_philosophy=philosophy,
        parent_a_id=parent_a.get("agent_id"),
        parent_b_id=parent_b.get("agent_id"),
    )


def spawn_clone(parent: dict[str, Any], mutation_rate: float = 0.10, seed: int | None = None) -> SpawnedAgent:
    """Spawn a clone from a single parent with mutation."""
    if seed is not None:
        random.seed(seed)
    parent_traits = parent.get("traits", {})
    clone_traits = mutate_traits(parent_traits, mutation_rate, seed)
    clone_generation = parent.get("generation", 1) + 1
    agent_id = generate_agent_id()
    name = generate_agent_name(clone_traits, clone_generation, seed)

    # Copy parent patterns (handle both old/new formats)
    parent_patterns = parent.get("assigned_patterns", [])
    patterns = []
    for p in parent_patterns:
        if isinstance(p, dict):
            # Full pattern dict - copy it
            patterns.append(p.copy())
        elif isinstance(p, str):
            # Legacy: just ID - wrap in minimal dict
            patterns.append({"pattern_id": p})

    philosophy = generate_trading_philosophy(clone_traits)
    return SpawnedAgent(
        agent_id=agent_id,
        name=name,
        generation=clone_generation,
        traits=clone_traits,
        assigned_patterns=patterns,
        trading_philosophy=philosophy,
        parent_a_id=parent.get("agent_id"),
        parent_b_id=None,
    )


# =============================================================================
# Validation
# =============================================================================


def validate_spawn_count(count: int) -> tuple[bool, str]:
    """Validate spawn count."""
    if count <= 0:
        return False, f"Count must be positive, got {count}"
    if count > MAX_SPAWN_COUNT:
        return False, f"Count exceeds maximum ({MAX_SPAWN_COUNT}), got {count}"
    return True, ""


def validate_spawned_agent(agent: SpawnedAgent) -> tuple[bool, str]:
    """Validate a spawned agent has all required fields."""
    if not agent.agent_id:
        return False, "Agent ID is required"
    if not agent.name:
        return False, "Agent name is required"
    if agent.generation < 1:
        return False, "Generation must be >= 1"
    is_valid, error = validate_all_traits(agent.traits)
    if not is_valid:
        return False, f"Invalid traits: {error}"
    if not agent.trading_philosophy:
        return False, "Trading philosophy is required"
    return True, ""


# =============================================================================
# Regime-Priority Pattern Selection
# =============================================================================


async def get_regime_priority_patterns(
    session: AsyncSession,
    top_pct_per_category: float = 0.20,
    final_pool_size: int = 50,
) -> list[dict[str, Any]]:
    """
    Select patterns that excel in the WEAKEST regime categories.

    This addresses the problem where agents score 99+ on bull markets but 0 on
    crash/bear periods. By selecting patterns that perform well in weak categories,
    we spawn agents that are robust across all market conditions.

    Algorithm:
    1. Find 5 weakest categories (crash, bear, 1m, sideways, etc.)
    2. For each: get top 20% patterns by that category's fitness
    3. Combine into pool, shuffle, return top N

    Args:
        session: Database session
        top_pct_per_category: Top X% of patterns per weak category (default 0.20)
        final_pool_size: Maximum patterns in final pool (default 50)

    Returns:
        List of pattern dicts suitable for agent spawning
    """
    from sqlalchemy import text

    from Fast_Swarm.Patterns.Services.pattern_service import get_weakest_regime_categories

    # Step 1: Get weakest 5 categories
    worst_categories = await get_weakest_regime_categories(session, top_n_worst=5)

    if not worst_categories:
        print("[SpawnService] No weak regime categories found. Falling back to standard patterns.")
        return []

    # Step 2: For each category, get top performers
    combined_pool = {}  # pattern_id -> pattern dict (dedup)

    for category in worst_categories:
        # Query patterns sorted by fitness in THIS category
        result = await session.execute(
            text("""
            SELECT
                p.pattern_id,
                p.entry_conditions,
                p.exit_conditions,
                p.origin,
                p.fitness_score,
                p.win_rate,
                COALESCE(
                    (p.fitness_by_regime->:category->>'fitness')::float,
                    CASE
                        WHEN jsonb_typeof(p.fitness_by_regime->:category) = 'number'
                        THEN (p.fitness_by_regime->:category)::text::float
                        ELSE NULL
                    END
                ) as category_fitness
            FROM patterns p
            WHERE p.is_active = true
              AND p.fitness_by_regime IS NOT NULL
              AND p.fitness_by_regime->:category IS NOT NULL
            ORDER BY category_fitness DESC NULLS LAST
            LIMIT :limit
        """),
            {"category": category, "limit": 30},
        )

        rows = result.fetchall()

        # Take top 20% of patterns for this category
        top_count = max(1, int(len(rows) * top_pct_per_category))

        for row in rows[:top_count]:
            pid = row[0]
            if pid not in combined_pool:
                combined_pool[pid] = {
                    "pattern_id": pid,
                    "entry_conditions": row[1],
                    "exit_conditions": row[2],
                    "type": row[3] or "unknown",
                    "fitness_score": float(row[4] or 0),
                    "win_rate": float(row[5] or 0.5),
                    "volatility": 0.5,
                    "best_category": category,
                    "category_fitness": float(row[6] or 0),
                }

    # Step 3: Shuffle and return top N
    pool_list = list(combined_pool.values())
    random.shuffle(pool_list)

    print(f"[SpawnService] Regime-priority pool: {len(pool_list)} patterns from weak categories {worst_categories}")

    return pool_list[:final_pool_size]


# =============================================================================
# Database Operations (Async)
# =============================================================================


async def spawn_and_persist(
    session: AsyncSession,
    count: int = 1,
    generation: int = 1,
    seed: int | None = None,
    available_patterns: list[dict] | None = None,
    config: SpawnConfig | None = None,
) -> list[str]:
    """Spawn agents and persist to database."""
    from Fast_Swarm.Agents.Models.agent_models import Agent

    is_valid, error = validate_spawn_count(count)
    if not is_valid:
        raise ValueError(error)
    spawned = spawn_agents(count, generation, seed, available_patterns, config)
    agent_ids = []
    for spawned_agent in spawned:
        # Convert Decimals to floats for JSON serialization (patterns from PostgreSQL)
        clean_patterns = _convert_decimals(spawned_agent.assigned_patterns)
        clean_traits = _convert_decimals(spawned_agent.traits)

        agent = Agent(
            agent_id=spawned_agent.agent_id,
            name=spawned_agent.name,
            generation=spawned_agent.generation,
            traits=clean_traits,
            assigned_patterns={"base": clean_patterns},
            trading_philosophy=spawned_agent.trading_philosophy,
            parent_a_id=spawned_agent.parent_a_id,
            parent_b_id=spawned_agent.parent_b_id,
            status="active",
            is_active=True,
            fitness_score=0.0,
            elo_rating=1500.0,
        )
        session.add(agent)
        agent_ids.append(spawned_agent.agent_id)
    await session.flush()
    return agent_ids


def _extract_pattern_ids(assigned_patterns: dict | None) -> list[str]:
    """Extract pattern IDs from assigned_patterns (handles both old and new formats)."""
    patterns = _extract_full_patterns(assigned_patterns)
    return [p.get("pattern_id", p.get("id", "")) for p in patterns if isinstance(p, dict)]


def _extract_full_patterns(assigned_patterns: dict | None) -> list[dict]:
    """
    Extract FULL pattern dicts from assigned_patterns.

    Returns list of pattern dicts with entry_conditions, exit_conditions, etc.
    Handles both old format (just IDs) and new format (full dicts).
    """
    if not assigned_patterns:
        return []

    # Handle dict format: {"base": [...], "situational": [...]}
    if isinstance(assigned_patterns, dict):
        base_patterns = assigned_patterns.get("base", [])
    elif isinstance(assigned_patterns, list):
        base_patterns = assigned_patterns
    else:
        return []

    patterns = []
    for p in base_patterns:
        if isinstance(p, dict):
            # New format: full pattern dict - include it
            patterns.append(p)
        elif isinstance(p, str):
            # Old format: just pattern ID - wrap in minimal dict
            patterns.append({"pattern_id": p})
    return patterns


async def spawn_child_and_persist(
    session: AsyncSession,
    parent_a_id: str,
    parent_b_id: str,
    mutation_rate: float = 0.10,
    seed: int | None = None,
) -> str:
    """Spawn child from two parents and persist."""
    from Fast_Swarm.Agents.Models.agent_models import Agent

    result_a = await session.execute(select(Agent).where(Agent.agent_id == parent_a_id))
    parent_a = result_a.scalars().first()
    result_b = await session.execute(select(Agent).where(Agent.agent_id == parent_b_id))
    parent_b = result_b.scalars().first()
    if not parent_a or not parent_b:
        raise ValueError("Both parents must exist")
    parent_a_dict = {
        "agent_id": parent_a.agent_id,
        "traits": parent_a.traits,
        "generation": parent_a.generation,
        "assigned_patterns": _extract_full_patterns(parent_a.assigned_patterns),
    }
    parent_b_dict = {
        "agent_id": parent_b.agent_id,
        "traits": parent_b.traits,
        "generation": parent_b.generation,
        "assigned_patterns": _extract_full_patterns(parent_b.assigned_patterns),
    }
    child = spawn_child(parent_a_dict, parent_b_dict, mutation_rate, seed)

    # Convert Decimals to floats for JSON serialization
    clean_patterns = _convert_decimals(child.assigned_patterns)
    clean_traits = _convert_decimals(child.traits)

    agent = Agent(
        agent_id=child.agent_id,
        name=child.name,
        generation=child.generation,
        traits=clean_traits,
        assigned_patterns={"base": clean_patterns},
        trading_philosophy=child.trading_philosophy,
        parent_a_id=child.parent_a_id,
        parent_b_id=child.parent_b_id,
        status="active",
        is_active=True,
        fitness_score=0.0,
        elo_rating=1500.0,
    )
    session.add(agent)
    await session.flush()
    return child.agent_id


# =============================================================================
# Class-Based API (Backward Compatibility)
# =============================================================================


class AgentSpawnService:
    """
    Class wrapper for spawn operations.
    Maintains backward compatibility with evolution_service.py.
    """

    def __init__(self):
        pass

    async def spawn_agents(
        self,
        session: AsyncSession,
        count: int = 1,
        generation: int = 1,
        seed: int | None = None,
        available_patterns: list[dict] | None = None,
    ) -> list[str]:
        """Spawn multiple agents and persist to database."""
        return await spawn_and_persist(
            session=session,
            count=count,
            generation=generation,
            seed=seed,
            available_patterns=available_patterns,
        )

    async def spawn_child(
        self,
        session: AsyncSession,
        parent_a_id: str,
        parent_b_id: str,
        mutation_rate: float = 0.10,
        seed: int | None = None,
    ) -> str:
        """Spawn child from two parents."""
        return await spawn_child_and_persist(
            session=session,
            parent_a_id=parent_a_id,
            parent_b_id=parent_b_id,
            mutation_rate=mutation_rate,
            seed=seed,
        )

    def generate_traits(self, seed: int | None = None) -> dict[str, float]:
        """Generate random traits for a new agent."""
        return generate_all_traits(seed=seed)

    def mutate_traits_for_clone(
        self,
        parent_traits: dict[str, float],
        mutation_rate: float = 0.10,
        seed: int | None = None,
    ) -> dict[str, float]:
        """Mutate traits for a clone."""
        return mutate_traits(parent_traits, mutation_rate, seed)

    def generate_philosophy(self, traits: dict[str, float]) -> str:
        """Generate trading philosophy from traits."""
        return generate_trading_philosophy(traits)

    def generate_name(
        self,
        traits: dict[str, float],
        generation: int,
        seed: int | None = None,
    ) -> str:
        """Generate agent name from traits."""
        return generate_agent_name(traits, generation, seed)

    async def spawn_new_agents(
        self,
        session: AsyncSession,
        count: int = 1,
        generation: int = 1,
        seed: int | None = None,
        available_patterns: list[dict] | None = None,
    ) -> list[str]:
        """
        Spawn fresh agents for population diversity.
        Alias for spawn_agents() for backward compatibility.
        """
        return await spawn_and_persist(
            session=session,
            count=count,
            generation=generation,
            seed=seed,
            available_patterns=available_patterns,
        )

    async def spawn_children(
        self,
        session: AsyncSession,
        parent_ids: list[str],
        mutation_rate: float = 0.10,
        seed: int | None = None,
    ) -> list[str]:
        """
        Spawn children from parent(s).

        If 1 parent: clone with mutation
        If 2 parents: crossover child
        """
        if len(parent_ids) == 1:
            # Clone
            return [await self.spawn_clone(session, parent_ids[0], mutation_rate, seed)]
        elif len(parent_ids) >= 2:
            # Crossover
            return [await spawn_child_and_persist(session, parent_ids[0], parent_ids[1], mutation_rate, seed)]
        return []

    async def spawn_clone(
        self,
        session: AsyncSession,
        parent_id: str,
        mutation_rate: float = 0.10,
        seed: int | None = None,
    ) -> str:
        """Spawn a clone from a single parent with mutation."""
        from Fast_Swarm.Agents.Models.agent_models import Agent

        result = await session.execute(select(Agent).where(Agent.agent_id == parent_id))
        parent = result.scalars().first()
        if not parent:
            raise ValueError(f"Parent {parent_id} not found")

        parent_dict = {
            "agent_id": parent.agent_id,
            "traits": parent.traits,
            "generation": parent.generation,
            "assigned_patterns": _extract_full_patterns(parent.assigned_patterns),
        }

        clone = spawn_clone(parent_dict, mutation_rate, seed)

        # Convert Decimals to floats for JSON serialization
        clean_patterns = _convert_decimals(clone.assigned_patterns)
        clean_traits = _convert_decimals(clone.traits)

        agent = Agent(
            agent_id=clone.agent_id,
            name=clone.name,
            generation=clone.generation,
            traits=clean_traits,
            assigned_patterns={"base": clean_patterns},
            trading_philosophy=clone.trading_philosophy,
            parent_a_id=clone.parent_a_id,
            parent_b_id=None,
            status="active",
            is_active=True,
            fitness_score=0.0,
            elo_rating=1500.0,
        )
        session.add(agent)
        await session.flush()
        return clone.agent_id
