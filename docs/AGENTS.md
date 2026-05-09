# Fast_Swarm Agents

**Definition**: Autonomous trading entities that evolve through natural selection
**Storage**: PostgreSQL with JSONB traits
**Lifecycle**: Spawn → Backtest → Rank → Cull/Reproduce

---

## Agent Model

```python
class Agent(SQLModel, table=True):
    # Identity
    agent_id: str = Field(primary_key=True)
    generation: int = Field(default=1)
    parent_a_id: Optional[str] = None
    parent_b_id: Optional[str] = None

    # Configuration
    traits: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    pattern_weights: Dict[str, float] = Field(default={}, sa_column=Column(JSONB))
    trading_philosophy: Optional[str] = None  # LLM generated

    # Performance Metrics
    fitness_score: float = Field(default=0.0)
    sortino_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None
    max_drawdown_pct: float = Field(default=0.0)
    annualized_roi_pct: float = Field(default=0.0)
    alpha: Optional[float] = None  # vs buy & hold

    # Status
    level: int = Field(default=1)          # Quintile tier (0-4)
    status: str = Field(default="active")  # active, culled
    backtest_count: int = Field(default=0)
    last_backtest_at: Optional[datetime] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

---

## Agent Traits

Traits are stored as JSONB with mostly **numerical values (0-1)**:

### Core Trading Traits

| Trait | Type | Range | Description |
|-------|------|-------|-------------|
| `risk_tolerance` | float | 0-1 | Conservative (0) to aggressive (1) |
| `position_sizing` | float | 0-1 | Fraction of capital per trade |
| `stop_loss_pct` | float | 0.01-0.20 | Stop loss percentage |
| `take_profit_pct` | float | 0.05-0.50 | Take profit percentage |
| `holding_period` | float | 0-1 | Scalper (0) to swing trader (1) |

### Strategy Traits

| Trait | Type | Range | Description |
|-------|------|-------|-------------|
| `trend_following` | float | 0-1 | Trend (1) vs mean reversion (0) |
| `momentum_weight` | float | 0-1 | Weight on momentum signals |
| `volatility_preference` | float | 0-1 | Avoid (0) vs seek (1) volatility |
| `regime_adaptability` | float | 0-1 | How much to adjust by regime |

### Example Traits Object

```json
{
    "risk_tolerance": 0.65,
    "position_sizing": 0.40,
    "stop_loss_pct": 0.05,
    "take_profit_pct": 0.15,
    "holding_period": 0.50,
    "trend_following": 0.70,
    "momentum_weight": 0.55,
    "volatility_preference": 0.45,
    "regime_adaptability": 0.60
}
```

---

## Pattern Weights

Each agent has weighted pattern assignments:

```json
{
    "pattern_id_abc123": 0.8,
    "pattern_id_def456": 0.5,
    "pattern_id_ghi789": 0.3
}
```

- Higher weight = stronger influence on decisions
- Patterns can be shared across agents
- Weights evolve through reproduction

---

## Trading Philosophy

LLM-generated narrative describing agent behavior:

```python
# Example philosophy
"""
This agent is a moderate risk-taker with a strong trend-following bias.
It prefers momentum-based entries with tight stops and lets winners run.
Best suited for bull market conditions with clear directional moves.
"""
```

**Generation Process:**
1. Collect agent traits
2. Send to LLM with prompt template
3. Store resulting description

**Status**: Getting prod ready (not yet in production)

---

## Agent Lifecycle

### 1. Spawning

New agents created via:
- **Genesis**: Initial population creation
- **Reproduction**: Offspring from two parents
- **Random Spawn**: Fill population gaps

```python
# spawn_service.py
async def spawn_agent(session) -> Agent:
    agent = Agent(
        agent_id=generate_id(),
        generation=1,
        traits=generate_random_traits(),
        pattern_weights=assign_random_patterns(),
        status="active"
    )
    session.add(agent)
    await session.commit()
    return agent
```

### 2. Backtesting

Agents tested across historical windows:

```python
# backtest_service.py
async def backtest_agent(agent: Agent, windows: List[Window]) -> None:
    results = []
    for window in windows:
        result = run_backtest(agent, window)
        results.append(result)

    # Update agent metrics
    agent.sortino_ratio = calculate_sortino(results)
    agent.alpha = calculate_alpha(results)
    agent.max_drawdown_pct = calculate_max_drawdown(results)
    agent.fitness_score = calculate_composite_fitness(results)
    agent.backtest_count += 1
    agent.last_backtest_at = datetime.utcnow()
```

### 3. Ranking

Agents assigned to quintile tiers:

| Tier | Percentile | Status |
|------|------------|--------|
| 4 | Top 20% | Elite |
| 3 | 60-80% | Strong |
| 2 | 40-60% | Average |
| 1 | 20-40% | Weak |
| 0 | Bottom 20% | Cull candidate |

### 4. Culling

Bottom performers removed (soft delete):

```python
# cull_service.py
async def cull_agent(session, agent: Agent) -> None:
    agent.status = "culled"
    await session.commit()
    # Agent preserved for historical analysis
```

### 5. Reproduction

Top performers create offspring:

```python
# spawn_service.py
async def reproduce(parent_a: Agent, parent_b: Agent) -> Agent:
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
```

---

## Agent Services

### Core Services

| Service | File | Purpose |
|---------|------|---------|
| `agent_service` | `agent_service.py` | High-level operations |
| `agent_crud` | `agent_crud.py` | Low-level DB operations |
| `spawn_service` | `spawn_service.py` | Agent creation |
| `cull_service` | `cull_service.py` | Agent removal |
| `fitness_service` | `fitness_service.py` | Fitness calculation |
| `ranking_service` | `ranking_service.py` | Tier assignment |
| `backtest_service` | `backtest_service.py` | Run backtests |
| `trait_service` | `trait_service.py` | Trait management |
| `memory_service` | `memory_service.py` | Agent learning |

### Hivemind Services (Partial Implementation)

| Service | File | Purpose |
|---------|------|---------|
| `governance_service` | `Hivemind/Services/governance_service.py` | Committee voting |

### Coach Services

Coaches manage **Hivemind roster** - they decide which agents join/leave the committee:

```python
# Coaches/
# - Select agents for Hivemind committee
# - Remove underperformers from committee
# - Balance committee diversity
```

---

## API Endpoints

### List Agents

```bash
GET /agents

Response:
{
    "agents": [
        {
            "agent_id": "agent_abc123",
            "generation": 5,
            "fitness_score": 0.82,
            "level": 4,
            "status": "active"
        }
    ],
    "total": 500
}
```

### Get Agent Details

```bash
GET /agents/{agent_id}

Response:
{
    "agent_id": "agent_abc123",
    "generation": 5,
    "parent_a_id": "agent_xyz789",
    "parent_b_id": "agent_def456",
    "traits": {
        "risk_tolerance": 0.65,
        "trend_following": 0.70
    },
    "pattern_weights": {
        "pattern_001": 0.8,
        "pattern_002": 0.5
    },
    "trading_philosophy": "Moderate risk trend-follower...",
    "fitness_score": 0.82,
    "sortino_ratio": 2.1,
    "alpha": 0.15,
    "level": 4,
    "status": "active",
    "backtest_count": 47,
    "created_at": "2026-01-10T08:30:00Z"
}
```

### Population Statistics

```bash
GET /agents/stats/average

Response:
{
    "total_active": 500,
    "total_culled": 1250,
    "avg_fitness": 0.54,
    "avg_sortino": 1.2,
    "avg_generation": 8.3,
    "tier_distribution": {
        "4": 100,
        "3": 100,
        "2": 100,
        "1": 100,
        "0": 100
    }
}
```

### Spawn Agents

```bash
POST /actions/spawn

{
    "count": 50,
    "assets": ["BTC", "ETH"]
}

Response:
{
    "agents_spawned": 50,
    "new_population_size": 550
}
```

### Cull Agents

```bash
POST /actions/cull

{
    "threshold_tier": 0,
    "dry_run": false
}

Response:
{
    "agents_culled": 100,
    "new_population_size": 450
}
```

---

## Database Queries

### Get Active Agents

```python
statement = (
    select(Agent)
    .where(Agent.status == "active")
    .order_by(desc(Agent.fitness_score))
)
```

### Get Elite Agents (Tier 4)

```python
statement = (
    select(Agent)
    .where(Agent.status == "active")
    .where(Agent.level == 4)
    .order_by(desc(Agent.fitness_score))
)
```

### Get Agent Lineage

```python
async def get_lineage(session, agent_id: str) -> List[Agent]:
    """Trace agent ancestry."""
    lineage = []
    current = await get_agent(session, agent_id)

    while current and current.parent_a_id:
        parent = await get_agent(session, current.parent_a_id)
        if parent:
            lineage.append(parent)
            current = parent
        else:
            break

    return lineage
```

---

## Fitness Calculation

```python
def calculate_composite_fitness(agent: Agent) -> float:
    """
    Composite fitness from Sortino, Alpha, and drawdown.
    """
    # Normalize components to 0-1 range
    sortino_norm = min(agent.sortino_ratio / 3.0, 1.0) if agent.sortino_ratio else 0
    alpha_norm = min(max(agent.alpha + 0.2, 0) / 0.4, 1.0) if agent.alpha else 0
    dd_score = 1 - min(agent.max_drawdown_pct / 0.3, 1.0)

    # Weighted combination
    fitness = (
        sortino_norm * 0.4 +
        alpha_norm * 0.4 +
        dd_score * 0.2
    )

    return round(fitness, 4)
```

---

## Key Design Decisions

### Why JSONB for Traits?
- Flexible schema evolution
- No migrations for new traits
- Efficient PostgreSQL indexing

### Why Soft Delete?
- Preserves historical data
- Enables lineage analysis
- Allows resurrection if needed

### Why LLM Philosophy?
- Human-readable agent descriptions
- Helps understand agent behavior
- Useful for debugging decisions

### Why 5 Tiers?
- More granular than binary
- Clear promotion paths
- Balances exploration/exploitation

---

*Last Updated: 2026-01-13*
