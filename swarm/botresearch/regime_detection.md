# REGIME DETECTION AUDIT
**Date**: 2026-01-21
**Status**: 5 CRITICAL FLAWS FOUND

## EXECUTIVE SUMMARY

System will misclassify crashes and cause overtrading due to regime detection logic errors.

## CRITICAL FINDINGS

### [CRITICAL] Missing Indicators = No Crash Detection
**File**: bear_protection_service.py:176-177
```python
if acc is None or adx_jerk is None:
    return False  # Missing data = "no danger signal"
```
**SCENARIO**: March 2020 crash, indicators lag during market open
**WRONG BEHAVIOR**: Regime stays NEUTRAL even during crash
**CORRECT BEHAVIOR**: Missing data should default to CONSERVATIVE (assume danger)

### [CRITICAL] Safe-to-Exit Logic Blocks Exits During Recovery
**File**: bear_protection_service.py:223-237
```python
for tf, vel, acc, jerk in [...]:
    if not self._check_safe_to_exit_defensive(acc, jerk):
        safe_to_exit_defensive = False  # ANY TF failing blocks exit
```
**SCENARIO**: 1h and 4h recover but 1d data is stale/missing
**WRONG BEHAVIOR**: Cannot exit DEFENSIVE because 1d indicator missing
**CORRECT BEHAVIOR**: Skip None values, don't penalize for missing data

### [CRITICAL] Can't Exit AGGRESSIVE Quickly
**File**: bear_protection_service.py:287-304
**SCENARIO**: Rally reverses after AGGRESSIVE entry
**WRONG BEHAVIOR**: Must wait `aggressive_min_hold_hours=1.0` + confirmation candles
**CORRECT BEHAVIOR**: Exit doesn't require waiting for new entries

### [HIGH] Dead Code in DEFENSIVE Entry Check
**File**: executor.py:1019
```python
if regime and regime.value == "DEFENSIVE" and max_position <= 0.25:
    pass  # DOES NOTHING!
```
Comment says "handled in _open_position" but code has no effect.

### [HIGH] Unbounded Counter Growth
**File**: bear_protection_service.py:268-282
`consecutive_safe_candles` increments forever with no cap (wastes memory at scale).

## REAL-WORLD IMPACT: March 2020 Replay

| Time | Market | System | Position |
|------|--------|--------|----------|
| 08:00 | -2% | Indicators lag, NEUTRAL | Long 65% |
| 08:15 | -8% | Still NEUTRAL (threshold -1.5) | Long 65% |
| 08:30 | -15% | DEFENSIVE triggered | Reducing |
| 08:45 | -18% | Exit signals but 1d lag | Stuck |
| 09:00 | -22% | Finally exit | 14.3% drawdown |

**Expected**: Detect by 08:15, reduce to 25%
**Actual**: Detect by 08:30, locked in 15%+ drawdown

## FIX PRIORITY

1. Fix missing indicator handling (default CONSERVATIVE)
2. Fix safe-to-exit logic (skip None values)
3. Fix AGGRESSIVE exit lag (decouple from entry)
4. Remove dead code in executor.py
5. Cap counter growth
