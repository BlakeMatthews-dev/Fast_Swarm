# Layer 5, 6, 7 Technical Implementation Plans

> Detailed implementation specs with Evidence-Driven Development (EDD) tests.

---

## Layer 5: Agent Competition (Tournament System)

**Current Status:** 30% complete (spawning works, competition doesn't)

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     TOURNAMENT ORCHESTRATOR                      │
│  (Runs weekly or on-demand)                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Agent A    │  │   Agent B    │  │   Agent C    │   ...    │
│  │  traits: {...}│  │  traits: {...}│  │  traits: {...}│          │
│  │  patterns: 5 │  │  patterns: 5 │  │  patterns: 5 │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                 │                   │
│         └─────────────────┴─────────────────┘                   │
│                           │                                      │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              CANONICAL BACKTEST PERIODS                      ││
│  │  Same data for ALL agents (fair competition)                ││
│  │  Period 1: 2024-01 to 2024-06 (bull market)                 ││
│  │  Period 2: 2024-06 to 2024-12 (choppy market)               ││
│  │  Period 3: 2023-01 to 2023-06 (bear recovery)               ││
│  └─────────────────────────────────────────────────────────────┘│
│                           │                                      │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    RANKING ENGINE                            ││
│  │  Primary: Sortino ratio (risk-adjusted)                     ││
│  │  Secondary: Calmar ratio (drawdown-adjusted)                ││
│  │  Tertiary: Total ROI (absolute performance)                 ││
│  │  Consistency: Std dev of period-to-period returns           ││
│  └─────────────────────────────────────────────────────────────┘│
│                           │                                      │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                  SELECTION PRESSURE                          ││
│  │  Top 20%: Clone with ±10% trait mutation                    ││
│  │  Middle 50%: Survive, no reproduction                       ││
│  │  Bottom 30%: Cull (patterns returned to pool)               ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Data Structures

```typescript
// v3/cloudflare-agents/shared/types.ts additions

interface TournamentConfig {
  tournament_id: string;
  created_at: string;
  status: 'pending' | 'running' | 'complete';
  canonical_periods: CanonicalPeriod[];
  agent_ids: string[];
  results?: TournamentResults;
}

interface CanonicalPeriod {
  period_id: string;
  start_date: string;        // ISO date
  end_date: string;          // ISO date
  regime: 'bull' | 'bear' | 'sideways' | 'volatile';
  assets: string[];          // BTC, ETH, SOL, etc.
  timeframes: ('1h' | '1d')[];
}

interface AgentTournamentResult {
  agent_id: string;
  period_results: PeriodResult[];
  aggregate: {
    total_roi_pct: number;
    avg_sortino: number;
    avg_calmar: number;
    max_drawdown_pct: number;
    consistency_score: number;  // 1 - (std_dev of period returns / mean)
    final_rank: number;
  };
}

interface PeriodResult {
  period_id: string;
  trades: number;
  roi_pct: number;
  sortino: number;
  calmar: number;
  max_drawdown_pct: number;
}

interface TournamentResults {
  rankings: AgentTournamentResult[];
  clone_candidates: string[];     // Top 20% agent_ids
  cull_candidates: string[];      // Bottom 30% agent_ids
  survivors: string[];            // Middle 50%
}
```

### Implementation Tasks

```typescript
// File: v3/cloudflare-agents/tournament/tournament-orchestrator.ts

/**
 * TournamentOrchestratorDO
 *
 * Runs agent tournaments on canonical periods.
 * Ensures fair comparison by testing all agents on identical data.
 */
export class TournamentOrchestratorDO {
  private state: DurableObjectState;

  // 5.1 Initialize Tournament
  async initializeTournament(config: {
    agent_count: number;
    periods: CanonicalPeriod[];
  }): Promise<TournamentConfig> {
    // Select random subset of active agents
    // Define canonical periods from historical data
    // Store tournament config
  }

  // 5.2 Run Tournament Phase
  async runTournamentPhase(tournament_id: string): Promise<void> {
    // For each agent in tournament:
    //   For each canonical period:
    //     Run backtest with agent's patterns + traits
    //     Store results
    // Use alarm() for chunked execution (avoid 30s timeout)
  }

  // 5.3 Calculate Rankings
  async calculateRankings(tournament_id: string): Promise<TournamentResults> {
    // Aggregate period results per agent
    // Sort by: sortino (primary), calmar (secondary), roi (tertiary)
    // Identify top 20%, bottom 30%
  }

  // 5.4 Execute Selection Pressure
  async executeSelection(tournament_id: string): Promise<{
    cloned: string[];
    culled: string[];
  }> {
    // Clone top 20% with trait mutation
    // Delete bottom 30% agents
    // Return patterns to pool
  }
}
```

### EDD Tests for Layer 5

```typescript
// File: v3/cloudflare-agents/tests/soundness/tournament.test.ts

import { describe, it, expect } from 'vitest';

describe('Layer 5: Tournament Soundness', () => {

  // ====== DETERMINISM TESTS ======

  describe('Determinism', () => {
    it('same agents + same periods = same rankings', async () => {
      const config = createTournamentConfig({ seed: 42 });

      const run1 = await runTournament(config);
      const run2 = await runTournament(config);

      expect(run1.rankings.map(r => r.agent_id))
        .toEqual(run2.rankings.map(r => r.agent_id));
      expect(run1.rankings.map(r => r.aggregate.final_rank))
        .toEqual(run2.rankings.map(r => r.aggregate.final_rank));
    });

    it('trait mutation is seeded and reproducible', async () => {
      const parent = createAgent({ seed: 42 });

      const child1 = cloneWithMutation(parent, { mutation_seed: 123 });
      const child2 = cloneWithMutation(parent, { mutation_seed: 123 });

      expect(child1.traits).toEqual(child2.traits);
    });
  });

  // ====== STATISTICAL SANITY TESTS ======

  describe('Statistical Sanity', () => {
    it('agent sortino ratios are within realistic bounds', async () => {
      const results = await runTournament(createTournamentConfig());

      for (const agent of results.rankings) {
        // Sortino between -5 and +10 is realistic
        expect(agent.aggregate.avg_sortino).toBeGreaterThanOrEqual(-5);
        expect(agent.aggregate.avg_sortino).toBeLessThanOrEqual(10);
      }
    });

    it('agent max drawdowns are within acceptable bounds', async () => {
      const results = await runTournament(createTournamentConfig());

      for (const agent of results.rankings) {
        // No agent should have >50% max drawdown
        expect(agent.aggregate.max_drawdown_pct).toBeLessThanOrEqual(50);
      }
    });

    it('top 20% have better metrics than bottom 30%', async () => {
      const results = await runTournament(createTournamentConfig());

      const topAgents = results.clone_candidates;
      const bottomAgents = results.cull_candidates;

      const topAvgSortino = avgSortino(results.rankings.filter(
        r => topAgents.includes(r.agent_id)
      ));
      const bottomAvgSortino = avgSortino(results.rankings.filter(
        r => bottomAgents.includes(r.agent_id)
      ));

      expect(topAvgSortino).toBeGreaterThan(bottomAvgSortino);
    });

    it('consistency score penalizes high variance', async () => {
      const stableAgent = await backtest(createAgent({
        period_returns: [10, 12, 11, 9, 10]  // Low variance
      }));
      const volatileAgent = await backtest(createAgent({
        period_returns: [50, -30, 40, -20, 10]  // High variance
      }));

      expect(stableAgent.consistency_score)
        .toBeGreaterThan(volatileAgent.consistency_score);
    });
  });

  // ====== SAFETY INVARIANT TESTS ======

  describe('Safety Invariants', () => {
    it('exactly 20% are cloned, 30% are culled', async () => {
      const agentCount = 50;
      const results = await runTournament(
        createTournamentConfig({ agent_count: agentCount })
      );

      expect(results.clone_candidates.length).toBe(Math.floor(agentCount * 0.2));
      expect(results.cull_candidates.length).toBe(Math.floor(agentCount * 0.3));
    });

    it('no agent appears in both clone and cull lists', async () => {
      const results = await runTournament(createTournamentConfig());

      const cloneSet = new Set(results.clone_candidates);
      const cullSet = new Set(results.cull_candidates);

      for (const id of cullSet) {
        expect(cloneSet.has(id)).toBe(false);
      }
    });

    it('culled agents have patterns returned to pool', async () => {
      const initialPoolSize = await getPatternPoolSize();
      const results = await runTournament(createTournamentConfig());
      await executeSelection(results);

      const culledPatternCount = results.cull_candidates.length * 5; // avg 5 patterns/agent
      const finalPoolSize = await getPatternPoolSize();

      expect(finalPoolSize).toBeGreaterThanOrEqual(
        initialPoolSize + culledPatternCount * 0.9  // Allow for some patterns dying
      );
    });

    it('trait mutation stays within bounds', async () => {
      for (let i = 0; i < 100; i++) {
        const parent = createAgent({ seed: i });
        const child = cloneWithMutation(parent, { mutation_rate: 0.1 });

        for (const [trait, value] of Object.entries(child.traits)) {
          expect(value).toBeGreaterThanOrEqual(0);
          expect(value).toBeLessThanOrEqual(1);
        }
      }
    });
  });

  // ====== ECONOMIC REALISM TESTS ======

  describe('Economic Realism', () => {
    it('all agents tested on identical periods', async () => {
      const results = await runTournament(createTournamentConfig());

      const periodsPerAgent = results.rankings.map(
        r => r.period_results.map(p => p.period_id).sort()
      );

      // All agents should have same periods
      const firstAgentPeriods = periodsPerAgent[0];
      for (const agentPeriods of periodsPerAgent) {
        expect(agentPeriods).toEqual(firstAgentPeriods);
      }
    });

    it('periods cover multiple market regimes', async () => {
      const config = createTournamentConfig();

      const regimes = config.canonical_periods.map(p => p.regime);
      const uniqueRegimes = new Set(regimes);

      expect(uniqueRegimes.size).toBeGreaterThanOrEqual(2);
    });

    it('minimum trade count per period for validity', async () => {
      const results = await runTournament(createTournamentConfig());

      for (const agent of results.rankings) {
        for (const period of agent.period_results) {
          // At least 10 trades per period for statistical validity
          expect(period.trades).toBeGreaterThanOrEqual(10);
        }
      }
    });
  });
});
```

---

## Layer 6: Coaches/Planners (Roster Management)

**Current Status:** 0% complete

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         COACH LAYER                              │
│  (Coaches are under selection pressure too)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Coach A    │  │   Coach B    │  │   Coach C    │          │
│  │  roster: 7   │  │  roster: 5   │  │  roster: 8   │          │
│  │  bench: 10   │  │  bench: 12   │  │  bench: 9    │          │
│  │  fitness: 72 │  │  fitness: 85 │  │  fitness: 68 │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                 │                   │
│         ▼                 ▼                 ▼                   │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐           │
│  │ Active      │   │ Active      │   │ Active      │           │
│  │ Roster      │   │ Roster      │   │ Roster      │           │
│  │ [A1,A2,A3.. │   │ [B1,B2,B3.. │   │ [C1,C2,C3.. │           │
│  └─────────────┘   └─────────────┘   └─────────────┘           │
│                                                                  │
│  COACH SELECTION PRESSURE:                                      │
│  - Coach fitness = weighted avg of roster agent fitness         │
│  - Top coaches get more agents to manage                        │
│  - Bottom coaches lose agents / get replaced                    │
│                                                                  │
│  ROSTER DECISIONS:                                              │
│  - Which agents to activate for this market regime?             │
│  - Which patterns to emphasize based on conditions?             │
│  - When to bench underperformers?                               │
└─────────────────────────────────────────────────────────────────┘
```

### Data Structures

```typescript
// v3/cloudflare-agents/shared/types.ts additions

interface Coach {
  coach_id: string;
  created_at: string;
  generation: number;
  parent_coach_id?: string;

  // Roster management
  active_roster: string[];        // Agent IDs currently playing
  bench: string[];                // Agent IDs on bench
  max_roster_size: number;        // 5-10 typically

  // Coach traits (affects roster decisions)
  traits: CoachTraits;

  // Performance
  fitness: number;
  total_managed_trades: number;
  roster_roi_history: number[];   // ROI per evaluation period
}

interface CoachTraits {
  // Roster composition preferences
  diversity_preference: number;      // 0-1: prefer varied vs focused traits
  risk_tolerance: number;            // 0-1: prefer aggressive vs conservative agents
  regime_sensitivity: number;        // 0-1: how often to swap based on regime

  // Decision timing
  swap_frequency: number;            // 0-1: frequent vs rare roster changes
  patience: number;                  // 0-1: quick to bench vs give agents time

  // Agent selection criteria weights
  recency_weight: number;            // 0-1: weight recent performance
  consistency_weight: number;        // 0-1: weight consistency vs peaks
  regime_match_weight: number;       // 0-1: weight regime appropriateness
}

interface RosterDecision {
  coach_id: string;
  timestamp: string;
  current_regime: MarketRegime;

  activations: string[];             // Agent IDs to move bench → active
  benches: string[];                 // Agent IDs to move active → bench

  reasoning: {
    agent_id: string;
    action: 'activate' | 'bench';
    reason: string;
  }[];
}

interface MarketRegime {
  trend: 'bull' | 'bear' | 'sideways';
  volatility: 'low' | 'medium' | 'high';
  correlation: number;               // BTC correlation with alts
  momentum: number;                  // -1 to +1
}
```

### Implementation Tasks

```typescript
// File: v3/cloudflare-agents/coaching/coach-do.ts

/**
 * CoachDO
 *
 * Manages a roster of agents, making activation decisions
 * based on market regime and agent performance.
 */
export class CoachDO {
  private state: DurableObjectState;

  // 6.1 Initialize Coach
  async initialize(config: {
    initial_agents: string[];
    traits?: Partial<CoachTraits>;
  }): Promise<Coach> {
    // Create coach with random or specified traits
    // Assign initial agents to bench
    // Select initial active roster
  }

  // 6.2 Evaluate Roster
  async evaluateRoster(regime: MarketRegime): Promise<RosterDecision> {
    // Score each agent for current regime
    // Consider: recent performance, regime fit, trait match
    // Generate swap recommendations
    // Apply coach traits to decision (patience, swap_frequency)
  }

  // 6.3 Execute Roster Change
  async executeRosterChange(decision: RosterDecision): Promise<void> {
    // Move agents between active and bench
    // Log decision for analysis
  }

  // 6.4 Calculate Coach Fitness
  async calculateFitness(): Promise<number> {
    // Weighted average of active roster performance
    // Penalize for high turnover (too much swapping)
    // Bonus for regime-appropriate selections
  }

  // 6.5 Clone Coach (for evolution)
  async clone(mutation_rate: number = 0.1): Promise<Coach> {
    // Copy coach with mutated traits
    // Inherit roster composition preferences
    // Reset performance history
  }
}

// File: v3/cloudflare-agents/coaching/coach-league.ts

/**
 * CoachLeagueDO
 *
 * Manages competition between coaches.
 * Applies selection pressure to coaches themselves.
 */
export class CoachLeagueDO {

  // 6.6 Run Coach Evaluation
  async evaluateCoaches(): Promise<CoachRankings> {
    // Rank coaches by their roster's aggregate performance
    // Consider: consistency, drawdown, regime adaptation
  }

  // 6.7 Coach Selection Pressure
  async applySelectionPressure(): Promise<{
    promoted: string[];
    demoted: string[];
    replaced: string[];
  }> {
    // Top coaches: get more agents to manage
    // Bottom coaches: lose agents or get replaced by clones of top coaches
  }
}
```

### EDD Tests for Layer 6

```typescript
// File: v3/cloudflare-agents/tests/soundness/coaching.test.ts

import { describe, it, expect } from 'vitest';

describe('Layer 6: Coach Soundness', () => {

  // ====== DETERMINISM TESTS ======

  describe('Determinism', () => {
    it('same coach + same regime = same roster decision', async () => {
      const coach = await createCoach({ seed: 42 });
      const regime: MarketRegime = { trend: 'bull', volatility: 'low', correlation: 0.8, momentum: 0.5 };

      const decision1 = await coach.evaluateRoster(regime);
      const decision2 = await coach.evaluateRoster(regime);

      expect(decision1.activations).toEqual(decision2.activations);
      expect(decision1.benches).toEqual(decision2.benches);
    });

    it('coach cloning with same seed produces identical traits', async () => {
      const parent = await createCoach({ seed: 42 });

      const child1 = await parent.clone({ mutation_seed: 123 });
      const child2 = await parent.clone({ mutation_seed: 123 });

      expect(child1.traits).toEqual(child2.traits);
    });
  });

  // ====== ROSTER DECISION TESTS ======

  describe('Roster Decisions', () => {
    it('high regime_sensitivity coach swaps more on regime change', async () => {
      const sensitiveCoach = await createCoach({
        traits: { regime_sensitivity: 0.9 }
      });
      const stableCoach = await createCoach({
        traits: { regime_sensitivity: 0.1 }
      });

      // Same agents, regime shifts from bull to bear
      const bullRegime: MarketRegime = { trend: 'bull', volatility: 'low', correlation: 0.8, momentum: 0.7 };
      const bearRegime: MarketRegime = { trend: 'bear', volatility: 'high', correlation: 0.9, momentum: -0.5 };

      await sensitiveCoach.evaluateRoster(bullRegime);
      await stableCoach.evaluateRoster(bullRegime);

      const sensitiveSwaps = await sensitiveCoach.evaluateRoster(bearRegime);
      const stableSwaps = await stableCoach.evaluateRoster(bearRegime);

      expect(sensitiveSwaps.activations.length + sensitiveSwaps.benches.length)
        .toBeGreaterThan(stableSwaps.activations.length + stableSwaps.benches.length);
    });

    it('coach respects max_roster_size', async () => {
      const coach = await createCoach({ max_roster_size: 5 });
      await coach.assignAgents(await createAgents(15));

      const roster = await coach.getActiveRoster();

      expect(roster.length).toBeLessThanOrEqual(5);
    });

    it('high patience coach gives underperformers more time', async () => {
      const patientCoach = await createCoach({ traits: { patience: 0.9 } });
      const impatientCoach = await createCoach({ traits: { patience: 0.1 } });

      // Add agent with 3 consecutive losing periods
      const strugglingAgent = await createAgent({ recent_roi: [-5, -3, -2] });

      await patientCoach.assignAgent(strugglingAgent);
      await impatientCoach.assignAgent(strugglingAgent);

      const patientDecision = await patientCoach.evaluateRoster(neutralRegime);
      const impatientDecision = await impatientCoach.evaluateRoster(neutralRegime);

      // Impatient coach should bench, patient should keep
      expect(impatientDecision.benches).toContain(strugglingAgent.agent_id);
      expect(patientDecision.benches).not.toContain(strugglingAgent.agent_id);
    });
  });

  // ====== COACH FITNESS TESTS ======

  describe('Coach Fitness', () => {
    it('coach fitness reflects roster performance', async () => {
      const goodCoach = await createCoach();
      const badCoach = await createCoach();

      // Assign high-performing agents to good coach
      await goodCoach.assignAgents(await createAgents(5, { avg_roi: 20 }));
      await badCoach.assignAgents(await createAgents(5, { avg_roi: -10 }));

      const goodFitness = await goodCoach.calculateFitness();
      const badFitness = await badCoach.calculateFitness();

      expect(goodFitness).toBeGreaterThan(badFitness);
    });

    it('excessive roster turnover penalizes fitness', async () => {
      const stableCoach = await createCoach();
      const churnCoach = await createCoach();

      // Same agents, same performance
      const agents = await createAgents(10, { avg_roi: 10 });
      await stableCoach.assignAgents(agents);
      await churnCoach.assignAgents(agents);

      // Churn coach swaps every period
      for (let i = 0; i < 10; i++) {
        await churnCoach.executeRosterChange({
          activations: agents.slice(i % 5, (i % 5) + 3).map(a => a.agent_id),
          benches: agents.slice(5 + (i % 3), 5 + (i % 3) + 3).map(a => a.agent_id)
        });
      }

      const stableFitness = await stableCoach.calculateFitness();
      const churnFitness = await churnCoach.calculateFitness();

      // Stable coach should score better despite same underlying agent performance
      expect(stableFitness).toBeGreaterThan(churnFitness);
    });
  });

  // ====== SELECTION PRESSURE TESTS ======

  describe('Coach Selection Pressure', () => {
    it('top coaches get more agents', async () => {
      const league = await createCoachLeague(5);
      await runEvaluationPeriod(league);

      const preRoster = await Promise.all(
        league.coaches.map(c => c.getAgentCount())
      );

      await league.applySelectionPressure();

      const postRoster = await Promise.all(
        league.coaches.map(c => c.getAgentCount())
      );

      const topCoachId = league.rankings[0].coach_id;
      const topCoachPre = preRoster[league.coaches.findIndex(c => c.coach_id === topCoachId)];
      const topCoachPost = postRoster[league.coaches.findIndex(c => c.coach_id === topCoachId)];

      expect(topCoachPost).toBeGreaterThanOrEqual(topCoachPre);
    });

    it('bottom coaches are replaced by clones of top coaches', async () => {
      const league = await createCoachLeague(5);
      await runEvaluationPeriod(league);

      const bottomCoachId = league.rankings[league.rankings.length - 1].coach_id;
      const topCoachId = league.rankings[0].coach_id;

      await league.applySelectionPressure();

      // Bottom coach should be replaced
      const stillExists = league.coaches.find(c => c.coach_id === bottomCoachId);
      expect(stillExists).toBeUndefined();

      // Should have a new coach with similar traits to top coach
      const newCoach = league.coaches.find(c => c.parent_coach_id === topCoachId);
      expect(newCoach).toBeDefined();
    });
  });

  // ====== SAFETY INVARIANTS ======

  describe('Safety Invariants', () => {
    it('agent cannot be on multiple rosters simultaneously', async () => {
      const league = await createCoachLeague(3);
      const allAgents = await getAllAgentsInLeague(league);

      const agentCounts = new Map<string, number>();
      for (const agent of allAgents) {
        const count = agentCounts.get(agent.agent_id) || 0;
        agentCounts.set(agent.agent_id, count + 1);
      }

      for (const [agentId, count] of agentCounts) {
        expect(count).toBe(1);
      }
    });

    it('coach trait values stay bounded 0-1', async () => {
      let coach = await createCoach({ seed: 42 });

      for (let generation = 0; generation < 20; generation++) {
        coach = await coach.clone({ mutation_rate: 0.2 });

        for (const [trait, value] of Object.entries(coach.traits)) {
          expect(value).toBeGreaterThanOrEqual(0);
          expect(value).toBeLessThanOrEqual(1);
        }
      }
    });
  });
});
```

---

## Layer 7: Collective Intelligence (Committee Voting)

**Current Status:** 0% complete

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      COMMITTEE SYSTEM                            │
│  (Collective decision-making beats individual agents)           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│                    SIGNAL RECEIVED                               │
│                         │                                        │
│                         ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                   COMMITTEE VOTING                           ││
│  │                                                              ││
│  │  Agent 1: LONG  (conf: 0.8)  [momentum trader]              ││
│  │  Agent 2: SHORT (conf: 0.6)  [mean reversion]               ││
│  │  Agent 3: LONG  (conf: 0.7)  [trend follower]               ││
│  │  Agent 4: WAIT  (conf: 0.5)  [conservative]                 ││
│  │  Agent 5: LONG  (conf: 0.9)  [aggressive]                   ││
│  │                                                              ││
│  │  Votes: LONG=3, SHORT=1, WAIT=1                             ││
│  │  Weighted: LONG=2.4, SHORT=0.6, WAIT=0.5                    ││
│  └─────────────────────────────────────────────────────────────┘│
│                         │                                        │
│                         ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                  QUORUM CHECK                                ││
│  │                                                              ││
│  │  Threshold: 60% agreement                                   ││
│  │  LONG votes: 3/5 = 60% ✓                                    ││
│  │  Weighted confidence: 0.8 avg                               ││
│  │                                                              ││
│  │  DECISION: EXECUTE LONG                                     ││
│  └─────────────────────────────────────────────────────────────┘│
│                         │                                        │
│                         ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                  POSITION SIZING                             ││
│  │                                                              ││
│  │  Base size: Kelly fraction                                  ││
│  │  Committee confidence: 0.8 → 80% of Kelly                   ││
│  │  Disagreement penalty: 2/5 dissenters → 0.9x                ││
│  │  Final size: 0.72 × Kelly                                   ││
│  └─────────────────────────────────────────────────────────────┘│
│                         │                                        │
│                         ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                WISDOM ACCUMULATION                           ││
│  │                                                              ││
│  │  After trade closes:                                        ││
│  │  - Record which agents voted correctly                      ││
│  │  - Update agent credibility scores                          ││
│  │  - Extract patterns: "When Agent 5 is confident + regime X" ││
│  │  - Store in collective wisdom                               ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Data Structures

```typescript
// v3/cloudflare-agents/shared/types.ts additions

interface CommitteeConfig {
  committee_id: string;
  members: string[];              // Agent IDs in committee
  quorum_threshold: number;       // 0-1, typically 0.6
  voting_mode: 'simple' | 'confidence_weighted' | 'credibility_weighted';
  size_scaling: 'fixed' | 'confidence_scaled' | 'disagreement_scaled';
}

type VoteDirection = 'LONG' | 'SHORT' | 'WAIT';

interface AgentVote {
  agent_id: string;
  direction: VoteDirection;
  confidence: number;             // 0-1
  reasoning?: string;
  patterns_triggered: string[];   // Which patterns led to this vote
}

interface CommitteeDecision {
  committee_id: string;
  timestamp: string;
  signal_id: string;
  asset: string;

  // Voting results
  votes: AgentVote[];
  vote_counts: Record<VoteDirection, number>;
  weighted_scores: Record<VoteDirection, number>;

  // Decision
  decision: VoteDirection;
  quorum_met: boolean;
  avg_confidence: number;
  disagreement_ratio: number;     // 0-1, how much dissent

  // Execution
  position_size_fraction: number; // 0-1, fraction of max position
  executed: boolean;
}

interface AgentCredibility {
  agent_id: string;
  total_votes: number;
  correct_votes: number;
  credibility_score: number;      // Bayesian update from vote accuracy
  regime_scores: Record<string, number>;  // Per-regime credibility
}

interface CollectiveWisdom {
  rules: WisdomRule[];
  updated_at: string;
}

interface WisdomRule {
  rule_id: string;
  pattern: string;                // "Agent X confident + regime Y"
  outcome: 'positive' | 'negative';
  confidence: number;
  sample_size: number;
  created_at: string;
}
```

### Implementation Tasks

```typescript
// File: v3/cloudflare-agents/committee/committee-do.ts

/**
 * CommitteeDO
 *
 * Aggregates votes from multiple agents to make collective decisions.
 * Tracks credibility and extracts wisdom from voting patterns.
 */
export class CommitteeDO {
  private state: DurableObjectState;

  // 7.1 Initialize Committee
  async initialize(config: CommitteeConfig): Promise<void> {
    // Set up committee with member agents
    // Initialize credibility scores
  }

  // 7.2 Collect Votes
  async collectVotes(signal: TradingSignal): Promise<AgentVote[]> {
    // Query each committee member for their vote
    // Parallel execution with timeout
    // Handle abstentions
  }

  // 7.3 Make Decision
  async makeDecision(votes: AgentVote[]): Promise<CommitteeDecision> {
    // Count votes, calculate weighted scores
    // Check quorum
    // Determine final decision
    // Calculate position sizing
  }

  // 7.4 Execute Decision
  async executeDecision(decision: CommitteeDecision): Promise<TradeExecution> {
    // Place order if decision is LONG or SHORT
    // Skip if WAIT or quorum not met
    // Log execution details
  }

  // 7.5 Update Credibility (after trade closes)
  async updateCredibility(
    decision: CommitteeDecision,
    outcome: TradeOutcome
  ): Promise<void> {
    // Determine which agents voted correctly
    // Bayesian update of credibility scores
    // Regime-specific credibility updates
  }

  // 7.6 Extract Wisdom
  async extractWisdom(): Promise<WisdomRule[]> {
    // Analyze voting patterns and outcomes
    // Identify: "When X, outcome is usually Y"
    // Store as explicit rules
  }

  // 7.7 Apply Wisdom to Future Decisions
  async applyWisdom(
    votes: AgentVote[],
    currentRegime: MarketRegime
  ): Promise<AgentVote[]> {
    // Boost/reduce votes based on wisdom rules
    // E.g., "Agent 5 is reliable in bull markets"
  }
}
```

### EDD Tests for Layer 7

```typescript
// File: v3/cloudflare-agents/tests/soundness/committee.test.ts

import { describe, it, expect } from 'vitest';

describe('Layer 7: Committee Soundness', () => {

  // ====== DETERMINISM TESTS ======

  describe('Determinism', () => {
    it('same votes = same decision', async () => {
      const committee = await createCommittee({ seed: 42 });
      const votes: AgentVote[] = [
        { agent_id: 'a1', direction: 'LONG', confidence: 0.8, patterns_triggered: [] },
        { agent_id: 'a2', direction: 'LONG', confidence: 0.7, patterns_triggered: [] },
        { agent_id: 'a3', direction: 'SHORT', confidence: 0.6, patterns_triggered: [] },
      ];

      const decision1 = await committee.makeDecision(votes);
      const decision2 = await committee.makeDecision(votes);

      expect(decision1.decision).toEqual(decision2.decision);
      expect(decision1.position_size_fraction).toEqual(decision2.position_size_fraction);
    });

    it('credibility updates are deterministic', async () => {
      const committee = await createCommittee({ seed: 42 });
      const decision = await createDecision();
      const outcome: TradeOutcome = { pnl_pct: 5, direction: 'LONG' };

      await committee.updateCredibility(decision, outcome);
      const cred1 = await committee.getCredibilityScores();

      // Reset and replay
      await committee.reset();
      await committee.updateCredibility(decision, outcome);
      const cred2 = await committee.getCredibilityScores();

      expect(cred1).toEqual(cred2);
    });
  });

  // ====== VOTING LOGIC TESTS ======

  describe('Voting Logic', () => {
    it('quorum requires threshold agreement', async () => {
      const committee = await createCommittee({ quorum_threshold: 0.6 });

      // 3/5 = 60% → exactly at threshold
      const borderlineVotes: AgentVote[] = [
        { agent_id: 'a1', direction: 'LONG', confidence: 0.8, patterns_triggered: [] },
        { agent_id: 'a2', direction: 'LONG', confidence: 0.7, patterns_triggered: [] },
        { agent_id: 'a3', direction: 'LONG', confidence: 0.6, patterns_triggered: [] },
        { agent_id: 'a4', direction: 'SHORT', confidence: 0.5, patterns_triggered: [] },
        { agent_id: 'a5', direction: 'WAIT', confidence: 0.4, patterns_triggered: [] },
      ];

      const decision = await committee.makeDecision(borderlineVotes);
      expect(decision.quorum_met).toBe(true);
      expect(decision.decision).toBe('LONG');

      // 2/5 = 40% → below threshold
      const noQuorumVotes: AgentVote[] = [
        { agent_id: 'a1', direction: 'LONG', confidence: 0.8, patterns_triggered: [] },
        { agent_id: 'a2', direction: 'LONG', confidence: 0.7, patterns_triggered: [] },
        { agent_id: 'a3', direction: 'SHORT', confidence: 0.6, patterns_triggered: [] },
        { agent_id: 'a4', direction: 'SHORT', confidence: 0.5, patterns_triggered: [] },
        { agent_id: 'a5', direction: 'WAIT', confidence: 0.4, patterns_triggered: [] },
      ];

      const noQuorumDecision = await committee.makeDecision(noQuorumVotes);
      expect(noQuorumDecision.quorum_met).toBe(false);
      expect(noQuorumDecision.decision).toBe('WAIT');
    });

    it('confidence weighting affects decision', async () => {
      const committee = await createCommittee({ voting_mode: 'confidence_weighted' });

      // 2 LONG with high confidence vs 3 SHORT with low confidence
      const votes: AgentVote[] = [
        { agent_id: 'a1', direction: 'LONG', confidence: 0.95, patterns_triggered: [] },
        { agent_id: 'a2', direction: 'LONG', confidence: 0.90, patterns_triggered: [] },
        { agent_id: 'a3', direction: 'SHORT', confidence: 0.3, patterns_triggered: [] },
        { agent_id: 'a4', direction: 'SHORT', confidence: 0.25, patterns_triggered: [] },
        { agent_id: 'a5', direction: 'SHORT', confidence: 0.2, patterns_triggered: [] },
      ];

      const decision = await committee.makeDecision(votes);

      // Weighted: LONG = 0.95 + 0.90 = 1.85, SHORT = 0.3 + 0.25 + 0.2 = 0.75
      expect(decision.decision).toBe('LONG');
    });

    it('credibility weighting favors proven agents', async () => {
      const committee = await createCommittee({ voting_mode: 'credibility_weighted' });

      // Set up credibility: a1 has 90% accuracy, a2-a5 have 40%
      await committee.setCredibility('a1', 0.9);
      await committee.setCredibility('a2', 0.4);
      await committee.setCredibility('a3', 0.4);
      await committee.setCredibility('a4', 0.4);
      await committee.setCredibility('a5', 0.4);

      // a1 says LONG, everyone else says SHORT
      const votes: AgentVote[] = [
        { agent_id: 'a1', direction: 'LONG', confidence: 0.8, patterns_triggered: [] },
        { agent_id: 'a2', direction: 'SHORT', confidence: 0.8, patterns_triggered: [] },
        { agent_id: 'a3', direction: 'SHORT', confidence: 0.8, patterns_triggered: [] },
        { agent_id: 'a4', direction: 'SHORT', confidence: 0.8, patterns_triggered: [] },
        { agent_id: 'a5', direction: 'SHORT', confidence: 0.8, patterns_triggered: [] },
      ];

      const decision = await committee.makeDecision(votes);

      // Weighted by credibility: LONG = 0.9 * 0.8, SHORT = 4 * 0.4 * 0.8 = 1.28
      // SHORT still wins, but it's closer
      expect(decision.weighted_scores['LONG']).toBeCloseTo(0.72);
      expect(decision.weighted_scores['SHORT']).toBeCloseTo(1.28);
    });
  });

  // ====== POSITION SIZING TESTS ======

  describe('Position Sizing', () => {
    it('high confidence = larger position', async () => {
      const committee = await createCommittee({ size_scaling: 'confidence_scaled' });

      const highConfVotes: AgentVote[] = [
        { agent_id: 'a1', direction: 'LONG', confidence: 0.95, patterns_triggered: [] },
        { agent_id: 'a2', direction: 'LONG', confidence: 0.90, patterns_triggered: [] },
        { agent_id: 'a3', direction: 'LONG', confidence: 0.85, patterns_triggered: [] },
      ];

      const lowConfVotes: AgentVote[] = [
        { agent_id: 'a1', direction: 'LONG', confidence: 0.55, patterns_triggered: [] },
        { agent_id: 'a2', direction: 'LONG', confidence: 0.50, patterns_triggered: [] },
        { agent_id: 'a3', direction: 'LONG', confidence: 0.45, patterns_triggered: [] },
      ];

      const highConfDecision = await committee.makeDecision(highConfVotes);
      const lowConfDecision = await committee.makeDecision(lowConfVotes);

      expect(highConfDecision.position_size_fraction)
        .toBeGreaterThan(lowConfDecision.position_size_fraction);
    });

    it('high disagreement = smaller position', async () => {
      const committee = await createCommittee({ size_scaling: 'disagreement_scaled' });

      const unanimousVotes: AgentVote[] = [
        { agent_id: 'a1', direction: 'LONG', confidence: 0.8, patterns_triggered: [] },
        { agent_id: 'a2', direction: 'LONG', confidence: 0.8, patterns_triggered: [] },
        { agent_id: 'a3', direction: 'LONG', confidence: 0.8, patterns_triggered: [] },
        { agent_id: 'a4', direction: 'LONG', confidence: 0.8, patterns_triggered: [] },
        { agent_id: 'a5', direction: 'LONG', confidence: 0.8, patterns_triggered: [] },
      ];

      const splitVotes: AgentVote[] = [
        { agent_id: 'a1', direction: 'LONG', confidence: 0.8, patterns_triggered: [] },
        { agent_id: 'a2', direction: 'LONG', confidence: 0.8, patterns_triggered: [] },
        { agent_id: 'a3', direction: 'LONG', confidence: 0.8, patterns_triggered: [] },
        { agent_id: 'a4', direction: 'SHORT', confidence: 0.8, patterns_triggered: [] },
        { agent_id: 'a5', direction: 'SHORT', confidence: 0.8, patterns_triggered: [] },
      ];

      const unanimousDecision = await committee.makeDecision(unanimousVotes);
      const splitDecision = await committee.makeDecision(splitVotes);

      expect(unanimousDecision.position_size_fraction)
        .toBeGreaterThan(splitDecision.position_size_fraction);
    });
  });

  // ====== CREDIBILITY UPDATE TESTS ======

  describe('Credibility Updates', () => {
    it('correct votes increase credibility', async () => {
      const committee = await createCommittee();

      const agent_id = 'a1';
      const initialCred = await committee.getCredibility(agent_id);

      // Agent voted LONG, trade was profitable
      const decision = await createDecision({
        votes: [{ agent_id, direction: 'LONG', confidence: 0.8, patterns_triggered: [] }],
        decision: 'LONG'
      });
      await committee.updateCredibility(decision, { pnl_pct: 5, direction: 'LONG' });

      const newCred = await committee.getCredibility(agent_id);
      expect(newCred).toBeGreaterThan(initialCred);
    });

    it('incorrect votes decrease credibility', async () => {
      const committee = await createCommittee();

      const agent_id = 'a1';
      await committee.setCredibility(agent_id, 0.7);

      // Agent voted LONG, but we lost money
      const decision = await createDecision({
        votes: [{ agent_id, direction: 'LONG', confidence: 0.8, patterns_triggered: [] }],
        decision: 'LONG'
      });
      await committee.updateCredibility(decision, { pnl_pct: -5, direction: 'LONG' });

      const newCred = await committee.getCredibility(agent_id);
      expect(newCred).toBeLessThan(0.7);
    });

    it('WAIT votes are neutral for credibility', async () => {
      const committee = await createCommittee();

      const agent_id = 'a1';
      await committee.setCredibility(agent_id, 0.7);

      const decision = await createDecision({
        votes: [{ agent_id, direction: 'WAIT', confidence: 0.5, patterns_triggered: [] }],
        decision: 'LONG'  // Committee went LONG but agent abstained
      });
      await committee.updateCredibility(decision, { pnl_pct: 5, direction: 'LONG' });

      const newCred = await committee.getCredibility(agent_id);
      // Slight penalty for missing a winning trade, but less than being wrong
      expect(newCred).toBeCloseTo(0.7, 1);
    });
  });

  // ====== WISDOM EXTRACTION TESTS ======

  describe('Wisdom Extraction', () => {
    it('identifies reliable agent-regime combinations', async () => {
      const committee = await createCommittee();

      // Simulate 20 trades where Agent 1 is right in bull markets
      for (let i = 0; i < 20; i++) {
        const decision = await createDecision({
          votes: [
            { agent_id: 'a1', direction: 'LONG', confidence: 0.8, patterns_triggered: [] }
          ],
          decision: 'LONG',
          regime: { trend: 'bull', volatility: 'low', correlation: 0.8, momentum: 0.5 }
        });
        await committee.updateCredibility(decision, { pnl_pct: 3, direction: 'LONG' });
      }

      const wisdom = await committee.extractWisdom();

      const rule = wisdom.rules.find(r =>
        r.pattern.includes('a1') && r.pattern.includes('bull')
      );
      expect(rule).toBeDefined();
      expect(rule?.outcome).toBe('positive');
      expect(rule?.confidence).toBeGreaterThan(0.7);
    });

    it('wisdom affects future vote weighting', async () => {
      const committee = await createCommittee();

      // Add wisdom rule: "a1 is reliable in bull markets"
      await committee.addWisdomRule({
        rule_id: 'r1',
        pattern: 'agent:a1 + regime:bull',
        outcome: 'positive',
        confidence: 0.9,
        sample_size: 50,
        created_at: new Date().toISOString()
      });

      const votes: AgentVote[] = [
        { agent_id: 'a1', direction: 'LONG', confidence: 0.6, patterns_triggered: [] },
        { agent_id: 'a2', direction: 'SHORT', confidence: 0.7, patterns_triggered: [] },
      ];

      const boostedVotes = await committee.applyWisdom(votes, {
        trend: 'bull', volatility: 'low', correlation: 0.8, momentum: 0.5
      });

      // a1's vote should be boosted
      const a1Vote = boostedVotes.find(v => v.agent_id === 'a1');
      expect(a1Vote?.confidence).toBeGreaterThan(0.6);
    });
  });

  // ====== SAFETY INVARIANTS ======

  describe('Safety Invariants', () => {
    it('never exceeds max position size', async () => {
      const committee = await createCommittee();

      // Even with 100% confidence and unanimous vote
      const maxConfVotes: AgentVote[] = Array(5).fill(null).map((_, i) => ({
        agent_id: `a${i}`,
        direction: 'LONG' as VoteDirection,
        confidence: 1.0,
        patterns_triggered: []
      }));

      const decision = await committee.makeDecision(maxConfVotes);

      expect(decision.position_size_fraction).toBeLessThanOrEqual(1.0);
    });

    it('credibility stays bounded 0-1', async () => {
      const committee = await createCommittee();

      // 100 consecutive correct votes
      for (let i = 0; i < 100; i++) {
        const decision = await createDecision({
          votes: [{ agent_id: 'a1', direction: 'LONG', confidence: 1.0, patterns_triggered: [] }],
          decision: 'LONG'
        });
        await committee.updateCredibility(decision, { pnl_pct: 10, direction: 'LONG' });
      }

      const cred = await committee.getCredibility('a1');
      expect(cred).toBeLessThanOrEqual(1.0);
      expect(cred).toBeGreaterThanOrEqual(0.0);
    });

    it('committee decision is logged for audit', async () => {
      const committee = await createCommittee();
      const votes = await createVotes(5);

      const decision = await committee.makeDecision(votes);

      // Decision should have full audit trail
      expect(decision.votes).toHaveLength(5);
      expect(decision.vote_counts).toBeDefined();
      expect(decision.weighted_scores).toBeDefined();
      expect(decision.timestamp).toBeDefined();
    });
  });

  // ====== COLLECTIVE > INDIVIDUAL TESTS ======

  describe('Collective Beats Individual', () => {
    it('committee has lower variance than individual agents', async () => {
      const committee = await createCommittee();

      // Run 100 simulated decisions
      const committeeReturns: number[] = [];
      const agent1Returns: number[] = [];

      for (let i = 0; i < 100; i++) {
        const signal = await generateRandomSignal();
        const votes = await committee.collectVotes(signal);
        const decision = await committee.makeDecision(votes);

        // Simulate outcome
        const outcome = simulateOutcome(decision);
        committeeReturns.push(outcome.pnl_pct);

        // What would agent 1 have done alone?
        const agent1Solo = simulateOutcome({
          ...decision,
          decision: votes.find(v => v.agent_id === 'a1')?.direction || 'WAIT'
        });
        agent1Returns.push(agent1Solo.pnl_pct);
      }

      const committeeStdDev = standardDeviation(committeeReturns);
      const agent1StdDev = standardDeviation(agent1Returns);

      // Committee should have lower variance
      expect(committeeStdDev).toBeLessThan(agent1StdDev);
    });
  });
});
```

---

## Summary: Implementation Order

### Phase 1 Complete → Move to Phase 2

| Layer | Priority | Est. Effort | Dependencies |
|-------|----------|-------------|--------------|
| **Layer 5: Tournament** | P0 | 2-3 days | Pattern fitness (done) |
| **Layer 6: Coaches** | P1 | 3-4 days | Layer 5 (agents must compete first) |
| **Layer 7: Committee** | P1 | 4-5 days | Layer 6 (need rosters for committee) |

### Test File Locations

```
v3/cloudflare-agents/tests/soundness/
├── tournament.test.ts          # Layer 5 EDD tests
├── coaching.test.ts            # Layer 6 EDD tests
└── committee.test.ts           # Layer 7 EDD tests
```

### Key Implementation Files

```
v3/cloudflare-agents/
├── tournament/
│   └── tournament-orchestrator.ts
├── coaching/
│   ├── coach-do.ts
│   └── coach-league.ts
└── committee/
    └── committee-do.ts
```

---

*Created: 2025-12-27*
