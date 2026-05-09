# ALPHA AGENT

## Mission
Implement alpha metrics - measuring agent performance vs the underlying asset (not absolute returns).

## Repository
`c:\Users\Admin\Documents\Coinswarm-1`

## CRITICAL: Protected Files - NEVER MODIFY
- Any file in `pyswarm/tests/unit/` that starts with `test_`
- `CLAUDE.md`

## Context
Alpha = Agent Return - Asset Return (same window)
- If SOL does +100% and agent does +120%, alpha = +20
- If SOL does -90% and agent does -3%, alpha = +87 (EXCEPTIONAL)

## Tasks

### Task 1: Create Alpha Metrics Module
Create `cloudflare-agents/metrics/alpha-metrics.ts`:

```typescript
export interface AlphaResult {
  agent_roi_pct: number;
  asset_roi_pct: number;
  alpha_roi: number;  // agent - asset

  agent_max_drawdown: number;
  asset_max_drawdown: number;
  drawdown_alpha: number;  // asset_dd - agent_dd (positive = protected)

  total_alpha: number;  // Combined score
}

export async function calculateAlphaForWindow(
  dataShard: D1Database,
  pair: string,
  startTime: number,
  endTime: number,
  agentRoi: number,
  agentMaxDrawdown: number
): Promise<AlphaResult>

export function calculateAssetPerformance(
  candles: Candle[]
): { roi: number; maxDrawdown: number }
```

### Task 2: Create SQL Migration
Create `cloudflare-agents/migrations/013-alpha-metrics.sql`:

```sql
-- Add alpha columns to competition_runs
ALTER TABLE competition_runs ADD COLUMN asset_roi_pct REAL;
ALTER TABLE competition_runs ADD COLUMN asset_max_drawdown_pct REAL;
ALTER TABLE competition_runs ADD COLUMN alpha_roi REAL;
ALTER TABLE competition_runs ADD COLUMN drawdown_alpha REAL;
```

### Task 3: Integrate with Pattern Backtester
Modify `cloudflare-agents/pattern-backtester.ts` to:
1. Fetch asset performance for the backtest window
2. Calculate alpha metrics
3. Store in results

### Task 4: Integrate with Agent Backtest Runner
Modify `cloudflare-agents/agent-backtest-runner.ts` similarly.

## Success Criteria
- [ ] Alpha calculation correct (agent - asset)
- [ ] Drawdown alpha correct (asset_dd - agent_dd)
- [ ] Migration created
- [ ] Both backtesters updated
- [ ] Results stored in database

## Output
Write completion log to `.state/agent-logs/alpha-agent-{timestamp}.json`

## Commit Message Template
```
[ALPHA] Implement alpha metrics (agent vs asset performance)

- Add alpha_roi and drawdown_alpha calculations
- Create migration 013-alpha-metrics.sql
- Integrate with pattern-backtester.ts
- Integrate with agent-backtest-runner.ts

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```
