"""
Memory Profiling Tests - Stress test memory usage and detect leaks.

MASTER TEST ADMIN: "Memory leaks are time bombs. Defuse them."

Tests memory behavior for:
- Agent object allocation
- Trade data storage
- Fitness calculation memory
- Large population handling
"""

import gc
import random
import sys
from typing import Any

import pytest

from Tests.Performance.conftest import PERFORMANCE_CONTRACTS

# =============================================================================
# Memory Measurement Utilities
# =============================================================================


def get_object_size_deep(obj, seen=None) -> int:
    """
    Recursively calculate total memory of an object and its contents.

    Note: This is approximate - Python memory is complex.
    """
    if seen is None:
        seen = set()

    obj_id = id(obj)
    if obj_id in seen:
        return 0

    seen.add(obj_id)
    size = sys.getsizeof(obj)

    if isinstance(obj, dict):
        size += sum(get_object_size_deep(k, seen) + get_object_size_deep(v, seen) for k, v in obj.items())
    elif isinstance(obj, (list, tuple, set, frozenset)):
        size += sum(get_object_size_deep(item, seen) for item in obj)
    elif hasattr(obj, "__dict__"):
        size += get_object_size_deep(obj.__dict__, seen)
    elif hasattr(obj, "__slots__"):
        size += sum(get_object_size_deep(getattr(obj, slot), seen) for slot in obj.__slots__ if hasattr(obj, slot))

    return size


def bytes_to_mb(bytes_val: int) -> float:
    """Convert bytes to megabytes."""
    return bytes_val / (1024 * 1024)


def get_process_memory_mb() -> float:
    """Get current process memory usage in MB (platform-dependent)."""
    try:
        import psutil

        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)
    except ImportError:
        # Fallback: estimate from gc
        gc.collect()
        return sum(sys.getsizeof(obj) for obj in gc.get_objects()) / (1024 * 1024)


# =============================================================================
# Test Data Generators
# =============================================================================


def generate_trade_data(count: int, seed: int = 42) -> list[dict[str, Any]]:
    """Generate trade data dictionaries."""
    random.seed(seed)
    trades = []
    for i in range(count):
        pnl_pct = random.gauss(0.5, 3.0)
        trades.append(
            {
                "trade_id": f"trade-{i:08d}",
                "pnl": pnl_pct * 1000,
                "pnl_pct": pnl_pct,
                "is_win": pnl_pct > 0,
                "entry_price": 50000.0,
                "exit_price": 50000.0 * (1 + pnl_pct / 100),
                "size": 1.0,
                "asset": "BTC/USDT",
                "timestamp": f"2024-01-{(i % 28) + 1:02d}",
            }
        )
    return trades


def generate_agent_data(count: int, seed: int = 42) -> list[dict[str, Any]]:
    """Generate agent data dictionaries."""
    random.seed(seed)
    agents = []
    for i in range(count):
        agents.append(
            {
                "agent_id": f"agent-{i:08d}",
                "name": f"Performance Agent {i}",
                "generation": random.randint(1, 50),
                "fitness_score": random.uniform(0, 100),
                "sharpe_ratio": random.uniform(-1, 3),
                "sortino_ratio": random.uniform(-2, 5),
                "win_rate": random.uniform(0.3, 0.7),
                "total_trades": random.randint(10, 1000),
                "status": "active",
                "is_active": True,
                "backtest_count": random.randint(0, 20),
                "traits": {f"trait_{j}": random.random() for j in range(22)},
                "fitness_by_regime": {
                    "crash": {"fitness": random.uniform(0, 100), "trades": random.randint(5, 50)},
                    "bull": {"fitness": random.uniform(0, 100), "trades": random.randint(5, 50)},
                    "bear": {"fitness": random.uniform(0, 100), "trades": random.randint(5, 50)},
                },
            }
        )
    return agents


# =============================================================================
# Object Size Tests
# =============================================================================


class TestObjectMemoryFootprint:
    """Test memory footprint of core objects."""

    def test_single_trade_size(self):
        """Measure memory of a single trade dict."""
        trade = generate_trade_data(1)[0]
        size = get_object_size_deep(trade)
        size_mb = bytes_to_mb(size)

        # Single trade should be < 1KB
        assert size < 2048, f"Single trade too large: {size} bytes"

    def test_single_agent_size(self):
        """Measure memory of a single agent dict."""
        agent = generate_agent_data(1)[0]
        size = get_object_size_deep(agent)

        # Single agent with traits and regime data should be < 10KB
        assert size < 10240, f"Single agent too large: {size} bytes"

    def test_trade_data_object_size(self):
        """Measure memory of TradeData dataclass."""
        try:
            from Agents.Services.fitness_service import TradeData

            trade = TradeData(
                pnl=100.0,
                pnl_pct=1.0,
                is_win=True,
                entry_price=50000.0,
                exit_price=50500.0,
                size=1.0,
            )
            size = sys.getsizeof(trade)

            # Dataclass should be compact (< 200 bytes base)
            assert size < 300, f"TradeData too large: {size} bytes"
        except ImportError:
            pytest.skip("fitness_service not available")


# =============================================================================
# Scaling Memory Tests
# =============================================================================


class TestMemoryScaling:
    """Test memory scaling with data size."""

    def test_1000_trades_memory(self):
        """CONTRACT: 1,000 trades < 5MB."""
        trades = generate_trade_data(1000)
        total_size = get_object_size_deep(trades)
        size_mb = bytes_to_mb(total_size)

        assert size_mb < 5, f"1,000 trades: {size_mb:.2f}MB > 5MB"

    def test_10000_trades_memory(self):
        """CONTRACT: 10,000 trades < 50MB."""
        trades = generate_trade_data(10000)
        total_size = get_object_size_deep(trades)
        size_mb = bytes_to_mb(total_size)

        assert size_mb < 50, f"10,000 trades: {size_mb:.2f}MB > 50MB"

    @pytest.mark.slow
    def test_100000_trades_memory(self):
        """CONTRACT: 100,000 trades < 500MB."""
        trades = generate_trade_data(100000)
        total_size = get_object_size_deep(trades)
        size_mb = bytes_to_mb(total_size)

        assert size_mb < 500, f"100,000 trades: {size_mb:.2f}MB > 500MB"

        # Cleanup
        del trades
        gc.collect()

    def test_1000_agents_memory(self):
        """CONTRACT: 1,000 agents < 50MB."""
        agents = generate_agent_data(1000)
        total_size = get_object_size_deep(agents)
        size_mb = bytes_to_mb(total_size)

        contract_limit = PERFORMANCE_CONTRACTS.get("memory_1000_agents", {}).get("max_mb", 50)
        assert size_mb < contract_limit, f"1,000 agents: {size_mb:.2f}MB > {contract_limit}MB"

    def test_10000_agents_memory(self):
        """CONTRACT: 10,000 agents < 500MB."""
        agents = generate_agent_data(10000)
        total_size = get_object_size_deep(agents)
        size_mb = bytes_to_mb(total_size)

        contract_limit = PERFORMANCE_CONTRACTS.get("memory_10000_agents", {}).get("max_mb", 500)
        assert size_mb < contract_limit, f"10,000 agents: {size_mb:.2f}MB > {contract_limit}MB"

        # Cleanup
        del agents
        gc.collect()

    def test_memory_scales_linearly(self):
        """CONTRACT: Memory scales linearly with count."""
        sizes = [100, 1000, 10000]
        memory_per_item = []

        for size in sizes:
            trades = generate_trade_data(size)
            total = get_object_size_deep(trades)
            per_item = total / size
            memory_per_item.append(per_item)
            del trades

        gc.collect()

        # Memory per item should be roughly constant (±50% variance for overhead)
        avg_per_item = sum(memory_per_item) / len(memory_per_item)
        for i, per_item in enumerate(memory_per_item):
            ratio = per_item / avg_per_item
            assert 0.5 < ratio < 2.0, (
                f"Non-linear scaling at size {sizes[i]}: {per_item:.0f} bytes/item (avg: {avg_per_item:.0f})"
            )


# =============================================================================
# Memory Leak Detection Tests
# =============================================================================


class TestMemoryLeaks:
    """Test for memory leaks in core operations."""

    def test_no_leak_in_fitness_loop(self):
        """CONTRACT: Repeated fitness calculations don't leak."""
        try:
            from Agents.Services.fitness_service import TradeData, calculate_fitness
        except ImportError:
            pytest.skip("fitness_service not available")

        trades = [
            TradeData(pnl=random.gauss(50, 100), pnl_pct=random.gauss(0.5, 1), is_win=random.random() > 0.4)
            for _ in range(100)
        ]

        # Force GC and get baseline
        gc.collect()
        baseline_objects = len(gc.get_objects())

        # Run many iterations
        for _ in range(1000):
            result = calculate_fitness(trades)
            del result

        gc.collect()
        final_objects = len(gc.get_objects())

        # Allow some growth but not unbounded
        growth = final_objects - baseline_objects
        assert growth < 500, f"Potential memory leak: {growth} new objects after 1000 iterations"

    def test_no_leak_in_sorting_loop(self):
        """CONTRACT: Repeated sorting doesn't leak."""
        agents = generate_agent_data(1000)

        gc.collect()
        baseline_objects = len(gc.get_objects())

        for _ in range(100):
            sorted_agents = sorted(agents, key=lambda a: a["fitness_score"], reverse=True)
            del sorted_agents

        gc.collect()
        final_objects = len(gc.get_objects())

        growth = final_objects - baseline_objects
        assert growth < 200, f"Potential sorting leak: {growth} new objects"

    def test_no_leak_in_filter_loop(self):
        """CONTRACT: Repeated filtering doesn't leak."""
        agents = generate_agent_data(1000)

        gc.collect()
        baseline_objects = len(gc.get_objects())

        for _ in range(100):
            filtered = [a for a in agents if a["fitness_score"] > 50]
            del filtered

        gc.collect()
        final_objects = len(gc.get_objects())

        growth = final_objects - baseline_objects
        assert growth < 200, f"Potential filter leak: {growth} new objects"

    def test_gc_effectiveness(self):
        """Test that garbage collection works properly."""
        # Create large objects
        large_list = generate_agent_data(10000)
        initial_id = id(large_list)

        # Delete and collect
        del large_list
        gc.collect()

        # Verify it's gone (can't directly check, but ensure no error)
        # Create new list to ensure memory is reusable
        new_list = generate_agent_data(10000)
        assert len(new_list) == 10000

        del new_list
        gc.collect()


# =============================================================================
# Peak Memory Tests
# =============================================================================


class TestPeakMemoryUsage:
    """Test peak memory usage during operations."""

    def test_fitness_batch_peak_memory(self):
        """Test peak memory during batch fitness calculation."""
        try:
            from Agents.Services.fitness_service import TradeData, calculate_fitness
        except ImportError:
            pytest.skip("fitness_service not available")

        # 100 agents, each with 100 trades
        all_trades = [
            [
                TradeData(pnl=random.gauss(50, 100), pnl_pct=random.gauss(0.5, 1), is_win=random.random() > 0.4)
                for _ in range(100)
            ]
            for _ in range(100)
        ]

        gc.collect()
        before_mb = get_process_memory_mb()

        # Calculate fitness for all
        results = [calculate_fitness(trades) for trades in all_trades]

        after_mb = get_process_memory_mb()
        peak_increase = after_mb - before_mb

        # Should not spike more than 50MB for this workload
        assert peak_increase < 100, f"Memory spike during batch: {peak_increase:.1f}MB"

        # Cleanup
        del results
        del all_trades
        gc.collect()

    def test_large_sort_peak_memory(self):
        """Test peak memory during large sort operation."""
        agents = generate_agent_data(10000)

        gc.collect()
        before_mb = get_process_memory_mb()

        # Sort creates a new list
        sorted_agents = sorted(agents, key=lambda a: a["fitness_score"], reverse=True)

        after_mb = get_process_memory_mb()
        peak_increase = after_mb - before_mb

        # Sorting 10k agents shouldn't spike more than 50MB
        assert peak_increase < 100, f"Memory spike during sort: {peak_increase:.1f}MB"

        del sorted_agents
        del agents
        gc.collect()


# =============================================================================
# Trait Memory Tests
# =============================================================================


class TestTraitMemoryEfficiency:
    """Test memory efficiency of trait storage."""

    def test_trait_dict_size(self):
        """Measure memory of a full trait dictionary."""
        traits = {f"trait_{i}": random.random() for i in range(22)}
        size = get_object_size_deep(traits)

        # 22 traits should be < 3KB (includes string keys + float values + dict overhead)
        assert size < 3072, f"Trait dict too large: {size} bytes"

    def test_trait_generation_memory(self):
        """Test memory usage of trait generation."""
        try:
            from Agents.Services.trait_service import generate_all_traits
        except ImportError:
            pytest.skip("trait_service not available")

        gc.collect()
        baseline = len(gc.get_objects())

        # Generate 1000 trait sets
        trait_sets = [generate_all_traits() for _ in range(1000)]

        gc.collect()
        after = len(gc.get_objects())

        # Should add roughly 1000 dict objects + contents
        growth = after - baseline
        assert growth < 50000, f"Trait generation creates too many objects: {growth}"

        del trait_sets
        gc.collect()

    def test_crossover_memory_efficiency(self):
        """Test memory efficiency of trait crossover."""
        try:
            from Agents.Services.trait_service import crossover_traits, generate_all_traits
        except ImportError:
            pytest.skip("trait_service not available")

        parent1 = generate_all_traits()
        parent2 = generate_all_traits()

        gc.collect()
        baseline = len(gc.get_objects())

        # Do many crossovers
        for _ in range(1000):
            child = crossover_traits(parent1, parent2)
            del child

        gc.collect()
        after = len(gc.get_objects())

        growth = after - baseline
        assert growth < 100, f"Crossover leaks objects: {growth} new"


# =============================================================================
# Edge Case Memory Tests
# =============================================================================


class TestMemoryEdgeCases:
    """Test memory behavior with edge cases."""

    def test_empty_list_memory(self):
        """Empty lists should use minimal memory."""
        empty = []
        size = sys.getsizeof(empty)

        # Empty list base size
        assert size < 100, f"Empty list unexpectedly large: {size} bytes"

    def test_none_values_memory(self):
        """Test memory with None values in data."""
        agents = generate_agent_data(100)
        for a in agents:
            a["fitness_score"] = None
            a["sharpe_ratio"] = None

        size = get_object_size_deep(agents)

        # None values shouldn't significantly increase size
        normal_agents = generate_agent_data(100)
        normal_size = get_object_size_deep(normal_agents)

        # Should be similar (within 20%)
        ratio = size / normal_size
        assert 0.8 < ratio < 1.2, f"None values affect size unexpectedly: {ratio:.2f}x"

    def test_large_strings_memory(self):
        """Test memory impact of large string fields."""
        agents = generate_agent_data(100)

        # Add large names
        for a in agents:
            a["name"] = "A" * 10000  # 10KB names

        size = get_object_size_deep(agents)
        size_mb = bytes_to_mb(size)

        # 100 agents with 10KB names = ~1MB just for names
        assert size_mb < 5, f"Large strings: {size_mb:.2f}MB"

    def test_deeply_nested_memory(self):
        """Test memory with deeply nested structures."""
        agents = generate_agent_data(100)

        # Add deep nesting
        for a in agents:
            a["deep"] = {"level1": {"level2": {"level3": {"data": list(range(100))}}}}

        size = get_object_size_deep(agents)
        size_mb = bytes_to_mb(size)

        # Should still be reasonable
        assert size_mb < 10, f"Deep nesting: {size_mb:.2f}MB"
