"""
Fitness Calculation Performance Tests - Stress test the 100-point fitness model.

MASTER TEST ADMIN: "If it's slow with 10 trades, it's dead with 10,000."

Tests scaling behavior of fitness calculations:
- 10 trades (baseline)
- 100 trades (typical)
- 1,000 trades (heavy user)
- 10,000 trades (stress test)
- 100,000 trades (breaking point)
"""

import random
import sys

import pytest

# Import fitness calculation functions
try:
    from Agents.Services.fitness_service import (
        TradeData,
        calculate_ev,
        calculate_ev_multiplier,
        calculate_fitness,
    )

    FITNESS_SERVICE_AVAILABLE = True
except ImportError:
    FITNESS_SERVICE_AVAILABLE = False


# =============================================================================
# Test Data Generators
# =============================================================================


def generate_trades(count: int, seed: int = 42) -> list[TradeData]:
    """Generate deterministic trade data for benchmarking."""
    random.seed(seed)
    trades = []
    for _ in range(count):
        pnl_pct = random.gauss(0.5, 3.0)  # Mean 0.5%, std 3%
        pnl = pnl_pct * 1000  # Assuming $100k position
        trades.append(
            TradeData(
                pnl=pnl,
                pnl_pct=pnl_pct,
                is_win=pnl_pct > 0,
                entry_price=50000.0,
                exit_price=50000.0 * (1 + pnl_pct / 100),
                size=1.0,
            )
        )
    return trades


# =============================================================================
# EV Calculation Scaling Tests
# =============================================================================


class TestEVCalculationScaling:
    """Test EV calculation performance at various scales."""

    def test_ev_10_trades(self, benchmark_runner):
        """Baseline: EV calculation with 10 trades."""
        trades = generate_trades(10)

        result = benchmark_runner.run(
            name="EV_10_trades",
            func=lambda: calculate_ev(trades),
            iterations=100,
            warmup=10,
        )

        assert result.mean_ms < 1.0, f"EV for 10 trades too slow: {result.mean_ms:.3f}ms"

    def test_ev_100_trades(self, benchmark_runner):
        """Typical: EV calculation with 100 trades."""
        trades = generate_trades(100)

        result = benchmark_runner.run(
            name="EV_100_trades",
            func=lambda: calculate_ev(trades),
            iterations=100,
            warmup=10,
        )

        assert result.mean_ms < 5.0, f"EV for 100 trades too slow: {result.mean_ms:.3f}ms"

    def test_ev_1000_trades(self, benchmark_runner):
        """Heavy: EV calculation with 1,000 trades."""
        trades = generate_trades(1000)

        result = benchmark_runner.run(
            name="EV_1000_trades",
            func=lambda: calculate_ev(trades),
            iterations=50,
            warmup=5,
        )

        assert result.mean_ms < 20.0, f"EV for 1,000 trades too slow: {result.mean_ms:.3f}ms"

    def test_ev_10000_trades(self, benchmark_runner):
        """Stress: EV calculation with 10,000 trades."""
        trades = generate_trades(10000)

        result = benchmark_runner.run(
            name="EV_10000_trades",
            func=lambda: calculate_ev(trades),
            iterations=20,
            warmup=2,
        )

        assert result.mean_ms < 100.0, f"EV for 10,000 trades too slow: {result.mean_ms:.3f}ms"

    def test_ev_scaling_is_linear(self, benchmark_runner):
        """CONTRACT: EV calculation should scale linearly O(n)."""
        sizes = [100, 1000, 10000]
        times = []

        for size in sizes:
            trades = generate_trades(size)
            result = benchmark_runner.run(
                name=f"EV_scaling_{size}",
                func=lambda t=trades: calculate_ev(t),
                iterations=10,
                warmup=2,
            )
            times.append(result.mean_ms)

        # Check scaling: time should roughly increase proportionally to size
        # Allow 3x tolerance for overhead
        ratio_1000_to_100 = times[1] / times[0]
        ratio_10000_to_1000 = times[2] / times[1]

        # Should be roughly 10x slower for 10x more trades (allowing 3x variance)
        assert ratio_1000_to_100 < 30, f"Non-linear scaling 100->1000: {ratio_1000_to_100:.1f}x"
        assert ratio_10000_to_1000 < 30, f"Non-linear scaling 1000->10000: {ratio_10000_to_1000:.1f}x"


# =============================================================================
# Full Fitness Calculation Scaling Tests
# =============================================================================


@pytest.mark.skipif(not FITNESS_SERVICE_AVAILABLE, reason="fitness_service not available")
class TestFitnessCalculationScaling:
    """Test full fitness calculation performance at various scales."""

    def test_fitness_10_trades(self, benchmark_runner):
        """CONTRACT: Fitness with 10 trades < 10ms."""
        trades = generate_trades(10)

        result = benchmark_runner.run(
            name="fitness_10_trades",
            func=lambda: calculate_fitness(trades),
            iterations=50,
            warmup=5,
            contract_key="fitness_10_trades",
        )

        assert result.passed, f"Contract failed: {result.mean_ms:.2f}ms > {result.contract_max_ms}ms"

    def test_fitness_100_trades(self, benchmark_runner):
        """CONTRACT: Fitness with 100 trades < 50ms."""
        trades = generate_trades(100)

        result = benchmark_runner.run(
            name="fitness_100_trades",
            func=lambda: calculate_fitness(trades),
            iterations=50,
            warmup=5,
            contract_key="fitness_100_trades",
        )

        assert result.passed, f"Contract failed: {result.mean_ms:.2f}ms > {result.contract_max_ms}ms"

    def test_fitness_1000_trades(self, benchmark_runner):
        """CONTRACT: Fitness with 1,000 trades < 200ms."""
        trades = generate_trades(1000)

        result = benchmark_runner.run(
            name="fitness_1000_trades",
            func=lambda: calculate_fitness(trades),
            iterations=20,
            warmup=2,
            contract_key="fitness_1000_trades",
        )

        assert result.passed, f"Contract failed: {result.mean_ms:.2f}ms > {result.contract_max_ms}ms"

    def test_fitness_10000_trades(self, benchmark_runner):
        """CONTRACT: Fitness with 10,000 trades < 1,000ms."""
        trades = generate_trades(10000)

        result = benchmark_runner.run(
            name="fitness_10000_trades",
            func=lambda: calculate_fitness(trades),
            iterations=10,
            warmup=1,
            contract_key="fitness_10000_trades",
        )

        assert result.passed, f"Contract failed: {result.mean_ms:.2f}ms > {result.contract_max_ms}ms"

    @pytest.mark.slow
    def test_fitness_100000_trades_breaking_point(self, benchmark_runner):
        """STRESS: Fitness with 100,000 trades - find breaking point."""
        trades = generate_trades(100000)

        result = benchmark_runner.run(
            name="fitness_100000_trades",
            func=lambda: calculate_fitness(trades),
            iterations=3,
            warmup=1,
        )

        # No hard limit - just record for analysis
        # Should complete in reasonable time (<10 seconds)
        assert result.mean_ms < 10000, f"100k trades took {result.mean_ms:.0f}ms"


# =============================================================================
# EV Multiplier Tests
# =============================================================================


class TestEVMultiplierPerformance:
    """Test EV multiplier calculation (should be O(1))."""

    def test_ev_multiplier_constant_time(self, benchmark_runner):
        """CONTRACT: EV multiplier is O(1) - constant time."""
        test_values = [-10.0, -5.0, -1.0, 0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]

        # Run many iterations to get stable timing
        for ev in test_values:
            result = benchmark_runner.run(
                name=f"ev_multiplier_{ev}",
                func=lambda e=ev: calculate_ev_multiplier(e),
                iterations=1000,
                warmup=100,
            )

            # Should be sub-microsecond (< 0.01ms)
            assert result.mean_ms < 0.1, f"EV multiplier for {ev} too slow: {result.mean_ms:.4f}ms"

    def test_ev_multiplier_batch(self, benchmark_runner):
        """Test batch EV multiplier calculation."""
        test_values = [random.uniform(-10, 10) for _ in range(10000)]

        def batch_calculate():
            return [calculate_ev_multiplier(ev) for ev in test_values]

        result = benchmark_runner.run(
            name="ev_multiplier_batch_10000",
            func=batch_calculate,
            iterations=10,
            warmup=2,
        )

        # 10,000 calculations should take < 50ms
        assert result.mean_ms < 50, f"Batch EV multiplier too slow: {result.mean_ms:.2f}ms"


# =============================================================================
# Component Isolation Tests
# =============================================================================


class TestFitnessComponentPerformance:
    """Test individual fitness component performance."""

    def test_sortino_calculation_scaling(self, timer):
        """Test Sortino ratio calculation at scale."""
        from Agents.Services.fitness_service import calculate_sortino

        sizes = [100, 1000, 10000]

        for size in sizes:
            trades = generate_trades(size)

            with timer() as t:
                for _ in range(10):
                    calculate_sortino(trades)

            avg_ms = t.elapsed_ms / 10
            # Should scale linearly - allow generous margin
            expected_max = size / 10  # 10ms per 100 trades
            assert avg_ms < expected_max, f"Sortino for {size} trades: {avg_ms:.2f}ms > {expected_max}ms"

    def test_drawdown_calculation_scaling(self, timer):
        """Test max drawdown calculation at scale."""
        from Agents.Services.fitness_service import calculate_max_drawdown

        sizes = [100, 1000, 10000]

        for size in sizes:
            trades = generate_trades(size)

            with timer() as t:
                for _ in range(10):
                    calculate_max_drawdown(trades)

            avg_ms = t.elapsed_ms / 10
            expected_max = size / 10
            assert avg_ms < expected_max, f"Drawdown for {size} trades: {avg_ms:.2f}ms > {expected_max}ms"


# =============================================================================
# Concurrent Fitness Calculation Tests
# =============================================================================


class TestConcurrentFitnessCalculation:
    """Test fitness calculation under concurrent load."""

    def test_sequential_fitness_batch(self, benchmark_runner):
        """Test sequential fitness calculation for multiple agents."""
        # 100 agents, each with 100 trades
        agent_trades = [generate_trades(100, seed=i) for i in range(100)]

        def calculate_all():
            return [calculate_fitness(trades) for trades in agent_trades]

        result = benchmark_runner.run(
            name="sequential_fitness_100_agents",
            func=calculate_all,
            iterations=5,
            warmup=1,
        )

        # 100 agents x 100 trades each should complete in < 5 seconds
        assert result.mean_ms < 5000, f"100 agent fitness took {result.mean_ms:.0f}ms"

    @pytest.mark.slow
    def test_large_batch_fitness(self, benchmark_runner):
        """Test fitness calculation for large agent population."""
        # 1000 agents, each with 50 trades
        agent_trades = [generate_trades(50, seed=i) for i in range(1000)]

        def calculate_all():
            return [calculate_fitness(trades) for trades in agent_trades]

        result = benchmark_runner.run(
            name="batch_fitness_1000_agents",
            func=calculate_all,
            iterations=3,
            warmup=1,
        )

        # 1000 agents should complete in < 30 seconds
        assert result.mean_ms < 30000, f"1000 agent fitness took {result.mean_ms:.0f}ms"


# =============================================================================
# Memory Efficiency Tests
# =============================================================================


class TestFitnessMemoryEfficiency:
    """Test memory efficiency of fitness calculations."""

    def test_no_memory_leak_in_loop(self):
        """CONTRACT: Repeated fitness calculations don't leak memory."""
        import gc

        trades = generate_trades(1000)

        # Force GC before measurement
        gc.collect()

        # Get baseline memory (approximate using sys.getsizeof on sample)
        baseline_objects = len(gc.get_objects())

        # Run many iterations
        for _ in range(100):
            result = calculate_fitness(trades)
            del result

        gc.collect()
        final_objects = len(gc.get_objects())

        # Should not have significant object growth
        growth = final_objects - baseline_objects
        assert growth < 1000, f"Potential memory leak: {growth} new objects"

    def test_trade_data_memory_footprint(self):
        """Test memory footprint of TradeData objects."""

        # Single TradeData
        single = TradeData(pnl=100, pnl_pct=1.0, is_win=True)
        single_size = sys.getsizeof(single)

        # Should be reasonably small (< 200 bytes)
        assert single_size < 200, f"TradeData too large: {single_size} bytes"

        # 100,000 trades
        trades = generate_trades(100000)

        # Total should be reasonable (< 50MB for 100k trades)
        # Note: This is approximate as sys.getsizeof doesn't count nested objects
        total_estimate = single_size * len(trades)
        assert total_estimate < 50_000_000, f"100k trades too large: {total_estimate / 1_000_000:.1f}MB"


# =============================================================================
# Edge Case Performance Tests
# =============================================================================


class TestFitnessEdgeCasePerformance:
    """Test fitness performance with edge case inputs."""

    def test_empty_trades_fast(self, timer):
        """CONTRACT: Empty trades list returns instantly."""
        with timer() as t:
            for _ in range(1000):
                calculate_fitness([])

        avg_ms = t.elapsed_ms / 1000
        assert avg_ms < 0.1, f"Empty trades too slow: {avg_ms:.4f}ms"

    def test_single_trade_fast(self, timer):
        """CONTRACT: Single trade returns quickly."""
        trade = generate_trades(1)[0]

        with timer() as t:
            for _ in range(1000):
                calculate_fitness([trade])

        avg_ms = t.elapsed_ms / 1000
        assert avg_ms < 1.0, f"Single trade too slow: {avg_ms:.4f}ms"

    def test_all_winners_performance(self, benchmark_runner):
        """Test performance with all winning trades."""
        trades = [TradeData(pnl=100, pnl_pct=1.0, is_win=True) for _ in range(1000)]

        result = benchmark_runner.run(
            name="fitness_all_winners_1000",
            func=lambda: calculate_fitness(trades),
            iterations=20,
            warmup=2,
        )

        # Should not be slower than mixed trades
        assert result.mean_ms < 500, f"All winners too slow: {result.mean_ms:.2f}ms"

    def test_all_losers_performance(self, benchmark_runner):
        """Test performance with all losing trades."""
        trades = [TradeData(pnl=-100, pnl_pct=-1.0, is_win=False) for _ in range(1000)]

        result = benchmark_runner.run(
            name="fitness_all_losers_1000",
            func=lambda: calculate_fitness(trades),
            iterations=20,
            warmup=2,
        )

        # Should return quickly (EV gate should short-circuit)
        assert result.mean_ms < 500, f"All losers too slow: {result.mean_ms:.2f}ms"

    def test_extreme_values_performance(self, benchmark_runner):
        """Test performance with extreme PnL values."""
        trades = [
            TradeData(
                pnl=random.choice([-1e6, 1e6]),
                pnl_pct=random.choice([-100.0, 100.0]),
                is_win=random.choice([True, False]),
            )
            for _ in range(1000)
        ]

        result = benchmark_runner.run(
            name="fitness_extreme_values_1000",
            func=lambda: calculate_fitness(trades),
            iterations=20,
            warmup=2,
        )

        # Extreme values shouldn't slow things down
        assert result.mean_ms < 500, f"Extreme values too slow: {result.mean_ms:.2f}ms"
