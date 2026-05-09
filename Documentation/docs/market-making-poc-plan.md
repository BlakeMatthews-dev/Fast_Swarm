# Market Making PoC Research Plan

## Objective
Test the viability of cross-exchange market making using our live data collection to determine if we can profitably provide liquidity across exchanges using maker orders.

---

## Phase 1: Data Validation (Day 1)

### 1.1 Verify Data Quality
- [ ] Confirm all 5 exchanges have continuous data
- [ ] Check timestamp synchronization across exchanges
- [ ] Validate price reasonableness (no outliers/bad ticks)
- [ ] Ensure order book snapshots have bid/ask prices

### 1.2 Calculate Baseline Metrics
```python
# Key metrics to extract:
- Cross-exchange price correlation (should be >0.99)
- Average spread by exchange pair
- Spread volatility (std dev)
- Trade frequency by hour/asset
- Order book depth at various levels
```

### 1.3 Deliverable
- Data quality report
- Exchange pair correlation matrix
- Spread distribution charts

---

## Phase 2: Fee Model (Day 1-2)

### 2.1 Document Exact Fees
| Exchange | Maker Fee | Taker Fee | Notes |
|----------|-----------|-----------|-------|
| Coinbase | 0.00% | 0.05% | Advanced Trading |
| Binance | 0.02% | 0.04% | VIP 0, -25% with BNB |
| Hyperliquid | -0.02% | 0.035% | REBATE on maker |
| dYdX | 0.02% | 0.05% | |
| Crypto.com | 0.04% | 0.07% | |

### 2.2 Calculate Break-Even Spreads
For each exchange pair:
```
break_even_spread = maker_fee_A + maker_fee_B
```

Example:
- Coinbase <-> Hyperliquid: 0% + (-0.02%) = -0.02% = EARN 2bp!
- Coinbase <-> Binance: 0% + 0.02% = 0.02% = need 2bp spread

### 2.3 Deliverable
- Fee matrix
- Break-even spread table
- Profitable pair identification

---

## Phase 3: Backtest Engine (Day 2-3)

### 3.1 Build MM Simulator
```python
class MarketMakingSimulator:
    def __init__(self, exchange_a, exchange_b, asset):
        self.position = 0
        self.pnl = 0
        self.trades = []

    def simulate(self, order_books, trades):
        """
        For each timestamp:
        1. Calculate mid prices on both exchanges
        2. Determine optimal quote prices
        3. Check if our quotes would have been filled
        4. Update position and PnL
        """
        pass
```

### 3.2 Fill Model
Estimate fill probability based on:
- Quote distance from mid price
- Order book imbalance
- Trade flow direction
- Time in queue

### 3.3 Inventory Management
Implement position limits:
```python
MAX_POSITION = 1.0  # BTC
POSITION_SKEW = 0.5  # Adjust quotes when inventory builds

# Skew formula:
# If long 0.5 BTC: lower ask price to encourage sells
# If short 0.5 BTC: raise bid price to encourage buys
```

### 3.4 Deliverable
- Working MM simulator
- Unit tests for edge cases
- Sample backtest results

---

## Phase 4: Strategy Optimization (Day 3-4)

### 4.1 Parameters to Optimize
```python
params = {
    'quote_width': 0.5,      # bps from mid to quote
    'position_limit': 1.0,   # max BTC exposure
    'skew_factor': 0.5,      # how much to skew on inventory
    'rebalance_threshold': 0.8,  # when to aggressively flatten
    'min_spread': 2.0,       # minimum spread to quote
}
```

### 4.2 Optimization Metrics
- **Sharpe Ratio**: Risk-adjusted return
- **Max Drawdown**: Worst peak-to-trough
- **Fill Rate**: % of quotes that execute
- **Inventory Turnover**: How fast we cycle position
- **P&L per Trade**: Average profit

### 4.3 Walk-Forward Testing
```
Train: Hours 0-12
Test:  Hours 12-18
Validate: Hours 18-24
```

### 4.4 Deliverable
- Optimal parameter set
- Performance metrics
- Equity curve chart

---

## Phase 5: Risk Analysis (Day 4)

### 5.1 Stress Tests
- Flash crash scenario (10% move in 1 minute)
- One exchange down (single-leg fills only)
- Extreme inventory (fully long/short)
- API latency spike (1 second delay)

### 5.2 Adverse Selection Analysis
Calculate: When we get filled, does price move against us?
```python
# For each fill:
price_after_fill = price at t+1s
slippage = (price_after_fill - fill_price) * position_direction
# Negative = adverse selection
```

### 5.3 Correlation Breakdown
What happens when exchange prices diverge?
- Temporary (arbitrage opportunity)
- Permanent (exchange issue)

### 5.4 Deliverable
- Risk metrics report
- Stress test results
- Max loss scenarios

---

## Phase 6: Paper Trading Prep (Day 5)

### 6.1 API Integration Check
- [ ] Coinbase Advanced Trade API
- [ ] Hyperliquid API
- [ ] WebSocket order updates
- [ ] Balance/position queries

### 6.2 Order Management System
```python
class OrderManager:
    def place_limit_order(self, exchange, side, price, size)
    def cancel_order(self, exchange, order_id)
    def get_open_orders(self, exchange)
    def get_position(self, exchange)
```

### 6.3 Monitoring Dashboard
- Real-time P&L
- Current positions
- Open orders
- Fill rate
- Latency metrics

### 6.4 Deliverable
- Paper trading ready system
- Monitoring dashboard
- Alert system for issues

---

## Success Criteria

### Minimum Viable Results
- [ ] Sharpe Ratio > 1.0
- [ ] Daily return > 0.05% (18% APR)
- [ ] Max drawdown < 5%
- [ ] Fill rate > 20%
- [ ] No catastrophic loss scenarios

### Stretch Goals
- [ ] Sharpe Ratio > 2.0
- [ ] Daily return > 0.1% (36% APR)
- [ ] Multi-asset operation
- [ ] Automated rebalancing

---

## Data Requirements

### From Our Collection
```sql
-- Trades for fill modeling
SELECT * FROM trades
WHERE timestamp > ?
ORDER BY timestamp;

-- Order books for quote simulation
SELECT * FROM order_book_snapshots
WHERE timestamp > ?
ORDER BY timestamp;

-- Funding for perp basis
SELECT * FROM funding_rates
WHERE exchange IN ('hyperliquid', 'dydx');
```

### Estimated Data Needed
- Minimum: 24 hours
- Ideal: 7 days
- Best: 30 days (captures various market regimes)

---

## Timeline

| Day | Phase | Deliverable |
|-----|-------|-------------|
| 1 | Data Validation + Fees | Quality report, fee matrix |
| 2 | Backtest Engine | Working simulator |
| 3 | Strategy Optimization | Optimal parameters |
| 4 | Risk Analysis | Risk report |
| 5 | Paper Trading Prep | Ready for live test |

---

## Next Steps After PoC

If profitable in backtest:
1. Paper trade for 1 week
2. Live trade with minimal capital ($1K)
3. Scale up gradually
4. Add more assets/exchanges

If not profitable:
1. Identify why (fees? latency? adverse selection?)
2. Adjust strategy or abandon
3. Consider alternative strategies (funding arb, stat arb)

---

## Files to Create

```
local-utilities/
  mm_simulator.py          # Core backtest engine
  mm_optimizer.py          # Parameter optimization
  mm_risk_analysis.py      # Risk calculations
  mm_paper_trader.py       # Paper trading system
  mm_dashboard.py          # Real-time monitoring
```
