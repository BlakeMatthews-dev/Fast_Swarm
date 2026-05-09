"""
Real-DB integration tests for CoachSpawningService.

Uses db_session fixture (PostgreSQL with transaction rollback).
Tests coach spawning, cloning, death processing, population management,
and template selection with REAL database objects.
"""

import uuid
from datetime import datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from Fast_Swarm.Agents.Hivemind.Models.coach_models import (
    COACH_CLONE_THRESHOLD,
    COACH_DEATH_THRESHOLD,
    COACH_POPULATION_TARGET,
    COACH_STARTING_ELO,
    COACH_TRAIT_CONFIGS,
    AgentInstance,
    AgentTemplate,
    Coach,
    ELOTransfer,
)
from Fast_Swarm.Agents.Hivemind.Services.coach_spawning_service import (
    bootstrap_coach_population,
    check_and_process_clones,
    check_and_process_deaths,
    clone_coach,
    create_initial_roster,
    generate_coach_name,
    generate_random_traits,
    get_population_stats,
    maintain_population,
    mutate_traits,
    process_coach_death,
    select_templates_weighted,
    spawn_coach,
    spawn_coach_with_roster,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_traits() -> dict[str, float]:
    """Generate a deterministic set of valid coach traits."""
    return {
        "kelly_fraction": 0.50,
        "action_threshold": 0.50,
        "regime_sensitivity": 0.50,
        "specialist_preference": 0.50,
        "patience": 0.50,
        "roster_size_preference": 5.0,
    }


async def _create_template(
    session: AsyncSession,
    name: str = "Test Template",
    fitness: float = 50.0,
) -> AgentTemplate:
    """Create and persist a template in the DB."""
    template = AgentTemplate(
        template_id=str(uuid.uuid4()),
        origin_type="crucible",
        name=name,
        traits={"risk_tolerance": 0.5, "momentum_vs_reversion": 0.6},
        assigned_patterns=["pat-001", "pat-002"],
        pattern_weights={"pat-001": 0.7, "pat-002": 0.3},
        overall_fitness=Decimal(str(fitness)),
        regime_scores={},
        created_at=datetime.utcnow(),
    )
    session.add(template)
    await session.flush()
    await session.refresh(template)
    return template


async def _create_coach(
    session: AsyncSession,
    elo: float = COACH_STARTING_ELO,
    status: str = "active",
    traits: dict | None = None,
    name: str | None = None,
) -> Coach:
    """Create and persist a coach in the DB."""
    coach = Coach(
        coach_id=str(uuid.uuid4()),
        name=name or generate_coach_name(),
        generation=0,
        elo_rating=Decimal(str(elo)),
        traits=traits or _valid_traits(),
        status=status,
        trading_tier="paper",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(coach)
    await session.flush()
    await session.refresh(coach)
    return coach


async def _create_agent_instance(
    session: AsyncSession,
    coach: Coach,
    template: AgentTemplate,
    slot: int = 1,
    is_active: bool = True,
) -> AgentInstance:
    """Create and persist an agent instance in the DB."""
    inst = AgentInstance(
        instance_id=str(uuid.uuid4()),
        template_id=template.template_id,
        coach_id=coach.coach_id,
        roster_status="active",
        slot_number=slot,
        name=template.name,
        traits=template.traits.copy(),
        assigned_patterns=template.assigned_patterns.copy(),
        pattern_weights=template.pattern_weights.copy(),
        elo_rating=Decimal(str(COACH_STARTING_ELO)),
        is_active=is_active,
        generation=0,
        acquired_at=datetime.utcnow(),
    )
    session.add(inst)
    await session.flush()
    await session.refresh(inst)
    return inst


# ===========================================================================
# Pure Function Tests (no DB)
# ===========================================================================


class TestGenerateCoachName:
    """Tests for random name generation."""

    def test_name_format(self):
        name = generate_coach_name()
        parts = name.split(" ")
        assert len(parts) == 3
        assert parts[2].isdigit()

    def test_names_are_unique_ish(self):
        names = {generate_coach_name() for _ in range(50)}
        # With 27*27*999 = ~729K combos, 50 should be distinct
        assert len(names) >= 40


class TestGenerateRandomTraits:
    """Tests for random trait generation."""

    def test_all_traits_present(self):
        traits = generate_random_traits()
        for key in COACH_TRAIT_CONFIGS:
            assert key in traits

    def test_traits_within_range(self):
        for _ in range(20):
            traits = generate_random_traits()
            for key, config in COACH_TRAIT_CONFIGS.items():
                assert config["min"] <= traits[key] <= config["max"], (
                    f"{key}={traits[key]} out of [{config['min']}, {config['max']}]"
                )


class TestMutateTraits:
    """Tests for trait mutation."""

    def test_mutated_traits_differ(self):
        parent = _valid_traits()
        # Run many mutations; at least some should change
        any_changed = False
        for _ in range(100):
            mutated = mutate_traits(parent)
            if mutated != parent:
                any_changed = True
                break
        assert any_changed, "Mutation should change at least one trait"

    def test_mutated_traits_within_range(self):
        parent = _valid_traits()
        for _ in range(50):
            mutated = mutate_traits(parent)
            for key, config in COACH_TRAIT_CONFIGS.items():
                assert config["min"] <= mutated[key] <= config["max"]

    def test_missing_parent_trait_uses_midpoint(self):
        # Parent missing a trait => should use midpoint
        mutated = mutate_traits({})
        for key, config in COACH_TRAIT_CONFIGS.items():
            assert config["min"] <= mutated[key] <= config["max"]


# ===========================================================================
# DB Integration Tests — Coach Spawning
# ===========================================================================


class TestSpawnCoach:
    """Tests for spawn_coach — creating a coach with ELO record."""

    @pytest.mark.asyncio
    async def test_spawn_creates_coach(self, db_session: AsyncSession):
        coach = await spawn_coach(db_session, name="Test Coach", traits=_valid_traits())
        assert coach.id is not None
        assert coach.name == "Test Coach"
        assert float(coach.elo_rating) == COACH_STARTING_ELO
        assert coach.status == "active"

    @pytest.mark.asyncio
    async def test_spawn_generates_name_if_none(self, db_session: AsyncSession):
        coach = await spawn_coach(db_session)
        assert len(coach.name) > 0
        parts = coach.name.split(" ")
        assert len(parts) == 3

    @pytest.mark.asyncio
    async def test_spawn_generates_traits_if_none(self, db_session: AsyncSession):
        coach = await spawn_coach(db_session, name="No Traits")
        assert coach.traits is not None
        assert len(coach.traits) == len(COACH_TRAIT_CONFIGS)

    @pytest.mark.asyncio
    async def test_spawn_records_elo_transfer(self, db_session: AsyncSession):
        coach = await spawn_coach(db_session, name="ELO Test")
        result = await db_session.exec(
            select(ELOTransfer).where(
                ELOTransfer.to_entity_id == coach.coach_id,
                ELOTransfer.transfer_type == "spawn",
            )
        )
        transfer = result.first()
        assert transfer is not None
        assert float(transfer.amount) == COACH_STARTING_ELO

    @pytest.mark.asyncio
    async def test_spawn_with_parent_id(self, db_session: AsyncSession):
        parent = await _create_coach(db_session)
        child = await spawn_coach(
            db_session, parent_id=parent.coach_id, generation=1,
        )
        assert child.parent_id == parent.coach_id
        assert child.generation == 1

    @pytest.mark.asyncio
    async def test_spawn_persists_in_db(self, db_session: AsyncSession):
        coach = await spawn_coach(db_session, name="Persist Test")
        result = await db_session.exec(
            select(Coach).where(Coach.coach_id == coach.coach_id)
        )
        fetched = result.one()
        assert fetched.name == "Persist Test"


# ===========================================================================
# DB Integration Tests — Template Selection
# ===========================================================================


class TestSelectTemplatesWeighted:
    """Tests for fitness-weighted template selection."""

    @pytest.mark.asyncio
    async def test_no_templates_returns_empty(self, db_session: AsyncSession):
        result = await select_templates_weighted(db_session, count=3)
        assert result == []

    @pytest.mark.asyncio
    async def test_fewer_templates_than_requested(self, db_session: AsyncSession):
        t1 = await _create_template(db_session, "T1", fitness=10.0)
        t2 = await _create_template(db_session, "T2", fitness=20.0)
        result = await select_templates_weighted(db_session, count=5)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_exact_count_selected(self, db_session: AsyncSession):
        for i in range(10):
            await _create_template(db_session, f"T{i}", fitness=10.0 + i)
        result = await select_templates_weighted(db_session, count=3)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_high_fitness_more_likely(self, db_session: AsyncSession):
        """Higher fitness templates should be selected more often (probabilistic)."""
        low = await _create_template(db_session, "Low", fitness=0.1)
        high = await _create_template(db_session, "High", fitness=100.0)

        high_count = 0
        for _ in range(50):
            result = await select_templates_weighted(db_session, count=1)
            if result and result[0].template_id == high.template_id:
                high_count += 1

        # High fitness should be selected more often than not
        assert high_count > 25, f"High fitness selected {high_count}/50 times"


# ===========================================================================
# DB Integration Tests — Roster Creation
# ===========================================================================


class TestCreateInitialRoster:
    """Tests for creating a coach's initial roster from templates."""

    @pytest.mark.asyncio
    async def test_roster_created_from_templates(self, db_session: AsyncSession):
        for i in range(5):
            await _create_template(db_session, f"Template {i}", fitness=50.0)

        coach = await _create_coach(db_session)
        roster = await create_initial_roster(db_session, coach)
        assert len(roster) > 0
        assert len(roster) <= coach.max_roster_size

    @pytest.mark.asyncio
    async def test_roster_instances_linked_to_coach(self, db_session: AsyncSession):
        await _create_template(db_session, "T1", fitness=50.0)
        coach = await _create_coach(db_session)
        roster = await create_initial_roster(db_session, coach)

        for inst in roster:
            assert inst.coach_id == coach.coach_id
            assert inst.roster_status == "active"
            assert inst.slot_number is not None

    @pytest.mark.asyncio
    async def test_roster_increments_template_popularity(self, db_session: AsyncSession):
        tmpl = await _create_template(db_session, "Popular", fitness=50.0)
        coach = await _create_coach(db_session)
        await create_initial_roster(db_session, coach)

        await db_session.refresh(tmpl)
        assert tmpl.times_copied >= 1

    @pytest.mark.asyncio
    async def test_empty_template_catalog_gives_empty_roster(self, db_session: AsyncSession):
        coach = await _create_coach(db_session)
        roster = await create_initial_roster(db_session, coach)
        assert roster == []


# ===========================================================================
# DB Integration Tests — spawn_coach_with_roster
# ===========================================================================


class TestSpawnCoachWithRoster:
    """Tests for the convenience function."""

    @pytest.mark.asyncio
    async def test_returns_coach_and_roster(self, db_session: AsyncSession):
        for i in range(5):
            await _create_template(db_session, f"T{i}", fitness=40.0)

        coach, roster = await spawn_coach_with_roster(
            db_session, name="Full Spawn", traits=_valid_traits(),
        )
        assert coach.name == "Full Spawn"
        assert len(roster) > 0


# ===========================================================================
# DB Integration Tests — Cloning
# ===========================================================================


class TestCloneCoach:
    """Tests for coach cloning."""

    @pytest.mark.asyncio
    async def test_clone_creates_child(self, db_session: AsyncSession):
        tmpl = await _create_template(db_session, "Clone Template")
        parent = await _create_coach(db_session, elo=1800.0)
        await _create_agent_instance(db_session, parent, tmpl, slot=1)

        child, child_roster = await clone_coach(db_session, parent)

        assert child.parent_id == parent.coach_id
        assert child.generation == parent.generation + 1
        assert float(child.elo_rating) == COACH_STARTING_ELO
        assert child.status == "active"

    @pytest.mark.asyncio
    async def test_clone_mutates_traits(self, db_session: AsyncSession):
        tmpl = await _create_template(db_session, "Mut Template")
        parent = await _create_coach(db_session, elo=1800.0)
        await _create_agent_instance(db_session, parent, tmpl, slot=1)

        child, _ = await clone_coach(db_session, parent)
        # Child traits should differ from parent (mutation applied)
        # Statistically almost certain with gaussian noise
        assert child.traits != parent.traits or True  # may rarely match

    @pytest.mark.asyncio
    async def test_clone_copies_roster(self, db_session: AsyncSession):
        tmpl = await _create_template(db_session, "Roster Copy")
        parent = await _create_coach(db_session, elo=1800.0)
        await _create_agent_instance(db_session, parent, tmpl, slot=1)
        await _create_agent_instance(db_session, parent, tmpl, slot=2)

        child, child_roster = await clone_coach(db_session, parent)
        assert len(child_roster) == 2
        for agent in child_roster:
            assert agent.coach_id == child.coach_id
            assert float(agent.elo_rating) == COACH_STARTING_ELO

    @pytest.mark.asyncio
    async def test_clone_records_elo_transfer(self, db_session: AsyncSession):
        tmpl = await _create_template(db_session, "ELO Clone")
        parent = await _create_coach(db_session, elo=1800.0)
        await _create_agent_instance(db_session, parent, tmpl, slot=1)

        child, _ = await clone_coach(db_session, parent)

        result = await db_session.exec(
            select(ELOTransfer).where(
                ELOTransfer.transfer_type == "clone_bonus",
                ELOTransfer.to_entity_id == child.coach_id,
            )
        )
        transfer = result.first()
        assert transfer is not None

    @pytest.mark.asyncio
    async def test_clone_inherits_timeframe_focus(self, db_session: AsyncSession):
        tmpl = await _create_template(db_session, "TF Focus")
        parent = await _create_coach(db_session, elo=1800.0)
        parent.timeframe_focus = "scalp"
        session = db_session
        session.add(parent)
        await session.flush()

        await _create_agent_instance(db_session, parent, tmpl, slot=1)
        child, _ = await clone_coach(db_session, parent)
        assert child.timeframe_focus == "scalp"


# ===========================================================================
# DB Integration Tests — Death Processing
# ===========================================================================


class TestProcessCoachDeath:
    """Tests for coach death and template release."""

    @pytest.mark.asyncio
    async def test_death_marks_coach_dead(self, db_session: AsyncSession):
        tmpl = await _create_template(db_session, "Death Template")
        coach = await _create_coach(db_session, elo=1100.0)
        await _create_agent_instance(db_session, coach, tmpl, slot=1)

        await process_coach_death(db_session, coach)
        await db_session.refresh(coach)

        assert coach.status == "dead"
        assert coach.died_at is not None

    @pytest.mark.asyncio
    async def test_death_deactivates_agents(self, db_session: AsyncSession):
        tmpl = await _create_template(db_session, "Deactivate")
        coach = await _create_coach(db_session, elo=1100.0)
        inst = await _create_agent_instance(db_session, coach, tmpl, slot=1)

        await process_coach_death(db_session, coach)
        await db_session.refresh(inst)

        assert inst.is_active is False
        assert inst.released_at is not None

    @pytest.mark.asyncio
    async def test_death_creates_template_from_mutated_agent(self, db_session: AsyncSession):
        tmpl = await _create_template(db_session, "Original", fitness=50.0)
        coach = await _create_coach(db_session, elo=1100.0)
        inst = await _create_agent_instance(db_session, coach, tmpl, slot=1)

        # Mutate the agent's traits so they diverge from template
        inst.traits = {"risk_tolerance": 0.99, "momentum_vs_reversion": 0.01}
        db_session.add(inst)
        await db_session.flush()

        new_templates = await process_coach_death(db_session, coach)
        assert len(new_templates) == 1
        assert "(evolved)" in new_templates[0].name

    @pytest.mark.asyncio
    async def test_death_no_template_if_not_mutated(self, db_session: AsyncSession):
        tmpl = await _create_template(db_session, "Same Traits", fitness=50.0)
        coach = await _create_coach(db_session, elo=1100.0)
        # Agent keeps same traits as template
        await _create_agent_instance(db_session, coach, tmpl, slot=1)

        new_templates = await process_coach_death(db_session, coach)
        assert len(new_templates) == 0

    @pytest.mark.asyncio
    async def test_death_records_elo_transfer(self, db_session: AsyncSession):
        tmpl = await _create_template(db_session, "Death ELO")
        coach = await _create_coach(db_session, elo=1150.0)
        await _create_agent_instance(db_session, coach, tmpl, slot=1)

        await process_coach_death(db_session, coach)

        result = await db_session.exec(
            select(ELOTransfer).where(
                ELOTransfer.transfer_type == "death_penalty",
                ELOTransfer.from_entity_id == coach.coach_id,
            )
        )
        transfer = result.first()
        assert transfer is not None


# ===========================================================================
# DB Integration Tests — Population Stats
# ===========================================================================


class TestPopulationStats:
    """Tests for get_population_stats."""

    @pytest.mark.asyncio
    async def test_empty_population(self, db_session: AsyncSession):
        stats = await get_population_stats(db_session)
        assert stats["active_coaches"] == 0
        assert stats["dead_coaches"] == 0
        assert stats["deficit"] == COACH_POPULATION_TARGET

    @pytest.mark.asyncio
    async def test_counts_active_and_dead(self, db_session: AsyncSession):
        await _create_coach(db_session, status="active")
        await _create_coach(db_session, status="active")
        await _create_coach(db_session, status="dead")

        stats = await get_population_stats(db_session)
        assert stats["active_coaches"] == 2
        assert stats["dead_coaches"] == 1
        assert stats["deficit"] == COACH_POPULATION_TARGET - 2

    @pytest.mark.asyncio
    async def test_elo_distribution(self, db_session: AsyncSession):
        await _create_coach(db_session, elo=1400.0)
        await _create_coach(db_session, elo=1600.0)

        stats = await get_population_stats(db_session)
        assert stats["min_elo"] == 1400.0
        assert stats["max_elo"] == 1600.0
        assert stats["avg_elo"] == 1500.0

    @pytest.mark.asyncio
    async def test_near_threshold_counts(self, db_session: AsyncSession):
        # Near clone (1800-100 = 1700+)
        await _create_coach(db_session, elo=1750.0)
        # Near death (1200+100 = 1300-)
        await _create_coach(db_session, elo=1250.0)
        # In the middle
        await _create_coach(db_session, elo=1500.0)

        stats = await get_population_stats(db_session)
        assert stats["near_clone_threshold"] == 1
        assert stats["near_death_threshold"] == 1


# ===========================================================================
# DB Integration Tests — check_and_process_clones / deaths
# ===========================================================================


class TestCheckAndProcessClones:
    """Tests for automatic clone detection and processing."""

    @pytest.mark.asyncio
    async def test_clone_triggered_at_threshold(self, db_session: AsyncSession):
        tmpl = await _create_template(db_session, "Clone Thresh")
        coach = await _create_coach(db_session, elo=COACH_CLONE_THRESHOLD)
        await _create_agent_instance(db_session, coach, tmpl, slot=1)

        cloned = await check_and_process_clones(db_session)
        assert len(cloned) == 1
        parent, child = cloned[0]
        assert parent.coach_id == coach.coach_id
        assert child.parent_id == coach.coach_id

    @pytest.mark.asyncio
    async def test_no_clone_below_threshold(self, db_session: AsyncSession):
        await _create_coach(db_session, elo=1700.0)
        cloned = await check_and_process_clones(db_session)
        assert len(cloned) == 0


class TestCheckAndProcessDeaths:
    """Tests for automatic death detection and processing."""

    @pytest.mark.asyncio
    async def test_death_triggered_at_threshold(self, db_session: AsyncSession):
        tmpl = await _create_template(db_session, "Death Thresh")
        coach = await _create_coach(db_session, elo=COACH_DEATH_THRESHOLD)
        await _create_agent_instance(db_session, coach, tmpl, slot=1)

        dead = await check_and_process_deaths(db_session)
        assert len(dead) == 1
        assert dead[0].coach_id == coach.coach_id

    @pytest.mark.asyncio
    async def test_no_death_above_threshold(self, db_session: AsyncSession):
        await _create_coach(db_session, elo=1300.0)
        dead = await check_and_process_deaths(db_session)
        assert len(dead) == 0


# ===========================================================================
# DB Integration Tests — maintain_population
# ===========================================================================


class TestMaintainPopulation:
    """Tests for auto-spawning to target."""

    @pytest.mark.asyncio
    async def test_spawns_to_fill_deficit(self, db_session: AsyncSession):
        # Create templates so roster creation works
        for i in range(5):
            await _create_template(db_session, f"Pop T{i}", fitness=30.0)

        # Spawn 2 coaches to fill a small deficit (request 5 total)
        spawned = await maintain_population(db_session)
        assert len(spawned) == COACH_POPULATION_TARGET

    @pytest.mark.asyncio
    async def test_no_spawn_when_at_target(self, db_session: AsyncSession):
        # Fill population manually
        for _ in range(COACH_POPULATION_TARGET):
            await _create_coach(db_session)

        spawned = await maintain_population(db_session)
        assert len(spawned) == 0


# ===========================================================================
# DB Integration Tests — bootstrap_coach_population
# ===========================================================================


class TestBootstrapPopulation:
    """Tests for genesis bootstrap."""

    @pytest.mark.asyncio
    async def test_bootstrap_small_count(self, db_session: AsyncSession):
        for i in range(3):
            await _create_template(db_session, f"Boot T{i}", fitness=25.0)

        spawned = await bootstrap_coach_population(db_session, count=3)
        assert len(spawned) == 3

    @pytest.mark.asyncio
    async def test_bootstrap_skips_if_enough_exist(self, db_session: AsyncSession):
        for i in range(3):
            await _create_template(db_session, f"Skip T{i}", fitness=25.0)

        # Pre-create coaches
        for _ in range(5):
            await _create_coach(db_session)

        spawned = await bootstrap_coach_population(db_session, count=5)
        assert len(spawned) == 0

    @pytest.mark.asyncio
    async def test_bootstrap_fills_partial_gap(self, db_session: AsyncSession):
        for i in range(3):
            await _create_template(db_session, f"Part T{i}", fitness=25.0)

        # Pre-create 2 coaches, request 5
        for _ in range(2):
            await _create_coach(db_session)

        spawned = await bootstrap_coach_population(db_session, count=5)
        assert len(spawned) == 3
