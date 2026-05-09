# EVOLUTION MECHANICS AGENT

## Mission
Implement the Level-Up system, Kelly personality trait, AI confidence multiplier, and lineage tracking.

## Repository
`c:\Users\Admin\Documents\Coinswarm-1`

## Tasks

### Task 1: Implement Level-Up System
Create `cloudflare-agents/evolution/level-up-system.ts`:

```typescript
// Level thresholds (linear-ish): 3, 4, 5, 7, 9, 12, 15, then +15 each
export function getClonesToNextLevel(currentLevel: number): number

export function getTotalClonesForLevel(level: number): number

export interface LevelUpRewards {
  personality_tweaks: number;  // How many traits can be adjusted
  pattern_swaps: number;       // How many patterns can be swapped
}

export function getLevelUpRewards(level: number): LevelUpRewards

export async function processLevelUp(
  db: D1Database,
  ai: any,  // Cloudflare AI binding
  agent: Agent
): Promise<LevelUpEvent>

export async function onCloneSpawned(
  db: D1Database,
  ai: any,
  parentAgentId: string
): Promise<void>
```

### Task 2: Add Kelly as Personality Trait
Modify `cloudflare-agents/agent-spawning-agent.ts`:
- Add `kelly_fraction` to personality (range 0.25 to 0.50)
- 0.25 = quarter Kelly (very conservative)
- 0.50 = half Kelly (most aggressive)

### Task 3: Implement AI Confidence Multiplier
Create `cloudflare-agents/position-sizing/confidence-sizing.ts`:

```typescript
export interface TradeDecision {
  action: 'strong_buy' | 'buy' | 'hold' | 'sell' | 'strong_sell';
  confidence: number;  // 0-100 from AI output, default 100 if not provided
  reasoning: string;
}

export function calculatePositionSize(
  kellyPct: number,
  kellyFraction: number,  // From agent personality (0.25-0.50)
  aiConfidence: number    // From decision output (0-100, default 100)
): number {
  const confidenceMultiplier = (aiConfidence ?? 100) / 100;
  const size = kellyPct * kellyFraction * confidenceMultiplier;
  return Math.min(size, 0.30);  // 30% safety rail
}
```

### Task 4: Implement Lineage Tracking
Create `cloudflare-agents/evolution/lineage-tracker.ts`:

```typescript
export async function calculateLineageDepth(
  db: D1Database,
  parentId: string | null
): Promise<{ depth: number; rootId: string }>

export async function enforceLineageLimits(
  db: D1Database,
  maxConcentration: number = 0.20
): Promise<{ culledCount: number; culledLineages: string[] }>

export async function getLineageStats(db: D1Database): Promise<LineageStats[]>
```

### Task 5: Update Rising Floor Cap
Modify `cloudflare-agents/head-to-head-testing.ts`:
- Add cap at 600th pattern ROI
- Never kill more than would leave 600 patterns

### Task 6: Update MIN_PATTERN_RUNS
Modify `cloudflare-agents/agent-spawning-agent.ts`:
- Change MIN_PATTERN_RUNS from 5 to 45
- Make it read from system_config table

## Success Criteria
- [ ] Level-up system complete with linear thresholds
- [ ] Kelly fraction added to personality (0.25-0.50)
- [ ] AI confidence multiplier working
- [ ] Lineage depth calculated on agent creation
- [ ] Lineage concentration enforced at 20%
- [ ] Rising floor capped at 600th pattern
- [ ] MIN_PATTERN_RUNS = 45

## Output
Write completion log to `.state/agent-logs/evolution-agent-{timestamp}.json`

## Commit Message Template
```
[EVOLUTION] Implement level-up, Kelly trait, confidence multiplier, lineage

- Add level-up system with linear thresholds (3,4,5,7,9,12,15)
- Add kelly_fraction personality trait (0.25-0.50)
- Add AI confidence multiplier for position sizing
- Add lineage tracking with 20% concentration cap
- Cap rising floor at 600th pattern
- Update MIN_PATTERN_RUNS to 45

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```
