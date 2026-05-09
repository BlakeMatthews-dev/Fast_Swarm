# METRICS AGENT

## Mission
Implement the advanced fitness metrics module: Sortino Ratio, Calmar Ratio, Ulcer Index, and Max Drawdown tracking.

## Repository
`c:\Users\Admin\Documents\Coinswarm-1`

## CRITICAL: Protected Files - NEVER MODIFY
- Any file in `pyswarm/tests/unit/` that starts with `test_`
- `CLAUDE.md`
- `.state/human-notes.md` (read-only for you)

## Tasks

### Task 1: Create Advanced Metrics Module
Create `cloudflare-agents/metrics/advanced-metrics.ts` with:

```typescript
// Sortino Ratio: (Returns - Target) / StdDev(Negative Returns Only)
export function calculateSortinoRatio(
  returns: number[],
  targetReturn: number = 0,
  periodsPerYear: number = 252
): number

// Calmar Ratio: CAGR / Max Drawdown
export function calculateCalmarRatio(
  cagrPct: number,
  maxDrawdownPct: number
): number

// Ulcer Index: sqrt(sum(Drawdown%^2) / n)
export function calculateUlcerIndex(equityCurve: number[]): number

// Max Drawdown: Largest peak-to-trough decline
export function calculateMaxDrawdown(equityCurve: number[]): {
  maxDrawdownPct: number;
  peakIndex: number;
  troughIndex: number;
}

// Profit Factor: Gross Wins / Gross Losses
export function calculateProfitFactor(
  wins: number[],
  losses: number[]
): number
```

### Task 2: Add Unit Tests
Create `cloudflare-agents/metrics/advanced-metrics.test.ts` with comprehensive tests.

### Task 3: Integrate with Backtest Runner
Modify `cloudflare-agents/agent-backtest-runner.ts` to:
1. Import the new metrics module
2. Calculate all metrics after each backtest run
3. Store results in competition_runs table

## Success Criteria
- [ ] All metric functions implemented with correct formulas
- [ ] Edge cases handled (empty arrays, zero denominators)
- [ ] Unit tests pass
- [ ] Metrics integrated into backtest runner
- [ ] No TypeScript errors

## Output
Write completion log to `.state/agent-logs/metrics-agent-{timestamp}.json`

## Commit Message Template
```
[METRICS] Implement advanced fitness metrics (Sortino/Calmar/MaxDD)

- Add calculateSortinoRatio, calculateCalmarRatio, calculateUlcerIndex
- Add calculateMaxDrawdown, calculateProfitFactor
- Integrate with agent-backtest-runner.ts
- Add unit tests

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```
