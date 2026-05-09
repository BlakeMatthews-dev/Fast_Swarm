"""
Singleton Safety Tests - RACE CONDITION HUNTER

MASTER TEST ADMIN DECREE: Global singletons must be thread-safe.
These tests verify that shared state doesn't leak between requests.

"Parallelism is a lie; timing is the truth."
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from Agents.Services.fitness_service import calculate_fitness
from Tests.Fixtures.factories import TradeFactory

# =============================================================================
# TEST: Fitness Calculation Thread Safety
# =============================================================================


class TestFitnessThreadSafety:
    """CONTRACT: Fitness calculation must be thread-safe."""

    @pytest.mark.concurrency
    def test_concurrent_fitness_calculations(self):
        """
        CONCURRENCY: Multiple threads calling calculate_fitness simultaneously.

        Each calculation should be independent - no shared state corruption.
        """
        num_threads = 10
        iterations_per_thread = 50
        results: list[float] = []
        errors: list[Exception] = []

        def run_fitness_calculations(thread_id: int):
            """Worker function for each thread."""
            thread_results = []
            try:
                for i in range(iterations_per_thread):
                    # Each thread uses its own trade data
                    trades = TradeFactory.create_batch(
                        count=20,
                        seed=thread_id * 1000 + i,  # Unique seed per iteration
                    )
                    result = calculate_fitness(trades)
                    thread_results.append(result.fitness_score)
            except Exception as e:
                errors.append(e)
            return thread_results

        # Run in parallel
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(run_fitness_calculations, i) for i in range(num_threads)]
            for future in as_completed(futures):
                results.extend(future.result())

        # No errors should have occurred
        assert len(errors) == 0, f"Thread errors: {errors}"

        # All results should be valid
        assert len(results) == num_threads * iterations_per_thread
        for score in results:
            assert 0.0 <= score <= 100.0, f"Invalid score {score}"

    @pytest.mark.concurrency
    def test_deterministic_under_concurrency(self):
        """
        CONCURRENCY: Same inputs produce same outputs even under concurrent load.
        """
        # Fixed trade data
        trades = TradeFactory.create_batch(count=30, seed=42)

        # Calculate expected result
        expected = calculate_fitness(trades).fitness_score

        # Run many concurrent calculations with same input
        num_threads = 20
        results: list[float] = []

        def calculate():
            result = calculate_fitness(trades)
            return result.fitness_score

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(calculate) for _ in range(100)]
            for future in as_completed(futures):
                results.append(future.result())

        # All results must match expected
        for score in results:
            assert score == expected, f"Non-deterministic: {score} != {expected}"


# =============================================================================
# TEST: Async Safety
# =============================================================================


class TestAsyncSafety:
    """CONTRACT: Calculations must be safe under async concurrency."""

    @pytest.mark.concurrency
    @pytest.mark.asyncio
    async def test_async_concurrent_fitness(self):
        """
        CONCURRENCY: Multiple async tasks calling fitness simultaneously.
        """
        num_tasks = 50
        results: list[float] = []

        async def async_fitness(task_id: int):
            """Async wrapper around fitness calculation."""
            trades = TradeFactory.create_batch(count=15, seed=task_id)
            # Run CPU-bound work in executor
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                calculate_fitness,
                trades,
            )
            return result.fitness_score

        # Run all tasks concurrently
        tasks = [async_fitness(i) for i in range(num_tasks)]
        results = await asyncio.gather(*tasks)

        # All results should be valid
        assert len(results) == num_tasks
        for score in results:
            assert 0.0 <= score <= 100.0

    @pytest.mark.concurrency
    @pytest.mark.asyncio
    async def test_async_determinism(self):
        """
        CONCURRENCY: Same inputs produce same outputs under async load.
        """
        trades = TradeFactory.create_batch(count=25, seed=123)
        expected = calculate_fitness(trades).fitness_score

        async def async_fitness():
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, calculate_fitness, trades)
            return result.fitness_score

        # Many concurrent async calculations
        tasks = [async_fitness() for _ in range(100)]
        results = await asyncio.gather(*tasks)

        # All must match
        for score in results:
            assert score == expected


# =============================================================================
# TEST: No State Leakage
# =============================================================================


class TestNoStateLeakage:
    """CONTRACT: No state leaks between calculations."""

    @pytest.mark.concurrency
    def test_independent_calculations(self):
        """
        CONCURRENCY: One calculation doesn't affect another.
        """
        # First calculation with positive trades
        positive_trades = TradeFactory.all_winners(count=20)
        result1 = calculate_fitness(positive_trades)

        # Second calculation with negative trades
        negative_trades = TradeFactory.all_losers(count=20)
        result2 = calculate_fitness(negative_trades)

        # Third calculation same as first - should match
        result3 = calculate_fitness(positive_trades)

        # Results should be deterministic regardless of order
        assert result1.fitness_score == result3.fitness_score, (
            "First and third calculations don't match - state leakage!"
        )

    @pytest.mark.concurrency
    def test_interleaved_calculations(self):
        """
        CONCURRENCY: Interleaved calculations produce correct results.
        """
        trades_a = TradeFactory.create_batch(count=30, seed=111)
        trades_b = TradeFactory.create_batch(count=30, seed=222)

        # Calculate expected values
        expected_a = calculate_fitness(trades_a).fitness_score
        expected_b = calculate_fitness(trades_b).fitness_score

        # Interleave calculations
        results_a = []
        results_b = []
        for _ in range(20):
            results_a.append(calculate_fitness(trades_a).fitness_score)
            results_b.append(calculate_fitness(trades_b).fitness_score)

        # All should match expected
        for score in results_a:
            assert score == expected_a
        for score in results_b:
            assert score == expected_b


# =============================================================================
# TEST: Memory Safety Under Load
# =============================================================================


class TestMemorySafetyUnderLoad:
    """CONTRACT: No memory leaks under sustained concurrent load."""

    @pytest.mark.concurrency
    @pytest.mark.slow
    def test_sustained_concurrent_load(self):
        """
        CONCURRENCY: System handles sustained concurrent load without degradation.

        Note: This test is marked slow - run with pytest -m slow
        """
        import gc

        num_threads = 5
        iterations = 100
        initial_objects = len(gc.get_objects())

        def workload(thread_id: int):
            for i in range(iterations):
                trades = TradeFactory.create_batch(count=50, seed=thread_id * iterations + i)
                result = calculate_fitness(trades)
                assert 0.0 <= result.fitness_score <= 100.0

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(workload, i) for i in range(num_threads)]
            for future in as_completed(futures):
                future.result()  # Raise any exceptions

        # Force garbage collection
        gc.collect()

        # Check for memory leaks (allow some growth but not excessive)
        final_objects = len(gc.get_objects())
        growth = final_objects - initial_objects

        # Allow up to 10% growth
        max_allowed_growth = initial_objects * 0.1
        assert growth < max_allowed_growth, f"Possible memory leak: {growth} new objects (max {max_allowed_growth})"
