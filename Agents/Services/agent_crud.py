"""
Agent CRUD Operations for Fast_Swarm.

Complete Create, Read, Update, Delete operations for agents.
Separated from agent_service.py for clarity.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..Models.agent_models import Agent
from .agent_service import calculate_derived_traits

# =============================================================================
# Constants
# =============================================================================

# The 22 required traits for a valid agent genome
REQUIRED_TRAITS = [
    # Core Risk (1-4)
    "risk_tolerance",
    "hold_duration_bias",
    "volatility_seeking",
    "profit_target_greed",
    # Pattern Selection (5-7)
    "win_rate_preference",
    "drawdown_sensitivity",
    "momentum_vs_reversion",
    # Trade Execution (8-10)
    "stop_loss_tightness",
    "entry_aggression",
    "exit_aggression",
    # Technical (11)
    "lookback_preference",
    # Sentiment (12-14)
    "sentiment_weight",
    "news_reactivity",
    "sentiment_contrarian",
    # Macro (15-16)
    "funding_rate_sensitivity",
    "correlation_awareness",
    # Additional (17-22)
    "patience",
    "adaptability",
    "trend_following",
    "mean_reversion",
    "breakout_preference",
    "volume_sensitivity",
]


# =============================================================================
# Helper Functions
# =============================================================================


def generate_agent_id() -> str:
    """Generate a unique agent ID."""
    return f"agent-{uuid.uuid4().hex[:12]}"


def generate_random_traits(seed: int | None = None) -> dict[str, float]:
    """
    Generate random trait values for a new agent.

    Args:
        seed: Optional random seed for deterministic generation

    Returns:
        Dictionary with all 22 traits, values in [0.0, 1.0]
    """
    import random

    if seed is not None:
        random.seed(seed)

    base_traits = {}
    for trait in REQUIRED_TRAITS:
        # Skip derived traits - they'll be calculated
        if trait not in ["drawdown_sensitivity", "stop_loss_tightness", "exit_aggression"]:
            base_traits[trait] = random.random()

    # Calculate derived traits
    return calculate_derived_traits(base_traits)


def validate_traits(traits: dict[str, Any]) -> tuple[bool, str]:
    """
    Validate that traits dict has all 22 required traits in valid range.

    Args:
        traits: Dictionary of trait values

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(traits, dict):
        return False, "Traits must be a dictionary"

    for trait_name in REQUIRED_TRAITS:
        if trait_name not in traits:
            return False, f"Missing required trait: {trait_name}"

        value = traits[trait_name]
        if not isinstance(value, (int, float)):
            return False, f"Trait {trait_name} must be numeric, got {type(value)}"

        if value < 0.0 or value > 1.0:
            return False, f"Trait {trait_name} must be in [0.0, 1.0], got {value}"

    return True, ""


# =============================================================================
# Create Operations
# =============================================================================


async def create_agent(
    session: AsyncSession,
    name: str,
    traits: dict[str, float] | None = None,
    agent_id: str | None = None,
    generation: int = 1,
    parent_a_id: str | None = None,
    parent_b_id: str | None = None,
    seed: int | None = None,
) -> Agent:
    """
    Create a new agent with validated traits.

    Args:
        session: Database session
        name: Agent name (required)
        traits: Optional traits dict (generated if not provided)
        agent_id: Optional custom ID (generated if not provided)
        generation: Generation number (default 1)
        parent_a_id: Optional parent A for breeding
        parent_b_id: Optional parent B for breeding
        seed: Optional seed for deterministic trait generation

    Returns:
        Created Agent instance

    Raises:
        ValueError: If traits are invalid or name missing
    """
    if not name:
        raise ValueError("Agent name is required")

    # Generate ID if not provided
    if agent_id is None:
        agent_id = generate_agent_id()

    # Generate or validate traits
    if traits is None:
        traits = generate_random_traits(seed)
    else:
        # Ensure all 22 traits are present
        is_valid, error = validate_traits(traits)
        if not is_valid:
            raise ValueError(error)

    agent = Agent(
        agent_id=agent_id,
        name=name,
        generation=generation,
        traits=traits,
        status="active",
        is_active=True,
        fitness_score=0.0,
        elo_rating=1500.0,
        parent_a_id=parent_a_id,
        parent_b_id=parent_b_id,
    )

    session.add(agent)
    await session.flush()
    await session.refresh(agent)
    return agent


async def bulk_create_agents(
    session: AsyncSession,
    agents_data: list[dict[str, Any]],
) -> list[str]:
    """
    Create multiple agents in a single transaction.

    Args:
        session: Database session
        agents_data: List of agent data dictionaries

    Returns:
        List of created agent IDs

    Raises:
        ValueError: If any agent data is invalid (atomic - all fail)
    """
    created_ids = []
    agents = []

    for data in agents_data:
        name = data.get("name")
        if not name:
            raise ValueError("Agent name is required")

        traits = data.get("traits")
        if traits:
            is_valid, error = validate_traits(traits)
            if not is_valid:
                raise ValueError(f"Invalid traits for agent '{name}': {error}")
        else:
            traits = generate_random_traits(data.get("seed"))

        agent_id = data.get("agent_id") or generate_agent_id()

        agent = Agent(
            agent_id=agent_id,
            name=name,
            generation=data.get("generation", 1),
            traits=traits,
            status="active",
            is_active=True,
            fitness_score=0.0,
            elo_rating=1500.0,
        )
        agents.append(agent)
        created_ids.append(agent_id)

    session.add_all(agents)
    await session.flush()

    return created_ids


# =============================================================================
# Read Operations
# =============================================================================


async def get_agent_by_id(
    session: AsyncSession,
    agent_id: str,
) -> Agent | None:
    """Fetch a specific agent by agent_id."""
    statement = select(Agent).where(Agent.agent_id == agent_id)
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def get_all_agents(
    session: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    include_inactive: bool = False,
) -> list[Agent]:
    """
    Fetch all agents with optional filtering.

    Args:
        session: Database session
        limit: Maximum results (default 50)
        offset: Pagination offset
        include_inactive: Whether to include inactive/culled agents

    Returns:
        List of Agent instances
    """
    statement = select(Agent)
    if not include_inactive:
        statement = statement.where(Agent.status == "active")
    statement = statement.offset(offset).limit(limit)

    result = await session.execute(statement)
    return list(result.scalars().all())


async def get_agents_by_status(
    session: AsyncSession,
    status: str,
    limit: int = 100,
    offset: int = 0,
) -> list[Agent]:
    """
    Get agents filtered by status.

    Args:
        session: Database session
        status: Status to filter by (active, retired, culled, dead)
        limit: Maximum results
        offset: Pagination offset

    Returns:
        List of matching agents
    """
    statement = select(Agent).where(Agent.status == status).offset(offset).limit(limit)
    result = await session.execute(statement)
    return list(result.scalars().all())


async def get_agents_by_generation(
    session: AsyncSession,
    generation: int,
    limit: int = 100,
) -> list[Agent]:
    """
    Get agents from a specific generation.

    Args:
        session: Database session
        generation: Generation number to filter
        limit: Maximum results

    Returns:
        List of agents from that generation
    """
    statement = select(Agent).where(Agent.generation == generation).where(Agent.status == "active").limit(limit)
    result = await session.execute(statement)
    return list(result.scalars().all())


async def get_agents_by_fitness(
    session: AsyncSession,
    min_fitness: float = 0.0,
    limit: int = 100,
    order_desc: bool = True,
) -> list[Agent]:
    """
    Fetch agents above a fitness threshold, ordered by fitness.

    Args:
        session: Database session
        min_fitness: Minimum fitness score
        limit: Maximum results
        order_desc: If True, highest fitness first

    Returns:
        List of Agent instances ordered by fitness
    """
    statement = select(Agent).where(Agent.status == "active").where(Agent.fitness_score >= min_fitness).limit(limit)
    if order_desc:
        statement = statement.order_by(Agent.fitness_score.desc())
    else:
        statement = statement.order_by(Agent.fitness_score.asc())

    result = await session.execute(statement)
    return list(result.scalars().all())


async def get_population_stats(session: AsyncSession) -> dict[str, Any]:
    """
    Get population statistics for all agents.

    Returns:
        Dictionary with stats:
        - total_count: Total agents
        - active_count: Active agents
        - avg_fitness: Average fitness (0 if empty)
        - max_generation: Highest generation number
        - fitness_distribution: Buckets of fitness scores
    """
    # Total count
    total_result = await session.execute(select(func.count(Agent.id)))
    total_count = total_result.scalar() or 0

    # Active count
    active_result = await session.execute(select(func.count(Agent.id)).where(Agent.status == "active"))
    active_count = active_result.scalar() or 0

    # Handle empty population
    if total_count == 0:
        return {
            "total_count": 0,
            "active_count": 0,
            "avg_fitness": 0.0,
            "max_generation": 0,
            "fitness_distribution": {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0},
        }

    # Average fitness
    avg_result = await session.execute(select(func.avg(Agent.fitness_score)))
    avg_fitness = avg_result.scalar() or 0.0

    # Max generation
    max_gen_result = await session.execute(select(func.max(Agent.generation)))
    max_generation = max_gen_result.scalar() or 0

    # Fitness distribution
    distribution = {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
    all_agents_result = await session.execute(select(Agent.fitness_score))
    for row in all_agents_result.scalars().all():
        fitness = row
        if fitness < 20:
            distribution["0-20"] += 1
        elif fitness < 40:
            distribution["20-40"] += 1
        elif fitness < 60:
            distribution["40-60"] += 1
        elif fitness < 80:
            distribution["60-80"] += 1
        else:
            distribution["80-100"] += 1

    return {
        "total_count": total_count,
        "active_count": active_count,
        "avg_fitness": float(avg_fitness),
        "max_generation": max_generation,
        "fitness_distribution": distribution,
    }


# =============================================================================
# Update Operations
# =============================================================================


async def update_agent(
    session: AsyncSession,
    agent_id: str,
    updates: dict[str, Any],
) -> Agent | None:
    """
    Partially update an agent's fields.

    Args:
        session: Database session
        agent_id: Agent to update
        updates: Dictionary of fields to update

    Returns:
        Updated Agent or None if not found

    Raises:
        ValueError: If trait values are invalid
    """
    agent = await get_agent_by_id(session, agent_id)
    if not agent:
        return None

    # Handle trait updates with validation
    if "traits" in updates:
        new_traits = {**agent.traits, **updates["traits"]}
        is_valid, error = validate_traits(new_traits)
        if not is_valid:
            raise ValueError(error)
        agent.traits = new_traits
        del updates["traits"]

    # Handle fitness with bounds
    if "fitness_score" in updates:
        agent.fitness_score = max(0.0, min(100.0, updates["fitness_score"]))
        del updates["fitness_score"]

    # Handle status changes
    if "status" in updates:
        new_status = updates["status"]
        if new_status in ("active", "retired", "culled", "dead"):
            agent.status = new_status
            agent.is_active = new_status == "active"
        del updates["status"]

    # Apply remaining safe updates
    safe_fields = {"name", "trading_philosophy", "assigned_patterns", "pattern_weights"}
    for field, value in updates.items():
        if field in safe_fields and hasattr(agent, field):
            setattr(agent, field, value)

    agent.updated_at = datetime.utcnow()

    await session.flush()
    await session.refresh(agent)
    return agent


async def update_agent_fitness(
    session: AsyncSession,
    agent_id: str,
    fitness_score: float,
    win_rate: float | None = None,
    total_trades: int | None = None,
    total_pnl: float | None = None,
) -> Agent | None:
    """
    Update agent fitness metrics after backtest.

    Args:
        session: Database session
        agent_id: Agent to update
        fitness_score: New fitness score
        win_rate: Optional win rate update
        total_trades: Optional trade count update
        total_pnl: Optional PnL update

    Returns:
        Updated Agent or None if not found
    """
    agent = await get_agent_by_id(session, agent_id)
    if not agent:
        return None

    agent.fitness_score = max(0.0, min(100.0, fitness_score))
    agent.last_backtest_at = datetime.utcnow()

    if win_rate is not None:
        agent.win_rate = max(0.0, min(1.0, win_rate))
    if total_trades is not None:
        agent.total_trades = max(0, total_trades)
    if total_pnl is not None:
        agent.total_pnl = total_pnl

    agent.backtest_count += 1
    agent.updated_at = datetime.utcnow()

    await session.flush()
    await session.refresh(agent)
    return agent


async def bulk_update_fitness(
    session: AsyncSession,
    updates: list[dict[str, Any]],
) -> int:
    """
    Update fitness scores for multiple agents.

    Args:
        session: Database session
        updates: List of {"agent_id": str, "fitness_score": float}

    Returns:
        Number of agents updated
    """
    updated_count = 0
    for update in updates:
        agent_id = update.get("agent_id")
        fitness = update.get("fitness_score")

        if agent_id and fitness is not None:
            agent = await get_agent_by_id(session, agent_id)
            if agent:
                agent.fitness_score = max(0.0, min(100.0, fitness))
                updated_count += 1

    await session.flush()
    return updated_count


# =============================================================================
# Delete Operations
# =============================================================================


async def delete_agent(
    session: AsyncSession,
    agent_id: str,
    hard_delete: bool = False,
) -> bool:
    """
    Delete an agent (soft delete by default).

    Soft delete sets status='dead' and is_active=False.
    Hard delete removes from database entirely.

    Args:
        session: Database session
        agent_id: Agent to delete
        hard_delete: If True, permanently remove from DB

    Returns:
        True if deleted, False if not found
    """
    agent = await get_agent_by_id(session, agent_id)
    if not agent:
        return False

    if hard_delete:
        await session.delete(agent)
    else:
        agent.status = "dead"
        agent.is_active = False
        agent.updated_at = datetime.utcnow()

    await session.flush()
    return True


async def bulk_delete_agents(
    session: AsyncSession,
    agent_ids: list[str],
) -> int:
    """
    Soft-delete multiple agents.

    Args:
        session: Database session
        agent_ids: List of agent IDs to delete

    Returns:
        Number of agents deleted
    """
    deleted_count = 0
    for agent_id in agent_ids:
        if await delete_agent(session, agent_id, hard_delete=False):
            deleted_count += 1

    return deleted_count
