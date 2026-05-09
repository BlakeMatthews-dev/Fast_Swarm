# DIVISION SAFETY AUDIT
**Date**: 2026-01-21
**Status**: CRITICAL BUGS FOUND

## EXECUTIVE SUMMARY

**CODEBASE IS NOT SAFE FROM DIVISION ERRORS** - 4 CRITICAL unguarded divisions found in hot paths.

## CRITICAL FINDINGS

### [CRITICAL] backtest_service.py:509-510 - Division by total_w
```python
avg_fitness = sum(w["fitness"] * w["trades"] for w in valid_windows) / total_w
avg_win_rate = sum((w["win_rate"] or 0) * w["trades"] for w in valid_windows) / total_w
```
**WHY DANGEROUS**: `total_w` calculated from `valid_windows`. If NO windows have trades > 0, then `total_w = 0`.
**PROOF**: Agent tested on empty candle data -> all windows get 0 trades -> `valid_windows = []` -> `total_w = 0` -> **ZeroDivisionError**

### [CRITICAL] backtest_service.py:545, 547, 549 - Division by regime_total
```python
"fitness": sum(w["fitness"] * w["trades"] for w in regime_windows) / regime_total,
"win_rate": sum((w["win_rate"] or 0) * w["trades"] for w in regime_windows) / regime_total,
"roi": sum(w["roi"] * w["trades"] for w in regime_windows) / regime_total,
```
**WHY DANGEROUS**: If a regime has NO windows with trades, `regime_total = 0`.
**PROOF**: Agent tested on sideways regime with 0 trades -> **ZeroDivisionError**

### [CRITICAL] backtest_service.py:583 - Division by tf_total
```python
sum(w["fitness"] * w["trades"] for w in tf_windows) / tf_total
```
**WHY DANGEROUS**: Same pattern - timeframe with 0 trades in a regime = division by 0.

### [CRITICAL] backtest_service.py:684 - Division by peak
```python
dd = ((peak - equity) / peak) * 100
```
**WHY DANGEROUS**: If `peak = 0` (starting from zero equity), divides by 0.

## CLEAN AREAS (Properly Guarded)

| Location | Guard | Status |
|----------|-------|--------|
| fitness.py:471 | `if abs_drawdown != 0` | OK |
| backtest_service.py:641 | `if total_trades > 0 else 0` | OK |
| backtest_service.py:662 | `if std_return > 0 else 0` | OK |
| backtest_service.py:672 | `if downside_std > 0 else 0` | OK |
| backtest_service.py:690 | `if max_dd > 0 else 0` | OK |

## HOW TO TRIGGER THE CRASHES

1. **Empty Dataset**: Agent spawned -> backtest with 0 candles -> all windows 0 trades -> CRASH
2. **Single Regime Zero Trades**: Regime "crash" has no data -> CRASH
3. **Timeframe Grid Zero Data**: Some timeframes empty for a regime -> CRASH

## RECOMMENDATIONS

Add guards before all divisions:
```python
if total_w > 0:
    avg_fitness = sum(...) / total_w
else:
    avg_fitness = 0
```

**Production risk: HIGH** - These will crash on first backtest with empty candles.
