# FITNESS FORMULA AGENT

## Mission
Update the fitness formula to be alpha-centric with Sortino, Calmar, and MaxDD as core components.

## Repository
`c:\Users\Admin\Documents\Coinswarm-1`

## Context
The owner specified these as P0 - CRITICAL for fitness:
- Alpha (agent vs asset) - PRIMARY measure
- Sortino Ratio - rewards upside volatility
- Calmar Ratio - return per unit of max pain
- Max Drawdown - direct penalty

## Current Fitness Location
Check `cloudflare-agents/agent-competition.ts` and `cloudflare-agents/evolution-agent-simple.ts` for existing fitness calculations.

## Tasks

### Task 1: Design New Fitness Formula
```typescript
interface AlphaFitnessWeights {
  alpha_cagr_weight: 0.30,        // Did you beat the asset?
  drawdown_alpha_weight: 0.25,    // Did you protect during crashes?
  sortino_weight: 0.15,           // Upside vs downside vol
  calmar_weight: 0.15,            // Return per max pain
  win_rate_weight: 0.10,          // Consistency
  max_drawdown_penalty: 0.05,     // Absolute drawdown penalty
}
```

### Task 2: Create Fitness Module
Create `cloudflare-agents/fitness/alpha-fitness.ts`:

```typescript
export function calculateAlphaFitness(
  metrics: AgentMetrics,
  weights?: Partial<AlphaFitnessWeights>
): number

// Normalization helpers
export function normalizeMetric(value: number, min: number, max: number): number
```

### Task 3: Update Competition Logic
Modify the competition/evolution files to use the new fitness formula.

### Task 4: Add Configuration
Make weights configurable via system_config table so they can be tuned without code changes.

## Success Criteria
- [ ] New fitness formula implemented
- [ ] Alpha metrics weighted highest (30% + 25% = 55%)
- [ ] Weights are configurable
- [ ] Existing agents can be re-scored
- [ ] No breaking changes to competition flow

## Output
Write completion log to `.state/agent-logs/fitness-agent-{timestamp}.json`

## Commit Message Template
```
[FITNESS] Implement alpha-centric fitness formula

- Add AlphaFitnessWeights with configurable weights
- Alpha + Drawdown Alpha = 55% of fitness
- Add Sortino, Calmar as core components
- Make weights configurable via system_config

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```
