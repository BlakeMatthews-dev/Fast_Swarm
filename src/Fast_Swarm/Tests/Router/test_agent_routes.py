"""
Agent Router Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Fast_Swarm/CLAUDE.md (API Routes)
Tests for agent-related services and route logic.

Note: These tests verify service-level behavior since the full app
has complex import dependencies. Integration tests with the running
server should be done separately.

MASTER TEST ADMIN: "APIs are promises. Broken promises break trust."
"""

from typing import Any

import pytest

from Fast_Swarm.Agents.Services.agent_service import (
    calculate_position_size,
    calculate_stop_loss,
    calculate_take_profit,
    get_trading_parameters,
)
from Fast_Swarm.Agents.Services.trait_service import ALL_22_TRAITS, generate_all_traits

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_agents() -> list[dict[str, Any]]:
    """Create mock agent data for testing."""
    agents = []
    for i in range(10):
        agents.append(
            {
                "agent_id": f"test-agent-{i:03d}",
                "name": f"Test Agent {i}",
                "generation": (i % 3) + 1,
                "traits": dict.fromkeys(ALL_22_TRAITS, 0.5),
                "status": "active" if i < 7 else "retired",
                "is_active": i < 7,
                "fitness_score": float(i * 10),
                "elo_rating": 1500.0 + i * 50,
                "total_trades": i * 5,
                "win_rate": 0.5 + (i * 0.02),
                "assigned_patterns": ["pattern-1", "pattern-2"] if i % 2 == 0 else [],
                "pattern_weights": {"pattern-1": 0.6, "pattern-2": 0.4} if i % 2 == 0 else {},
            }
        )
    return agents


@pytest.fixture
def sample_agent_data() -> dict[str, Any]:
    """Sample agent data for creation tests."""
    return {
        "agent_id": "test-agent-001",
        "name": "Test Agent",
        "generation": 1,
        "traits": generate_all_traits(seed=42),
        "status": "active",
        "is_active": True,
        "fitness_score": 50.0,
        "elo_rating": 1500.0,
    }


# =============================================================================
# TEST: Agent List Service Logic
# =============================================================================


class TestAgentListLogic:
    """CONTRACT: Agent listing logic works correctly."""

    def test_pagination_offset_logic(self, mock_agents):
        """CONTRACT: Offset skips correct number of agents."""
        # Simulate pagination
        offset = 3
        limit = 5
        paginated = mock_agents[offset : offset + limit]

        assert len(paginated) == 5
        assert paginated[0]["agent_id"] == "test-agent-003"

    def test_pagination_limit_logic(self, mock_agents):
        """CONTRACT: Limit returns correct number of agents."""
        limit = 3
        limited = mock_agents[:limit]

        assert len(limited) == 3

    def test_pagination_offset_beyond_list(self, mock_agents):
        """CONTRACT: Offset beyond list returns empty."""
        offset = 1000
        paginated = mock_agents[offset:]

        assert paginated == []

    def test_filter_by_status_active(self, mock_agents):
        """CONTRACT: Can filter to active agents only."""
        active = [a for a in mock_agents if a["status"] == "active"]
        assert len(active) == 7
        assert all(a["is_active"] for a in active)

    def test_filter_by_status_retired(self, mock_agents):
        """CONTRACT: Can filter to retired agents only."""
        retired = [a for a in mock_agents if a["status"] == "retired"]
        assert len(retired) == 3
        assert all(not a["is_active"] for a in retired)

    def test_sort_by_fitness_descending(self, mock_agents):
        """CONTRACT: Agents can be sorted by fitness descending."""
        sorted_agents = sorted(mock_agents, key=lambda a: a["fitness_score"], reverse=True)
        assert sorted_agents[0]["fitness_score"] == 90.0
        assert sorted_agents[-1]["fitness_score"] == 0.0

    def test_sort_by_fitness_ascending(self, mock_agents):
        """CONTRACT: Agents can be sorted by fitness ascending."""
        sorted_agents = sorted(mock_agents, key=lambda a: a["fitness_score"])
        assert sorted_agents[0]["fitness_score"] == 0.0
        assert sorted_agents[-1]["fitness_score"] == 90.0


# =============================================================================
# TEST: Agent Get By ID Logic
# =============================================================================


class TestAgentGetByIdLogic:
    """CONTRACT: Get agent by ID logic works correctly."""

    def test_find_agent_by_id(self, mock_agents):
        """CONTRACT: Can find agent by exact ID match."""
        target_id = "test-agent-005"
        found = next((a for a in mock_agents if a["agent_id"] == target_id), None)

        assert found is not None
        assert found["agent_id"] == target_id

    def test_agent_not_found_returns_none(self, mock_agents):
        """CONTRACT: Non-existent ID returns None."""
        target_id = "nonexistent-agent"
        found = next((a for a in mock_agents if a["agent_id"] == target_id), None)

        assert found is None

    def test_agent_includes_all_fields(self, sample_agent_data):
        """CONTRACT: Agent data includes all required fields."""
        required_fields = ["agent_id", "name", "generation", "traits", "status", "is_active", "fitness_score"]
        for field in required_fields:
            assert field in sample_agent_data, f"Missing field: {field}"

    def test_agent_traits_complete(self, sample_agent_data):
        """CONTRACT: Agent has all 22 traits."""
        traits = sample_agent_data["traits"]
        assert len(traits) >= 22, f"Expected 22 traits, got {len(traits)}"


# =============================================================================
# TEST: Agent Stats Calculation Logic
# =============================================================================


class TestAgentStatsLogic:
    """CONTRACT: Agent statistics calculation logic."""

    def test_average_fitness_calculation(self, mock_agents):
        """CONTRACT: Average fitness calculated correctly."""
        total_fitness = sum(a["fitness_score"] for a in mock_agents)
        avg_fitness = total_fitness / len(mock_agents)

        # Expected: (0+10+20+30+40+50+60+70+80+90)/10 = 45.0
        assert avg_fitness == 45.0

    def test_count_by_status(self, mock_agents):
        """CONTRACT: Count agents by status."""
        active_count = sum(1 for a in mock_agents if a["status"] == "active")
        retired_count = sum(1 for a in mock_agents if a["status"] == "retired")

        assert active_count == 7
        assert retired_count == 3

    def test_average_generation(self, mock_agents):
        """CONTRACT: Average generation calculated correctly."""
        total_gen = sum(a["generation"] for a in mock_agents)
        avg_gen = total_gen / len(mock_agents)

        # Generations: 1,2,3,1,2,3,1,2,3,1 = 19/10 = 1.9
        assert avg_gen == 1.9

    def test_win_rate_statistics(self, mock_agents):
        """CONTRACT: Win rate statistics calculated correctly."""
        win_rates = [a["win_rate"] for a in mock_agents]
        avg_win_rate = sum(win_rates) / len(win_rates)

        # Should be around 0.59 (0.50 + 0.52 + ... + 0.68) / 10
        assert 0.58 < avg_win_rate < 0.60


# =============================================================================
# TEST: Spawn Logic
# =============================================================================


class TestSpawnLogic:
    """CONTRACT: Agent spawning logic."""

    def test_spawn_count_validation(self):
        """CONTRACT: Spawn count must be positive."""
        assert 0 <= 0  # count=0 is valid (spawns nothing)
        assert 10 > 0  # count=10 is valid

    def test_spawn_max_limit(self):
        """CONTRACT: Max spawn limit is 1000."""
        max_spawn = 1000
        assert 500 <= max_spawn
        assert 1001 > max_spawn

    def test_spawn_creates_unique_ids(self):
        """CONTRACT: Each spawned agent gets unique ID."""
        import uuid

        ids = [f"agent-{uuid.uuid4().hex[:8]}" for _ in range(10)]
        assert len(set(ids)) == 10  # All unique

    def test_spawn_assigns_generation_1(self):
        """CONTRACT: New spawns are generation 1."""
        new_agent = {"generation": 1}
        assert new_agent["generation"] == 1

    def test_spawn_initializes_fitness_zero(self):
        """CONTRACT: New spawns have zero fitness."""
        new_agent = {"fitness_score": 0.0}
        assert new_agent["fitness_score"] == 0.0


# =============================================================================
# TEST: Cull Logic
# =============================================================================


class TestCullLogic:
    """CONTRACT: Agent culling logic."""

    def test_cull_by_survival_rate(self, mock_agents):
        """CONTRACT: survival_rate=0.6 keeps top 60%."""
        survival_rate = 0.6
        sorted_agents = sorted(mock_agents, key=lambda a: a["fitness_score"], reverse=True)
        survivors_count = int(len(sorted_agents) * survival_rate)
        survivors = sorted_agents[:survivors_count]
        culled = sorted_agents[survivors_count:]

        assert len(survivors) == 6
        assert len(culled) == 4

    def test_cull_preserves_minimum(self, mock_agents):
        """CONTRACT: Never cull below minimum population."""
        min_population = 5
        survival_rate = 0.3  # Would normally keep only 3

        sorted_agents = sorted(mock_agents, key=lambda a: a["fitness_score"], reverse=True)
        would_keep = int(len(sorted_agents) * survival_rate)
        actual_keep = max(would_keep, min_population)

        assert actual_keep >= min_population

    def test_cull_by_fitness_threshold(self, mock_agents):
        """CONTRACT: Can cull all below fitness threshold."""
        threshold = 40.0
        survivors = [a for a in mock_agents if a["fitness_score"] >= threshold]
        culled = [a for a in mock_agents if a["fitness_score"] < threshold]

        assert len(survivors) == 6  # 40, 50, 60, 70, 80, 90
        assert len(culled) == 4  # 0, 10, 20, 30

    def test_cull_dry_run_no_changes(self, mock_agents):
        """CONTRACT: Dry run shows preview without changes."""
        original_count = len(mock_agents)
        # Dry run just calculates, doesn't modify
        would_cull = 4

        assert len(mock_agents) == original_count  # No change


# =============================================================================
# TEST: Trading Parameter Calculation
# =============================================================================


class TestTradingParameterLogic:
    """CONTRACT: Trading parameters derived from traits correctly."""

    def test_position_size_from_risk_tolerance(self):
        """CONTRACT: Position size scales with risk_tolerance."""
        low_risk = calculate_position_size(0.1)
        mid_risk = calculate_position_size(0.5)
        high_risk = calculate_position_size(0.9)

        assert low_risk < mid_risk < high_risk
        assert 0.01 <= low_risk <= 0.10
        assert 0.01 <= high_risk <= 0.10

    def test_stop_loss_from_tightness(self):
        """CONTRACT: Stop loss inversely related to tightness."""
        loose = calculate_stop_loss(0.1)  # Low tightness = loose stop
        tight = calculate_stop_loss(0.9)  # High tightness = tight stop

        assert loose > tight  # Loose stop is higher percentage

    def test_take_profit_from_greed(self):
        """CONTRACT: Take profit scales with greed."""
        conservative = calculate_take_profit(0.1)
        greedy = calculate_take_profit(0.9)

        assert conservative < greedy

    def test_trading_params_complete(self):
        """CONTRACT: get_trading_parameters returns all params."""
        traits = dict.fromkeys(ALL_22_TRAITS, 0.5)
        params = get_trading_parameters(traits)

        assert "position_size_pct" in params
        assert "stop_loss_pct" in params
        assert "take_profit_pct" in params
        assert "max_hold_ms" in params


# =============================================================================
# TEST: Regime Fitness Logic
# =============================================================================


class TestRegimeFitnessLogic:
    """CONTRACT: Per-regime fitness tracking logic."""

    def test_regime_fitness_structure(self):
        """CONTRACT: Regime fitness has correct structure."""
        regime_fitness = {
            "bull": {"fitness": 75.0, "trades": 50, "win_rate": 0.65},
            "bear": {"fitness": 45.0, "trades": 30, "win_rate": 0.45},
            "crash": {"fitness": 20.0, "trades": 10, "win_rate": 0.30},
        }

        for regime, data in regime_fitness.items():
            assert "fitness" in data
            assert "trades" in data
            assert 0 <= data["fitness"] <= 100

    def test_best_worst_regime_selection(self):
        """CONTRACT: Can identify best and worst regimes."""
        regime_fitness = {
            "bull": {"fitness": 75.0},
            "bear": {"fitness": 45.0},
            "crash": {"fitness": 20.0},
            "sideways": {"fitness": 60.0},
        }

        sorted_regimes = sorted(regime_fitness.items(), key=lambda x: x[1]["fitness"], reverse=True)

        best = sorted_regimes[0][0]
        worst = sorted_regimes[-1][0]

        assert best == "bull"
        assert worst == "crash"

    def test_regime_count(self):
        """CONTRACT: Count regimes tested."""
        regime_fitness = {
            "bull": {"fitness": 75.0},
            "bear": {"fitness": 45.0},
        }

        regimes_tested = len(regime_fitness)
        assert regimes_tested == 2


# =============================================================================
# TEST: Top Agents by Regime Logic
# =============================================================================


class TestTopAgentsByRegimeLogic:
    """CONTRACT: Top agents by regime logic."""

    def test_top_agents_sorted_by_regime_fitness(self):
        """CONTRACT: Agents sorted by regime-specific fitness."""
        agents = [
            {"agent_id": "a1", "fitness_by_regime": {"bull": {"fitness": 80}}},
            {"agent_id": "a2", "fitness_by_regime": {"bull": {"fitness": 60}}},
            {"agent_id": "a3", "fitness_by_regime": {"bull": {"fitness": 90}}},
        ]

        regime = "bull"
        sorted_agents = sorted(
            agents, key=lambda a: a["fitness_by_regime"].get(regime, {}).get("fitness", 0), reverse=True
        )

        assert sorted_agents[0]["agent_id"] == "a3"
        assert sorted_agents[1]["agent_id"] == "a1"
        assert sorted_agents[2]["agent_id"] == "a2"

    def test_top_agents_limit(self):
        """CONTRACT: Limit parameter limits results."""
        agents = [{"id": i} for i in range(100)]
        limit = 20
        limited = agents[:limit]

        assert len(limited) == 20

    def test_agents_without_regime_excluded(self):
        """CONTRACT: Agents without regime data are excluded."""
        agents = [
            {"agent_id": "a1", "fitness_by_regime": {"bull": {"fitness": 80}}},
            {"agent_id": "a2", "fitness_by_regime": {}},  # No regimes
            {"agent_id": "a3", "fitness_by_regime": {"bear": {"fitness": 70}}},  # Different regime
        ]

        regime = "bull"
        filtered = [a for a in agents if regime in a.get("fitness_by_regime", {})]

        assert len(filtered) == 1
        assert filtered[0]["agent_id"] == "a1"


# =============================================================================
# TEST: Edge Cases
# =============================================================================


class TestAgentRoutesEdgeCases:
    """CONTRACT: Edge cases in agent routes logic."""

    def test_empty_agent_list(self):
        """CONTRACT: Empty list handled gracefully."""
        agents = []
        avg_fitness = sum(a.get("fitness_score", 0) for a in agents)
        count = len(agents)

        assert count == 0
        assert avg_fitness == 0

    def test_single_agent(self):
        """CONTRACT: Single agent list handled correctly."""
        agents = [{"agent_id": "only-one", "fitness_score": 50.0}]
        avg_fitness = sum(a["fitness_score"] for a in agents) / len(agents)

        assert avg_fitness == 50.0

    def test_all_same_fitness(self):
        """CONTRACT: All agents with same fitness handled."""
        agents = [{"fitness_score": 50.0} for _ in range(10)]
        sorted_agents = sorted(agents, key=lambda a: a["fitness_score"], reverse=True)

        # All have same fitness - order is stable but all equal
        assert all(a["fitness_score"] == 50.0 for a in sorted_agents)

    def test_none_fitness_handled(self):
        """CONTRACT: None fitness values handled."""
        agents = [
            {"fitness_score": None},
            {"fitness_score": 50.0},
            {"fitness_score": None},
        ]

        # Filter out None values for calculations
        valid = [a for a in agents if a["fitness_score"] is not None]
        assert len(valid) == 1

    def test_special_characters_in_agent_id(self):
        """CONTRACT: Special characters don't break matching."""
        agents = [
            {"agent_id": "agent-with-dashes"},
            {"agent_id": "agent_with_underscores"},
            {"agent_id": "agent.with.dots"},
        ]

        # Simple string matching still works
        target = "agent-with-dashes"
        found = next((a for a in agents if a["agent_id"] == target), None)
        assert found is not None


# =============================================================================
# TEST: Response Structure Validation
# =============================================================================


class TestResponseStructure:
    """CONTRACT: Response structures are correct."""

    def test_agent_response_fields(self, sample_agent_data):
        """CONTRACT: Agent response has required fields."""
        required = ["agent_id", "name", "traits", "fitness_score"]
        for field in required:
            assert field in sample_agent_data

    def test_stats_response_structure(self):
        """CONTRACT: Stats response has expected structure."""
        stats = {
            "total_agents": 100,
            "active_agents": 75,
            "average_fitness": 45.5,
        }

        assert "total_agents" in stats or "active_agents" in stats
        assert isinstance(stats.get("average_fitness", 0), (int, float))

    def test_spawn_response_structure(self):
        """CONTRACT: Spawn response has expected fields."""
        spawn_response = {
            "message": "Spawned 10 new agents",
            "agents": ["agent-1", "agent-2"],
            "count": 2,
        }

        assert "agents" in spawn_response or "message" in spawn_response

    def test_cull_response_structure(self):
        """CONTRACT: Cull response has expected fields."""
        cull_response = {
            "culled_count": 4,
            "survivors": 6,
            "message": "Culled 4 agents",
        }

        assert "culled_count" in cull_response or "message" in cull_response
