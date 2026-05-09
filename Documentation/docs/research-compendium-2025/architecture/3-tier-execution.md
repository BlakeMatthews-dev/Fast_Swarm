# 3-Tier Execution Architecture

> **Strategic Intelligence → Trading Roster → Execution Layer**
>
> This document describes the hierarchical decision-making architecture derived from multi-agent trading research.

---

## Overview

The 3-tier architecture separates concerns across different time horizons and decision types:

```
┌─────────────────────────────────────────────────────────────┐
│                    TIER 1: STRATEGIC                        │
│         (Planners, Coaches, Long-term Goals)                │
│                                                             │
│   Time Horizon: Days to Weeks                               │
│   Decisions: Regime classification, roster composition,     │
│              risk allocation, strategy selection            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    TIER 2: ROSTER                           │
│         (Committee, Active Agents, Pattern Selection)       │
│                                                             │
│   Time Horizon: Hours to Days                               │
│   Decisions: Trade entry/exit signals, pattern matching,    │
│              position sizing, agent voting                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    TIER 3: EXECUTION                        │
│         (Order Management, Slippage Control, Risk Gates)    │
│                                                             │
│   Time Horizon: Seconds to Minutes                          │
│   Decisions: Order routing, execution timing, circuit       │
│              breakers, position limits                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Tier 1: Strategic Intelligence

### Purpose
Long-term decision making that sets the context for all trading activity.

### Components

| Component | Responsibility | Frequency |
|-----------|---------------|-----------|
| **Regime Classifier** | Identify market regime (bull/bear/sideways, high/low volatility) | Every 4-24 hours |
| **Roster Coach** | Select which agents/patterns are active based on regime | Daily |
| **Risk Allocator** | Set portfolio-level risk limits | Daily |
| **Strategy Planner** | Decide macro strategy (aggressive/defensive) | Weekly |

### Key Decisions

1. **Regime Classification**
   - Input: Multi-timeframe OHLCV, volatility metrics, trend indicators
   - Output: Regime label (e.g., `bull_volatile`, `bear_calm`, `sideways`)
   - Used by: Roster selection, risk limits

2. **Roster Composition**
   - Input: Agent performance by regime, current regime
   - Output: Active roster of 5-10 agents with weights
   - Related trait: `regime_affinity` scores per agent

3. **Risk Allocation**
   - Input: Account balance, recent drawdown, market conditions
   - Output: Max position size, max daily loss, max open positions

### Paper References

| Paper | Contribution | Path |
|-------|--------------|------|
| MacroHFT | Regime-aware position sizing | [papers/arxiv-2406.14537-macro-hft.md](../papers/arxiv-2406.14537-macro-hft.md) |
| MASA | Multi-agent risk parity | [papers/arxiv-2402.00515-masa.md](../papers/arxiv-2402.00515-masa.md) |
| HMM Papers | Regime detection algorithms | [concepts/regime-detection.md](../concepts/regime-detection.md) |

### Implementation Code

```python
# CONCEPTUAL: Strategic tier flow
class StrategicTier:
    """
    Tier 1: Long-term strategic decisions.

    Paper References:
    - MacroHFT (arxiv-2406.14537): Regime-aware decision making
    - MASA (arxiv-2402.00515): Multi-agent coordination
    """

    def __init__(self):
        self.regime_classifier = RegimeClassifier()
        self.roster_coach = RosterCoach()
        self.risk_allocator = RiskAllocator()

    def daily_update(self, market_data: MarketData) -> StrategicContext:
        # 1. Classify current regime
        regime = self.regime_classifier.classify(market_data)

        # 2. Select active roster based on regime
        roster = self.roster_coach.select_roster(
            regime=regime,
            available_agents=self.all_agents,
            max_agents=10
        )

        # 3. Allocate risk budget
        risk_limits = self.risk_allocator.calculate(
            account_balance=market_data.account_balance,
            recent_drawdown=market_data.drawdown_30d,
            regime_volatility=regime.volatility_level
        )

        return StrategicContext(
            regime=regime,
            active_roster=roster,
            risk_limits=risk_limits,
            valid_until=now() + timedelta(hours=24)
        )
```

---

## Tier 2: Trading Roster

### Purpose
Tactical decision making for trade entry/exit within strategic constraints.

### Components

| Component | Responsibility | Frequency |
|-----------|---------------|-----------|
| **Committee** | Aggregate agent votes into trade decisions | Per signal |
| **Pattern Matcher** | Identify entry/exit conditions | Continuous |
| **Position Sizer** | Calculate optimal position size | Per trade |
| **Agent Pool** | Individual trading agents with traits | Continuous |

### Key Decisions

1. **Trade Entry**
   - Input: Pattern signal, agent votes, current positions
   - Output: Entry decision (BUY/SELL/HOLD) with confidence
   - Quorum: Requires N/M agent agreement

2. **Position Sizing**
   - Input: Signal confidence, agent traits, risk limits
   - Output: Position size as % of portfolio
   - Method: Kelly criterion with confidence bounds

3. **Exit Timing**
   - Input: Current P&L, market conditions, exit patterns
   - Output: Exit signal with urgency level

### Paper References

| Paper | Contribution | Path |
|-------|--------------|------|
| TradingAgents | Bull/bear debate, committee voting | [papers/arxiv-2412.20138-trading-agents.md](../papers/arxiv-2412.20138-trading-agents.md) |
| Kelly Papers | Position sizing formulas | [concepts/position-sizing.md](../concepts/position-sizing.md) |
| M3T | Hierarchical pattern matching | [papers/arxiv-2212.14670-m3t.md](../papers/arxiv-2212.14670-m3t.md) |

### Committee Voting Flow

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ Agent 1  │  │ Agent 2  │  │ Agent 3  │  │ Agent 4  │  │ Agent 5  │
│ (Bull)   │  │ (Bear)   │  │ (Neutral)│  │ (Bull)   │  │ (Bear)   │
└────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
     │             │             │             │             │
     │  vote: BUY  │ vote: HOLD  │ vote: HOLD  │  vote: BUY  │ vote: SELL
     │  conf: 0.8  │  conf: 0.6  │  conf: 0.3  │  conf: 0.7  │  conf: 0.5
     │             │             │             │             │
     └─────────────┴─────────────┴─────────────┴─────────────┘
                                 │
                                 ▼
                   ┌─────────────────────────┐
                   │      COMMITTEE          │
                   │                         │
                   │  Weighted Vote:         │
                   │  BUY:  0.8 + 0.7 = 1.5  │
                   │  HOLD: 0.6 + 0.3 = 0.9  │
                   │  SELL: 0.5             │
                   │                         │
                   │  Decision: BUY          │
                   │  Confidence: 0.52       │
                   └───────────┬─────────────┘
                               │
                               ▼
                   ┌─────────────────────────┐
                   │    POSITION SIZER       │
                   │                         │
                   │  Kelly: f* = (p*b - q)/b│
                   │  Adjusted: 0.52 * f*    │
                   │  Capped: min(max, ...)  │
                   │                         │
                   │  Size: 3.2% of portfolio│
                   └─────────────────────────┘
```

---

## Tier 3: Execution Layer

### Purpose
Low-latency execution with safety guarantees.

### Components

| Component | Responsibility | Frequency |
|-----------|---------------|-----------|
| **Order Manager** | Submit/cancel/modify orders | Per order |
| **Slippage Monitor** | Track execution quality | Per fill |
| **Circuit Breaker** | Halt trading on excessive loss | Continuous |
| **Position Tracker** | Track open positions | Continuous |

### Key Decisions

1. **Order Routing**
   - Input: Trade decision, order book state
   - Output: Order type, size, limit price
   - Constraints: Max slippage tolerance

2. **Circuit Breaker Triggers**
   - Daily loss > 5%: Reduce position sizes 50%
   - Daily loss > 8%: Close all positions
   - Daily loss > 10%: Halt trading for 24h

3. **Position Limits**
   - Max single position: 20-50% (trait-dependent)
   - Max correlated exposure: 60%
   - Max leverage: 1x (no leverage by default)

### Paper References

| Paper | Contribution | Path |
|-------|--------------|------|
| Stop-Loss Papers | Circuit breaker formulas | [concepts/risk-management.md](../concepts/risk-management.md) |
| Market Microstructure | Execution algorithms | (various) |

### Safety Invariants

```python
# PRODUCTION: Execution tier safety checks
class ExecutionTier:
    """
    Tier 3: Order execution with safety guarantees.

    CRITICAL: These invariants must NEVER be violated.
    """

    MAX_DAILY_LOSS_PCT = 0.10      # 10% max daily loss
    MAX_SINGLE_POSITION_PCT = 0.50 # 50% max single position
    MAX_SLIPPAGE_BPS = 50          # 50 bps max slippage

    def execute_order(self, order: Order) -> ExecutionResult:
        # Safety checks - NEVER skip these
        if self.daily_loss_pct() >= self.MAX_DAILY_LOSS_PCT:
            return ExecutionResult(
                status='REJECTED',
                reason='DAILY_LOSS_LIMIT_EXCEEDED'
            )

        if order.size_pct > self.MAX_SINGLE_POSITION_PCT:
            return ExecutionResult(
                status='REJECTED',
                reason='POSITION_SIZE_EXCEEDED'
            )

        # Execute with slippage protection
        result = self.submit_with_slippage_check(order)

        if result.slippage_bps > self.MAX_SLIPPAGE_BPS:
            self.cancel_and_retry(order)

        return result
```

---

## Inter-Tier Communication

### Data Flow

```
Strategic → Roster:
  - regime: str
  - risk_limits: RiskLimits
  - active_agents: list[AgentID]

Roster → Execution:
  - trade_decision: Decision
  - position_size: float
  - urgency: str

Execution → Roster (feedback):
  - fill_price: float
  - slippage: float
  - execution_time: datetime

Roster → Strategic (feedback):
  - trade_pnl: float
  - agent_performance: dict[AgentID, PnL]
```

### Feedback Loops

1. **Execution → Roster**: Fill quality affects future position sizing
2. **Roster → Strategic**: Agent performance affects roster selection
3. **Strategic → All**: Regime changes propagate constraints

---

## Related Files

- [5-layer-hierarchy.md](5-layer-hierarchy.md) - Cognitive hierarchy within Tier 2
- [data-schemas.md](data-schemas.md) - Data structures for inter-tier communication
- [implementation-roadmap.md](implementation-roadmap.md) - Build order for tiers

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-28 | Initial architecture document |
