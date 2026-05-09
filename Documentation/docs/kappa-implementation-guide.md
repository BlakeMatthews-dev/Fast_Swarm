# κ-Inspired Implementation Guide for Coinswarm

This document provides detailed implementation suggestions for closing the κ-gaps identified in the kappaTune analysis.

---

## 1. Agent Traits: Adaptive Mutation Rates

### Current State
```typescript
// cloning.ts:41 - Uniform mutation rate for ALL traits
export const DEFAULT_CLONE_CONFIG: CloneConfig = {
  mutationRate: 0.1,  // ALWAYS 10%, regardless of trait importance
  ...
};

// trait-mutation.ts:119 - Same rate applied to every trait
export function mutateTrait(original: number, mutationRate: number, seed: number): number {
  const delta = (randomValue * 2 - 1) * mutationRate;  // ±10% always
  return Math.max(0, Math.min(1, original + delta));
}
```

### Problem
- Traits that have **converged** in top performers still mutate at 10%
- Traits that are **unexplored** only mutate at 10%
- Evolution wastes budget re-exploring solved dimensions
- Risk of destroying converged optimal values

### Solution: Trait Specialization Scoring

#### Step 1: Add Trait Analysis Infrastructure

```typescript
// NEW FILE: v3/cloudflare-agents/spawning/trait-specialization.ts

import type { AgentTraits, SpawnedAgent } from './types';
import { INDEPENDENT_TRAITS } from './trait-mutation';

/**
 * Specialization analysis for a single trait
 */
export interface TraitSpecialization {
  trait: keyof AgentTraits;

  // Statistics from elite agents
  eliteMean: number;           // Average value in top performers
  eliteStdDev: number;         // Standard deviation in top performers
  eliteMin: number;
  eliteMax: number;

  // Derived metrics
  convergenceScore: number;    // 0 = high variance (explore), 1 = converged (protect)
  fitnessCorrelation: number;  // Pearson r with fitness (-1 to 1)

  // Recommended mutation rate
  recommendedMutationRate: number;  // Lower for high convergence
}

/**
 * Calculate trait specialization from a population of agents
 */
export function analyzeTraitSpecialization(
  agents: Array<{ traits: AgentTraits; fitness: number }>,
  elitePercentile: number = 0.2  // Top 20%
): Map<keyof AgentTraits, TraitSpecialization> {
  const result = new Map<keyof AgentTraits, TraitSpecialization>();

  if (agents.length < 10) {
    // Not enough data - return neutral specialization
    for (const trait of INDEPENDENT_TRAITS) {
      result.set(trait as keyof AgentTraits, {
        trait: trait as keyof AgentTraits,
        eliteMean: 0.5,
        eliteStdDev: 0.29,  // Uniform distribution std dev
        eliteMin: 0,
        eliteMax: 1,
        convergenceScore: 0,
        fitnessCorrelation: 0,
        recommendedMutationRate: 0.1,
      });
    }
    return result;
  }

  // Sort by fitness and get elite
  const sorted = [...agents].sort((a, b) => b.fitness - a.fitness);
  const eliteCount = Math.max(3, Math.floor(agents.length * elitePercentile));
  const elite = sorted.slice(0, eliteCount);

  for (const trait of INDEPENDENT_TRAITS) {
    const traitKey = trait as keyof AgentTraits;

    // Get elite trait values
    const eliteValues = elite.map(a => a.traits[traitKey] as number);
    const allValues = agents.map(a => a.traits[traitKey] as number);
    const fitnessValues = agents.map(a => a.fitness);

    // Calculate elite statistics
    const eliteMean = eliteValues.reduce((a, b) => a + b, 0) / eliteValues.length;
    const eliteVariance = eliteValues.reduce((sum, v) => sum + (v - eliteMean) ** 2, 0) / eliteValues.length;
    const eliteStdDev = Math.sqrt(eliteVariance);
    const eliteMin = Math.min(...eliteValues);
    const eliteMax = Math.max(...eliteValues);

    // Convergence score: Low std dev = high convergence
    // Uniform distribution has std dev ~0.29, fully converged = 0
    const convergenceScore = Math.max(0, Math.min(1, 1 - (eliteStdDev / 0.29)));

    // Pearson correlation with fitness
    const allMean = allValues.reduce((a, b) => a + b, 0) / allValues.length;
    const fitnessMean = fitnessValues.reduce((a, b) => a + b, 0) / fitnessValues.length;

    let numerator = 0;
    let denomX = 0;
    let denomY = 0;

    for (let i = 0; i < agents.length; i++) {
      const xDiff = allValues[i] - allMean;
      const yDiff = fitnessValues[i] - fitnessMean;
      numerator += xDiff * yDiff;
      denomX += xDiff ** 2;
      denomY += yDiff ** 2;
    }

    const fitnessCorrelation = denomX > 0 && denomY > 0
      ? numerator / (Math.sqrt(denomX) * Math.sqrt(denomY))
      : 0;

    // Recommended mutation rate:
    // Base: 0.1
    // Reduce by up to 70% for highly converged traits
    // Reduce by up to 30% for traits with strong fitness correlation
    const convergenceReduction = convergenceScore * 0.07;  // 0-7%
    const correlationReduction = Math.abs(fitnessCorrelation) * 0.03;  // 0-3%
    const recommendedMutationRate = Math.max(0.02, 0.1 - convergenceReduction - correlationReduction);

    result.set(traitKey, {
      trait: traitKey,
      eliteMean,
      eliteStdDev,
      eliteMin,
      eliteMax,
      convergenceScore,
      fitnessCorrelation,
      recommendedMutationRate,
    });
  }

  return result;
}
```

#### Step 2: Modify Cloning to Use Adaptive Rates

```typescript
// MODIFY: cloning.ts

import { TraitSpecialization, analyzeTraitSpecialization } from './trait-specialization';

export interface CloneConfig {
  mutationRate: number;  // Base rate (still used as fallback)
  memory_condensation: number;
  inheritance_decay: number;

  // NEW: Trait-specific mutation rates from specialization analysis
  traitMutationRates?: Map<keyof AgentTraits, number>;
}

// MODIFY: cloneAgent function
export function cloneAgent(
  parent: SpawnedAgent,
  _patternPool: EquippablePattern[],
  seed: number,
  config: Partial<CloneConfig> = {}
): CloneResult {
  const fullConfig = { ...DEFAULT_CLONE_CONFIG, ...config };

  // Use adaptive mutation if provided
  const mutatedTraits = fullConfig.traitMutationRates
    ? mutateTraitsAdaptively(parent.traits, fullConfig.traitMutationRates, seed)
    : mutateAllTraits(parent.traits, fullConfig.mutationRate, seed);

  // ... rest of function
}

// NEW: Adaptive mutation function
function mutateTraitsAdaptively(
  traits: AgentTraits,
  mutationRates: Map<keyof AgentTraits, number>,
  seed: number
): AgentTraits {
  const rng = seededRandom(seed);
  const result: Partial<AgentTraits> = {};

  for (const trait of INDEPENDENT_TRAITS) {
    const traitKey = trait as keyof AgentTraits;
    const rate = mutationRates.get(traitKey) ?? 0.1;  // Fallback to 10%
    const traitSeed = Math.floor(rng() * 2 ** 31);

    result[traitKey] = mutateTrait(traits[traitKey] as number, rate, traitSeed);
  }

  // Derive dependent traits...
  return result as AgentTraits;
}
```

#### Step 3: Integration Point in Evolution Controller

```typescript
// MODIFY: evolution-controller.ts - in selection phase

async function performSelection(agents: SpawnedAgent[], fitnesses: Map<string, number>) {
  // NEW: Analyze trait specialization before cloning survivors
  const agentData = agents.map(a => ({
    traits: a.traits,
    fitness: fitnesses.get(a.agent_id) ?? 0
  }));

  const specialization = analyzeTraitSpecialization(agentData);

  // Log for monitoring
  console.log('[Evolution] Trait specialization:');
  for (const [trait, spec] of specialization) {
    if (spec.convergenceScore > 0.5) {
      console.log(`  ${trait}: converged to ${spec.eliteMean.toFixed(2)} ± ${spec.eliteStdDev.toFixed(2)}, mutation rate: ${spec.recommendedMutationRate.toFixed(3)}`);
    }
  }

  // Extract mutation rates
  const traitMutationRates = new Map<keyof AgentTraits, number>();
  for (const [trait, spec] of specialization) {
    traitMutationRates.set(trait, spec.recommendedMutationRate);
  }

  // Clone survivors with adaptive rates
  for (const survivor of survivors) {
    const clone = cloneAgent(survivor, patternPool, seed, {
      traitMutationRates
    });
    // ...
  }
}
```

### Implementation Effort: Medium
- New file: ~150 lines
- Modifications: ~50 lines across 2 files
- Testing: Verify convergence detection, mutation rate adjustment

---

## 2. Pattern Evolution: Stability-Aware Selection

### Current State
```typescript
// evolution-controller.ts - Selection only considers fitness
const PROMOTE_PERCENTILE = 80;  // Top 20% promoted
const KEEP_PERCENTILE = 30;     // Bottom 30% retired

// Patterns are ranked purely by fitness score
```

### Problem
- High-fitness but **unstable** patterns get promoted (could be overfit)
- Stable patterns with moderate fitness get retired
- No reward for consistency across backtests

### Solution: Add Stability Metric to Selection

#### Step 1: Calculate Pattern Stability

```typescript
// NEW FILE: v3/cloudflare-agents/patterns/pattern-stability.ts

export interface PatternStabilityMetrics {
  pattern_id: string;

  // Raw statistics from backtest runs
  runCount: number;
  fitnessMean: number;
  fitnessStdDev: number;
  fitnessMin: number;
  fitnessMax: number;

  // Derived stability score (0-100)
  stabilityScore: number;

  // Classification
  stability: 'stable' | 'moderate' | 'unstable';

  // Recommendation
  selectionAdjustment: number;  // Add to fitness for selection
}

/**
 * Calculate stability metrics for a pattern
 */
export function calculatePatternStability(
  patternId: string,
  fitnessValues: number[]
): PatternStabilityMetrics {
  if (fitnessValues.length < 3) {
    return {
      pattern_id: patternId,
      runCount: fitnessValues.length,
      fitnessMean: fitnessValues[0] ?? 0,
      fitnessStdDev: 0,
      fitnessMin: fitnessValues[0] ?? 0,
      fitnessMax: fitnessValues[0] ?? 0,
      stabilityScore: 50,  // Neutral - not enough data
      stability: 'moderate',
      selectionAdjustment: 0,
    };
  }

  const mean = fitnessValues.reduce((a, b) => a + b, 0) / fitnessValues.length;
  const variance = fitnessValues.reduce((sum, v) => sum + (v - mean) ** 2, 0) / fitnessValues.length;
  const stdDev = Math.sqrt(variance);
  const min = Math.min(...fitnessValues);
  const max = Math.max(...fitnessValues);

  // Coefficient of variation (normalized std dev)
  const cv = mean > 0 ? stdDev / mean : 1;

  // Stability score: Low CV = high stability
  // CV of 0.1 (10%) = 90 stability
  // CV of 0.3 (30%) = 70 stability
  // CV of 0.5 (50%) = 50 stability
  // CV of 1.0 (100%) = 0 stability
  const stabilityScore = Math.max(0, Math.min(100, 100 - (cv * 100)));

  // Classification
  let stability: 'stable' | 'moderate' | 'unstable';
  if (stabilityScore >= 75) stability = 'stable';
  else if (stabilityScore >= 50) stability = 'moderate';
  else stability = 'unstable';

  // Selection adjustment:
  // Stable patterns get a bonus (+5 to +10)
  // Unstable patterns get a penalty (-5 to -10)
  let selectionAdjustment = 0;
  if (stability === 'stable') {
    selectionAdjustment = 5 + (stabilityScore - 75) / 5;  // +5 to +10
  } else if (stability === 'unstable') {
    selectionAdjustment = -5 - (50 - stabilityScore) / 10;  // -5 to -10
  }

  return {
    pattern_id: patternId,
    runCount: fitnessValues.length,
    fitnessMean: mean,
    fitnessStdDev: stdDev,
    fitnessMin: min,
    fitnessMax: max,
    stabilityScore,
    stability,
    selectionAdjustment: Math.round(selectionAdjustment * 10) / 10,
  };
}

/**
 * Calculate effective fitness for selection (fitness + stability adjustment)
 */
export function calculateEffectiveFitness(
  baseFitness: number,
  stability: PatternStabilityMetrics
): number {
  return Math.max(0, Math.min(100, baseFitness + stability.selectionAdjustment));
}
```

#### Step 2: Integrate into Pattern Selection

```typescript
// MODIFY: evolution-controller.ts

import { calculatePatternStability, calculateEffectiveFitness } from '../patterns/pattern-stability';

async function selectPatterns(patterns: Pattern[], runs: BacktestRun[]) {
  // Group runs by pattern
  const runsByPattern = new Map<string, number[]>();
  for (const run of runs) {
    const existing = runsByPattern.get(run.pattern_id) ?? [];
    existing.push(run.fitness_score);
    runsByPattern.set(run.pattern_id, existing);
  }

  // Calculate stability for each pattern
  const stabilityByPattern = new Map<string, PatternStabilityMetrics>();
  for (const [patternId, fitnessValues] of runsByPattern) {
    stabilityByPattern.set(patternId, calculatePatternStability(patternId, fitnessValues));
  }

  // Calculate effective fitness for selection
  const effectiveFitness = new Map<string, number>();
  for (const pattern of patterns) {
    const stability = stabilityByPattern.get(pattern.pattern_id);
    const baseFitness = pattern.fitness_score;

    const effective = stability
      ? calculateEffectiveFitness(baseFitness, stability)
      : baseFitness;

    effectiveFitness.set(pattern.pattern_id, effective);

    // Log stability adjustments
    if (stability && Math.abs(stability.selectionAdjustment) > 0) {
      console.log(`[Selection] ${pattern.pattern_id}: base=${baseFitness.toFixed(1)}, stability=${stability.stability}, adjustment=${stability.selectionAdjustment > 0 ? '+' : ''}${stability.selectionAdjustment.toFixed(1)}, effective=${effective.toFixed(1)}`);
    }
  }

  // Use effectiveFitness instead of raw fitness for selection
  const sortedPatterns = [...patterns].sort(
    (a, b) => (effectiveFitness.get(b.pattern_id) ?? 0) - (effectiveFitness.get(a.pattern_id) ?? 0)
  );

  // ... continue with promotion/retirement logic
}
```

#### Step 3: Store Stability in Database

```sql
-- Add to pattern table
ALTER TABLE patterns ADD COLUMN stability_score REAL DEFAULT 50;
ALTER TABLE patterns ADD COLUMN stability_category TEXT DEFAULT 'moderate';
ALTER TABLE patterns ADD COLUMN run_count INTEGER DEFAULT 0;
ALTER TABLE patterns ADD COLUMN fitness_std_dev REAL DEFAULT 0;
```

### Implementation Effort: Medium
- New file: ~100 lines
- Modifications: ~50 lines
- Migration: 1 SQL file
- Testing: Verify stability calculation, selection adjustment

---

## 3. Memory System: κ-Tiered Decay

### Current State
```typescript
// agent-memory-do.ts:355-359 - Uniform decay for all memories
private handleCleanup(): Response {
  // Delete low-relevance memories older than 30 days
  this.state.storage.sql.exec(`
    DELETE FROM memories
    WHERE relevance_score < 0.3 AND created_at < ?
  `, thirtyDaysAgo);
}
```

### Problem
- All memory types decay at the same rate
- Wisdom (philosophy) and episodic (recent trades) treated equally
- Access frequency doesn't protect important memories

### Solution: Memory-Type-Specific Decay Rates

#### Step 1: Define Memory κ Tiers

```typescript
// MODIFY: agent-memory-do.ts

/**
 * Memory type κ configuration
 * Higher κ = more specialized = slower decay
 */
const MEMORY_KAPPA_CONFIG: Record<MemoryType, {
  kappa: number;           // Relative importance (1-10)
  baseDecayPerDay: number; // Daily relevance decay rate
  minRelevance: number;    // Never decay below this
  protectedDays: number;   // Days before ANY decay starts
}> = {
  // Episodic: Recent events, high turnover
  episodic: {
    kappa: 2,
    baseDecayPerDay: 0.03,    // 3% per day
    minRelevance: 0.1,
    protectedDays: 7,         // 1 week protection
  },

  // Pattern: Learned pattern behaviors, medium stability
  pattern: {
    kappa: 5,
    baseDecayPerDay: 0.01,    // 1% per day
    minRelevance: 0.2,
    protectedDays: 30,        // 1 month protection
  },

  // Regime: Market regime observations, important context
  regime: {
    kappa: 7,
    baseDecayPerDay: 0.005,   // 0.5% per day
    minRelevance: 0.3,
    protectedDays: 90,        // 3 month protection
  },

  // Behavioral: Agent decision tendencies, core personality
  behavioral: {
    kappa: 9,
    baseDecayPerDay: 0.002,   // 0.2% per day
    minRelevance: 0.4,
    protectedDays: 180,       // 6 month protection
  },
};
```

#### Step 2: Implement κ-Aware Decay

```typescript
// MODIFY: agent-memory-do.ts

/**
 * Calculate decay rate based on memory type and access patterns
 */
function calculateMemoryDecayRate(memory: MemoryRecord): number {
  const config = MEMORY_KAPPA_CONFIG[memory.memory_type];
  if (!config) return 0.01;  // Default 1% per day

  // Check protection period
  const ageMs = Date.now() - memory.created_at;
  const ageDays = ageMs / (24 * 60 * 60 * 1000);

  if (ageDays < config.protectedDays) {
    return 0;  // No decay during protection
  }

  // Access frequency bonus: More accessed = slower decay
  // Each access reduces decay by 10%, up to 50% reduction
  const accessBonus = Math.min(0.5, memory.accessed_count * 0.1);

  // Reinforcement bonus: High relevance memories decay slower
  const relevanceBonus = memory.relevance_score * 0.2;

  // Final decay rate
  const baseDecay = config.baseDecayPerDay;
  const effectiveDecay = baseDecay * (1 - accessBonus) * (1 - relevanceBonus);

  return Math.max(0.001, effectiveDecay);  // Minimum 0.1% per day
}

/**
 * Apply κ-tiered decay to all memories
 */
private async applyKappaTieredDecay(): Promise<{ updated: number; deleted: number }> {
  const now = Date.now();
  const oneDayAgo = now - (24 * 60 * 60 * 1000);

  // Get memories that need decay (not accessed in last 24h)
  const memories = this.state.storage.sql.exec(`
    SELECT * FROM memories WHERE last_accessed_at < ?
  `, oneDayAgo).toArray() as MemoryRecord[];

  let updated = 0;
  let deleted = 0;

  for (const memory of memories) {
    const config = MEMORY_KAPPA_CONFIG[memory.memory_type];
    if (!config) continue;

    const decayRate = calculateMemoryDecayRate(memory);

    // Calculate days since last access
    const daysSinceAccess = (now - memory.last_accessed_at) / (24 * 60 * 60 * 1000);

    // Apply exponential decay
    const newRelevance = memory.relevance_score * Math.pow(1 - decayRate, daysSinceAccess);

    // Check if below minimum threshold
    if (newRelevance < config.minRelevance) {
      // Delete memory
      this.state.storage.sql.exec(`DELETE FROM memories WHERE memory_id = ?`, memory.memory_id);
      deleted++;
    } else if (newRelevance < memory.relevance_score - 0.01) {
      // Update relevance
      this.state.storage.sql.exec(`
        UPDATE memories SET relevance_score = ? WHERE memory_id = ?
      `, newRelevance, memory.memory_id);
      updated++;
    }
  }

  return { updated, deleted };
}

/**
 * Modified cleanup handler
 */
private handleCleanup(): Response {
  const now = Date.now();

  // 1. Delete expired memories (with expires_at)
  this.state.storage.sql.exec(`
    DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at < ?
  `, now);

  // 2. Apply κ-tiered decay
  const { updated, deleted } = this.applyKappaTieredDecay();

  return this.json({
    success: true,
    cleaned: { expired: 0, decayed: deleted, updated }
  });
}
```

#### Step 3: Add Access-Based Protection

```typescript
// MODIFY: handleGetRelevantMemories

private handleGetRelevantMemories(params: URLSearchParams): Response {
  // ... existing code ...

  // Update access counts AND boost relevance slightly for accessed memories
  for (const memory of memories) {
    const mem = memory as unknown as MemoryRecord;
    const config = MEMORY_KAPPA_CONFIG[mem.memory_type];

    // Small relevance boost for being accessed (capped at 1.0)
    const accessBoost = 0.01 * (config?.kappa ?? 1);
    const newRelevance = Math.min(1.0, mem.relevance_score + accessBoost);

    this.state.storage.sql.exec(`
      UPDATE memories
      SET accessed_count = accessed_count + 1,
          last_accessed_at = ?,
          relevance_score = ?
      WHERE memory_id = ?
    `, Date.now(), newRelevance, mem.memory_id);
  }

  return this.json({ memories, count: memories.length });
}
```

### Implementation Effort: Low-Medium
- Modifications: ~150 lines in agent-memory-do.ts
- No new files needed
- Testing: Verify decay rates, access protection

---

## 4. Evolution Phases: Adaptive Learning Rates

### Current State
```typescript
// Evolution phases use same parameters regardless of cycle maturity
// Phase 1: CHAOS - Generate random trades
// Phase 2: DISCOVERY - AI analyzes
// Phase 3: BACKTEST - Test patterns
// Phase 4: SELECTION - Promote/retire
```

### Problem
- Early cycles should explore broadly (high mutation, loose selection)
- Mature cycles should refine (low mutation, strict selection)
- No adaptation based on evolution stage

### Solution: Cycle-Aware Parameters

```typescript
// NEW: v3/cloudflare-agents/evolution/cycle-parameters.ts

export interface CycleParameters {
  // Selection
  promotePercentile: number;    // Top X% promoted
  retirePercentile: number;     // Bottom X% retired

  // Mutation
  baseMutationRate: number;     // For trait mutation
  patternMutationRate: number;  // For pattern parameter variation

  // Exploration
  chaosTradeCount: number;      // Trades per chaos phase
  diversityBonus: number;       // Bonus for novel patterns

  // Thresholds
  minFitnessToSurvive: number;  // Absolute minimum
}

/**
 * Calculate parameters based on evolution maturity
 */
export function calculateCycleParameters(
  cycleNumber: number,
  totalPatterns: number,
  avgFitness: number
): CycleParameters {
  // Maturity factor: 0 = brand new, 1 = mature
  // Saturates around cycle 50
  const maturity = 1 - Math.exp(-cycleNumber / 20);

  // Coverage factor: How well have we explored the space?
  // More patterns = more coverage
  const coverage = Math.min(1, totalPatterns / 1000);

  // Performance factor: High avg fitness = less exploration needed
  const performance = Math.min(1, avgFitness / 70);

  // Combined exploration need: High early, low when mature/covered/performing
  const explorationNeed = Math.max(0, 1 - (maturity + coverage + performance) / 3);

  return {
    // Selection: Stricter as we mature
    promotePercentile: 80 + (maturity * 10),      // 80% → 90%
    retirePercentile: 30 - (maturity * 10),       // 30% → 20%

    // Mutation: Lower as we converge
    baseMutationRate: 0.10 - (maturity * 0.05),   // 10% → 5%
    patternMutationRate: 0.15 - (maturity * 0.08), // 15% → 7%

    // Exploration: More chaos early
    chaosTradeCount: Math.round(900 + explorationNeed * 600),  // 900 → 1500
    diversityBonus: explorationNeed * 10,          // 0 → 10 pts

    // Thresholds: Stricter as we mature
    minFitnessToSurvive: 30 + (maturity * 10),    // 30 → 40
  };
}

/**
 * Log cycle parameters for monitoring
 */
export function logCycleParameters(
  cycleNumber: number,
  params: CycleParameters
): void {
  console.log(`[Evolution] Cycle ${cycleNumber} parameters:`);
  console.log(`  Selection: promote top ${100 - params.promotePercentile}%, retire bottom ${params.retirePercentile}%`);
  console.log(`  Mutation: traits ${(params.baseMutationRate * 100).toFixed(1)}%, patterns ${(params.patternMutationRate * 100).toFixed(1)}%`);
  console.log(`  Exploration: ${params.chaosTradeCount} chaos trades, diversity bonus ${params.diversityBonus.toFixed(1)}`);
  console.log(`  Minimum fitness: ${params.minFitnessToSurvive}`);
}
```

#### Integration into Evolution Controller

```typescript
// MODIFY: evolution-controller.ts

import { calculateCycleParameters, logCycleParameters } from './cycle-parameters';

async function runEvolutionCycle() {
  // Get current state
  const cycleNumber = await this.getCycleNumber();
  const patterns = await this.getAllPatterns();
  const avgFitness = patterns.reduce((sum, p) => sum + p.fitness_score, 0) / patterns.length;

  // Calculate adaptive parameters
  const params = calculateCycleParameters(cycleNumber, patterns.length, avgFitness);
  logCycleParameters(cycleNumber, params);

  // Phase 1: CHAOS with adaptive trade count
  const chaosTrades = await this.generateChaosTrades(params.chaosTradeCount);

  // Phase 2: DISCOVERY (unchanged)
  const discoveries = await this.discoverPatterns(chaosTrades);

  // Phase 3: BACKTEST (unchanged)
  const results = await this.backtestPatterns(discoveries);

  // Phase 4: SELECTION with adaptive thresholds
  await this.selectPatterns(results, {
    promotePercentile: params.promotePercentile,
    retirePercentile: params.retirePercentile,
    minFitness: params.minFitnessToSurvive,
    diversityBonus: params.diversityBonus,
  });

  // Cloning with adaptive mutation
  await this.cloneSurvivors({
    mutationRate: params.baseMutationRate,
  });
}
```

### Implementation Effort: Low
- New file: ~80 lines
- Modifications: ~30 lines
- Testing: Verify parameter progression across cycles

---

## 5. Fitness Calculation: Leverage Existing Signed Metrics

### Current State
The fitness calculation already has **proto-κ properties**:
- **Alpha**: Measures specialization vs benchmark (negative = "wrong" specialization)
- **Sortino**: Measures downside risk specialization
- **Calmar**: Measures drawdown-adjusted specialization

### Problem
This is actually well-designed! The gap is:
- No explicit **stability component** in fitness
- No **regime-specific** fitness adjustment

### Solution: Add Stability Component

```typescript
// MODIFY: shared/fitness-calculator.ts

// Update METRIC_WEIGHTS to include stability
export const METRIC_WEIGHTS = {
  alpha: 35,       // Reduced from 40
  sortino: 14,
  calmar: 11,
  expectancy: 28,  // Reduced from 30
  drawdown: 5,
  stability: 7,    // NEW: Reward consistency
} as const;

/**
 * Calculate stability contribution to fitness
 *
 * Based on coefficient of variation of per-trade returns
 */
export function calculateStabilityContribution(
  tradeReturns: number[]
): number {
  if (tradeReturns.length < 5) {
    return 3.5;  // Neutral contribution if not enough trades
  }

  const mean = tradeReturns.reduce((a, b) => a + b, 0) / tradeReturns.length;
  const variance = tradeReturns.reduce((sum, v) => sum + (v - mean) ** 2, 0) / tradeReturns.length;
  const stdDev = Math.sqrt(variance);

  // Coefficient of variation
  const cv = Math.abs(mean) > 0.001 ? stdDev / Math.abs(mean) : 1;

  // Score: Low CV = high stability = high score
  // CV of 0.5 = 7 points (max)
  // CV of 1.0 = 3.5 points (neutral)
  // CV of 2.0 = 0 points (min)
  const score = Math.max(0, Math.min(7, 7 * (1 - cv / 2)));

  return score;
}

// Update calculateBoundedFitness to include stability
export function calculateBoundedFitness(
  metrics: FitnessInput,
  tradeReturns?: number[]
): number {
  // ... existing contributions ...

  // NEW: Stability contribution
  const stabilityContribution = tradeReturns
    ? calculateStabilityContribution(tradeReturns)
    : 3.5;  // Neutral if no trade data

  const total =
    alphaContribution +
    sortinoContribution +
    calmarContribution +
    expectancyContribution +
    drawdownContribution +
    stabilityContribution;  // NEW

  // ... rest of function
}
```

### Implementation Effort: Low
- Modifications: ~40 lines in fitness-calculator.ts
- Update tests for new weight distribution

---

## 6. Market Regimes: Regime-Aware Pattern Activation

### Current State
```typescript
// regime-tagger.ts - Only used AFTER decisions for learning
// Patterns have no regime-specific fitness tracking
```

### Problem
- Patterns are evaluated with **global** fitness
- A pattern that's excellent in bull markets might be terrible in bear markets
- No regime-based pattern selection

### Solution: Regime-Specific Pattern Performance

#### Step 1: Track Performance by Regime

```typescript
// NEW: v3/cloudflare-agents/patterns/regime-performance.ts

import type { MarketRegime } from '../regime/regime-tagger';

export interface RegimePerformance {
  pattern_id: string;
  regime: MarketRegime;

  // Performance in this regime
  runCount: number;
  avgFitness: number;
  avgAlpha: number;
  winRate: number;

  // Confidence in this regime assessment
  confidence: number;  // 0-1 based on sample size
}

export interface PatternRegimeProfile {
  pattern_id: string;

  // Performance by regime
  byRegime: Map<MarketRegime, RegimePerformance>;

  // Derived insights
  bestRegimes: MarketRegime[];       // Where pattern shines
  worstRegimes: MarketRegime[];      // Where pattern struggles
  isRegimeSpecialist: boolean;       // True if performance varies significantly
  isRegimeGeneralist: boolean;       // True if consistent across regimes
}

/**
 * Calculate regime-specific performance profile
 */
export function calculateRegimeProfile(
  patternId: string,
  runs: Array<{
    regime: MarketRegime;
    fitness: number;
    alpha: number;
    winRate: number;
  }>
): PatternRegimeProfile {
  const byRegime = new Map<MarketRegime, RegimePerformance>();

  // Group runs by regime
  const regimeGroups = new Map<MarketRegime, typeof runs>();
  for (const run of runs) {
    const existing = regimeGroups.get(run.regime) ?? [];
    existing.push(run);
    regimeGroups.set(run.regime, existing);
  }

  // Calculate stats for each regime
  for (const [regime, regimeRuns] of regimeGroups) {
    const avgFitness = regimeRuns.reduce((sum, r) => sum + r.fitness, 0) / regimeRuns.length;
    const avgAlpha = regimeRuns.reduce((sum, r) => sum + r.alpha, 0) / regimeRuns.length;
    const avgWinRate = regimeRuns.reduce((sum, r) => sum + r.winRate, 0) / regimeRuns.length;

    // Confidence increases with sample size
    const confidence = Math.min(1, regimeRuns.length / 10);

    byRegime.set(regime, {
      pattern_id: patternId,
      regime,
      runCount: regimeRuns.length,
      avgFitness,
      avgAlpha,
      winRate: avgWinRate,
      confidence,
    });
  }

  // Determine best/worst regimes
  const sorted = [...byRegime.entries()].sort((a, b) => b[1].avgFitness - a[1].avgFitness);
  const bestRegimes = sorted.filter(([_, p]) => p.avgFitness > 60 && p.confidence > 0.5).map(([r]) => r);
  const worstRegimes = sorted.filter(([_, p]) => p.avgFitness < 40 && p.confidence > 0.5).map(([r]) => r);

  // Check if specialist or generalist
  const performances = [...byRegime.values()].filter(p => p.confidence > 0.5);
  const fitnessValues = performances.map(p => p.avgFitness);
  const mean = fitnessValues.reduce((a, b) => a + b, 0) / fitnessValues.length;
  const variance = fitnessValues.reduce((sum, v) => sum + (v - mean) ** 2, 0) / fitnessValues.length;
  const cv = Math.sqrt(variance) / mean;

  const isRegimeSpecialist = cv > 0.2;  // >20% variation across regimes
  const isRegimeGeneralist = cv < 0.1 && mean > 50;  // Consistent AND good

  return {
    pattern_id: patternId,
    byRegime,
    bestRegimes,
    worstRegimes,
    isRegimeSpecialist,
    isRegimeGeneralist,
  };
}

/**
 * Get recommended pattern weight for current regime
 */
export function getRegimeAdjustedWeight(
  profile: PatternRegimeProfile,
  currentRegime: MarketRegime,
  baseWeight: number
): number {
  const regimePerf = profile.byRegime.get(currentRegime);

  if (!regimePerf || regimePerf.confidence < 0.3) {
    return baseWeight;  // Not enough data
  }

  // Adjust weight based on regime-specific performance
  // Good in this regime: boost weight
  // Bad in this regime: reduce weight
  const regimeFitness = regimePerf.avgFitness;

  if (regimeFitness > 70) {
    return baseWeight * 1.3;  // +30% weight
  } else if (regimeFitness > 55) {
    return baseWeight * 1.1;  // +10% weight
  } else if (regimeFitness < 40) {
    return baseWeight * 0.5;  // -50% weight
  } else if (regimeFitness < 50) {
    return baseWeight * 0.8;  // -20% weight
  }

  return baseWeight;
}
```

#### Step 2: Store Regime Performance in Database

```sql
-- New table for regime-specific pattern performance
CREATE TABLE IF NOT EXISTS pattern_regime_performance (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pattern_id TEXT NOT NULL,
  regime TEXT NOT NULL,
  run_count INTEGER DEFAULT 0,
  avg_fitness REAL DEFAULT 0,
  avg_alpha REAL DEFAULT 0,
  win_rate REAL DEFAULT 0,
  confidence REAL DEFAULT 0,
  updated_at INTEGER NOT NULL,

  UNIQUE(pattern_id, regime)
);

CREATE INDEX idx_regime_perf_pattern ON pattern_regime_performance(pattern_id);
CREATE INDEX idx_regime_perf_regime ON pattern_regime_performance(regime);
```

#### Step 3: Integrate with Agent Pattern Selection

```typescript
// MODIFY: agent-do.ts - selectPatternsForTrade

async selectPatternsForTrade(currentRegime: MarketRegime): Promise<PatternWeight[]> {
  const baseWeights = this.pattern_weights;

  // Get regime profiles for our patterns
  const profiles = await this.getPatternRegimeProfiles(this.pattern_ids);

  // Adjust weights based on regime
  const adjustedWeights: PatternWeight[] = [];
  let totalWeight = 0;

  for (const [patternId, baseWeight] of Object.entries(baseWeights)) {
    const profile = profiles.get(patternId);
    const adjustedWeight = profile
      ? getRegimeAdjustedWeight(profile, currentRegime, baseWeight)
      : baseWeight;

    adjustedWeights.push({ pattern_id: patternId, weight: adjustedWeight });
    totalWeight += adjustedWeight;
  }

  // Normalize to sum to 1.0
  for (const pw of adjustedWeights) {
    pw.weight = pw.weight / totalWeight;
  }

  return adjustedWeights;
}
```

### Implementation Effort: Medium-High
- New file: ~150 lines
- New migration: regime_performance table
- Modifications: Pattern selection, backtest storage
- Testing: Verify regime tracking, weight adjustment

---

## 7. Intelligence Signals: Historical Accuracy Weighting

### Current State
```typescript
// agent-do.ts:680-760 - Fixed weights for intelligence sources
const SENTIMENT_WEIGHT = 0.1;  // Always 10%
const MACRO_WEIGHT = 0.05;     // Always 5%
```

### Problem
- No tracking of whether intelligence signals were accurate
- All signals treated equally regardless of historical performance

### Solution: Track and Use Signal Accuracy

```typescript
// NEW: v3/cloudflare-agents/intelligence/signal-accuracy.ts

export interface SignalAccuracyRecord {
  signalType: string;          // 'fear_greed', 'reddit', 'fed_regime', etc.
  signalValue: string | number; // What the signal said
  prediction: 'bullish' | 'bearish' | 'neutral';
  outcome: 'correct' | 'incorrect' | 'neutral';
  timestamp: number;
}

export interface SignalAccuracyStats {
  signalType: string;
  totalPredictions: number;
  correctPredictions: number;
  accuracy: number;            // 0-1
  confidenceInterval: number;  // Based on sample size
  recommendedWeight: number;   // Accuracy-adjusted weight
}

/**
 * Calculate accuracy-adjusted weights for intelligence signals
 */
export function calculateSignalWeights(
  stats: Map<string, SignalAccuracyStats>,
  baseWeights: Record<string, number>
): Record<string, number> {
  const adjustedWeights: Record<string, number> = {};

  for (const [signal, baseWeight] of Object.entries(baseWeights)) {
    const accuracy = stats.get(signal);

    if (!accuracy || accuracy.totalPredictions < 20) {
      // Not enough data - use base weight
      adjustedWeights[signal] = baseWeight;
      continue;
    }

    // Adjust weight based on accuracy
    // 50% accuracy = 0.5x weight (random, useless)
    // 60% accuracy = 1.0x weight (baseline)
    // 70% accuracy = 1.5x weight (good signal)
    // 80% accuracy = 2.0x weight (excellent signal)
    const accuracyMultiplier = Math.max(0.3, Math.min(2.0, (accuracy.accuracy - 0.5) * 5));

    adjustedWeights[signal] = baseWeight * accuracyMultiplier;
  }

  // Normalize
  const total = Object.values(adjustedWeights).reduce((a, b) => a + b, 0);
  for (const signal of Object.keys(adjustedWeights)) {
    adjustedWeights[signal] = adjustedWeights[signal] / total;
  }

  return adjustedWeights;
}
```

#### Storage and Tracking

```sql
-- Signal accuracy tracking
CREATE TABLE IF NOT EXISTS signal_accuracy (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_id TEXT,
  signal_type TEXT NOT NULL,
  signal_value TEXT,
  prediction TEXT NOT NULL,
  outcome TEXT,
  trade_id TEXT,
  timestamp INTEGER NOT NULL
);

CREATE INDEX idx_signal_accuracy_type ON signal_accuracy(signal_type);
CREATE INDEX idx_signal_accuracy_agent ON signal_accuracy(agent_id);
```

### Implementation Effort: Medium
- New file: ~100 lines
- Migration: 1 table
- Modifications: Intelligence integration in agent-do.ts

---

## 8. Exchange Execution: Exchange-Specific Routing

### Current State
- Agents can connect to multiple exchanges
- No tracking of per-exchange performance

### Solution: Exchange Specialization Tracking

```typescript
// NEW: v3/cloudflare-agents/exchanges/exchange-specialization.ts

export interface ExchangePerformance {
  exchange: string;
  totalTrades: number;
  winRate: number;
  avgSlippage: number;
  avgLatency: number;
  netPnL: number;
}

export interface ExchangeSpecialization {
  agent_id: string;

  // Performance by exchange
  byExchange: Map<string, ExchangePerformance>;

  // Recommended primary exchange
  primaryExchange: string;

  // Exchanges to avoid
  excludeExchanges: string[];
}

/**
 * Route orders to best-performing exchange
 */
export function selectBestExchange(
  spec: ExchangeSpecialization,
  availableExchanges: string[],
  orderSize: number
): string {
  // Filter to available and non-excluded
  const candidates = availableExchanges.filter(
    e => !spec.excludeExchanges.includes(e)
  );

  if (candidates.length === 0) {
    return availableExchanges[0] ?? 'default';
  }

  // Score each exchange
  const scores = candidates.map(exchange => {
    const perf = spec.byExchange.get(exchange);
    if (!perf || perf.totalTrades < 10) {
      return { exchange, score: 50 };  // Neutral for new exchanges
    }

    // Score based on: win rate (40%), slippage (30%), PnL (30%)
    const winRateScore = perf.winRate * 40;
    const slippageScore = Math.max(0, 30 - perf.avgSlippage * 100);
    const pnlScore = Math.min(30, Math.max(0, perf.netPnL / 100 * 30));

    return {
      exchange,
      score: winRateScore + slippageScore + pnlScore
    };
  });

  // Return highest scoring
  scores.sort((a, b) => b.score - a.score);
  return scores[0]?.exchange ?? candidates[0] ?? 'default';
}
```

### Implementation Effort: Low-Medium
- New file: ~80 lines
- Modifications: Order routing in exchange client

---

## 9. Derived Traits: Already Well-Implemented

### Current State
```typescript
// trait-mutation.ts - Already implemented correctly
export const DERIVED_TRAITS = [
  'drawdown_sensitivity',    // ≈ 1 - risk_tolerance
  'stop_loss_tightness',     // ≈ 1 - risk_tolerance
  'exit_aggression',         // ≈ 1 - hold_duration_bias
];
```

### Assessment
This is **well-designed** and mimics kappaTune's coupled layer concept:
- Reduces effective parameter count
- Prevents contradictory trait combinations
- Derived traits inherit κ from their anchors

### Only Minor Enhancement Needed

```typescript
// OPTIONAL: Make coupling strength evolvable

export interface DerivedTraitConfig {
  anchor: keyof AgentTraits;
  couplingStrength: number;  // 0 = independent, 1 = fully coupled
  noiseLevel: number;        // Current is 0.05 (±5%)
}

// Could let evolution discover optimal coupling strength
// But this is a "nice to have", not a gap
```

### Implementation Effort: None required (already good)

---

## Implementation Priority

| Component | Impact | Effort | Priority |
|-----------|--------|--------|----------|
| 1. Adaptive Trait Mutation | High | Medium | **P1** |
| 3. κ-Tiered Memory Decay | High | Low-Med | **P1** |
| 2. Pattern Stability | Medium | Medium | **P2** |
| 6. Regime-Aware Patterns | High | Med-High | **P2** |
| 4. Adaptive Cycle Params | Medium | Low | **P3** |
| 5. Stability in Fitness | Medium | Low | **P3** |
| 7. Signal Accuracy | Medium | Medium | **P3** |
| 8. Exchange Routing | Low | Low-Med | **P4** |
| 9. Derived Traits | N/A | None | Done |

### Recommended Implementation Order

1. **Week 1**: Adaptive Trait Mutation + κ-Tiered Memory Decay
2. **Week 2**: Pattern Stability Scoring
3. **Week 3**: Regime-Aware Pattern Performance
4. **Week 4**: Remaining items (cycle params, signal accuracy, etc.)
