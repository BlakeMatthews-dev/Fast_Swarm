# Glossary

> **Term definitions for the Coinswarm Research Compendium**
>
> Organized alphabetically with cross-references.

---

## A

### Active Roster
The subset of agents (typically 5-10) currently executing trades. Selected by Coaches based on regime affinity and recent performance. See [5-layer-hierarchy.md](../architecture/5-layer-hierarchy.md).

### Affinity Score
A 0-1 value representing how well an agent performs in a specific regime. Evolves based on trade outcomes. Higher affinity = better performance = more likely to be selected for roster. See [evolutionary-systems.md](../concepts/evolutionary-systems.md).

### Agent
An autonomous trading entity with 16 personality traits that influence decision-making. Agents compete, evolve, and can be cloned or retired. See [5-layer-hierarchy.md](../architecture/5-layer-hierarchy.md).

### ATR (Average True Range)
A volatility indicator measuring the average range between high and low prices over N periods. Used for position sizing and stop-loss calculation.

---

## B

### Backtest
Testing a trading strategy against historical data to estimate performance before live trading. Must include realistic slippage and fees.

### Bollinger Bands
Technical indicator with upper and lower bands at N standard deviations from a moving average. Position within bands indicates overbought/oversold.

### Bull/Bear Debate
From TradingAgents paper: structured argument between bullish and bearish agents before committee vote. Multiple debate rounds with rebuttals. See [three-pillars.md](../concepts/three-pillars.md).

---

## C

### Chaos Phase
The first evolution phase where random trades are made on real OHLCV data. Winners and losers are analyzed to discover patterns.

### Circuit Breaker
Automatic safety mechanism that halts trading when loss limits are exceeded. See [risk-management.md](../concepts/risk-management.md).

### Clone
Creating offspring agent from successful parent with small mutations (typically ±5-10% trait variation).

### Coach
Layer 4 in cognitive hierarchy. Manages agent roster selection, trait optimization, and agent development. See [5-layer-hierarchy.md](../architecture/5-layer-hierarchy.md).

### Committee
Layer 3 in cognitive hierarchy. Aggregates agent votes into trade decisions through weighted voting or debate. See [5-layer-hierarchy.md](../architecture/5-layer-hierarchy.md).

### Confidence
A 0-1 value indicating certainty in a signal or decision. Low confidence = smaller position size or skip trade.

### Crossover (Genetic)
Combining genetic material from two parent patterns to create offspring. Each gene randomly selected from either parent.

---

## D

### D1
Cloudflare's SQL database. Used for pattern definitions, agent configs. Note: Stats in D1 are often stale - use DO for live data.

### DO (Durable Object)
Cloudflare's stateful compute. Each DO has its own SQLite instance. Used for hot data like candles, pattern runs.

### Drawdown
Peak-to-trough decline in portfolio value. Expressed as percentage. Used for risk management triggers.

---

## E

### EMA (Exponential Moving Average)
Moving average that weights recent prices more heavily. `EMA = price * alpha + EMA_prev * (1 - alpha)` where `alpha = 2 / (period + 1)`.

### Episodic Memory
Short-term memory storing specific trade experiences. Retained ~7 days, used for similarity retrieval. See [memory-systems.md](../concepts/memory-systems.md).

### Evolution Cycle
The 4-phase process: CHAOS → DISCOVERY → BACKTEST → SELECT. Runs continuously to improve pattern and agent populations.

---

## F

### Fear & Greed Index
Sentiment indicator (0-100). Low values = fear (potential buy). High values = greed (potential sell).

### Fibonacci Estimation
Using Fibonacci numbers (1, 2, 3, 5, 8, 13, 21, 34, 55, 89) for complexity estimation. Non-linear scale reflects estimation uncertainty.

### Fitness Score
0-100 value measuring pattern/agent quality. Components: Sharpe, ROI, win rate, drawdown. <40 = die, 40-79 = survive, 80+ = promoted.

### Fractional Kelly
Using a fraction (typically 0.25-0.5) of full Kelly bet size for safety. Full Kelly is too aggressive for real trading.

### Funding Rate
Periodic payment between long/short positions on perpetual futures. Negative = shorts pay longs. Used as sentiment indicator.

---

## G

### Gene
A single parameter in a pattern's genetic representation (e.g., `rsi_min: 25`). Can mutate during evolution.

### Generation
The iteration number in evolutionary process. Higher generation = more evolved.

---

## H

### HMM (Hidden Markov Model)
Statistical model with hidden states that generate observable outputs. Used for regime detection.

### Hold Duration Bias (Trait #2)
Agent trait influencing preference for longer vs shorter trades. 0 = short-term, 1 = long-term.

---

## K

### Kelly Criterion
Formula for optimal bet sizing: `f* = (p*b - q) / b` where p = win rate, b = win/loss ratio. See [position-sizing.md](../concepts/position-sizing.md).

### Key (K)
In MacroHFT memory M=(K,E,V): the context vector used for similarity matching when retrieving memories.

---

## L

### Lookback Preference (Trait #11)
Agent trait affecting indicator period selection. 0 = short lookbacks (5-20), 1 = long lookbacks (50-200).

---

## M

### M=(K,E,V)
MacroHFT memory structure: Key (context), Event (action), Value (outcome). Maps to Episodic Memory.

### MACD
Moving Average Convergence Divergence. Momentum indicator using EMA differences.

### Mutation
Small random changes to genes/traits during reproduction. Typically ±10% per generation.

---

## N

### NVT Ratio
Network Value to Transactions. Crypto fundamental metric. High NVT = overvalued.

---

## O

### OHLCV
Open, High, Low, Close, Volume. Standard candlestick data format.

### OBV (On-Balance Volume)
Cumulative volume indicator. Rises on up days, falls on down days.

---

## P

### Pattern
Atomic trading rule with entry/exit conditions discovered through evolution. See [5-layer-hierarchy.md](../architecture/5-layer-hierarchy.md).

### Planner
Layer 5 in cognitive hierarchy. Sets long-term goals, regime strategies, capital allocation.

### Position Sizing
Determining what fraction of capital to allocate to a trade. Based on Kelly criterion with adjustments.

### Profit Factor
Total gross profit divided by total gross loss. >1 = profitable.

---

## R

### Regime
Market state classification: bull_volatile, bull_calm, bear_volatile, bear_calm, sideways. See [regime-detection.md](../concepts/regime-detection.md).

### Risk Tolerance (Trait #1)
Agent trait affecting position size willingness. 0 = conservative, 1 = aggressive.

### RSI (Relative Strength Index)
Momentum oscillator (0-100). <30 = oversold, >70 = overbought.

### Roster
The team of active trading agents. Selected based on regime affinity.

---

## S

### Semantic Memory
Aggregated statistics from many episodic memories. Pattern/regime performance summaries. See [memory-systems.md](../concepts/memory-systems.md).

### Sharpe Ratio
Risk-adjusted return: `(return - risk_free) / volatility`. Higher = better risk-adjusted performance.

### SOPR (Spent Output Profit Ratio)
Crypto on-chain metric. <1 = coins moving at loss (capitulation).

### Sortino Ratio
Like Sharpe but only penalizes downside volatility.

---

## T

### Three Pillars
Technical (40%) + Sentiment (30%) + Fundamental (30%). Multi-modal signal framework. See [three-pillars.md](../concepts/three-pillars.md).

### Tier
Pattern quality level: Tier 3 (Untested) → Tier 2 (Proven) → Tier 1 (Elite).

### Trait
One of 16 personality parameters (0-1) that define agent behavior. See [traits.md](traits.md).

### TTL (Time To Live)
How long an episodic memory is retained before expiring.

---

## V

### Value (V)
In MacroHFT memory M=(K,E,V): the outcome/reward of the action.

### VaR (Value at Risk)
Maximum expected loss at a given confidence level (e.g., 95% VaR = 2%).

---

## W

### Walk-Forward Validation
Backtesting method: train on past data, test on future data, roll forward. Prevents lookahead bias.

### WHEN-DO-BECAUSE
Wisdom rule format: WHEN <condition> DO <action> BECAUSE <reason>. See [memory-systems.md](../concepts/memory-systems.md).

### Win Rate
Percentage of trades that are profitable. Typical range: 40-60%.

### Wisdom Memory
High-level beliefs extracted from patterns in experience. WHEN-DO-BECAUSE rules. See [memory-systems.md](../concepts/memory-systems.md).

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-28 | Initial glossary |
