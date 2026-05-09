---
paths:
  - "**/tests/**"
  - "**/*.test.ts"
  - "**/*.spec.ts"
  - v3/cloudflare-agents/**/*.ts
---

# Evidence-Driven Development (EDD) Rules

> EDD = TDD + Economic Validation
> Every commit must pass BOTH functional tests AND soundness tests.

---

## Core Principle

Traditional TDD ensures functional correctness. EDD adds validation that behavior is:
1. **Economically rational** (not gaming test data)
2. **Behaviorally stable** (works under noise and regime shifts)
3. **Safe** (respects position limits, loss limits)
4. **Performant** (meets latency SLAs)
5. **Deterministic** (reproducible results)

---

## Seven Categories of Soundness

### 1. Determinism Tests

**Same inputs must always produce same outputs:**

```typescript
test('agent produces deterministic results', () => {
  const agent = new TrendAgent({ seed: 42 });
  const data = loadFixture('btc_2024_jan.csv');

  const run1 = simulate(agent, data);
  const run2 = simulate(agent, data);

  expect(run1.actions).toEqual(run2.actions);
  expect(run1.finalPnl).toBe(run2.finalPnl);
});
```

**Required for:** Reproducible research, debugging, compliance audits.

---

### 2. Statistical Sanity Tests

**Metrics must be within realistic bounds:**

```typescript
test('strategy sharpe is realistic', () => {
  const backtest = runBacktest(strategy, { dataset: 'oos_2024' });

  // Sharpe 0.5-3.0 is realistic; >3 suggests overfitting
  expect(backtest.sharpeRatio).toBeGreaterThanOrEqual(0.5);
  expect(backtest.sharpeRatio).toBeLessThanOrEqual(3.0);

  // Max 40% decay from training to test
  expect(backtest.sharpeRatio).toBeGreaterThanOrEqual(backtest.trainSharpe * 0.6);
});

test('drawdown is acceptable', () => {
  const backtest = runBacktest(strategy, { dataset: 'oos_2024' });

  expect(backtest.maxDrawdown).toBeLessThanOrEqual(0.20); // Max 20%
});
```

**Required for:** Avoiding overfitting, ensuring economic viability.

---

### 3. Safety Invariant Tests

**System must never violate risk limits:**

```typescript
test('position size never exceeds limit', () => {
  const backtest = runBacktest(agent, { dataset: 'stress_test' });

  for (const trade of backtest.trades) {
    expect(trade.size).toBeLessThanOrEqual(agent.maxPositionSize);
  }
});

test('daily loss never exceeds limit', () => {
  const backtest = runBacktest(agent, { dataset: 'stress_test' });
  const dailyPnl = backtest.groupByDay();

  for (const [day, pnl] of Object.entries(dailyPnl)) {
    expect(pnl).toBeGreaterThanOrEqual(-settings.maxDailyLoss);
  }
});

test('circuit breaker halts on max drawdown', () => {
  const backtest = runBacktest(agent, { dataset: 'crash_scenario' });

  if (backtest.maxDrawdown >= 0.15) {
    expect(backtest.halted).toBe(true);
    expect(backtest.haltReason).toBe('MAX_DRAWDOWN_EXCEEDED');
  }
});
```

**Required for:** Risk management, capital preservation.

---

### 4. Latency & Throughput Tests

**System must meet performance SLAs:**

```typescript
test('order placement p99 < 100ms', async () => {
  const latencies: number[] = [];

  for (let i = 0; i < 100; i++) {
    const start = performance.now();
    await client.createOrder({ ... });
    latencies.push(performance.now() - start);
  }

  const p99 = percentile(latencies, 99);
  expect(p99).toBeLessThan(100);
});

test('decision throughput >= 100/sec', () => {
  const agent = new CommitteeAgent();
  const start = performance.now();

  for (let i = 0; i < 1000; i++) {
    agent.decide(generateMarketState());
  }

  const throughput = 1000 / ((performance.now() - start) / 1000);
  expect(throughput).toBeGreaterThanOrEqual(100);
});
```

**Required for:** Real-time execution, scalability.

---

### 5. Economic Realism Tests

**Profits must not come from impossible scenarios:**

```typescript
test('no lookahead bias', () => {
  const agent = new TrendAgent();
  const pastData = loadFixture('btc_jan_1_to_15.csv');
  const futureData = loadFixture('btc_jan_16_to_31.csv');

  const decision = agent.decide(pastData);

  // Agent's state should not contain future data
  expect(agent.hasAccessTo(futureData)).toBe(false);
});

test('backtest includes realistic slippage', () => {
  const backtest = runBacktest(strategy, {
    dataset: 'oos_2024',
    slippageModel: 'historical_knn'
  });

  expect(backtest.avgSlippageBps).toBeGreaterThanOrEqual(2.0);
  expect(backtest.slippageCost).toBeGreaterThan(0);
});

test('transaction costs reduce profits', () => {
  const backtest = runBacktest(strategy, { dataset: 'oos_2024' });

  expect(backtest.totalFees).toBeGreaterThan(0);
  expect(backtest.grossPnl).toBeGreaterThan(backtest.netPnl);
});
```

**Required for:** Realistic performance expectations.

---

### 6. Memory Stability Tests

**Pattern statistics must converge, weights must not oscillate:**

```typescript
test('pattern statistics converge', () => {
  const memory = new PatternMemory();

  // Record 1000 trades with same pattern
  for (let i = 0; i < 1000; i++) {
    memory.record(simulateTrade('breakout_v1'));
  }

  const stats500 = memory.getStats('breakout_v1', { asOf: 500 });
  const stats1000 = memory.getStats('breakout_v1', { asOf: 1000 });

  // Stats should converge (low variance in recent window)
  expect(Math.abs(stats500.sharpe - stats1000.sharpe)).toBeLessThanOrEqual(0.2);
});

test('weights do not oscillate', () => {
  const memory = new EpisodicMemory();

  for (let t = 0; t < 100; t++) {
    memory.updateWeights(simulateTrade());
  }

  const weights = memory.getWeightHistory();
  const recentStd = std(weights.slice(-20));

  expect(recentStd).toBeLessThanOrEqual(0.1);
});
```

**Required for:** Learning stability, avoiding feedback loops.

---

### 7. Consensus Integrity Tests

**Quorum commits require matching votes:**

```typescript
test('quorum requires >= 3 identical votes', () => {
  const managers = [1, 2, 3].map(id => new MemoryManager({ id }));
  const proposal = { patternId: 'p1', update: { sharpe: 1.5 } };

  const votes = managers.map(mgr => mgr.vote(proposal));

  // All managers should produce identical votes
  expect(votes.every(v => v.decision === votes[0].decision)).toBe(true);
  expect(votes.every(v => v.voteHash === votes[0].voteHash)).toBe(true);

  // Commit only if >= 3 accept
  const accepts = votes.filter(v => v.decision === 'ACCEPT').length;
  if (accepts >= 3) {
    const commit = commitProposal(proposal, votes);
    expect(commit.committed).toBe(true);
  }
});

test('replay produces identical state', () => {
  const cluster1 = new MemoryCluster({ managers: 3, seed: 42 });
  const cluster2 = new MemoryCluster({ managers: 3, seed: 42 });

  const events = loadFixture('events_2024_jan.json');

  for (const event of events) {
    cluster1.process(event);
    cluster2.process(event);
  }

  expect(cluster1.stateHash()).toBe(cluster2.stateHash());
});
```

**Required for:** Distributed system correctness.

---

## Test Hierarchy

```
tests/
├── unit/           # Fast, isolated (< 1s each)
├── integration/    # Multi-component (< 10s each)
├── performance/    # Latency and throughput
├── soundness/      # Economic validation (can be slow)
│   ├── determinism/
│   ├── statistical/
│   ├── safety/
│   ├── realism/
│   └── consensus/
└── backtest/       # Full strategy backtests
```

---

## Commit Blocking Rules

A commit is **blocked** if:
- Any unit test fails
- Any integration test fails
- Any performance test exceeds SLA
- Any soundness test fails
- Backtest Sharpe < baseline - tolerance
- Coverage decreases

---

## EDD Development Loop

```
1. Define behavior test (TDD)
   ↓
2. Implement minimal logic to pass
   ↓
3. Validate against soundness metrics (EDD)
   ↓
4. Refactor / simplify
   ↓
5. Commit once BOTH functional AND soundness tests pass
```

---

## Key Metrics Bounds

| Metric | Realistic Range | Red Flag |
|--------|-----------------|----------|
| Sharpe Ratio | 0.5 - 3.0 | > 3.0 (overfitting) |
| Max Drawdown | < 20% | > 30% |
| Win Rate | 40% - 60% | > 70% (suspicious) |
| Avg Trade Duration | > 1 hour | < 1 min (overtrading) |
| Slippage | 2-10 bps | 0 (unrealistic) |
