# Cloudflare Quota Analysis Report - Coinswarm V3

**Generated:** 2025-12-21
**Plan:** Workers Paid ($5/month base)

---

## Executive Summary

| Resource | Current Usage | Full Implementation | Paid Plan Limit | Status |
|----------|---------------|---------------------|-----------------|--------|
| **Workers Requests** | ~2K/day | ~50K/day | 10M/month | Safe |
| **CPU Time** | ~500K ms/day | ~15M ms/day | 30M ms/month | Monitor |
| **D1 Reads** | ~50K/day | ~5M/day | 25B/month | Safe |
| **D1 Writes** | ~10K/day | ~500K/day | 50M/month | Safe |
| **KV Reads** | ~15K/day | ~200K/day | 10M/month | Safe |
| **KV Writes** | ~5K/day | ~50K/day | 1M/month | Safe |
| **DO Requests** | ~5K/day | ~500K/day | 1M/month | Monitor |
| **DO Duration** | ~50K GB-s/day | ~500K GB-s/day | 400K GB-s/month | RISK |
| **R2 Storage** | ~10 MB | ~5 GB | 10 GB free | Safe |
| **Workers AI** | ~100/day | ~2K/day | 10K/day free | Safe |
| **Queues** | ~5K ops/day | ~100K ops/day | 1M/month | Safe |

**Estimated Monthly Cost:** $5-15 (current) → $25-75 (full implementation)

---

## 1. Workers Requests

### Paid Plan Limits
| Metric | Included | Overage |
|--------|----------|---------|
| Requests | 10 million/month | $0.30/million |

### Current Usage (Development)
- **Cron triggers:** 1 per minute × 60 × 24 = 1,440/day
- **API requests (dashboard):** ~500/day (estimated light usage)
- **Total:** ~2,000 requests/day → **60,000/month**

### Full Implementation
- **Cron triggers:** 1,440/day (same)
- **API requests (active users):** ~10,000/day (10 users × 1000 actions)
- **Internal subrequests:** ~40,000/day (DO-to-DO calls)
- **Total:** ~50,000 requests/day → **1.5 million/month**

### Cost Analysis
| Scenario | Monthly Usage | Included | Overage | Cost |
|----------|---------------|----------|---------|------|
| Current | 60K | 10M | 0 | $0 |
| Full | 1.5M | 10M | 0 | $0 |

**Status:** Well under limits. No cost concerns.

---

## 2. CPU Time

### Paid Plan Limits
| Metric | Included | Overage |
|--------|----------|---------|
| CPU milliseconds | 30 million/month | $0.02/million |

### Current Usage
- **Per backtest:** ~100-500ms CPU
- **Backtests per minute:** 150 (per cron trigger)
- **Daily:** 150 × 60 × 24 = 216,000 backtests
- **CPU per day:** 216K × 300ms = **64.8 million ms/day**

**Wait** - this exceeds the monthly limit on a daily basis. Let me re-analyze.

### Re-analysis: Actual CPU Patterns
The BacktestSchedulerDO dispatches 150 backtests, but:
1. Each backtest runs in a separate DO (PatternDO)
2. DO duration is billed separately from Worker CPU
3. Worker CPU is only for the scheduler coordination (~5-10ms per dispatch)

**Corrected Worker CPU:**
- **Cron handler:** ~50ms per trigger × 1,440/day = 72,000 ms/day
- **API handlers:** ~20ms per request × 500/day = 10,000 ms/day
- **Queue consumers:** ~10ms per message × 5,000/day = 50,000 ms/day
- **Total:** ~132,000 ms/day → **4 million ms/month**

### Full Implementation
- **Cron handler:** ~100ms × 1,440/day = 144,000 ms/day
- **API handlers:** ~20ms × 10,000/day = 200,000 ms/day
- **Queue consumers:** ~10ms × 50,000/day = 500,000 ms/day
- **Total:** ~844,000 ms/day → **25 million ms/month**

### Cost Analysis
| Scenario | Monthly Usage | Included | Overage | Cost |
|----------|---------------|----------|---------|------|
| Current | 4M ms | 30M ms | 0 | $0 |
| Full | 25M ms | 30M ms | 0 | $0 |

**Status:** Within limits but approaching threshold at full scale.

---

## 3. D1 Database

### Paid Plan Limits
| Metric | Included | Overage |
|--------|----------|---------|
| Rows read | 25 billion/month | $0.001/million |
| Rows written | 50 million/month | $1.00/million |
| Storage | 5 GB | $0.75/GB-month |

### Current Tables
From [wrangler.toml](v3/cloudflare-agents/wrangler.toml):
- `discovered_patterns` - Pattern metadata and fitness scores
- `agents` - Trading agent configurations
- `backtest_queue` - Pending backtests
- `trades`, `positions` - Trade records
- `competition_results` - Evolution outcomes

### Current Usage

**Reads per evolution cycle (every minute):**
- Agent lookups: ~10 rows
- Pattern status checks: ~30 rows
- System config: ~5 rows
- **Per cycle:** ~45 rows
- **Daily:** 45 × 1,440 = **64,800 rows/day**

**Writes per evolution cycle:**
- Pattern fitness updates: ~30 rows
- Agent updates: ~5 rows
- Competition results: ~50 rows
- **Per cycle:** ~85 rows
- **Daily:** 85 × 1,440 = **122,400 rows/day**

### Full Implementation

**Reads (10x scaling for active competitions):**
- Pattern queries: 500 rows/cycle
- Agent queries: 100 rows/cycle
- Trade history: 200 rows/cycle
- **Per cycle:** ~800 rows
- **Daily:** 800 × 1,440 = **1.15 million rows/day**
- **Monthly:** ~35 million rows

**Writes:**
- Pattern updates: 150 rows/cycle
- Trade records: 300 rows/cycle
- Agent state: 50 rows/cycle
- **Per cycle:** ~500 rows
- **Daily:** 500 × 1,440 = **720,000 rows/day**
- **Monthly:** ~22 million rows

### Cost Analysis
| Scenario | Reads/month | Writes/month | Cost |
|----------|-------------|--------------|------|
| Current | 2M | 3.7M | $0 |
| Full | 35M | 22M | $0 |

**Status:** Well under limits. D1 is cheap for this use case.

---

## 4. Workers KV

### Paid Plan Limits
| Metric | Included | Overage |
|--------|----------|---------|
| Reads | 10 million/month | $0.50/million |
| Writes | 1 million/month | $5.00/million |
| Deletes | 1 million/month | $5.00/million |
| List ops | 1 million/month | $5.00/million |
| Storage | 1 GB | $0.50/GB-month |

### Keys Used
From codebase analysis:
1. `pattern-leaderboard` - Full leaderboard (~5-20 MB)
2. `pattern-run-counts` - Aggregated counts (~100 KB)
3. `retired-pattern-ids` - Blocklist (~50 KB)
4. Various cache keys for API responses

### Current Usage

**Reads:**
- Leaderboard reads: ~10/cycle × 1,440 = 14,400/day
- Cache hits: ~100/day
- **Daily:** ~15,000 reads → **450,000/month**

**Writes:**
- Leaderboard updates: ~3/cycle × 1,440 = 4,320/day
- Cache updates: ~500/day
- **Daily:** ~5,000 writes → **150,000/month**

### Full Implementation

**Reads (increased dashboard traffic):**
- Leaderboard reads: 50/cycle × 1,440 = 72,000/day
- API cache hits: 5,000/day
- **Daily:** ~77,000 reads → **2.3 million/month**

**Writes:**
- Leaderboard updates: 10/cycle × 1,440 = 14,400/day
- Cache updates: 2,000/day
- **Daily:** ~16,000 writes → **480,000/month**

### Cost Analysis
| Scenario | Reads/month | Writes/month | Cost |
|----------|-------------|--------------|------|
| Current | 450K | 150K | $0 |
| Full | 2.3M | 480K | $0 |

**Status:** Safe. Approaching 50% of write limit at full scale.

---

## 5. Durable Objects

### Paid Plan Limits
| Metric | Included | Overage |
|--------|----------|---------|
| Requests | 1 million/month | $0.15/million |
| Duration | 400,000 GB-s/month | $12.50/million GB-s |
| SQLite rows read | 25 billion/month | $0.001/million |
| SQLite rows written | 50 million/month | $1.00/million |
| Storage | 5 GB | $0.20/GB-month |

### Durable Objects (9 Total)
| DO Class | Instances | Purpose |
|----------|-----------|---------|
| EvolutionAgentDO | 1 | Evolution cycle state |
| PatternDO | ~1,000+ | Pattern backtest runners |
| PatternDiscoveryDO | 1 | Chaos trade discovery |
| AssetPriceDO | ~50 | Per-asset price cache |
| BacktestSchedulerDO | 1 | Backtest orchestration |
| AgentMemoryDO | ~100+ | Per-agent memory |
| MomentumTraderDO | ~50 | Trading personality |
| MeanReversionDO | ~50 | Trading personality |
| TrendFollowerDO | ~50 | Trading personality |

### Current Usage

**Requests:**
- Backtest dispatches: 150/min × 1,440 = 216,000/day
- DO-to-DO calls: ~50/min × 1,440 = 72,000/day
- Internal state updates: ~20/min × 1,440 = 28,800/day
- **Daily:** ~317,000 → **9.5 million/month**

**Duration (critical metric):**
- Each backtest keeps PatternDO active for ~5-30 seconds
- Using 128 MB memory = 0.125 GB
- Duration per backtest: 0.125 GB × 15s = 1.875 GB-s
- Daily backtests: 216,000
- **Daily duration:** 216,000 × 1.875 = **405,000 GB-s/day**

**This EXCEEDS the monthly limit on a single day!**

### Full Implementation

**Requests (same pattern, more instances):**
- Daily: ~500,000 → **15 million/month**

**Duration (CRITICAL):**
- At 405K GB-s/day → **12.15 million GB-s/month**

### Cost Analysis
| Scenario | Requests/month | Duration GB-s | Cost |
|----------|----------------|---------------|------|
| Current | 9.5M | 12M | **$145** |
| Full | 15M | 20M+ | **$250+** |

**Breakdown:**
- Requests: (9.5M - 1M) × $0.15/M = $1.28
- Duration: (12M - 400K) × $12.50/M = **$144.50**

**Status:** RISK - Duration is the primary cost driver.

### Mitigation Strategies
1. **Reduce DO active time** - Exit DOs faster after backtests
2. **Use smaller memory footprint** - Optimize data structures
3. **Batch operations** - Keep DOs active for longer but do more work
4. **Hibernate aggressively** - Call `blockConcurrencyWhile()` to hibernate

---

## 6. R2 Storage

### Paid Plan Limits
| Metric | Free Tier | Overage |
|--------|-----------|---------|
| Storage | 10 GB/month | $0.015/GB-month |
| Class A (writes) | 1 million/month | $4.50/million |
| Class B (reads) | 10 million/month | $0.36/million |

### Current Usage
- **Storage:** ~10 MB (archived trade logs)
- **Writes:** ~5/day (pruning archives)
- **Reads:** ~0/day (historical queries rare)

### Full Implementation
- **Storage:** ~5 GB (trade archives grow over time)
- **Writes:** ~50/day
- **Reads:** ~100/day

### Cost Analysis
| Scenario | Storage | Writes | Reads | Cost |
|----------|---------|--------|-------|------|
| Current | 10 MB | 150/month | 0 | $0 |
| Full | 5 GB | 1,500/month | 3,000/month | $0 |

**Status:** Well under free tier.

---

## 7. Workers AI

### Paid Plan Limits
| Metric | Free Tier | Overage |
|--------|-----------|---------|
| Neurons | 10,000/day free | $0.011/1,000 neurons |

### Models Used
From codebase:
- `@cf/meta/llama-3.2-1b-instruct` - Pattern discovery (~2,500 neurons/request)
- `@cf/meta/llama-3.2-3b-instruct` - Pattern suggestions (~5,000 neurons/request)
- `@cf/meta-llama/llama-2-7b-chat-hf-lora` - Academic paper analysis (~10,000 neurons/request)

### Current Usage
- **Pattern discovery:** ~10 calls/day × 2,500 = 25,000 neurons
- **Pattern suggestions:** ~5 calls/day × 5,000 = 25,000 neurons
- **Total:** ~50,000 neurons/day

**Already exceeds free tier by 40,000 neurons/day!**

### Cost Analysis
| Scenario | Neurons/day | Free | Overage Cost |
|----------|-------------|------|--------------|
| Current | 50K | 10K | $0.44/day = **$13.20/month** |
| Full | 200K | 10K | $2.09/day = **$62.70/month** |

**Status:** AI is a significant cost at current usage.

### Mitigation
1. **Cache AI responses** - Same patterns don't need re-analysis
2. **Batch requests** - Analyze multiple patterns per call
3. **Use smaller models** - llama-3.2-1b instead of 3b where possible
4. **Conditional calling** - Only call AI when chaos trades exceed threshold

---

## 8. Queues

### Paid Plan Limits
| Metric | Included | Overage |
|--------|----------|---------|
| Operations | 1 million/month | $0.40/million |

### Queues Configured
1. `coinswarm-v3-kv-updates` - Batch KV writes
2. `coinswarm-v3-indicator-calc` - Pre-compute indicators
3. `coinswarm-v3-d1-retire` - Batch D1 retirements

### Current Usage
- **KV updates:** ~3,000/day
- **Indicator calcs:** ~150/day
- **D1 retirements:** ~100/day
- **Total:** ~3,250 ops/day → **98,000/month**

### Full Implementation
- **KV updates:** ~15,000/day
- **Indicator calcs:** ~1,000/day
- **D1 retirements:** ~500/day
- **Total:** ~16,500 ops/day → **495,000/month**

### Cost Analysis
| Scenario | Operations/month | Included | Cost |
|----------|------------------|----------|------|
| Current | 98K | 1M | $0 |
| Full | 495K | 1M | $0 |

**Status:** Safe. Under 50% of limit.

---

## Total Cost Summary

### Current Development Usage

| Resource | Monthly Cost |
|----------|--------------|
| Workers Paid Base | $5.00 |
| Worker Requests | $0.00 |
| Worker CPU | $0.00 |
| D1 | $0.00 |
| KV | $0.00 |
| **Durable Objects** | **$145.00** |
| R2 | $0.00 |
| **Workers AI** | **$13.20** |
| Queues | $0.00 |
| **TOTAL** | **$163.20/month** |

### Full Implementation

| Resource | Monthly Cost |
|----------|--------------|
| Workers Paid Base | $5.00 |
| Worker Requests | $0.00 |
| Worker CPU | $0.00 |
| D1 | $0.00 |
| KV | $0.00 |
| **Durable Objects** | **$250.00+** |
| R2 | $0.00 |
| **Workers AI** | **$62.70** |
| Queues | $0.00 |
| **TOTAL** | **$317.70+/month** |

---

## Critical Issues & Recommendations

### 1. Durable Object Duration (HIGHEST PRIORITY)

**Problem:** 405,000 GB-s/day exceeds 400,000 GB-s/month limit by 100x.

**Root Cause:** PatternDO instances stay active for 15-30 seconds per backtest, and there are 216,000 backtests/day.

**Solutions:**

A. **Reduce batch size** (immediate)
   - Current: 150 backtests/minute
   - Reduce to: 20 backtests/minute
   - Impact: 90% reduction in DO duration
   - Tradeoff: Evolution cycles take longer

B. **Hibernate DOs aggressively**
   - Use `ctx.waitUntil()` for background cleanup
   - Ensure DOs hibernate within 1-2 seconds
   - Could reduce average active time from 15s to 2s

C. **Consolidate backtests**
   - Run multiple patterns in a single DO
   - Batch 10 patterns per DO activation
   - Reduces total activations by 10x

D. **Architecture change**
   - Move backtest logic from DOs to regular Workers
   - Workers bill CPU time, not duration
   - Significant refactor required

### 2. Workers AI Usage (MEDIUM PRIORITY)

**Problem:** 50K neurons/day exceeds 10K free tier.

**Solutions:**

A. **Cache AI responses** (immediate)
   - Store pattern analysis in KV
   - Check cache before calling AI
   - 80%+ cache hit rate possible

B. **Reduce model size**
   - Use llama-3.2-1b (2,500 neurons) instead of 3b (5,000 neurons)
   - 50% cost reduction

C. **Make AI calls conditional**
   - Only analyze patterns after they show promise (fitness > 50)
   - Skip AI for simple pattern mutations

### 3. KV Write Approaching Limit (LOW PRIORITY)

**Problem:** Full implementation uses 480K of 1M write limit.

**Solution:**
- Batch leaderboard updates (every 5 minutes instead of every minute)
- Use Queues to aggregate updates before writing

---

## Revised Architecture Recommendations

### Immediate Changes (This Week)

1. **Reduce backtest batch size to 20/minute**
   ```typescript
   // In BacktestSchedulerDO
   const BATCH_SIZE = 20;  // Was 150
   ```

2. **Add AI response caching**
   ```typescript
   const cacheKey = `ai-pattern-${patternHash}`;
   const cached = await env.PATTERN_CACHE.get(cacheKey);
   if (cached) return JSON.parse(cached);
   ```

3. **Use smaller AI models**
   - Replace llama-3.2-3b with llama-3.2-1b for routine analysis

### Medium-Term Changes (This Month)

4. **Consolidate pattern backtests**
   - Create a BacktestWorkerDO that runs batches of 10 patterns
   - Reduces DO instances by 10x

5. **Implement aggressive hibernation**
   - Add explicit `await ctx.blockConcurrencyWhile()` patterns
   - Target <2 second active time per backtest

### Long-Term Changes (Next Quarter)

6. **Hybrid architecture**
   - Move CPU-intensive backtest logic to regular Workers
   - Use DOs only for state coordination
   - Could reduce DO duration costs to near-zero

---

## Monitoring Recommendations

Add these metrics to the dashboard:

1. **DO Duration Tracking**
   ```typescript
   console.log('[Metrics] DO Duration', {
     doClass: 'PatternDO',
     activeTimeMs: Date.now() - startTime,
     patternId
   });
   ```

2. **AI Neuron Usage**
   ```typescript
   console.log('[Metrics] AI Usage', {
     model: '@cf/meta/llama-3.2-1b-instruct',
     estimatedNeurons: 2500,
     dailyTotal: dailyNeuronCount
   });
   ```

3. **Cost Alerts**
   - Alert when DO duration exceeds 300K GB-s/month
   - Alert when AI neurons exceed 8K/day

---

## Sources

- [Cloudflare Workers Pricing](https://developers.cloudflare.com/workers/platform/pricing/)
- [Durable Objects Pricing](https://developers.cloudflare.com/durable-objects/platform/pricing/)
- [Workers KV Pricing](https://developers.cloudflare.com/kv/platform/pricing/)
- [Workers AI Pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)
- [R2 Storage Pricing](https://developers.cloudflare.com/r2/pricing/)
- [Queues Pricing](https://developers.cloudflare.com/queues/platform/pricing/)
