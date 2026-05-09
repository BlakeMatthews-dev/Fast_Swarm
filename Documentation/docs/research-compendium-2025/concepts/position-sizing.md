# Position Sizing

> **Kelly Criterion and Confidence-Adjusted Allocation**
>
> How much to bet on each trade based on edge and confidence.

---

## Overview

Position sizing determines what fraction of capital to allocate to each trade. The core insight from Kelly criterion papers:

> "The optimal bet size depends on both the probability of winning AND the size of the win/loss."

---

## Source Papers

| Paper | Key Contribution | Path |
|-------|------------------|------|
| Kelly 1956 | Original Kelly criterion | Classic |
| Thorp | Kelly for trading | Classic |
| arxiv-2402.15588 | Focused portfolio sizing | [../papers/arxiv-2402.15588-focused-portfolio.md](../papers/arxiv-2402.15588-focused-portfolio.md) |
| MASA | Multi-agent risk parity | [../papers/arxiv-2402.00515-masa.md](../papers/arxiv-2402.00515-masa.md) |

---

## Kelly Criterion Fundamentals

### Basic Formula

For a binary outcome (win/lose):

$$
f^* = \frac{p \cdot b - q}{b}
$$

Where:
- $f^*$ = fraction of capital to bet
- $p$ = probability of winning
- $q$ = probability of losing (1 - p)
- $b$ = win/loss ratio (how much you win per dollar risked)

### Example

If you have:
- 55% win rate (p = 0.55, q = 0.45)
- 2:1 reward/risk ratio (b = 2)

Then:
$$
f^* = \frac{0.55 \times 2 - 0.45}{2} = \frac{1.1 - 0.45}{2} = \frac{0.65}{2} = 0.325
$$

Optimal bet = 32.5% of capital.

### The Problem with Full Kelly

Full Kelly is mathematically optimal for long-run wealth growth BUT:
1. Assumes perfect probability estimates (we don't have them)
2. Creates extreme volatility
3. One bad estimate can be catastrophic

**Solution: Fractional Kelly (Half-Kelly or less)**

---

## Fractional Kelly

### Formula

$$
f_{fractional} = k \cdot f^*
$$

Where $k$ is typically 0.25 to 0.5 (Quarter to Half Kelly).

### Why Fractional?

| Kelly Fraction | Risk Level | Notes |
|----------------|------------|-------|
| Full (k=1.0) | Maximum | Theoretically optimal, practically dangerous |
| Half (k=0.5) | High | 75% of optimal growth, much less volatility |
| Quarter (k=0.25) | Moderate | Safe for uncertain estimates |
| Eighth (k=0.125) | Conservative | For high-uncertainty situations |

### Implementation

```python
def calculate_kelly_fraction(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    kelly_multiplier: float = 0.25  # Quarter Kelly default
) -> float:
    """
    Calculate Kelly criterion position size.

    Args:
        win_rate: Historical win rate (0-1)
        avg_win: Average winning trade return (positive)
        avg_loss: Average losing trade return (positive, absolute value)
        kelly_multiplier: Fraction of full Kelly to use (0.25-0.5 typical)

    Returns:
        Position size as fraction of capital (0-1)

    Paper Reference: Kelly 1956, adapted for trading
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

    # Apply fractional multiplier
    fractional_kelly = kelly_multiplier * full_kelly

    # Safety cap
    return min(fractional_kelly, 0.25)  # Never more than 25%
```

---

## Confidence-Adjusted Kelly

### Key Insight

Our win rate estimates have uncertainty. Higher uncertainty = smaller bet.

### Formula

$$
f_{adjusted} = f^* \cdot k \cdot c
$$

Where:
- $f^*$ = full Kelly fraction
- $k$ = Kelly multiplier (0.25-0.5)
- $c$ = confidence in the signal (0-1)

### Implementation

```python
def confidence_adjusted_kelly(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    signal_confidence: float,
    kelly_multiplier: float = 0.25,
    min_confidence: float = 0.5
) -> float:
    """
    Position size adjusted by signal confidence.

    Low confidence signals get smaller positions.
    Confidence below min_confidence = no trade.

    Paper Reference: MASA - confidence-weighted allocation
    """
    if signal_confidence < min_confidence:
        return 0.0

    base_kelly = calculate_kelly_fraction(
        win_rate, avg_win, avg_loss, kelly_multiplier
    )

    # Scale by confidence
    # Confidence 0.5 -> 0.5x position
    # Confidence 1.0 -> 1.0x position
    confidence_factor = signal_confidence

    return base_kelly * confidence_factor
```

---

## Constrained Kelly for Multiple Positions

### The Problem

With multiple concurrent positions:
1. Correlation between positions matters
2. Total portfolio risk needs limiting
3. Individual position limits needed

### Constraints

```python
@dataclass
class PositionConstraints:
    """Constraints for position sizing."""

    # Per-position limits
    max_single_position: float = 0.20   # 20% max per trade
    min_position_size: float = 0.01     # 1% minimum (avoid dust)

    # Portfolio limits
    max_total_exposure: float = 0.80    # 80% max invested
    max_correlated_exposure: float = 0.40  # 40% max in correlated assets

    # Risk limits
    max_portfolio_var: float = 0.02     # 2% daily VaR
    max_drawdown_limit: float = 0.15    # 15% max drawdown trigger
```

### Constrained Optimization

```python
def constrained_kelly_allocation(
    signals: list[TradeSignal],
    constraints: PositionConstraints,
    current_positions: dict[str, float],
    correlation_matrix: np.ndarray
) -> dict[str, float]:
    """
    Allocate capital across multiple signals with constraints.

    Paper Reference: arxiv-2402.15588 "Sizing the Bets"
    "Focused portfolios require careful position sizing to
     manage concentration risk while capturing alpha"

    Uses constrained optimization to maximize expected growth
    while respecting all risk limits.
    """
    allocations = {}

    for signal in signals:
        # Base Kelly calculation
        base_size = confidence_adjusted_kelly(
            win_rate=signal.pattern.win_rate,
            avg_win=signal.pattern.avg_win,
            avg_loss=signal.pattern.avg_loss,
            signal_confidence=signal.confidence,
        )

        # Apply single position limit
        size = min(base_size, constraints.max_single_position)

        # Check total exposure
        current_total = sum(current_positions.values())
        if current_total + size > constraints.max_total_exposure:
            size = max(0, constraints.max_total_exposure - current_total)

        # Check correlation
        correlated_exposure = calculate_correlated_exposure(
            signal.asset,
            size,
            current_positions,
            correlation_matrix
        )
        if correlated_exposure > constraints.max_correlated_exposure:
            size *= constraints.max_correlated_exposure / correlated_exposure

        # Apply minimum
        if size < constraints.min_position_size:
            size = 0.0

        allocations[signal.asset] = size

    return allocations
```

---

## Agent Trait Integration

Position sizing is influenced by agent personality traits:

| Trait | Effect on Position Size |
|-------|------------------------|
| `risk_tolerance` | Higher = larger base positions |
| `drawdown_sensitivity` | Higher = more conservative after losses |
| `win_rate_preference` | Higher = prefer many small positions |
| `profit_target_greed` | Higher = hold winners longer |

### Trait-Adjusted Sizing

```python
def trait_adjusted_position_size(
    base_size: float,
    agent_traits: dict[str, float],
    recent_drawdown: float
) -> float:
    """
    Adjust position size based on agent personality.

    Paper Reference: TradingAgents - trait-driven behavior
    """
    # Risk tolerance scaling
    # 0.5 risk_tolerance = 0.75x size
    # 1.0 risk_tolerance = 1.25x size
    risk_factor = 0.5 + agent_traits['risk_tolerance'] * 0.75

    # Drawdown sensitivity adjustment
    # If in drawdown and sensitive, reduce size
    if recent_drawdown > 0.05:  # 5% drawdown
        dd_factor = 1.0 - (
            agent_traits['drawdown_sensitivity'] *
            min(recent_drawdown * 2, 0.5)  # Max 50% reduction
        )
    else:
        dd_factor = 1.0

    adjusted = base_size * risk_factor * dd_factor

    # Never exceed safe maximum
    return min(adjusted, 0.25)
```

---

## Practical Position Sizing Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                      TRADE SIGNAL RECEIVED                       │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                    CALCULATE BASE KELLY                          │
│  Using pattern's win rate, avg win, avg loss                     │
│  f* = (p * b - q) / b                                           │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                    APPLY FRACTIONAL KELLY                        │
│  f_frac = k * f* where k = 0.25 (quarter Kelly)                 │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                  ADJUST FOR CONFIDENCE                           │
│  f_conf = f_frac * signal_confidence                            │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                  ADJUST FOR AGENT TRAITS                         │
│  Apply risk_tolerance, drawdown_sensitivity                      │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                  APPLY CONSTRAINTS                               │
│  - Max single position (20%)                                     │
│  - Max total exposure (80%)                                      │
│  - Max correlated exposure (40%)                                 │
│  - Portfolio VaR limit                                           │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                    FINAL POSITION SIZE                           │
│  Ready for execution tier                                        │
└──────────────────────────────────────────────────────────────────┘
```

---

## Common Mistakes to Avoid

1. **Using Full Kelly**: Always use fractional (0.25-0.5)
2. **Ignoring Correlation**: Correlated positions compound risk
3. **Fixed Position Sizes**: Adapt to confidence and conditions
4. **Ignoring Drawdown**: Reduce size during losing streaks
5. **Over-Precision**: Kelly inputs are estimates, not facts

---

## Implementation Code

See [../code/kelly_criterion.py](../code/kelly_criterion.py) for production implementation.

---

## Related Files

- [risk-management.md](risk-management.md) - Stop losses and circuit breakers
- [../architecture/3-tier-execution.md](../architecture/3-tier-execution.md) - Execution constraints
- [../meta/traits.md](../meta/traits.md) - Trait definitions

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-28 | Initial concept document |
