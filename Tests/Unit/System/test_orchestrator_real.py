"""
Real-DB integration tests for BacktestOrchestrator.

Uses db_session fixture (PostgreSQL with transaction rollback).
Tests pipeline state, phase transitions, start/stop lifecycle, and
phase methods with REAL Agent/Pattern rows in the database.

External calls (window pool, candle loading, backtest services, discovery,
evolution cycle) are mocked to avoid network/filesystem dependencies.
"""

import asyncio
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from Fast_Swarm.Agents.Models.agent_models import Agent
from Fast_Swarm.Patterns.Models.pattern_models import Pattern
from Fast_Swarm.System.Services.orchestrator import (
    BacktestOrchestrator,
    PipelinePhase,
    PipelineState,
    get_orchestrator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_traits() -> dict[str, float]:
    return {
        "risk_tolerance": 0.5, "hold_duration_bias": 0.5, "volatility_seeking": 0.5,
        "profit_target_greed": 0.5, "win_rate_preference": 0.5, "drawdown_sensitivity": 0.5,
        "momentum_vs_reversion": 0.5, "stop_loss_tightness": 0.5, "entry_aggression": 0.5,
        "exit_aggression": 0.5, "lookback_preference": 0.5, "sentiment_weight": 0.5,
        "news_reactivity": 0.5, "sentiment_contrarian": 0.5, "funding_rate_sensitivity": 0.5,
        "correlation_awareness": 0.5, "patience": 0.5, "adaptability": 0.5,
        "trend_following": 0.5, "mean_reversion": 0.5, "breakout_preference": 0.5,
        "volume_sensitivity": 0.5,
    }


def _make_agent(
    agent_id: str | None = None,
    fitness: float = 50.0,
    generation: int = 1,
    status: str = "active",
) -> Agent:
    return Agent(
        agent_id=agent_id or f"test-{uuid.uuid4().hex[:8]}",
        name=f"Orch-Agent-{uuid.uuid4().hex[:4]}",
        generation=generation,
        level=1,
        traits=_default_traits(),
        status=status,
        is_active=(status == "active"),
        fitness_score=Decimal(str(fitness)),
        fitness_by_regime={},
        elo_rating=Decimal("1500"),
    )


def _make_pattern(
    pattern_id: str | None = None,
    fitness: float = 60.0,
    is_active: bool = True,
    priority: int = 5,
) -> Pattern:
    return Pattern(
        pattern_id=pattern_id or f"pat-{uuid.uuid4().hex[:8]}",
        name=f"Orch-Pattern-{uuid.uuid4().hex[:4]}",
        origin="technical",
        status="untested",
        is_active=is_active,
        priority=priority,
        entry_conditions=[{"indicator": "rsi", "operator": "<", "value": 30}],
        exit_conditions=[{"indicator": "rsi", "operator": ">", "value": 70}],
        fitness_score=Decimal(str(fitness)),
        total_trades=0,
        total_runs=0,
    )


async def _seed_patterns(session: AsyncSession, count: int = 5) -> list[Pattern]:
    patterns = []
    for i in range(count):
        p = _make_pattern(priority=10 - i)
        session.add(p)
        patterns.append(p)
    await session.flush()
    for p in patterns:
        await session.refresh(p)
    return patterns


async def _seed_agents(session: AsyncSession, count: int = 5) -> list[Agent]:
    agents = []
    for i in range(count):
        a = _make_agent(fitness=10.0 + i * 20)
        session.add(a)
        agents.append(a)
    await session.flush()
    for a in agents:
        await session.refresh(a)
    return agents


# ---------------------------------------------------------------------------
# Tests: PipelineState / PipelinePhase
# ---------------------------------------------------------------------------

class TestPipelineState:
    """Tests for the PipelineState dataclass and PipelinePhase enum."""

    def test_default_state(self):
        state = PipelineState()
        assert state.phase == PipelinePhase.IDLE
        assert state.started_at is None
        assert state.windows_loaded == 0
        assert state.patterns_tested == 0
        assert state.agents_tested == 0
        assert state.cycles_completed == 0
        assert state.consecutive_errors == 0

    def test_phase_enum_values(self):
        assert PipelinePhase.IDLE.value == "idle"
        assert PipelinePhase.LOADING_WINDOWS.value == "loading_windows"
        assert PipelinePhase.TESTING_PATTERNS.value == "testing_patterns"
        assert PipelinePhase.TESTING_AGENTS.value == "testing_agents"
        assert PipelinePhase.EVOLUTION.value == "evolution"
        assert PipelinePhase.PATTERN_DISCOVERY.value == "pattern_discovery"
        assert PipelinePhase.COOLDOWN.value == "cooldown"

    def test_error_tracking(self):
        state = PipelineState()
        state.last_error = "something broke"
        state.consecutive_errors = 2
        assert state.last_error == "something broke"
        assert state.consecutive_errors == 2

    def test_timeout_tracking(self):
        state = PipelineState()
        state.patterns_skipped_timeout = 5
        state.agents_skipped_timeout = 3
        assert state.patterns_skipped_timeout == 5
        assert state.agents_skipped_timeout == 3


# ---------------------------------------------------------------------------
# Tests: BacktestOrchestrator initialization and status
# ---------------------------------------------------------------------------

class TestOrchestratorInit:
    """Tests for orchestrator construction and configuration."""

    def test_initial_state(self):
        orch = BacktestOrchestrator()
        assert orch.is_running is False
        assert orch.state.phase == PipelinePhase.IDLE
        assert orch._current_windows == []
        assert orch._preloaded_candles == {}

    def test_get_status_idle(self):
        orch = BacktestOrchestrator()
        status = orch.get_status()
        assert status["running"] is False
        assert status["phase"] == "idle"
        assert status["started_at"] is None
        assert status["windows_loaded"] == 0
        assert status["patterns_tested"] == 0
        assert status["agents_tested"] == 0
        assert status["cycles_completed"] == 0
        assert status["last_error"] is None

    def test_configuration_constants(self):
        orch = BacktestOrchestrator()
        assert orch.PATTERNS_PER_BATCH == 500
        assert orch.AGENTS_PER_BATCH == 100
        assert orch.WINDOWS_PER_BATCH == 1
        assert orch.WINDOWS_BEFORE_EVOLUTION == 50
        assert orch.PARALLEL_TESTS == 8
        assert orch.COOLDOWN_SECONDS == 60
        assert orch.MAX_CONSECUTIVE_ERRORS == 3
        assert orch.PATTERN_TIMEOUT_SECONDS == 30
        assert orch.AGENT_TIMEOUT_SECONDS == 60
        assert orch.PHASE_WATCHDOG_SECONDS == 600


# ---------------------------------------------------------------------------
# Tests: start / stop lifecycle
# ---------------------------------------------------------------------------

class TestOrchestratorLifecycle:
    """Tests for start/stop behavior."""

    @pytest.mark.asyncio
    async def test_start_sets_running(self):
        orch = BacktestOrchestrator()
        with patch.object(orch, "_run_pipeline", new_callable=AsyncMock):
            await orch.start()
            assert orch.is_running is True
            assert orch.state.started_at is not None
            assert orch.state.consecutive_errors == 0
            # Cleanup
            await orch.stop()

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        """Calling start twice should not create a second task."""
        orch = BacktestOrchestrator()
        with patch.object(orch, "_run_pipeline", new_callable=AsyncMock):
            await orch.start()
            first_task = orch._task
            await orch.start()  # second call should be no-op
            assert orch._task is first_task
            await orch.stop()

    @pytest.mark.asyncio
    async def test_stop_resets_state(self):
        orch = BacktestOrchestrator()
        with patch.object(orch, "_run_pipeline", new_callable=AsyncMock):
            await orch.start()
            await orch.stop()
            assert orch.is_running is False
            assert orch.state.phase == PipelinePhase.IDLE

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        """Stopping a stopped orchestrator should be a no-op."""
        orch = BacktestOrchestrator()
        await orch.stop()  # Should not raise
        assert orch.is_running is False


# ---------------------------------------------------------------------------
# Tests: _phase_load_windows
# ---------------------------------------------------------------------------

class TestPhaseLoadWindows:
    """Tests for Phase 1: loading windows from pool."""

    @pytest.mark.asyncio
    async def test_no_windows_when_pool_not_initialized(self, db_session: AsyncSession):
        orch = BacktestOrchestrator()
        with patch(
            "Fast_Swarm.local_agents.backtest.windows.is_initialized",
            return_value=False,
        ):
            await orch._phase_load_windows(db_session)

        assert orch._current_windows == []
        assert orch.state.phase == PipelinePhase.LOADING_WINDOWS

    @pytest.mark.asyncio
    async def test_loads_windows_from_pool(self, db_session: AsyncSession):
        mock_window = MagicMock()
        mock_window.symbol = "BTC/USDT"
        mock_window.timeframe = "1h"
        mock_window.start_ts = 1700000000
        mock_window.end_ts = 1700003600

        orch = BacktestOrchestrator()
        with patch(
            "Fast_Swarm.local_agents.backtest.windows.is_initialized",
            return_value=True,
        ), patch(
            "Fast_Swarm.local_agents.backtest.windows.get_windows",
            return_value=[mock_window],
        ), patch(
            "Fast_Swarm.local_agents.backtest.windows.get_pool_stats",
            return_value={"total": 100},
        ), patch(
            "Fast_Swarm.local_agents.backtest.data.LazyCandleCache",
            return_value=MagicMock(),
        ):
            await orch._phase_load_windows(db_session)

        assert len(orch._current_windows) == 1
        assert orch._current_windows[0]["asset"] == "BTC/USDT"
        assert orch.state.windows_loaded == 1


# ---------------------------------------------------------------------------
# Tests: _phase_test_patterns
# ---------------------------------------------------------------------------

class TestPhaseTestPatterns:
    """Tests for Phase 2: testing patterns on windows."""

    @pytest.mark.asyncio
    async def test_no_patterns_to_test(self, db_session: AsyncSession):
        """When no active patterns exist, phase completes cleanly."""
        orch = BacktestOrchestrator()
        orch._running = True
        orch._current_windows = [{"asset": "BTC/USDT", "timeframe": "1h"}]
        await orch._phase_test_patterns(db_session)
        assert orch.state.patterns_total == 0

    @pytest.mark.asyncio
    async def test_patterns_tested_with_real_db(self, db_session: AsyncSession):
        """Seed real patterns and verify they are queried and tested."""
        patterns = await _seed_patterns(db_session, count=3)

        orch = BacktestOrchestrator()
        orch._running = True
        orch._current_windows = [{"asset": "BTC/USDT", "timeframe": "1h"}]
        orch._preloaded_candles = {}

        mock_service = MagicMock()
        mock_service.test_pattern_on_windows = AsyncMock(return_value={"total_trades": 5})

        with patch(
            "Fast_Swarm.Patterns.Services.discovery_service.PatternDiscoveryService",
            return_value=mock_service,
        ):
            await orch._phase_test_patterns(db_session)

        assert orch.state.patterns_total == 3
        assert orch.state.patterns_tested == 3
        assert mock_service.test_pattern_on_windows.call_count == 3

    @pytest.mark.asyncio
    async def test_pattern_timeout_counted(self, db_session: AsyncSession):
        """Patterns that timeout should be counted in skipped stats."""
        await _seed_patterns(db_session, count=2)

        orch = BacktestOrchestrator()
        orch._running = True
        orch._current_windows = [{"asset": "ETH/USDT", "timeframe": "15m"}]
        orch._preloaded_candles = {}
        # Use a very short timeout to force timeouts
        orch.PATTERN_TIMEOUT_SECONDS = 0.001

        async def _slow_test(*args, **kwargs):
            await asyncio.sleep(10)
            return {"total_trades": 0}

        mock_service = MagicMock()
        mock_service.test_pattern_on_windows = _slow_test

        with patch(
            "Fast_Swarm.Patterns.Services.discovery_service.PatternDiscoveryService",
            return_value=mock_service,
        ):
            await orch._phase_test_patterns(db_session)

        assert orch.state.patterns_skipped_timeout == 2

    @pytest.mark.asyncio
    async def test_archived_patterns_excluded(self, db_session: AsyncSession):
        """Archived patterns should not be fetched for testing."""
        active_pat = _make_pattern(pattern_id="active-1", is_active=True, priority=10)
        archived_pat = _make_pattern(pattern_id="archived-1", is_active=True, priority=10)
        archived_pat.status = "archived"
        db_session.add(active_pat)
        db_session.add(archived_pat)
        await db_session.flush()

        orch = BacktestOrchestrator()
        orch._running = True
        orch._current_windows = [{"asset": "BTC/USDT", "timeframe": "1h"}]
        orch._preloaded_candles = {}

        mock_service = MagicMock()
        mock_service.test_pattern_on_windows = AsyncMock(return_value={"total_trades": 1})

        with patch(
            "Fast_Swarm.Patterns.Services.discovery_service.PatternDiscoveryService",
            return_value=mock_service,
        ):
            await orch._phase_test_patterns(db_session)

        # Only the active non-archived pattern should be tested
        assert orch.state.patterns_total == 1


# ---------------------------------------------------------------------------
# Tests: _phase_test_agents
# ---------------------------------------------------------------------------

class TestPhaseTestAgents:
    """Tests for Phase 3: testing agents on windows."""

    @pytest.mark.asyncio
    async def test_no_agents_to_test(self, db_session: AsyncSession):
        orch = BacktestOrchestrator()
        orch._running = True
        orch._current_windows = [{"asset": "BTC/USDT", "timeframe": "1h"}]
        await orch._phase_test_agents(db_session)
        assert orch.state.agents_total == 0

    @pytest.mark.asyncio
    async def test_agents_tested_with_real_db(self, db_session: AsyncSession):
        """Seed real agents and verify they are queried and tested."""
        agents = await _seed_agents(db_session, count=4)

        orch = BacktestOrchestrator()
        orch._running = True
        orch._current_windows = [{"asset": "BTC/USDT", "timeframe": "1h"}]
        orch._preloaded_candles = {}

        mock_service = MagicMock()
        mock_service.backtest_agent_on_windows = AsyncMock(return_value=None)

        with patch(
            "Fast_Swarm.Agents.Services.backtest_service.AgentBacktestService",
            return_value=mock_service,
        ):
            await orch._phase_test_agents(db_session)

        assert orch.state.agents_total == 4
        assert orch.state.agents_tested == 4
        assert mock_service.backtest_agent_on_windows.call_count == 4

    @pytest.mark.asyncio
    async def test_inactive_agents_excluded(self, db_session: AsyncSession):
        """Only active agents should be tested."""
        active_agent = _make_agent(agent_id="active-ag", status="active")
        retired_agent = _make_agent(agent_id="retired-ag", status="retired")
        db_session.add(active_agent)
        db_session.add(retired_agent)
        await db_session.flush()

        orch = BacktestOrchestrator()
        orch._running = True
        orch._current_windows = [{"asset": "BTC/USDT", "timeframe": "1h"}]
        orch._preloaded_candles = {}

        mock_service = MagicMock()
        mock_service.backtest_agent_on_windows = AsyncMock(return_value=None)

        with patch(
            "Fast_Swarm.Agents.Services.backtest_service.AgentBacktestService",
            return_value=mock_service,
        ):
            await orch._phase_test_agents(db_session)

        assert orch.state.agents_total == 1

    @pytest.mark.asyncio
    async def test_agent_error_does_not_crash_phase(self, db_session: AsyncSession):
        """If one agent backtest errors, others should still complete."""
        agents = await _seed_agents(db_session, count=3)

        call_count = 0

        async def _fail_second(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Simulated backtest failure")

        orch = BacktestOrchestrator()
        orch._running = True
        orch._current_windows = [{"asset": "BTC/USDT", "timeframe": "1h"}]
        orch._preloaded_candles = {}

        mock_service = MagicMock()
        mock_service.backtest_agent_on_windows = _fail_second

        with patch(
            "Fast_Swarm.Agents.Services.backtest_service.AgentBacktestService",
            return_value=mock_service,
        ):
            await orch._phase_test_agents(db_session)

        # 2 should succeed, 1 should fail silently
        assert orch.state.agents_tested == 2


# ---------------------------------------------------------------------------
# Tests: _phase_evolution
# ---------------------------------------------------------------------------

class TestPhaseEvolution:
    """Tests for Phase 4: evolution."""

    @pytest.mark.asyncio
    async def test_evolution_phase_calls_service(self, db_session: AsyncSession):
        orch = BacktestOrchestrator()
        mock_service = MagicMock()
        mock_service.run_evolution_cycle = AsyncMock(return_value={"spawned": 5})

        with patch(
            "Fast_Swarm.System.Services.evolution_cycle_service.EvolutionCycleService",
            return_value=mock_service,
        ):
            await orch._phase_evolution(db_session)

        assert orch.state.phase == PipelinePhase.EVOLUTION
        mock_service.run_evolution_cycle.assert_awaited_once_with(db_session)

    @pytest.mark.asyncio
    async def test_evolution_error_does_not_crash(self, db_session: AsyncSession):
        orch = BacktestOrchestrator()
        mock_service = MagicMock()
        mock_service.run_evolution_cycle = AsyncMock(side_effect=RuntimeError("Evolution failed"))

        with patch(
            "Fast_Swarm.System.Services.evolution_cycle_service.EvolutionCycleService",
            return_value=mock_service,
        ):
            # Should not raise
            await orch._phase_evolution(db_session)

        assert orch.state.phase == PipelinePhase.EVOLUTION


# ---------------------------------------------------------------------------
# Tests: _phase_pattern_discovery
# ---------------------------------------------------------------------------

class TestPhasePatternDiscovery:
    """Tests for Phase 5: pattern discovery."""

    @pytest.mark.asyncio
    async def test_discovery_phase_calls_service(self, db_session: AsyncSession):
        orch = BacktestOrchestrator()
        mock_service = MagicMock()
        mock_service.run_discovery_cycle = AsyncMock(return_value={"discovered": 3})

        with patch(
            "Fast_Swarm.Patterns.Services.discovery_service.PatternDiscoveryService",
            return_value=mock_service,
        ):
            await orch._phase_pattern_discovery(db_session)

        assert orch.state.phase == PipelinePhase.PATTERN_DISCOVERY
        mock_service.run_discovery_cycle.assert_awaited_once_with(db_session)

    @pytest.mark.asyncio
    async def test_discovery_error_does_not_crash(self, db_session: AsyncSession):
        orch = BacktestOrchestrator()
        mock_service = MagicMock()
        mock_service.run_discovery_cycle = AsyncMock(side_effect=RuntimeError("Discovery failed"))

        with patch(
            "Fast_Swarm.Patterns.Services.discovery_service.PatternDiscoveryService",
            return_value=mock_service,
        ):
            await orch._phase_pattern_discovery(db_session)

        assert orch.state.phase == PipelinePhase.PATTERN_DISCOVERY


# ---------------------------------------------------------------------------
# Tests: _phase_cooldown
# ---------------------------------------------------------------------------

class TestPhaseCooldown:
    """Tests for cooldown phase."""

    @pytest.mark.asyncio
    async def test_cooldown_respects_stop(self):
        """Cooldown should exit early when _running becomes False."""
        orch = BacktestOrchestrator()
        orch._running = True
        orch.COOLDOWN_SECONDS = 10  # 10 seconds total

        # Stop after a brief delay
        async def _stop_soon():
            await asyncio.sleep(0.1)
            orch._running = False

        stop_task = asyncio.create_task(_stop_soon())
        await orch._phase_cooldown()
        await stop_task

        assert orch.state.phase == PipelinePhase.COOLDOWN


# ---------------------------------------------------------------------------
# Tests: get_orchestrator singleton
# ---------------------------------------------------------------------------

class TestGetOrchestrator:
    """Tests for the global singleton factory."""

    def test_returns_same_instance(self):
        import Fast_Swarm.System.Services.orchestrator as mod
        # Reset singleton
        mod._orchestrator = None
        orch1 = get_orchestrator()
        orch2 = get_orchestrator()
        assert orch1 is orch2
        # Cleanup
        mod._orchestrator = None

    def test_creates_instance_if_none(self):
        import Fast_Swarm.System.Services.orchestrator as mod
        mod._orchestrator = None
        orch = get_orchestrator()
        assert isinstance(orch, BacktestOrchestrator)
        mod._orchestrator = None


# ---------------------------------------------------------------------------
# Tests: get_status reflects phase changes
# ---------------------------------------------------------------------------

class TestGetStatusReflectsState:
    """Verify get_status accurately mirrors internal state."""

    def test_status_after_state_mutation(self):
        orch = BacktestOrchestrator()
        orch._running = True
        orch.state.phase = PipelinePhase.TESTING_AGENTS
        orch.state.started_at = datetime(2026, 1, 1, 0, 0, 0)
        orch.state.windows_loaded = 5
        orch.state.patterns_tested = 100
        orch.state.patterns_total = 500
        orch.state.agents_tested = 20
        orch.state.agents_total = 100
        orch.state.cycles_completed = 3
        orch.state.last_error = "test error"

        status = orch.get_status()
        assert status["running"] is True
        assert status["phase"] == "testing_agents"
        assert status["started_at"] == "2026-01-01T00:00:00"
        assert status["windows_loaded"] == 5
        assert status["patterns_tested"] == 100
        assert status["patterns_total"] == 500
        assert status["agents_tested"] == 20
        assert status["agents_total"] == 100
        assert status["cycles_completed"] == 3
        assert status["last_error"] == "test error"
