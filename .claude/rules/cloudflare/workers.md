---
paths:
  - v2/cloudflare-agents/**/*.ts
  - v3/cloudflare-agents/**/*.ts
  - cloudflare-agents/**/*.ts
---

# Cloudflare Workers Rules

## Storage Hierarchy
```
HOT:  DO SQLite + KV  → Accurate, real-time data (prices, state, configs)
COLD: R2              → Archive, bulk storage, training data, logs
STALE: D1             → Historical/aggregated data, SQL joins across agents
                         ⚠️ D1 is nearly always STALE - never trust for live data
```

## Durable Objects
- DO SQLite for hot/ephemeral data
- Always implement `alarm()` for scheduled tasks
- Keep DO state minimal
- Use `blockConcurrencyWhile()` for initialization

## KV
- Cache frequently accessed data
- Pattern configs, agent traits, lookup tables
- TTL for auto-expiration

## R2
- Archive old trades, training examples
- Bulk data exports
- Anything that doesn't need SQL queries

## D1 - CRITICAL: Stats are STALE

⚠️ **D1 pattern stats (fitness, ROI, win_rate, number_of_runs, sharpe, etc.) are ALWAYS STALE**

| D1 Column | Trust Level | Notes |
|-----------|-------------|-------|
| `pattern_id` | ✅ Authoritative | Use for existence checks |
| `name`, `entry_conditions`, `exit_conditions` | ✅ Authoritative | Pattern definition |
| `origin`, `tags`, `description` | ✅ Authoritative | Metadata |
| `fitness_score`, `total_roi_pct`, `sharpe_ratio` | ❌ STALE | Get from DO/KV |
| `number_of_runs`, `benchmark_beats` | ❌ STALE | Get from DO/KV |
| `win_rate`, `profit_factor`, `max_drawdown_pct` | ❌ STALE | Get from DO/KV |

**Why?** Backtest results are stored in DO SQLite (PatternDO), not synced to D1 in real-time.
The dashboard shows real stats from DO. D1 only has pattern definitions.

- Use for: pattern ID lookups, cross-agent joins, batch pattern creation
- Historical OHLCV data (searchable by asset/timeframe)
- Batch writes (max 1000 rows, use `INSERT OR IGNORE`)

## Resource Limits
- 128MB memory per DO
- 30s CPU time per request
- 1000 subrequests per invocation

## Data Access
- V2 owns the data shards (DATA_SHARD_1 through DATA_SHARD_5)
- V3 accesses data through V2's API endpoints
- Never query D1 directly from V3 - use AssetPriceDO API

## Error Handling
```typescript
// Always wrap async operations
try {
  const result = await operation();
  return new Response(JSON.stringify(result));
} catch (error) {
  console.error('[Component] Error:', error);
  return new Response(JSON.stringify({ error: error.message }), { status: 500 });
}
```

## Logging Format
```typescript
console.log('[ComponentName] Action { context }');
// Example: [AssetPriceDO] Fetched candles { asset: 'BTC', count: 100 }
```
