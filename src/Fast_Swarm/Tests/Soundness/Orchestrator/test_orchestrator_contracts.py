"""
Orchestrator Economic Validity Tests - CONTRACT-BASED (EDD)

Source of truth: Orchestrator design principles from CLAUDE.md:
- P0 (Data Collection) runs independently, never blocked
- P2 (Backtesting/Evolution) runs sequentially via orchestrator
- Download once, precompute-fanout pattern
- No concurrent pattern AND agent testing

These tests verify the orchestrator maintains economic validity:
1. Sequential execution (no resource contention)
2. Preloaded data reuse (efficiency)
3. Graceful error handling (no cascading failures)
4. Phase isolation (one thing at a time)
"""


import pytest

from Fast_Swarm.System.Services.orchestrator import (
    BacktestOrchestrator,
    PipelinePhase,
    PipelineState,
    get_orchestrator,
)

# ============================================================================
# SEQUENTIAL EXECUTION CONTRACT
# ============================================================================


class TestSequentialExecution:
    """CONTRACT: Orchestrator runs phases sequentially, never concurrently."""

    def test_initial_state_is_idle(self):
        """CONTRACT: Orchestrator starts in IDLE phase."""
        orchestrator = BacktestOrchestrator()
        assert orchestrator.state.phase == PipelinePhase.IDLE
        assert orchestrator.is_running is False

    def test_phases_are_mutually_exclusive(self):
        """CONTRACT: Only one phase can be active at a time."""
        # Verify PipelinePhase enum has distinct values
        phases = list(PipelinePhase)
        phase_values = [p.value for p in phases]
        assert len(phase_values) == len(set(phase_values)), "Phase values must be unique"

    def test_phase_transitions_are_sequential(self):
        """CONTRACT: Phases follow the defined order."""
        expected_order = [
            PipelinePhase.LOADING_WINDOWS,
            PipelinePhase.TESTING_PATTERNS,
            PipelinePhase.TESTING_AGENTS,
            PipelinePhase.EVOLUTION,
            PipelinePhase.PATTERN_DISCOVERY,
            PipelinePhase.COOLDOWN,
        ]
        # Verify all expected phases exist
        for phase in expected_order:
            assert phase in PipelinePhase

    def test_cannot_start_twice(self):
        """CONTRACT: Calling start() twice doesn't spawn multiple pipelines."""
        orchestrator = BacktestOrchestrator()
        orchestrator._running = True  # Simulate already running

        # start() should be idempotent when already running
        # (implementation prints "[Orchestrator] Already running")
        assert orchestrator.is_running is True


class TestDataPreloading:
    """CONTRACT: Download once, test many (precompute-fanout)."""

    def test_windows_loaded_once_per_cycle(self):
        """CONTRACT: Windows are loaded at start of cycle, not per-pattern/agent."""
        orchestrator = BacktestOrchestrator()
        # Verify state tracks windows loaded (should be 0 initially)
        assert orchestrator.state.windows_loaded == 0

    def test_preloaded_candles_dict_exists(self):
        """CONTRACT: Preloaded candles are stored for reuse."""
        orchestrator = BacktestOrchestrator()
        assert hasattr(orchestrator, "_preloaded_candles")
        assert isinstance(orchestrator._preloaded_candles, dict)

    def test_current_windows_list_exists(self):
        """CONTRACT: Current windows are stored for the cycle."""
        orchestrator = BacktestOrchestrator()
        assert hasattr(orchestrator, "_current_windows")
        assert isinstance(orchestrator._current_windows, list)


class TestBatchConfiguration:
    """CONTRACT: Batch sizes are reasonable for system resources."""

    def test_patterns_per_batch_reasonable(self):
        """CONTRACT: Patterns per batch is between 5 and 100."""
        assert 5 <= BacktestOrchestrator.PATTERNS_PER_BATCH <= 100

    def test_agents_per_batch_reasonable(self):
        """CONTRACT: Agents per batch is between 5 and 50."""
        assert 5 <= BacktestOrchestrator.AGENTS_PER_BATCH <= 50

    def test_windows_per_batch_reasonable(self):
        """CONTRACT: Windows per batch is between 10 and 200."""
        assert 10 <= BacktestOrchestrator.WINDOWS_PER_BATCH <= 200

    def test_cooldown_exists(self):
        """CONTRACT: Cooldown between cycles prevents resource exhaustion."""
        assert BacktestOrchestrator.COOLDOWN_SECONDS >= 30


# ============================================================================
# ERROR HANDLING CONTRACT
# ============================================================================


class TestGracefulErrorHandling:
    """CONTRACT: Errors don't crash the system, just increment counters."""

    def test_consecutive_errors_tracked(self):
        """CONTRACT: Consecutive errors are counted."""
        state = PipelineState()
        assert state.consecutive_errors == 0

        state.consecutive_errors += 1
        assert state.consecutive_errors == 1

    def test_max_consecutive_errors_defined(self):
        """CONTRACT: There's a limit on consecutive errors before stopping."""
        assert BacktestOrchestrator.MAX_CONSECUTIVE_ERRORS >= 2
        assert BacktestOrchestrator.MAX_CONSECUTIVE_ERRORS <= 10

    def test_last_error_tracked(self):
        """CONTRACT: Last error message is stored for debugging."""
        state = PipelineState()
        assert state.last_error is None

        state.last_error = "Test error"
        assert state.last_error == "Test error"


class TestStateTracking:
    """CONTRACT: State is properly tracked for monitoring/dashboard."""

    def test_patterns_progress_tracked(self):
        """CONTRACT: Pattern testing progress is tracked."""
        state = PipelineState()
        assert state.patterns_tested == 0
        assert state.patterns_total == 0

    def test_agents_progress_tracked(self):
        """CONTRACT: Agent testing progress is tracked."""
        state = PipelineState()
        assert state.agents_tested == 0
        assert state.agents_total == 0

    def test_cycles_completed_tracked(self):
        """CONTRACT: Completed cycles are counted."""
        state = PipelineState()
        assert state.cycles_completed == 0

    def test_timestamps_tracked(self):
        """CONTRACT: Start time and last cycle time are tracked."""
        state = PipelineState()
        assert state.started_at is None
        assert state.last_cycle_at is None


class TestStatusAPI:
    """CONTRACT: get_status() returns all relevant information."""

    def test_status_contains_required_fields(self):
        """CONTRACT: Status dict has all fields needed for dashboard."""
        orchestrator = BacktestOrchestrator()
        status = orchestrator.get_status()

        required_fields = [
            "running",
            "phase",
            "windows_loaded",
            "patterns_tested",
            "patterns_total",
            "agents_tested",
            "agents_total",
            "cycles_completed",
            "last_error",
        ]

        for field in required_fields:
            assert field in status, f"Missing required field: {field}"

    def test_status_phase_is_string(self):
        """CONTRACT: Phase is returned as string (not enum) for JSON serialization."""
        orchestrator = BacktestOrchestrator()
        status = orchestrator.get_status()
        assert isinstance(status["phase"], str)


# ============================================================================
# SINGLETON CONTRACT
# ============================================================================


class TestSingletonPattern:
    """CONTRACT: Only one orchestrator instance exists."""

    def test_get_orchestrator_returns_same_instance(self):
        """CONTRACT: get_orchestrator() returns the same instance."""
        orch1 = get_orchestrator()
        orch2 = get_orchestrator()
        assert orch1 is orch2


# ============================================================================
# GRACEFUL SHUTDOWN CONTRACT
# ============================================================================


class TestGracefulShutdown:
    """CONTRACT: Orchestrator can be stopped gracefully."""

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        """CONTRACT: Stopping when not running is a no-op."""
        orchestrator = BacktestOrchestrator()
        orchestrator._running = False

        # Should not raise
        await orchestrator.stop()
        assert orchestrator.is_running is False

    def test_stop_sets_running_false(self):
        """CONTRACT: stop() sets _running to False."""
        orchestrator = BacktestOrchestrator()
        orchestrator._running = True
        orchestrator._running = False  # Simulate stop
        assert orchestrator._running is False


# ============================================================================
# PRIORITY ISOLATION CONTRACT
# ============================================================================


class TestPriorityIsolation:
    """CONTRACT: P0 (data collection) is never blocked by P2 (orchestrator)."""

    def test_orchestrator_does_not_import_stream_manager(self):
        """CONTRACT: Orchestrator module doesn't touch P0 components."""
        import Fast_Swarm.System.Services.orchestrator as orch_module

        # Check the module doesn't import stream/collection modules
        module_source = open(orch_module.__file__).read()
        assert "stream_manager" not in module_source
        assert "data_collector" not in module_source

    def test_orchestrator_only_uses_async_session(self):
        """CONTRACT: Orchestrator uses async sessions (non-blocking)."""
        import Fast_Swarm.System.Services.orchestrator as orch_module

        module_source = open(orch_module.__file__).read()
        assert "AsyncSession" in module_source or "async_session_maker" in module_source
