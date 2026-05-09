"""
Performance Test Configuration - Fixtures and utilities for stress testing.

MASTER TEST ADMIN: "Speed is a feature. Measure it."
"""

import functools
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

# =============================================================================
# Performance Contracts (SLOs)
# =============================================================================

PERFORMANCE_CONTRACTS = {
    # Fitness calculations
    "fitness_10_trades": {"max_ms": 10, "description": "Fitness with 10 trades"},
    "fitness_100_trades": {"max_ms": 50, "description": "Fitness with 100 trades"},
    "fitness_1000_trades": {"max_ms": 200, "description": "Fitness with 1,000 trades"},
    "fitness_10000_trades": {"max_ms": 1000, "description": "Fitness with 10,000 trades"},
    # Ranking operations
    "ranking_100_agents": {"max_ms": 50, "description": "Rank 100 agents"},
    "ranking_1000_agents": {"max_ms": 100, "description": "Rank 1,000 agents"},
    "ranking_10000_agents": {"max_ms": 500, "description": "Rank 10,000 agents"},
    # Culling operations
    "cull_selection_1000_agents": {"max_ms": 100, "description": "Select agents to cull from 1,000"},
    "cull_selection_10000_agents": {"max_ms": 500, "description": "Select agents to cull from 10,000"},
    # Sorting operations
    "sort_100_agents": {"max_ms": 5, "description": "Sort 100 agents by fitness"},
    "sort_1000_agents": {"max_ms": 20, "description": "Sort 1,000 agents by fitness"},
    "sort_10000_agents": {"max_ms": 200, "description": "Sort 10,000 agents by fitness"},
    # Trait operations
    "trait_generation": {"max_ms": 1, "description": "Generate full trait set"},
    "trait_crossover": {"max_ms": 1, "description": "Crossover two trait sets"},
    "trait_mutation_batch_100": {"max_ms": 10, "description": "Mutate 100 trait sets"},
    # Evolution cycle (excluding database)
    "evolution_selection_1000": {"max_ms": 200, "description": "Select breeders/survivors from 1,000"},
    # Memory limits (in MB)
    "memory_1000_agents": {"max_mb": 50, "description": "Memory for 1,000 agent objects"},
    "memory_10000_agents": {"max_mb": 500, "description": "Memory for 10,000 agent objects"},
    "memory_100000_trades": {"max_mb": 100, "description": "Memory for 100,000 trade objects"},
}


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""

    name: str
    duration_ms: float
    iterations: int
    mean_ms: float
    min_ms: float
    max_ms: float
    std_ms: float
    contract_max_ms: float
    passed: bool
    memory_mb: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BenchmarkRunner:
    """Utility for running and recording benchmarks."""

    def __init__(self):
        self.results: list[BenchmarkResult] = []
        self.results_file = Path(__file__).parent / "benchmark_results.json"

    def run(
        self,
        name: str,
        func: Callable,
        iterations: int = 10,
        warmup: int = 2,
        contract_key: str = None,
    ) -> BenchmarkResult:
        """
        Run a benchmark with warmup and multiple iterations.

        Args:
            name: Benchmark name
            func: Function to benchmark (must be callable with no args)
            iterations: Number of timed iterations
            warmup: Number of warmup iterations (not timed)
            contract_key: Key in PERFORMANCE_CONTRACTS for SLO comparison

        Returns:
            BenchmarkResult with timing data
        """
        # Warmup
        for _ in range(warmup):
            func()

        # Timed runs
        times = []
        for _ in range(iterations):
            start = time.perf_counter()
            func()
            elapsed = (time.perf_counter() - start) * 1000  # Convert to ms
            times.append(elapsed)

        # Calculate stats
        import statistics

        mean_ms = statistics.mean(times)
        min_ms = min(times)
        max_ms = max(times)
        std_ms = statistics.stdev(times) if len(times) > 1 else 0.0
        total_ms = sum(times)

        # Check contract
        contract_max = float("inf")
        if contract_key and contract_key in PERFORMANCE_CONTRACTS:
            contract_max = PERFORMANCE_CONTRACTS[contract_key]["max_ms"]

        result = BenchmarkResult(
            name=name,
            duration_ms=total_ms,
            iterations=iterations,
            mean_ms=mean_ms,
            min_ms=min_ms,
            max_ms=max_ms,
            std_ms=std_ms,
            contract_max_ms=contract_max,
            passed=mean_ms <= contract_max,
        )

        self.results.append(result)
        return result

    def save_results(self):
        """Save all benchmark results to JSON file."""
        existing = []
        if self.results_file.exists():
            try:
                existing = json.loads(self.results_file.read_text())
            except json.JSONDecodeError:
                existing = []

        # Add new results
        existing.extend([r.to_dict() for r in self.results])

        # Keep last 100 results
        existing = existing[-100:]

        self.results_file.write_text(json.dumps(existing, indent=2))


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def benchmark_runner():
    """Provide a benchmark runner instance."""
    runner = BenchmarkRunner()
    yield runner
    # Save results after test
    runner.save_results()


@pytest.fixture
def performance_contracts():
    """Provide performance contracts for reference."""
    return PERFORMANCE_CONTRACTS


@pytest.fixture
def large_trade_list():
    """Generate a large list of trades for stress testing."""

    def _generate(count: int):
        import random

        random.seed(42)  # Deterministic

        from Tests.Fixtures.factories import create_trade_data

        trades = []
        for i in range(count):
            pnl_pct = random.gauss(0.5, 3.0)  # Mean 0.5%, std 3%
            trades.append(
                create_trade_data(
                    pnl=pnl_pct * 1000,  # Assuming $100k position
                    pnl_pct=pnl_pct,
                    is_win=pnl_pct > 0,
                )
            )
        return trades

    return _generate


@pytest.fixture
def large_agent_list():
    """Generate a large list of mock agents for stress testing."""

    def _generate(count: int):
        import random

        random.seed(42)  # Deterministic

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
                    "traits": {f"trait_{j}": random.random() for j in range(22)},
                }
            )
        return agents

    return _generate


@pytest.fixture
def timer():
    """Simple timer context manager for inline timing."""

    @dataclass
    class Timer:
        start_time: float = 0.0
        end_time: float = 0.0
        elapsed_ms: float = 0.0

        def __enter__(self):
            self.start_time = time.perf_counter()
            return self

        def __exit__(self, *args):
            self.end_time = time.perf_counter()
            self.elapsed_ms = (self.end_time - self.start_time) * 1000

    return Timer


# =============================================================================
# Decorators
# =============================================================================


def performance_test(contract_key: str = None, max_ms: float = None):
    """
    Decorator to mark a test as a performance test with optional SLO.

    Usage:
        @performance_test(contract_key="fitness_1000_trades")
        def test_fitness_performance():
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000

            # Check contract
            limit = max_ms
            if contract_key and contract_key in PERFORMANCE_CONTRACTS:
                limit = PERFORMANCE_CONTRACTS[contract_key]["max_ms"]

            if limit is not None:
                assert elapsed_ms <= limit, f"Performance contract violated: {elapsed_ms:.2f}ms > {limit}ms"

            return result

        # Mark as performance test
        wrapper._performance_test = True
        wrapper._contract_key = contract_key
        return wrapper

    return decorator


def skip_if_slow():
    """Skip performance tests if running in quick mode."""
    return (
        pytest.mark.skipif(
            pytest.config.getoption("--quick", default=False), reason="Skipping slow performance tests in quick mode"
        )
        if hasattr(pytest, "config")
        else lambda f: f
    )
