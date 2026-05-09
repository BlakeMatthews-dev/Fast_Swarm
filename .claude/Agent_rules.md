# Agent Rules

Rules and guidelines for Claude agents working on this project.

---

## Core Principles

1. **Real Data Only** - Never use fake, mock, or synthetic data. Query D1 shards.
2. **Evolution Discovers** - Let fitness-based selection find optimal values, don't predefine.
3. **Raw Values** - Store `rsi: 28.3` not `rsi_oversold`. Precision matters.
4. **Complete Tasks** - Finish what you start. No TODO shortcuts.
5. **Self-Documenting** - `benchmark_beats` not `wins`, `annualized_roi_pct` not `roi`.

---

## Behavior Guidelines

### When Working on Cloudflare Workers
- V2 owns data shards, V3 accesses through V2 API
- **HOT**: DO SQLite + KV for accurate, real-time data
- **COLD**: R2 for archives, bulk storage, training data
- **STALE**: D1 for historical queries, SQL joins (⚠️ never trust D1 for live data)
- Batch D1 writes (max 1000 rows per transaction)
- Log format: `[Component] Action { context }`

### When Working on Patterns/Evolution
- Generate RANDOM ranges - evolution finds optimal
- Store raw indicator values, never buckets
- Minimum 100 trades for statistical significance
- Bound all calculations (no Infinity/NaN)

### When Working on Python Utilities
- Use `uv` for package management
- Save checkpoints for long operations
- Real data from D1/R2 only

### When Using LLMs
- Workers AI for live trading (<500ms)
- Local Ollama (phi4, gpt-oss) for batch
- Context engineering > expensive models
- Log (prompt, response, outcome) for LoRA training

---

## Prohibited Actions

1. **Never generate fake prices** - Always fetch from ohlcv_* tables
2. **Never hardcode thresholds** - Let evolution discover (RSI 30 ≠ always oversold)
3. **Never leave TODO shortcuts** - Do the fix or ask user
4. **Never modify test stubs** - Preserve TDD placeholders
5. **Never query V2 data from V3 directly** - Use API endpoints
6. **Never transform continuous to categorical** - `rsi: 28.3` not `rsi_bucket_3`
7. **Never commit API keys or secrets** - Use environment variables

---

## Model Hierarchy

```
Workers AI (FREE)         → Live trading, <500ms latency
Local Ollama (up to 120B) → Overnight batch, phi4, gpt-oss
Claude Code + Opus 4.5    → Code generation, architecture
```

---

## Data Shards Reference

| Shard | Contents |
|-------|----------|
| DATA_SHARD_1 | Major cryptos (BTC, ETH, etc.) - 2GB |
| DATA_SHARD_2 | ARB, ETFs, L2s - 2.5MB |
| DATA_SHARD_3 | Solana tokens (pending) |
| DATA_SHARD_4 | BSC DeFi - 1.5MB |
| DATA_SHARD_5 | Reserved |
| DB | Main evolution DB - 700MB |
