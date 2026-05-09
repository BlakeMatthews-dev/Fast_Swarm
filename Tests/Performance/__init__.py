"""
Performance Testing Module - Stress tests and benchmarks for Fast_Swarm.

MASTER TEST ADMIN: "If you don't measure it, you can't improve it."

This module contains:
- test_fitness_scaling.py: Fitness calculation performance at various trade counts
- test_ranking_scaling.py: Agent ranking and sorting performance
- test_memory_profiling.py: Memory usage and leak detection
- test_trait_scaling.py: Trait generation, mutation, crossover performance

Performance Contracts (SLOs):
- Fitness with 1,000 trades: < 200ms
- Ranking 10,000 agents: < 500ms
- Trait generation: < 1ms
- Memory for 10,000 agents: < 500MB

Run all performance tests:
    pytest Tests/Performance/ -v

Run with timing details:
    pytest Tests/Performance/ -v --durations=0

Skip slow tests:
    pytest Tests/Performance/ -v -m "not slow"
"""

from .conftest import (
    PERFORMANCE_CONTRACTS,
    BenchmarkResult,
    BenchmarkRunner,
    performance_test,
)

__all__ = [
    "PERFORMANCE_CONTRACTS",
    "BenchmarkResult",
    "BenchmarkRunner",
    "performance_test",
]
