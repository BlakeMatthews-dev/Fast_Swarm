# ASYNC ISSUES AUDIT
**Date**: 2026-01-21
**Status**: 8 CRITICAL/HIGH BUGS FOUND

## EXECUTIVE SUMMARY

Multiple async bugs that would cause hangs, deadlocks, and data corruption under concurrent load.

## CRITICAL FINDINGS

### [CRITICAL] Evolution Flag Race Condition - DATA CORRUPTION (95% confidence)
**File**: evolution_service.py:28-76
**SCENARIO**: Multiple concurrent evolution requests bypass lock and run simultaneously
**CONSEQUENCE**: Duplicate agents created, corrupted fitness metrics
**ROOT CAUSE**: `_active_evolution_run` flag set inside lock then released before background task starts

### [CRITICAL] Collector Batch Queue Race Condition - LOST DATA (92% confidence)
**File**: collector_service.py:34-38
**SCENARIO**: WebSocket callbacks append to queue without synchronization while flush swaps list
**CONSEQUENCE**: Lost or duplicated trade ticks, corrupted candles
**ROOT CAUSE**: No asyncio.Lock protecting `_write_queue_*` and `_pending_candles` dicts

### [CRITICAL] Session Pool Exhaustion - COMPLETE HANG (98% confidence)
**File**: Database.py:57-66
**SCENARIO**: 500 concurrent backtests need 100+ connections but pool only has 50
**CONSEQUENCE**: Event loop deadlock, all operations blocked
**ROOT CAUSE**: `pool_size=20, max_overflow=30` insufficient for concurrent backtests

### [CRITICAL] WebSocket Callback Thread Safety - CORRUPTED CANDLES (88% confidence)
**File**: stream_manager_service.py:41-51
**SCENARIO**: Callbacks modify shared `_minute_candles` during reconnection without locks
**CONSEQUENCE**: Mixed old/new candle data persisted, incorrect backtests
**ROOT CAUSE**: Callbacks run in WebSocket thread, not asyncio-controlled

### [CRITICAL] Evolution Flag Permanent Lock - SYSTEM OUTAGE (90% confidence)
**File**: evolution_service.py:104-217
**SCENARIO**: Unhandled exception in evolution cycle re-raised, bypasses finally block
**CONSEQUENCE**: `_active_evolution_run` stays True forever, evolution disabled until restart

### [HIGH] Unbounded Queue Growth on DB Failure - OOM CRASH (87% confidence)
**File**: collector_service.py:398-404
**SCENARIO**: Failed flush re-queues all data indefinitely during database outage
**CONSEQUENCE**: Memory exhaustion, process crash

### [HIGH] Ollama Timeout Blocks Evolution - 30 SECOND STALL (82% confidence)
**File**: llm_service.py:46
**SCENARIO**: TCP connection to unresponsive Ollama hangs, blocks all evolution
**CONSEQUENCE**: 30-second freeze in trading system

### [HIGH] Missing Query Timeout - INDEFINITE WAIT (88% confidence)
**File**: Main.py:160-165
**SCENARIO**: Slow database query without index blocks entire backtest pipeline
**CONSEQUENCE**: System appears frozen

## IMMEDIATE FIXES

1. Replace global flag with semaphore: `_evolution_semaphore = asyncio.Semaphore(1)`
2. Protect all shared queues with asyncio.Lock
3. Increase connection pool: `pool_size=50, max_overflow=100`
4. Add query timeouts: `asyncio.wait_for(..., timeout=30)`
5. Queue WebSocket callbacks via asyncio.Queue
