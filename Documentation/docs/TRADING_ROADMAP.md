# Coinswarm Trading System Roadmap
## POC → Pilot → Enterprise

---

## Current State Summary

### What's Production-Ready ✅

| Layer | Components | Status |
|-------|------------|--------|
| **Data Collection** | OHLCV (43 assets), Tick-level (Coinbase), Order Book (4 exchanges), Funding rates | ✅ Complete |
| **Backtesting** | TypeScript + Python engines, 100+ indicators, slippage model | ✅ Complete |
| **Pattern Discovery** | Chaos → AI Discovery → Backtest → Selection (4-phase) | ✅ Complete |
| **Agent Evolution** | 16 traits, mutation, reproduction, pruning | ✅ Complete |
| **Risk Management** | Circuit breakers, position limits, Kelly sizing | ✅ Complete |
| **Signing Service** | Solana, EVM, CEX (4 exchanges) | ✅ Complete |
| **Storage** | D1, DO SQLite, KV, Local SQLite | ✅ Complete |
| **Tests** | 70K+ lines across unit/integration/soundness | ✅ Complete |

### What's Partially Built 🟡

| Component | Status | Gap |
|-----------|--------|-----|
| Hyperliquid | WebSocket feeds, REST partial | Need order execution |
| dYdX | WebSocket feeds | Need order execution |
| Jupiter | Quotes working | Need swap execution |
| Execution Coordinator | Framework exists | Need routing logic |

### What's Missing ⚫

| Component | Priority | Impact |
|-----------|----------|--------|
| Live order execution | CRITICAL | Can't trade without it |
| Cross-exchange arbitrage | HIGH | Major profit opportunity |
| Funding rate harvesting | HIGH | Low-risk yield |
| Market making | MEDIUM | Maker fees + spread capture |
| DEX execution | MEDIUM | Access to Solana ecosystem |

---

## Strategy Taxonomy

### 1. Directional Strategies (Pattern-Based)
```
Pattern Signal → Risk Check → Order Execution → Position Management
```
- **What exists**: Pattern discovery, backtesting, risk management
- **What's needed**: Order execution bridge

### 2. Market Making (Maker Fees + Spread)
```
Order Book Analysis → Quote Spread → Place Limit Orders → Manage Inventory
```
- **What exists**: Order book feeds, imbalance detection
- **What's needed**: Quote management, inventory risk

### 3. Funding Rate Arbitrage
```
Monitor Funding → Spot/Perp Hedge → Collect Funding → Rebalance
```
- **What exists**: Funding rate feeds (Hyperliquid, dYdX)
- **What's needed**: Delta-neutral position management

### 4. Cross-Exchange Arbitrage
```
Price Feeds (All Exchanges) → Detect Spread → Simultaneous Execution
```
- **What exists**: Multi-exchange WebSocket feeds
- **What's needed**: Atomic execution, latency optimization

### 5. DEX-CEX Arbitrage
```
Jupiter Quote → CEX Price → If Spread > Threshold → Execute Both Legs
```
- **What exists**: Jupiter quotes, CEX feeds
- **What's needed**: Solana transaction execution

---

## Phase 1: POC (2-3 Weeks)

### Goal: First Live Trade on Lowest-Fee Exchange

#### Week 1: Hyperliquid Execution

**Why Hyperliquid First:**
- 0.02% maker / 0.05% taker (10x cheaper than Coinbase)
- WebSocket already implemented
- Perpetual futures = can go long/short
- No KYC for small amounts

**Funding Path (ACH → Hyperliquid):**
```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌─────────────┐
│  ACH Bank   │───▶│   Coinbase   │───▶│  Arbitrum   │───▶│ Hyperliquid │
│   (free)    │    │  USD→USDC    │    │   ($0.50)   │    │   (free)    │
└─────────────┘    │   (free)     │    └─────────────┘    └─────────────┘
                   └──────────────┘
```

| Step | Action | Cost | Time |
|------|--------|------|------|
| 1 | ACH → Coinbase | Free | 3-5 days |
| 2 | USD → USDC (Coinbase) | Free (1:1) | Instant |
| 3 | Withdraw USDC → Arbitrum | ~$0.50 | 5-10 min |
| 4 | Deposit on Hyperliquid | ~$0.10 | 1-2 min |
| **Total** | | **~$0.60** | **3-5 days first time** |

*Note: Use Coinbase for USDC (they're a Circle partner, 1:1 conversion).
Select "Arbitrum One" network for withdrawal - NOT Ethereum mainnet ($15+ fees).*

**Tasks:**
```
1. Implement hyperliquid_trader.py
   - Order placement (market, limit)
   - Position queries
   - Order cancellation
   - Leverage setting

2. EDD tests for Hyperliquid
   tests/trading/test_hyperliquid_execution.py
   - Order validation
   - Fill handling
   - Position tracking

3. Wire to existing infrastructure
   - RiskManager integration
   - PositionManager integration
   - Audit trail

4. Paper trading mode
   - Simulate orders without execution
   - Log what WOULD have happened
```

**Deliverable:** Place a real $10 trade on Hyperliquid testnet

#### Week 2: Pattern-to-Trade Pipeline

**Tasks:**
```
1. Implement PatternEvaluator
   - Load pattern conditions
   - Evaluate against live indicators
   - Generate signals with confidence

2. Implement PatternTrader
   - Filter by confidence threshold
   - Filter by pattern fitness
   - Cooldown between signals

3. Trading Loop (Main Entry Point)
   - Subscribe to Hyperliquid WebSocket
   - Calculate indicators on each tick
   - Evaluate all active patterns
   - Route signals through RiskManager
   - Execute via HyperliquidTrader
   - Update PositionManager
```

**Deliverable:** Pattern fires → Trade executes automatically

#### Week 3: Multi-Exchange Foundation

**Tasks:**
```
1. Abstract Trader Interface
   class BaseTrader:
       def validate_order(request) -> (bool, str)
       def execute_order(request) -> OrderResult
       def get_positions() -> List[Position]
       def cancel_order(order_id) -> bool

2. Implement BinanceUSTrader (0.1% fees)
   - Signing already done
   - REST API client exists

3. Exchange Router
   - Select exchange based on:
     - Asset availability
     - Fee tier
     - Current position
     - Latency
```

**Deliverable:** Same pattern can trade on Hyperliquid OR Binance

---

## Phase 2: Pilot (4-6 Weeks)

### Goal: $1K-$10K Capital, Multiple Strategies

#### Week 4-5: Funding Rate Strategy

```python
# Funding Rate Harvester Strategy

class FundingRateHarvester:
    """
    Captures funding rates by holding delta-neutral positions.

    When funding rate > threshold:
      - If positive: Short perp, Long spot
      - If negative: Long perp, Short spot

    Expected return: 20-50% APY in volatile markets
    """

    def __init__(self, config):
        self.min_funding_rate = Decimal("0.0001")  # 0.01% / 8h = 10% APY
        self.max_position_size = Decimal("10000")  # USD
        self.rebalance_threshold = Decimal("0.02")  # 2% delta drift

    async def evaluate(self, funding_data: FundingData) -> Optional[Signal]:
        if abs(funding_data.rate) < self.min_funding_rate:
            return None

        # Positive funding = shorts pay longs
        if funding_data.rate > 0:
            return Signal(
                perp_side="short",  # Collect funding
                spot_side="long",   # Hedge delta
                size=self.calculate_size(funding_data),
            )
        else:
            return Signal(
                perp_side="long",
                spot_side="short",
                size=self.calculate_size(funding_data),
            )
```

**Components Needed:**
- Delta calculator (spot + perp combined)
- Rebalancing logic (when delta drifts)
- Funding collection tracker
- P&L attribution (funding vs price movement)

#### Week 5-6: Market Making (Maker Rebates)

```python
# Market Making Strategy

class SimpleMarketMaker:
    """
    Places limit orders on both sides of the book.
    Captures spread when both sides fill.

    Key parameters:
    - spread_bps: How wide to quote (e.g., 10 bps each side)
    - size: Order size
    - inventory_limit: Max position before hedging

    Revenue: Spread capture + maker rebates
    Risk: Inventory accumulation during trends
    """

    def __init__(self, config):
        self.spread_bps = 10  # 0.1% each side = 0.2% round-trip
        self.order_size = Decimal("0.01")  # BTC
        self.inventory_limit = Decimal("0.1")  # Max 0.1 BTC position
        self.skew_factor = Decimal("0.5")  # Skew quotes based on inventory

    def calculate_quotes(self, mid_price: Decimal, inventory: Decimal):
        # Skew quotes to reduce inventory
        skew = inventory * self.skew_factor

        bid_offset = self.spread_bps - skew  # Tighter bid if short
        ask_offset = self.spread_bps + skew  # Wider ask if short

        return {
            "bid": mid_price * (1 - bid_offset / 10000),
            "ask": mid_price * (1 + ask_offset / 10000),
            "size": self.order_size,
        }

    async def manage_orders(self, book: OrderBook):
        quotes = self.calculate_quotes(book.mid_price, self.inventory)

        # Cancel stale orders
        await self.cancel_orders_outside(quotes)

        # Place new orders if needed
        await self.place_or_update_orders(quotes)
```

**Components Needed:**
- Order book subscription (already have)
- Quote management (place/cancel/amend)
- Inventory tracking
- Fill monitoring
- Maker rebate tracking

#### Week 6: Cross-Exchange Arbitrage

```python
# Cross-Exchange Arbitrage

class CrossExchangeArbitrage:
    """
    Monitors same asset across exchanges.
    When spread exceeds threshold, execute simultaneously.

    Example:
      BTC on Binance: $50,000
      BTC on Hyperliquid: $50,100
      Spread: 0.2%

      Action: Buy Binance, Sell Hyperliquid
      Profit: ~$100 - fees
    """

    def __init__(self, config):
        self.min_spread_bps = 15  # 0.15% minimum
        self.exchanges = ["hyperliquid", "binance", "coinbase"]

    async def detect_opportunity(self, prices: Dict[str, Decimal]):
        best_bid = max(prices.items(), key=lambda x: x[1])
        best_ask = min(prices.items(), key=lambda x: x[1])

        spread_bps = (best_bid[1] - best_ask[1]) / best_ask[1] * 10000

        if spread_bps > self.min_spread_bps:
            return ArbitrageOpportunity(
                buy_exchange=best_ask[0],
                sell_exchange=best_bid[0],
                spread_bps=spread_bps,
                expected_profit=self.calculate_profit(spread_bps),
            )
        return None

    async def execute(self, opportunity: ArbitrageOpportunity):
        # CRITICAL: Execute both legs simultaneously
        buy_task = self.buy(opportunity.buy_exchange, ...)
        sell_task = self.sell(opportunity.sell_exchange, ...)

        results = await asyncio.gather(buy_task, sell_task)
        # Handle partial fills, slippage, etc.
```

**Components Needed:**
- Synchronized price feeds (already have)
- Atomic execution (both legs or neither)
- Latency measurement
- Slippage tracking
- Position reconciliation

---

## Phase 3: Enterprise (8-12 Weeks)

### Goal: $100K+ Capital, Full Automation

#### Weeks 7-8: DEX Integration

**Jupiter Execution (Solana):**
```typescript
// Complete Jupiter swap execution

class JupiterExecutor {
  async executeSwap(params: {
    inputMint: string;
    outputMint: string;
    amount: number;
    slippageBps: number;
  }): Promise<SwapResult> {
    // 1. Get quote
    const quote = await this.getQuote(params);

    // 2. Get swap transaction
    const swapTx = await this.getSwapTransaction(quote, this.wallet);

    // 3. Sign via signing service
    const signed = await this.signingService.signSolana(swapTx);

    // 4. Submit and confirm
    const signature = await this.connection.sendRawTransaction(signed);
    await this.connection.confirmTransaction(signature);

    return { signature, filledAmount: quote.outAmount };
  }
}
```

**DEX-CEX Arbitrage:**
```
Jupiter Price (BONK/USDC) < Binance Price
  → Buy BONK on Jupiter
  → Sell BONK on Binance
  → Bridge USDC back to Solana
```

#### Weeks 9-10: Advanced Market Making

**Multi-Level Quoting:**
```python
# Layered order book presence

class AdvancedMarketMaker:
    def __init__(self):
        self.levels = [
            {"distance_bps": 5, "size_pct": 0.3},   # 30% at 5 bps
            {"distance_bps": 10, "size_pct": 0.4},  # 40% at 10 bps
            {"distance_bps": 20, "size_pct": 0.3},  # 30% at 20 bps
        ]

    async def quote(self, mid_price, total_size):
        orders = []
        for level in self.levels:
            bid = mid_price * (1 - level["distance_bps"] / 10000)
            ask = mid_price * (1 + level["distance_bps"] / 10000)
            size = total_size * level["size_pct"]
            orders.extend([
                Order(side="buy", price=bid, size=size),
                Order(side="sell", price=ask, size=size),
            ])
        return orders
```

**Volatility-Adjusted Spreads:**
```python
# Widen spreads during high volatility

def calculate_spread(self, atr: Decimal, base_spread: Decimal) -> Decimal:
    # Higher ATR = wider spreads
    volatility_multiplier = 1 + (atr / self.reference_atr - 1) * 0.5
    return base_spread * volatility_multiplier
```

#### Weeks 11-12: Coaching System (Layer 6)

```python
# Coach agents manage trader agents

class Coach:
    """
    Layer 6: Selects and manages trader agents.

    Responsibilities:
    - Roster selection (which agents trade)
    - Capital allocation (how much each gets)
    - Strategy mix (pattern types per agent)
    - Performance review (retire underperformers)
    """

    def __init__(self, config):
        self.roster_size = 10  # Agents under management
        self.capital = Decimal("100000")
        self.min_fitness = Decimal("60")

    async def select_roster(self, candidates: List[Agent]) -> List[Agent]:
        # Filter by fitness
        qualified = [a for a in candidates if a.fitness >= self.min_fitness]

        # Diversify by strategy type
        by_type = self.group_by_strategy(qualified)

        # Pick top from each category
        roster = []
        for strategy_type, agents in by_type.items():
            top_n = agents[:self.per_strategy_limit]
            roster.extend(top_n)

        return roster[:self.roster_size]

    async def allocate_capital(self, roster: List[Agent]) -> Dict[str, Decimal]:
        # Kelly-weighted allocation
        total_kelly = sum(a.kelly_fraction for a in roster)

        allocations = {}
        for agent in roster:
            weight = agent.kelly_fraction / total_kelly
            allocations[agent.id] = self.capital * weight

        return allocations
```

---

## Architecture: Full System

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              LAYER 7: COMMITTEE                              │
│                     (Multi-coach consensus, cultural memory)                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                              LAYER 6: COACHES                                │
│                 (Roster selection, capital allocation, strategy mix)         │
├─────────────────────────────────────────────────────────────────────────────┤
│                             LAYER 5: AGENTS                                  │
│                    (16 traits, pattern selection, decision zones)            │
├─────────────────────────────────────────────────────────────────────────────┤
│                            LAYER 4: STRATEGIES                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Directional │  │   Market    │  │  Funding    │  │    Arbitrage        │ │
│  │  (Patterns) │  │   Making    │  │    Rate     │  │ (Cross-X, DEX-CEX)  │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
├─────────┴────────────────┴───────────────┴─────────────────────┴────────────┤
│                          LAYER 3: EXECUTION                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                      Execution Coordinator                               ││
│  │   ┌──────────────┬──────────────┬──────────────┬──────────────────────┐ ││
│  │   │  Hyperliquid │   Binance    │    dYdX      │      Jupiter         │ ││
│  │   │   (0.02%)    │   (0.10%)    │   (0.05%)    │      (0.10%)         │ ││
│  │   └──────────────┴──────────────┴──────────────┴──────────────────────┘ ││
│  └─────────────────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────────────────┤
│                           LAYER 2: RISK                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Position  │  │   Circuit   │  │    Kelly    │  │     Drawdown        │ │
│  │   Manager   │  │  Breakers   │  │   Sizing    │  │     Detection       │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
├─────────────────────────────────────────────────────────────────────────────┤
│                           LAYER 1: DATA                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │    Ticks    │  │  Order Book │  │   Funding   │  │    Intelligence     │ │
│  │  (WebSocket)│  │   (Depth)   │  │   Rates     │  │  (Sentiment/Macro)  │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow: Tick to Trade

```
1. TICK ARRIVES (WebSocket)
   └── coinbase_ws.py / hyperliquid_ws.py / binance_ws.py

2. INDICATOR CALCULATION
   └── technical-indicators.ts (RSI, MACD, BB, etc.)
   └── order_book.py (spread, imbalance, walls)
   └── cvd.py (cumulative volume delta)

3. PATTERN EVALUATION
   └── pattern-matcher.ts (check conditions)
   └── confidence-calculator.ts (signal strength)

4. RISK CHECK
   └── risk_manager.py (circuit breakers, limits)
   └── position_manager.py (exposure check)

5. EXECUTION
   └── execution-coordinator.ts (route to exchange)
   └── hyperliquid_trader.py / binance_trader.py

6. POSITION UPDATE
   └── position_manager.py (track open position)
   └── agent-memory-do.ts (record decision)

7. MONITORING
   └── evolution_dashboard.py (real-time view)
   └── audit.py (full trail)
```

---

## Implementation Priority Matrix

| Strategy | Revenue Potential | Complexity | Dependencies | Priority |
|----------|-------------------|------------|--------------|----------|
| **Directional (Patterns)** | Medium | LOW | Execution only | 1️⃣ |
| **Funding Rate** | High (20-50% APY) | MEDIUM | Perp + Spot | 2️⃣ |
| **Cross-Exchange Arb** | High | MEDIUM | Multi-exchange | 3️⃣ |
| **Market Making** | Medium | HIGH | Quote management | 4️⃣ |
| **DEX-CEX Arb** | High | HIGH | Solana + CEX | 5️⃣ |

---

## Success Metrics by Phase

### POC Success Criteria
- [ ] 1 pattern executes live trade on Hyperliquid
- [ ] Position tracked correctly
- [ ] Risk limits enforced
- [ ] Audit trail complete

### Pilot Success Criteria
- [ ] 3+ patterns trading simultaneously
- [ ] Funding rate strategy generating yield
- [ ] Cross-exchange arb detecting opportunities
- [ ] < 5% drawdown over 30 days
- [ ] All circuit breakers tested

### Enterprise Success Criteria
- [ ] 10+ agents trading autonomously
- [ ] 5 strategies running in parallel
- [ ] Coach layer allocating capital
- [ ] 99.9% uptime
- [ ] < 10% max drawdown
- [ ] Positive Sharpe > 1.5

---

## Risk Controls by Phase

| Phase | Max Capital | Max Position | Daily Loss Limit | Circuit Breaker |
|-------|-------------|--------------|------------------|-----------------|
| POC | $100 | $50 | 20% | 10% |
| Pilot | $10,000 | $2,500 | 10% | 5% |
| Enterprise | $100,000+ | $25,000 | 5% | 2% |

---

## Files to Create (POC)

```
local-utilities/
├── hyperliquid_trader.py       # Order execution
├── pattern_evaluator.py        # Live pattern matching
├── pattern_trader.py           # Signal → Trade
├── trading_loop.py             # Main entry point
├── tests/trading/
│   ├── test_hyperliquid_execution.py
│   ├── test_pattern_evaluator.py
│   └── test_trading_loop.py
```

---

## Next Step

**Start with POC Week 1: Hyperliquid Execution**

This gives us:
1. Lowest fees (0.02%/0.05%)
2. WebSocket already working
3. Perpetual futures (long/short)
4. Path to funding rate strategy
