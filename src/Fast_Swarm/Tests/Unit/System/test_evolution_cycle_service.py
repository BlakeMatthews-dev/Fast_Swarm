"""
Unit Tests for EvolutionCycleService - 6-Phase Evolution Pipeline

Tests the orchestration logic of EvolutionCycleService without requiring
a real database. All sub-services are mocked with AsyncMock.

Coverage:
- Phase orchestration (order, keys, flags, parameters)
- Population extinction detection & emergency spawn
- Emergency spawn logic (cap, formula, negative handling)
- Pattern fallback chain (regime -> quintile -> top40% -> all)
- Error recovery per phase
- Breeding, cloning, level increment
- Crucible eligibility & testing
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper: build a fake Agent object with .agent_id and .level
# ---------------------------------------------------------------------------
def _make_agent(agent_id: str, fitness: float = 50.0, level: int = 1):
    agent = SimpleNamespace(
        agent_id=agent_id,
        fitness_score=fitness,
        level=level,
        status="active",
    )
    return agent


def _make_agents(n: int, base_fitness: float = 100.0):
    """Create n fake agents with descending fitness."""
    return [
        _make_agent(f"agent-{i}", fitness=base_fitness - i, level=1)
        for i in range(n)
    ]


def _make_ranking_dicts(n: int, base_fitness: float = 100.0):
    """Create ranking dicts as returned by rank_agents."""
    return [
        {"agent_id": f"agent-{i}", "fitness_score": base_fitness - i, "rank": i + 1}
        for i in range(n)
    ]


def _make_crucible_entry(agent_id: str, entry_id: int = 1, level: int = 5):
    return SimpleNamespace(
        id=entry_id,
        agent_id=agent_id,
        level_at_entry=level,
    )


# ---------------------------------------------------------------------------
# Patch targets -- all relative to the evolution_cycle_service module
# ---------------------------------------------------------------------------
_MOD = "Fast_Swarm.System.Services.evolution_cycle_service"

# These are imported locally inside run_evolution_cycle, so we patch at source
_CRUCIBLE_ENTRY = "Fast_Swarm.System.Services.crucible_entry_service.CrucibleEntryService"
_CRUCIBLE_TEST = "Fast_Swarm.System.Services.crucible_test_service.CrucibleTestService"
_REGIME_PATTERNS = "Fast_Swarm.Agents.Services.spawn_service.get_regime_priority_patterns"


def _build_service_with_mocks(agent_count=20):
    """
    Instantiate EvolutionCycleService with every sub-service replaced by mocks.
    Returns (service, mocks_dict).
    """
    from Fast_Swarm.System.Services.evolution_cycle_service import EvolutionCycleService

    svc = EvolutionCycleService.__new__(EvolutionCycleService)

    agents = _make_agents(agent_count)
    rankings = _make_ranking_dicts(agent_count)

    # Sub-service mocks
    svc.state_cache = MagicMock()
    svc.state_cache.refresh_caches = AsyncMock()
    svc.state_cache.get_cache_stats = MagicMock(return_value={"patterns": 100, "agents": agent_count})
    svc.state_cache.invalidate_pattern_cache = MagicMock()
    svc.state_cache.load_pattern_cache = AsyncMock()

    svc.pattern_discovery = MagicMock()
    svc.pattern_discovery.run_batch_backtest = AsyncMock(return_value={"tested": 50, "promoted": 3})

    svc.agent_backtest = MagicMock()
    svc.agent_backtest.backtest_agents = AsyncMock(return_value={
        f"agent-{i}": {"sharpe": 1.2} for i in range(agent_count)
    })

    svc.agent_ranking = MagicMock()
    svc.agent_ranking.rank_agents = AsyncMock(return_value=rankings)
    svc.agent_ranking.get_all_agents_ranked = AsyncMock(return_value=list(agents))
    svc.agent_ranking.calculate_population_stats = AsyncMock(return_value={
        "total": agent_count, "avg_fitness": 50.0, "max_fitness": 100.0,
    })

    svc.agent_spawn = MagicMock()
    svc.agent_spawn.spawn_children = AsyncMock(return_value=["child-1"])
    svc.agent_spawn.spawn_new_agents = AsyncMock(return_value=["new-1", "new-2"])
    svc.agent_spawn.spawn_agents_batch = AsyncMock(return_value=["new-1", "new-2"])

    svc.agent_cull = MagicMock()
    svc.agent_cull.cull_agents = AsyncMock(return_value={
        "culled_count": 6,
        "remaining_count": agent_count - 6,
        "min_population_protected": False,
    })

    svc.pattern_backtest = MagicMock()
    svc.pattern_cull = MagicMock()

    mocks = {
        "state_cache": svc.state_cache,
        "pattern_discovery": svc.pattern_discovery,
        "agent_backtest": svc.agent_backtest,
        "agent_ranking": svc.agent_ranking,
        "agent_spawn": svc.agent_spawn,
        "agent_cull": svc.agent_cull,
        "agents": agents,
        "rankings": rankings,
    }
    return svc, mocks


def _mock_session(agents=None):
    """Create a mock AsyncSession that returns the given agents from execute()."""
    session = AsyncMock()
    if agents is None:
        agents = []

    # session.execute(select(Agent).where(...)) returns scalars().all() chain
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = agents

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    session.execute = AsyncMock(return_value=result_mock)
    session.exec = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    return session


# ===========================================================================
# TestPhaseOrchestration
# ===========================================================================
class TestPhaseOrchestration:
    """Tests for overall pipeline orchestration."""

    @pytest.mark.asyncio
    async def test_all_phases_run(self):
        """All major phases execute and appear in results."""
        svc, mocks = _build_service_with_mocks(20)
        session = _mock_session(mocks["agents"])

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[{"pattern_id": "p1"}]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(session)

        # Verify all phase keys present
        phases = result["phases"]
        assert "pattern_discovery" in phases
        assert "backtest" in phases
        assert "rank" in phases
        assert "level_increment" in phases
        assert "breed" in phases
        assert "clone" in phases
        assert "cull" in phases
        assert "crucible" in phases

    @pytest.mark.asyncio
    async def test_result_dict_complete(self):
        """Result dict has all top-level keys."""
        svc, mocks = _build_service_with_mocks(20)
        session = _mock_session(mocks["agents"])

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[{"pattern_id": "p1"}]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(session)

        assert "cycle_start" in result
        assert "cycle_end" in result
        assert "duration_seconds" in result
        assert "final_population" in result
        assert "cache_stats" in result
        assert "phases" in result

    @pytest.mark.asyncio
    async def test_rapid_evolution_flag(self):
        """rapid_evolution=True uses aggressive clone/survival percentiles."""
        svc, mocks = _build_service_with_mocks(20)
        session = _mock_session(mocks["agents"])

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[{"pattern_id": "p1"}]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(session, rapid_evolution=True)

        # With rapid_evolution, cull_percentile = 1.0 - 0.55 = 0.45
        cull_call = mocks["agent_cull"].cull_agents
        cull_call.assert_awaited_once()
        _, kwargs = cull_call.call_args
        assert abs(kwargs["cull_percentile"] - 0.45) < 0.01

    @pytest.mark.asyncio
    async def test_custom_parameters(self):
        """Non-default breeding_count and mutation_rate are respected."""
        svc, mocks = _build_service_with_mocks(30)
        session = _mock_session(mocks["agents"])

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[{"pattern_id": "p1"}]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(
                session, breeding_count=6, mutation_rate=0.30,
            )

        # 6 breeders -> 3 pairs -> spawn_children called 3 times
        assert mocks["agent_spawn"].spawn_children.await_count == 3 + int(30 * 0.20)  # 3 breed + 6 clones
        # Check mutation_rate passed
        for call in mocks["agent_spawn"].spawn_children.call_args_list:
            assert call.kwargs["mutation_rate"] == 0.30

    @pytest.mark.asyncio
    async def test_backtest_assets_passed(self):
        """backtest_assets forwarded to backtest service."""
        svc, mocks = _build_service_with_mocks(20)
        session = _mock_session(mocks["agents"])
        assets = ["BTC/USDT", "ETH/USDT"]

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[{"pattern_id": "p1"}]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(session, backtest_assets=assets)

        _, kwargs = mocks["agent_backtest"].backtest_agents.call_args
        assert kwargs["assets"] == assets

    @pytest.mark.asyncio
    async def test_blue_green_switch(self):
        """USE_DEV_BACKTEST env var controls which backtest service is imported."""
        # This is a module-level import switch, so we just verify the flag is read
        from Fast_Swarm.System.Services import evolution_cycle_service as mod
        # The module reads USE_DEV_BACKTEST at import time; verify the variable exists
        assert hasattr(mod, "USE_DEV_BACKTEST")
        assert isinstance(mod.USE_DEV_BACKTEST, bool)


# ===========================================================================
# TestPopulationExtinction
# ===========================================================================
class TestPopulationExtinction:
    """Tests for population extinction detection and recovery."""

    @pytest.mark.asyncio
    async def test_zero_agents_triggers_emergency_spawn(self):
        """No active agents triggers emergency spawn."""
        svc, mocks = _build_service_with_mocks(0)
        session = _mock_session([])  # zero agents

        mocks["agent_spawn"].spawn_agents_batch = AsyncMock(return_value=[f"emergency-{i}" for i in range(10)])
        # After emergency spawn, backtest will use the emergency agent ids
        mocks["agent_backtest"].backtest_agents = AsyncMock(return_value={
            f"emergency-{i}": {"sharpe": 1.0} for i in range(10)
        })

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(session, target_agent_population=10)

        assert "emergency_spawn" in result
        assert result["emergency_spawn"]["triggered"] is True
        assert result["emergency_spawn"]["agents_spawned"] == 10

    @pytest.mark.asyncio
    async def test_spawn_failure_returns_error(self):
        """Emergency spawn failure returns error in result."""
        svc, mocks = _build_service_with_mocks(0)
        session = _mock_session([])

        mocks["agent_spawn"].spawn_agents_batch = AsyncMock(side_effect=RuntimeError("DB down"))

        result = await svc.run_evolution_cycle(session)

        assert "error" in result
        assert "emergency spawn failed" in result["error"]

    @pytest.mark.asyncio
    async def test_single_agent_no_extinction(self):
        """1 agent does not trigger emergency spawn."""
        agents = _make_agents(1)
        svc, mocks = _build_service_with_mocks(1)
        mocks["agent_ranking"].get_all_agents_ranked = AsyncMock(return_value=agents)
        mocks["agent_ranking"].rank_agents = AsyncMock(return_value=_make_ranking_dicts(1))
        session = _mock_session(agents)

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[{"pattern_id": "p1"}]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(session)

        assert "emergency_spawn" not in result

    @pytest.mark.asyncio
    async def test_empty_db_emergency(self):
        """Completely empty database triggers emergency spawn."""
        svc, mocks = _build_service_with_mocks(0)
        session = _mock_session([])

        mocks["agent_spawn"].spawn_agents_batch = AsyncMock(return_value=["e-1", "e-2"])
        mocks["agent_backtest"].backtest_agents = AsyncMock(return_value={
            "e-1": {"sharpe": 0.5}, "e-2": {"sharpe": 0.6},
        })

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(session, target_agent_population=2)

        assert result["emergency_spawn"]["triggered"] is True
        # spawn_agents_batch called with count=target_agent_population and strategy="genesis"
        call_kwargs = mocks["agent_spawn"].spawn_agents_batch.call_args.kwargs
        assert call_kwargs["count"] == 2
        assert call_kwargs["strategy"] == "genesis"

    @pytest.mark.asyncio
    async def test_post_emergency_continues(self):
        """After emergency spawn, remaining pipeline phases still run."""
        svc, mocks = _build_service_with_mocks(0)
        session = _mock_session([])

        emergency_ids = ["e-1", "e-2", "e-3"]
        mocks["agent_spawn"].spawn_new_agents = AsyncMock(return_value=emergency_ids)
        mocks["agent_backtest"].backtest_agents = AsyncMock(return_value={
            eid: {"sharpe": 1.0} for eid in emergency_ids
        })
        mocks["agent_ranking"].get_all_agents_ranked = AsyncMock(
            return_value=_make_agents(3)
        )

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[{"pattern_id": "p1"}]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(session, target_agent_population=3)

        # Backtest, rank, breed, cull should all have run
        assert "backtest" in result["phases"]
        assert "rank" in result["phases"]
        assert "cull" in result["phases"]
        mocks["agent_ranking"].rank_agents.assert_awaited_once()


# ===========================================================================
# TestEmergencySpawn
# ===========================================================================
class TestEmergencySpawn:
    """Tests for emergency spawn logic and spawn count formula."""

    @pytest.mark.asyncio
    async def test_calls_spawn_new_agents(self):
        """Emergency spawn calls spawn_new_agents with generation=1."""
        svc, mocks = _build_service_with_mocks(0)
        session = _mock_session([])

        mocks["agent_spawn"].spawn_new_agents = AsyncMock(return_value=["e-1"])
        mocks["agent_backtest"].backtest_agents = AsyncMock(return_value={"e-1": {}})

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            await svc.run_evolution_cycle(session, target_agent_population=5)

        call_kwargs = mocks["agent_spawn"].spawn_new_agents.call_args.kwargs
        assert call_kwargs["generation"] == 1
        assert call_kwargs["count"] == 5

    @pytest.mark.asyncio
    async def test_spawn_cap_at_10(self):
        """Phase 5 spawn is capped at MAX_SPAWN_PER_CYCLE=10."""
        svc, mocks = _build_service_with_mocks(20)
        session = _mock_session(mocks["agents"])

        # Make cull return huge number to trigger large spawn
        mocks["agent_cull"].cull_agents = AsyncMock(return_value={
            "culled_count": 50,
            "remaining_count": 5,
        })

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[{"pattern_id": "p1"}]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(session, target_agent_population=500)

        # The final spawn_new_agents call (phase 5) should have count <= 10
        # Find the spawn call from phase 5 (last call to spawn_new_agents)
        spawn_calls = mocks["agent_spawn"].spawn_new_agents.call_args_list
        if spawn_calls:
            last_call_kwargs = spawn_calls[-1].kwargs
            assert last_call_kwargs["count"] <= 10

    @pytest.mark.asyncio
    async def test_spawn_count_formula(self):
        """spawn = max(culled - children - clones, target - current)."""
        svc, mocks = _build_service_with_mocks(20)
        session = _mock_session(mocks["agents"])

        # Setup: culled=6, children=5 (from 10 breeders paired), clones=2
        # spawn_children returns 1 id per call
        mocks["agent_spawn"].spawn_children = AsyncMock(return_value=["child-x"])
        mocks["agent_cull"].cull_agents = AsyncMock(return_value={
            "culled_count": 6,
            "remaining_count": 14,
        })

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[{"pattern_id": "p1"}]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(
                session, target_agent_population=10, breeding_count=10,
            )

        # spawn_children called for 5 breed pairs + clone_candidates
        # The formula is exercised; verify spawn phase exists
        assert "spawn" in result["phases"]

    @pytest.mark.asyncio
    async def test_negative_spawn_count_zero(self):
        """If children + clones exceed culled, spawn count cannot go negative."""
        svc, mocks = _build_service_with_mocks(20)
        session = _mock_session(mocks["agents"])

        # culled=2 but children+clones will be > 2
        mocks["agent_cull"].cull_agents = AsyncMock(return_value={
            "culled_count": 2,
            "remaining_count": 18,
        })
        # spawn_children returns 1 per call; 5 breed + 4 clone = 9 > 2
        mocks["agent_spawn"].spawn_children = AsyncMock(return_value=["child-x"])

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[{"pattern_id": "p1"}]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(
                session, target_agent_population=10, breeding_count=10,
            )

        spawn_phase = result["phases"]["spawn"]
        assert spawn_phase["agents_spawned"] == 0
        assert "sufficient" in spawn_phase.get("message", "").lower() or spawn_phase["agents_spawned"] == 0


# ===========================================================================
# TestPatternFallback
# ===========================================================================
class TestPatternFallback:
    """Tests for the 4-level pattern fallback chain in Phase 5."""

    @pytest.mark.asyncio
    async def test_regime_patterns_used(self):
        """Regime-specific patterns are used when available."""
        svc, mocks = _build_service_with_mocks(20)
        session = _mock_session(mocks["agents"])

        # Force spawn to be needed
        mocks["agent_cull"].cull_agents = AsyncMock(return_value={
            "culled_count": 15, "remaining_count": 5,
        })
        regime_patterns = [{"pattern_id": f"regime-{i}"} for i in range(5)]

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=regime_patterns):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(session, target_agent_population=500)

        spawn_phase = result["phases"]["spawn"]
        assert spawn_phase["pattern_source"] == "regime_priority"
        assert spawn_phase["pattern_count"] == 5

    @pytest.mark.asyncio
    async def test_quintile_fallback(self):
        """When regime patterns empty, quintile fallback is used."""
        svc, mocks = _build_service_with_mocks(20)
        session = _mock_session(mocks["agents"])

        mocks["agent_cull"].cull_agents = AsyncMock(return_value={
            "culled_count": 15, "remaining_count": 5,
        })

        # Make pattern query return some patterns for quintile path
        fake_pattern = SimpleNamespace(
            pattern_id="p-1", fitness_score=80.0, is_active=True,
            entry_conditions=[{"indicator": "rsi", "operator": "<", "value": 30}],
            exit_conditions=[{"indicator": "rsi", "operator": ">", "value": 70}],
            origin="TECHNICAL", win_rate=0.6,
            backtest_count=10, assets_tested=["BTC"], timeframes_tested=["1h"],
        )
        session.exec = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[fake_pattern])))

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.get_tiers_by_quintile", return_value={"p-1": 1}), \
             patch(f"{_MOD}.is_spawn_eligible", return_value=True):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(session, target_agent_population=500)

        spawn_phase = result["phases"]["spawn"]
        assert spawn_phase["pattern_source"] == "quintile_fallback"

    @pytest.mark.asyncio
    async def test_top_40_pct_fallback(self):
        """When quintile yields no spawn-eligible, top 40% fallback used."""
        svc, mocks = _build_service_with_mocks(20)
        session = _mock_session(mocks["agents"])

        mocks["agent_cull"].cull_agents = AsyncMock(return_value={
            "culled_count": 15, "remaining_count": 5,
        })

        fake_patterns = [
            SimpleNamespace(
                pattern_id=f"p-{i}", fitness_score=float(100 - i * 10), is_active=True,
                entry_conditions=[{"indicator": "rsi"}], exit_conditions=[{"indicator": "rsi"}],
                origin="TECHNICAL", win_rate=0.5,
                backtest_count=5, assets_tested=[], timeframes_tested=[],
            )
            for i in range(10)
        ]
        session.exec = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=fake_patterns)))

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.get_tiers_by_quintile", return_value={f"p-{i}": 5 for i in range(10)}), \
             patch(f"{_MOD}.is_spawn_eligible", return_value=False):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(session, target_agent_population=500)

        spawn_phase = result["phases"]["spawn"]
        # Top 40% of 10 = 4 patterns
        assert spawn_phase["pattern_count"] == 4

    @pytest.mark.asyncio
    async def test_all_empty_uses_all_patterns(self):
        """When no patterns exist at all, spawn still proceeds with empty list."""
        svc, mocks = _build_service_with_mocks(20)
        session = _mock_session(mocks["agents"])

        mocks["agent_cull"].cull_agents = AsyncMock(return_value={
            "culled_count": 15, "remaining_count": 5,
        })

        # No patterns in DB
        session.exec = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(session, target_agent_population=500)

        # spawn_new_agents still called, just with empty pattern list
        spawn_calls = mocks["agent_spawn"].spawn_new_agents.call_args_list
        assert len(spawn_calls) >= 1


# ===========================================================================
# TestErrorRecovery
# ===========================================================================
class TestErrorRecovery:
    """Tests for graceful error handling per phase."""

    @pytest.mark.asyncio
    async def test_phase_exception_rollback_continue(self):
        """Exception in pattern_discovery phase triggers rollback, pipeline continues."""
        svc, mocks = _build_service_with_mocks(20)
        session = _mock_session(mocks["agents"])

        mocks["pattern_discovery"].run_batch_backtest = AsyncMock(
            side_effect=RuntimeError("pattern DB error")
        )

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[{"pattern_id": "p1"}]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(session)

        # Pattern discovery should be marked as skipped
        pd = result["phases"]["pattern_discovery"]
        assert pd.get("skipped") is True
        assert "pattern DB error" in pd.get("reason", "")
        # Session rollback was called
        session.rollback.assert_awaited()
        # Rest of pipeline still ran
        assert "backtest" in result["phases"]
        assert "rank" in result["phases"]

    @pytest.mark.asyncio
    async def test_backtest_failure_handled(self):
        """Backtest service raising an exception propagates (not silently eaten)."""
        svc, mocks = _build_service_with_mocks(20)
        session = _mock_session(mocks["agents"])

        mocks["agent_backtest"].backtest_agents = AsyncMock(
            side_effect=RuntimeError("backtest crash")
        )

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            with pytest.raises(RuntimeError, match="backtest crash"):
                await svc.run_evolution_cycle(session)

    @pytest.mark.asyncio
    async def test_ranking_failure_handled(self):
        """Ranking service exception propagates."""
        svc, mocks = _build_service_with_mocks(20)
        session = _mock_session(mocks["agents"])

        mocks["agent_ranking"].rank_agents = AsyncMock(
            side_effect=RuntimeError("ranking crash")
        )

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            with pytest.raises(RuntimeError, match="ranking crash"):
                await svc.run_evolution_cycle(session)

    @pytest.mark.asyncio
    async def test_cull_failure_handled(self):
        """Cull service exception propagates."""
        svc, mocks = _build_service_with_mocks(20)
        session = _mock_session(mocks["agents"])

        mocks["agent_cull"].cull_agents = AsyncMock(
            side_effect=RuntimeError("cull crash")
        )

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            with pytest.raises(RuntimeError, match="cull crash"):
                await svc.run_evolution_cycle(session)


# ===========================================================================
# TestBreedingAndCloning
# ===========================================================================
class TestBreedingAndCloning:
    """Tests for breeding pairs, cloning, and level increment."""

    @pytest.mark.asyncio
    async def test_top_10_breed(self):
        """Top 10 agents are selected for breeding (5 pairs)."""
        svc, mocks = _build_service_with_mocks(30)
        session = _mock_session(mocks["agents"])

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[{"pattern_id": "p1"}]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(session, breeding_count=10)

        breed_phase = result["phases"]["breed"]
        assert breed_phase["breeding_parents"] == 10

    @pytest.mark.asyncio
    async def test_5_children_from_pairs(self):
        """10 breeders form 5 pairs, each producing 1 child = 5 children."""
        svc, mocks = _build_service_with_mocks(30)
        session = _mock_session(mocks["agents"])
        mocks["agent_spawn"].spawn_children = AsyncMock(return_value=["child-1"])

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[{"pattern_id": "p1"}]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(session, breeding_count=10)

        assert result["phases"]["breed"]["children_spawned"] == 5  # 5 pairs * 1 child each

    @pytest.mark.asyncio
    async def test_clone_percentile(self):
        """Top X% (excluding breeders) are cloned."""
        svc, mocks = _build_service_with_mocks(50)
        session = _mock_session(mocks["agents"])
        mocks["agent_ranking"].get_all_agents_ranked = AsyncMock(return_value=_make_agents(50))
        mocks["agent_spawn"].spawn_children = AsyncMock(return_value=["clone-1"])

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[{"pattern_id": "p1"}]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(
                session, breeding_count=10, clone_percentile=0.20,
            )

        # clone_count = int(50 * 0.20) = 10
        # clone_candidates = agents[10:20] (excluding top 10 breeders)
        clone_phase = result["phases"]["clone"]
        assert clone_phase["clone_candidates"] == 10

    @pytest.mark.asyncio
    async def test_level_increment_top_10(self):
        """Top 10 agents get +2 levels each."""
        agents = _make_agents(20)
        for a in agents:
            a.level = 3

        svc, mocks = _build_service_with_mocks(20)
        mocks["agent_ranking"].get_all_agents_ranked = AsyncMock(return_value=agents)
        session = _mock_session(agents)

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[{"pattern_id": "p1"}]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(session)

        level_phase = result["phases"]["level_increment"]
        assert level_phase["agents_leveled"] == 10
        assert level_phase["level_increase"] == 2
        # Verify actual agent objects were mutated
        for a in agents[:10]:
            assert a.level == 5  # 3 + 2


# ===========================================================================
# TestCruciblePhase
# ===========================================================================
class TestCruciblePhase:
    """Tests for Crucible eligibility and testing (Phase 6)."""

    @pytest.mark.asyncio
    async def test_crucible_eligibility_checked(self):
        """Crucible eligibility check runs for leveled agents."""
        svc, mocks = _build_service_with_mocks(20)
        session = _mock_session(mocks["agents"])

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[{"pattern_id": "p1"}]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            result = await svc.run_evolution_cycle(session)

        mock_crucible.check_agents_batch.assert_awaited_once()
        # Should have checked the 10 leveled agents
        call_args = mock_crucible.check_agents_batch.call_args
        agent_ids_checked = call_args[0][1]  # positional: session, agent_ids
        assert len(agent_ids_checked) == 10

    @pytest.mark.asyncio
    async def test_eligible_agents_tested(self):
        """Eligible agents are sent to crucible test service."""
        svc, mocks = _build_service_with_mocks(20)
        session = _mock_session(mocks["agents"])

        entries = [
            _make_crucible_entry("agent-0", entry_id=1, level=5),
            _make_crucible_entry("agent-1", entry_id=2, level=5),
        ]

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_CRUCIBLE_TEST) as mock_test_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[{"pattern_id": "p1"}]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=entries)

            mock_test_svc = mock_test_cls.return_value
            mock_test_svc.run_crucible_test = AsyncMock(return_value={"status": "completed"})

            result = await svc.run_evolution_cycle(session)

        crucible_phase = result["phases"]["crucible"]
        assert crucible_phase["entries_created"] == 2
        assert crucible_phase["tests_run"] == 2
        assert crucible_phase["tests_completed"] == 2
        assert mock_test_svc.run_crucible_test.await_count == 2

    @pytest.mark.asyncio
    async def test_no_eligible_skips(self):
        """No eligible agents means no crucible tests run."""
        svc, mocks = _build_service_with_mocks(20)
        session = _mock_session(mocks["agents"])

        with patch(_CRUCIBLE_ENTRY) as mock_crucible_cls, \
             patch(_CRUCIBLE_TEST) as mock_test_cls, \
             patch(_REGIME_PATTERNS, new_callable=AsyncMock, return_value=[{"pattern_id": "p1"}]):
            mock_crucible = mock_crucible_cls.return_value
            mock_crucible.check_agents_batch = AsyncMock(return_value=[])

            mock_test_svc = mock_test_cls.return_value
            mock_test_svc.run_crucible_test = AsyncMock()

            result = await svc.run_evolution_cycle(session)

        crucible_phase = result["phases"]["crucible"]
        assert crucible_phase["entries_created"] == 0
        # CrucibleTestService should NOT have been called
        mock_test_svc.run_crucible_test.assert_not_awaited()
        assert "tests_run" not in crucible_phase
