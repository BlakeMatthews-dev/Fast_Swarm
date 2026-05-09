# Master Orchestration Plan: Evolution System Technical Requirements

**Created:** 2025-12-05
**Source:** `.state/plans/evolution-tech-requirements-v1.md`
**Total Tasks:** 47 identified tasks across 3 phases
**Estimated Duration:** 4 weeks (70+ hours of implementation)

---

## Executive Summary

This orchestration plan transforms the 47 tasks from the Evolution System Technical Requirements into a **5-wave parallel agent execution plan**. Each wave contains tasks that can be worked on simultaneously by specialized agents.

### Current State Analysis

**Already Implemented:**
- Sortino Ratio: `cloudflare-agents/metrics/advanced-metrics.ts` (lines 10-32)
- Calmar Ratio: `cloudflare-agents/metrics/advanced-metrics.ts` (lines 34-47)
- Ulcer Index: `cloudflare-agents/metrics/advanced-metrics.ts` (lines 49-66)
- Profit Factor: `cloudflare-agents/metrics/advanced-metrics.ts` (lines 107-113)
- Slippage Model: `cloudflare-agents/trading/slippage-model.ts` (complete)
- Lineage Tracking Schema: `cloudflare-agents/migrations/016-lineage-tracking.sql`
- Advanced Metrics Schema: `cloudflare-agents/migrations/013-advanced-metrics.sql`
- Circuit Breakers: `cloudflare-agents/config/circuit-breakers.ts`
- R2 Storage Binding: `wrangler.toml` (TRADE_LOGS bucket configured)

**Still Needed:**
- Kelly Criterion position sizing module
- Correlation matrix calculation
- Regime tagging system
- Token specialization metadata
- R2 agent history storage (different from TRADE_LOGS)
- Diversity metrics dashboard
- Live vs backtest divergence alerts
- Alpha decay detection
- Coach agent system
- Enhanced circuit breakers
- Unit tests for all metrics

---

## Dependency Graph (Simplified)

```
WAVE 1: Foundation/Security
  |-- Audit existing CAGR (Task 1.3)
  |-- Min pattern runs config (Task 1.2)
  |-- Profit factor integration (Task 1.1) [EXISTS - need integration]
  |-- Rising floor enhancement (Task 1.6)
  |-- Lineage depth calculation (Task 1.4) [SCHEMA EXISTS - need TypeScript]

WAVE 2: Advanced Metrics
  |-- Sortino integration (Task 2.1) [EXISTS - need integration]
  |-- Calmar integration (Task 2.2) [EXISTS - need integration]
  |-- Ulcer integration (Task 2.3) [EXISTS - need integration]
  |-- Slippage integration (Task 2.8) [EXISTS - need wider integration]
  |-- Kelly Criterion (Task 2.4) [NEW]

WAVE 3: Metadata & Safety
  |-- Token specialization (Task 2.5)
  |-- Regime tagging (Task 2.6)
  |-- Enhanced circuit breakers (Task 2.7)
  |-- Correlation matrix (Task 1.5)

WAVE 4: Infrastructure
  |-- R2 agent history storage (Task 3.1)
  |-- Diversity dashboard (Task 3.2)
  |-- Divergence alerts (Task 3.3)
  |-- Alpha decay detection (Task 3.4)

WAVE 5: Stage 4 Foundation
  |-- Coach agent system (Task 3.5)
  |-- Testing & verification
```

---

## Wave 1: Foundation (Tasks 1.1-1.4, 1.6)

**Duration:** 1 sprint (10 hours)
**Dependencies:** None
**Agents:** 4 parallel

### Agent 1A: Metrics Auditor

**Mission:** Verify and document existing metric calculations

**Files to Audit:**
- `cloudflare-agents/agent-backtest-runner.ts` (CAGR calculation lines 377-381)
- `cloudflare-agents/agent-competition.ts` (CAGR lines 186-197)
- `cloudflare-agents/metrics/advanced-metrics.ts`
- `cloudflare-agents/pattern-backtester.ts`

**Tasks:**
1. Verify CAGR is geometric: `(ending/starting)^(1/years) - 1`
2. Document all metric formulas in code comments
3. Create unit tests in `cloudflare-agents/tests/metrics.test.ts`
4. Add edge case handling (zero values, negative values, Infinity)

**Output:**
- `.state/agent-logs/metrics-auditor-{timestamp}.json`
- `cloudflare-agents/tests/metrics.test.ts` (NEW)

---

### Agent 1B: Pattern Threshold Agent

**Mission:** Implement configurable minimum pattern runs before agent assignment

**Files to Modify:**
- `cloudflare-agents/agent-spawning-agent.ts` (lines 34, 74-88)
- `cloudflare-agents/head-to-head-testing.ts` (MIN_RUNS_FOR_FLOOR)

**Current State:**
```typescript
// agent-spawning-agent.ts line 34
const MIN_PATTERN_RUNS = 5;
```

**Target State:**
```typescript
// Fetch from system_config, default 20
const minRunsResult = await db.prepare(`
  SELECT COALESCE(value, 20) as min_runs
  FROM system_config WHERE key = 'min_pattern_runs_for_agent'
`).first();
const MIN_PATTERN_RUNS = minRunsResult?.min_runs || 20;
```

**Tasks:**
1. Add `min_pattern_runs_for_agent` to system_config INSERT
2. Update `agent-spawning-agent.ts` to use config value
3. Sync with `head-to-head-testing.ts` MIN_RUNS_FOR_FLOOR constant
4. Add API endpoint to GET/SET this config value

**Output:**
- `cloudflare-agents/migrations/027-min-pattern-runs-config.sql`
- Modified `agent-spawning-agent.ts`

---

### Agent 1C: Profit Factor Integrator

**Mission:** Integrate profit factor tracking into pattern testing

**Files to Modify:**
- `cloudflare-agents/head-to-head-testing.ts`
- `cloudflare-agents/pattern-backtester.ts`

**Existing:**
- Schema exists: `migrations/013-advanced-metrics.sql` (gross_wins, gross_losses, profit_factor)
- Calculator exists: `metrics/advanced-metrics.ts` calculateProfitFactor()

**Tasks:**
1. Update `runBacktestForPattern()` to track gross wins/losses
2. Calculate profit_factor after each backtest run
3. Update discovered_patterns table with gross_wins, gross_losses
4. Add profit_factor to pattern leaderboard dashboard

**Output:**
- Modified `pattern-backtester.ts`
- Modified `dashboards/patterns.html`

---

### Agent 1D: Lineage Calculator

**Mission:** Implement lineage depth calculation in TypeScript

**Schema Exists:**
```sql
-- migrations/016-lineage-tracking.sql
ALTER TABLE trading_agents ADD COLUMN lineage_depth INTEGER DEFAULT 0;
ALTER TABLE trading_agents ADD COLUMN lineage_root_id TEXT;
ALTER TABLE trading_agents ADD COLUMN kelly_fraction REAL DEFAULT 0.35;
```

**Files to Modify:**
- `cloudflare-agents/agent-spawning-agent.ts`
- `cloudflare-agents/agent-competition.ts`

**Tasks:**
1. Create `calculateLineageDepth()` function:
```typescript
async function calculateLineageDepth(db: D1Database, parentId: string | null): Promise<{depth: number, rootId: string}> {
  if (!parentId) return { depth: 0, rootId: '' };
  let depth = 0;
  let currentId = parentId;
  let rootId = parentId;
  while (currentId && depth < 100) {
    const parent = await db.prepare(`SELECT parent_id FROM trading_agents WHERE agent_id = ?`).bind(currentId).first();
    if (!parent?.parent_id) { rootId = currentId; break; }
    currentId = parent.parent_id as string;
    depth++;
  }
  return { depth: depth + 1, rootId };
}
```
2. Call on agent spawn/clone
3. Add lineage depth to agent dashboard
4. Add MAX_LINEAGE_DEPTH config (default 10) to prevent infinite recursion

**Output:**
- `cloudflare-agents/utils/lineage-calculator.ts` (NEW)
- Modified `agent-spawning-agent.ts`
- Modified `dashboards/agents.html`

---

## Wave 2: Advanced Metrics Integration (Tasks 2.1-2.4, 2.8)

**Duration:** 1 sprint (15 hours)
**Dependencies:** Wave 1 complete
**Agents:** 5 parallel

### Agent 2A: Sortino Integration

**Mission:** Wire Sortino ratio into all backtest pipelines

**Existing:**
- Calculator: `metrics/advanced-metrics.ts` calculateSortinoRatio()
- Schema: `migrations/013-advanced-metrics.sql` (sortino_ratio column exists)

**Files to Modify:**
- `cloudflare-agents/agent-backtest-runner.ts`
- `cloudflare-agents/pattern-backtester.ts`
- `cloudflare-agents/agent-competition.ts`

**Tasks:**
1. Import calculateSortinoRatio into backtest files
2. Calculate and store after each backtest run
3. Add to fitness formula (already weighted at 0.15)
4. Add to dashboard displays

---

### Agent 2B: Calmar Integration

**Mission:** Wire Calmar ratio into fitness calculations

**Existing:**
- Calculator: `metrics/advanced-metrics.ts` calculateCalmarRatio()
- Schema: column exists

**Tasks:**
1. Import calculateCalmarRatio into backtest files
2. Store in competition_runs and discovered_patterns
3. Verify fitness formula uses it (weighted at 0.25)
4. Add to leaderboards

---

### Agent 2C: Ulcer Index Integration

**Mission:** Track Ulcer Index for all agents/patterns

**Existing:**
- Calculator: `metrics/advanced-metrics.ts` calculateUlcerIndex()
- Schema: column exists

**Tasks:**
1. Build equity curve during backtests
2. Calculate Ulcer Index from equity curve
3. Store and display in dashboards
4. Add to pattern comparison views

---

### Agent 2D: Kelly Criterion Implementor

**Mission:** Create Kelly Criterion position sizing module

**Files to Create:**
- `cloudflare-agents/position-sizing/kelly-criterion.ts` (NEW)

**Implementation:**
```typescript
export interface KellyResult {
  kellyPct: number;
  halfKellyPct: number;
  quarterKellyPct: number;
  winProbability: number;
  winLossRatio: number;
  isValid: boolean;
  reason: string;
}

export function calculateKellyCriterion(
  winRate: number,
  avgWinPct: number,
  avgLossPct: number
): KellyResult {
  if (winRate <= 0 || winRate >= 1) {
    return { kellyPct: 0, halfKellyPct: 0, quarterKellyPct: 0,
             winProbability: winRate, winLossRatio: 0,
             isValid: false, reason: 'Invalid win rate' };
  }
  if (avgLossPct <= 0) {
    return { kellyPct: 0, halfKellyPct: 0, quarterKellyPct: 0,
             winProbability: winRate, winLossRatio: Infinity,
             isValid: false, reason: 'Invalid loss average' };
  }
  const winLossRatio = avgWinPct / avgLossPct;
  const kellyPct = winRate - ((1 - winRate) / winLossRatio);
  const cappedKelly = Math.min(Math.max(kellyPct, 0), 0.25); // Cap at 25%
  return {
    kellyPct: cappedKelly * 100,
    halfKellyPct: (cappedKelly / 2) * 100,
    quarterKellyPct: (cappedKelly / 4) * 100,
    winProbability: winRate,
    winLossRatio,
    isValid: true,
    reason: 'OK'
  };
}
```

**Tasks:**
1. Create position-sizing directory
2. Implement Kelly Criterion with safety caps
3. Add to StrategyConfig interface
4. Integrate into agent-backtest-runner.ts
5. Add unit tests

**Output:**
- `cloudflare-agents/position-sizing/kelly-criterion.ts`
- `cloudflare-agents/tests/kelly.test.ts`

---

### Agent 2E: Slippage Wider Integration

**Mission:** Apply slippage model to all backtest pipelines

**Existing:**
- Model: `cloudflare-agents/trading/slippage-model.ts` (complete)
- Already imported in `pattern-backtester.ts`

**Tasks:**
1. Verify slippage applied in `agent-backtest-runner.ts`
2. Verify slippage applied in `head-to-head-testing.ts`
3. Add slippage statistics to backtest results
4. Log slippage impact on ROI

---

## Wave 3: Metadata & Safety (Tasks 1.5, 2.5-2.7)

**Duration:** 1 sprint (17 hours)
**Dependencies:** Wave 2 complete
**Agents:** 4 parallel

### Agent 3A: Token Specialization Agent

**Mission:** Track agent performance per token/timeframe

**Files to Create:**
- `cloudflare-agents/migrations/028-token-specialization.sql`
- `cloudflare-agents/token-specialization.ts`

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS agent_token_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    token TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    trades INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    win_rate REAL,
    roi_pct REAL,
    sharpe_ratio REAL,
    sortino_ratio REAL,
    calmar_ratio REAL,
    max_drawdown_pct REAL,
    profit_factor REAL,
    regime TEXT CHECK(regime IN ('bull', 'bear', 'chop', 'flat')),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(agent_id, token, timeframe, window_start)
);
CREATE INDEX idx_token_perf_agent ON agent_token_performance(agent_id);
CREATE INDEX idx_token_perf_token ON agent_token_performance(token);
CREATE INDEX idx_token_perf_regime ON agent_token_performance(regime);
```

**Tasks:**
1. Create migration
2. Update backtest runner to record per-token stats
3. Create API endpoint to query token specialization
4. Add to agent detail dashboard

---

### Agent 3B: Regime Tagger

**Mission:** Classify market regimes for all backtested periods

**Files to Create:**
- `cloudflare-agents/regime-tagger.ts`

**Implementation:**
```typescript
export type MarketRegime = 'bull' | 'bear' | 'chop' | 'flat';

export function classifyRegime(
  startPrice: number,
  endPrice: number,
  volatilityPct: number  // ATR as % of price
): MarketRegime {
  const returnPct = ((endPrice - startPrice) / startPrice) * 100;
  if (returnPct > 20) return 'bull';
  if (returnPct < -20) return 'bear';
  if (volatilityPct > 3) return 'chop';
  return 'flat';
}

export async function tagBacktestWithRegime(
  dataShard: D1Database,
  pair: string,
  startTime: number,
  endTime: number
): Promise<MarketRegime> { /* ... */ }
```

**Tasks:**
1. Implement regime classification
2. Integrate into backtest runner
3. Store regime tags with backtest results
4. Add regime filter to pattern leaderboard

---

### Agent 3C: Circuit Breaker Enhancer

**Mission:** Upgrade circuit breakers per TRD requirements

**Files to Modify:**
- `cloudflare-agents/config/circuit-breakers.ts`
- `cloudflare-agents/grand-competition-agent.ts`

**Current vs Required:**
| Parameter | Current | Required |
|-----------|---------|----------|
| Portfolio 24h | 5% | 20% |
| Single Position | N/A | 15% |
| Exchange API Failure | N/A | Hold positions |
| Consensus Timeout | 5s | No trade |

**Enhanced Config:**
```typescript
export const CIRCUIT_BREAKER_CONFIG_V2: CircuitBreakerConfig = {
    // Existing
    max_daily_loss_pct: 5,
    max_weekly_loss_pct: 10,
    max_drawdown_pct: 15,
    max_trades_per_hour: 10,
    max_trades_per_day: 50,
    max_correlated_positions: 3,
    min_confidence_to_trade: 0.6,
    max_committee_decision_time_ms: 5000,
    // NEW
    portfolio_24h_stop_pct: 20,
    single_position_stop_pct: 15,
    exchange_api_failure_action: 'hold' as const,
    consensus_timeout_action: 'no_trade' as const,
    pause_duration_hours: 24,
};
```

**Tasks:**
1. Add new fields to CircuitBreakerConfig interface
2. Implement single position stop loss
3. Implement exchange API failure handling
4. Implement consensus timeout behavior
5. Add circuit breaker dashboard panel

---

### Agent 3D: Correlation Matrix Builder

**Mission:** Calculate correlation matrix for top agents

**Files to Create:**
- `cloudflare-agents/agent-correlation-matrix.ts`
- `cloudflare-agents/migrations/029-correlation-matrix.sql`

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS agent_correlation_matrix (
    agent_a_id TEXT NOT NULL,
    agent_b_id TEXT NOT NULL,
    correlation_coefficient REAL NOT NULL,
    shared_pattern_count INTEGER DEFAULT 0,
    common_trades_pct REAL DEFAULT 0,
    calculated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (agent_a_id, agent_b_id)
);
```

**Implementation:**
```typescript
async function calculateAgentCorrelation(
  db: D1Database,
  agentA: string,
  agentB: string,
  lookbackDays: number = 30
): Promise<number> {
  // Get daily returns for both agents from competition_runs
  // Calculate Pearson correlation coefficient
  // Return -1 to +1 value
}
```

**Tasks:**
1. Create migration
2. Implement Pearson correlation calculation
3. Create scheduled job to calculate correlations for top 50 agents
4. Add correlation heatmap to swarm dashboard

---

## Wave 4: Infrastructure (Tasks 3.1-3.4)

**Duration:** 1 sprint (28 hours)
**Dependencies:** Wave 3 complete
**Agents:** 4 parallel

### Agent 4A: R2 Agent History Storage

**Mission:** Store detailed agent histories in R2 for analysis

**Configuration:**
```toml
# Add to wrangler.toml
[[r2_buckets]]
binding = "AGENT_HISTORY"
bucket_name = "coinswarm-agent-history"
```

**Files to Create:**
- `cloudflare-agents/storage/r2-agent-history.ts`

**Storage Format:**
```
/agents/{agent_id}/runs.jsonl
```

**Implementation:**
```typescript
export async function appendAgentRun(
  r2: R2Bucket,
  agentId: string,
  runData: BacktestRunRecord
): Promise<void> {
  const key = `agents/${agentId}/runs.jsonl`;
  const existing = await r2.get(key);
  const existingText = existing ? await existing.text() : '';
  const newContent = existingText + JSON.stringify(runData) + '\n';
  await r2.put(key, newContent, {
    httpMetadata: { contentType: 'application/x-ndjson' }
  });
}

export async function getAgentRunHistory(
  r2: R2Bucket,
  agentId: string,
  limit: number = 100
): Promise<BacktestRunRecord[]> {
  const key = `agents/${agentId}/runs.jsonl`;
  const obj = await r2.get(key);
  if (!obj) return [];
  const text = await obj.text();
  return text.trim().split('\n').slice(-limit).map(line => JSON.parse(line));
}
```

**Tasks:**
1. Create R2 bucket: `wrangler r2 bucket create coinswarm-agent-history`
2. Add binding to wrangler.toml
3. Implement JSONL append/read utilities
4. Wire into agent-backtest-runner.ts
5. Add retention policy (delete > 90 days old)

---

### Agent 4B: Diversity Metrics Dashboard

**Mission:** Create dashboard for swarm diversity monitoring

**Files to Create:**
- `cloudflare-agents/diversity-metrics.ts`
- `cloudflare-agents/dashboards/diversity.html`

**Metrics:**
```typescript
export interface DiversityMetrics {
  unique_personalities: number;
  personality_entropy: number;  // Higher = more diverse
  pattern_usage_gini: number;   // 0 = equal, 1 = concentrated
  top_lineages: { root_id: string; agent_count: number }[];
  trait_variance: {
    risk_tolerance: number;
    loss_aversion: number;
    holding_bias: number;
  };
  correlation_clustering: number;
}
```

**Tasks:**
1. Implement diversity calculations
2. Create diversity.html dashboard
3. Add API endpoint `/api/diversity`
4. Add alerts for low diversity (< 20% personality variance)

---

### Agent 4C: Divergence Alert System

**Mission:** Alert when live performance diverges from backtest

**Files to Create:**
- `cloudflare-agents/divergence-monitor.ts`
- `cloudflare-agents/alert-system.ts`
- `cloudflare-agents/dashboards/alerts.html`

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS divergence_alerts (
    alert_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    backtest_value REAL NOT NULL,
    live_value REAL NOT NULL,
    divergence_pct REAL NOT NULL,
    severity TEXT CHECK(severity IN ('warning', 'critical')),
    acknowledged INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

**Alert Conditions:**
- Live ROI diverges from backtest ROI by > 20%
- Live win rate diverges from backtest by > 15%
- Live Sharpe diverges from backtest by > 0.5

**Tasks:**
1. Create migration
2. Implement divergence detection
3. Create alerts dashboard
4. Add webhook/notification integration

---

### Agent 4D: Alpha Decay Detector

**Mission:** Detect patterns/agents losing their edge over time

**Files to Create:**
- `cloudflare-agents/alpha-decay-detector.ts`

**Implementation:**
```typescript
export interface AlphaDecayAnalysis {
  pattern_id: string;
  lifetime_roi_pct: number;
  rolling_30d_roi_pct: number;
  decay_ratio: number;
  days_since_positive_edge: number;
  status: 'healthy' | 'degrading' | 'decayed';
}

export function analyzeAlphaDecay(
  lifetimeRoi: number,
  rolling30dRoi: number,
  daysSincePositive: number
): 'healthy' | 'degrading' | 'decayed' {
  const decayRatio = rolling30dRoi / lifetimeRoi;
  if (decayRatio > 0.7 && daysSincePositive < 14) return 'healthy';
  if (decayRatio > 0.5 || daysSincePositive < 30) return 'degrading';
  return 'decayed';
}
```

**Tasks:**
1. Implement decay detection
2. Add to pattern evaluation pipeline
3. Create decay status column in patterns table
4. Add decay indicators to pattern dashboard

---

## Wave 5: Stage 4 Foundation & Testing (Task 3.5 + Tests)

**Duration:** 1 sprint (20+ hours)
**Dependencies:** Wave 4 complete
**Agents:** 3 parallel

### Agent 5A: Coach Agent System (Stage 4)

**Mission:** Implement coach agents that manage rosters of trading agents

**Files to Create:**
- `cloudflare-agents/coach-agent.ts`
- `cloudflare-agents/roster-manager.ts`
- `cloudflare-agents/schemas/coach-agents-schema.sql`

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS coach_agents (
    coach_id TEXT PRIMARY KEY,
    coach_name TEXT NOT NULL,
    generation INTEGER DEFAULT 1,
    parent_coach_id TEXT,
    risk_parity REAL DEFAULT 0.5,
    concentration REAL DEFAULT 0.5,
    regime_sensitivity REAL DEFAULT 0.5,
    correlation_tolerance REAL DEFAULT 0.5,
    calmar_weight REAL DEFAULT 0.3,
    sharpe_weight REAL DEFAULT 0.3,
    win_rate_weight REAL DEFAULT 0.2,
    token_affinity_weight REAL DEFAULT 0.2,
    roster_roi REAL DEFAULT 0,
    roster_sharpe REAL DEFAULT 0,
    roster_calmar REAL DEFAULT 0,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS coach_rosters (
    coach_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    allocation_pct REAL NOT NULL,
    added_at TEXT DEFAULT CURRENT_TIMESTAMP,
    removed_at TEXT,
    PRIMARY KEY (coach_id, agent_id, added_at)
);
```

**Tasks:**
1. Create schema migration
2. Implement CoachAgent class with mutable traits
3. Implement roster selection logic
4. Create coach leaderboard dashboard
5. Add coach evolution (spawn/clone/eliminate)

---

### Agent 5B: Integration Test Suite

**Mission:** Create comprehensive integration tests

**Files to Create:**
- `cloudflare-agents/tests/integration/backtest.test.ts`
- `cloudflare-agents/tests/integration/metrics.test.ts`
- `cloudflare-agents/tests/integration/evolution.test.ts`

**Tests:**
1. Full backtest pipeline with all metrics
2. Agent spawning with lineage tracking
3. Pattern competition with fitness floor
4. Circuit breaker triggers
5. Correlation matrix calculation

---

### Agent 5C: Documentation Agent

**Mission:** Update all documentation to match implementation

**Files to Update:**
- `docs/ARCHITECTURE.md`
- `docs/AGENTS.md`
- `cloudflare-agents/CHAOS_TRADING_ARCHITECTURE.md`

**Tasks:**
1. Document all new metrics
2. Document Kelly Criterion usage
3. Document circuit breaker v2
4. Document coach agent system
5. Update API endpoint documentation

---

## Execution Schedule

### Week 1: Waves 1-2 (Foundation + Metrics)
- **Day 1-2:** Wave 1 agents execute in parallel
- **Day 3-4:** Wave 2 agents execute in parallel
- **Day 5:** Integration testing for Waves 1-2

### Week 2: Wave 3 (Metadata & Safety)
- **Day 1-3:** Wave 3 agents execute in parallel
- **Day 4-5:** Integration testing, bug fixes

### Week 3: Wave 4 (Infrastructure)
- **Day 1-4:** Wave 4 agents execute in parallel
- **Day 5:** Integration testing, R2 verification

### Week 4: Wave 5 (Stage 4 + Testing)
- **Day 1-3:** Wave 5 agents execute in parallel
- **Day 4-5:** Full system testing, documentation

---

## Agent Launch Commands

### Wave 1 Launch
```bash
# Execute all Wave 1 agents in parallel
# Agent 1A: Metrics Auditor
# Agent 1B: Pattern Threshold Agent
# Agent 1C: Profit Factor Integrator
# Agent 1D: Lineage Calculator
```

### Wave 2 Launch
```bash
# Execute all Wave 2 agents in parallel after Wave 1 completion
# Agent 2A: Sortino Integration
# Agent 2B: Calmar Integration
# Agent 2C: Ulcer Index Integration
# Agent 2D: Kelly Criterion Implementor
# Agent 2E: Slippage Wider Integration
```

### Wave 3 Launch
```bash
# Execute all Wave 3 agents in parallel after Wave 2 completion
# Agent 3A: Token Specialization Agent
# Agent 3B: Regime Tagger
# Agent 3C: Circuit Breaker Enhancer
# Agent 3D: Correlation Matrix Builder
```

### Wave 4 Launch
```bash
# Execute all Wave 4 agents in parallel after Wave 3 completion
# Agent 4A: R2 Agent History Storage
# Agent 4B: Diversity Metrics Dashboard
# Agent 4C: Divergence Alert System
# Agent 4D: Alpha Decay Detector
```

### Wave 5 Launch
```bash
# Execute all Wave 5 agents in parallel after Wave 4 completion
# Agent 5A: Coach Agent System
# Agent 5B: Integration Test Suite
# Agent 5C: Documentation Agent
```

---

## Success Criteria

### Phase 1 Complete (Waves 1-2):
- [ ] All patterns show profit_factor in dashboard
- [ ] Agents only spawn from patterns with configurable min runs (default 20)
- [ ] Lineage depth visible in swarm dashboard
- [ ] Sortino, Calmar, Ulcer Index calculated for all backtests
- [ ] Kelly position sizing available as strategy option
- [ ] CAGR verified as geometric with unit tests

### Phase 2 Complete (Waves 3-4):
- [ ] Regime tags assigned to all historical periods
- [ ] Circuit breakers v2 deployed with enhanced thresholds
- [ ] Correlation matrix shown for top 50 agents
- [ ] Agent histories stored in R2
- [ ] Diversity metrics dashboard live
- [ ] Divergence alerts triggering
- [ ] Alpha decay detection running

### Phase 3 Complete (Wave 5):
- [ ] Coach agent system deployed
- [ ] Integration test suite passing
- [ ] All documentation updated

---

## Rollback Procedures

### Database Rollback
```sql
-- Each migration should have a rollback script
-- Store in cloudflare-agents/migrations/rollback/
```

### Worker Rollback
```bash
# Cloudflare maintains deployment history
wrangler rollback --version=<previous_version>
```

### Feature Flags
```typescript
// Use system_config for gradual rollout
await db.prepare(`
  INSERT OR REPLACE INTO system_config (key, value)
  VALUES ('feature_kelly_sizing', 'false')
`).run();
```

---

## Open Questions for Human Decision

1. **Minimum pattern runs:** 20 or 30 as default threshold?
2. **Kelly sizing cap:** 25% max or lower (15%)?
3. **R2 retention policy:** 90 days or longer?
4. **Coach agent count:** Start with 3 or 5 coaches?
5. **Circuit breaker thresholds:** Are 20% portfolio / 15% position acceptable?

---

## Repository Path Reference

```
c:\Users\Admin\Documents\Coinswarm-1\
├── cloudflare-agents/
│   ├── metrics/
│   │   └── advanced-metrics.ts        # Sortino, Calmar, Ulcer, Profit Factor
│   ├── trading/
│   │   └── slippage-model.ts          # Slippage calculations
│   ├── position-sizing/               # NEW: Kelly Criterion
│   ├── storage/                       # NEW: R2 utilities
│   ├── config/
│   │   └── circuit-breakers.ts        # Circuit breaker config
│   ├── migrations/
│   │   ├── 013-advanced-metrics.sql   # Existing
│   │   ├── 016-lineage-tracking.sql   # Existing
│   │   └── 027-*.sql through 030-*.sql  # NEW migrations
│   ├── dashboards/
│   │   ├── diversity.html             # NEW
│   │   └── alerts.html                # NEW
│   └── tests/                         # NEW test directory
└── .state/
    └── agent-prompts/
        └── master-orchestration-plan.md  # This file
```

---

*Document Version: 1.0*
*Last Updated: 2025-12-05*
