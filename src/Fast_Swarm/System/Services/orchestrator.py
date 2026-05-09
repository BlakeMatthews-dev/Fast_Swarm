"""
Lightweight Orchestrator - Sequential backtest pipeline.

Priorities:
- P0: Data collection (always running, never blocked)
- P1: Live trades (not implemented yet)
- P2: Backtesting/Evolution (sequential pipeline)

Pipeline phases (run sequentially, not concurrently):
1. Grab windows ONCE from pool
2. Test batch of patterns on those windows
3. Test batch of agents on those SAME windows
4. Repeat until all patterns/agents tested on current windows
5. Run evolution cycle
6. Run pattern discovery
7. Go to step 1 with new windows

This prevents:
- Testing patterns AND agents at the same time (resource contention)
- Multiple backtest loops running concurrently
- Data loading happening multiple times
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession


class PipelinePhase(Enum):
    """Current phase of the backtest pipeline."""
    IDLE = "idle"
    LOADING_WINDOWS = "loading_windows"
    TESTING_PATTERNS = "testing_patterns"
    TESTING_AGENTS = "testing_agents"
    EVOLUTION = "evolution"
    PATTERN_DISCOVERY = "pattern_discovery"
    COOLDOWN = "cooldown"


@dataclass
class PipelineState:
    """Current state of the orchestrator pipeline."""
    phase: PipelinePhase = PipelinePhase.IDLE
    started_at: datetime | None = None

    # Current batch tracking
    windows_loaded: int = 0
    patterns_tested: int = 0
    patterns_total: int = 0
    agents_tested: int = 0
    agents_total: int = 0

    # Cycle tracking
    cycles_completed: int = 0
    last_cycle_at: datetime | None = None

    # Error tracking
    last_error: str | None = None
    consecutive_errors: int = 0

    # Timeout tracking
    patterns_skipped_timeout: int = 0  # Patterns skipped due to timeout
    agents_skipped_timeout: int = 0  # Agents skipped due to timeout

    # Watchdog tracking
    last_progress_at: datetime | None = None  # Last time any progress was made
    watchdog_killed_phase: bool = False  # Set true if watchdog had to kill a phase


class BacktestOrchestrator:
    """
    Lightweight orchestrator for sequential backtest pipeline.

    Key design principles:
    - ONE thing at a time (no concurrent backtesting)
    - Download ONCE, test MANY (precompute-fanout)
    - Never block P0 data collection
    - Graceful degradation on errors
    """

    # Configuration
    PATTERNS_PER_BATCH = 500  # Patterns to test per window
    AGENTS_PER_BATCH = 100  # Agents to test per window
    WINDOWS_PER_BATCH = 1  # Windows to load per batch (1 = test one at a time)
    WINDOWS_BEFORE_EVOLUTION = 50  # Test this many windows before evolution/discovery
    PARALLEL_TESTS = 8  # Tuned for 128GB system with PostgreSQL memory fix
    COOLDOWN_SECONDS = 60  # Pause between cycles
    MAX_CONSECUTIVE_ERRORS = 3  # Stop after this many errors

    # Timeout settings (prevent freezing)
    PATTERN_TIMEOUT_SECONDS = 30  # Max time per pattern test before skip
    AGENT_TIMEOUT_SECONDS = 60  # Max time per agent test before skip
    PHASE_WATCHDOG_SECONDS = 600  # 10 minutes - kill phase if no progress

    def __init__(self):
        self.state = PipelineState()
        self._running = False
        self._task: asyncio.Task | None = None

        # Cached data (download once, use many times)
        self._current_windows: list = []
        self._preloaded_candles: dict = {}

    @property
    def is_running(self) -> bool:
        return self._running

    def get_status(self) -> dict:
        """Get current orchestrator status for API/dashboard."""
        return {
            "running": self._running,
            "phase": self.state.phase.value,
            "started_at": self.state.started_at.isoformat() if self.state.started_at else None,
            "windows_loaded": self.state.windows_loaded,
            "patterns_tested": self.state.patterns_tested,
            "patterns_total": self.state.patterns_total,
            "agents_tested": self.state.agents_tested,
            "agents_total": self.state.agents_total,
            "cycles_completed": self.state.cycles_completed,
            "last_cycle_at": self.state.last_cycle_at.isoformat() if self.state.last_cycle_at else None,
            "last_error": self.state.last_error,
        }

    async def start(self):
        """Start the orchestrator pipeline."""
        if self._running:
            print("[Orchestrator] Already running")
            return

        self._running = True
        self.state.started_at = datetime.utcnow()
        self.state.consecutive_errors = 0
        print("[Orchestrator] Starting sequential backtest pipeline...")

        self._task = asyncio.create_task(self._run_pipeline())

    async def stop(self):
        """Stop the orchestrator pipeline gracefully."""
        if not self._running:
            return

        print("[Orchestrator] Stopping...")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self.state.phase = PipelinePhase.IDLE
        print("[Orchestrator] Stopped")

    async def _run_pipeline(self):
        """Main pipeline loop - runs phases sequentially."""
        from Fast_Swarm.Database import async_session_maker

        while self._running:
            try:
                async with async_session_maker() as session:
                    # Test multiple windows before evolution
                    windows_tested = 0

                    for _ in range(self.WINDOWS_BEFORE_EVOLUTION):
                        if not self._running:
                            break

                        # Phase 1: Load 1 window
                        await self._phase_load_windows(session)

                        if not self._current_windows:
                            print("[Orchestrator] No windows loaded, skipping")
                            continue

                        # Phase 2: Test patterns on this window
                        await self._phase_test_patterns(session)

                        # Phase 3: Test agents on this SAME window
                        await self._phase_test_agents(session)

                        windows_tested += 1
                        print(f"[Orchestrator] Window {windows_tested}/{self.WINDOWS_BEFORE_EVOLUTION} complete")

                    # Phase 4: Evolution cycle (after testing many windows)
                    await self._phase_evolution(session)

                    # Phase 5: Pattern discovery
                    await self._phase_pattern_discovery(session)

                    # Cycle complete
                    self.state.cycles_completed += 1
                    self.state.last_cycle_at = datetime.utcnow()
                    self.state.consecutive_errors = 0

                    print(f"[Orchestrator] Cycle {self.state.cycles_completed} complete ({windows_tested} windows tested)")

                    # Cooldown before next cycle
                    await self._phase_cooldown()

            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.state.last_error = str(e)
                self.state.consecutive_errors += 1
                print(f"[Orchestrator] Error in pipeline: {e}")

                if self.state.consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
                    print(f"[Orchestrator] Too many errors ({self.state.consecutive_errors}), stopping")
                    self._running = False
                    break

                # Brief pause before retry
                await asyncio.sleep(30)

    async def _phase_load_windows(self, session: AsyncSession):
        """Phase 1: Load windows from pool (download once)."""
        self.state.phase = PipelinePhase.LOADING_WINDOWS
        print("[Orchestrator] Phase 1: Loading windows from pool...")

        from Fast_Swarm.local_agents.backtest.data import LazyCandleCache
        from Fast_Swarm.local_agents.backtest.windows import get_pool_stats, get_windows, is_initialized

        # Check pool is initialized
        if not is_initialized():
            print("[Orchestrator] Window pool not initialized!")
            self._current_windows = []
            return

        # Get windows from pool
        pool_windows = get_windows(count=self.WINDOWS_PER_BATCH)

        # Convert to dict format
        self._current_windows = [
            {
                "asset": w.symbol,
                "timeframe": w.timeframe,
                "start_ts": w.start_ts,
                "end_ts": w.end_ts,
                "regime": f"random_{w.timeframe}",
            }
            for w in pool_windows
        ]

        self.state.windows_loaded = len(self._current_windows)

        # Load candles (triggers enrichment for unenriched data)
        if self._current_windows:
            self._preloaded_candles = LazyCandleCache(pool_windows)
            # Pre-warm the cache — this triggers enrichment if needed
            # so by the time patterns run, data is ready
            w = pool_windows[0]
            cache_key = f"{w.symbol}_{w.timeframe}"
            try:
                df = self._preloaded_candles[cache_key]
                # Check if enrichment produced usable indicators
                has_indicators = "rsi_14" in df.columns and df["rsi_14"].notna().sum() > 50
                if not has_indicators:
                    print(f"[Orchestrator] Window {w.symbol}/{w.timeframe} has no enriched indicators — skipping pattern tests")
                    self._current_windows = []  # Empty = phase 2 skips
                    return
            except Exception as e:
                print(f"[Orchestrator] Cache warm failed: {e}")

        sym = f"{pool_windows[0].symbol}/{pool_windows[0].timeframe}" if pool_windows else "none"
        print(f"[Orchestrator] Loaded {len(self._current_windows)} windows: {sym}")

    async def _phase_test_patterns(self, session: AsyncSession):
        """Phase 2: Test patterns on current windows.

        Architecture: compute-then-write.
        1. Load all patterns from DB (one query)
        2. Run all pattern evaluations (pure computation, no DB writes)
        3. Collect results in memory
        4. Write everything back in one batch
        """
        self.state.phase = PipelinePhase.TESTING_PATTERNS
        self.state.watchdog_killed_phase = False
        print("[Orchestrator] Phase 2: Testing patterns...")

        from sqlmodel import select

        from Fast_Swarm.Patterns.Models.pattern_models import Pattern
        from Fast_Swarm.Patterns.Services.discovery_service import PatternDiscoveryService

        # 1. LOAD: Get patterns that need testing (one query)
        result = await session.execute(
            select(Pattern)
            .where(Pattern.is_active.is_(True))
            .where(Pattern.status != "archived")
            .order_by(Pattern.priority.desc(), Pattern.last_backtest_at.asc().nullsfirst())
            .limit(self.PATTERNS_PER_BATCH)
        )
        patterns = result.scalars().all()

        self.state.patterns_total = len(patterns)
        self.state.patterns_tested = 0
        self.state.patterns_skipped_timeout = 0
        self.state.last_progress_at = datetime.utcnow()

        if not patterns:
            print("[Orchestrator] No patterns to test")
            return

        # 2a. PRE-COMPUTE: Benchmarks for each window (one DB query per window)
        from Fast_Swarm.Patterns.Services.discovery_service import (
            PatternTestContext,
            _apply_result_to_pattern,
        )

        benchmarks = {}
        for w in self._current_windows:
            try:
                asset, tf = w.get("asset", "BTC"), w.get("timeframe", "1h")
                result = await session.execute(
                    text("""
                        SELECT close FROM enhanced_candles
                        WHERE symbol = :asset AND timeframe = :tf
                          AND EXTRACT(EPOCH FROM time) * 1000 >= :start
                          AND EXTRACT(EPOCH FROM time) * 1000 <= :end
                        ORDER BY time LIMIT 1
                    """),
                    {"asset": asset, "tf": tf, "start": w["start_ts"], "end": w["end_ts"]},
                )
                start_row = result.fetchone()
                result = await session.execute(
                    text("""
                        SELECT close FROM enhanced_candles
                        WHERE symbol = :asset AND timeframe = :tf
                          AND EXTRACT(EPOCH FROM time) * 1000 >= :start
                          AND EXTRACT(EPOCH FROM time) * 1000 <= :end
                        ORDER BY time DESC LIMIT 1
                    """),
                    {"asset": asset, "tf": tf, "start": w["start_ts"], "end": w["end_ts"]},
                )
                end_row = result.fetchone()
                if start_row and end_row and float(start_row[0]) > 0:
                    bh = ((float(end_row[0]) - float(start_row[0])) / float(start_row[0])) * 100
                    benchmarks[(asset, tf, w["start_ts"])] = bh
            except Exception:
                pass  # Benchmark defaults to 0 if query fails

        # 2b. CREATE: Shared context (one loader, one config, shared candle cache)
        ctx = PatternTestContext(
            preloaded_candles=self._preloaded_candles,
            benchmarks=benchmarks,
        )

        # 2c. COMPUTE: Run all patterns (pure computation, no DB writes)
        service = PatternDiscoveryService()
        semaphore = asyncio.Semaphore(self.PARALLEL_TESTS)
        collected_results = []  # (pattern, result_dict) pairs
        zero_trade_count = 0
        tested_count = 0
        watchdog_triggered = False

        async def test_one_pattern(pattern, idx: int):
            """Test single pattern — pure computation, no DB."""
            nonlocal zero_trade_count, tested_count, watchdog_triggered
            async with semaphore:
                if not self._running or watchdog_triggered:
                    return

                try:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(
                            service.compute_pattern_results,
                            pattern,
                            self._current_windows,
                            ctx,
                        ),
                        timeout=self.PATTERN_TIMEOUT_SECONDS,
                    )

                    tested_count += 1
                    self.state.patterns_tested = tested_count
                    self.state.last_progress_at = datetime.utcnow()

                    trades = result.get("total_trades", 0) if result else 0
                    if trades == 0:
                        zero_trade_count += 1

                    collected_results.append((pattern, result))

                except asyncio.TimeoutError:
                    self.state.patterns_skipped_timeout += 1
                    self.state.last_progress_at = datetime.utcnow()
                    collected_results.append((pattern, {"status": "timeout", "runs": 1}))
                    print(f"[Orchestrator] TIMEOUT: Pattern {pattern.pattern_id[:8]} exceeded {self.PATTERN_TIMEOUT_SECONDS}s")
                except Exception as e:
                    self.state.last_progress_at = datetime.utcnow()
                    print(f"[Orchestrator] Error testing pattern {pattern.pattern_id[:8]}: {e}")

        async def watchdog():
            """Kill the phase if no progress for PHASE_WATCHDOG_SECONDS."""
            nonlocal watchdog_triggered
            while not watchdog_triggered and self._running:
                await asyncio.sleep(30)
                if self.state.last_progress_at:
                    elapsed = (datetime.utcnow() - self.state.last_progress_at).total_seconds()
                    if elapsed > self.PHASE_WATCHDOG_SECONDS:
                        watchdog_triggered = True
                        self.state.watchdog_killed_phase = True
                        print(f"[Orchestrator] WATCHDOG: No progress for {elapsed:.0f}s — killing phase")
                        return

        watchdog_task = asyncio.create_task(watchdog())
        try:
            await asyncio.gather(*[test_one_pattern(p, i) for i, p in enumerate(patterns)])
        finally:
            watchdog_task.cancel()
            try:
                await watchdog_task
            except asyncio.CancelledError:
                pass

        # 3. WRITE: Apply all results and persist in one transaction
        if collected_results:
            total_trades_persisted = 0
            for pattern, result in collected_results:
                _apply_result_to_pattern(pattern, result)
                session.add(pattern)

            # Collect and persist all trade records from all patterns
            all_trade_records = []
            for _, result in collected_results:
                trade_records = result.get("trades", [])
                if trade_records:
                    all_trade_records.extend(trade_records)

            if all_trade_records:
                try:
                    from Fast_Swarm.Trades.Services.trade_service import persist_backtest_trades
                    total_trades_persisted = await persist_backtest_trades(
                        session, all_trade_records, source="pattern_backtest"
                    )
                except Exception as e:
                    print(f"[Orchestrator] Trade persist error: {e}")

            try:
                await session.commit()
                trades_with_results = sum(1 for _, r in collected_results if r.get("total_trades", 0) > 0)
                print(f"[Orchestrator] Persisted {len(collected_results)} patterns ({trades_with_results} with trades, {total_trades_persisted} trade records)")
            except Exception as e:
                print(f"[Orchestrator] Batch commit error: {e}")
                await session.rollback()

        await session.commit()

        # Summary with diagnostic warning if many patterns produced 0 trades
        timeouts = sum(1 for r in results if r.get("status") == "timeout")
        zero_pct = (zero_trade_count / len(patterns) * 100) if patterns else 0

        summary = f"[Orchestrator] Tested {tested_count}/{self.state.patterns_total} patterns"
        if timeouts > 0:
            summary += f" (timeouts={timeouts})"
        if watchdog_triggered:
            summary += " ⚠️ WATCHDOG KILLED"
        if zero_pct > 50:
            summary += f" ⚠️ {zero_pct:.0f}% had 0 trades - check indicator enrichment!"
        print(summary)

    async def _phase_test_agents(self, session: AsyncSession):
        """Phase 3: Test agents on current windows (compute-then-write).

        Architecture: ONE batch read → parallel pure compute (no DB) → ONE batch write.
        This prevents the concurrent session bug where N agents write to one session.
        """
        self.state.phase = PipelinePhase.TESTING_AGENTS
        print("[Orchestrator] Phase 3: Testing agents (compute-then-write)...")

        from sqlmodel import select

        from Fast_Swarm.Agents.Models.agent_models import Agent

        # ── BATCH READ: Load agents + hydrate patterns ────────────────
        result = await session.execute(
            select(Agent)
            .where(Agent.is_active.is_(True))
            .order_by(Agent.last_backtest_at.asc().nullsfirst())
            .limit(self.AGENTS_PER_BATCH)
        )
        agents = result.scalars().all()

        self.state.agents_total = len(agents)
        self.state.agents_tested = 0

        if not agents:
            print("[Orchestrator] No agents to test")
            return

        # Pre-hydrate all pattern references in one batch query
        from Fast_Swarm.Patterns.Models.pattern_models import Pattern

        all_ref_ids = set()
        for agent in agents:
            assigned = agent.assigned_patterns or {}
            if isinstance(assigned, dict):
                for p in assigned.get("base", []):
                    if isinstance(p, str):
                        all_ref_ids.add(p)
                    elif isinstance(p, dict) and not (p.get("entry_conditions") and p.get("exit_conditions")):
                        pid = p.get("pattern_id", p.get("id", ""))
                        if pid:
                            all_ref_ids.add(pid)
            elif isinstance(assigned, list):
                for item in assigned:
                    if isinstance(item, str):
                        all_ref_ids.add(item)

        pattern_cache = {}
        if all_ref_ids:
            pat_result = await session.execute(
                select(Pattern).where(Pattern.pattern_id.in_(list(all_ref_ids)))
            )
            for p in pat_result.scalars().all():
                pattern_cache[p.pattern_id] = {
                    "pattern_id": p.pattern_id,
                    "name": p.name,
                    "entry_conditions": p.entry_conditions,
                    "exit_conditions": p.exit_conditions,
                }
            print(f"[Orchestrator] Pre-hydrated {len(pattern_cache)} patterns for {len(agents)} agents")

        # ── PARALLEL COMPUTE: No DB access ────────────────────────────
        from Fast_Swarm.Agents.Services.backtest_service import AgentBacktestService

        service = AgentBacktestService()
        semaphore = asyncio.Semaphore(self.PARALLEL_TESTS)
        computed_results = []  # List of (agent, result_dict) or (agent, Exception)

        async def compute_one_agent(agent):
            """Pure compute — no session access."""
            async with semaphore:
                if not self._running:
                    return agent, {"skipped": True}
                try:
                    result = await service.backtest_agent_on_windows_compute(
                        agent,
                        self._current_windows,
                        preloaded_candles=self._preloaded_candles,
                        pattern_cache=pattern_cache,
                    )
                    return agent, result
                except Exception as e:
                    print(f"[Orchestrator] Error computing agent {agent.agent_id}: {e}")
                    return agent, {"error": str(e)}

        raw_results = await asyncio.gather(
            *[compute_one_agent(a) for a in agents],
            return_exceptions=True,
        )

        for r in raw_results:
            if isinstance(r, Exception):
                print(f"[Orchestrator] Agent compute exception: {r}")
                continue
            computed_results.append(r)

        # ── BATCH WRITE: Apply all results to DB ──────────────────────
        from datetime import datetime
        from decimal import Decimal

        for agent, result in computed_results:
            if result.get("error") or result.get("skipped"):
                continue

            agent.fitness_score = float(result.get("fitness", 0.0))
            agent.sortino_ratio = result.get("sortino")
            agent.win_rate = result.get("win_rate")
            agent.total_trades = int(agent.total_trades or 0) + int(result.get("total_trades", 0))
            agent.winning_trades = int(agent.winning_trades or 0) + int(result.get("winning_trades", 0))
            agent.total_pnl = Decimal(str(float(agent.total_pnl or 0) + float(result.get("total_pnl", 0))))
            agent.backtest_count = int(agent.backtest_count or 0) + 1
            agent.last_backtest_at = datetime.utcnow()

            # Persist hydrated patterns if they were resolved from refs
            if result.get("hydrated_patterns"):
                agent.assigned_patterns = {"base": result["hydrated_patterns"]}

            # Per-regime fitness
            if result.get("fitness_by_regime"):
                agent.fitness_by_regime = result["fitness_by_regime"]

            self.state.agents_tested += 1

        await session.commit()
        print(f"[Orchestrator] Tested {self.state.agents_tested}/{self.state.agents_total} agents")

    async def _phase_evolution(self, session: AsyncSession):
        """Phase 4: Run evolution cycle."""
        self.state.phase = PipelinePhase.EVOLUTION
        print("[Orchestrator] Phase 4: Running evolution...")

        try:
            from Fast_Swarm.System.Services.evolution_cycle_service import EvolutionCycleService

            service = EvolutionCycleService()
            result = await service.run_evolution_cycle(session)

            print(f"[Orchestrator] Evolution complete: {result}")

        except Exception as e:
            print(f"[Orchestrator] Evolution error: {e}")

    async def _phase_pattern_discovery(self, session: AsyncSession):
        """Phase 5: Run pattern discovery."""
        self.state.phase = PipelinePhase.PATTERN_DISCOVERY
        print("[Orchestrator] Phase 5: Running pattern discovery...")

        try:
            from Fast_Swarm.Patterns.Services.discovery_service import PatternDiscoveryService

            service = PatternDiscoveryService()
            result = await service.run_discovery_cycle(session)

            print(f"[Orchestrator] Pattern discovery complete: {result}")

        except Exception as e:
            print(f"[Orchestrator] Pattern discovery error: {e}")

    async def _phase_cooldown(self):
        """Cooldown phase between cycles."""
        self.state.phase = PipelinePhase.COOLDOWN
        print(f"[Orchestrator] Cooldown for {self.COOLDOWN_SECONDS}s...")

        # Sleep in chunks to allow graceful shutdown
        for _ in range(self.COOLDOWN_SECONDS // 5):
            if not self._running:
                break
            await asyncio.sleep(5)


# Global singleton
_orchestrator: BacktestOrchestrator | None = None


def get_orchestrator() -> BacktestOrchestrator:
    """Get or create the global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = BacktestOrchestrator()
    return _orchestrator
