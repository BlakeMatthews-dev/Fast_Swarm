# Fast_Swarm API Reference

**Framework**: FastAPI
**Base URL**: `http://localhost:8000`
**Documentation**: `http://localhost:8000/docs` (Swagger UI)

---

## Routers Overview

| Router | Prefix | Purpose |
|--------|--------|---------|
| `agent_router` | `/agents` | Agent CRUD and queries |
| `actions_router` | `/actions` | Spawn, backtest, cull operations |
| `evolution_router` | `/evolution` | Evolution control and status |
| `pattern_router` | `/patterns` | Pattern CRUD and queries |
| `trade_router` | `/trades` | Trade history queries |
| `system_router` | `/system` | Health and system status |
| `governance_router` | `/governance` | Hivemind committee (partial) |
| `market_data_router` | `/market-data` | Market data access |
| `exchange_router` | `/exchanges` | Exchange state |
| `sentiment_router` | `/sentiment` | Sentiment data (not used) |

---

## Agents API

### GET /agents

List active agents.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `status` | string | `active` | Filter by status |
| `tier` | int | - | Filter by tier (0-4) |
| `limit` | int | 100 | Max results |
| `offset` | int | 0 | Pagination offset |

**Response:**
```json
{
    "agents": [
        {
            "agent_id": "agent_abc123",
            "generation": 5,
            "fitness_score": 0.82,
            "sortino_ratio": 2.1,
            "alpha": 0.15,
            "level": 4,
            "status": "active",
            "backtest_count": 47,
            "created_at": "2026-01-10T08:30:00Z"
        }
    ],
    "total": 500,
    "limit": 100,
    "offset": 0
}
```

### GET /agents/{agent_id}

Get agent details.

**Response:**
```json
{
    "agent_id": "agent_abc123",
    "generation": 5,
    "parent_a_id": "agent_xyz789",
    "parent_b_id": "agent_def456",
    "traits": {
        "risk_tolerance": 0.65,
        "trend_following": 0.70,
        "position_sizing": 0.40
    },
    "pattern_weights": {
        "pattern_001": 0.8,
        "pattern_002": 0.5
    },
    "trading_philosophy": "Moderate risk trend-follower...",
    "fitness_score": 0.82,
    "sortino_ratio": 2.1,
    "calmar_ratio": 1.8,
    "max_drawdown_pct": 0.12,
    "annualized_roi_pct": 0.45,
    "alpha": 0.15,
    "level": 4,
    "status": "active",
    "backtest_count": 47,
    "last_backtest_at": "2026-01-13T10:00:00Z",
    "created_at": "2026-01-10T08:30:00Z"
}
```

### GET /agents/stats/average

Population statistics.

**Response:**
```json
{
    "total_active": 500,
    "total_culled": 1250,
    "avg_fitness": 0.54,
    "avg_sortino": 1.2,
    "avg_alpha": 0.08,
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

---

## Actions API

### POST /actions/spawn

Create new agents.

**Request:**
```json
{
    "count": 50,
    "assets": ["BTC", "ETH", "SOL"]
}
```

**Response:**
```json
{
    "agents_spawned": 50,
    "agent_ids": ["agent_001", "agent_002", ...],
    "new_population_size": 550
}
```

### POST /actions/backtest

Run backtest for agents.

**Request:**
```json
{
    "agent_ids": ["agent_abc123", "agent_def456"],
    "timeframe": "1h",
    "assets": ["BTC", "ETH"]
}
```

**Response:**
```json
{
    "backtests_completed": 2,
    "results": [
        {
            "agent_id": "agent_abc123",
            "sortino_ratio": 2.1,
            "alpha": 0.15,
            "trades": 47,
            "win_rate": 0.62
        }
    ]
}
```

### POST /actions/cull

Remove weak agents.

**Request:**
```json
{
    "threshold_tier": 0,
    "dry_run": false
}
```

**Response:**
```json
{
    "agents_culled": 100,
    "culled_ids": ["agent_001", "agent_002", ...],
    "new_population_size": 400
}
```

---

## Evolution API

### POST /evolution/start

Start evolution cycle.

**Request:**
```json
{
    "generations": 5,
    "population_size": 500,
    "elite_percent": 0.20,
    "survival_percent": 0.60,
    "mutation_rate": 0.15,
    "assets": ["BTC", "ETH", "SOL", "BNB"],
    "timeframe": "1h"
}
```

**Response:**
```json
{
    "message": "Evolution started",
    "cycle_id": "cycle_abc123",
    "generations": 5,
    "population_size": 500
}
```

### GET /evolution/status

Get evolution status.

**Response:**
```json
{
    "is_running": true,
    "cycle_id": "cycle_abc123",
    "current_generation": 3,
    "total_generations": 5,
    "phase": "backtest",
    "agents_processed": 250,
    "agents_total": 500,
    "started_at": "2026-01-13T10:00:00Z",
    "elapsed_seconds": 180
}
```

---

## Patterns API

### GET /patterns

List patterns.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `is_active` | bool | `true` | Filter by active status |
| `origin` | string | - | Filter by origin |
| `tier` | int | - | Filter by tier (0-4) |
| `symbol` | string | - | Filter by symbol |
| `limit` | int | 100 | Max results |

**Response:**
```json
{
    "patterns": [
        {
            "pattern_id": "pattern_abc123",
            "name": "RSI Oversold Momentum",
            "origin": "chaos_analysis",
            "symbol": "BTC",
            "timeframe": "1h",
            "fitness_score": 0.78,
            "tier": 3,
            "is_active": true
        }
    ],
    "total": 150
}
```

### GET /patterns/{pattern_id}

Get pattern details.

**Response:**
```json
{
    "pattern_id": "pattern_abc123",
    "name": "RSI Oversold Momentum",
    "conditions": {
        "entry": {
            "operator": "AND",
            "conditions": [
                {"indicator": "rsi_14", "comparison": "<", "value": 30},
                {"indicator": "close", "comparison": ">", "value": "sma_20"}
            ]
        },
        "exit": {
            "operator": "OR",
            "conditions": [
                {"indicator": "rsi_14", "comparison": ">", "value": 70},
                {"indicator": "pnl_pct", "comparison": ">", "value": 0.05}
            ]
        }
    },
    "symbol": "BTC",
    "timeframe": "1h",
    "origin": "chaos_analysis",
    "fitness_score": 0.78,
    "fitness_by_regime": {
        "bull": 0.85,
        "bear": 0.45,
        "chop": 0.72,
        "flat": 0.61
    },
    "tier": 3,
    "is_active": true,
    "created_at": "2026-01-05T12:00:00Z"
}
```

---

## Trades API

### GET /trades

Query trade history.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `agent_id` | string | - | Filter by agent |
| `pattern_id` | string | - | Filter by pattern |
| `symbol` | string | - | Filter by symbol |
| `is_winner` | bool | - | Filter by outcome |
| `regime` | string | - | Filter by regime |
| `limit` | int | 100 | Max results |

**Response:**
```json
{
    "trades": [
        {
            "id": 12345,
            "symbol": "BTCUSDT",
            "entry_time": "2026-01-10T10:00:00Z",
            "exit_time": "2026-01-10T14:30:00Z",
            "entry_price": 42000.50,
            "exit_price": 43250.75,
            "side": "long",
            "pnl_pct": 0.0297,
            "is_winner": true,
            "agent_id": "agent_abc123",
            "pattern_id": "pattern_xyz789",
            "regime": "bull",
            "ai_consulted": true,
            "ai_decision": "hold"
        }
    ],
    "total": 1500
}
```

---

## System API

### GET /system/health

System health check.

**Response:**
```json
{
    "status": "healthy",
    "database": "connected",
    "streams": {
        "binance": "connected",
        "coinbase": "connected",
        "dydx": "connected",
        "hyperliquid": "connected"
    },
    "evolution": {
        "is_running": true,
        "current_cycle": "cycle_abc123"
    },
    "uptime_seconds": 86400,
    "version": "1.0.0"
}
```

### GET /

Root endpoint.

**Response:**
```json
{
    "message": "CoinSwarm API is running",
    "status": "active"
}
```

---

## Market Data API

### GET /market-data/candles

Get historical candles.

**Query Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `symbol` | string | Yes | Trading pair |
| `timeframe` | string | Yes | Candle interval |
| `start` | datetime | No | Start time |
| `end` | datetime | No | End time |
| `limit` | int | No | Max results |

**Response:**
```json
{
    "candles": [
        {
            "timestamp": "2026-01-13T10:00:00Z",
            "open": 42000.50,
            "high": 42150.00,
            "low": 41950.25,
            "close": 42100.00,
            "volume": 1250.5,
            "rsi_14": 55.2,
            "sma_20": 41800.00,
            "macd": 125.5
        }
    ],
    "symbol": "BTCUSDT",
    "timeframe": "1h",
    "count": 100
}
```

---

## Exchange API

### GET /exchanges

List connected exchanges.

**Response:**
```json
{
    "exchanges": ["binance", "coinbase", "dydx", "hyperliquid"]
}
```

### GET /exchanges/{exchange}/state

Get exchange state.

**Response:**
```json
{
    "exchange": "binance",
    "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    "status": "connected",
    "latency_ms": 45,
    "last_update": "2026-01-13T10:30:00Z"
}
```

---

## Governance API (Partial)

### GET /governance/committee

Get Hivemind committee status.

**Response:**
```json
{
    "committee_size": 5,
    "members": [
        {
            "agent_id": "agent_abc123",
            "elo_rating": 1650,
            "vote_weight": 0.25
        }
    ],
    "status": "partial_implementation"
}
```

---

## Dashboard

### GET /dashboard

Serve main dashboard HTML.

**Response:** HTML page

### GET /dashboard/evolution

Serve evolution progress dashboard.

**Response:** HTML page

---

## Error Responses

All errors follow this format:

```json
{
    "detail": "Error message describing what went wrong"
}
```

### Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request |
| 404 | Not Found |
| 422 | Validation Error |
| 500 | Internal Server Error |

---

## Authentication

Currently **no authentication** required (personal bot use case).

---

## Rate Limiting

Currently **no rate limiting** (single user).

---

*Last Updated: 2026-01-13*
