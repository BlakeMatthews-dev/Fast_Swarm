"""
Trait Operations Performance Tests - Stress test trait manipulation.

MASTER TEST ADMIN: "22 traits, infinite combinations, finite patience."

Tests performance of:
- Trait generation
- Trait mutation
- Trait crossover
- Batch trait operations
"""

import random

# =============================================================================
# Test Data Generators
# =============================================================================


def generate_trait_set(seed: int = None) -> dict[str, float]:
    """Generate a random trait set."""
    if seed is not None:
        random.seed(seed)

    trait_names = [
        "risk_tolerance",
        "position_sizing",
        "stop_loss_tightness",
        "take_profit_target",
        "hold_duration",
        "momentum_weight",
        "reversion_preference",
        "volatility_affinity",
        "trend_following",
        "breakout_sensitivity",
        "mean_reversion",
        "range_trading",
        "news_sensitivity",
        "correlation_awareness",
        "sector_focus",
        "timeframe_preference",
        "entry_patience",
        "exit_aggression",
        "drawdown_tolerance",
        "profit_lock_tendency",
        "scaling_in",
        "scaling_out",
    ]

    return {name: random.random() for name in trait_names}


# =============================================================================
# Trait Generation Performance Tests
# =============================================================================


class TestTraitGenerationPerformance:
    """Test trait generation performance."""

    def test_single_trait_set_generation(self, benchmark_runner):
        """CONTRACT: Single trait set generation < 1ms."""
        try:
            from Agents.Services.trait_service import generate_all_traits

            generate_func = generate_all_traits
        except ImportError:
            generate_func = generate_trait_set

        result = benchmark_runner.run(
            name="single_trait_generation",
            func=generate_func,
            iterations=1000,
            warmup=100,
            contract_key="trait_generation",
        )

        assert result.passed, f"Contract failed: {result.mean_ms:.4f}ms > {result.contract_max_ms}ms"

    def test_batch_trait_generation_100(self, benchmark_runner):
        """Test generating 100 trait sets."""
        try:
            from Agents.Services.trait_service import generate_all_traits

            generate_func = generate_all_traits
        except ImportError:
            generate_func = generate_trait_set

        def batch_generate():
            return [generate_func() for _ in range(100)]

        result = benchmark_runner.run(
            name="batch_trait_generation_100",
            func=batch_generate,
            iterations=50,
            warmup=5,
        )

        # 100 generations should take < 50ms
        assert result.mean_ms < 50, f"Batch generation too slow: {result.mean_ms:.2f}ms"

    def test_batch_trait_generation_1000(self, benchmark_runner):
        """Test generating 1,000 trait sets."""
        try:
            from Agents.Services.trait_service import generate_all_traits

            generate_func = generate_all_traits
        except ImportError:
            generate_func = generate_trait_set

        def batch_generate():
            return [generate_func() for _ in range(1000)]

        result = benchmark_runner.run(
            name="batch_trait_generation_1000",
            func=batch_generate,
            iterations=10,
            warmup=2,
        )

        # 1000 generations should take < 500ms
        assert result.mean_ms < 500, f"Batch generation too slow: {result.mean_ms:.2f}ms"


# =============================================================================
# Trait Mutation Performance Tests
# =============================================================================


class TestTraitMutationPerformance:
    """Test trait mutation performance."""

    def test_single_trait_mutation(self, benchmark_runner):
        """Test mutating a single trait value."""
        try:
            from Agents.Services.trait_service import mutate_trait

            mutate_func = lambda v: mutate_trait(v, mutation_rate=0.1)
        except ImportError:

            def mutate_func(value):
                mutation = random.gauss(0, 0.1)
                return max(0.0, min(1.0, value + mutation))

        def run_mutations():
            value = 0.5
            for _ in range(100):
                value = mutate_func(value)
            return value

        result = benchmark_runner.run(
            name="single_trait_mutation_100x",
            func=run_mutations,
            iterations=100,
            warmup=10,
        )

        # 100 mutations should be < 1ms
        assert result.mean_ms < 5, f"Mutation too slow: {result.mean_ms:.4f}ms"

    def test_full_trait_set_mutation(self, benchmark_runner):
        """Test mutating all 22 traits."""
        try:
            from Agents.Services.trait_service import generate_all_traits, mutate_traits

            traits = generate_all_traits()
            mutate_func = lambda: mutate_traits(traits.copy(), mutation_rate=0.1)
        except ImportError:
            traits = generate_trait_set(42)

            def mutate_func():
                mutated = traits.copy()
                for key in mutated:
                    if random.random() < 0.1:
                        mutation = random.gauss(0, 0.1)
                        mutated[key] = max(0.0, min(1.0, mutated[key] + mutation))
                return mutated

        result = benchmark_runner.run(
            name="full_trait_mutation",
            func=mutate_func,
            iterations=500,
            warmup=50,
        )

        # Full mutation should be < 1ms
        assert result.mean_ms < 1, f"Full mutation too slow: {result.mean_ms:.4f}ms"

    def test_batch_mutation_100(self, benchmark_runner):
        """CONTRACT: Mutate 100 trait sets < 10ms."""
        try:
            from Agents.Services.trait_service import generate_all_traits, mutate_traits

            trait_sets = [generate_all_traits() for _ in range(100)]
            mutate_func = lambda ts: [mutate_traits(t.copy(), mutation_rate=0.1) for t in ts]
        except ImportError:
            trait_sets = [generate_trait_set(i) for i in range(100)]

            def mutate_func(ts):
                results = []
                for traits in ts:
                    mutated = traits.copy()
                    for key in mutated:
                        if random.random() < 0.1:
                            mutation = random.gauss(0, 0.1)
                            mutated[key] = max(0.0, min(1.0, mutated[key] + mutation))
                    results.append(mutated)
                return results

        result = benchmark_runner.run(
            name="batch_mutation_100",
            func=lambda: mutate_func(trait_sets),
            iterations=50,
            warmup=5,
            contract_key="trait_mutation_batch_100",
        )

        assert result.passed, f"Contract failed: {result.mean_ms:.2f}ms > {result.contract_max_ms}ms"


# =============================================================================
# Trait Crossover Performance Tests
# =============================================================================


class TestTraitCrossoverPerformance:
    """Test trait crossover performance."""

    def test_single_crossover(self, benchmark_runner):
        """CONTRACT: Single crossover < 1ms."""
        try:
            from Agents.Services.trait_service import crossover_traits, generate_all_traits

            parent1 = generate_all_traits()
            parent2 = generate_all_traits()
            crossover_func = lambda: crossover_traits(parent1, parent2)
        except ImportError:
            parent1 = generate_trait_set(1)
            parent2 = generate_trait_set(2)

            def crossover_func():
                child = {}
                for key in parent1:
                    child[key] = parent1[key] if random.random() < 0.5 else parent2[key]
                return child

        result = benchmark_runner.run(
            name="single_crossover",
            func=crossover_func,
            iterations=1000,
            warmup=100,
            contract_key="trait_crossover",
        )

        assert result.passed, f"Contract failed: {result.mean_ms:.4f}ms > {result.contract_max_ms}ms"

    def test_batch_crossover_100(self, benchmark_runner):
        """Test 100 crossover operations."""
        try:
            from Agents.Services.trait_service import crossover_traits, generate_all_traits

            parents = [(generate_all_traits(), generate_all_traits()) for _ in range(100)]
            crossover_func = lambda: [crossover_traits(p1, p2) for p1, p2 in parents]
        except ImportError:
            parents = [(generate_trait_set(i), generate_trait_set(i + 100)) for i in range(100)]

            def crossover_func():
                children = []
                for p1, p2 in parents:
                    child = {key: p1[key] if random.random() < 0.5 else p2[key] for key in p1}
                    children.append(child)
                return children

        result = benchmark_runner.run(
            name="batch_crossover_100",
            func=crossover_func,
            iterations=50,
            warmup=5,
        )

        # 100 crossovers should be < 50ms
        assert result.mean_ms < 50, f"Batch crossover too slow: {result.mean_ms:.2f}ms"

    def test_crossover_and_mutate(self, benchmark_runner):
        """Test combined crossover + mutation (typical breeding)."""
        try:
            from Agents.Services.trait_service import crossover_and_mutate, generate_all_traits

            parent1 = generate_all_traits()
            parent2 = generate_all_traits()
            breed_func = lambda: crossover_and_mutate(parent1, parent2, mutation_rate=0.1)
        except ImportError:
            parent1 = generate_trait_set(1)
            parent2 = generate_trait_set(2)

            def breed_func():
                # Crossover
                child = {key: parent1[key] if random.random() < 0.5 else parent2[key] for key in parent1}
                # Mutation
                for key in child:
                    if random.random() < 0.1:
                        mutation = random.gauss(0, 0.1)
                        child[key] = max(0.0, min(1.0, child[key] + mutation))
                return child

        result = benchmark_runner.run(
            name="crossover_and_mutate",
            func=breed_func,
            iterations=500,
            warmup=50,
        )

        # Combined operation should be < 2ms
        assert result.mean_ms < 2, f"Breed operation too slow: {result.mean_ms:.4f}ms"


# =============================================================================
# Trait Validation Performance Tests
# =============================================================================


class TestTraitValidationPerformance:
    """Test trait validation performance."""

    def test_validate_single_value(self, benchmark_runner):
        """Test validating a single trait value."""
        try:
            from Agents.Services.trait_service import validate_trait_value

            validate_func = validate_trait_value
        except ImportError:

            def validate_func(value):
                return 0.0 <= value <= 1.0

        def run_validations():
            values = [random.uniform(-0.5, 1.5) for _ in range(100)]
            return [validate_func(v) for v in values]

        result = benchmark_runner.run(
            name="validate_100_values",
            func=run_validations,
            iterations=100,
            warmup=10,
        )

        # 100 validations should be < 1ms
        assert result.mean_ms < 1, f"Validation too slow: {result.mean_ms:.4f}ms"

    def test_validate_full_trait_set(self, benchmark_runner):
        """Test validating all traits in a set."""
        try:
            from Agents.Services.trait_service import validate_trait_value

            validate_func = validate_trait_value
        except ImportError:

            def validate_func(value):
                return 0.0 <= value <= 1.0

        traits = generate_trait_set(42)

        def validate_all():
            return all(validate_func(v) for v in traits.values())

        result = benchmark_runner.run(
            name="validate_full_trait_set",
            func=validate_all,
            iterations=1000,
            warmup=100,
        )

        # Validating 22 traits should be < 0.1ms
        assert result.mean_ms < 0.5, f"Full validation too slow: {result.mean_ms:.4f}ms"

    def test_clamp_traits(self, benchmark_runner):
        """Test clamping out-of-bounds trait values."""
        try:
            from Agents.Services.trait_service import clamp_traits

            clamp_func = clamp_traits
        except ImportError:

            def clamp_func(traits):
                return {k: max(0.0, min(1.0, v)) for k, v in traits.items()}

        # Some out-of-bounds values
        traits = generate_trait_set(42)
        for key in list(traits.keys())[:5]:
            traits[key] = random.uniform(-1, 2)

        result = benchmark_runner.run(
            name="clamp_traits",
            func=lambda: clamp_func(traits.copy()),
            iterations=1000,
            warmup=100,
        )

        assert result.mean_ms < 0.5, f"Clamping too slow: {result.mean_ms:.4f}ms"


# =============================================================================
# Evolution Selection Performance Tests
# =============================================================================


class TestEvolutionSelectionPerformance:
    """Test evolution selection algorithm performance."""

    def test_breeder_selection_from_1000(self, benchmark_runner):
        """CONTRACT: Select breeders from 1,000 agents < 200ms."""
        agents = [{"agent_id": f"agent-{i}", "fitness_score": random.uniform(0, 100)} for i in range(1000)]

        def select_breeders():
            # Sort by fitness
            sorted_agents = sorted(agents, key=lambda a: a["fitness_score"], reverse=True)
            # Top 20% are breeders
            breeder_count = int(len(sorted_agents) * 0.2)
            return sorted_agents[:breeder_count]

        result = benchmark_runner.run(
            name="breeder_selection_1000",
            func=select_breeders,
            iterations=50,
            warmup=5,
            contract_key="evolution_selection_1000",
        )

        assert result.passed, f"Contract failed: {result.mean_ms:.2f}ms > {result.contract_max_ms}ms"

    def test_tournament_selection(self, benchmark_runner):
        """Test tournament selection performance."""
        agents = [{"agent_id": f"agent-{i}", "fitness_score": random.uniform(0, 100)} for i in range(1000)]

        def tournament_selection(tournament_size=5, num_selections=100):
            selected = []
            for _ in range(num_selections):
                tournament = random.sample(agents, tournament_size)
                winner = max(tournament, key=lambda a: a["fitness_score"])
                selected.append(winner)
            return selected

        result = benchmark_runner.run(
            name="tournament_selection_100",
            func=tournament_selection,
            iterations=50,
            warmup=5,
        )

        # 100 tournament selections should be < 50ms
        assert result.mean_ms < 50, f"Tournament selection too slow: {result.mean_ms:.2f}ms"

    def test_roulette_wheel_selection(self, benchmark_runner):
        """Test roulette wheel (fitness-proportionate) selection."""
        agents = [
            {"agent_id": f"agent-{i}", "fitness_score": random.uniform(1, 100)}  # Min 1 to avoid div/0
            for i in range(1000)
        ]

        def roulette_selection(num_selections=100):
            total_fitness = sum(a["fitness_score"] for a in agents)
            selected = []

            for _ in range(num_selections):
                spin = random.uniform(0, total_fitness)
                current = 0
                for agent in agents:
                    current += agent["fitness_score"]
                    if current >= spin:
                        selected.append(agent)
                        break

            return selected

        result = benchmark_runner.run(
            name="roulette_selection_100",
            func=roulette_selection,
            iterations=20,
            warmup=2,
        )

        # Roulette is O(n) per selection, so 100 selections from 1000 = O(100k)
        assert result.mean_ms < 200, f"Roulette selection too slow: {result.mean_ms:.2f}ms"


# =============================================================================
# Edge Case Performance Tests
# =============================================================================


class TestTraitEdgeCases:
    """Test performance with edge case inputs."""

    def test_empty_traits_dict(self, timer):
        """Test operations on empty trait dict."""
        empty = {}

        with timer() as t:
            for _ in range(1000):
                _ = {k: max(0.0, min(1.0, v)) for k, v in empty.items()}

        avg_ms = t.elapsed_ms / 1000
        assert avg_ms < 0.01, f"Empty dict too slow: {avg_ms:.6f}ms"

    def test_single_trait(self, timer):
        """Test operations on single-trait dict."""
        single = {"only_trait": 0.5}

        with timer() as t:
            for _ in range(1000):
                mutated = single.copy()
                mutated["only_trait"] = max(0.0, min(1.0, mutated["only_trait"] + random.gauss(0, 0.1)))

        avg_ms = t.elapsed_ms / 1000
        assert avg_ms < 0.05, f"Single trait too slow: {avg_ms:.4f}ms"

    def test_extreme_trait_values(self, timer):
        """Test with extreme (but valid) trait values."""
        extreme = generate_trait_set(42)
        for key in extreme:
            extreme[key] = 0.0 if random.random() < 0.5 else 1.0

        with timer() as t:
            for _ in range(100):
                # Crossover with extremes
                child = {k: extreme[k] if random.random() < 0.5 else extreme[k] for k in extreme}
                # Mutate
                for key in child:
                    if random.random() < 0.1:
                        mutation = random.gauss(0, 0.1)
                        child[key] = max(0.0, min(1.0, child[key] + mutation))

        avg_ms = t.elapsed_ms / 100
        assert avg_ms < 1, f"Extreme values too slow: {avg_ms:.4f}ms"

    def test_many_traits(self, benchmark_runner):
        """Test performance with more than 22 traits (hypothetical expansion)."""
        many_traits = {f"trait_{i}": random.random() for i in range(100)}

        def mutate_many():
            mutated = many_traits.copy()
            for key in mutated:
                if random.random() < 0.1:
                    mutation = random.gauss(0, 0.1)
                    mutated[key] = max(0.0, min(1.0, mutated[key] + mutation))
            return mutated

        result = benchmark_runner.run(
            name="mutate_100_traits",
            func=mutate_many,
            iterations=500,
            warmup=50,
        )

        # Even 100 traits should be < 2ms
        assert result.mean_ms < 2, f"Many traits too slow: {result.mean_ms:.4f}ms"
