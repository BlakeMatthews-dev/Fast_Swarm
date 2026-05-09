# .claude/CLAUDE.md

> **See `/CLAUDE.md` at project root for main guidance.**
> This file contains supplementary technical details.

---

## Quick Reference

### Start Development

```bash
# 1. Start PostgreSQL (auto-starts via Docker.py if needed)
cd ../local-utilities && docker-compose up -d

# 2. Run server
uvicorn Fast_Swarm.Main:app --reload

# 3. Open docs
http://localhost:8000/docs
```

### Run Tests

```bash
pytest Fast_Swarm/Tests/                    # All tests
pytest Fast_Swarm/Tests/Soundness/          # EDD tests
pytest Fast_Swarm/Tests/Triage/             # Behavioral tests
pytest Fast_Swarm/Tests/test_sanity.py -k test_name  # Specific
```

---

## Current System Status

| Component | Status | Notes |
|-----------|--------|-------|
| Evolution Loop | ✅ Partial | Runs but some components need fixes |
| Pattern Discovery | ✅ Active | Chaos analysis fully wired |
| AI Consultation | ✅ Active | Used during backtests |
| Exchange Streams | ✅ Active | 4 exchanges connected |
| LLM Integration | 🔄 WIP | Getting prod ready |
| Hivemind Committee | 🔄 Partial | Scaffolded, not complete |
| Dashboard | 🔄 WIP | Intended to be primary UI |
| Live Trading | ⏸️ None | Backtest only |

---

## Key Metrics (Correct Info)

**Primary Fitness Metrics:**
- **Sortino Ratio** - NOT Sharpe (we want upside volatility)
- **Alpha** - Agent CAGR minus Buy&Hold CAGR

**Ranking:**
- **5-Tier Quintile** system (0-4), not 3-tier
- **Regime-based** fitness (bull, bear, chop, flat)
- **Time-based** regime detection (known historical periods)

**ELO** is ONLY for Hivemind committee voting, not general evolution.

---

## Database Tables

### Core Tables

| Table | Purpose |
|-------|---------|
| `agents` | Trading agents with traits, fitness |
| `patterns` | Trading patterns with conditions |
| `backtest_trades_unified` | All backtest trade records |
| `enhanced_candles` | OHLCV + pre-computed indicators |
| `evolution_cycles` | Evolution run tracking |
| `system_config` | Runtime configuration (JSONB) |

### Key Indexes

```sql
idx_agents_status_fitness    -- Fast agent queries
idx_patterns_origin          -- Filter by discovery method
idx_backtest_trades_agent    -- Trades by agent
```

---

## Background Loops

Started in `Main.py` lifespan:

| Loop | Interval | Purpose |
|------|----------|---------|
| `evolution_loop()` | 5 gen + 2min cooldown | Evolve population |
| `pattern_discovery_loop()` | 6 hours | Create patterns via chaos |
| `pattern_backtest_loop()` | 10 minutes | Test patterns |
| `window_pool_refresh_loop()` | Daily 3am | Maintain coverage |

---

## Domain Directories

```
Agents/
├── Models/          # SQLModel + Pydantic
├── Services/        # Business logic
├── Routers/         # FastAPI endpoints
├── Hivemind/        # Committee (partial)
└── Coaches/         # Roster management

Patterns/
├── Models/
├── Services/
└── Routers/

Infrastructure/
├── Services/        # Streams, collection, backfill
└── Routers/

System/
├── Services/        # Robustness, wisdom, crucible
└── Routers/
```

---

## What NOT to Do

Based on project requirements:

1. **NO train/test split** - Pure backtesting, no ML training phases
2. **NO deterministic window pools** - Randomness is the point (signal from noise)
3. **NO Sharpe as primary** - Use Sortino (allows upside volatility)
4. **NO Cloudflare references** - FastAPI is the system now
5. **NO Redis** - PostgreSQL only

---

## Legacy/Deprecated

See `docs/DEPRECATED.md` for historical reference:

- ❌ Cloudflare Workers architecture
- ❌ D1 database shards
- ❌ Redis memory system
- ❌ `local_agents/` directory (legacy code)

---

## File Locations

| What | Where |
|------|-------|
| Main app | `Main.py` |
| Database | `Database.py` |
| Singletons | `Dependencies.py` |
| Docker setup | `Docker.py` |
| Exchange clients | `exchanges/*.py` |
| Tests | `Tests/` |
| Documentation | `docs/` |

---

*Last Updated: 2026-01-13*
