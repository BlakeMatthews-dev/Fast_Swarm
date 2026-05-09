# MASTER IMPLEMENTATION PLAN - Fast_Swarm Trading System

**Created**: 2026-01-21
**Status**: PLANNING PHASE
**Source**: 18 Audit Reports from `/swarm/botresearch/`

---

## EXECUTIVE SUMMARY

This plan addresses 10 critical bug categories discovered across 18 audit reports covering the complete MVP flow:

```
Chaos -> Patterns -> Backtest -> Fitness by Regime -> Agent Spawn ->
Agent Backtest -> LLM consultation -> Evolution (cull/breed) ->
Crucible -> Paper Trading -> Live Trading
```

**Verified Working (No Fixes Needed):**
- Lookahead bias handling (MFE/MAE is intentional training data)
- Pattern-to-agent flow (regime fitness IS used in spawn)
- Evolution selection (lineage checks optional, fitness correct)
- Evolution cull/breed cycle (healthy implementation)
- Agent decision LLM (3-zone model working correctly)
- Crucible flow (entry triggers verified)

**Requires Fixes:**
- 4 division safety bugs (crash risk)
- 9 security vulnerabilities (4 critical)
- 8 async race conditions (data corruption risk)
- 5 backtest realism issues (0.5-1.5% optimism)
- Sortino formula error (15% inflation)
- 6 trait validation gaps
- 3 ELO mathematical errors
- 4 WebSocket silent failure modes
- 10 data integrity gaps
- 5 regime detection flaws

---

## PART 1: BUG FIX PRIORITIZATION

### P0 - BLOCKERS (Must fix before ANY testing)

These bugs will cause crashes or corrupt data, making all test results invalid.

| ID | Category | Location | Issue | Impact |
|----|----------|----------|-------|--------|
| P0-1 | Division | `backtest_service.py:509-510` | `total_w` can be 0 | ZeroDivisionError crash |
| P0-2 | Division | `backtest_service.py:545,547,549` | `regime_total` can be 0 | ZeroDivisionError crash |
| P0-3 | Division | `backtest_service.py:583` | `tf_total` can be 0 | ZeroDivisionError crash |
| P0-4 | Division | `backtest_service.py:684` | `peak` can be 0 | ZeroDivisionError crash |
| P0-5 | Data | `collector_service.py:153-164` | No OHLC validation | Negative ATR, corrupted indicators |
| P0-6 | Data | `backtest_service.py:437` | `close_price` defaults to 0 | -100% fake losses |
| P0-7 | Traits | `trio_engine.py:265` | Missing trait key | KeyError crash |

**Estimated Fix Time**: 4-6 hours

### P1 - CRITICAL (Must fix this sprint)

These bugs cause data corruption, wrong calculations, or security holes.

| ID | Category | Location | Issue | Impact |
|----|----------|----------|-------|--------|
| P1-1 | Async | `evolution_service.py:28-76` | Evolution flag race | Duplicate agents, corrupted fitness |
| P1-2 | Async | `collector_service.py:34-38` | Queue race condition | Lost/duplicated ticks |
| P1-3 | Async | `Database.py:57-66` | Pool exhaustion | Complete hang (50 connections vs 500 backtests) |
| P1-4 | Async | `evolution_service.py:104-217` | Flag permanent lock | Evolution disabled until restart |
| P1-5 | Fitness | `backtest_service.py:668-672` | Sortino uses wrong formula | 15% inflation in rankings |
| P1-6 | Backtest | `backtest_service.py:644` | Spread not deducted | 0.04-0.4% per-trade optimism |
| P1-7 | Backtest | `backtest_service.py:478` | Entry at signal close | 0.3-0.5% per-trade optimism |
| P1-8 | Traits | `backtest_service.py:365` | Unvalidated DB load | Corrupted traits flow to calculations |
| P1-9 | Traits | `evolution_service.py:323-327` | Mutation breaks derived traits | Inconsistent trait contracts |
| P1-10 | Traits | `evolution_service.py:420-428` | Crossover defaults to 0 | Traits regress toward 0 |
| P1-11 | Security | `Database.py:24` | Hardcoded password | DB compromise if env var missing |
| P1-12 | Security | `Main.py:318-330` | No auth on any endpoint | Complete system access |

**Estimated Fix Time**: 16-24 hours

### P2 - IMPORTANT (Fix soon)

These bugs cause suboptimal behavior but won't crash or corrupt data.

| ID | Category | Location | Issue | Impact |
|----|----------|----------|-------|--------|
| P2-1 | WebSocket | `base_ws.py:292-296` | No heartbeat timeout | Trading on stale data |
| P2-2 | WebSocket | `base_ws.py:303-355` | Message blocks event loop | Missing trades during flash crash |
| P2-3 | WebSocket | `base_ws.py:375-391` | Reconnect data gap | 50+ lost updates |
| P2-4 | ELO | `elo_transfer_service.py:87-114` | Non-zero-sum | ELO inflation |
| P2-5 | ELO | `governance_service.py:312` | Fixed benchmark | Pairwise comparison missing |
| P2-6 | Regime | `bear_protection_service.py:176-177` | Missing data = no danger | Should default CONSERVATIVE |
| P2-7 | Regime | `bear_protection_service.py:223-237` | Safe-to-exit blocks on None | Can't exit DEFENSIVE |
| P2-8 | Regime | `bear_protection_service.py:287-304` | Can't exit AGGRESSIVE quickly | Holds during reversal |
| P2-9 | MVP | `genesis.py:185` | Exit conditions not generated | Incomplete patterns |
| P2-10 | MVP | `decision.py:92-124` | Zone not persisted | No feedback loop |
| P2-11 | MVP | `crucible_test_service.py:33` | Test never called | Agents never graduate |
| P2-12 | Async | `collector_service.py:398-404` | Unbounded queue on DB failure | OOM crash |
| P2-13 | Async | `llm_service.py:46` | Ollama timeout blocks evolution | 30s stall |

**Estimated Fix Time**: 16-20 hours

### P3 - NICE TO HAVE (Improvements)

| ID | Category | Location | Issue | Impact |
|----|----------|----------|-------|--------|
| P3-1 | Security | `Main.py:314-315` | CORS misconfiguration | CSRF risk |
| P3-2 | Security | `Main.py:40` | Test router in prod | Info disclosure |
| P3-3 | Data | `backfill_service.py:370-390` | No timestamp validation | Timezone confusion |
| P3-4 | Data | `collector_service.py:56-64` | No gap detection | Stale baseline |
| P3-5 | ELO | Variable K-factor | Static K=32 | Suboptimal convergence |
| P3-6 | Pattern | Confidence bounds | Can exceed [0,1] | Invalid state |
| P3-7 | Crucible | No min fitness to pass | 0% fitness passes | Weak graduation |

**Estimated Fix Time**: 8-12 hours

---

## PART 2: VALIDATION AGENT ARCHITECTURE

### 2.1 Pre-Commit Agents (CI/CD Integration)

These agents run on every commit via GitHub Actions or pre-commit hooks.

#### AGENT: Division Safety Checker
```
Purpose: Scan all Python files for unguarded divisions
Trigger: Pre-commit hook, CI pipeline
Output: Pass/fail with line numbers
Technology: AST parsing + dataflow analysis
```

**Detection Rules:**
1. Find all `/` and `//` operators
2. Trace divisor to source (variable, function return, literal)
3. Check for guards: `if divisor > 0`, `if divisor != 0`, `or 0`
4. Flag unguarded divisions in financial/metric code
5. Whitelist: division by constants, test files

#### AGENT: Trait Bounds Validator
```
Purpose: Ensure all trait pathways include validation
Trigger: Pre-commit hook when touching Agents/ or Evolution/
Output: List of unvalidated pathways
Technology: Static analysis + grep patterns
```

**Detection Rules:**
1. Find all `AgentTraits` instantiations
2. Verify each has validation decorator or explicit check
3. Find all `agent.traits[key]` accesses
4. Verify `.get(key, default)` or try/except wrapper
5. Flag direct dictionary access without guards

#### AGENT: Async Pattern Detector
```
Purpose: Find async antipatterns that cause races/deadlocks
Trigger: Pre-commit hook when touching async code
Output: List of potential race conditions
Technology: AST analysis for async patterns
```

**Detection Rules:**
1. Global mutable state modified in async functions without locks
2. `await` inside loops without semaphore/throttle
3. Missing `asyncio.Lock` around shared data structures
4. Fire-and-forget tasks without supervision
5. Missing timeouts on await calls

### 2.2 Runtime Gatekeepers (Live Validation)

These run during system operation to catch bad data before it corrupts results.

#### GATEKEEPER: Data Integrity Validator
```
Purpose: Validate all candle data before processing
Location: collector_service.py flush path, backtest_service.py load path
Action: Reject invalid data, log anomaly, alert if > 1% rejection
```

**Validation Rules:**
```python
def validate_candle(candle: dict) -> tuple[bool, str]:
    # OHLC relationships
    if candle["high"] < candle["low"]:
        return False, "high < low"
    if candle["high"] < candle["open"]:
        return False, "high < open"
    if candle["high"] < candle["close"]:
        return False, "high < close"
    if candle["low"] > candle["open"]:
        return False, "low > open"
    if candle["low"] > candle["close"]:
        return False, "low > close"

    # Positive values
    if candle["close"] <= 0:
        return False, "close <= 0"
    if candle["volume"] < 0:
        return False, "volume < 0"

    # Timestamp sanity
    if candle["timestamp"] > datetime.utcnow():
        return False, "future timestamp"

    return True, "ok"
```

#### GATEKEEPER: Fitness Calculation Auditor
```
Purpose: Verify fitness calculations produce sane values
Location: After backtest_service.py fitness calculation
Action: Flag anomalies, prevent obviously wrong values from persisting
```

**Sanity Bounds:**
```python
def audit_fitness(metrics: dict) -> list[str]:
    warnings = []

    # Sortino realistic range
    if metrics["sortino"] > 5.0:
        warnings.append(f"Sortino {metrics['sortino']:.2f} > 5.0 (suspiciously high)")
    if metrics["sortino"] < -3.0:
        warnings.append(f"Sortino {metrics['sortino']:.2f} < -3.0 (check for errors)")

    # Sharpe realistic range
    if metrics["sharpe"] > 4.0:
        warnings.append(f"Sharpe {metrics['sharpe']:.2f} > 4.0 (world-class hedge fund level)")

    # Win rate bounds
    if not (0.0 <= metrics["win_rate"] <= 1.0):
        warnings.append(f"Win rate {metrics['win_rate']:.2f} outside [0,1]")

    # Drawdown sanity
    if metrics["max_drawdown"] > 100:
        warnings.append(f"Max drawdown {metrics['max_drawdown']:.2f}% > 100%")
    if metrics["max_drawdown"] < 0:
        warnings.append(f"Max drawdown {metrics['max_drawdown']:.2f}% negative")

    # ROI sanity (for backtests)
    if abs(metrics["roi"]) > 1000:
        warnings.append(f"ROI {metrics['roi']:.2f}% extreme (data issue?)")

    return warnings
```

#### GATEKEEPER: WebSocket Health Monitor
```
Purpose: Detect silent WebSocket failures
Location: Background task in Main.py
Action: Reconnect stale connections, alert on prolonged outage
```

**Health Checks:**
```python
async def websocket_health_loop():
    while True:
        await asyncio.sleep(30)  # Check every 30s

        for exchange, client in stream_manager.clients.items():
            last_message = client.last_message_time
            stale_seconds = (datetime.utcnow() - last_message).total_seconds()

            if stale_seconds > 60:
                logger.warning(f"{exchange} stale for {stale_seconds}s, reconnecting")
                await client.reconnect()

            if stale_seconds > 300:
                logger.error(f"{exchange} DEAD for {stale_seconds}s")
                # Alert via webhook/email
```

### 2.3 Evolution Cycle Gates (Process Validation)

These gates run at specific points in the evolution cycle to ensure integrity.

#### GATE: Pre-Backtest Data Validation
```
Location: backtest_service.py before running any backtest
Purpose: Ensure we have valid data to test against
```

**Checks:**
1. Candle count >= minimum threshold (e.g., 500 candles)
2. No gaps > 1 hour in candle sequence
3. All required indicators present and non-null
4. Data freshness within acceptable range

#### GATE: Post-Backtest Metric Sanity
```
Location: After backtest completion, before persisting results
Purpose: Catch obviously wrong results before they affect evolution
```

**Checks:**
1. All required metrics present (sortino, sharpe, win_rate, max_drawdown, roi)
2. No NaN/Inf values
3. Values within realistic bounds
4. Trade count > 0 (or explicitly marked as "no trades")

#### GATE: Pre-Cull Fitness Verification
```
Location: Before culling agents
Purpose: Ensure we're not culling based on corrupted fitness
```

**Checks:**
1. Population has been backtested in current cycle
2. Fitness scores are not all identical (would indicate error)
3. Fitness distribution is reasonable (not all 0 or all 100)
4. Elite agents have non-zero trade counts

---

## PART 3: PROMPT TEMPLATES

All prompts stored in `/swarm/prompts/validation/` for validation agents.

### 3.1 Division Safety Checker Prompt

**File**: `/swarm/prompts/validation/division_safety_checker.txt`

```
=== MISSION ===
You are an automated division safety checker running as part of CI/CD.
Your job is to scan Python files for unguarded division operations that could cause ZeroDivisionError.

=== GOAL ===
For each file scanned, produce a PASS/FAIL result with specific findings.
Success = Zero unguarded divisions in financial calculation paths.

=== MINDSET ===
Think defensively. Assume all data can be empty, zero, or null.
- Empty database results mean denominators could be 0
- Zero volatility (flat markets) means std dev = 0
- First-day bootstrapping means no historical data

=== OUTPUT REQUIREMENT ===
Output JSON format:
{
  "status": "PASS" | "FAIL",
  "file": "path/to/file.py",
  "findings": [
    {
      "line": 123,
      "code": "result = x / y",
      "severity": "CRITICAL" | "HIGH" | "MEDIUM",
      "reason": "y traces to sum() which can be 0 for empty input",
      "suggested_fix": "if y > 0 else 0"
    }
  ]
}

=== DETECTION RULES ===
1. CRITICAL: Division in fitness/metric calculation without guard
2. HIGH: Division in hot path (backtest loop) without guard
3. MEDIUM: Division in utility function without guard
4. IGNORE: Division by constants, already guarded, test files
```

### 3.2 Trait Validator Prompt

**File**: `/swarm/prompts/validation/trait_validator.txt`

```
=== MISSION ===
You are a trait integrity guardian. Your job is to ensure all agent traits are validated before use.

=== GOAL ===
Identify every pathway where traits enter or exit the system without validation.
Success = All 6 trait pathways have explicit validation.

=== MINDSET ===
Traits are the DNA of agents. Corrupted traits = corrupted evolution.
Every entry point is a potential corruption vector:
- Spawn (should be validated)
- Database load (often not validated)
- Mutation (partial validation)
- Crossover (often not validated)
- API updates (often not validated)
- Pattern matching access (often not validated)

=== OUTPUT REQUIREMENT ===
Output to: /swarm/botresearch/validation/trait_validation_report.md

For each pathway:
- VALIDATED: How it's validated
- UNVALIDATED: What checks are missing
- RECOMMENDED FIX: Specific code change

=== VALIDATION REQUIREMENTS ===
1. All traits in [0.0, 1.0] range (clamped, not silently)
2. Required traits present: risk_tolerance, momentum_vs_reversion, volatility_seeking, etc.
3. Derived traits consistent with source traits
4. No KeyError possible on trait access
```

### 3.3 Async Pattern Detector Prompt

**File**: `/swarm/prompts/validation/async_detector.txt`

```
=== MISSION ===
You are a concurrency bug hunter. Your job is to find race conditions, deadlocks, and async antipatterns.

=== GOAL ===
Identify code that will fail under concurrent load.
Success = All shared state protected, all awaits bounded, all tasks supervised.

=== MINDSET ===
Assume maximum chaos:
- 500 concurrent backtest requests
- WebSocket callbacks firing at 100/second
- Database queries taking 5 seconds
- Ollama unresponsive for 30 seconds

=== OUTPUT REQUIREMENT ===
Output to: /swarm/botresearch/validation/async_report.md

For each finding:
- Pattern type (race condition, deadlock, unbounded, fire-and-forget)
- Confidence level (50-100%)
- Scenario that triggers it
- Recommended fix

=== ANTIPATTERNS TO DETECT ===
1. Global mutable state without asyncio.Lock
2. await inside loop without semaphore (pool exhaustion)
3. Missing timeout on external calls (hang forever)
4. Tasks created but never awaited/supervised
5. Queue operations without locks (list.append in callback + list swap)
6. Boolean flags for concurrency control (should be Semaphore)
```

### 3.4 Data Integrity Validator Prompt

**File**: `/swarm/prompts/validation/data_integrity.txt`

```
=== MISSION ===
You are a data quality guardian. Your job is to ensure only valid market data flows through the system.

=== GOAL ===
Prevent garbage data from corrupting backtests and evolution.
Success = All candles validated, all anomalies logged, no silent corruption.

=== MINDSET ===
Bad data is worse than no data. Invalid OHLC relationships mean:
- ATR calculations produce garbage
- Indicators produce NaN
- Backtests show impossible results
- Evolution selects on noise

=== OUTPUT REQUIREMENT ===
Runtime validation returns tuple[bool, str] for each candle.
Batch validation returns summary report with:
- Total candles checked
- Rejection count by reason
- Anomaly trends (increasing rejections = upstream problem)

=== VALIDATION RULES ===
Required invariants:
1. high >= max(open, close, low)
2. low <= min(open, close, high)
3. close > 0, open > 0, high > 0, low > 0
4. volume >= 0
5. timestamp <= now (no future data)
6. timestamp in expected sequence (no large gaps)
```

### 3.5 Fitness Auditor Prompt

**File**: `/swarm/prompts/validation/fitness_auditor.txt`

```
=== MISSION ===
You are a metrics sanity checker. Your job is to catch obviously wrong fitness calculations.

=== GOAL ===
Flag results that are mathematically impossible or statistically implausible.
Success = No agent ranked on corrupt fitness.

=== MINDSET ===
Good traders exist in a known range:
- Sortino > 3.0 is hedge fund legend territory
- Sharpe > 2.5 is exceptional
- Win rate > 70% with positive ROI is rare
- Max drawdown < 5% with high returns is suspicious

=== OUTPUT REQUIREMENT ===
Return list of warnings for any anomaly.
Block persistence if CRITICAL anomaly detected.

=== SANITY BOUNDS ===
CRITICAL (block):
- NaN or Inf in any metric
- Win rate outside [0, 1]
- Negative max drawdown
- Sortino > 10 or < -10

HIGH (warn):
- Sortino > 5 (verify data quality)
- ROI > 500% in single window (verify no lookahead)
- Win rate > 80% with high trade count (verify slippage)

MEDIUM (log):
- Zero trades in regime window
- All identical fitness scores
```

### 3.6 WebSocket Health Monitor Prompt

**File**: `/swarm/prompts/validation/websocket_health.txt`

```
=== MISSION ===
You are a connection health monitor. Your job is to detect silent WebSocket failures.

=== GOAL ===
Ensure the system never trades on stale data without knowing it.
Success = All connections monitored, stale connections reconnected, outages alerted.

=== MINDSET ===
Silent failure is the worst failure:
- Connection dies but socket stays "open"
- Data stops flowing but no error raised
- System continues trading on 5-hour-old data

=== OUTPUT REQUIREMENT ===
Continuous monitoring with:
- Heartbeat every 30 seconds
- Staleness threshold: 60 seconds
- Reconnect attempt on stale
- Alert on > 5 minute outage

=== HEALTH METRICS ===
Track per exchange:
- last_message_time
- messages_per_minute (should be > 0)
- reconnect_count_24h
- current_state (CONNECTED, RECONNECTING, DEAD)
```

---

## PART 4: IMPLEMENTATION SEQUENCE

### Phase 1: Foundation Fixes (Week 1)

**Goal**: Make the system safe to test. Fix all crash bugs and data corruption issues.

#### Day 1-2: Division Safety (P0-1 through P0-4)

1. **Add guards to backtest_service.py**

```python
# Line 509-510: Guard total_w
if total_w > 0:
    avg_fitness = sum(w["fitness"] * w["trades"] for w in valid_windows) / total_w
    avg_win_rate = sum((w["win_rate"] or 0) * w["trades"] for w in valid_windows) / total_w
else:
    avg_fitness = 0.0
    avg_win_rate = 0.0

# Line 545-549: Guard regime_total
if regime_total > 0:
    regime_metrics = {
        "fitness": sum(w["fitness"] * w["trades"] for w in regime_windows) / regime_total,
        "win_rate": sum((w["win_rate"] or 0) * w["trades"] for w in regime_windows) / regime_total,
        "roi": sum(w["roi"] * w["trades"] for w in regime_windows) / regime_total,
    }
else:
    regime_metrics = {"fitness": 0.0, "win_rate": 0.0, "roi": 0.0}

# Line 583: Guard tf_total
tf_fitness = sum(w["fitness"] * w["trades"] for w in tf_windows) / tf_total if tf_total > 0 else 0.0

# Line 684: Guard peak
if peak > 0:
    dd = ((peak - equity) / peak) * 100
else:
    dd = 0.0
```

2. **Add test contracts**

File: `Tests/Soundness/Foundations/test_div_safety.py`

```python
def test_backtest_empty_candles_no_crash():
    """Backtest with 0 candles should return safe defaults, not crash."""
    result = run_backtest(agent_id=1, candles=[])
    assert result["fitness"] == 0.0
    assert result["win_rate"] == 0.0

def test_backtest_single_regime_zero_trades():
    """Regime with no trades should not cause division error."""
    result = run_backtest_regime(regime="crash", candles=flat_market_candles)
    assert isinstance(result["fitness"], float)
    assert not math.isnan(result["fitness"])

def test_drawdown_zero_equity_start():
    """Starting from zero equity should not crash drawdown calc."""
    result = calculate_drawdown(equity_curve=[0, 100, 90])
    assert isinstance(result, float)
```

#### Day 2-3: Data Integrity (P0-5, P0-6)

1. **Add OHLC validation to collector_service.py**

```python
def validate_candle(candle: dict) -> tuple[bool, str]:
    """Validate OHLC relationships and value sanity."""
    o, h, l, c = candle["open"], candle["high"], candle["low"], candle["close"]

    # OHLC relationships
    if h < l:
        return False, f"high ({h}) < low ({l})"
    if h < o or h < c:
        return False, f"high ({h}) < open ({o}) or close ({c})"
    if l > o or l > c:
        return False, f"low ({l}) > open ({o}) or close ({c})"

    # Positive values
    if c <= 0 or o <= 0 or h <= 0 or l <= 0:
        return False, "non-positive price"
    if candle.get("volume", 0) < 0:
        return False, "negative volume"

    return True, "ok"

# In flush path (line ~164):
for candle in candles_to_write:
    valid, reason = validate_candle(candle)
    if not valid:
        logger.warning(f"Rejecting invalid candle: {reason}")
        continue
    valid_candles.append(candle)
```

2. **Fix default value trap in backtest_service.py**

```python
# Line 437: Don't default to 0
close_price = candle.get("close")
if close_price is None or close_price <= 0:
    logger.warning(f"Invalid close price at {candle.get('timestamp')}, skipping candle")
    continue
```

#### Day 3-4: Trait Safety (P0-7, P1-8 through P1-10)

1. **Add trait validation decorator to Agent model**

```python
# In Agent model (SQLModel):
from pydantic import validator

class Agent(SQLModel, table=True):
    traits: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB))

    @validator("traits", pre=True, always=True)
    def validate_traits(cls, v):
        if not isinstance(v, dict):
            raise ValueError("traits must be a dict")

        required = ["risk_tolerance", "momentum_vs_reversion", "volatility_seeking"]
        for key in required:
            if key not in v:
                raise ValueError(f"Missing required trait: {key}")
            if not (0.0 <= v[key] <= 1.0):
                raise ValueError(f"Trait {key}={v[key]} outside [0,1]")

        return v
```

2. **Fix trio_engine.py KeyError**

```python
# Line 265: Safe trait access
exit_threshold = agent.traits.get("exit_threshold", 0.5)  # Default if missing
```

3. **Fix mutation preserving derived traits**

```python
# In evolution_service.py after mutation:
mutated_traits = recalculate_derived_traits(mutated_traits)
```

4. **Fix crossover defaults**

```python
# Line 420-428: Don't default to 0
val_b = traits_b.get(key, traits_a.get(key, 0.5))  # Use parent A's value, then 0.5
```

### Phase 2: Async & Concurrency (Week 1-2)

#### Day 4-5: Evolution Race Conditions (P1-1, P1-4)

1. **Replace boolean flag with semaphore**

```python
# In evolution_service.py:
_evolution_semaphore = asyncio.Semaphore(1)

async def start_evolution_cycle():
    acquired = _evolution_semaphore.acquire_nowait()
    if not acquired:
        raise HTTPException(409, "Evolution already running")

    try:
        asyncio.create_task(_run_evolution_with_cleanup())
    except Exception:
        _evolution_semaphore.release()
        raise

async def _run_evolution_with_cleanup():
    try:
        await _run_evolution_cycle()
    finally:
        _evolution_semaphore.release()  # Always releases, even on exception
```

#### Day 5-6: Queue Race Conditions (P1-2)

1. **Add locks to collector queues**

```python
# In collector_service.py:
_write_lock = asyncio.Lock()

async def add_to_queue(item):
    async with _write_lock:
        _write_queue.append(item)

async def flush_queue():
    async with _write_lock:
        items = _write_queue[:]
        _write_queue.clear()
    # Process items outside lock
```

#### Day 6: Connection Pool (P1-3)

```python
# In Database.py:
engine = create_async_engine(
    DATABASE_URL,
    pool_size=100,      # Was 20
    max_overflow=150,   # Was 30
    pool_timeout=60,    # Add timeout
    pool_recycle=3600,  # Recycle connections hourly
)
```

### Phase 3: Backtest Realism (Week 2)

#### Day 7-8: Fix Backtest Optimism (P1-6, P1-7)

1. **Deduct spread from PnL**

```python
# Line 644:
net_pnl = gross_pnl - fees_pct - slippage_pct - spread_pct
```

2. **Entry at next candle open**

```python
# Line 478: Change entry price logic
# Instead of: entry_price = close_price
# Use: Store signal, execute on next candle
pending_signal = {"direction": signal, "signal_price": close_price}

# On next candle:
if pending_signal:
    entry_price = candle["open"]  # Execute at next open
    # Add slippage
    entry_price *= (1 + random.uniform(0.001, 0.003))  # 0.1-0.3% slippage
```

#### Day 8: Fix Sortino Formula (P1-5)

```python
# Line 668-672: Correct Sortino formula
target_return = 0  # Usually 0 or risk-free rate

# Downside deviation (not standard deviation of negatives)
squared_downside = [min(0, r - target_return)**2 for r in returns]
downside_deviation = math.sqrt(sum(squared_downside) / len(returns)) if returns else 0

sortino = (avg_return - target_return) / downside_deviation if downside_deviation > 0 else 0
```

### Phase 4: Validation Gates (Week 2-3)

#### Day 9-10: Implement Gatekeepers

1. **Create validation module**

```
Fast_Swarm/
  Validation/
    __init__.py
    candle_validator.py      # OHLC checks
    fitness_auditor.py       # Metric sanity
    trait_validator.py       # Trait bounds
    websocket_monitor.py     # Connection health
```

2. **Integrate into pipelines**

```python
# In backtest_service.py
from Fast_Swarm.Validation.candle_validator import validate_candle
from Fast_Swarm.Validation.fitness_auditor import audit_fitness

# Before backtest:
for candle in candles:
    if not validate_candle(candle)[0]:
        raise ValueError("Invalid candle data")

# After backtest:
warnings = audit_fitness(metrics)
if warnings:
    logger.warning(f"Fitness anomalies: {warnings}")
```

### Phase 5: Security Hardening (Week 3)

#### Day 11-12: Fix Critical Security (P1-11, P1-12)

1. **Remove hardcoded password**

```python
# Database.py line 24:
POSTGRES_PASSWORD = os.environ["POSTGRES_PASSWORD"]  # Fail if not set
```

2. **Add authentication middleware**

```python
# In Main.py:
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key != os.environ["FAST_SWARM_API_KEY"]:
        raise HTTPException(401, "Invalid API key")

# Apply to routers
app.include_router(actions_router, dependencies=[Depends(verify_api_key)])
```

### Phase 6: WebSocket & Regime Fixes (Week 3-4)

#### Day 13-14: WebSocket Health (P2-1 through P2-3)

1. **Add heartbeat monitoring**
2. **Add message queueing**
3. **Add reconnect with gap handling**

#### Day 15-16: Regime Detection (P2-6 through P2-8)

1. **Default missing data to CONSERVATIVE**
2. **Fix safe-to-exit None handling**
3. **Decouple AGGRESSIVE exit from entry timing**

### Phase 7: MVP Flow Completion (Week 4)

#### Day 17-18: Complete MVP Pipeline (P2-9 through P2-11)

1. **Call generate_exit_conditions() in pattern discovery**
2. **Persist DecisionZone to database**
3. **Call run_crucible_test() after crucible entry**

### Phase 8: ELO Redesign (Week 4-5)

#### Day 19-20: Fix ELO System (P2-4, P2-5)

1. **Implement pairwise zero-sum ELO**
2. **Remove fixed benchmark**
3. **Standardize floor/ceiling**

---

## PART 5: TEST CONTRACTS

### 5.1 Division Safety Contracts

File: `Tests/Soundness/Foundations/test_div_safety.py`

```python
"""Division safety test contracts - MUST PASS before any release."""

import pytest
import math

class TestDivisionSafety:
    """All division operations must be guarded."""

    def test_backtest_empty_candles_returns_safe_defaults(self):
        """Empty candle list should return 0 fitness, not crash."""
        result = run_backtest(agent_id=1, candles=[])
        assert result["fitness"] == 0.0
        assert result["win_rate"] == 0.0
        assert not math.isnan(result["fitness"])

    def test_backtest_single_regime_zero_trades(self):
        """Regime with 0 trades should not ZeroDivisionError."""
        result = run_backtest_by_regime(regime="crash", candles=sideways_candles)
        assert isinstance(result["fitness"], float)

    def test_drawdown_zero_peak_handled(self):
        """Zero peak equity should not ZeroDivisionError."""
        result = calculate_drawdown([0, 100, 90, 110])
        assert isinstance(result, float)
        assert result >= 0

    def test_sortino_zero_downside_handled(self):
        """All positive returns (0 downside) should not crash."""
        returns = [0.01, 0.02, 0.015, 0.03]
        sortino = calculate_sortino(returns)
        assert isinstance(sortino, float)
        assert not math.isnan(sortino)

    def test_sharpe_zero_volatility_handled(self):
        """Flat returns (0 std) should not crash."""
        returns = [0.01, 0.01, 0.01, 0.01]
        sharpe = calculate_sharpe(returns)
        assert isinstance(sharpe, float)
```

### 5.2 Data Integrity Contracts

File: `Tests/Soundness/Backtest/test_data_integrity.py`

```python
"""Data integrity test contracts."""

class TestOHLCValidation:
    """OHLC relationships must be enforced."""

    def test_high_less_than_low_rejected(self):
        """Candle with high < low should be rejected."""
        candle = {"open": 100, "high": 95, "low": 105, "close": 100, "volume": 1000}
        valid, reason = validate_candle(candle)
        assert not valid
        assert "high" in reason.lower() and "low" in reason.lower()

    def test_zero_close_rejected(self):
        """Candle with close=0 should be rejected."""
        candle = {"open": 100, "high": 105, "low": 95, "close": 0, "volume": 1000}
        valid, reason = validate_candle(candle)
        assert not valid

    def test_negative_volume_rejected(self):
        """Candle with negative volume should be rejected."""
        candle = {"open": 100, "high": 105, "low": 95, "close": 102, "volume": -100}
        valid, reason = validate_candle(candle)
        assert not valid

    def test_valid_candle_accepted(self):
        """Normal candle should pass validation."""
        candle = {"open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000}
        valid, reason = validate_candle(candle)
        assert valid
```

### 5.3 Trait Validation Contracts

File: `Tests/Soundness/Traits/test_trait_validation.py`

```python
"""Trait validation test contracts."""

class TestTraitBounds:
    """All traits must be in valid ranges."""

    def test_trait_above_one_rejected(self):
        """Trait > 1.0 should be rejected."""
        with pytest.raises(ValueError):
            Agent(traits={"risk_tolerance": 1.5, "momentum_vs_reversion": 0.5})

    def test_trait_below_zero_rejected(self):
        """Trait < 0.0 should be rejected."""
        with pytest.raises(ValueError):
            Agent(traits={"risk_tolerance": -0.1, "momentum_vs_reversion": 0.5})

    def test_missing_required_trait_rejected(self):
        """Missing required trait should be rejected."""
        with pytest.raises(ValueError):
            Agent(traits={"momentum_vs_reversion": 0.5})  # Missing risk_tolerance

    def test_mutation_preserves_bounds(self):
        """Mutated traits must stay in [0, 1]."""
        original = {"risk_tolerance": 0.95}  # Near boundary
        mutated = mutate_traits(original, mutation_rate=0.2)
        assert 0.0 <= mutated["risk_tolerance"] <= 1.0

    def test_crossover_preserves_bounds(self):
        """Crossover output must be in [0, 1]."""
        parent_a = {"risk_tolerance": 0.1}
        parent_b = {"risk_tolerance": 0.9}
        child = crossover_traits(parent_a, parent_b)
        assert 0.0 <= child["risk_tolerance"] <= 1.0
```

### 5.4 Async Safety Contracts

File: `Tests/Soundness/Async/test_async_safety.py`

```python
"""Async safety test contracts."""

class TestEvolutionConcurrency:
    """Evolution must handle concurrent requests safely."""

    @pytest.mark.asyncio
    async def test_concurrent_evolution_blocked(self):
        """Second evolution request should be rejected."""
        # Start first evolution
        task1 = asyncio.create_task(start_evolution_cycle())
        await asyncio.sleep(0.1)  # Let it start

        # Second should fail
        with pytest.raises(HTTPException) as exc:
            await start_evolution_cycle()
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_evolution_flag_releases_on_error(self):
        """Evolution flag must release even on exception."""
        # Force an error during evolution
        with patch("evolution_service._run_evolution_cycle", side_effect=Exception("test")):
            with pytest.raises(Exception):
                await start_evolution_cycle()

        # Should be able to start again
        # (This would hang forever if flag didn't release)
        await asyncio.wait_for(start_evolution_cycle(), timeout=5.0)
```

### 5.5 Backtest Realism Contracts

File: `Tests/Soundness/Backtest/test_economic_validity.py`

```python
"""Economic validity test contracts."""

class TestBacktestRealism:
    """Backtest must include realistic costs."""

    def test_spread_deducted_from_pnl(self):
        """Spread cost must be deducted."""
        result = run_single_trade_backtest(spread_pct=0.1)
        # Gross PnL 1% - spread 0.1% = net 0.9%
        assert result["net_pnl"] < result["gross_pnl"]

    def test_entry_at_next_open(self):
        """Entry should be at next candle open, not signal close."""
        signal_candle = {"close": 100}
        next_candle = {"open": 101}
        entry_price = get_entry_price(signal_candle, next_candle)
        assert entry_price >= 101  # At or above next open (with slippage)

    def test_slippage_applied(self):
        """Slippage must be added to entry/exit prices."""
        entries = [get_entry_price_with_slippage(100) for _ in range(100)]
        # Should have variance from slippage
        assert max(entries) > min(entries)
        # All should be >= base price (for longs)
        assert all(e >= 100 for e in entries)
```

### 5.6 Fitness Calculation Contracts

File: `Tests/Soundness/Metrics/test_fitness_formulas.py`

```python
"""Fitness formula test contracts."""

class TestSortinoFormula:
    """Sortino must use correct downside deviation."""

    def test_sortino_uses_downside_deviation(self):
        """Sortino denominator should be downside deviation, not stdev of negatives."""
        returns = [0.05, -0.02, 0.03, -0.01, 0.04]

        # Calculate expected downside deviation (target = 0)
        squared_downside = [min(0, r)**2 for r in returns]
        expected_dd = math.sqrt(sum(squared_downside) / len(returns))

        sortino = calculate_sortino(returns)
        expected_sortino = sum(returns) / len(returns) / expected_dd

        assert abs(sortino - expected_sortino) < 0.001

    def test_sortino_all_positive_returns(self):
        """All positive returns should give high Sortino (0 downside)."""
        returns = [0.01, 0.02, 0.015]
        sortino = calculate_sortino(returns)
        # With 0 downside deviation, should return 0 or capped value
        assert sortino == 0 or sortino > 100  # Implementation choice
```

---

## PART 6: SUCCESS CRITERIA

### Phase 1 Complete When:
- [ ] All division safety tests pass
- [ ] OHLC validation active in collector
- [ ] Trait validation decorator on Agent model
- [ ] No KeyError possible from trait access

### Phase 2 Complete When:
- [ ] Evolution uses semaphore (not boolean flag)
- [ ] Queue operations protected by locks
- [ ] Connection pool sized for load
- [ ] Concurrent evolution tests pass

### Phase 3 Complete When:
- [ ] Spread deducted from PnL
- [ ] Entry at next candle open
- [ ] Sortino uses correct formula
- [ ] Economic validity tests pass

### Phase 4 Complete When:
- [ ] Validation module exists
- [ ] Gatekeepers integrated in pipelines
- [ ] Health monitoring active
- [ ] All sanity bounds enforced

### Phase 5 Complete When:
- [ ] No hardcoded credentials
- [ ] API key auth on all endpoints
- [ ] Test router disabled in production

### Full MVP Complete When:
- [ ] All P0 bugs fixed
- [ ] All P1 bugs fixed
- [ ] All validation agents active
- [ ] All test contracts passing
- [ ] Paper trading implemented

---

## APPENDIX: FILE LOCATIONS

| Bug Category | Primary Files |
|--------------|---------------|
| Division Safety | `backtest_service.py` |
| Data Integrity | `collector_service.py`, `backfill_service.py` |
| Async Issues | `evolution_service.py`, `collector_service.py`, `Database.py` |
| Trait Validation | `agent_models.py`, `evolution_service.py`, `trio_engine.py` |
| Backtest Realism | `backtest_service.py` |
| Fitness Formulas | `backtest_service.py` |
| Security | `Database.py`, `Main.py` |
| WebSocket | `base_ws.py`, `stream_manager_service.py` |
| Regime Detection | `bear_protection_service.py`, `executor.py` |
| ELO System | `elo_transfer_service.py`, `governance_service.py` |

---

*Plan Created: 2026-01-21*
*Target Completion: 4-5 weeks*
*Total Estimated Hours: 60-80*
