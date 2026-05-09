"""
Coach Spawning Service for Coopetition System.

Implements:
- Population target maintenance (100 coaches)
- Random trait generation for new coaches
- Fitness-weighted template selection for initial roster
- Clone creation with trait mutation

Design:
- Pure random new coaches (maximum exploration)
- Coaches choose roster via fitness-weighted random selection
- Maintains population at target through auto-spawning
"""

import random
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from ..Models.coach_models import (
    COACH_CLONE_THRESHOLD,
    COACH_DEATH_THRESHOLD,
    COACH_POPULATION_TARGET,
    COACH_STARTING_ELO,
    COACH_TRAIT_CONFIGS,
    AgentInstance,
    AgentTemplate,
    Coach,
)
from .elo_transfer_service import apply_clone_bonus, apply_death_elo, apply_spawn_elo

# =============================================================================
# Name Generation
# =============================================================================

COACH_ADJECTIVES = [
    "Bold", "Swift", "Calm", "Fierce", "Wise", "Sharp", "Quick", "Steady",
    "Cunning", "Patient", "Brave", "Clever", "Silent", "Keen", "Agile",
    "Ruthless", "Prudent", "Fearless", "Cautious", "Relentless", "Stoic",
    "Vigilant", "Tenacious", "Shrewd", "Astute", "Resolute", "Nimble",
]

COACH_NOUNS = [
    "Wolf", "Hawk", "Bear", "Fox", "Lion", "Eagle", "Tiger", "Shark",
    "Viper", "Falcon", "Panther", "Cobra", "Raven", "Lynx", "Orca",
    "Mantis", "Scorpion", "Phoenix", "Dragon", "Sphinx", "Griffin",
    "Hydra", "Kraken", "Chimera", "Basilisk", "Wyvern", "Leviathan",
]


def generate_coach_name() -> str:
    """Generate a random coach name."""
    adj = random.choice(COACH_ADJECTIVES)
    noun = random.choice(COACH_NOUNS)
    num = random.randint(1, 999)
    return adj + " " + noun + " " + str(num)


# =============================================================================
# Trait Generation
# =============================================================================


def generate_random_traits() -> dict[str, float]:
    """
    Generate random traits within valid ranges.

    Each trait is uniformly sampled from its min-max range.
    """
    traits = {}
    for trait_name, config in COACH_TRAIT_CONFIGS.items():
        min_val = config["min"]
        max_val = config["max"]
        traits[trait_name] = random.uniform(min_val, max_val)
    return traits


def mutate_traits(parent_traits: dict[str, float]) -> dict[str, float]:
    """
    Mutate parent traits with gaussian noise.

    Each trait is perturbed by N(0, mutation_std) and clamped to valid range.
    """
    mutated = {}
    for trait_name, config in COACH_TRAIT_CONFIGS.items():
        parent_val = parent_traits.get(trait_name, (config["min"] + config["max"]) / 2)
        mutation_std = config["mutation_std"]

        # Apply gaussian mutation
        new_val = parent_val + random.gauss(0, mutation_std)

        # Clamp to valid range
        new_val = max(config["min"], min(config["max"], new_val))
        mutated[trait_name] = new_val

    return mutated


# =============================================================================
# Template Selection
# =============================================================================


async def select_templates_weighted(
    session: AsyncSession,
    count: int = 3,
) -> list[AgentTemplate]:
    """
    Select templates using fitness-weighted random selection.

    Higher fitness = higher probability of selection.

    Args:
        session: Database session
        count: Number of templates to select

    Returns:
        List of selected AgentTemplate objects
    """
    # Get all templates
    result = await session.exec(select(AgentTemplate))
    templates = list(result.all())

    if not templates:
        return []

    if len(templates) <= count:
        return templates

    # Calculate selection weights (fitness + small epsilon to avoid zero)
    weights = [max(0.1, float(t.overall_fitness)) for t in templates]

    # Weighted random selection without replacement
    selected = []
    available = list(zip(templates, weights))

    for _ in range(count):
        if not available:
            break

        total_weight = sum(w for _, w in available)
        r = random.uniform(0, total_weight)

        cumulative = 0
        for i, (template, weight) in enumerate(available):
            cumulative += weight
            if r <= cumulative:
                selected.append(template)
                available.pop(i)
                break

    return selected


# =============================================================================
# Coach Creation
# =============================================================================


async def spawn_coach(
    session: AsyncSession,
    name: str | None = None,
    traits: dict[str, float] | None = None,
    parent_id: str | None = None,
    generation: int = 0,
) -> Coach:
    """
    Spawn a new coach with random or specified traits.

    Args:
        session: Database session
        name: Coach name (generated if not provided)
        traits: Coach traits (random if not provided)
        parent_id: Parent coach ID (for clones)
        generation: Generation number

    Returns:
        Created Coach object
    """
    coach = Coach(
        coach_id=str(uuid.uuid4()),
        name=name or generate_coach_name(),
        generation=generation,
        parent_id=parent_id,
        elo_rating=Decimal(str(COACH_STARTING_ELO)),
        traits=traits or generate_random_traits(),
        status="active",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    session.add(coach)
    await session.commit()
    await session.refresh(coach)

    # Record ELO spawn
    await apply_spawn_elo(session, coach.coach_id, COACH_STARTING_ELO)

    return coach


async def create_initial_roster(
    session: AsyncSession,
    coach: Coach,
) -> list[AgentInstance]:
    """
    Create initial roster for a new coach.

    Uses fitness-weighted random selection to pick templates,
    then creates agent instances from them.

    Args:
        session: Database session
        coach: Coach to create roster for

    Returns:
        List of created AgentInstance objects
    """
    # Determine roster size from coach trait
    roster_size = coach.max_roster_size

    # Select templates
    templates = await select_templates_weighted(session, count=roster_size)

    instances = []
    for i, template in enumerate(templates):
        instance = AgentInstance(
            instance_id=str(uuid.uuid4()),
            template_id=template.template_id,
            coach_id=coach.coach_id,
            roster_status="active",
            slot_number=i + 1,
            name=template.name,
            traits=template.traits.copy(),
            assigned_patterns=template.assigned_patterns.copy(),
            pattern_weights=template.pattern_weights.copy(),
            elo_rating=Decimal(str(COACH_STARTING_ELO)),
            generation=0,
            acquired_at=datetime.utcnow(),
        )

        session.add(instance)
        instances.append(instance)

        # Update template popularity
        template.times_copied += 1
        session.add(template)

    await session.commit()

    # Refresh all instances
    for instance in instances:
        await session.refresh(instance)

    return instances


async def spawn_coach_with_roster(
    session: AsyncSession,
    name: str | None = None,
    traits: dict[str, float] | None = None,
) -> tuple[Coach, list[AgentInstance]]:
    """
    Spawn a new coach and create their initial roster.

    Convenience function combining spawn_coach and create_initial_roster.

    Args:
        session: Database session
        name: Optional coach name
        traits: Optional coach traits

    Returns:
        Tuple of (Coach, list of AgentInstance)
    """
    coach = await spawn_coach(session, name=name, traits=traits)
    roster = await create_initial_roster(session, coach)
    return coach, roster


# =============================================================================
# Clone Creation
# =============================================================================


async def clone_coach(
    session: AsyncSession,
    parent: Coach,
) -> tuple[Coach, list[AgentInstance]]:
    """
    Clone a coach that hit the clone threshold.

    Creates a new coach with mutated traits and copies the parent's roster.

    Args:
        session: Database session
        parent: Parent coach to clone

    Returns:
        Tuple of (child Coach, child roster)
    """
    # Mutate parent traits
    child_traits = mutate_traits(parent.traits)

    # Create child coach
    child = Coach(
        coach_id=str(uuid.uuid4()),
        name=generate_coach_name(),
        generation=parent.generation + 1,
        parent_id=parent.coach_id,
        elo_rating=Decimal(str(COACH_STARTING_ELO)),  # Clones start at 1500
        traits=child_traits,
        status="active",
        timeframe_focus=parent.timeframe_focus,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    session.add(child)
    await session.commit()
    await session.refresh(child)

    # Record clone ELO
    await apply_clone_bonus(session, parent.coach_id, child.coach_id, COACH_STARTING_ELO)

    # Copy parent's active roster to child
    parent_roster_result = await session.exec(
        select(AgentInstance)
        .where(AgentInstance.coach_id == parent.coach_id)
        .where(AgentInstance.is_active.is_(True))
    )
    parent_roster = parent_roster_result.all()

    child_roster = []
    for i, parent_agent in enumerate(parent_roster):
        # Create new instance copying parent agent's current state
        child_agent = AgentInstance(
            instance_id=str(uuid.uuid4()),
            template_id=parent_agent.template_id,
            coach_id=child.coach_id,
            roster_status=parent_agent.roster_status,
            slot_number=parent_agent.slot_number,
            name=parent_agent.name,
            traits=parent_agent.traits.copy(),
            assigned_patterns=parent_agent.assigned_patterns.copy(),
            pattern_weights=parent_agent.pattern_weights.copy(),
            elo_rating=Decimal(str(COACH_STARTING_ELO)),  # Fresh ELO for child's agents
            parent_instance_id=parent_agent.instance_id,
            generation=parent_agent.generation + 1,
            acquired_at=datetime.utcnow(),
        )

        session.add(child_agent)
        child_roster.append(child_agent)

    await session.commit()

    for agent in child_roster:
        await session.refresh(agent)

    return child, child_roster


# =============================================================================
# Population Management
# =============================================================================


async def get_population_stats(session: AsyncSession) -> dict[str, Any]:
    """
    Get current coach population statistics.

    Returns:
        Dict with population metrics
    """
    # Count active coaches
    active_result = await session.exec(
        select(func.count(Coach.id)).where(Coach.status == "active")
    )
    active_count = active_result.one()

    # Count dead coaches
    dead_result = await session.exec(
        select(func.count(Coach.id)).where(Coach.status == "dead")
    )
    dead_count = dead_result.one()

    # Get ELO distribution
    elo_result = await session.exec(
        select(Coach.elo_rating).where(Coach.status == "active")
    )
    elos = [float(e) for e in elo_result.all()]

    avg_elo = sum(elos) / len(elos) if elos else COACH_STARTING_ELO
    min_elo = min(elos) if elos else 0
    max_elo = max(elos) if elos else 0

    # Count coaches near thresholds
    near_clone = sum(1 for e in elos if e >= COACH_CLONE_THRESHOLD - 100)
    near_death = sum(1 for e in elos if e <= COACH_DEATH_THRESHOLD + 100)

    return {
        "active_coaches": active_count,
        "dead_coaches": dead_count,
        "target_population": COACH_POPULATION_TARGET,
        "deficit": max(0, COACH_POPULATION_TARGET - active_count),
        "avg_elo": avg_elo,
        "min_elo": min_elo,
        "max_elo": max_elo,
        "near_clone_threshold": near_clone,
        "near_death_threshold": near_death,
    }


async def maintain_population(
    session: AsyncSession,
) -> list[Coach]:
    """
    Spawn coaches to maintain population at target.

    Called periodically to ensure 100 active coaches.

    Returns:
        List of newly spawned coaches
    """
    stats = await get_population_stats(session)
    deficit = stats["deficit"]

    if deficit <= 0:
        return []

    spawned = []
    for _ in range(deficit):
        coach, _ = await spawn_coach_with_roster(session)
        spawned.append(coach)

    return spawned


# =============================================================================
# Death Processing
# =============================================================================


async def process_coach_death(
    session: AsyncSession,
    coach: Coach,
) -> list[AgentTemplate]:
    """
    Process a coach death (hit 1200 ELO threshold).

    - Mark coach as dead
    - Snapshot mutated agents to template catalog
    - Remove agent instances

    Args:
        session: Database session
        coach: Coach that died

    Returns:
        List of templates created from mutated agents
    """
    # Mark coach as dead
    coach.status = "dead"
    coach.died_at = datetime.utcnow()
    session.add(coach)

    # Record death ELO transfer
    await apply_death_elo(session, coach)

    # Get coach's roster
    roster_result = await session.exec(
        select(AgentInstance).where(AgentInstance.coach_id == coach.coach_id)
    )
    roster = roster_result.all()

    new_templates = []

    for agent in roster:
        # Check if agent has mutated from template
        template_result = await session.exec(
            select(AgentTemplate).where(AgentTemplate.template_id == agent.template_id)
        )
        original_template = template_result.first()

        # Only create new template if agent has diverged
        if original_template and agent.traits != original_template.traits:
            new_template = AgentTemplate(
                template_id=str(uuid.uuid4()),
                origin_type="release",
                source_agent_id=agent.instance_id,
                parent_template_id=agent.template_id,
                name=agent.name + " (evolved)",
                traits=agent.traits.copy(),
                assigned_patterns=agent.assigned_patterns.copy(),
                pattern_weights=agent.pattern_weights.copy(),
                overall_fitness=Decimal(str(float(agent.elo_rating) / 10)),  # Approximate fitness from ELO
                regime_scores={},
                created_at=datetime.utcnow(),
            )
            session.add(new_template)
            new_templates.append(new_template)

        # Deactivate agent instance
        agent.is_active = False
        agent.released_at = datetime.utcnow()
        session.add(agent)

    await session.commit()

    for template in new_templates:
        await session.refresh(template)

    return new_templates


# =============================================================================
# Clone Processing
# =============================================================================


async def check_and_process_clones(
    session: AsyncSession,
) -> list[tuple[Coach, Coach]]:
    """
    Check for coaches at clone threshold and process cloning.

    Returns:
        List of (parent, child) tuples for cloned coaches
    """
    # Find coaches at or above clone threshold
    result = await session.exec(
        select(Coach)
        .where(Coach.status == "active")
        .where(Coach.elo_rating >= COACH_CLONE_THRESHOLD)
    )
    coaches_to_clone = result.all()

    cloned = []
    for parent in coaches_to_clone:
        child, _ = await clone_coach(session, parent)
        cloned.append((parent, child))

        # Reset parent ELO to prevent immediate re-clone
        # (They keep their ELO but it's tracked they cloned)
        parent.updated_at = datetime.utcnow()
        session.add(parent)

    await session.commit()

    return cloned


async def check_and_process_deaths(
    session: AsyncSession,
) -> list[Coach]:
    """
    Check for coaches at death threshold and process deaths.

    Returns:
        List of coaches that died
    """
    # Find coaches at or below death threshold
    result = await session.exec(
        select(Coach)
        .where(Coach.status == "active")
        .where(Coach.elo_rating <= COACH_DEATH_THRESHOLD)
    )
    coaches_to_kill = result.all()

    dead = []
    for coach in coaches_to_kill:
        await process_coach_death(session, coach)
        dead.append(coach)

    return dead


# =============================================================================
# Bootstrap / Genesis
# =============================================================================


async def bootstrap_coach_population(
    session: AsyncSession,
    count: int | None = None,
) -> list[Coach]:
    """
    Bootstrap the initial coach population.

    Called once at system startup if no coaches exist.

    Args:
        session: Database session
        count: Number to spawn (defaults to COACH_POPULATION_TARGET)

    Returns:
        List of spawned coaches
    """
    count = count or COACH_POPULATION_TARGET

    # Check if coaches already exist
    existing_result = await session.exec(
        select(func.count(Coach.id)).where(Coach.status == "active")
    )
    existing = existing_result.one()

    if existing >= count:
        return []

    to_spawn = count - existing
    spawned = []

    for _ in range(to_spawn):
        coach, _ = await spawn_coach_with_roster(session)
        spawned.append(coach)

    return spawned
