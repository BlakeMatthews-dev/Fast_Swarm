# Multi-Window Backtest System

This document describes the multi-window backtesting approach used in Fast_Swarm for evaluating both agents and patterns.

---

## Overview

The backtest system evaluates trading performance across **multiple time windows** and **multiple timeframes** to ensure robustness and reduce overfitting to specific market conditions.

### Key Principles

1. **No Train/Test Split** - All data is used for testing. There is no "training" phase.
2. **Multi-Window Validation** - Performance must be consistent across different time periods.
3. **Asymmetric Weighting** - Smaller windows are penalized (less statistically reliable).
4. **PostgreSQL Only** - All environments use PostgreSQL with TimescaleDB.

---

## Configuration

### Timeframe Windows

| Timeframe | Window | Candles | Duration | Weight |
|-----------|--------|---------|----------|--------|
| **1h** | Small | 240 | ~10 days | 30% |
| **1h** | Medium | 800 | ~33 days | 100% |
| **1h** | Large | 2880 | ~120 days | 100% |
| **15m** | Small | 720 | ~7.5 days | 30% |
| **15m** | Medium | 2400 | ~25 days | 100% |
| **15m** | Large | 8000 | ~83 days | 100% |

### Window Weighting Formula

```python
def window_weight(window_idx: int) -> float:
    """
    Asymmetric weighting: small=30%, medium=100%, large=100%

    Small windows have less data, making fitness scores less reliable.
    Medium and large windows get full weight.
    """
    weights = [0.30, 1.0, 1.0]  # [small, medium, large]
    return weights[window_idx]
```

### Fitness Aggregation

Fitness is aggregated using a **trade-count weighted average**:

```python
# Per-timeframe aggregation
for fitness, trade_count, win_idx, weight in window_data:
    w = trade_count * weight  # Weight by both trade count AND window weight
    weighted_sum += fitness * w
    total_weight += w

tf_fitness = weighted_sum / total_weight

# Cross-timeframe aggregation
for tf in timeframes:
    weighted_sum += tf_fitness[tf] * tf_trades[tf]
    total_weight += tf_trades[tf]

final_fitness = weighted_sum / total_weight
```

### Minimum Trades Threshold

```python
MIN_TRADES_FOR_SIGNIFICANCE = 2  # Per window
```

A window only contributes to fitness if it has at least 2 trades. This prevents single-trade flukes from influencing scores.

---

## Scripts

### Agent Backtest: `scripts/run_backtest.py`

Tests all active agents across multi-timeframe windows.

```bash
cd Fast_Swarm && python scripts/run_backtest.py
```

**Output metrics:**
- Total trades per timeframe/window
- Agents scored per window
- Window coverage (% of agents with 2+ windows)
- Fitness distribution (mean, median, std, quartiles)
- Top 10 agents by fitness

### Pattern Backtest: `scripts/run_pattern_backtest.py`

Tests 500 random active patterns across the same windows.

```bash
cd Fast_Swarm && python scripts/run_pattern_backtest.py
```

**Process:**
1. Load 500 random patterns where `is_active=True` and `entry_conditions IS NOT NULL`
2. Create dummy agent per pattern (isolates pattern performance)
3. Run through all windows
4. Calculate pattern-specific fitness
5. Update pattern fitness in database

---

## Target Metrics

| Metric | Target | Reasoning |
|--------|--------|-----------|
| Agents on 2+ windows | 50% | Ensures broad validation |
| Agents scored (any window) | 80%+ | Most agents should generate trades |
| Patterns on 2+ windows | 50% | Same reasoning as agents |

---

## Database Integration

### Data Source

All candle data comes from `enhanced_candles` table (TimescaleDB hypertable):

```python
statement = (
    select(EnhancedCandle)
    .where(EnhancedCandle.symbol == asset)
    .where(EnhancedCandle.timeframe == timeframe)
    .order_by(EnhancedCandle.time.desc())
    .offset(offset).limit(window_size)
)
```

### Async Session Management

**Critical:** asyncpg connection pools are tied to event loops. On Windows, when `asyncio.run()` closes, the proactor event loop destroys transport layers, making pooled connections unusable.

```python
# WRONG - causes "Event loop is closed" errors
patterns = asyncio.run(load_patterns())  # Creates pool
data = asyncio.run(load_data())          # Pool connections dead!

# CORRECT Option 1 - Single async context for reads
async def load_all_async():
    patterns = await load_patterns()
    data = await load_data()
    return patterns, data

patterns, data = asyncio.run(load_all_async())

# CORRECT Option 2 - Use sync psycopg3 for writes after async reads
# (avoids asyncpg pool entirely for write phase)
def update_pattern_fitness_sync(updates):
    import psycopg  # psycopg3 (modern, faster)
    conn = psycopg.connect(...)  # Fresh sync connection
    cursor.executemany(sql, batch_data)  # Uses prepared statements
    conn.close()
```

The pattern backtest script uses Option 2: async reads via asyncpg, sync writes via psycopg3.

---

## Results Interpretation

### Agent Backtest Example Output

```
=== 1h ===
  small (240): 842 trades, 36 scored
  medium (800): 4116 trades, 81 scored
  large (2880): 10851 trades, 89 scored

=== 15m ===
  small (720): 1152 trades, 67 scored
  medium (2400): 4895 trades, 95 scored
  large (8000): 14892 trades, 100 scored

--- AGENTS ---
Total: 224
Scored: 180 (80.4%)

*** WINDOW COVERAGE (target: 50% on 2+ windows) ***
  1+ windows: 180 (80.4%)
  2+ windows: 101 (45.1%)
  3+ windows: 63 (28.1%)
```

### Pattern Backtest Example Output

```
=== 1h ===
  small (240): 283 trades, 94 patterns scored
  medium (800): 1773 trades, 218 patterns scored
  large (2880): 4363 trades, 236 patterns scored

=== 15m ===
  small (720): 385 trades, 172 patterns scored
  medium (2400): 1595 trades, 246 patterns scored
  large (8000): 5181 trades, 269 patterns scored

--- SUMMARY ---
Patterns tested: 500
Patterns scored: 288 (57.6%)
Total trades: 13,580

*** WINDOW COVERAGE ***
  1+ windows: 288 (57.6%)
  2+ windows: 256 (51.2%)  <-- TARGET MET!

--- FITNESS ---
Mean: 31.29
Median: 30.01
Top: 80.0 (volatility_breakout)
```

---

## Architecture Decisions

### Why No Train/Test Split?

1. **No ML Training** - Patterns are rule-based, not learned from data
2. **Evolution is Selection** - Genetic evolution selects patterns, doesn't train them
3. **All Data is Test Data** - Every window is a validation window
4. **Overfitting Detection** - Multi-window consistency catches overfitting

### Why Asymmetric Weighting?

1. **Statistical Reliability** - Small windows have fewer trades, higher variance
2. **Recent Data Value** - Small window is most recent, but least reliable
3. **Balanced Approach** - Medium/large windows anchor the score

### Why Multiple Timeframes?

1. **Regime Diversity** - Different timeframes capture different market behaviors
2. **Robustness** - A pattern working on both 1h and 15m is more robust
3. **Trade Frequency** - 15m generates more trades for statistical significance

---

## Related Files

| File | Purpose |
|------|---------|
| `scripts/run_backtest.py` | Agent multi-window backtest |
| `scripts/run_pattern_backtest.py` | Pattern multi-window backtest |
| `local_agents/config.py` | Configuration constants |
| `local_agents/backtest/engine.py` | Core backtest engine |
| `local_agents/backtest/pattern_matcher.py` | Pattern condition evaluation |
| `local_agents/core/evolution.py` | Fitness evaluation functions |

---

## Changelog

### 2026-01-10: Multi-Window Backtest Implementation

#### Changes Made

| Change | File | Reasoning |
|--------|------|-----------|
| Removed `WALK_FORWARD_SPLIT` config | `local_agents/config.py` | No train/test split - all data is for testing |
| Removed SQLite references | `local_agents/config.py`, `CLAUDE.md` | PostgreSQL-only architecture |
| Lowered `MIN_TRADES_FOR_SIGNIFICANCE` from 30 to 2 | `local_agents/config.py` | Per-window threshold was too high; agents couldn't score |
| Created multi-window agent backtest | `scripts/run_backtest.py` | Replaced single-window approach |
| Created multi-window pattern backtest | `scripts/run_pattern_backtest.py` | Patterns need same validation as agents |
| Renamed `TestOutOfSampleValidation` to `TestMultiWindowValidation` | `Tests/Soundness/Backtest/test_economic_validity.py` | Terminology correction |
| Added train/test split warning | `CLAUDE.md` | Prevent accidental reintroduction |
| Used psycopg3 for DB writes | `scripts/run_pattern_backtest.py` | asyncpg pool tied to event loop; psycopg3 sync avoids issue |
| **Added accumulation mode** | `local_agents/backtest/engine.py` | BTC/ETH/SOL never exit at loss; hold until profit or end of data |
| Marked `max_hold_candles` as deprecated | `local_agents/backtest/engine.py` | Was never enforced; now explicitly documented |

#### Configuration Evolution

| Iteration | 1h Windows | 15m Windows | Result |
|-----------|------------|-------------|--------|
| Initial | [200, 200, 200] | [200, 200, 200] | 8% on 2+ windows |
| v2 | [400, 400, 400] | [400, 400, 400] | 15% on 2+ windows |
| v3 | [120, 400, 1440] | [360, 1200, 4000] | 32% on 2+ windows |
| v4 (final) | [240, 800, 2880] | [720, 2400, 8000] | 45% on 2+ windows |

#### Weighting Evolution

| Iteration | Formula | Result |
|-----------|---------|--------|
| Initial | Symmetric normal (small=30%, medium=100%, large=30%) | Unbalanced |
| v2 | Linear recency (30 candles=30%, 100 candles=100%) | Complex |
| Final | Asymmetric (small=30%, medium=100%, large=100%) | Clean, robust |

#### Key Insights

1. **Window Size Matters More Than Weighting** - Doubling window sizes had more impact than tuning weights
2. **Timeframe Scaling** - 15m windows need 3x more candles than 1h to cover same calendar time
3. **asyncpg Connection Pools** - Cannot call `asyncio.run()` multiple times with shared session makers
4. **Trade Threshold Sweet Spot** - 2 trades per window balances noise vs. data availability
5. **psycopg3 > psycopg2** - Modern psycopg3 (`import psycopg`) is faster with prepared statements

#### asyncpg vs psycopg3 for Mixed Workflows

When a script needs both async reads (large dataset) and sync writes (batch updates):

| Driver | Use Case | Event Loop Behavior |
|--------|----------|---------------------|
| asyncpg | High-throughput async reads | Pool tied to event loop; dies when loop closes |
| psycopg3 sync | Batch writes after async | Fresh connection per call; no pool issues |
| psycopg3 async | Alternative to asyncpg | Different pool management, but same loop issues |

**Solution:** Use asyncpg for reads in one `asyncio.run()`, then psycopg3 sync for writes afterward.

---

---

## Accumulation Mode (NEW)

For high-conviction assets (BTC, ETH, SOL), the backtest engine now supports **accumulation mode** - a strategic approach that assumes these assets will recover from any drawdown.

### Configuration

```python
# Default ON in BacktestConfig
accumulation_mode: bool = True
accumulation_assets: set = {'BTC', 'ETH', 'SOL', 'BTC-USD', 'ETH-USD', ...}
unlimited_capital: bool = True
```

### Behavior

| Scenario | Trading Mode | Accumulation Mode |
|----------|--------------|-------------------|
| Price drops 10% | **Stop loss exits** | **Hold** |
| Price drops 50% | **Stop loss exits** | **Hold** |
| Price recovers | N/A (already exited) | **Exit at profit** |
| End of data | Close at current price | Close at current price |

### Exit Reasons

| Exit Reason | Trading Mode | Accumulation Mode |
|-------------|--------------|-------------------|
| `stop_loss` | ✅ Active | ❌ Disabled |
| `take_profit` | ✅ Active | ✅ Active |
| `trailing_stop` | ✅ Active | ✅ Active |
| `condition` | ✅ Active | ✅ Active |
| `end_of_data` | ✅ Active | ✅ Active |

### Rationale

```
Historical BTC Drawdowns:
- 2014: -85% → recovered in 3 years
- 2018: -84% → recovered in 3 years
- 2022: -77% → recovered in 2 years

If you assume recovery is inevitable:
- Stop losses = unnecessary friction
- Every dip = buying opportunity
- Time to profit > if profit
```

### New Metrics for Accumulation

| Metric | Description |
|--------|-------------|
| `time_to_profit` | Candles held before exit |
| `max_underwater_duration` | Longest period in drawdown |
| `recovery_efficiency` | % of bounce captured |
| `end_of_data_exits` | Trades forced closed (still underwater) |

---

## Future Improvements

1. **Canonical Periods** - Add regime-labeled historical windows (bull, bear, sideways)
2. **Multi-Position Support** - Allow concurrent positions for true unlimited capital
3. **Confidence Scoring** - Implement steep sigmoid/log curve for condition matching
4. **Parallel Execution** - Pattern backtests are embarrassingly parallel
5. **Time-to-Profit Metrics** - Track how long positions hold before profit
