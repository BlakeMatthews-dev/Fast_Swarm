# Shared Todo List

All non-trivial todos from Claude sessions are logged here.

## Agent Labeling Format

```
- [ ] Unclaimed task
- [@TASK_ID] Task claimed by agent (in progress)
- [x] Completed task
- [x][@TASK_ID] Completed by specific agent
- [!] BLOCKED - needs human or dependency
```

When an agent claims a task, it changes `[ ]` to `[@its-task-id]`.
Other agents MUST NOT touch tasks labeled with another agent's ID.

---

## Active Todos

### Efficiency Improvements: N+1 Fixes and Eager Enrichment

**Source Plan:** C:\Users\Admin\.claude\plans\generic-tumbling-sun.md

#### Phase 1: Eager Candle Preloading (Orchestrator)

- [@orch-ea1] ORCH-EAGER: Add eager preload call to orchestrator._phase_load_windows()
  - File: src/Fast_Swarm/System/Services/orchestrator.py
  - After line 253 (LazyCandleCache creation), add: `await asyncio.to_thread(self._preloaded_candles.preload_all)`
  - Add print statement: "[Orchestrator] All candles preloaded and enriched"
  - Import asyncio if not already imported
  - Test: Orchestrator logs show "preloaded and enriched" BEFORE "Testing patterns"

- [ ] ORCH-TEST: Write test for eager preloading behavior
  - File: Tests/Unit/System/test_orchestrator_preload.py
  - Test that LazyCandleCache.preload_all() is called during _phase_load_windows
  - Test that preload completes before _phase_test_patterns is called
  - EDD: Verify determinism (same windows -> same preload calls)

#### Phase 2: Batch Pattern Loading

- [@batch-ex1] BATCH-EXTRACT: Create helper function to extract pattern reference IDs from agent
  - File: src/Fast_Swarm/Agents/Services/backtest_service.py
  - Create: `def _extract_pattern_refs(agent) -> tuple[list[dict], list[str]]`
  - Returns: (embedded_patterns, reference_ids)
  - Handles 3 forms: embedded dict, string ID, partial dict
  - This isolates the complex extraction logic for reuse

- [ ] BATCH-LOOKUP: Create helper function to batch-fetch patterns
  - File: src/Fast_Swarm/Agents/Services/backtest_service.py
  - Create: `async def _batch_fetch_patterns(session, pattern_ids: set[str]) -> dict[str, dict]`
  - Single query: `select(Pattern).where(Pattern.pattern_id.in_(list(pattern_ids)))`
  - Returns: dict mapping pattern_id -> hydrated pattern dict
  - Test: Verify single DB query for N pattern IDs

- [ ] BATCH-AGENTS: Refactor backtest_agents() to use batch pattern loading
  - File: src/Fast_Swarm/Agents/Services/backtest_service.py
  - BEFORE loop: collect all reference_ids from all agents
  - BEFORE loop: call _batch_fetch_patterns() once
  - IN loop: use memory lookup instead of DB query
  - Preserve hydrate-once persistence (write back to agent)
  - Test: Verify pattern queries reduced from N to 1

- [ ] BATCH-SINGLE: Refactor backtest_agent_on_windows() to use batch pattern loading
  - File: src/Fast_Swarm/Agents/Services/backtest_service.py
  - Use same _extract_pattern_refs() and _batch_fetch_patterns() helpers
  - For single agent, this is still 1 query but cleaner code
  - Preserve hydrate-once persistence
  - Test: Existing tests still pass

- [ ] BATCH-TEST: Write tests for batch pattern loading
  - File: Tests/Unit/Agents/test_batch_pattern_loading.py
  - Test _extract_pattern_refs() with all 3 pattern forms
  - Test _batch_fetch_patterns() returns correct dict
  - Test backtest_agents() makes only 1 pattern query for 10 agents
  - EDD: Division safety (0 agents, 0 patterns)
  - EDD: Determinism (same agents -> same pattern dict)

#### Phase 3: Evolution Path Candle Loading

- [ ] EVOL-CACHE: Refactor backtest_agents() to share candle cache across agents
  - File: src/Fast_Swarm/Agents/Services/backtest_service.py
  - BEFORE agent loop: collect all unique windows across all agents
  - BEFORE agent loop: create ONE LazyCandleCache for all windows
  - BEFORE agent loop: call preload_all() to eager-load + enrich
  - IN agent loop: pass shared cache to each engine
  - Test: Verify candle loads reduced from N*M to M (where M = unique symbol/timeframe pairs)

- [ ] EVOL-WINDOW: Optimize window collection for shared cache
  - File: src/Fast_Swarm/Agents/Services/backtest_service.py
  - Create: `async def _collect_all_windows(session, agents, assets, timeframes) -> tuple[list, dict]`
  - Returns: (all_unique_windows, agent_to_windows_map)
  - agent_to_windows_map allows filtering per-agent without re-querying
  - Test: Window query happens once, not per-agent

- [ ] EVOL-TEST: Write tests for shared candle cache in evolution path
  - File: Tests/Unit/Agents/test_evolution_candle_cache.py
  - Test that backtest_agents() creates ONE cache for multiple agents
  - Test that preload_all() is called before agent loop
  - Test that agents share the same cache instance
  - EDD: Memory efficiency (cache not duplicated)
  - EDD: Determinism (same agents+windows -> same cache state)

#### Verification and Cleanup

- [ ] VERIFY-ORCH: Integration test for orchestrator eager loading
  - File: Tests/Integration/test_orchestrator_efficiency.py
  - Start orchestrator, verify log sequence:
    1. "Loading windows from pool"
    2. "All candles preloaded and enriched"
    3. "Testing patterns"
  - Verify no lock contention errors
  - Verify no timeout errors from enrichment

- [ ] VERIFY-EVOL: Integration test for evolution path efficiency
  - File: Tests/Integration/test_backtest_efficiency.py
  - Run backtest_agents() with 5 agents
  - Instrument to count DB queries
  - Verify pattern queries = 1 (not 5)
  - Verify candle loads = M (not 5*M)

---

### Previous Tasks (Carried Forward)

#### PostgreSQL Migration for live_collector.py
- [ ] Update LiveCollector.__init__ to not pass db_path to PostgreSQL store
- [ ] Update LiveCollector to use ExtendedDataStorePostgres instead of SQLite
- [ ] Remove --db argument from live_collector.py CLI
- [ ] Verify PostgreSQL connection works with POSTGRES_PASSWORD env var
- [ ] Kill old collector processes still using SQLite
- [ ] Start live_collector.py with PostgreSQL backend
- [ ] Verify data is flowing into PostgreSQL tables

#### Deep Trace (Deferred - Low Priority)
- [ ] Deep trace: All imports and dependencies
- [ ] Deep trace: exchange_selector.py routing algorithm
- [ ] Deep trace: position_manager.py position tracking
- [ ] Deep trace: risk_manager.py circuit breakers
- [ ] Deep trace: indicators_extra JSONB flow
- [ ] Deep trace: _get_indicator_fuzzy fallback chains
- [ ] Deep trace: walk_forward pattern simulation paths
- [ ] Deep trace: Committee.evaluate_pattern live trading flow
- [ ] Deep trace: genesis_spawn_agent external module flow
- [ ] Deep trace: Agent.from_dict() deserialization paths
- [ ] Deep trace: Coach roster assignment to committees
- [ ] Deep trace: Pattern crossover/inheritance during reproduction
- [ ] Compile comprehensive code path map

---

## Completed

| Task | Agent | Completed |
|------|-------|-----------|
| Create agent-progress directory | orchestrator | 2026-01-24 |
| Create check-file-lock.py | orchestrator | 2026-01-24 |
| Create check-todo-tests.py | orchestrator | 2026-01-24 |
| Create parallel-todo-state.md | orchestrator | 2026-01-24 |
| Create shared-context.md | orchestrator | 2026-01-24 |
| Fix test_crucible.py failures | Master Test Admin | 2026-01-02 |
| Test Deep Trace failures | Master Test Admin | 2026-01-02 |
| Test agent_state.py memory system | Master Test Admin | 2026-01-02 |
| Property tests (bounds, NaN/Inf) | Master Test Admin | 2026-01-02 |
