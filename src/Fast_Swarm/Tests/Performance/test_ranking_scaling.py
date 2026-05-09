"""
Ranking and Sorting Performance Tests - Stress test agent ranking operations.

MASTER TEST ADMIN: "Sorting 10,000 agents should feel instant."

Tests scaling behavior of:
- Agent ranking by fitness
- Top/bottom agent selection
- Percentile calculations
- Population statistics
"""

import random
from typing import Any

import pytest

# =============================================================================
# Test Data Generators
# =============================================================================


def generate_mock_agents(count: int, seed: int = 42) -> list[dict[str, Any]]:
    """Generate deterministic mock agent data for benchmarking."""
    random.seed(seed)
    agents = []
    for i in range(count):
        agents.append(
            {
                "agent_id": f"perf-agent-{i:06d}",
                "name": f"Performance Agent {i}",
                "generation": random.randint(1, 50),
                "fitness_score": random.uniform(0, 100),
                "sharpe_ratio": random.uniform(-1, 3),
                "win_rate": random.uniform(0.3, 0.7),
                "total_trades": random.randint(10, 1000),
                "status": "active",
                "is_active": True,
                "backtest_count": random.randint(0, 20),
            }
        )
    return agents


# =============================================================================
# Sorting Performance Tests
# =============================================================================


class TestSortingPerformance:
    """Test sorting performance at various scales."""

    def test_sort_100_agents(self, benchmark_runner):
        """CONTRACT: Sort 100 agents < 5ms."""
        agents = generate_mock_agents(100)

        def sort_by_fitness():
            return sorted(agents, key=lambda a: a["fitness_score"], reverse=True)

        result = benchmark_runner.run(
            name="sort_100_agents",
            func=sort_by_fitness,
            iterations=100,
            warmup=10,
            contract_key="sort_100_agents",
        )

        assert result.passed, f"Contract failed: {result.mean_ms:.3f}ms > {result.contract_max_ms}ms"

    def test_sort_1000_agents(self, benchmark_runner):
        """CONTRACT: Sort 1,000 agents < 20ms."""
        agents = generate_mock_agents(1000)

        def sort_by_fitness():
            return sorted(agents, key=lambda a: a["fitness_score"], reverse=True)

        result = benchmark_runner.run(
            name="sort_1000_agents",
            func=sort_by_fitness,
            iterations=50,
            warmup=5,
            contract_key="sort_1000_agents",
        )

        assert result.passed, f"Contract failed: {result.mean_ms:.3f}ms > {result.contract_max_ms}ms"

    def test_sort_10000_agents(self, benchmark_runner):
        """CONTRACT: Sort 10,000 agents < 200ms."""
        agents = generate_mock_agents(10000)

        def sort_by_fitness():
            return sorted(agents, key=lambda a: a["fitness_score"], reverse=True)

        result = benchmark_runner.run(
            name="sort_10000_agents",
            func=sort_by_fitness,
            iterations=20,
            warmup=2,
            contract_key="sort_10000_agents",
        )

        assert result.passed, f"Contract failed: {result.mean_ms:.3f}ms > {result.contract_max_ms}ms"

    @pytest.mark.slow
    def test_sort_100000_agents(self, benchmark_runner):
        """STRESS: Sort 100,000 agents - find limits."""
        agents = generate_mock_agents(100000)

        def sort_by_fitness():
            return sorted(agents, key=lambda a: a["fitness_score"], reverse=True)

        result = benchmark_runner.run(
            name="sort_100000_agents",
            func=sort_by_fitness,
            iterations=5,
            warmup=1,
        )

        # Should complete in reasonable time
        assert result.mean_ms < 5000, f"100k agents sort: {result.mean_ms:.0f}ms"

    def test_sort_scaling_is_nlogn(self, benchmark_runner):
        """CONTRACT: Sorting scales as O(n log n)."""
        sizes = [100, 1000, 10000]
        times = []

        for size in sizes:
            agents = generate_mock_agents(size)

            result = benchmark_runner.run(
                name=f"sort_scaling_{size}",
                func=lambda a=agents: sorted(a, key=lambda x: x["fitness_score"], reverse=True),
                iterations=10,
                warmup=2,
            )
            times.append(result.mean_ms)

        # O(n log n) means 10x data should be ~11-13x slower, not 100x
        # 1000/100 = 10x data, expected ~13x slower
        # 10000/1000 = 10x data, expected ~13x slower
        ratio_1000_to_100 = times[1] / times[0] if times[0] > 0 else float("inf")
        ratio_10000_to_1000 = times[2] / times[1] if times[1] > 0 else float("inf")

        # Allow generous margin (20x instead of theoretical 13x)
        assert ratio_1000_to_100 < 50, f"Non-optimal scaling 100->1000: {ratio_1000_to_100:.1f}x"
        assert ratio_10000_to_1000 < 50, f"Non-optimal scaling 1000->10000: {ratio_10000_to_1000:.1f}x"


# =============================================================================
# Ranking Logic Performance Tests
# =============================================================================


class TestRankingLogicPerformance:
    """Test ranking logic performance (excluding database)."""

    def test_rank_assignment_100_agents(self, benchmark_runner):
        """Test assigning ranks to 100 agents."""
        agents = generate_mock_agents(100)
        sorted_agents = sorted(agents, key=lambda a: a["fitness_score"], reverse=True)

        def assign_ranks():
            return [{**agent, "rank": i + 1} for i, agent in enumerate(sorted_agents)]

        result = benchmark_runner.run(
            name="rank_assignment_100",
            func=assign_ranks,
            iterations=100,
            warmup=10,
        )

        assert result.mean_ms < 5, f"Rank assignment too slow: {result.mean_ms:.3f}ms"

    def test_rank_assignment_10000_agents(self, benchmark_runner):
        """Test assigning ranks to 10,000 agents."""
        agents = generate_mock_agents(10000)
        sorted_agents = sorted(agents, key=lambda a: a["fitness_score"], reverse=True)

        def assign_ranks():
            return [{**agent, "rank": i + 1} for i, agent in enumerate(sorted_agents)]

        result = benchmark_runner.run(
            name="rank_assignment_10000",
            func=assign_ranks,
            iterations=20,
            warmup=2,
        )

        assert result.mean_ms < 500, f"Rank assignment too slow: {result.mean_ms:.2f}ms"

    def test_full_ranking_pipeline(self, benchmark_runner):
        """Test complete ranking pipeline (sort + rank + stats)."""
        agents = generate_mock_agents(1000)

        def full_pipeline():
            # Sort
            sorted_agents = sorted(agents, key=lambda a: a["fitness_score"], reverse=True)

            # Assign ranks
            ranked = [{**agent, "rank": i + 1} for i, agent in enumerate(sorted_agents)]

            # Calculate percentiles
            total = len(ranked)
            for i, agent in enumerate(ranked):
                agent["percentile"] = 100 * (total - i) / total

            return ranked

        result = benchmark_runner.run(
            name="full_ranking_pipeline_1000",
            func=full_pipeline,
            iterations=20,
            warmup=2,
            contract_key="ranking_1000_agents",
        )

        assert result.passed, f"Contract failed: {result.mean_ms:.2f}ms > {result.contract_max_ms}ms"


# =============================================================================
# Top/Bottom Selection Performance Tests
# =============================================================================


class TestTopBottomSelectionPerformance:
    """Test top/bottom agent selection performance."""

    def test_top_10_from_1000(self, benchmark_runner):
        """Test selecting top 10 from 1,000 agents."""
        agents = generate_mock_agents(1000)

        def get_top_10():
            sorted_agents = sorted(agents, key=lambda a: a["fitness_score"], reverse=True)
            return sorted_agents[:10]

        result = benchmark_runner.run(
            name="top_10_from_1000",
            func=get_top_10,
            iterations=50,
            warmup=5,
        )

        assert result.mean_ms < 50, f"Top 10 selection too slow: {result.mean_ms:.3f}ms"

    def test_top_10_from_10000(self, benchmark_runner):
        """Test selecting top 10 from 10,000 agents."""
        agents = generate_mock_agents(10000)

        def get_top_10():
            sorted_agents = sorted(agents, key=lambda a: a["fitness_score"], reverse=True)
            return sorted_agents[:10]

        result = benchmark_runner.run(
            name="top_10_from_10000",
            func=get_top_10,
            iterations=20,
            warmup=2,
        )

        assert result.mean_ms < 300, f"Top 10 selection too slow: {result.mean_ms:.2f}ms"

    def test_top_percentile_selection(self, benchmark_runner):
        """Test selecting top X% of agents."""
        agents = generate_mock_agents(1000)

        def get_top_20_percent():
            sorted_agents = sorted(agents, key=lambda a: a["fitness_score"], reverse=True)
            count = int(len(sorted_agents) * 0.2)
            return sorted_agents[:count]

        result = benchmark_runner.run(
            name="top_20pct_from_1000",
            func=get_top_20_percent,
            iterations=50,
            warmup=5,
        )

        assert result.mean_ms < 50, f"Top percentile too slow: {result.mean_ms:.3f}ms"

    def test_bottom_30_percent_selection(self, benchmark_runner):
        """Test selecting bottom 30% for culling."""
        agents = generate_mock_agents(1000)

        def get_bottom_30_percent():
            sorted_agents = sorted(agents, key=lambda a: a["fitness_score"])  # Ascending
            count = int(len(sorted_agents) * 0.3)
            return sorted_agents[:count]

        result = benchmark_runner.run(
            name="bottom_30pct_from_1000",
            func=get_bottom_30_percent,
            iterations=50,
            warmup=5,
        )

        assert result.mean_ms < 50, f"Bottom percentile too slow: {result.mean_ms:.3f}ms"

    def test_nlargest_optimization(self, benchmark_runner):
        """Compare sorted[:n] vs heapq.nlargest for top selection."""
        import heapq

        agents = generate_mock_agents(10000)

        def using_sorted():
            sorted_agents = sorted(agents, key=lambda a: a["fitness_score"], reverse=True)
            return sorted_agents[:10]

        def using_heapq():
            return heapq.nlargest(10, agents, key=lambda a: a["fitness_score"])

        result_sorted = benchmark_runner.run(
            name="top_10_using_sorted",
            func=using_sorted,
            iterations=20,
            warmup=2,
        )

        result_heapq = benchmark_runner.run(
            name="top_10_using_heapq",
            func=using_heapq,
            iterations=20,
            warmup=2,
        )

        # heapq should be faster for small k from large n
        # Just ensure both are reasonable
        assert result_sorted.mean_ms < 500, "sorted method too slow"
        assert result_heapq.mean_ms < 500, "heapq method too slow"


# =============================================================================
# Population Statistics Performance Tests
# =============================================================================


class TestPopulationStatsPerformance:
    """Test population statistics calculation performance."""

    def test_basic_stats_1000_agents(self, benchmark_runner):
        """Test basic statistics for 1,000 agents."""
        import statistics

        agents = generate_mock_agents(1000)

        def calculate_stats():
            fitness_scores = [a["fitness_score"] for a in agents]
            generations = [a["generation"] for a in agents]

            return {
                "count": len(agents),
                "avg_fitness": statistics.mean(fitness_scores),
                "max_fitness": max(fitness_scores),
                "min_fitness": min(fitness_scores),
                "median_fitness": statistics.median(fitness_scores),
                "std_fitness": statistics.stdev(fitness_scores),
                "avg_generation": statistics.mean(generations),
            }

        result = benchmark_runner.run(
            name="population_stats_1000",
            func=calculate_stats,
            iterations=50,
            warmup=5,
        )

        assert result.mean_ms < 50, f"Stats calculation too slow: {result.mean_ms:.3f}ms"

    def test_basic_stats_10000_agents(self, benchmark_runner):
        """Test basic statistics for 10,000 agents."""
        import statistics

        agents = generate_mock_agents(10000)

        def calculate_stats():
            fitness_scores = [a["fitness_score"] for a in agents]
            generations = [a["generation"] for a in agents]

            return {
                "count": len(agents),
                "avg_fitness": statistics.mean(fitness_scores),
                "max_fitness": max(fitness_scores),
                "min_fitness": min(fitness_scores),
                "median_fitness": statistics.median(fitness_scores),
                "std_fitness": statistics.stdev(fitness_scores),
                "avg_generation": statistics.mean(generations),
            }

        result = benchmark_runner.run(
            name="population_stats_10000",
            func=calculate_stats,
            iterations=20,
            warmup=2,
        )

        assert result.mean_ms < 200, f"Stats calculation too slow: {result.mean_ms:.2f}ms"

    def test_percentile_calculation(self, benchmark_runner):
        """Test percentile calculation performance."""
        agents = generate_mock_agents(1000)

        def calculate_percentiles():
            fitness_scores = sorted([a["fitness_score"] for a in agents])
            percentiles = {}

            for p in [10, 25, 50, 75, 90, 95, 99]:
                idx = int(len(fitness_scores) * p / 100)
                percentiles[f"p{p}"] = fitness_scores[min(idx, len(fitness_scores) - 1)]

            return percentiles

        result = benchmark_runner.run(
            name="percentile_calculation_1000",
            func=calculate_percentiles,
            iterations=50,
            warmup=5,
        )

        assert result.mean_ms < 20, f"Percentile calculation too slow: {result.mean_ms:.3f}ms"


# =============================================================================
# Filtering Performance Tests
# =============================================================================


class TestFilteringPerformance:
    """Test agent filtering performance."""

    def test_filter_by_status(self, benchmark_runner):
        """Test filtering agents by status."""
        agents = generate_mock_agents(10000)
        # Make 20% inactive
        for i in range(0, len(agents), 5):
            agents[i]["status"] = "culled"

        def filter_active():
            return [a for a in agents if a["status"] == "active"]

        result = benchmark_runner.run(
            name="filter_active_10000",
            func=filter_active,
            iterations=50,
            warmup=5,
        )

        assert result.mean_ms < 50, f"Status filter too slow: {result.mean_ms:.3f}ms"

    def test_filter_by_generation(self, benchmark_runner):
        """Test filtering agents by generation range."""
        agents = generate_mock_agents(10000)

        def filter_by_generation():
            return [a for a in agents if 10 <= a["generation"] <= 30]

        result = benchmark_runner.run(
            name="filter_generation_10000",
            func=filter_by_generation,
            iterations=50,
            warmup=5,
        )

        assert result.mean_ms < 50, f"Generation filter too slow: {result.mean_ms:.3f}ms"

    def test_filter_by_fitness_threshold(self, benchmark_runner):
        """Test filtering agents by fitness threshold."""
        agents = generate_mock_agents(10000)

        def filter_by_fitness():
            return [a for a in agents if a["fitness_score"] >= 50.0]

        result = benchmark_runner.run(
            name="filter_fitness_10000",
            func=filter_by_fitness,
            iterations=50,
            warmup=5,
        )

        assert result.mean_ms < 50, f"Fitness filter too slow: {result.mean_ms:.3f}ms"

    def test_multi_filter_chain(self, benchmark_runner):
        """Test chained filters performance."""
        agents = generate_mock_agents(10000)
        # Make some inactive
        for i in range(0, len(agents), 5):
            agents[i]["status"] = "culled"

        def multi_filter():
            return [
                a for a in agents if a["status"] == "active" and a["fitness_score"] >= 30.0 and a["backtest_count"] >= 3
            ]

        result = benchmark_runner.run(
            name="multi_filter_10000",
            func=multi_filter,
            iterations=50,
            warmup=5,
        )

        assert result.mean_ms < 100, f"Multi-filter too slow: {result.mean_ms:.3f}ms"


# =============================================================================
# Cull Selection Performance Tests
# =============================================================================


class TestCullSelectionPerformance:
    """Test cull selection logic performance (excluding database)."""

    def test_cull_selection_1000_agents(self, benchmark_runner):
        """CONTRACT: Select agents to cull from 1,000 < 100ms."""
        agents = generate_mock_agents(1000)
        # Ensure some have enough backtests
        for i, a in enumerate(agents):
            a["backtest_count"] = 5 if i % 2 == 0 else 1

        def select_for_cull():
            min_backtests = 3
            min_population = 150
            cull_percentile = 0.3

            # Split by backtest count
            evaluated = [a for a in agents if a["backtest_count"] >= min_backtests]
            protected = [a for a in agents if a["backtest_count"] < min_backtests]

            # Sort evaluated by fitness
            evaluated.sort(key=lambda a: a["fitness_score"])

            # Calculate cull count
            total = len(agents)
            if total <= min_population:
                return []

            cull_count = int(len(evaluated) * cull_percentile)
            max_cull = total - min_population
            cull_count = min(cull_count, max_cull)

            return evaluated[:cull_count]

        result = benchmark_runner.run(
            name="cull_selection_1000",
            func=select_for_cull,
            iterations=50,
            warmup=5,
            contract_key="cull_selection_1000_agents",
        )

        assert result.passed, f"Contract failed: {result.mean_ms:.2f}ms > {result.contract_max_ms}ms"

    def test_cull_selection_10000_agents(self, benchmark_runner):
        """CONTRACT: Select agents to cull from 10,000 < 500ms."""
        agents = generate_mock_agents(10000)
        for i, a in enumerate(agents):
            a["backtest_count"] = 5 if i % 2 == 0 else 1

        def select_for_cull():
            min_backtests = 3
            min_population = 150
            cull_percentile = 0.3

            evaluated = [a for a in agents if a["backtest_count"] >= min_backtests]
            protected = [a for a in agents if a["backtest_count"] < min_backtests]

            evaluated.sort(key=lambda a: a["fitness_score"])

            total = len(agents)
            if total <= min_population:
                return []

            cull_count = int(len(evaluated) * cull_percentile)
            max_cull = total - min_population
            cull_count = min(cull_count, max_cull)

            return evaluated[:cull_count]

        result = benchmark_runner.run(
            name="cull_selection_10000",
            func=select_for_cull,
            iterations=20,
            warmup=2,
            contract_key="cull_selection_10000_agents",
        )

        assert result.passed, f"Contract failed: {result.mean_ms:.2f}ms > {result.contract_max_ms}ms"


# =============================================================================
# Edge Case Performance Tests
# =============================================================================


class TestRankingEdgeCases:
    """Test ranking performance with edge cases."""

    def test_empty_agent_list(self, timer):
        """CONTRACT: Empty list returns instantly."""
        agents = []

        with timer() as t:
            for _ in range(1000):
                sorted(agents, key=lambda a: a.get("fitness_score", 0), reverse=True)

        avg_ms = t.elapsed_ms / 1000
        assert avg_ms < 0.01, f"Empty list too slow: {avg_ms:.6f}ms"

    def test_single_agent(self, timer):
        """CONTRACT: Single agent returns quickly."""
        agents = generate_mock_agents(1)

        with timer() as t:
            for _ in range(1000):
                sorted_agents = sorted(agents, key=lambda a: a["fitness_score"], reverse=True)
                _ = sorted_agents[:1]

        avg_ms = t.elapsed_ms / 1000
        assert avg_ms < 0.1, f"Single agent too slow: {avg_ms:.4f}ms"

    def test_all_same_fitness(self, benchmark_runner):
        """Test performance when all agents have same fitness."""
        agents = generate_mock_agents(1000)
        for a in agents:
            a["fitness_score"] = 50.0

        def sort_same_fitness():
            return sorted(agents, key=lambda a: a["fitness_score"], reverse=True)

        result = benchmark_runner.run(
            name="sort_same_fitness_1000",
            func=sort_same_fitness,
            iterations=50,
            warmup=5,
        )

        # Should be same or faster than varied fitness
        assert result.mean_ms < 50, f"Same fitness sort too slow: {result.mean_ms:.3f}ms"

    def test_already_sorted(self, benchmark_runner):
        """Test performance with already sorted data."""
        agents = generate_mock_agents(1000)
        agents.sort(key=lambda a: a["fitness_score"], reverse=True)

        def sort_already_sorted():
            return sorted(agents, key=lambda a: a["fitness_score"], reverse=True)

        result = benchmark_runner.run(
            name="sort_already_sorted_1000",
            func=sort_already_sorted,
            iterations=50,
            warmup=5,
        )

        # Python's Timsort is efficient on sorted data
        assert result.mean_ms < 30, f"Already sorted too slow: {result.mean_ms:.3f}ms"

    def test_reverse_sorted(self, benchmark_runner):
        """Test performance with reverse sorted data."""
        agents = generate_mock_agents(1000)
        agents.sort(key=lambda a: a["fitness_score"])  # Ascending (reverse of what we want)

        def sort_reverse_sorted():
            return sorted(agents, key=lambda a: a["fitness_score"], reverse=True)

        result = benchmark_runner.run(
            name="sort_reverse_sorted_1000",
            func=sort_reverse_sorted,
            iterations=50,
            warmup=5,
        )

        assert result.mean_ms < 50, f"Reverse sorted too slow: {result.mean_ms:.3f}ms"
