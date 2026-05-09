# Deprecated Architecture Reference

**Status**: HISTORICAL REFERENCE ONLY - This content describes systems that are no longer part of Fast_Swarm.

**Last Updated**: 2026-01-13

---

## Why This File Exists

Fast_Swarm evolved from an earlier Cloudflare Workers-based architecture. Some documentation files still reference this legacy system. This file preserves that historical context while making clear it's no longer active.

**Current System**: FastAPI + PostgreSQL (see `CLAUDE.md`)

---

## Deprecated: Cloudflare Workers Architecture

The following was the original edge computing architecture, now replaced by FastAPI:

### Original Stack (No Longer Used)
- **Cloudflare Workers** - Edge compute for evolution agents
- **Cloudflare D1** - SQLite-based database shards
- **Durable Objects** - Stateful agent instances
- **KV Namespace** - Historical data caching

### Why Deprecated
- Complexity of distributed edge system wasn't needed for single-user bot
- FastAPI + PostgreSQL provides simpler, more debuggable architecture
- Local development is easier without Cloudflare emulation

### Legacy Worker Files (May Still Exist in Codebase)
- `evolution-agent-simple.ts` - Main evolution Durable Object
- `simulation-competition-worker.ts` - Agent competition orchestration
- `pattern-mining-worker.ts` - Pattern discovery
- `backtest-worker.ts` - Pattern backtesting
- `historical-data-collection-cron.ts` - OHLCV collection

---

## Deprecated: Redis Memory System

The following Redis-based memory system was planned but never fully implemented and has been removed:

### Original Design (Never Deployed)
```
Quorum-Governed Memory System
├── Episodic Memory (per-bot, Redis hash)
├── Pattern Memory (shared, Redis vectors)
├── Regime Memory (shared, real-time)
└── HNSW vector index for kNN retrieval
```

### Redis Schema (Historical)
```redis
# Episodic memory entry (REMOVED)
hash:epi:{bot_id}:{entry_id}
  v        BLOB          # float32[384] embedding
  ts       NUMERIC       # epoch seconds
  sym      TAG           # symbol
  reg      TAG           # regime
  a        TAG           # action
  pnl      NUMERIC       # realized PnL
  w        NUMERIC       # weight

# Pattern statistics (REMOVED)
hash:pattern:{pattern_id}
  n, mu, sig, sr, t05, t95, slip_mu, reg, last
```

### Why Deprecated
- PostgreSQL with JSONB provides sufficient flexibility
- Vector search not needed for current pattern matching approach
- Reduced infrastructure complexity

---

## Deprecated: D1 Database Shards

The original system used Cloudflare D1 SQLite shards:

### Original Shard Layout (No Longer Used)
| Binding | Database | Contents |
|---------|----------|----------|
| `DATA_SHARD_1` | coinswarm-data-shard-1 | BTC, ETH, SOL OHLCV |
| `DATA_SHARD_2` | coinswarm-data-shard-2 | ETFs, ARB, OP data |
| `DATA_SHARD_3` | coinswarm-data-shard-3 | Solana tokens |
| `DATA_SHARD_4` | coinswarm-data-shard-4 | BSC DeFi tokens |
| `DB` | coinswarm-evolution | Main evolution tables |

### Current Approach
All data now lives in a single PostgreSQL database with proper indexing.

---

## Deprecated: Multi-Region Deployment

The original architecture planned for multi-region deployment:

### Original Plan (Not Implemented)
```
REGION 1: GCP us-east4 (Coinbase-optimized)
├── MCP Server → Coinbase: 2-5ms
├── Trading Agents
└── Risk Manager

REGION 2: GCP asia-northeast1 (Binance-optimized)
├── Binance Ingestor → Binance: 2-5ms
└── Data normalization
```

### Current Approach
Single-region deployment sufficient for personal bot use case.

---

## Deprecated: Complexity That Was Removed

| Feature | Status | Reason |
|---------|--------|--------|
| Multi-tenant architecture | Removed | Single user only |
| Rate limiting infrastructure | Removed | Not needed for personal use |
| Complex caching layers | Removed | PostgreSQL sufficient |
| Message queues (NATS) | Removed | Async Python tasks work fine |
| Geographic distribution | Removed | Single region sufficient |

---

## Legacy Code Paths

The following code paths may still exist but are not integrated:

### `local_agents/` Directory
- Ported from older version
- Never updated to current architecture
- Contains: `backtest/`, `trading_utilities/`, `prompts/`
- **Status**: Legacy, may be removed

### Genesis Scripts
- Various `genesis*.py` files exist
- Some are dead code
- Only agent spawning genesis is relevant

---

## Documentation Files to Review

These documentation files may contain outdated Cloudflare/Redis references:

- `Documentation/docs/ARCHITECTURE.md` - Extensive Cloudflare content
- `Documentation/docs/DEPLOYMENT.md` - Cloudflare deployment guides
- `Documentation/docs/API.md` - Cloudflare Workers API reference
- `.claude/COINSWARM_API_MAP.md` - May reference old architecture

---

## Migration Notes

If you encounter references to deprecated systems:

1. **Cloudflare Workers** → Use FastAPI services instead
2. **D1 Database** → Use PostgreSQL via `Database.py`
3. **Redis** → Use PostgreSQL JSONB fields
4. **Durable Objects** → Use Python classes with database persistence
5. **KV Namespace** → Use PostgreSQL tables
6. **Wrangler CLI** → Use `uvicorn` for development

---

*This file preserved for historical reference. The current system is documented in `CLAUDE.md` and `docs/ARCHITECTURE.md`.*
