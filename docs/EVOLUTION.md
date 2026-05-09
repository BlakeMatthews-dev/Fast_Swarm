# Fast_Swarm Evolution System

**Purpose**: Evolve trading agents through natural selection
**Status**: ✅ Partially Working (core loop runs, some components need fixes)
**Loop Interval**: 5 generations + 2 minute cooldown

---

## Core Philosophy

> **"Alpha is emergent."** Instead of building one "perfect" predictor, we simulate an ecosystem of diverse, imperfect agents. Individually flawed, together they reveal high-probability market moves.

### Tenets

1. **Diversity > Optimization**: Over-optimizing leads to overfitting. We prioritize diversity.
2. **Evolution over Design**: We don't hard-code "winning" strategies. We code the rules of evolution.
3. **Signal from Noise**: Randomness is the point. Window pools provide coverage, NOT determinism.

---

## Evolution Loop

```python
async def evolution_loop():
    """
    Main evolution loop - runs continuously in background.

    Started in Main.py lifespan.
    """
    while True:
        for generation in range(GENERATIONS_PER_CYCLE):  # Default: 5
            # Phase 1: Backtest all active agents
            await backtest_population()

            # Phase 2: Rank by fitness (Sortino + Alpha)
            await rank_agents()

            # Phase 3: Assign quintile tiers (0-4)
            await assign_tiers()

            # Phase 4: Cull bottom performers (Tier 0)
            await cull_weak_agents()

            # Phase 5: Reproduce top performers (Tier 3-4)
            await reproduce_elite_agents()

            # Phase 6: Crucible check (every 5th generation)
            if generation % 5 == 0:
                await run_crucible()

        # Cooldown between cycles
        await asyncio.sleep(COOLDOWN_SECONDS)  # Default: 120
```

---

## Reproduction Mechanics

### Crossover + Mutation + Pattern Recombination

When two elite agents reproduce:

```python
async def reproduce(parent_a: Agent, parent_b: Agent) -> Agent:
    """
    Create offspring from two parent agents.

    Combines:
    1. Trait crossover (blend parent traits)
    2. Mutation (small random changes)
    3. Pattern recombination (inherit patterns from both)
    """
    child = Agent(
        agent_id=generate_id(),
        generation=max(parent_a.generation, parent_b.generation) + 1,
        parent_a_id=parent_a.agent_id,
        parent_b_id=parent_b.agent_id,
        traits=crossover_traits(parent_a.traits, parent_b.traits),
        pattern_weights=recombine_patterns(
            parent_a.pattern_weights,
            parent_b.pattern_weights
        ),
        status="active"
    )
    return child


def crossover_traits(traits_a: dict, traits_b: dict) -> dict:
    """
    Blend traits from both parents with mutation.

    For each trait:
    - 50% chance to inherit from parent A or B
    - Small mutation applied (±5% of range)
    """
    child_traits = {}

    for trait_name in traits_a.keys():
        # Pick parent
        if random.random() < 0.5:
            base_value = traits_a[trait_name]
        else:
            base_value = traits_b[trait_name]

        # Apply mutation
        mutation = random.gauss(0, MUTATION_RATE)  # Default: 0.15
        child_traits[trait_name] = clamp(base_value + mutation, 0, 1)

    return child_traits


def recombine_patterns(weights_a: dict, weights_b: dict) -> dict:
    """
    Combine pattern weights from both parents.

    - Patterns present in both get averaged weight
    - Patterns in only one get inherited at 50% weight
    - Random chance to drop low-weight patterns
    """
    combined = {}

    all_patterns = set(weights_a.keys()) | set(weights_b.keys())

    for pattern_id in all_patterns:
        weight_a = weights_a.get(pattern_id, 0)
        weight_b = weights_b.get(pattern_id, 0)

        if weight_a > 0 and weight_b > 0:
            # Both parents have it - average
            combined[pattern_id] = (weight_a + weight_b) / 2
        else:
            # Only one parent - inherit at reduced weight
            combined[pattern_id] = max(weight_a, weight_b) * 0.5

        # Chance to drop low-weight patterns
        if combined[pattern_id] < 0.2 and random.random() < 0.3:
            del combined[pattern_id]

    return combined
```

---

## 5-Tier Quintile System

Agents are ranked into quintiles based on fitness score:

| Tier | Percentile | Description | Actions |
|------|------------|-------------|---------|
| 4 | Top 20% | Elite | Reproduce, Crucible candidates |
| 3 | 60-80% | Strong | Reproduce with Tier 4 |
| 2 | 40-60% | Average | Survive, no reproduction |
| 1 | 20-40% | Weak | Survive with warning |
| 0 | Bottom 20% | Failing | Culled (soft delete) |

```python
async def assign_tiers(session) -> None:
    """Assign quintile tiers based on fitness ranking."""
    agents = await get_active_agents(session)
    sorted_agents = sorted(agents, key=lambda a: a.fitness_score, reverse=True)

    total = len(sorted_agents)
    for i, agent in enumerate(sorted_agents):
        percentile = i / total

        if percentile < 0.2:
            agent.level = 4  # Top 20%
        elif percentile < 0.4:
            agent.level = 3  # 60-80%
        elif percentile < 0.6:
            agent.level = 2  # 40-60%
        elif percentile < 0.8:
            agent.level = 1  # 20-40%
        else:
            agent.level = 0  # Bottom 20%

    await session.commit()
```

---

## Time-Based Regime Classification

Regimes are detected using **known historical periods**, not dynamic indicators:

| Regime | Description | Example Periods |
|--------|-------------|-----------------|
| Bull | Strong uptrend | 2021 Q1, 2024 Q1 |
| Bear | Strong downtrend | 2022 Q2-Q4, COVID crash |
| Chop | High volatility, no direction | Most consolidation periods |
| Flat | Low volatility sideways | 2023 summer |

```python
# Canonical periods are pre-defined, not detected dynamically
CANONICAL_PERIODS = [
    {"start": "2021-01-01", "end": "2021-04-15", "regime": "bull"},
    {"start": "2022-04-01", "end": "2022-12-31", "regime": "bear"},
    {"start": "2023-06-01", "end": "2023-09-01", "regime": "flat"},
    # ... more periods
]
```

**Why Time-Based?**
- More deterministic than indicator-based detection
- Avoids regime detection becoming another prediction problem
- Known historical periods allow better validation
- Prevents overfitting to regime detector quirks

---

## Evolution Run Learnings

From a 17-generation run with 2,789 agents and 1.9M trades:

### Winning Trait Profile

| Trait | Top 50 Avg | Bottom 50 Avg | Insight |
|-------|-----------|--------------|---------|
| `risk_tolerance` | **0.953** | 0.493 | High risk wins |
| `hold_duration_bias` | **0.826** | 0.490 | Patient exits win |
| `exit_aggression` | **0.177** | 0.511 | Low exit aggression wins |
| `lookback_preference` | **0.316** | 0.565 | Short lookback wins |
| `sentiment_weight` | **0.681** | 0.485 | Sentiment matters |
| `profit_target_greed` | **0.702** | 0.526 | Let winners run |

### Key Findings

1. **High risk + patient exits wins**: Top performers take big positions (risk=0.95) but exit slowly (exit_agg=0.18)

2. **Hold longer, look shorter**: Long holding (0.83) with short lookback (0.32) = momentum following

3. **Sentiment contrarians**: Weight sentiment highly (0.68) but act contrarian (0.65)

4. **Entry aggression doesn't matter**: Both groups ~0.52 - exit timing matters more than entry

### Confidence Calibration

| Confidence Range | Trades | Avg PnL | Win Rate |
|-----------------|--------|---------|----------|
| 0.0-0.2 | 11,247 | -0.27% | 27.4% |
| 0.2-0.4 | 15,521 | -0.22% | 31.6% |
| 0.4-0.6 | 186,942 | -0.07% | 29.2% |
| **0.6-0.8** | **434,393** | **+0.48%** | **47.8%** |
| 0.8-1.0 | 1,284,030 | +0.29% | 43.2% |

**Sweet spot is 0.6-0.8 confidence** - very high confidence (0.8+) shows overconfidence bias.

### Asset Performance

| Asset | Trades | Avg PnL | Win Rate |
|-------|--------|---------|----------|
| ETH | 160,637 | +1.98% | 49.7% |
| SOL | 196,203 | +1.29% | 49.4% |
| BTC | 1,575,299 | -0.01% | 41.1% |

**BTC is hardest** - significantly lower win rate. ETH and SOL more profitable.

---

## Recommended Trait Distributions

Based on evolution learnings, bias initial trait distributions:

```python
OPTIMIZED_TRAIT_RANGES = {
    'risk_tolerance': (0.7, 1.0),      # Not 0-1
    'hold_duration_bias': (0.6, 1.0),  # Not 0-1
    'exit_aggression': (0.0, 0.4),     # Lower is better!
    'lookback_preference': (0.1, 0.5), # Shorter lookback wins
    'sentiment_weight': (0.5, 0.9),    # High sentiment weight
    'profit_target_greed': (0.5, 0.9), # Let winners run
}
```

---

## Window Pool System

Windows are random historical periods used for backtesting:

### Purpose
- **Coverage**: Test agents across diverse market conditions
- **Performance**: Pre-compute indicators for common windows
- **NOT Determinism**: Randomness is a feature, not a bug

### Window Pool Refresh

```python
# Runs daily at 3am
async def window_pool_refresh_loop():
    """Maintain fresh pool of testing windows."""
    while True:
        await refresh_window_pool()
        await asyncio.sleep(until_3am())
```

---

## Culling (Soft Delete)

Bottom performers are soft-deleted, not removed:

```python
async def cull_agent(session, agent: Agent) -> None:
    """Mark agent as culled (preserved for analysis)."""
    agent.status = "culled"
    agent.culled_at = datetime.utcnow()
    agent.culled_reason = "tier_0_evolution"
    await session.commit()
```

**Why Soft Delete?**
- Preserves historical data
- Enables lineage analysis
- Allows resurrection if needed

---

## Background Loops

Started in `Main.py` lifespan:

| Loop | Interval | Purpose |
|------|----------|---------|
| `evolution_loop()` | 5 gen + 2min cooldown | Evolve population |
| `pattern_discovery_loop()` | 6 hours | Chaos analysis patterns |
| `pattern_backtest_loop()` | 10 minutes | Test patterns |
| `window_pool_refresh_loop()` | Daily 3am | Maintain window pool |

---

## API Endpoints

### Start Evolution

```bash
POST /evolution/start
{
    "generations": 5,
    "population_size": 500,
    "elite_percent": 0.20,
    "mutation_rate": 0.15,
    "assets": ["BTC", "ETH", "SOL"]
}
```

### Get Status

```bash
GET /evolution/status

Response:
{
    "is_running": true,
    "cycle_id": "cycle_abc123",
    "current_generation": 3,
    "total_generations": 5,
    "phase": "backtest",
    "agents_processed": 250,
    "agents_total": 500
}
```

---

*Last Updated: 2026-01-13*
