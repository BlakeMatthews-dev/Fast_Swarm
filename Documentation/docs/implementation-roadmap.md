# Coinswarm Implementation Roadmap

> Full implementation plan mapping current state to each phase completion.

---

## Current State Assessment (2025-12-27)

Based on V3 codebase audit:

```
Layer 7: Collective Intelligence (Committee)           [  ] MISSING
Layer 6: Coaches/Planners (Selection Pressure)         [  ] MISSING
Layer 5: Agent Competition (Tournament)                [~~] PARTIAL (30%)
Layer 4: Agents Born (Spawning with Traits)            [OK] DONE
Layer 3: Pattern Competition (Fitness Scoring)         [OK] DONE
Layer 2: Pattern Entry (Discovery from Chaos)          [~~] PARTIAL (70%)
Layer 1: Real Market Data (OHLCV, Indicators)          [OK] DONE
```

---

## Phase 1: Pattern Discovery & Backtesting

**Status: 70% Complete**

**Target Metrics:**
- 100+ Tier 1 patterns
- Sortino > 1.5
- Calmar > 1.0
- Max Drawdown < 15%

### What's DONE

| Component | Status | Location |
|-----------|--------|----------|
| OHLCV Data Access | DONE | AssetPriceDO, V2 API |
| Technical Indicators | DONE | shared/technical-indicators.ts (40+ indicators) |
| Chaos Trade Generation | DONE | PatternDiscoveryDO |
| Pattern Storage (D1) | DONE | discovered_patterns table |
| Backtest Engine | DONE | backtest/engine.ts |
| Backtest Scheduler | DONE | BacktestSchedulerDO |
| Fitness Scoring | DONE | shared/fitness-calculator.ts |
| Tier Promotion | DONE | Selection phase (top 20% promote) |
| Pattern Pruning | DONE | prunePatterns3SD() |

### What's PARTIAL

| Component | Status | Gap |
|-----------|--------|-----|
| AI Pattern Discovery | 30% | Basic correlation only, no ML feature engineering |
| Walk-Forward Validation | 0% | Same period for train+test = overfitting risk |
| Multi-Timeframe | 50% | Tests 1h and 1d separately, no confirmation logic |

### Tasks to Complete Phase 1

```
[X] 1.1 Fitness Calculator (DONE 2025-12-16)
    - Uses Sortino (not Sharpe) - ±14 points
    - Uses Calmar - ±11 points
    - Uses Alpha - ±40 points
    - Drawdown bonus - 0-5 points
    - Expectancy - 0-30 points
    - See: shared/fitness-calculator.ts, local-utilities/fitness_calculator.py

[ ] 1.2 Walk-Forward Validation
    - Split backtest periods: 70% train, 30% test
    - Pattern must pass BOTH to promote
    - Implement in backtest-scheduler-do.ts

[ ] 1.3 Consolidate Backtest Paths
    - Currently: cron trigger vs scheduler (confusing)
    - Single source of truth for backtest orchestration

[ ] 1.4 Pattern Quality Gate
    - Minimum 100 trades across all runs
    - Minimum 3 different market regimes tested
    - No promotion until quality gate passes
    - Add hard filter: MaxDD < 15% or auto-reject

[ ] 1.5 Unified Local Database
    - Merge 24K chaos + academic patterns
    - SQLModel schema
    - Provenance tracking (origin, author, paper)
```

### Exit Criteria for Phase 1

- [ ] 100+ patterns with fitness > 80
- [ ] All Tier 1 patterns have Sortino > 1.5
- [ ] All Tier 1 patterns have Calmar > 1.0
- [ ] All Tier 1 patterns have MaxDD < 15%
- [ ] Walk-forward validation proves out-of-sample performance
- [ ] Patterns consistently beat buy-and-hold benchmark

---

## Phase 2: Agent Trading

**Status: 40% Complete**

**Target Metrics:**
- Stable agent population (20-50 agents)
- Clear trait winners emerge
- 50-100% APR in paper trading

### What's DONE

| Component | Status | Location |
|-----------|--------|----------|
| 16 Trait System | DONE | spawning/types.ts |
| Trait Inheritance | DONE | 13 independent + 3 derived |
| Agent Spawning | DONE | agent-spawner.ts |
| Pattern Assignment | DONE | 2-5 patterns per agent |
| Decision Zones | DONE | NO_TRADE / AI_ZONE / AUTO_ZONE |
| Agent Memory (Episodic) | DONE | AgentMemoryDO |
| Agent Fitness Calc | DONE | agent-fitness.ts |

### What's PARTIAL

| Component | Status | Gap |
|-----------|--------|-----|
| Agent Cloning | 20% | cloning.ts exists, not wired |
| Agent Backtesting | 50% | Works but no canonical period coordination |
| Selection Pressure | 30% | Logic exists, no full reproduction cycle |
| Agent Leaderboard | 50% | KV storage, not integrated with selection |

### What's MISSING

| Component | Gap |
|-----------|-----|
| Full Reproduction Cycle | spawn → compete → clone winners → mutate → cull losers |
| Multi-Agent Tournament | Head-to-head on same data |
| Agent-Specific Pattern Weights | Learn which patterns work for each agent |
| Paper Trading Simulation | Run agents against live-ish data stream |

### Tasks to Complete Phase 2

```
[ ] 2.1 Wire Agent Reproduction Cycle
    - spawning/agent-evolution-controller.ts is incomplete
    - Need: spawn batch → backtest all → rank → clone top 20% → mutate → cull bottom 30%
    - Store lineage (parent_id, generation)

[ ] 2.2 Multi-Agent Tournament System
    - All agents backtest same canonical periods
    - Head-to-head comparison on identical data
    - Ranking by: Sortino, Calmar, total ROI, consistency

[ ] 2.3 Trait Analysis Dashboard
    - Which traits correlate with success?
    - Visualize trait distributions of top vs bottom agents
    - Inform trait mutation strategy

[ ] 2.4 Agent-Specific Pattern Learning
    - Track which patterns work for which agent traits
    - Adjust pattern weights based on historical agent success
    - Store in semantic memory layer

[ ] 2.5 Paper Trading Mode
    - Stream recent candles (not historical)
    - Agents make real-time decisions
    - Track hypothetical P&L
    - No actual execution yet

[ ] 2.6 Position Sizing with Kelly
    - kelly-criterion.ts exists but not integrated
    - Tie position size to agent confidence + traits
    - risk_tolerance trait affects Kelly fraction
```

### Exit Criteria for Phase 2

- [ ] 20-50 agents competing simultaneously
- [ ] 5+ generations of evolution completed
- [ ] Clear trait patterns emerge (e.g., "low risk_tolerance + high win_rate_preference wins")
- [ ] Top agents consistently beat random baseline
- [ ] Paper trading shows 50-100% APR potential
- [ ] Agent lineage tracking works (can trace ancestry)

---

## Phase 3: Hivemind Committee + Coaches

**Status: 5% Complete**

**Target Metrics:**
- Committee beats best individual agent
- Lower drawdown than Phase 2
- 100-150% APR

### What's DONE

| Component | Status | Location |
|-----------|--------|----------|
| Market Intelligence | PARTIAL | intelligence/market-intelligence.ts |
| Sentiment Boost | DONE | calculateEnhancedSignal() |

### What's MISSING (Almost Everything)

| Component | Gap |
|-----------|-----|
| Committee Voting | No quorum system, no consensus rules |
| Coach/Planner System | No roster management, no coach selection pressure |
| Cognitive Hierarchy | Documented but not implemented |
| Wisdom Extraction | No "when-do-because" rules |
| Semantic Memory Rollup | Episodic exists, no consolidation to semantic |
| Self-Reflection | No agent introspection |

### Tasks to Complete Phase 3

```
[ ] 3.1 Committee Architecture
    - CommitteeDO: holds list of active agents
    - On trade signal: poll all agents, collect votes
    - Quorum rules: require 60%+ agreement to act
    - Tie-breaking: highest-fitness agent decides

[ ] 3.2 Voting Mechanism
    - Each agent votes: LONG / SHORT / ABSTAIN
    - Confidence-weighted voting (high confidence = more weight)
    - Veto power for agents with specific expertise (pattern match)

[ ] 3.3 Coach/Planner System
    - CoachDO: manages which agents are "active" vs "benched"
    - Roster size: 5-10 active agents per coach
    - Coach fitness: measured by team performance
    - Coaches under selection pressure (bad coaches replaced)

[ ] 3.4 Roster Management
    - Coaches can swap agents weekly
    - Based on: recent performance, market regime, agent traits
    - "Situational" agents: activate based on conditions

[ ] 3.5 Wisdom Extraction
    - After 50 trades: analyze episodic memory
    - Extract rules: "WHEN rsi < 30 AND btc_trend = up, DO buy, BECAUSE 70% win rate"
    - Store in wisdom_rules JSON
    - Apply rules as confidence boost in future decisions

[ ] 3.6 Semantic Memory Consolidation
    - Every 50 trades: roll up episodic → semantic
    - Semantic: pattern_affinities, regime_preferences, indicator_biases
    - Forget old episodic (7-day window)

[ ] 3.7 Memory Inheritance for Clones
    - When agent clones: child inherits parent's semantic memory
    - NOT episodic (child starts fresh experiences)
    - Wisdom rules passed down with decay factor

[ ] 3.8 Cognitive Hierarchy Routing
    - Simple signals: individual agent decides
    - Medium signals: committee votes
    - Complex/conflicting: escalate to coach for roster adjustment
    - Unknown regime: conservative default (reduce position)
```

### Exit Criteria for Phase 3

- [ ] Committee voting system operational
- [ ] Coach system managing 3+ rosters
- [ ] Coaches under selection pressure (bad ones replaced)
- [ ] Committee outperforms best individual agent by 10%+
- [ ] Lower max drawdown than Phase 2 (collective = safer)
- [ ] Wisdom rules being generated and applied
- [ ] Memory inheritance working (clones benefit from parent knowledge)

---

## Phase 4: Cross-Exchange Market Making (PARALLEL)

**Status: Research Complete, Implementation 0%**

**Target Metrics:**
- 180-270% APR
- Near-riskless spread capture

### What's DONE

| Component | Status | Location |
|-----------|--------|----------|
| Research & Validation | DONE | Live data collected 2025-12-27 |
| Fee Analysis | DONE | Maker fees: CB 0%, HL -0.02% rebate |
| Backtest Simulation | DONE | mm_simulator.py: $752/day on $100K |
| Capital Requirements | DONE | min_capital_analysis.py |
| PoC Plan | DONE | docs/market-making-poc-plan.md |

### What's MISSING

| Component | Gap |
|-----------|-----|
| Exchange API Integration | No Coinbase/Hyperliquid API connectors |
| Order Management System | No limit order placement/cancellation |
| Inventory Management | No position tracking across exchanges |
| Real-Time Execution | No WebSocket order updates |
| Risk Dashboard | No live P&L / position monitoring |

### Tasks to Complete Phase 4

```
[ ] 4.1 Exchange API Connectors
    - Coinbase Advanced Trade API
    - Hyperliquid API
    - Common interface for order operations

[ ] 4.2 Order Management System
    - place_limit_order(exchange, side, price, size)
    - cancel_order(exchange, order_id)
    - get_open_orders(exchange)
    - get_position(exchange)

[ ] 4.3 MM Strategy Engine
    - Quote calculation: mid price ± spread
    - Inventory skew: adjust quotes based on position
    - Rebalance trigger: flatten when inventory too large

[ ] 4.4 Real-Time Monitoring
    - WebSocket for order fills
    - Live P&L calculation
    - Position tracking per exchange
    - Alert on: disconnection, large loss, inventory limit

[ ] 4.5 Paper Trading Mode
    - Simulate orders against live order book
    - Track hypothetical fills
    - Validate strategy before real capital

[ ] 4.6 Go-Live Checklist
    - [ ] API credentials configured
    - [ ] Risk limits set (max position, max daily loss)
    - [ ] Circuit breakers tested
    - [ ] Monitoring dashboard operational
    - [ ] Start with minimum capital ($1-2K)
```

### Prerequisites (from other phases)

- [ ] Phase 2+ operational (proves we can manage real-time systems)
- [ ] Exchange API credentials obtained
- [ ] $10K+ capital available

---

## Phase 5: Full Autonomous System + Grand Challenge

**Status: 0% Complete**

**Target Metrics:**
- Three pillars weighted (Tech 40% + Sentiment 30% + Fundamental 30%)
- Full autonomy with circuit breakers
- Grand Challenge elite competition

### What's MISSING (Everything)

| Component | Gap |
|-----------|-----|
| Three Pillars Integration | Only technical implemented |
| Fundamental Analysis | No on-chain metrics, no TVL tracking |
| Self-Reflection | No system-wide introspection |
| Circuit Breakers | Basic exists, not comprehensive |
| Grand Challenge | No elite tournament format |
| Memory Optimizer | No cross-generation wisdom distillation |

### Tasks to Complete Phase 5

```
[ ] 5.1 Fundamental Pillar
    - On-chain metrics: active addresses, TVL, whale movements
    - Exchange flows: inflows/outflows
    - Funding rates across perp exchanges

[ ] 5.2 Sentiment Pillar Enhancement
    - Fear & Greed Index integration
    - Social sentiment (Twitter/Reddit NLP)
    - News impact scoring

[ ] 5.3 Three Pillar Weighting
    - Dynamic weights based on regime
    - Bull market: more technical
    - Uncertainty: more sentiment
    - Recovery: more fundamental

[ ] 5.4 System Self-Reflection
    - Weekly analysis: what worked/didn't
    - Auto-adjust pillar weights
    - Identify blind spots

[ ] 5.5 Comprehensive Circuit Breakers
    - Daily loss limit
    - Correlation breakdown detection
    - Volatility regime shift pause
    - Exchange anomaly detection

[ ] 5.6 Grand Challenge Tournament
    - Elite patterns compete for top slots
    - High-stakes, winner-take-all format
    - Top performers get more capital allocation

[ ] 5.7 Memory Optimizer
    - Cross-generation wisdom distillation
    - "Cultural knowledge" shared across all agents
    - Best practices codified and propagated
```

### Exit Criteria for Phase 5

- [ ] All three pillars operational and weighted
- [ ] Self-reflection adjusting system behavior
- [ ] Circuit breakers preventing catastrophic losses
- [ ] Grand Challenge producing elite performers
- [ ] System runs autonomously for 30+ days
- [ ] Consistent positive returns with acceptable drawdown

---

## Implementation Priority Matrix

### Now (Phase 1 Completion)

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| DONE | Fitness uses Sortino/Calmar/MaxDD | - | - |
| P0 | Walk-forward validation | 4h | HIGH |
| P1 | Consolidate backtest paths | 3h | MEDIUM |
| P1 | Pattern quality gate | 2h | MEDIUM |
| P2 | Unified local database | 8h | MEDIUM |

### Next (Phase 2)

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| P0 | Wire agent reproduction cycle | 8h | HIGH |
| P0 | Multi-agent tournament | 6h | HIGH |
| P1 | Trait analysis dashboard | 4h | MEDIUM |
| P1 | Paper trading mode | 6h | HIGH |
| P2 | Kelly criterion integration | 3h | MEDIUM |

### Later (Phase 3)

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| P0 | Committee voting system | 12h | HIGH |
| P0 | Coach/planner system | 10h | HIGH |
| P1 | Wisdom extraction | 8h | MEDIUM |
| P1 | Semantic memory rollup | 6h | MEDIUM |
| P2 | Memory inheritance | 4h | MEDIUM |

### Parallel (Phase 4 - When Bandwidth Allows)

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| P1 | Exchange API connectors | 12h | HIGH |
| P1 | Order management system | 8h | HIGH |
| P2 | MM strategy engine | 10h | HIGH |
| P2 | Paper trading simulation | 6h | MEDIUM |

---

## Quick Reference: What to Build Next

```
IMMEDIATE (This Week):
1. Update fitness calculator: Sortino > Sharpe, add Calmar, MaxDD filter
2. Implement walk-forward validation in backtest scheduler
3. Add pattern quality gate (100 trades, 3 regimes minimum)

NEXT SPRINT:
4. Wire agent reproduction: spawn → compete → clone → mutate → cull
5. Build multi-agent tournament on canonical periods
6. Paper trading mode for agents

FOLLOWING SPRINT:
7. Committee voting architecture
8. Coach/roster management
9. Wisdom extraction from episodic memory
```

---

*Last updated: 2025-12-27*
