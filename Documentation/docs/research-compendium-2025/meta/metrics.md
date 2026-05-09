# Performance Metrics

> **Formulas and definitions for evaluating trading performance**
>
> All metrics should be calculated consistently across the system.

---

## Return Metrics

### Simple Return

$$
R = \frac{P_{end} - P_{start}}{P_{start}}
$$

Where:
- $P_{end}$ = ending price/value
- $P_{start}$ = starting price/value

### Log Return

$$
r = \ln\left(\frac{P_{end}}{P_{start}}\right)
$$

Log returns are additive across time periods and more suitable for statistical analysis.

### Total Return (ROI)

$$
ROI = \frac{\text{Total PnL}}{\text{Initial Capital}}
$$

### Annualized Return

$$
R_{annual} = (1 + R_{total})^{\frac{252}{n}} - 1
$$

Where:
- $n$ = number of trading days
- 252 = trading days per year

---

## Risk-Adjusted Metrics

### Sharpe Ratio

$$
\text{Sharpe} = \frac{R_p - R_f}{\sigma_p}
$$

Where:
- $R_p$ = portfolio return
- $R_f$ = risk-free rate (often 0 for crypto)
- $\sigma_p$ = standard deviation of returns

**Interpretation:**
- < 0: Losing money
- 0-1: Subpar
- 1-2: Good
- 2-3: Very good
- > 3: Excellent (or suspicious overfitting)

**Annualized Sharpe:**

$$
\text{Sharpe}_{annual} = \text{Sharpe}_{daily} \times \sqrt{252}
$$

### Sortino Ratio

$$
\text{Sortino} = \frac{R_p - R_f}{\sigma_d}
$$

Where $\sigma_d$ = downside deviation (only negative returns).

Better than Sharpe when returns are asymmetric (don't penalize upside volatility).

### Calmar Ratio

$$
\text{Calmar} = \frac{R_{annual}}{\text{Max Drawdown}}
$$

Higher = better return per unit of maximum pain.

---

## Drawdown Metrics

### Drawdown

$$
DD_t = \frac{P_{peak} - P_t}{P_{peak}}
$$

Current decline from peak value.

### Maximum Drawdown

$$
\text{Max DD} = \max_t(DD_t)
$$

Largest peak-to-trough decline. Critical risk metric.

### Average Drawdown

$$
\text{Avg DD} = \frac{1}{n}\sum_{i=1}^{n} DD_i
$$

Mean drawdown across all drawdown periods.

### Drawdown Duration

Time spent in drawdown before recovery to previous peak.

---

## Trade Metrics

### Win Rate

$$
\text{Win Rate} = \frac{\text{Winning Trades}}{\text{Total Trades}}
$$

Typical healthy range: 40-60%.

### Profit Factor

$$
\text{Profit Factor} = \frac{\text{Gross Profit}}{\text{Gross Loss}}
$$

- < 1: Losing system
- 1-1.5: Marginal
- 1.5-2: Good
- > 2: Excellent

### Average Win / Average Loss

$$
\text{Win/Loss Ratio} = \frac{\text{Avg Win}}{\text{Avg Loss}}
$$

Relationship with win rate:
- High win rate + low ratio = many small wins, few big losses
- Low win rate + high ratio = few big wins, many small losses

### Expectancy (Average Trade)

$$
E = (W \times \text{Avg Win}) - (L \times \text{Avg Loss})
$$

Where:
- $W$ = win rate
- $L$ = 1 - win rate

Expected profit per trade. Must be positive for profitable system.

---

## Position Sizing Metrics

### Kelly Fraction

$$
f^* = \frac{p \cdot b - q}{b}
$$

Where:
- $p$ = win probability
- $q$ = loss probability (1-p)
- $b$ = win/loss ratio

Optimal fraction of capital to bet for maximum growth.

### Fractional Kelly

$$
f = k \cdot f^*
$$

Where $k$ typically 0.25-0.5 for safety.

### Optimal f

$$
f = \frac{W}{A} - \frac{(1-W)}{B}
$$

Where:
- $W$ = win rate
- $A$ = average win
- $B$ = average loss

---

## Volatility Metrics

### Standard Deviation (Volatility)

$$
\sigma = \sqrt{\frac{1}{n-1}\sum_{i=1}^{n}(r_i - \bar{r})^2}
$$

### Annualized Volatility

$$
\sigma_{annual} = \sigma_{daily} \times \sqrt{252}
$$

### ATR (Average True Range)

$$
TR_t = \max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|)
$$

$$
ATR_n = \frac{1}{n}\sum_{i=1}^{n}TR_i
$$

Or as EMA:

$$
ATR_t = \frac{ATR_{t-1} \times (n-1) + TR_t}{n}
$$

---

## Regime Detection Metrics

### Trend Strength (ADX)

Average Directional Index. Measures trend strength regardless of direction.

- < 20: Weak/no trend
- 20-40: Strong trend
- > 40: Very strong trend

### Volatility Percentile

$$
\text{Vol Percentile} = \frac{\#(\sigma < \sigma_{current})}{\text{Total Observations}}
$$

Where current volatility ranks in historical distribution.

---

## Fitness Score Components

Our fitness function combines multiple metrics:

$$
\text{Fitness} = w_1 \cdot S_{sharpe} + w_2 \cdot S_{roi} + w_3 \cdot S_{winrate} + w_4 \cdot S_{drawdown} + w_5 \cdot S_{trades}
$$

**Component Scores (each 0-100):**

| Component | Formula | Weight |
|-----------|---------|--------|
| Sharpe Score | $\min(100, \max(0, \text{Sharpe} \times 30 + 50))$ | 30% |
| ROI Score | $\min(100, \max(0, \text{ROI} \times 2 + 50))$ | 25% |
| Win Rate Score | $\text{Win Rate} \times 100$ | 20% |
| Drawdown Score | $\max(0, 100 - \text{DD} \times 200)$ | 15% |
| Trade Bonus | $\min(20, \text{Trades} / 10)$ | 10% |

---

## Sanity Bounds (EDD)

From Evidence-Driven Development rules:

| Metric | Realistic Range | Red Flag |
|--------|-----------------|----------|
| Sharpe Ratio | 0.5 - 3.0 | > 3.0 (overfitting) |
| Max Drawdown | < 20% | > 30% |
| Win Rate | 40% - 60% | > 70% (suspicious) |
| Profit Factor | 1.2 - 2.5 | > 3.0 (suspicious) |
| Avg Trade Duration | > 1 hour | < 1 min (overtrading) |
| Slippage | 2-10 bps | 0 (unrealistic) |

---

## Code Implementation

```python
def calculate_sharpe(returns: list[float], risk_free: float = 0.0) -> float:
    """Calculate Sharpe ratio."""
    if len(returns) < 2:
        return 0.0

    excess_returns = [r - risk_free for r in returns]
    mean_return = np.mean(excess_returns)
    std_return = np.std(excess_returns, ddof=1)

    if std_return == 0:
        return 0.0

    return mean_return / std_return


def calculate_sortino(returns: list[float], risk_free: float = 0.0) -> float:
    """Calculate Sortino ratio (downside volatility only)."""
    if len(returns) < 2:
        return 0.0

    excess_returns = [r - risk_free for r in returns]
    downside_returns = [r for r in excess_returns if r < 0]

    if not downside_returns:
        return float('inf')  # No downside

    mean_return = np.mean(excess_returns)
    downside_std = np.std(downside_returns, ddof=1)

    if downside_std == 0:
        return float('inf')

    return mean_return / downside_std


def calculate_max_drawdown(equity_curve: list[float]) -> float:
    """Calculate maximum drawdown."""
    peak = equity_curve[0]
    max_dd = 0.0

    for value in equity_curve:
        if value > peak:
            peak = value
        dd = (peak - value) / peak
        max_dd = max(max_dd, dd)

    return max_dd


def calculate_profit_factor(trades: list[float]) -> float:
    """Calculate profit factor."""
    gross_profit = sum(t for t in trades if t > 0)
    gross_loss = abs(sum(t for t in trades if t < 0))

    if gross_loss == 0:
        return float('inf') if gross_profit > 0 else 0.0

    return gross_profit / gross_loss


def calculate_expectancy(
    win_rate: float,
    avg_win: float,
    avg_loss: float
) -> float:
    """Calculate expected profit per trade."""
    return (win_rate * avg_win) - ((1 - win_rate) * avg_loss)


def calculate_fitness(
    sharpe: float,
    roi: float,
    win_rate: float,
    max_drawdown: float,
    trade_count: int
) -> float:
    """
    Calculate fitness score (0-100).

    Used for pattern/agent selection.
    """
    # Component scores
    sharpe_score = min(100, max(0, sharpe * 30 + 50))
    roi_score = min(100, max(0, roi * 200 + 50))  # roi as decimal
    winrate_score = win_rate * 100
    dd_score = max(0, 100 - max_drawdown * 200)  # dd as decimal
    trade_bonus = min(20, trade_count / 10)

    # Weighted combination
    fitness = (
        0.30 * sharpe_score +
        0.25 * roi_score +
        0.20 * winrate_score +
        0.15 * dd_score +
        0.10 * trade_bonus
    )

    return float(np.clip(fitness, 0, 100))
```

---

## Related Files

- [../concepts/position-sizing.md](../concepts/position-sizing.md) - Kelly criterion
- [../concepts/risk-management.md](../concepts/risk-management.md) - Drawdown management
- [traits.md](traits.md) - How traits affect metrics

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-28 | Initial metrics document |
