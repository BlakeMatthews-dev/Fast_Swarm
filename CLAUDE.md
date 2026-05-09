# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## System Overview

Fast_Swarm is a **personal evolutionary trading research system** (single user). It discovers trading patterns through chaos analysis and evolves agents via natural selection.

**Current Status:**
- ✅ Evolution loop - Partially working
- ✅ Chaos analysis pattern discovery - Active
- ✅ AI consultation in backtests - Active
- ✅ 4 exchange WebSocket streams - Active
- 🔄 LLM integration - Getting prod ready
- 🔄 Hivemind committee - Partial implementation
- 🔄 Dashboard - WIP
- ⏸️ Live trading - Not implemented (backtest only)

## Commands

```bash
# Start PostgreSQL (from parent directory)
cd ../local-utilities && docker-compose up -d

# Run development server
uvicorn Fast_Swarm.Main:app --reload
# Access docs at http://localhost:8000/docs

# Run all tests
pytest Fast_Swarm/Tests/

# Run specific test file
pytest Fast_Swarm/Tests/test_sanity.py

# Run specific test
pytest Fast_Swarm/Tests/test_sanity.py -k test_root_endpoint

# Run soundness/EDD tests
pytest Fast_Swarm/Tests/Soundness/

# Run triage tests (economic validity, behavioral logic)
pytest Fast_Swarm/Tests/Triage/
```

## Architecture

Fast_Swarm is a FastAPI control plane wrapping Coinswarm's evolutionary trading system. All data flows through PostgreSQL via async SQLModel.

```
Client (HTTP)
    |
FastAPI (Main.Py)
    |
Routers (API endpoints)
    |
Services (business logic)
    |
SQLModel/asyncpg
    |
PostgreSQL
```

### Core Files

| File | Purpose |
|------|---------|
| `Main.Py` | FastAPI app entry, lifespan management, router registration |
| `Database.py` | Async PostgreSQL engine, session factory |
| `Dependencies.py` | Global singletons: StreamManager, DataCollector, RobustnessService |

### Background Loops (Main.py lifespan)

| Loop | Frequency | Purpose |
|------|-----------|---------|
| `evolution_loop()` | 5 gen/cycle, 2min cooldown | Evolve agent population |
| `pattern_discovery_loop()` | Every 6 hours | Create new patterns via chaos analysis |
| `pattern_backtest_loop()` | Every 10 minutes | Test patterns, promote tiers |
| `window_pool_refresh_loop()` | Daily at 3am | Maintain backtest coverage |

### Exchanges (WebSocket Streams)

4 exchange integrations in `exchanges/`:
- **Binance** - `binance_ws.py`
- **Coinbase** - `coinbase_ws.py`
- **dYdX** - `dydx_ws.py`
- **Hyperliquid** - `hyperliquid_ws.py`

### Domain Structure

Each domain follows `Models/ -> Services/ -> Routers/` pattern:

- **Agents/** - Agent CRUD, stats, evolution, spawning, culling
  - `Hivemind/` - Committee governance (partial implementation)
  - `Coaches/` - Manage which agents join Hivemind roster
- **Patterns/** - Trading pattern management and discovery
- **Trades/** - Trade history queries
- **Evolution/** - Evolution cycle monitoring
- **Infrastructure/** - Market data, exchange integration, WebSocket streams
- **System/** - Health endpoints, robustness testing, wisdom extraction
- **Tests/** - Unit, Integration, Soundness (EDD), Triage, Router tests

### API Routes

```
GET  /agents              - List active agents
GET  /agents/{id}         - Get agent details
GET  /agents/stats/average - Population statistics

GET  /patterns            - List patterns
GET  /patterns/{id}       - Pattern details

GET  /trades              - Recent trades (filters: agent_id, asset, limit)

POST /evolution/start     - Start evolution cycle (background)
POST /actions/spawn       - Create new agents
POST /actions/backtest    - Run backtest
POST /actions/cull        - Remove weak agents

GET  /system/health       - System health status
```

## Key Metrics

**Primary fitness metrics** (NOT Sharpe/win rate):
- **Sortino Ratio** - Risk-adjusted return using downside deviation only
- **Alpha** - `Agent CAGR - Asset Buy&Hold CAGR` (excess return vs holding)

**Ranking System:**
- **5-Tier Quintile** - Patterns/agents ranked into quintiles (0-4) by percentile
- **Regime-based** - Fitness scored per regime (bull, bear, chop, flat)
- **Time-based regimes** - Using known historical periods, not dynamic indicators

**ELO** is used ONLY for Hivemind committee voting, not general evolution.

## Key Patterns

### SQLModel with JSONB

Agent traits are stored as JSONB for flexible schema:

```python
from sqlalchemy.dialects.postgresql import JSONB

class Agent(SQLModel, table=True):
    traits: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
```

### Async Database Sessions

```python
from Fast_Swarm.Database import get_session

@router.get("/")
async def read_items(session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(Model))
    return result.all()
```

### Division Safety

All metrics calculations must guard against division by zero (see `Tests/Soundness/Foundations/test_div_safety.py`):

```python
sharpe = (mean_return / std_return) if std_return > 0 else 0
```

## Environment Variables

```
POSTGRES_USER=coinswarm
POSTGRES_PASSWORD=coinswarm_dev_2024
POSTGRES_DB=coinswarm
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

**NOTE: PostgreSQL ONLY** - No SQLite. All environments (dev, test, prod) use PostgreSQL.

## CRITICAL: No Train/Test Split Concepts

**DO NOT** add train/test split, walk-forward validation, or similar ML training concepts without explicit user confirmation. This system does **pure backtesting** - there is no "training" phase. All historical data is used for testing/evaluation only.

- ❌ No `WALK_FORWARD_SPLIT`
- ❌ No `train_data` / `test_data` separation
- ❌ No "holdout" sets
- ✅ All data is for backtesting/evaluation

If you think such a concept is needed, **ASK FIRST** before implementing.

## Evidence-Driven Development (EDD)

Tests in `Tests/Soundness/` validate economic correctness beyond functional tests:

- **Determinism** - Same inputs produce same outputs
- **Division Safety** - No crashes on zero volatility
- **Statistical Sanity** - Sortino 0.5-3.0, drawdown less than 20%
- **Economic Validity** - No lookahead bias, realistic slippage

Run soundness tests before commits that touch metrics or backtest logic.

## Core Philosophy: Signal from Noise

**The entire point of Coinswarm is to find patterns from chaos.**

- Window pool is for **coverage + performance**, NOT deterministic reproducibility
- Removing randomness defeats the purpose
- We discover patterns humans haven't found by testing millions of random combinations
- Patterns must prove themselves across diverse market conditions

This is like AlphaGo discovering novel strategies through self-play - we discover trading patterns through chaos exploration.

## Documentation

Comprehensive technical documentation in `docs/`:

| Document | Purpose |
|----------|---------|
| `docs/ARCHITECTURE.md` | System architecture, philosophy, domain structure |
| `docs/EVOLUTION.md` | Evolution loop, reproduction, tier system, learnings |
| `docs/AGENTS.md` | Agent model, traits, lifecycle |
| `docs/PATTERNS.md` | Pattern conditions, slot system, discovery |
| `docs/METRICS.md` | Sortino, Alpha, Kelly Criterion, fitness scoring |
| `docs/EXCHANGES.md` | WebSocket integration, 4 exchanges |
| `docs/API.md` | FastAPI endpoints reference |
| `docs/CRUCIBLE.md` | Wisdom extraction, clone-and-retire |
| `docs/DEPRECATED.md` | Legacy systems (Cloudflare, Redis) |

## Output Formatting

**NO UNICODE OR EMOJI** - This project is developed on Windows with cp1252 encoding. Do NOT use:

- Box drawing characters (like those in polars DataFrame output)
- Emoji in code output or print statements
- Non-ASCII characters in any generated output

Use plain ASCII for all terminal output: `=`, `-`, `|`, `+` for tables and separators.

## Legacy/Deprecated

The following are **NOT part of the current system** (see `docs/DEPRECATED.md`):
- ❌ Cloudflare Workers architecture (docs reference this, but FastAPI is primary)
- ❌ Redis for vector memory (removed, PostgreSQL only)
- ❌ D1/SQLite databases (PostgreSQL only)
- ❌ `local_agents/` directory (legacy code, partially imported)
