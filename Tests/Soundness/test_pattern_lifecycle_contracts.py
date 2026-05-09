"""
Pattern Lifecycle Contracts - EDD (Evidence-Driven Development) Tests.

These tests document and verify the CORRECT behavior of the pattern lifecycle
as specified in the plan: transient-pondering-crane.md

CRITICAL BEHAVIORS TESTED:
1. V2 Signed Risk fitness formula (Alpha, Sortino, Calmar, Expectancy, Exit Efficiency)
2. Quintile-based tier system (NOT fixed ranges)
3. TOP 10 fixed breeding (NOT percentage-based)
4. Affinity sort in genesis (NOT random shuffle)
5. Spawn eligibility (100+ backtests on 3+ assets, 4 timeframes)
"""

from dataclasses import dataclass

import pytest

# =============================================================================
# CONTRACT 1: V2 Signed Risk Fitness Formula
# =============================================================================


class TestV2SignedRiskFitnessFormula:
    """
    V2 Signed Risk formula for patterns:

    Signed Components (CAN GO NEGATIVE):
    - Alpha: -35 to +35 pts
    - Sortino: -14 to +14 pts (capped at ±10 input)
    - Calmar: -11 to +11 pts (capped at ±10 input)

    Normalized Components (0 to max):
    - Expectancy: 0-25 pts
    - Drawdown: 0-5 pts (bonus for LOW drawdown)
    - Exit Efficiency: 0-10 pts

    Total range: -60 to +100, clamped to 0-100
    """

    def test_fitness_uses_sortino_not_sharpe(self):
        """Pattern fitness must use Sortino ratio, NOT Sharpe ratio."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_pattern_fitness

        # Create metrics with high Sortino
        @dataclass
        class MockMetrics:
            alpha_pct: float = 0.0
            sortino_ratio: float = 5.0  # High Sortino
            calmar_ratio: float = 0.0
            expectancy_pct: float = 0.0
            max_drawdown_pct: float = 25.0
            exit_efficiency: float = 0.5

        result = calculate_pattern_fitness(MockMetrics())

        # Sortino should contribute to fitness
        assert result.sortino_contribution > 0, "Sortino must contribute to fitness"
        assert hasattr(result, "sortino_contribution"), "Must track sortino contribution"

    def test_fitness_uses_calmar_ratio(self):
        """Pattern fitness must use Calmar ratio (return / max drawdown)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_pattern_fitness

        @dataclass
        class MockMetrics:
            alpha_pct: float = 0.0
            sortino_ratio: float = 0.0
            calmar_ratio: float = 5.0  # High Calmar
            expectancy_pct: float = 0.0
            max_drawdown_pct: float = 10.0
            exit_efficiency: float = 0.5

        result = calculate_pattern_fitness(MockMetrics())

        assert result.calmar_contribution > 0, "Calmar must contribute to fitness"
        assert hasattr(result, "calmar_contribution"), "Must track calmar contribution"

    def test_fitness_uses_expectancy(self):
        """Pattern fitness must use Expectancy (win% * avg_win - loss% * avg_loss)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_pattern_fitness

        @dataclass
        class MockMetrics:
            alpha_pct: float = 0.0
            sortino_ratio: float = 0.0
            calmar_ratio: float = 0.0
            expectancy_pct: float = 5.0  # High expectancy
            max_drawdown_pct: float = 25.0
            exit_efficiency: float = 0.5

        result = calculate_pattern_fitness(MockMetrics())

        assert result.expectancy_score > 0, "Expectancy must contribute to fitness"
        assert hasattr(result, "expectancy_score"), "Must track expectancy score"

    def test_fitness_uses_exit_efficiency(self):
        """Pattern fitness must use Exit Efficiency (pnl/mfe ratio)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_pattern_fitness

        @dataclass
        class MockMetrics:
            alpha_pct: float = 0.0
            sortino_ratio: float = 0.0
            calmar_ratio: float = 0.0
            expectancy_pct: float = 0.0
            max_drawdown_pct: float = 25.0
            exit_efficiency: float = 0.9  # High exit efficiency

        result = calculate_pattern_fitness(MockMetrics())

        assert result.exit_efficiency_score > 0, "Exit efficiency must contribute to fitness"

    def test_fitness_signed_components_can_be_negative(self):
        """Signed components (alpha, sortino, calmar) CAN be negative."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_pattern_fitness

        @dataclass
        class MockMetrics:
            alpha_pct: float = -50.0  # Negative alpha
            sortino_ratio: float = -5.0  # Negative sortino
            calmar_ratio: float = -5.0  # Negative calmar
            expectancy_pct: float = 0.0
            max_drawdown_pct: float = 25.0
            exit_efficiency: float = 0.5

        result = calculate_pattern_fitness(MockMetrics())

        assert result.alpha_contribution < 0, "Alpha can be negative"
        assert result.sortino_contribution < 0, "Sortino can be negative"
        assert result.calmar_contribution < 0, "Calmar can be negative"
        assert result.signed_total < 0, "Signed total can be negative"

    def test_fitness_clamped_to_0_100(self):
        """Final fitness must be clamped to [0, 100]."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_pattern_fitness

        # Worst case - all negative
        @dataclass
        class BadMetrics:
            alpha_pct: float = -100.0
            sortino_ratio: float = -10.0
            calmar_ratio: float = -10.0
            expectancy_pct: float = -10.0
            max_drawdown_pct: float = 50.0
            exit_efficiency: float = 0.0

        result = calculate_pattern_fitness(BadMetrics())
        assert result.final_fitness >= 0, "Fitness cannot be below 0"

        # Best case - all positive
        @dataclass
        class GoodMetrics:
            alpha_pct: float = 100.0
            sortino_ratio: float = 10.0
            calmar_ratio: float = 10.0
            expectancy_pct: float = 10.0
            max_drawdown_pct: float = 0.0
            exit_efficiency: float = 1.0

        result = calculate_pattern_fitness(GoodMetrics())
        assert result.final_fitness <= 100, "Fitness cannot be above 100"

    def test_fitness_no_ev_gate_for_patterns(self):
        """Pattern fitness does NOT use EV gate (unlike agent fitness)."""
        from Fast_Swarm.local_agents.shared.fitness import calculate_pattern_fitness

        # Pattern with negative expectancy should still have non-zero fitness
        # if other components are positive (unlike agent which would be gated)
        @dataclass
        class MockMetrics:
            alpha_pct: float = 50.0  # Strong positive alpha
            sortino_ratio: float = 3.0
            calmar_ratio: float = 3.0
            expectancy_pct: float = -5.0  # Negative expectancy
            max_drawdown_pct: float = 15.0
            exit_efficiency: float = 0.6

        result = calculate_pattern_fitness(MockMetrics())

        # Should have fitness > 0 despite negative expectancy
        assert result.final_fitness > 0, "Pattern fitness should NOT gate on expectancy (V2 Signed Risk)"


# =============================================================================
# CONTRACT 2: Quintile-Based Tier System
# =============================================================================


class TestQuintileBasedTierSystem:
    """
    Tier system must be QUINTILE-BASED, not fixed ranges.

    | Quintile | Tier | Status | Spawn Eligibility |
    |----------|------|--------|-------------------|
    | Top 20%  | 1    | ELITE  | ✅ Shown to agents |
    | 20-40%   | 2    | PROVEN | ✅ Available for spawn |
    | 40-60%   | 3    | UNTESTED | ❌ Cannot be assigned |
    | 60-80%   | 4    | WEAK   | ❌ Cannot be assigned |
    | Bottom 20% | 5  | CULL   | 🗑️ Culled |
    """

    def test_get_tiers_by_quintile_function_exists(self):
        """A function to calculate quintile-based tiers must exist."""
        from Patterns.Services.pattern_service import get_tiers_by_quintile

        assert callable(get_tiers_by_quintile), "get_tiers_by_quintile must be callable"

    def test_top_quintile_is_tier_1(self):
        """Top 20% of patterns by fitness should be Tier 1."""
        from Patterns.Services.pattern_service import get_tiers_by_quintile

        # Create patterns with various fitness scores
        patterns = [
            {"pattern_id": f"p{i}", "fitness_score": 50 + i * 5}
            for i in range(10)  # Fitness: 50, 55, 60, ..., 95
        ]

        tiers = get_tiers_by_quintile(patterns)

        # Top 20% (2 patterns: 90, 95) should be tier 1
        assert tiers["p9"] == 1, "Highest fitness (95) should be tier 1"
        assert tiers["p8"] == 1, "Second highest (90) should be tier 1"

    def test_bottom_quintile_is_tier_5_cull(self):
        """Bottom 20% of patterns should be Tier 5 (CULL)."""
        from Patterns.Services.pattern_service import get_tiers_by_quintile

        patterns = [{"pattern_id": f"p{i}", "fitness_score": 50 + i * 5} for i in range(10)]

        tiers = get_tiers_by_quintile(patterns)

        # Bottom 20% (2 patterns: 50, 55) should be tier 5
        assert tiers["p0"] == 5, "Lowest fitness (50) should be tier 5 (CULL)"
        assert tiers["p1"] == 5, "Second lowest (55) should be tier 5 (CULL)"

    def test_middle_quintiles_assigned_correctly(self):
        """Middle quintiles should be assigned tiers 2-4."""
        from Patterns.Services.pattern_service import get_tiers_by_quintile

        patterns = [
            {"pattern_id": f"p{i}", "fitness_score": 50 + i * 5}
            for i in range(10)  # Fitness: 50, 55, 60, ..., 95
        ]

        tiers = get_tiers_by_quintile(patterns)

        # Verify tier distribution
        # p9, p8 -> tier 1 (top 20%)
        # p7, p6 -> tier 2 (20-40%)
        # p5, p4 -> tier 3 (40-60%)
        # p3, p2 -> tier 4 (60-80%)
        # p1, p0 -> tier 5 (bottom 20%)

        assert tiers["p7"] == 2, "p7 (85) should be tier 2"
        assert tiers["p6"] == 2, "p6 (80) should be tier 2"
        assert tiers["p5"] == 3, "p5 (75) should be tier 3"
        assert tiers["p4"] == 3, "p4 (70) should be tier 3"
        assert tiers["p3"] == 4, "p3 (65) should be tier 4"
        assert tiers["p2"] == 4, "p2 (60) should be tier 4"

    def test_only_tier_1_and_2_are_spawn_eligible(self):
        """Only Tier 1 and 2 patterns can be shown to agents for spawn."""
        from Patterns.Services.pattern_service import is_spawn_eligible

        assert is_spawn_eligible(tier=1) == True, "Tier 1 should be spawn eligible"
        assert is_spawn_eligible(tier=2) == True, "Tier 2 should be spawn eligible"
        assert is_spawn_eligible(tier=3) == False, "Tier 3 should NOT be spawn eligible"
        assert is_spawn_eligible(tier=4) == False, "Tier 4 should NOT be spawn eligible"
        assert is_spawn_eligible(tier=5) == False, "Tier 5 should NOT be spawn eligible"


# =============================================================================
# CONTRACT 3: TOP 10 Fixed Breeding (Not Percentage)
# =============================================================================


class TestTop10FixedBreeding:
    """
    TOP 10 AGENTS (fixed number) breed - NOT top percentage.

    Separate from cloning:
    - TOP 10 (fixed) → breed via crossover
    - Top N% → clone with mutation
    """

    def test_select_for_breeding_exists(self):
        """select_for_breeding function must exist."""
        from Fast_Swarm.local_agents.core.evolution import select_for_breeding

        assert callable(select_for_breeding), "select_for_breeding must be callable"

    def test_select_for_cloning_exists(self):
        """select_for_cloning function must exist."""
        from Fast_Swarm.local_agents.core.evolution import select_for_cloning

        assert callable(select_for_cloning), "select_for_cloning must be callable"

    def test_elite_for_breeding_is_fixed_10_not_percentage(self):
        """Elite pool for breeding must be exactly 10 agents, not a percentage."""
        from Fast_Swarm.local_agents.core.evolution import select_for_breeding

        # Create mock agents
        class MockAgent:
            def __init__(self, agent_id, fitness):
                self.agent_id = agent_id
                self.fitness_score = fitness

        # With 100 agents, should still select TOP 10
        mock_population = [MockAgent(f"a{i}", 50 + i) for i in range(100)]

        elite = select_for_breeding(mock_population)

        assert len(elite) == 10, (
            f"Elite for breeding must be exactly 10, got {len(elite)}. This is a FIXED number, not a percentage."
        )

    def test_breeding_uses_top_10_when_population_larger(self):
        """With large populations, still use exactly top 10 for breeding."""
        from Fast_Swarm.local_agents.core.evolution import select_for_breeding

        class MockAgent:
            def __init__(self, agent_id, fitness):
                self.agent_id = agent_id
                self.fitness_score = fitness

        # 50 agents
        mock_population = [MockAgent(f"a{i}", i) for i in range(50)]

        elite = select_for_breeding(mock_population)

        assert len(elite) == 10, "Must select TOP 10, not percentage"

        # Verify they are the top 10 by fitness
        expected_top_ids = {f"a{i}" for i in range(40, 50)}
        actual_ids = {a.agent_id for a in elite}
        assert actual_ids == expected_top_ids, "Must be the TOP 10 by fitness"

    def test_breeding_uses_all_when_population_under_10(self):
        """With fewer than 10 agents, use all for breeding pool."""
        from Fast_Swarm.local_agents.core.evolution import select_for_breeding

        class MockAgent:
            def __init__(self, agent_id, fitness):
                self.agent_id = agent_id
                self.fitness_score = fitness

        mock_population = [MockAgent(f"a{i}", 50 + i) for i in range(5)]

        elite = select_for_breeding(mock_population)

        assert len(elite) == 5, "With 5 agents, all should be in breeding pool"


# =============================================================================
# CONTRACT 4: Affinity Sort (Not Random Shuffle)
# =============================================================================


class TestAffinitySortNotShuffle:
    """
    Pattern selection for spawn must use AFFINITY SORT, not random shuffle.

    Pipeline:
    1. Filter: fitness in top quintile + 100+ backtests + required timeframes
    2. Sort: by affinity score (trait alignment)
    3. Take: top 15 most aligned
    4. Pass: raw trait + pattern data (NO affinity score) to AI
    """

    def test_affinity_functions_exist(self):
        """Affinity calculation functions must exist."""
        from Fast_Swarm.local_agents.core.genesis import (
            calculate_pattern_affinity,
            get_top_patterns_for_spawn,
            prepare_spawn_prompt_data,
            sort_patterns_by_affinity,
        )

        assert callable(calculate_pattern_affinity)
        assert callable(sort_patterns_by_affinity)
        assert callable(get_top_patterns_for_spawn)
        assert callable(prepare_spawn_prompt_data)

    def test_genesis_does_not_shuffle_patterns(self):
        """Genesis must NOT randomly shuffle patterns before selection."""
        # This is a code inspection test - verify shuffle is not used
        import inspect

        from Fast_Swarm.local_agents.core.genesis import select_patterns_llm

        source = inspect.getsource(select_patterns_llm)

        # Should NOT contain random.shuffle
        assert "random.shuffle" not in source, (
            "select_patterns_llm must NOT use random.shuffle. Use affinity sort instead."
        )

    def test_affinity_sort_is_deterministic(self):
        """Affinity sort must produce deterministic results (given same traits)."""
        from Fast_Swarm.local_agents.core.genesis import sort_patterns_by_affinity
        from Fast_Swarm.local_agents.core.traits import generate_traits

        traits = generate_traits(seed=42)
        patterns = [{"pattern_id": f"p{i}", "type": "momentum" if i % 2 == 0 else "reversion"} for i in range(20)]

        # Should be deterministic
        sorted1 = sort_patterns_by_affinity(traits, patterns)
        sorted2 = sort_patterns_by_affinity(traits, patterns)

        ids1 = [p["pattern_id"] for p in sorted1]
        ids2 = [p["pattern_id"] for p in sorted2]

        assert ids1 == ids2, "Affinity sort must be deterministic"

    def test_affinity_sort_before_taking_top_15(self):
        """Must sort by affinity BEFORE taking top 15 patterns."""
        from Fast_Swarm.local_agents.core.genesis import get_top_patterns_for_spawn
        from Fast_Swarm.local_agents.core.traits import generate_traits

        traits = generate_traits(seed=42)
        patterns = [{"pattern_id": f"p{i}", "fitness_score": 80, "type": "momentum"} for i in range(30)]

        top_15 = get_top_patterns_for_spawn(traits, patterns)

        assert len(top_15) == 15, "Must take exactly 15 patterns"

    def test_raw_data_passed_to_ai_not_affinity_score(self):
        """AI receives raw trait/pattern data, NOT the combined affinity score."""
        from Fast_Swarm.local_agents.core.genesis import prepare_spawn_prompt_data
        from Fast_Swarm.local_agents.core.traits import generate_traits

        traits = generate_traits(seed=42)
        patterns = [{"pattern_id": "p1", "type": "momentum", "win_rate": 0.58}]

        prompt_data = prepare_spawn_prompt_data(traits, patterns)

        # Should contain raw traits
        assert "traits" in prompt_data
        # Should NOT contain affinity scores
        assert "affinity_score" not in str(prompt_data), "AI should see raw data, not pre-computed affinity scores"


# =============================================================================
# CONTRACT 5: Spawn Eligibility Requirements
# =============================================================================


class TestSpawnEligibilityRequirements:
    """
    Patterns cannot be spawned/culled until:
    - 100+ backtest windows
    - Tested on 3+ assets
    - Tested on all 4 timeframes (1m, 15m, 1h, 1d)
    """

    def test_minimum_backtest_windows_required(self):
        """Pattern needs 100+ backtest windows before spawn eligibility."""
        from Patterns.Services.pattern_service import is_spawn_eligible

        pattern_few_tests = {
            "backtest_count": 50,
            "tier": 1,
            "assets_tested": ["BTC", "ETH", "SOL"],
            "timeframes_tested": ["1m", "15m", "1h", "1d"],
        }
        pattern_many_tests = {
            "backtest_count": 100,
            "tier": 1,
            "assets_tested": ["BTC", "ETH", "SOL"],
            "timeframes_tested": ["1m", "15m", "1h", "1d"],
        }

        assert is_spawn_eligible(pattern_few_tests) == False, (
            "Pattern with < 100 backtests should NOT be spawn eligible"
        )
        assert is_spawn_eligible(pattern_many_tests) == True, (
            "Pattern with >= 100 backtests should be spawn eligible (if tier 1-2)"
        )

    def test_minimum_assets_required(self):
        """Pattern needs to be tested on 3+ assets."""
        from Patterns.Services.pattern_service import is_spawn_eligible

        pattern_few_assets = {
            "backtest_count": 100,
            "assets_tested": ["BTC", "ETH"],
            "timeframes_tested": ["1m", "15m", "1h", "1d"],
            "tier": 1,
        }
        pattern_many_assets = {
            "backtest_count": 100,
            "assets_tested": ["BTC", "ETH", "SOL"],
            "timeframes_tested": ["1m", "15m", "1h", "1d"],
            "tier": 1,
        }

        assert is_spawn_eligible(pattern_few_assets) == False, (
            "Pattern tested on < 3 assets should NOT be spawn eligible"
        )
        assert is_spawn_eligible(pattern_many_assets) == True, "Pattern tested on >= 3 assets should be spawn eligible"

    def test_all_timeframes_required(self):
        """Pattern needs to be tested on all 4 timeframes: 1m, 15m, 1h, 1d."""
        from Patterns.Services.pattern_service import is_spawn_eligible

        pattern_partial = {
            "backtest_count": 100,
            "assets_tested": ["BTC", "ETH", "SOL"],
            "timeframes_tested": ["1h", "1d"],  # Missing 1m, 15m
            "tier": 1,
        }
        pattern_complete = {
            "backtest_count": 100,
            "assets_tested": ["BTC", "ETH", "SOL"],
            "timeframes_tested": ["1m", "15m", "1h", "1d"],
            "tier": 1,
        }

        assert is_spawn_eligible(pattern_partial) == False, "Pattern missing timeframes should NOT be spawn eligible"
        assert is_spawn_eligible(pattern_complete) == True, "Pattern tested on all timeframes should be spawn eligible"

    def test_cull_requires_same_eligibility(self):
        """Patterns cannot be culled until they meet the same eligibility requirements."""
        from Patterns.Services.pattern_service import is_cull_eligible

        # Pattern with low fitness but not enough testing
        pattern_undertested = {
            "fitness_score": 20,  # Low fitness
            "backtest_count": 50,  # Not enough tests
            "tier": 5,  # Cull tier
            "assets_tested": [],
            "timeframes_tested": [],
        }

        assert is_cull_eligible(pattern_undertested) == False, "Cannot cull pattern until it has 100+ backtests"


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
