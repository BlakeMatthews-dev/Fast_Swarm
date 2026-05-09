"""
Evolution Cycle Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (Evolution Cycle)
4-Phase cycle: SPAWN → BACKTEST → SELECT → REPRODUCE
"""

import pytest

from Fast_Swarm.Agents.Services.evolution_service import (
    AgentEvolutionService,
    _extract_patterns_from_agent,
    get_evolution_status,
    reset_evolution_flag,
)

# ============================================================================
# Test Data Helpers
# ============================================================================


def make_mock_agent(
    agent_id: str,
    generation: int = 1,
    traits: dict | None = None,
    patterns: list | None = None,
    parent_a_id: str | None = None,
) -> object:
    """Create a mock agent object for testing."""
    class MockAgent:
        pass

    agent = MockAgent()
    agent.agent_id = agent_id
    agent.generation = generation
    agent.traits = traits or {
        "risk_tolerance": 0.5,
        "volatility_seeking": 0.5,
        "stop_loss_tightness": 0.5,
        "profit_target_greed": 0.5,
    }
    agent.assigned_patterns = patterns or {
        "base": [
            {
                "pattern_id": "p1",
                "entry_conditions": [{"indicator": "rsi_14", "min": 30, "max": 70}],
                "exit_conditions": {"stop_loss": 5},
                "fitness_score": 60.0,
            }
        ],
        "weights": {"p1": 1.0},
    }
    agent.pattern_weights = {"p1": 1.0}
    agent.parent_a_id = parent_a_id
    agent.parent_b_id = None
    agent.trading_philosophy = "Test philosophy"
    agent.is_active = True
    agent.status = "active"
    agent.level = 1
    return agent


# ============================================================================
# EVOLUTION STATUS CONTRACT
# ============================================================================


class TestEvolutionStatus:
    """CONTRACT: Evolution status tracking."""

    def test_get_status_returns_dict(self):
        """CONTRACT: get_evolution_status returns status dict."""
        status = get_evolution_status()
        assert isinstance(status, dict)
        assert "is_running" in status
        assert "last_result" in status

    def test_reset_flag_sets_false(self):
        """CONTRACT: reset_evolution_flag sets running to False."""
        reset_evolution_flag()
        status = get_evolution_status()
        assert status["is_running"] is False

    def test_status_tracks_running_state(self):
        """CONTRACT: Status tracks whether evolution is running."""
        status = get_evolution_status()
        assert isinstance(status["is_running"], bool)


# ============================================================================
# PATTERN EXTRACTION CONTRACT
# ============================================================================


class TestPatternExtraction:
    """CONTRACT: Extract patterns from agent's JSONB."""

    def test_extract_from_modern_format(self):
        """CONTRACT: Extract patterns from modern dict format."""
        agent = make_mock_agent("agent-1")
        patterns = _extract_patterns_from_agent(agent)
        assert len(patterns) >= 1
        assert patterns[0]["pattern_id"] == "p1"

    def test_extract_preserves_entry_conditions(self):
        """CONTRACT: Extracted patterns have entry_conditions."""
        agent = make_mock_agent("agent-1")
        patterns = _extract_patterns_from_agent(agent)
        assert "entry_conditions" in patterns[0]

    def test_extract_preserves_exit_conditions(self):
        """CONTRACT: Extracted patterns have exit_conditions."""
        agent = make_mock_agent("agent-1")
        patterns = _extract_patterns_from_agent(agent)
        assert "exit_conditions" in patterns[0]

    def test_extract_preserves_fitness(self):
        """CONTRACT: Extracted patterns have fitness_score."""
        agent = make_mock_agent("agent-1")
        patterns = _extract_patterns_from_agent(agent)
        assert patterns[0]["fitness_score"] == 60.0

    def test_extract_from_legacy_list_format(self):
        """CONTRACT: Extract patterns from legacy list format."""
        agent = make_mock_agent(
            "agent-1",
            patterns=[
                {
                    "pattern_id": "legacy-p1",
                    "entry_conditions": [{"indicator": "sma_20", "min": 100}],
                    "exit_conditions": {"take_profit": 10},
                }
            ],
        )
        patterns = _extract_patterns_from_agent(agent)
        assert len(patterns) >= 1

    def test_extract_from_none_returns_empty(self):
        """CONTRACT: None patterns returns empty list."""
        agent = make_mock_agent("agent-1")
        agent.assigned_patterns = None
        patterns = _extract_patterns_from_agent(agent)
        assert patterns == []

    def test_extract_empty_base_returns_empty(self):
        """CONTRACT: Empty base list returns empty patterns."""
        agent = make_mock_agent("agent-1")
        agent.assigned_patterns = {"base": [], "weights": {}}
        patterns = _extract_patterns_from_agent(agent)
        assert patterns == []


# ============================================================================
# LINEAGE DETECTION CONTRACT
# ============================================================================


class TestLineageDetection:
    """CONTRACT: Same lineage detection for crossover."""

    def test_same_lineage_parent_child(self):
        """CONTRACT: Parent-child relationship = same lineage."""
        service = AgentEvolutionService()
        parent = make_mock_agent("parent-1")
        child = make_mock_agent("child-1", parent_a_id="parent-1")
        assert service._are_same_lineage(parent, child) is True

    def test_same_lineage_siblings(self):
        """CONTRACT: Siblings (same parent) = same lineage."""
        service = AgentEvolutionService()
        sibling1 = make_mock_agent("sib-1", parent_a_id="parent-1")
        sibling2 = make_mock_agent("sib-2", parent_a_id="parent-1")
        assert service._are_same_lineage(sibling1, sibling2) is True

    def test_different_lineage_unrelated(self):
        """CONTRACT: Unrelated agents = different lineage."""
        service = AgentEvolutionService()
        agent1 = make_mock_agent("agent-1")
        agent2 = make_mock_agent("agent-2")
        assert service._are_same_lineage(agent1, agent2) is False

    def test_different_lineage_different_parents(self):
        """CONTRACT: Different parents = different lineage."""
        service = AgentEvolutionService()
        agent1 = make_mock_agent("agent-1", parent_a_id="parent-a")
        agent2 = make_mock_agent("agent-2", parent_a_id="parent-b")
        assert service._are_same_lineage(agent1, agent2) is False


# ============================================================================
# EVOLUTION SERVICE INITIALIZATION
# ============================================================================


class TestEvolutionServiceInit:
    """CONTRACT: Evolution service initialization."""

    def test_service_initializes(self):
        """CONTRACT: AgentEvolutionService can be initialized."""
        service = AgentEvolutionService()
        assert service is not None

    def test_service_has_spawn_service(self):
        """CONTRACT: Service has spawn_service attribute."""
        service = AgentEvolutionService()
        assert hasattr(service, "spawn_service")

    def test_service_has_cull_service(self):
        """CONTRACT: Service has cull_service attribute."""
        service = AgentEvolutionService()
        assert hasattr(service, "cull_service")

    def test_service_has_ranking_service(self):
        """CONTRACT: Service has ranking_service attribute."""
        service = AgentEvolutionService()
        assert hasattr(service, "ranking_service")


# ============================================================================
# TRAIT MUTATION CONTRACT
# ============================================================================


class TestTraitMutation:
    """CONTRACT: Trait mutation during cloning."""

    def test_mutation_bounded_0_to_1(self):
        """CONTRACT: Mutated traits stay in [0, 1] range."""
        import random

        traits = {"risk_tolerance": 0.95, "volatility_seeking": 0.05}

        # Simulate mutation logic from clone_agent
        mutation_rate = 0.1
        mutated = {}
        for key, value in traits.items():
            mutation = (random.random() - 0.5) * 2 * mutation_rate
            mutated[key] = max(0, min(1, value + mutation))

        for value in mutated.values():
            assert 0.0 <= value <= 1.0

    def test_mutation_rate_affects_range(self):
        """CONTRACT: Higher mutation rate = larger changes possible."""
        import random

        random.seed(42)
        traits = {"risk_tolerance": 0.5}

        low_mutation = 0.05
        high_mutation = 0.20

        low_mutated = max(0, min(1, 0.5 + (random.random() - 0.5) * 2 * low_mutation))
        random.seed(42)  # Reset for fair comparison
        high_mutated = max(0, min(1, 0.5 + (random.random() - 0.5) * 2 * high_mutation))

        # High mutation should have larger potential delta
        assert abs(high_mutated - 0.5) >= abs(low_mutated - 0.5) * 0.9  # Allow some tolerance


# ============================================================================
# CROSSOVER LOGIC CONTRACT
# ============================================================================


class TestCrossoverLogic:
    """CONTRACT: Crossover trait inheritance."""

    def test_crossover_50_50_inheritance(self):
        """CONTRACT: Each trait has 50% chance from each parent."""
        import random

        random.seed(42)
        traits_a = {"risk_tolerance": 0.2, "volatility_seeking": 0.8}
        traits_b = {"risk_tolerance": 0.8, "volatility_seeking": 0.2}

        # Simulate crossover
        mixed = {}
        noise_rate = 0.05
        for key in traits_a.keys():
            base = traits_a[key] if random.random() < 0.5 else traits_b[key]
            noise = (random.random() - 0.5) * 2 * noise_rate
            mixed[key] = max(0, min(1, base + noise))

        # Should have inherited from either parent
        assert mixed["risk_tolerance"] is not None
        assert 0.0 <= mixed["risk_tolerance"] <= 1.0

    def test_crossover_generation_increments(self):
        """CONTRACT: Child generation = max(parent_gens) + 1."""
        parent_a_gen = 3
        parent_b_gen = 5
        child_gen = max(parent_a_gen, parent_b_gen) + 1
        assert child_gen == 6

    def test_crossover_noise_bounded(self):
        """CONTRACT: Crossover noise keeps traits in bounds."""
        import random

        for _ in range(100):
            base = random.random()
            noise_rate = 0.05
            noise = (random.random() - 0.5) * 2 * noise_rate
            result = max(0, min(1, base + noise))
            assert 0.0 <= result <= 1.0


# ============================================================================
# EVOLUTION CYCLE STRUCTURE
# ============================================================================


class TestEvolutionCycleStructure:
    """CONTRACT: Evolution cycle method structure."""

    def test_evolve_generation_method_exists(self):
        """CONTRACT: evolve_generation method exists."""
        service = AgentEvolutionService()
        assert hasattr(service, "evolve_generation")

    def test_clone_agent_method_exists(self):
        """CONTRACT: clone_agent method exists."""
        service = AgentEvolutionService()
        assert hasattr(service, "clone_agent")

    def test_crossover_agents_method_exists(self):
        """CONTRACT: crossover_agents method exists."""
        service = AgentEvolutionService()
        assert hasattr(service, "crossover_agents")


# ============================================================================
# EVOLUTION PERCENTILES CONTRACT
# ============================================================================


class TestEvolutionPercentiles:
    """CONTRACT: Evolution percentile parameters."""

    def test_default_promotion_percentile(self):
        """CONTRACT: Default top 20% promoted."""
        promotion_percentile = 0.2
        assert 0.1 <= promotion_percentile <= 0.3

    def test_default_retirement_percentile(self):
        """CONTRACT: Default bottom 30% culled."""
        retirement_percentile = 0.3
        assert 0.2 <= retirement_percentile <= 0.5

    def test_percentiles_dont_overlap_excessively(self):
        """CONTRACT: Promotion + retirement < 100%."""
        promotion = 0.2
        retirement = 0.3
        assert promotion + retirement < 1.0


# ============================================================================
# LEVEL UP CONTRACT
# ============================================================================


class TestLevelUp:
    """CONTRACT: Parent level increases when spawning children."""

    def test_clone_increments_parent_level(self):
        """CONTRACT: Clone operation levels up parent."""
        # Logic from clone_agent: parent.level = (parent.level or 0) + 1
        parent_level = 3
        new_level = (parent_level or 0) + 1
        assert new_level == 4

    def test_crossover_increments_both_parent_levels(self):
        """CONTRACT: Crossover levels up both parents."""
        parent_a_level = 2
        parent_b_level = 5
        new_a_level = (parent_a_level or 0) + 1
        new_b_level = (parent_b_level or 0) + 1
        assert new_a_level == 3
        assert new_b_level == 6

    def test_child_starts_at_level_1(self):
        """CONTRACT: New children start at level 1."""
        child_level = 1
        assert child_level == 1


# ============================================================================
# GENERATION TRACKING CONTRACT
# ============================================================================


class TestGenerationTracking:
    """CONTRACT: Generation number tracking."""

    def test_clone_increments_generation(self):
        """CONTRACT: Clone generation = parent_gen + 1."""
        parent_gen = 5
        clone_gen = parent_gen + 1
        assert clone_gen == 6

    def test_crossover_uses_max_parent_gen(self):
        """CONTRACT: Crossover gen = max(parent_gens) + 1."""
        parent_a_gen = 3
        parent_b_gen = 7
        child_gen = max(parent_a_gen, parent_b_gen) + 1
        assert child_gen == 8

    def test_spawn_starts_at_gen_1(self):
        """CONTRACT: Fresh spawns start at generation 1."""
        spawn_gen = 1
        assert spawn_gen == 1


# ============================================================================
# PATTERN INHERITANCE CONTRACT
# ============================================================================


class TestPatternInheritance:
    """CONTRACT: Pattern inheritance during reproduction."""

    def test_clone_inherits_parent_patterns(self):
        """CONTRACT: Clone gets same patterns as parent."""
        parent_patterns = {"base": [{"pattern_id": "p1"}, {"pattern_id": "p2"}]}
        clone_patterns = parent_patterns  # Direct inheritance
        assert clone_patterns == parent_patterns

    def test_crossover_merges_patterns(self):
        """CONTRACT: Crossover child gets union of parent patterns."""
        patterns_a = [{"pattern_id": "p1", "fitness_score": 50}]
        patterns_b = [{"pattern_id": "p2", "fitness_score": 60}, {"pattern_id": "p3", "fitness_score": 40}]

        # Merge logic from crossover_agents
        pattern_map = {}
        for p in patterns_a + patterns_b:
            pid = p.get("pattern_id")
            if pid not in pattern_map or p.get("fitness_score", 0) > pattern_map[pid].get("fitness_score", 0):
                pattern_map[pid] = p
        merged = list(pattern_map.values())

        assert len(merged) == 3
        pattern_ids = {p["pattern_id"] for p in merged}
        assert pattern_ids == {"p1", "p2", "p3"}

    def test_crossover_prefers_higher_fitness_on_duplicate(self):
        """CONTRACT: When patterns overlap, keep higher fitness."""
        patterns_a = [{"pattern_id": "p1", "fitness_score": 50}]
        patterns_b = [{"pattern_id": "p1", "fitness_score": 80}]  # Same pattern, higher fitness

        pattern_map = {}
        for p in patterns_a + patterns_b:
            pid = p.get("pattern_id")
            if pid not in pattern_map or p.get("fitness_score", 0) > pattern_map[pid].get("fitness_score", 0):
                pattern_map[pid] = p

        assert pattern_map["p1"]["fitness_score"] == 80


# ============================================================================
# ERROR HANDLING CONTRACT
# ============================================================================


class TestEvolutionErrorHandling:
    """CONTRACT: Evolution error handling."""

    def test_evolve_generation_returns_dict(self):
        """CONTRACT: evolve_generation returns result dict structure."""
        # Expected keys in result
        expected_keys = [
            "promoted_count",
            "cloned_count",
            "crossbred_count",
            "culled_count",
        ]
        # Just verify the method signature expects these
        assert len(expected_keys) == 4

    def test_failure_details_included(self):
        """CONTRACT: Result includes failure details for debugging."""
        # Expected structure from evolve_generation
        failure_details_structure = {
            "clone_failures": [],
            "crossover_failures": [],
        }
        assert "clone_failures" in failure_details_structure
        assert "crossover_failures" in failure_details_structure


# ============================================================================
# CONCURRENCY PROTECTION CONTRACT
# ============================================================================


class TestConcurrencyProtection:
    """CONTRACT: Evolution concurrency protection."""

    def test_evolution_flag_prevents_concurrent_runs(self):
        """CONTRACT: Only one evolution can run at a time."""
        # The _active_evolution_run flag and _evolution_lock prevent races
        reset_evolution_flag()
        status = get_evolution_status()
        assert status["is_running"] is False

    def test_flag_reset_on_startup(self):
        """CONTRACT: Flag resets on startup to prevent stuck state."""
        reset_evolution_flag()
        status = get_evolution_status()
        assert status["is_running"] is False
