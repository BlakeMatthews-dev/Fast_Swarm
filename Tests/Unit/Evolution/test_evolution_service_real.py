"""
Real-DB integration tests for AgentEvolutionService.

Uses db_session fixture (PostgreSQL with transaction rollback).
Tests clone, crossover, batch_clone, lineage detection, and evolve_generation
with REAL Agent/Pattern rows in the database.

External calls (spawn_agent, AgentDatabase) are mocked to avoid
touching local_agents infrastructure.
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from Fast_Swarm.Agents.Models.agent_models import Agent
from Fast_Swarm.Agents.Services.evolution_service import (
    AgentEvolutionService,
    _extract_patterns_from_agent,
    get_evolution_status,
    reset_evolution_flag,
)
from Fast_Swarm.Patterns.Models.pattern_models import Pattern


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_traits() -> dict[str, float]:
    return {
        "risk_tolerance": 0.5, "hold_duration_bias": 0.5, "volatility_seeking": 0.5,
        "profit_target_greed": 0.5, "win_rate_preference": 0.5, "drawdown_sensitivity": 0.5,
        "momentum_vs_reversion": 0.5, "stop_loss_tightness": 0.5, "entry_aggression": 0.5,
        "exit_aggression": 0.5, "lookback_preference": 0.5, "sentiment_weight": 0.5,
        "news_reactivity": 0.5, "sentiment_contrarian": 0.5, "funding_rate_sensitivity": 0.5,
        "correlation_awareness": 0.5, "patience": 0.5, "adaptability": 0.5,
        "trend_following": 0.5, "mean_reversion": 0.5, "breakout_preference": 0.5,
        "volume_sensitivity": 0.5,
    }


def _make_agent(
    agent_id: str | None = None,
    fitness: float = 50.0,
    generation: int = 1,
    level: int = 1,
    status: str = "active",
    traits: dict | None = None,
    parent_a_id: str | None = None,
    parent_b_id: str | None = None,
    assigned_patterns: dict | None = None,
    backtest_count: int = 0,
) -> Agent:
    """Build an Agent instance (not yet added to session)."""
    return Agent(
        agent_id=agent_id or f"test-{uuid.uuid4().hex[:8]}",
        name=f"TestAgent-{uuid.uuid4().hex[:4]}",
        generation=generation,
        level=level,
        traits=traits or _default_traits(),
        status=status,
        is_active=(status == "active"),
        fitness_score=Decimal(str(fitness)),
        fitness_by_regime={},
        elo_rating=Decimal("1500"),
        parent_a_id=parent_a_id,
        parent_b_id=parent_b_id,
        assigned_patterns=assigned_patterns or {},
        backtest_count=backtest_count,
    )


def _make_pattern(pattern_id: str | None = None, fitness: float = 60.0) -> Pattern:
    """Build a Pattern instance."""
    return Pattern(
        pattern_id=pattern_id or f"pat-{uuid.uuid4().hex[:8]}",
        name=f"TestPattern-{uuid.uuid4().hex[:4]}",
        origin="technical",
        status="untested",
        is_active=True,
        entry_conditions=[{"indicator": "rsi", "operator": "<", "value": 30}],
        exit_conditions=[{"indicator": "rsi", "operator": ">", "value": 70}],
        fitness_score=Decimal(str(fitness)),
        total_trades=0,
        total_runs=0,
    )


def _fake_spawn_agent(**kwargs):
    """Return a mock agent record mimicking spawn_agent output."""
    record = MagicMock()
    record.agent_id = f"spawned-{uuid.uuid4().hex[:8]}"
    record.traits = _default_traits()
    record.pattern_ids = []
    record.pattern_weights = {}
    record.trading_philosophy = "test philosophy"
    return record


async def _seed_agents(session: AsyncSession, count: int, fitness_start: float = 10.0) -> list[Agent]:
    """Seed N agents with ascending fitness scores."""
    agents = []
    for i in range(count):
        a = _make_agent(
            fitness=fitness_start + i * 10,
            backtest_count=5,
        )
        session.add(a)
        agents.append(a)
    await session.flush()
    for a in agents:
        await session.refresh(a)
    return agents


# ---------------------------------------------------------------------------
# Tests: _extract_patterns_from_agent
# ---------------------------------------------------------------------------

class TestExtractPatternsFromAgent:
    """Tests for pattern extraction from agent JSONB."""

    def test_none_assigned_patterns(self):
        agent = _make_agent(assigned_patterns=None)
        agent.assigned_patterns = None
        result = _extract_patterns_from_agent(agent)
        assert result == []

    def test_empty_dict(self):
        agent = _make_agent(assigned_patterns={})
        result = _extract_patterns_from_agent(agent)
        assert result == []

    def test_modern_dict_format_with_base(self):
        patterns_data = {
            "base": [
                {
                    "pattern_id": "p1",
                    "entry_conditions": [{"indicator": "rsi", "operator": "<", "value": 30}],
                    "exit_conditions": [{"indicator": "rsi", "operator": ">", "value": 70}],
                    "fitness_score": 80.0,
                },
                {
                    "pattern_id": "p2",
                    "entry_conditions": [{"indicator": "macd", "operator": ">", "value": 0}],
                    "exit_conditions": [{"indicator": "macd", "operator": "<", "value": 0}],
                },
            ]
        }
        agent = _make_agent(assigned_patterns=patterns_data)
        result = _extract_patterns_from_agent(agent)
        assert len(result) == 2
        assert result[0]["pattern_id"] == "p1"
        assert result[0]["fitness_score"] == 80.0
        assert result[1]["fitness_score"] == 50.0  # default

    def test_legacy_list_format(self):
        patterns_list = [
            {
                "pattern_id": "leg1",
                "entry_conditions": [{"indicator": "bb", "operator": "<", "value": 20}],
                "exit_conditions": [{"indicator": "bb", "operator": ">", "value": 80}],
            }
        ]
        agent = _make_agent()
        agent.assigned_patterns = patterns_list
        result = _extract_patterns_from_agent(agent)
        assert len(result) == 1
        assert result[0]["pattern_id"] == "leg1"

    def test_legacy_list_with_string_ids_ignored(self):
        """String-only pattern IDs in legacy format cannot be recovered."""
        agent = _make_agent()
        agent.assigned_patterns = ["pat-abc", "pat-def"]
        result = _extract_patterns_from_agent(agent)
        assert result == []

    def test_preserves_confidence_threshold(self):
        patterns_data = {
            "base": [
                {
                    "pattern_id": "p1",
                    "entry_conditions": [{"indicator": "rsi", "operator": "<", "value": 30}],
                    "exit_conditions": [{"indicator": "rsi", "operator": ">", "value": 70}],
                    "confidence_threshold": 0.85,
                    "position_size_modifier": 1.5,
                },
            ]
        }
        agent = _make_agent(assigned_patterns=patterns_data)
        result = _extract_patterns_from_agent(agent)
        assert result[0]["confidence_threshold"] == 0.85
        assert result[0]["position_size_modifier"] == 1.5

    def test_skips_incomplete_patterns_in_base(self):
        """Patterns missing entry or exit conditions are skipped."""
        patterns_data = {
            "base": [
                {"pattern_id": "bad1", "entry_conditions": [{"indicator": "rsi"}]},
                {"pattern_id": "bad2", "exit_conditions": [{"indicator": "rsi"}]},
                {
                    "pattern_id": "good",
                    "entry_conditions": [{"indicator": "rsi", "operator": "<", "value": 30}],
                    "exit_conditions": [{"indicator": "rsi", "operator": ">", "value": 70}],
                },
            ]
        }
        agent = _make_agent(assigned_patterns=patterns_data)
        result = _extract_patterns_from_agent(agent)
        assert len(result) == 1
        assert result[0]["pattern_id"] == "good"


# ---------------------------------------------------------------------------
# Tests: lineage detection
# ---------------------------------------------------------------------------

class TestLineageDetection:
    """Tests for AgentEvolutionService._are_same_lineage."""

    def setup_method(self):
        self.service = AgentEvolutionService()

    def test_parent_child_forward(self):
        parent = _make_agent(agent_id="parent-1")
        child = _make_agent(agent_id="child-1", parent_a_id="parent-1")
        assert self.service._are_same_lineage(parent, child) is True

    def test_parent_child_reverse(self):
        parent = _make_agent(agent_id="parent-1")
        child = _make_agent(agent_id="child-1", parent_a_id="parent-1")
        assert self.service._are_same_lineage(child, parent) is True

    def test_siblings_share_parent(self):
        sibling_a = _make_agent(agent_id="sib-a", parent_a_id="shared-parent")
        sibling_b = _make_agent(agent_id="sib-b", parent_a_id="shared-parent")
        assert self.service._are_same_lineage(sibling_a, sibling_b) is True

    def test_unrelated_agents(self):
        a = _make_agent(agent_id="a-1", parent_a_id="parent-x")
        b = _make_agent(agent_id="b-1", parent_a_id="parent-y")
        assert self.service._are_same_lineage(a, b) is False

    def test_both_no_parents(self):
        a = _make_agent(agent_id="a-1")
        b = _make_agent(agent_id="b-1")
        assert self.service._are_same_lineage(a, b) is False


# ---------------------------------------------------------------------------
# Tests: clone_agent
# ---------------------------------------------------------------------------

class TestCloneAgent:
    """Tests for AgentEvolutionService.clone_agent with real DB."""

    @pytest.mark.asyncio
    async def test_clone_creates_child_in_db(self, db_session: AsyncSession):
        parent = _make_agent(agent_id="parent-clone-1", fitness=80.0, generation=3, level=2)
        parent.assigned_patterns = {
            "base": [
                {
                    "pattern_id": "p1",
                    "entry_conditions": [{"indicator": "rsi", "operator": "<", "value": 30}],
                    "exit_conditions": [{"indicator": "rsi", "operator": ">", "value": 70}],
                }
            ]
        }
        db_session.add(parent)
        await db_session.flush()

        service = AgentEvolutionService()
        with patch(
            "Fast_Swarm.local_agents.core.genesis.spawn_agent",
            side_effect=_fake_spawn_agent,
        ), patch(
            "Fast_Swarm.local_agents.core.state.AgentDatabase",
            return_value=MagicMock(),
        ):
            child_id = await service.clone_agent(db_session, "parent-clone-1", mutation_rate=0.1)

        # Verify child exists
        result = await db_session.exec(select(Agent).where(Agent.agent_id == child_id))
        child = result.first()
        assert child is not None
        assert child.generation == 4  # parent gen + 1
        assert child.parent_a_id == "parent-clone-1"
        assert child.status == "active"
        assert child.level == 1  # child starts at level 1

    @pytest.mark.asyncio
    async def test_clone_levels_up_parent(self, db_session: AsyncSession):
        parent = _make_agent(agent_id="parent-level", level=3)
        db_session.add(parent)
        await db_session.flush()

        service = AgentEvolutionService()
        with patch(
            "Fast_Swarm.local_agents.core.genesis.spawn_agent",
            side_effect=_fake_spawn_agent,
        ), patch(
            "Fast_Swarm.local_agents.core.state.AgentDatabase",
            return_value=MagicMock(),
        ):
            await service.clone_agent(db_session, "parent-level")

        # Re-fetch parent
        result = await db_session.exec(select(Agent).where(Agent.agent_id == "parent-level"))
        parent_refreshed = result.first()
        assert parent_refreshed.level == 4  # was 3, now 4

    @pytest.mark.asyncio
    async def test_clone_mutates_traits(self, db_session: AsyncSession):
        custom_traits = _default_traits()
        custom_traits["risk_tolerance"] = 0.8
        parent = _make_agent(agent_id="parent-mut", traits=custom_traits)
        db_session.add(parent)
        await db_session.flush()

        service = AgentEvolutionService()
        with patch(
            "Fast_Swarm.local_agents.core.genesis.spawn_agent",
            side_effect=_fake_spawn_agent,
        ), patch(
            "Fast_Swarm.local_agents.core.state.AgentDatabase",
            return_value=MagicMock(),
        ):
            child_id = await service.clone_agent(db_session, "parent-mut", mutation_rate=0.2)

        result = await db_session.exec(select(Agent).where(Agent.agent_id == child_id))
        child = result.first()
        # Traits should be mutated but still in [0, 1] range
        for key, val in child.traits.items():
            if isinstance(val, (int, float)):
                assert 0.0 <= val <= 1.0, f"Trait {key}={val} out of range"

    @pytest.mark.asyncio
    async def test_clone_nonexistent_parent_raises(self, db_session: AsyncSession):
        service = AgentEvolutionService()
        with pytest.raises(ValueError, match="not found"):
            await service.clone_agent(db_session, "nonexistent-parent-id")


# ---------------------------------------------------------------------------
# Tests: batch_clone_agents
# ---------------------------------------------------------------------------

class TestBatchCloneAgents:
    """Tests for AgentEvolutionService.batch_clone_agents."""

    @pytest.mark.asyncio
    async def test_batch_clone_multiple_parents(self, db_session: AsyncSession):
        parents = []
        for i in range(3):
            a = _make_agent(agent_id=f"batch-parent-{i}", generation=2, level=1)
            db_session.add(a)
            parents.append(a)
        await db_session.flush()

        service = AgentEvolutionService()
        with patch(
            "Fast_Swarm.local_agents.core.genesis.spawn_agent",
            side_effect=_fake_spawn_agent,
        ), patch(
            "Fast_Swarm.local_agents.core.state.AgentDatabase",
            return_value=MagicMock(),
        ):
            cloned_ids, failures = await service.batch_clone_agents(db_session, parents, mutation_rate=0.1)

        assert len(cloned_ids) == 3
        assert len(failures) == 0
        # All parents should have leveled up
        for p in parents:
            assert p.level == 2

    @pytest.mark.asyncio
    async def test_batch_clone_single_commit(self, db_session: AsyncSession):
        """Batch clone uses a single commit, not N commits."""
        parents = []
        for i in range(5):
            a = _make_agent(agent_id=f"batch-single-{i}")
            db_session.add(a)
            parents.append(a)
        await db_session.flush()

        service = AgentEvolutionService()
        with patch(
            "Fast_Swarm.local_agents.core.genesis.spawn_agent",
            side_effect=_fake_spawn_agent,
        ), patch(
            "Fast_Swarm.local_agents.core.state.AgentDatabase",
            return_value=MagicMock(),
        ):
            cloned_ids, failures = await service.batch_clone_agents(db_session, parents)

        # Verify all 5 children exist in DB
        result = await db_session.exec(select(Agent).where(Agent.agent_id.in_(cloned_ids)))
        children = result.all()
        assert len(children) == 5

    @pytest.mark.asyncio
    async def test_batch_clone_partial_failure(self, db_session: AsyncSession):
        """If one parent fails, others should still succeed."""
        parents = [
            _make_agent(agent_id="good-parent-1"),
            _make_agent(agent_id="good-parent-2"),
        ]
        for p in parents:
            db_session.add(p)
        await db_session.flush()

        call_count = 0

        def _spawn_with_failure(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Simulated failure")
            return _fake_spawn_agent(**kwargs)

        service = AgentEvolutionService()
        with patch(
            "Fast_Swarm.local_agents.core.genesis.spawn_agent",
            side_effect=_spawn_with_failure,
        ), patch(
            "Fast_Swarm.local_agents.core.state.AgentDatabase",
            return_value=MagicMock(),
        ):
            cloned_ids, failures = await service.batch_clone_agents(db_session, parents)

        assert len(cloned_ids) == 1
        assert len(failures) == 1
        assert failures[0]["error_type"] == "RuntimeError"


# ---------------------------------------------------------------------------
# Tests: crossover_agents
# ---------------------------------------------------------------------------

class TestCrossoverAgents:
    """Tests for AgentEvolutionService.crossover_agents."""

    @pytest.mark.asyncio
    async def test_crossover_creates_child(self, db_session: AsyncSession):
        parent_a = _make_agent(agent_id="xover-a", generation=2, parent_a_id="root-a")
        parent_b = _make_agent(agent_id="xover-b", generation=3, parent_a_id="root-b")
        db_session.add(parent_a)
        db_session.add(parent_b)
        await db_session.flush()

        service = AgentEvolutionService()
        with patch(
            "Fast_Swarm.local_agents.core.genesis.spawn_agent",
            side_effect=_fake_spawn_agent,
        ), patch(
            "Fast_Swarm.local_agents.core.state.AgentDatabase",
            return_value=MagicMock(),
        ):
            child_id = await service.crossover_agents(
                db_session,
                parent_a=parent_a,
                parent_b=parent_b,
            )

        result = await db_session.exec(select(Agent).where(Agent.agent_id == child_id))
        child = result.first()
        assert child is not None
        assert child.generation == 4  # max(2, 3) + 1
        assert child.level == 1

    @pytest.mark.asyncio
    async def test_crossover_levels_up_both_parents(self, db_session: AsyncSession):
        parent_a = _make_agent(agent_id="xlvl-a", level=2, parent_a_id="root-x")
        parent_b = _make_agent(agent_id="xlvl-b", level=5, parent_a_id="root-y")
        db_session.add(parent_a)
        db_session.add(parent_b)
        await db_session.flush()

        service = AgentEvolutionService()
        with patch(
            "Fast_Swarm.local_agents.core.genesis.spawn_agent",
            side_effect=_fake_spawn_agent,
        ), patch(
            "Fast_Swarm.local_agents.core.state.AgentDatabase",
            return_value=MagicMock(),
        ):
            await service.crossover_agents(db_session, parent_a=parent_a, parent_b=parent_b)

        assert parent_a.level == 3
        assert parent_b.level == 6

    @pytest.mark.asyncio
    async def test_crossover_same_lineage_rejected(self, db_session: AsyncSession):
        parent = _make_agent(agent_id="lineage-parent")
        child = _make_agent(agent_id="lineage-child", parent_a_id="lineage-parent")
        db_session.add(parent)
        db_session.add(child)
        await db_session.flush()

        service = AgentEvolutionService()
        with pytest.raises(ValueError, match="same lineage"):
            await service.crossover_agents(
                db_session,
                parent_a=parent,
                parent_b=child,
            )

    @pytest.mark.asyncio
    async def test_crossover_traits_in_range(self, db_session: AsyncSession):
        traits_a = _default_traits()
        traits_a["risk_tolerance"] = 0.9
        traits_b = _default_traits()
        traits_b["risk_tolerance"] = 0.1

        parent_a = _make_agent(agent_id="trait-a", traits=traits_a, parent_a_id="root-1")
        parent_b = _make_agent(agent_id="trait-b", traits=traits_b, parent_a_id="root-2")
        db_session.add(parent_a)
        db_session.add(parent_b)
        await db_session.flush()

        service = AgentEvolutionService()
        with patch(
            "Fast_Swarm.local_agents.core.genesis.spawn_agent",
            side_effect=_fake_spawn_agent,
        ), patch(
            "Fast_Swarm.local_agents.core.state.AgentDatabase",
            return_value=MagicMock(),
        ):
            child_id = await service.crossover_agents(
                db_session, parent_a=parent_a, parent_b=parent_b, noise_rate=0.05,
            )

        result = await db_session.exec(select(Agent).where(Agent.agent_id == child_id))
        child = result.first()
        for key, val in child.traits.items():
            if isinstance(val, (int, float)):
                assert 0.0 <= val <= 1.0, f"Trait {key}={val} out of range"

    @pytest.mark.asyncio
    async def test_crossover_by_id_lookup(self, db_session: AsyncSession):
        """Test crossover using parent IDs instead of objects."""
        parent_a = _make_agent(agent_id="id-lookup-a", parent_a_id="root-la")
        parent_b = _make_agent(agent_id="id-lookup-b", parent_a_id="root-lb")
        db_session.add(parent_a)
        db_session.add(parent_b)
        await db_session.flush()

        service = AgentEvolutionService()
        with patch(
            "Fast_Swarm.local_agents.core.genesis.spawn_agent",
            side_effect=_fake_spawn_agent,
        ), patch(
            "Fast_Swarm.local_agents.core.state.AgentDatabase",
            return_value=MagicMock(),
        ):
            child_id = await service.crossover_agents(
                db_session,
                parent_a_id="id-lookup-a",
                parent_b_id="id-lookup-b",
            )

        result = await db_session.exec(select(Agent).where(Agent.agent_id == child_id))
        child = result.first()
        assert child is not None


# ---------------------------------------------------------------------------
# Tests: evolve_generation (full 4-phase cycle)
# ---------------------------------------------------------------------------

class TestEvolveGeneration:
    """Tests for AgentEvolutionService.evolve_generation."""

    @pytest.mark.asyncio
    async def test_evolve_returns_correct_keys(self, db_session: AsyncSession):
        """evolve_generation returns a dict with all expected keys."""
        # Seed agents: need at least a few with varying fitness
        agents = await _seed_agents(db_session, count=10, fitness_start=10.0)

        service = AgentEvolutionService()
        with patch(
            "Fast_Swarm.local_agents.core.genesis.spawn_agent",
            side_effect=_fake_spawn_agent,
        ), patch(
            "Fast_Swarm.local_agents.core.state.AgentDatabase",
            return_value=MagicMock(),
        ):
            result = await service.evolve_generation(
                db_session,
                promotion_percentile=0.3,
                retirement_percentile=0.2,
            )

        expected_keys = {
            "promoted_count", "cloned_count", "clone_failures",
            "crossbred_count", "crossover_failures", "lineage_skips",
            "culled_count", "cloned_ids", "crossbred_ids", "culled_ids",
            "failure_details",
        }
        assert expected_keys.issubset(set(result.keys()))

    @pytest.mark.asyncio
    async def test_evolve_clones_top_agents(self, db_session: AsyncSession):
        """Top agents should be cloned."""
        agents = await _seed_agents(db_session, count=10, fitness_start=10.0)

        service = AgentEvolutionService()
        with patch(
            "Fast_Swarm.local_agents.core.genesis.spawn_agent",
            side_effect=_fake_spawn_agent,
        ), patch(
            "Fast_Swarm.local_agents.core.state.AgentDatabase",
            return_value=MagicMock(),
        ):
            result = await service.evolve_generation(
                db_session,
                promotion_percentile=0.3,
                retirement_percentile=0.2,
            )

        # Top 30% of 10 = 3 agents promoted/cloned
        assert result["promoted_count"] == 3
        assert result["cloned_count"] == 3

    @pytest.mark.asyncio
    async def test_evolve_with_no_agents(self, db_session: AsyncSession):
        """Evolution with empty population should not crash."""
        service = AgentEvolutionService()
        result = await service.evolve_generation(db_session)
        assert result["promoted_count"] == 0
        assert result["cloned_count"] == 0
        assert result["culled_count"] == 0


# ---------------------------------------------------------------------------
# Tests: module-level functions
# ---------------------------------------------------------------------------

class TestModuleLevelFunctions:
    """Tests for module-level evolution state functions."""

    def test_reset_evolution_flag(self):
        import Fast_Swarm.Agents.Services.evolution_service as mod
        mod._active_evolution_run = True
        reset_evolution_flag()
        assert mod._active_evolution_run is False

    def test_get_evolution_status_idle(self):
        import Fast_Swarm.Agents.Services.evolution_service as mod
        mod._active_evolution_run = False
        mod._last_evolution_result = None
        status = get_evolution_status()
        assert status["is_running"] is False
        assert status["last_result"] is None

    def test_get_evolution_status_running(self):
        import Fast_Swarm.Agents.Services.evolution_service as mod
        mod._active_evolution_run = True
        mod._last_evolution_result = {"run_id": "test", "status": "completed"}
        status = get_evolution_status()
        assert status["is_running"] is True
        assert status["last_result"]["run_id"] == "test"
        # Cleanup
        mod._active_evolution_run = False
        mod._last_evolution_result = None
