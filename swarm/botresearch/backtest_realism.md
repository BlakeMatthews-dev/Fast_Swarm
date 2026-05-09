# BACKTEST REALISM AUDIT
**Date**: 2026-01-21
**Status**: 5 CRITICAL OPTIMISMS FOUND

## EXECUTIVE SUMMARY

Backtest is 0.5-1.5% OPTIMISTIC due to unrealistic assumptions. Live trading will underperform.

## CRITICAL FINDINGS

### [CRITICAL] Entry Price Uses Signal Candle Close (Should be Next Open)
**File**: backtest_service.py:478
```python
open_trade = {
    "entry_price": close_price,  # Uses signal candle close!
}
```
**REALITY**: You can't execute at the close that generated the signal. Entry should be next candle open + slippage.
**MAGNITUDE**: -0.3% to -0.5% per trade. 52% win rate in backtest becomes 48% in reality.

### [CRITICAL] Spread Cost Calculated But NOT Deducted
**File**: backtest_service.py:59-62 (calculated) and 644 (NOT used)
```python
# Line 59-62: spread_pct calculated
# Line 644: NOT DEDUCTED!
net_pnl = gross_pnl - fees_pct - slippage_pct  # spread_pct MISSING!
```
**REALITY**: Every trade must cross bid-ask spread.
**MAGNITUDE**: BTC 0.04%, small caps 0.40% per trade.

### [CRITICAL] Exit Price Uses Current Candle Close (Lookahead)
**File**: backtest_service.py:459, 493
```python
exit_price=close_price,  # Executes at exact close
```
**REALITY**: Exit signal fires at close, can't execute there. Exit at next open + slippage.
**MAGNITUDE**: Stop losses 0.3-0.5% worse, take profits 0.1-0.3% worse.

### [HIGH] Position Size Cost Model Doesn't Scale with Liquidity
**File**: backtest_models.py:31
5% position in BTC = negligible impact. 5% in small cap = 0.5-2% market impact.

### [HIGH] No Execution Variance
All calculations assume perfect execution. Reality: partial fills, gap risk, slippage variance.

## CUMULATIVE IMPACT

| Component | Backtest | Reality | Gap |
|-----------|----------|---------|-----|
| Entry slippage | 0% | -0.3% | -0.3% |
| Spread (not deducted) | 0% | -0.04% | -0.04% |
| Exit slippage | 0% | -0.2% | -0.2% |
| **Total** | **0%** | **-0.54%** | **-0.54%** |

For marginal strategies (1% profit margin), these gaps are LETHAL.

## FIXES REQUIRED

1. Add `spread_pct` to line 644 deduction
2. Use next candle open for entry (line 478)
3. Add execution variance (0.1-0.25% random per trade)
4. Scale slippage with position size vs daily volume
5. Implement unimplemented tests in test_economic_validity.py

## WARNING

Evolved strategies will be overfit to backtest delusions and underperform in live trading.
