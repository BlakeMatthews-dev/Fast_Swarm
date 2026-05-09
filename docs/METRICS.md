# Fast_Swarm Metrics Reference

**Primary Metrics**: Sortino Ratio, Alpha (vs Buy & Hold)
**Ranking System**: 5-Tier Quintile, Regime-Based Fitness

---

## Primary Fitness Metrics

### Sortino Ratio (Primary Risk-Adjusted Metric)

Unlike Sharpe ratio which penalizes all volatility, Sortino only penalizes **downside deviation** - upside volatility is good!

```python
def sortino_ratio(returns: List[float], target_return: float = 0) -> float:
    """
    Sortino = (Mean Return - Target) / Downside Deviation

    - Only negative returns count toward risk
    - Higher is better (2.0+ is excellent)
    """
    excess_returns = [r - target_return for r in returns]
    mean_excess = sum(excess_returns) / len(excess_returns)

    # Only downside deviation
    downside_returns = [r for r in excess_returns if r < 0]
    if not downside_returns:
        return float('inf')  # No downside = infinite Sortino

    downside_dev = (sum(r**2 for r in downside_returns) / len(downside_returns)) ** 0.5

    if downside_dev == 0:
        return 0  # Division safety

    return mean_excess / downside_dev
```

**Why Sortino over Sharpe?**
- Trading strategies WANT upside volatility
- A strategy that makes 50% one month and 5% the next is better than 10% every month
- Sharpe would penalize the volatile winner unfairly

### Alpha (vs Buy & Hold)

Alpha measures **excess return over simply holding the asset**.

```python
def calculate_alpha(agent_cagr: float, asset_cagr: float) -> float:
    """
    Alpha = Agent CAGR - Asset Buy&Hold CAGR

    - Positive alpha = agent beats holding
    - Negative alpha = should have just held
    """
    return agent_cagr - asset_cagr
```

**Example:**
- BTC returned 80% over backtest period (buy & hold)
- Agent returned 120% over same period
- Alpha = 120% - 80% = **+40% alpha**

This is the purest measure of whether the strategy adds value.

---

## Secondary Metrics

### Calmar Ratio

Risk-adjusted return using maximum drawdown:

```python
def calmar_ratio(annualized_return: float, max_drawdown: float) -> float:
    """
    Calmar = Annualized Return / Max Drawdown

    - Higher is better
    - 1.0+ is good, 2.0+ is excellent
    """
    if max_drawdown == 0:
        return 0  # Division safety
    return annualized_return / abs(max_drawdown)
```

### Maximum Drawdown

Largest peak-to-trough decline:

```python
def max_drawdown(equity_curve: List[float]) -> float:
    """
    Returns the worst percentage decline from any peak.
    """
    peak = equity_curve[0]
    max_dd = 0

    for value in equity_curve:
        if value > peak:
            peak = value
        dd = (peak - value) / peak
        if dd > max_dd:
            max_dd = dd

    return max_dd
```

### Win Rate

Percentage of winning trades (used as secondary indicator, NOT primary fitness):

```python
def win_rate(trades: List[Trade]) -> float:
    """
    Simple percentage of profitable trades.

    Note: High win rate with small wins and big losses is BAD.
    Always pair with profit factor or expectancy.
    """
    winners = sum(1 for t in trades if t.pnl > 0)
    return winners / len(trades) if trades else 0
```

---

## Ranking System

### 5-Tier Quintile System

Agents and patterns are ranked into quintiles (0-4) based on percentile:

| Tier | Percentile | Description |
|------|------------|-------------|
| 4 | Top 20% | Elite performers |
| 3 | 60-80% | Strong performers |
| 2 | 40-60% | Average |
| 1 | 20-40% | Below average |
| 0 | Bottom 20% | Candidates for culling |

```python
def assign_tier(fitness_score: float, all_scores: List[float]) -> int:
    """
    Assign tier based on percentile ranking.
    """
    sorted_scores = sorted(all_scores)
    percentile = sorted_scores.index(fitness_score) / len(sorted_scores)

    if percentile >= 0.8:
        return 4
    elif percentile >= 0.6:
        return 3
    elif percentile >= 0.4:
        return 2
    elif percentile >= 0.2:
        return 1
    else:
        return 0
```

### Regime-Based Fitness

Fitness is calculated **per market regime**, not globally:

| Regime | Description | Detection |
|--------|-------------|-----------|
| Bull | Strong uptrend | Time-based (known periods) |
| Bear | Strong downtrend | Time-based (known periods) |
| Chop | Sideways volatility | Time-based (known periods) |
| Flat | Low volatility sideways | Time-based (known periods) |

```python
# Pattern fitness stored per regime
pattern.fitness_by_regime = {
    "bull": 0.85,   # Great in bull markets
    "bear": 0.32,   # Poor in bear markets
    "chop": 0.61,   # Decent in chop
    "flat": 0.45    # Below average in flat
}
```

**Why Time-Based Regimes?**
- Uses known historical periods (COVID crash, 2021 bull run, etc.)
- More deterministic than indicator-based detection
- Avoids regime detection becoming another prediction problem
- Easier to validate backtest results

---

## ELO Rating (Hivemind Only)

ELO is used **only for Hivemind committee voting**, not general evolution:

```python
def update_elo(winner_elo: float, loser_elo: float, k: float = 32) -> tuple:
    """
    Standard ELO calculation for head-to-head competition.

    Used when Hivemind committee members vote on trades.
    """
    expected_winner = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    expected_loser = 1 - expected_winner

    new_winner_elo = winner_elo + k * (1 - expected_winner)
    new_loser_elo = loser_elo + k * (0 - expected_loser)

    return new_winner_elo, new_loser_elo
```

**When ELO is Used:**
- Hivemind committee members vote on trade proposals
- Correct voters gain ELO, incorrect voters lose ELO
- High ELO agents get more voting weight

**When ELO is NOT Used:**
- General evolution selection (uses Sortino/Alpha)
- Pattern ranking (uses quintile system)
- Agent reproduction (uses fitness-based selection)

---

## Division Safety

All metric calculations must guard against division by zero:

```python
# CORRECT
sortino = (mean_return / downside_dev) if downside_dev > 0 else 0

# WRONG - will crash
sortino = mean_return / downside_dev
```

See `Tests/Soundness/Foundations/test_div_safety.py` for comprehensive tests.

---

## Metric Sanity Bounds

From EDD (Evidence-Driven Development) tests:

| Metric | Healthy Range | Red Flag |
|--------|---------------|----------|
| Sortino | 0.5 - 3.0 | > 5.0 (likely overfitting) |
| Alpha | -20% to +100% | > 200% (suspicious) |
| Max Drawdown | < 20% | > 50% (too risky) |
| Win Rate | 40% - 70% | > 90% (likely data issue) |
| Calmar | 0.5 - 3.0 | > 5.0 (likely overfitting) |

---

## What's NOT Used for Fitness

These metrics exist in the codebase but are **secondary indicators**, not primary fitness:

| Metric | Why Not Primary |
|--------|-----------------|
| Sharpe Ratio | Penalizes upside volatility unfairly |
| Win Rate | High win rate with bad R:R is losing strategy |
| Total Return | Doesn't account for risk |
| Trade Count | More trades ≠ better |
| Profit Factor | Less intuitive than Sortino |

---

## Composite Fitness Score

The fitness scoring system uses a **hybrid approach** with three phases:

### Phase 1: Hard Constraints (Auto-Reject)

Patterns/agents that fail these are immediately disqualified (fitness = 0):

| Constraint | Threshold | Reason |
|------------|-----------|--------|
| Max Drawdown | > 80% | Catastrophic risk |
| Profit Factor | < 0.5 | Gross losses > 2x gross wins |

### Phase 2: Multiplicative Core (0-60 points)

One bad metric tanks the entire core score - prevents compensating for poor risk metrics with high returns:

```python
# Normalize each component to 0-1 range
sortino_norm = min(sortino / 4, 1.0)
calmar_norm = min(calmar / 4, 1.0)
dd_factor = 1 - (max_drawdown_pct / 100)
pf_norm = min((profit_factor - 0.5) / 2.5, 1.0)

# Multiplicative combination
core_score = sortino_norm * calmar_norm * dd_factor * pf_norm * 60
```

### Phase 3: Additive Bonuses (0-40 points)

```python
alpha_bonus = min((alpha_cagr + 50) * 0.2, 20)  # 0-20 points
beat_bonus = benchmark_beat_rate * 10           # 0-10 points
win_bonus = win_rate * 10                       # 0-10 points

total_bonus = alpha_bonus + beat_bonus + win_bonus
```

### Final Score

```python
fitness = clamp(core_score + total_bonus, 0, 100)
```

### Score Interpretation

| Score Range | Tier | Action |
|-------------|------|--------|
| 70-100 | Elite | Production-ready |
| 50-69 | Good | Worth monitoring |
| 30-49 | Average | Needs improvement |
| 15-29 | Poor | Likely to be pruned |
| 0-14 | Terrible | Auto-rejected |

### Why Multiplicative Core?

Prevents patterns from compensating bad risk metrics with high returns:

```
Pattern A: Sortino 3.0, Calmar 0.2, DD 20%, PF 2.0
Core = (0.75 × 0.05 × 0.8 × 0.6) × 60 = 1.08 (BAD - low calmar tanks it)

Pattern B: Sortino 2.0, Calmar 2.0, DD 20%, PF 1.5
Core = (0.5 × 0.5 × 0.8 × 0.4) × 60 = 4.8 (BETTER - balanced)
```

---

## Position Sizing: Kelly Criterion

Optimal position size based on edge and win/loss ratio:

### Formula

```python
def calculate_kelly_fraction(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    kelly_multiplier: float = 0.25  # Quarter Kelly default
) -> float:
    """
    Kelly Criterion: K = W - (1-W)/R

    Where:
        W = win probability (win rate)
        R = win/loss ratio (avg_win / avg_loss)
        K = optimal position size as fraction of capital
    """
    if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
        return 0.0

    p = win_rate
    q = 1 - win_rate
    b = avg_win / avg_loss  # Win/loss ratio

    # Full Kelly
    full_kelly = (p * b - q) / b

    # If negative, no edge - don't bet
    if full_kelly <= 0:
        return 0.0

    # Apply fractional multiplier (Half Kelly or Quarter Kelly)
    fractional_kelly = kelly_multiplier * full_kelly

    # Safety cap at 25%
    return min(fractional_kelly, 0.25)
```

### Kelly Fractions

| Kelly Fraction | Risk Level | Notes |
|----------------|------------|-------|
| Full (k=1.0) | Maximum | Theoretically optimal, practically dangerous |
| Half (k=0.5) | High | 75% of optimal growth, much less volatility |
| Quarter (k=0.25) | Moderate | Safe for uncertain estimates (default) |
| Eighth (k=0.125) | Conservative | For high-uncertainty situations |

### Example

```python
# 65% win rate, 2:1 win/loss ratio
kelly = calculate_kelly_fraction(0.65, 0.10, 0.05)
# Full Kelly = 0.575 (57.5% of capital)
# Quarter Kelly = 0.144 (14.4% of capital)
```

### Confidence-Adjusted Kelly

Position size scales with signal confidence:

```python
def confidence_adjusted_kelly(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    signal_confidence: float,  # 0-1
    kelly_multiplier: float = 0.25,
    min_confidence: float = 0.5
) -> float:
    """Low confidence signals get smaller positions."""
    if signal_confidence < min_confidence:
        return 0.0

    base_kelly = calculate_kelly_fraction(
        win_rate, avg_win, avg_loss, kelly_multiplier
    )

    return base_kelly * signal_confidence
```

---

## Alpha Metrics (Extended)

### Alpha CAGR

Annualized excess return over buy-and-hold:

```python
alpha_cagr = agent_cagr - benchmark_cagr
```

### Drawdown Alpha

How much better/worse your max drawdown is vs benchmark:

```python
drawdown_alpha = benchmark_max_dd - agent_max_dd
# Positive = better risk profile than buy-hold
```

### Alpha Decay Ratio

Measures if pattern is degrading over time:

```python
alpha_decay_ratio = recent_30d_roi / lifetime_roi
```

| Value | Interpretation |
|-------|---------------|
| > 1.0 | Pattern improving (rare) |
| 0.8 - 1.0 | Healthy (normal variance) |
| 0.5 - 0.8 | Degrading (investigate) |
| < 0.5 | Decayed (retire pattern) |

**Auto-Retirement Trigger**: Alpha decay < 0.5 for 60+ days → Pattern retired

---

## Diversity Metrics

### Shannon Entropy

Measures pattern usage diversity across agent population:

```python
entropy = -sum(p * log(p) for p in pattern_usage_probabilities)
```

| Value | Interpretation |
|-------|---------------|
| > 0.7 | Excellent diversity |
| 0.5 - 0.7 | Good diversity |
| 0.3 - 0.5 | Moderate (warning) |
| < 0.3 | Poor (monoculture risk) |

### Correlation Coefficient

Measures how similarly two agents trade:

```python
correlation = cov(returns_A, returns_B) / (std(returns_A) * std(returns_B))
```

For diversification, want low correlation:
- < 0.3: Excellent diversification
- 0.3 - 0.5: Good
- > 0.7: High redundancy (eliminate one agent)

---

## Metrics in Database Schema

```sql
-- Agent metrics
ALTER TABLE agents ADD COLUMN sortino_ratio FLOAT;
ALTER TABLE agents ADD COLUMN calmar_ratio FLOAT;
ALTER TABLE agents ADD COLUMN max_drawdown_pct FLOAT DEFAULT 0.0;
ALTER TABLE agents ADD COLUMN annualized_roi_pct FLOAT DEFAULT 0.0;
ALTER TABLE agents ADD COLUMN alpha FLOAT;  -- vs buy&hold

-- Pattern metrics
ALTER TABLE patterns ADD COLUMN fitness_by_regime JSONB DEFAULT '{}';
-- Example: {"bull": 0.85, "bear": 0.32, "chop": 0.61, "flat": 0.45}
```

---

*Last Updated: 2026-01-13*
