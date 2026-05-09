# WEBSOCKET STATE AUDIT
**Date**: 2026-01-21
**Status**: 4 CRITICAL, 6 HIGH FAILURE MODES

## EXECUTIVE SUMMARY

Multiple failure modes where connections fail silently, causing trading on stale data.

## CRITICAL FINDINGS

### [CRITICAL] No Heartbeat Timeout - Infinite Hang (92% confidence)
**File**: base_ws.py:292-296
```python
async for message in self.ws:  # INFINITE WAIT, NO TIMEOUT
```
**FAILURE**: If connection dies, loop hangs forever. No error, no alert.
**CONSEQUENCE**: Trading on 5-hour-old candle without knowing.

### [CRITICAL] Message Processing Blocks Event Loop (88% confidence)
**File**: base_ws.py:303-355
Callbacks execute synchronously. At 100 trades/sec with 10ms callback, buffer overflows silently.
**CONSEQUENCE**: Missing trades during flash crashes.

### [CRITICAL] Reconnect Window = Data Gap (90% confidence)
**File**: base_ws.py:375-391
```python
await asyncio.sleep(delay)  # MESSAGES LOST DURING THIS SLEEP
```
5-second reconnect = 50+ order book updates lost, 500+ trades gone.

### [CRITICAL] No Timeout on WebSocket Send (87% confidence)
**File**: base_ws.py:399-402
If disconnect during send, subscription silently fails. Reports CONNECTED with zero data.

## HIGH FINDINGS

### [HIGH] Unbounded Callback Registration (85% confidence)
```python
def on_trade(self, callback):
    self._trade_callbacks.append(callback)  # NO DEDUP
```
Service restart = duplicate callbacks = duplicate database inserts = data loss.

### [HIGH] Race Condition in State Check (84% confidence)
```python
if self.ws and self.state == ConnectionState.CONNECTED:
    await self.ws.send(...)  # TOCTOU bug
```

### [HIGH] Polling Tasks Not Supervised (82% confidence)
dYdX/Hyperliquid polling tasks created but never monitored. Silent death = stale funding.

### [HIGH] Order Book Flush Race Condition (86% confidence)
```python
snapshots_to_write = self._write_queue_orderbooks[:]  # Non-atomic copy
self._write_queue_orderbooks = []  # Separate clear
```

### [HIGH] No Connection Monitoring (80% confidence)
Tasks fire-and-forget. If Binance dies, no alert. Trading continues on 1 of 4 exchanges.

### [MEDIUM] Max Reconnect Causes Permanent Closure
After 7.5 minutes of failures, connection gives up forever. Needs manual restart.

## IMPACT TABLE

| Failure Mode | Detection | Trading Impact |
|--------------|-----------|----------------|
| No heartbeat | NONE | Days of stale data |
| Message blocking | NONE | Corrupted backtests |
| Reconnect gap | NONE | Slippage surprises |
| Failed send | NONE | Zero data for symbol |

## IMMEDIATE FIXES

1. Add heartbeat detector loop (check every 30s, reconnect if 60s stale)
2. Queue messages before callbacks (decouple receive from process)
3. Use asyncio.Lock for all state changes
4. Add connection health monitoring with alerts
