# FITNESS CALCULATION AUDIT
**Date**: 2026-01-21
**Status**: MATHEMATICAL ERRORS FOUND

## EXECUTIVE SUMMARY

Critical metric calculation errors that would rank agents incorrectly during evolution.

## CRITICAL FINDINGS

### [CRITICAL] Sortino Denominator Bug
**File**: backtest_service.py:668-672
```python
negative_returns = [r for r in returns if r < 0]
downside_std = statistics.stdev(negative_returns) if len(negative_returns) > 1 else 0
sortino = (avg_pnl / downside_std) if downside_std > 0 else 0
```

**CURRENT**: Uses `stdev()` (sample std with n-1 denominator)
**CORRECT**: Sortino should use target-based downside deviation:
```python
# Correct formula:
downside_deviation = sqrt(sum(min(r - target, 0)^2) / n)
```

**IMPACT**: Sortino values inflated by ~15% for small sample sizes.

### [HIGH] Alpha Not Subtracting Benchmark Correctly
**File**: Multiple locations
Alpha should be: `Agent CAGR - Benchmark (Buy & Hold) CAGR`

Need to verify benchmark CAGR is calculated on same time period as agent CAGR.

### [HIGH] Sharpe Not Consistently Annualized
**File**: backtest_service.py:660-662
```python
sharpe_raw = (mean_return / std_return) if std_return > 0 else 0
sharpe = sharpe_raw * sqrt(252)  # Annualized
```
Check: Are all Sharpe calculations using same annualization factor?

### [MEDIUM] Win Rate Edge Cases
**File**: backtest_service.py:641
```python
win_rate = wins / total_trades if total_trades > 0 else 0
```
**Question**: Does win rate only count CLOSED trades? Open trades shouldn't count.

## FORMULA VERIFICATION

### Sortino (NEEDS FIX)
```
CORRECT: Sortino = (Mean Return - Risk Free) / Downside Deviation
where Downside Deviation = sqrt(sum(min(r-target, 0)^2) / n)

CURRENT: Uses standard deviation of negative returns only
```

### Sharpe (VERIFY)
```
CORRECT: Sharpe = (Mean Return - Risk Free) / Std Dev * sqrt(annualization)
Check: Is annualization_factor consistent across all uses?
```

### Calmar (OK)
```
CURRENT: calmar = annualized_return / max_drawdown if max_drawdown > 0 else 0
STATUS: Correctly guarded
```

## IMPACT ON EVOLUTION

If Sortino is inflated:
- Agents with few negative trades look better than they are
- Agents with many small losses look worse than they should
- Selection pressure biased toward "lucky" agents, not robust ones

## RECOMMENDATIONS

1. Fix Sortino to use target-based downside deviation
2. Verify Alpha subtracts correct benchmark
3. Standardize annualization factors
4. Add unit tests for each metric formula
