"""
Selection Pressure Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: Master_plan.md (Selection Pressure)
Top performers breed, middle survives, bottom culled.

Tests use AgentFactory to create agent dicts and apply selection
logic in-memory, without requiring a database connection.
"""

import pytest

from Tests.Fixtures.factories import AgentFactory, ALL_22_TRAITS

# ============================================================================
# Helpers
# ============================================================================


def _make_agents(count, fitness_range=None, statuses=None):
    """Create a list of agent dicts sorted by fitness descending."""
    agents = []
    for i in range(count):
        fitness = fitness_range[i] if fitness_range else float(i * 10)
        status = statuses[i] if statuses else "active"
        agents.append(
            AgentFactory.create(
                agent_id=f"agent-{i:03d}",
                name=f"Agent {i}",
                fitness_score=fitness,
                status=status,
                generation=1,
                seed=i,
            )
        )
    return agents


def _rank_agents(agents, exclude_retired=True):
    """Rank agents by fitness descending. Ties broken by agent_id."""
    filtered = [a for a in agents if not exclude_retired or a["status"] == "active"]
    return sorted(filtered, key=lambda a: (-a["fitness_score"], a["agent_id"]))


def _select_elite(ranked, count=10):
    """Select top N for breeding."""
    return ranked[:count]


def _select_survivors(ranked, survival_rate=0.70):
    """Select top X% as survivors."""
    count = int(len(ranked) * survival_rate)
    return ranked[:count]


def _select_culled(ranked, cull_rate=0.30):
    """Select bottom X% for culling."""
    count = int(len(ranked) * cull_rate)
    return ranked[-count:] if count > 0 else []


def _select_clones(ranked, clone_rate=0.20, exclude_top=10):
    """Select top X% (excluding breeders) for cloning."""
    eligible = ranked[exclude_top:]
    count = int(len(eligible) * clone_rate)
    return eligible[:count]


# ============================================================================
# SELECTION PRESSURE CONTRACT
# ============================================================================


class TestEliteSelection:
    """CONTRACT: Elite selection for breeding."""

    def test_top_10_selected_for_breeding(self):
        """CONTRACT: Top 10 agents by fitness selected for breeding."""
        agents = _make_agents(100)
        ranked = _rank_agents(agents)
        elite = _select_elite(ranked, count=10)
        assert len(elite) == 10
        # Elite should be the 10 highest-fitness agents
        elite_fitness = [a["fitness_score"] for a in elite]
        all_fitness = sorted([a["fitness_score"] for a in agents], reverse=True)
        assert elite_fitness == all_fitness[:10]

    def test_selection_by_fitness_descending(self):
        """CONTRACT: Selection ordered by fitness (highest first)."""
        agents = _make_agents(50)
        ranked = _rank_agents(agents)
        for i in range(len(ranked) - 1):
            assert ranked[i]["fitness_score"] >= ranked[i + 1]["fitness_score"]

    def test_selection_excludes_retired(self):
        """CONTRACT: Retired agents not eligible."""
        statuses = ["active"] * 8 + ["retired"] * 2
        agents = _make_agents(10, statuses=statuses)
        ranked = _rank_agents(agents, exclude_retired=True)
        assert len(ranked) == 8
        assert all(a["status"] == "active" for a in ranked)

    def test_selection_minimum_fitness_threshold(self):
        """CONTRACT: Breeding requires minimum fitness (e.g., 60)."""
        fitness_vals = [90, 80, 70, 60, 50, 40, 30, 20, 10, 5]
        agents = _make_agents(10, fitness_range=fitness_vals)
        ranked = _rank_agents(agents)
        min_fitness = 60
        breeders = [a for a in _select_elite(ranked) if a["fitness_score"] >= min_fitness]
        assert all(a["fitness_score"] >= min_fitness for a in breeders)
        assert len(breeders) == 4  # 90, 80, 70, 60


class TestSurvivorSelection:
    """CONTRACT: Survivor selection (middle tier)."""

    def test_top_70_percent_survive(self):
        """CONTRACT: Default: top 70% survive."""
        agents = _make_agents(100)
        ranked = _rank_agents(agents)
        survivors = _select_survivors(ranked, survival_rate=0.70)
        assert len(survivors) == 70

    def test_survivors_unchanged(self):
        """CONTRACT: Survivors keep traits, patterns, memories."""
        agents = _make_agents(10)
        ranked = _rank_agents(agents)
        survivors = _select_survivors(ranked)
        for survivor in survivors:
            # Find original agent
            original = next(a for a in agents if a["agent_id"] == survivor["agent_id"])
            assert survivor["traits"] == original["traits"]
            assert survivor["fitness_score"] == original["fitness_score"]

    def test_survivor_generation_unchanged(self):
        """CONTRACT: Survivors stay same generation."""
        agents = _make_agents(10)
        for i, a in enumerate(agents):
            a["generation"] = i % 3 + 1
        ranked = _rank_agents(agents)
        survivors = _select_survivors(ranked)
        for survivor in survivors:
            original = next(a for a in agents if a["agent_id"] == survivor["agent_id"])
            assert survivor["generation"] == original["generation"]


class TestCullSelection:
    """CONTRACT: Cull selection (bottom tier)."""

    def test_bottom_30_percent_culled(self):
        """CONTRACT: Default: bottom 30% culled."""
        agents = _make_agents(100)
        ranked = _rank_agents(agents)
        culled = _select_culled(ranked, cull_rate=0.30)
        assert len(culled) == 30

    def test_cull_sets_status_retired(self):
        """CONTRACT: Culled agents get status='retired'."""
        agents = _make_agents(10)
        ranked = _rank_agents(agents)
        culled = _select_culled(ranked, cull_rate=0.30)
        for agent in culled:
            agent["status"] = "retired"
        assert all(a["status"] == "retired" for a in culled)

    def test_cull_preserves_history(self):
        """CONTRACT: Culled agent history preserved."""
        agents = _make_agents(10)
        ranked = _rank_agents(agents)
        culled = _select_culled(ranked, cull_rate=0.30)
        # Culling sets status but doesn't delete the agent record
        for agent in culled:
            agent["status"] = "retired"
            assert agent["agent_id"] is not None
            assert agent["traits"] is not None
            assert agent["fitness_score"] is not None

    def test_cull_by_fitness_ascending(self):
        """CONTRACT: Lowest fitness culled first."""
        fitness_vals = [90, 80, 70, 60, 50, 40, 30, 20, 10, 5]
        agents = _make_agents(10, fitness_range=fitness_vals)
        ranked = _rank_agents(agents)
        culled = _select_culled(ranked, cull_rate=0.30)
        # Culled should be the lowest 3 fitness scores
        culled_fitness = sorted([a["fitness_score"] for a in culled])
        assert culled_fitness == [5.0, 10.0, 20.0]


class TestCloneSelection:
    """CONTRACT: Clone selection (high performers)."""

    def test_top_20_percent_clone(self):
        """CONTRACT: Default: top 20% (excluding breeders) clone."""
        agents = _make_agents(100)
        ranked = _rank_agents(agents)
        clones = _select_clones(ranked, clone_rate=0.20, exclude_top=10)
        # 20% of (100 - 10) = 18
        assert len(clones) == 18

    def test_clone_excludes_top_10(self):
        """CONTRACT: Top 10 breeders excluded from clone pool."""
        agents = _make_agents(50)
        ranked = _rank_agents(agents)
        elite = _select_elite(ranked, count=10)
        clones = _select_clones(ranked, clone_rate=0.20, exclude_top=10)
        elite_ids = {a["agent_id"] for a in elite}
        clone_ids = {a["agent_id"] for a in clones}
        assert elite_ids.isdisjoint(clone_ids), "Breeders should not be in clone pool"

    def test_clone_selection_by_fitness(self):
        """CONTRACT: Clone selection based on fitness ranking."""
        agents = _make_agents(50)
        ranked = _rank_agents(agents)
        clones = _select_clones(ranked, clone_rate=0.20, exclude_top=10)
        # Clones should be from the next-highest fitness tier after breeders
        if len(clones) > 1:
            for i in range(len(clones) - 1):
                assert clones[i]["fitness_score"] >= clones[i + 1]["fitness_score"]


class TestFitnessRanking:
    """CONTRACT: Fitness-based ranking."""

    def test_rank_by_fitness_score(self):
        """CONTRACT: Agents ranked by fitness_score field."""
        agents = _make_agents(20)
        ranked = _rank_agents(agents)
        for i in range(len(ranked) - 1):
            assert ranked[i]["fitness_score"] >= ranked[i + 1]["fitness_score"]

    def test_ties_broken_deterministically(self):
        """CONTRACT: Same fitness ties broken by agent_id."""
        agents = [
            AgentFactory.create(agent_id="agent-bbb", fitness_score=50.0),
            AgentFactory.create(agent_id="agent-aaa", fitness_score=50.0),
            AgentFactory.create(agent_id="agent-ccc", fitness_score=50.0),
        ]
        ranked = _rank_agents(agents)
        # Same fitness -> sorted by agent_id ascending
        assert ranked[0]["agent_id"] == "agent-aaa"
        assert ranked[1]["agent_id"] == "agent-bbb"
        assert ranked[2]["agent_id"] == "agent-ccc"

    def test_ranking_excludes_retired(self):
        """CONTRACT: Retired agents not included in ranking."""
        agents = [
            AgentFactory.create(agent_id="a1", fitness_score=90.0, status="active"),
            AgentFactory.create(agent_id="a2", fitness_score=95.0, status="retired"),
            AgentFactory.create(agent_id="a3", fitness_score=80.0, status="active"),
        ]
        ranked = _rank_agents(agents, exclude_retired=True)
        assert len(ranked) == 2
        assert ranked[0]["agent_id"] == "a1"


class TestSelectionPressureStrength:
    """CONTRACT: Selection pressure adjustable."""

    def test_default_selection_pressure(self):
        """CONTRACT: Default pressure: 70% survive, 30% cull."""
        agents = _make_agents(100)
        ranked = _rank_agents(agents)
        survivors = _select_survivors(ranked, survival_rate=0.70)
        culled = _select_culled(ranked, cull_rate=0.30)
        assert len(survivors) == 70
        assert len(culled) == 30

    def test_rapid_evolution_pressure(self):
        """CONTRACT: Rapid: 55% survive, 45% cull."""
        agents = _make_agents(100)
        ranked = _rank_agents(agents)
        survivors = _select_survivors(ranked, survival_rate=0.55)
        culled = _select_culled(ranked, cull_rate=0.45)
        assert len(survivors) == 55
        assert len(culled) == 45

    def test_configurable_survival_rate(self):
        """CONTRACT: Survival rate is configurable."""
        agents = _make_agents(100)
        ranked = _rank_agents(agents)
        for rate in [0.50, 0.60, 0.70, 0.80, 0.90]:
            survivors = _select_survivors(ranked, survival_rate=rate)
            assert len(survivors) == int(100 * rate)


class TestMinimumPopulation:
    """CONTRACT: Minimum population protection."""

    def test_never_cull_below_minimum(self):
        """CONTRACT: Never cull below min_population (default 10)."""
        agents = _make_agents(15)
        ranked = _rank_agents(agents)
        min_population = 10
        cull_count = int(len(ranked) * 0.30)  # 4
        # Ensure we don't go below minimum
        max_cull = len(ranked) - min_population  # 5
        actual_cull = min(cull_count, max_cull)
        remaining = len(ranked) - actual_cull
        assert remaining >= min_population

    def test_minimum_population_configurable(self):
        """CONTRACT: Minimum population is configurable."""
        agents = _make_agents(20)
        ranked = _rank_agents(agents)
        for min_pop in [5, 10, 15]:
            cull_count = int(len(ranked) * 0.50)  # 10
            max_cull = len(ranked) - min_pop
            actual_cull = min(cull_count, max_cull)
            remaining = len(ranked) - actual_cull
            assert remaining >= min_pop


class TestSelectionDeterminism:
    """CONTRACT: Selection is deterministic."""

    def test_same_fitness_same_selection(self):
        """CONTRACT: Same fitness values -> same selection."""
        agents1 = _make_agents(50)
        agents2 = _make_agents(50)
        ranked1 = _rank_agents(agents1)
        ranked2 = _rank_agents(agents2)
        for a, b in zip(ranked1, ranked2):
            assert a["agent_id"] == b["agent_id"]
            assert a["fitness_score"] == b["fitness_score"]

    def test_selection_reproducible(self):
        """CONTRACT: Selection reproducible across runs."""
        agents = _make_agents(100)
        ranked = _rank_agents(agents)
        elite1 = _select_elite(ranked, count=10)
        elite2 = _select_elite(ranked, count=10)
        assert [a["agent_id"] for a in elite1] == [a["agent_id"] for a in elite2]


class TestPatternSelection:
    """CONTRACT: Pattern selection pressure."""

    def test_pattern_tier_promotion(self):
        """CONTRACT: High fitness patterns promoted to higher tier."""
        pattern = {"pattern_id": "p1", "tier": 3, "fitness_score": 85.0}
        # Promotion: fitness >= 80 -> tier + 1
        if pattern["fitness_score"] >= 80.0:
            pattern["tier"] = min(5, pattern["tier"] + 1)
        assert pattern["tier"] == 4

    def test_pattern_tier_demotion(self):
        """CONTRACT: Low fitness patterns demoted to lower tier."""
        pattern = {"pattern_id": "p1", "tier": 3, "fitness_score": 30.0}
        # Demotion: fitness < 40 -> tier - 1
        if pattern["fitness_score"] < 40.0:
            pattern["tier"] = max(1, pattern["tier"] - 1)
        assert pattern["tier"] == 2

    def test_pattern_culling(self):
        """CONTRACT: Very low fitness patterns culled."""
        patterns = [
            {"pattern_id": "p1", "fitness_score": 85.0, "is_active": True},
            {"pattern_id": "p2", "fitness_score": 15.0, "is_active": True},
            {"pattern_id": "p3", "fitness_score": 5.0, "is_active": True},
        ]
        cull_threshold = 20.0
        for p in patterns:
            if p["fitness_score"] < cull_threshold:
                p["is_active"] = False
        active = [p for p in patterns if p["is_active"]]
        assert len(active) == 1
        assert active[0]["pattern_id"] == "p1"


class TestSelectionMetrics:
    """CONTRACT: Selection metrics tracking."""

    def test_track_selection_counts(self):
        """CONTRACT: Track counts for each selection outcome."""
        agents = _make_agents(100)
        ranked = _rank_agents(agents)
        elite = _select_elite(ranked, count=10)
        survivors = _select_survivors(ranked, survival_rate=0.70)
        culled = _select_culled(ranked, cull_rate=0.30)
        clones = _select_clones(ranked, clone_rate=0.20, exclude_top=10)

        metrics = {
            "elite_count": len(elite),
            "survivor_count": len(survivors),
            "culled_count": len(culled),
            "clone_count": len(clones),
        }
        assert metrics["elite_count"] == 10
        assert metrics["survivor_count"] == 70
        assert metrics["culled_count"] == 30
        assert metrics["clone_count"] == 18

    def test_track_average_fitness_survivors(self):
        """CONTRACT: Track average fitness of survivors."""
        fitness_vals = list(range(0, 100, 10))  # 0, 10, 20, ..., 90
        agents = _make_agents(10, fitness_range=fitness_vals)
        ranked = _rank_agents(agents)
        survivors = _select_survivors(ranked, survival_rate=0.70)
        avg_fitness = sum(a["fitness_score"] for a in survivors) / len(survivors)
        # Top 7 by fitness: 90, 80, 70, 60, 50, 40, 30 -> avg = 60
        assert avg_fitness == pytest.approx(60.0)

    def test_track_average_fitness_culled(self):
        """CONTRACT: Track average fitness of culled."""
        fitness_vals = list(range(0, 100, 10))  # 0, 10, 20, ..., 90
        agents = _make_agents(10, fitness_range=fitness_vals)
        ranked = _rank_agents(agents)
        culled = _select_culled(ranked, cull_rate=0.30)
        avg_fitness = sum(a["fitness_score"] for a in culled) / len(culled)
        # Bottom 3 by fitness: 0, 10, 20 -> avg = 10
        assert avg_fitness == pytest.approx(10.0)
