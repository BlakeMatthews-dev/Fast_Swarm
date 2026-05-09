# CLOUDFLARE TIERS - Complete Documentation

**Consolidated from 4 source files covering Cloudflare paid/free tier limits and multi-cloud optimization.**

---

# TABLE OF CONTENTS

- [PART 1: Workers Paid Plan ($5/month) Complete Limits](#part-1-workers-paid-plan-5month-complete-limits)
- [PART 2: Free Tier Maximization Strategy](#part-2-free-tier-maximization-strategy)
- [PART 3: Free Tier Performance Analysis](#part-3-free-tier-performance-analysis)
- [PART 4: Multi-Cloud Free Tier Optimization](#part-4-multi-cloud-free-tier-optimization)

---

# PART 1: Workers Paid Plan ($5/month) Complete Limits

*Source: CLOUDFLARE_PAID_PLAN_LIMITS.md*

**Base Cost**: $5 USD per month minimum

## Workers

### Included Monthly Limits
- **Requests**: 10 million requests/month
- **CPU Time**: Standard usage model (pay per ms)
- **Duration**: No wall clock time charges (only CPU time)

### Overage Pricing
- **$0.50** per million requests (after 10M included)
- **$0.02** per million CPU milliseconds

## D1 Database

### Included Monthly Limits
- **Rows Read**: 25 billion rows
- **Rows Written**: 50 million rows
- **Storage**: 5 GB

### Overage Pricing
- **Rows Read**: $0.001 per million rows
- **Rows Written**: $1.00 per million rows
- **Storage**: $0.75 per GB/month

### Database Limits
- **Max Database Size**: 10 GB
- **Max Databases per Account**: 50,000
- **Total Storage per Account**: 1 TB maximum
- **Time Travel**: 30 days FREE

## KV Storage

### Included Monthly Limits
- **Storage**: 1 GB
- **Read Operations**: 10 million
- **Write Operations**: 1 million
- **Delete/List Operations**: 1 million each

### Overage Pricing
- **Storage**: $0.50 per GB/month
- **Read Operations**: $0.50 per million
- **Write/Delete/List**: $5.00 per million

## R2 Object Storage

### Free Tier (Applies to ALL Plans)
- **Storage**: 10 GB
- **Class A Operations**: 1 million/month
- **Class B Operations**: 10 million/month
- **Egress**: UNLIMITED (always free)

### Overage Pricing
- **Storage**: $0.015 per GB/month
- **Class A Operations**: $4.50 per million
- **Class B Operations**: $0.36 per million

## Durable Objects

### Included Monthly Limits
- **Requests**: 1 million requests

### Overage Pricing
- **Requests**: $0.15 per million
- **Storage**: 10 GB per object (SQLite-backed)

## Queues

### Included Monthly Limits
- **Operations**: 1 million operations

### Overage Pricing
- **$0.40** per million operations
- Operation = each 64 KB chunk written, read, or deleted

## Workers AI

### Included Daily Limits
- **Neurons**: 10,000 Neurons/day (FREE)
- Resets daily at 00:00 UTC

### Pricing Beyond Free Tier
- **$0.011** per 1,000 Neurons

## Vectorize

### Included Monthly Limits
- **Queried Vector Dimensions**: 30 million/month
- **Stored Vector Dimensions**: 5 million/account

### Overage Pricing
- **Queried Dimensions**: $0.01 per million
- **Stored Dimensions**: $0.05 per 100 million

## Hyperdrive

- **FREE** - No additional charges beyond Workers Paid plan
- Connection pooling and query caching included

## Summary Table - $5/month Included Limits

| Service | Included Usage | Overage Price |
|---------|---------------|---------------|
| **Workers** | 10M requests | $0.50/M requests |
| **D1** | 25B reads, 50M writes, 5GB | $0.001/M reads, $1/M writes |
| **KV** | 1GB, 10M reads, 1M writes | $0.50/GB, $0.50/M reads |
| **R2** | 10GB, 1M Class A, 10M Class B | $0.015/GB |
| **Durable Objects** | 1M requests | $0.15/M requests |
| **Queues** | 1M operations | $0.40/M operations |
| **Workers AI** | 10K Neurons/day | $0.011/1K Neurons |
| **Vectorize** | 30M queried, 5M stored dims | $0.01/M |
| **Hyperdrive** | FREE | Workers pricing |

## Quick Reference Card

```
CLOUDFLARE WORKERS PAID PLAN - $5/MONTH INCLUDED LIMITS

COMPUTE
├─ Workers:         10M requests/month
├─ Workers AI:      10K Neurons/day
└─ Hyperdrive:      FREE (unlimited)

STORAGE
├─ D1:              5 GB + 25B reads + 50M writes
├─ KV:              1 GB + 10M reads + 1M writes
├─ R2:              10 GB + 1M writes + 10M reads
└─ Durable Objects: 1M requests

MESSAGING
└─ Queues:          1M operations

VECTOR/AI
└─ Vectorize:       30M queried + 5M stored dimensions

ZERO EGRESS FEES: D1, R2, KV, Queues
TIME TRAVEL: D1 (30 days, FREE)
SCALE TO ZERO: Workers, Containers
```

---

# PART 2: Free Tier Maximization Strategy

*Source: cloudflare-free-tier-maximization.md*

## Cloudflare Free Services Inventory

| Service | Free Tier Limits | Best For |
|---------|-----------------|----------|
| **Workers** | 100K req/day, 10ms CPU | API routing, lightweight logic |
| **Pages** | Unlimited requests | Static sites, SPA hosting |
| **D1** | 5M reads/day, 100K writes/day | SQLite data, read replicas |
| **KV** | 100K reads/day, 1K writes/day | Hot cache, session data |
| **R2** | 10GB storage, 1M Class A ops | Object storage, files |
| **Workers AI** | 10K neurons/day | AI inference |
| **CDN** | Unlimited bandwidth | Asset caching |
| **DNS** | Unlimited queries | Domain management |
| **DDoS Protection** | Unmetered | Security |

**Key Insight**: Workers, Pages, D1, KV, R2, Workers AI, and CDN are all free with generous limits!

## Architecture: All Free Cloudflare Services

```
┌────────────────────────────────────────────────────────────┐
│         USER REQUEST (via Cloudflare DNS - FREE)           │
└──────────────────┬─────────────────────────────────────────┘
                   │
                   ▼
         ┌──────────────────┐
         │  Cloudflare CDN  │ ← FREE, unlimited bandwidth
         │   (Asset Cache)  │
         └────────┬─────────┘
                  │
        ┌─────────┴──────────┐
        │                    │
        ▼                    ▼
  ┌──────────┐         ┌──────────┐
  │ Workers  │         │  Pages   │ ← FREE, unlimited requests
  │ (API)    │         │ (Frontend)│
  │ 100K/day │         └──────────┘
  └────┬─────┘
       │
       ├─────────────────────────────────────┐
       │                                     │
       ▼                                     ▼
  ┌──────────┐                         ┌──────────┐
  │ D1 (SQL) │ ← FREE 5M reads/day    │ KV Cache │ ← FREE 100K reads/day
  │ Patterns │                         │ Market   │
  │ Trades   │                         │ Data     │
  └──────────┘                         └──────────┘
       │                                     │
       ▼                                     ▼
  ┌──────────┐                         ┌──────────┐
  │ R2 Store │ ← FREE 10GB storage    │Workers AI│ ← FREE 10K neurons/day
  │Historical│                         │ML Infer- │
  │ OHLCV    │                         │ence      │
  └──────────┘                         └──────────┘

Total Cost: $0/month
```

## Service Distribution Strategy

### 1. Workers (100K requests/day FREE)

Split across multiple worker scripts:
- Worker 1: MCP API Server (30K req/day)
- Worker 2: Data Ingest (30K req/day)
- Worker 3: Trading Logic (20K req/day)
- Worker 4: Analytics (20K req/day)

**Strategy**: Route via `fetch()` between workers (doesn't count against limits!)

### 2. D1 Database (5M reads/day, 100K writes/day FREE)

Split by read/write patterns:
- D1 Instance 1: Hot Trading Data (write-heavy)
- D1 Instance 2: Historical Patterns (read-heavy)
- D1 Instance 3: Metadata (rarely accessed)

**Why multiple D1?** Each gets 5M reads/day, so 3 instances = 15M reads/day total!

### 3. KV Storage (100K reads/day, 1K writes/day FREE)

Use for ultra-hot cache only:
- KV Namespace 1: Market Data (1-second TTL)
- KV Namespace 2: Predictions (5-second TTL)
- KV Namespace 3: Sessions

**Strategy**: Multiple namespaces, write only on change (not every tick)

### 4. R2 Storage (10GB, 1M Class A ops FREE)

```
r2://historical/
├── ohlcv/ (5GB historical data)
├── patterns/ (20MB)
├── backtests/ (1GB)
└── exports/ (500MB)
Total: ~7GB of 10GB free
```

**No egress fees** - Read as much as you want!

### 5. Workers AI (10K neurons/day FREE)

```
@cf/meta/llama-2-7b-chat-int8    ~100 neurons/request → 100 inferences/day
@cf/baai/bge-base-en-v1.5        ~20 neurons/request → 500 embeddings/day
@cf/huggingface/distilbert-sst-2 ~50 neurons/request → 200 analyses/day
```

**Strategy**: Use for non-critical predictions, fall back to heuristics if quota exceeded

### 6. Cloudflare Pages (Unlimited FREE)

- Unlimited requests
- Unlimited bandwidth via CDN
- Pages Functions = separate 100K/day quota!

## Request Budget Optimization

**100K requests/day = 1.16 requests/second**

### Strategy 1: Aggressive Caching
```
Without cache: 864K req/day
With 1s cache: 8.6K req/day (99% reduction)
```

### Strategy 2: Pages Functions for Static API
Move read-only endpoints to Pages Functions (separate quota!)

### Strategy 3: Client-Side Aggregation
Batch 100 trades into 1 request instead of 100 requests

## Maximum Free Capacity

| Resource | Free Limit | With Optimization |
|----------|-----------|-------------------|
| **Requests** | 100K/day | 400K/day (Pages + multi-Worker) |
| **D1 Reads** | 5M/day | 15M/day (3 replicas) + KV cache |
| **D1 Writes** | 100K/day | 100K/day |
| **KV Reads** | 100K/day | 1M/day (10 namespaces) |
| **KV Writes** | 1K/day | 10K/day (10 namespaces) |
| **R2 Storage** | 10GB | 10GB |
| **Workers AI** | 10K neurons | 10K neurons |

**Verdict**: Run a sandbox trading MVP entirely free if:
- Trading volume is low (<10 trades/day)
- Market data updates are cached
- Historical data is archived to R2
- ML inference is limited

## When You'll Need to Pay

1. **First**: KV writes (1K/day) → $5/mo upgrade
2. **Second**: Workers requests (100K/day) → $5/mo upgrade
3. **Third**: D1 writes (100K/day) → $5/mo upgrade

**Total when you outgrow free**: $15/month

---

# PART 3: Free Tier Performance Analysis

*Source: free-tier-performance-analysis.md*

**TL;DR**: Free tiers are **architecturally identical** to paid tiers, with only **capacity limits**, not performance degradation. Scale from free → paid with **zero code changes**.

## Service-by-Service Performance Comparison

### Cloudflare Workers

| Metric | Free Tier | Paid Tier | Delta |
|--------|-----------|-----------|-------|
| Cold Start | <1ms | <1ms | **0%** |
| Execution Speed | V8 isolate | V8 isolate | **0%** |
| Edge Locations | 300+ PoPs | 300+ PoPs | **0%** |
| Latency (P50) | 10-30ms | 10-30ms | **0%** |
| CPU Time/Request | 10ms limit | 30s limit | Only limit, not speed |

**Verdict**: ZERO performance compromise

### Cloudflare D1

| Metric | Free Tier | Paid Tier | Delta |
|--------|-----------|-----------|-------|
| Read Latency | 1-5ms | 1-5ms | **0%** |
| Write Latency | 5-10ms | 5-10ms | **0%** |
| Reads | 5M/day | 25M/day | Only throughput |
| Writes | 100K/day | 10M/day | Only throughput |

**Verdict**: ZERO performance compromise

### Cloudflare KV

| Metric | Free Tier | Paid Tier | Delta |
|--------|-----------|-----------|-------|
| Read Latency | 1-3ms | 1-3ms | **0%** |
| Write Latency | 1-5ms | 1-5ms | **0%** |
| Propagation | 60 seconds | 60 seconds | **0%** |

**Verdict**: ZERO performance compromise

### Azure Cosmos DB

| Metric | Free (1000 RU/s) | Paid (5000 RU/s) | Delta |
|--------|------------------|------------------|-------|
| Point Read Latency | <5ms P99 | <5ms P99 | **0%** |
| Write Latency | <10ms P99 | <10ms P99 | **0%** |

**Verdict**: ZERO latency difference, just lower throughput

### Azure Redis Cache

| Metric | Free C0 | Paid C1 | Delta |
|--------|---------|---------|-------|
| Latency (P50) | 2ms | 1ms | Slightly slower |
| Latency (P99) | 8ms | 3ms | +5ms variance |

**Verdict**: SLIGHT compromise (+2-5ms P99), acceptable for MVP

### GCP Cloud Run / Functions

| Metric | Free Tier | Paid Tier | Delta |
|--------|-----------|-----------|-------|
| Cold Start | 1-3 seconds | 0ms (min instances) | Cold start only |
| Warm Latency | 10-50ms | 10-50ms | **0%** |

**Mitigation**: Keep-alive ping every 5 minutes = always warm = **FREE**

## Summary: Performance Compromises

### NO COMPROMISE (Identical Performance):
- Cloudflare Workers
- Cloudflare D1
- Cloudflare KV
- Cloudflare R2
- Azure Cosmos DB
- AWS DynamoDB
- AWS SQS

### SLIGHT COMPROMISE (Easily Mitigated):
- GCP Cloud Run/Functions: Cold starts → mitigate with keep-alive pings
- Azure Redis Cache: +2-5ms P99 → acceptable for MVP

### REAL COMPROMISE:
- **None!** All free tiers have production-quality performance.

## Performance Benchmarks - Free Tier

```
User → Cloudflare Worker:                 10ms
Worker → GCP Cloud Run (warm):            15ms
Cloud Run → Coinbase API:                 5ms
Cloud Run → Cosmos DB:                    5ms
Cloud Run → Redis Cache:                  3ms
Cloud Run → DynamoDB:                     8ms
Worker → User response:                   10ms

TOTAL: 56ms (P50)

vs Paid tier with all upgrades:
TOTAL: 35ms (P50) → Only 21ms faster
```

**Is 21ms worth $200/month?** For MVP: **NO**

## Conclusion

**Free tier limitations are**:
- Throughput caps (requests/day, RU/s, storage)
- Cold starts (easily mitigated)
- Slightly higher P99 on shared infra (+2-5ms)

**Free tier does NOT compromise**:
- Latency (P50) - identical to paid
- Features - all production features available
- Reliability - same SLAs
- Global distribution - same edge network
- Security - same encryption, DDoS protection

---

# PART 4: Multi-Cloud Free Tier Optimization

*Source: multi-cloud-free-tier-optimization.md*

**Goal**: Use the BEST free tier from each cloud provider for maximum value.

## Cloud Provider Free Tiers Comparison

### Best From Each Provider

| Provider | Best Free Services | Monthly Value |
|----------|-------------------|---------------|
| **Cloudflare** | CDN (unlimited), DDoS (unmetered), Pages (unlimited) | ~$700 |
| **GCP** | Cloud Functions (2M/mo), Cloud Run (2M/mo), BigQuery | ~$70 |
| **Azure** | Cosmos DB (1000 RU/s), Redis (250MB), Functions (1M) | ~$85 |
| **AWS** | Lambda (1M), DynamoDB (25GB), SQS (1M) | ~$30 |

**TOTAL**: ~$885/month of services for FREE

## Optimal Multi-Cloud Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                   MULTI-CLOUD FREE TIER STACK                    │
└──────────────────────────────────────────────────────────────────┘

USER
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│ CLOUDFLARE (Edge Layer - $700/mo value FREE)                    │
│ - CDN: Unlimited bandwidth                                      │
│ - DNS: Unlimited queries                                        │
│ - DDoS: Unmetered                                               │
│ - Workers: 100K req/day API gateway                             │
│ - Pages: Unlimited static hosting                               │
│ - KV: Market data cache                                         │
└────────────────────┬────────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌──────────────────┐      ┌──────────────────┐
│ GCP (Compute)    │      │ AZURE (Data)     │
│ $70/mo FREE      │      │ $85/mo FREE      │
│                  │      │                  │
│ - Cloud Run      │      │ - Cosmos DB      │
│   2M req/mo      │      │   1000 RU/s      │
│                  │      │                  │
│ - Cloud Funcs    │      │ - Redis Cache    │
│   2M invoke/mo   │      │   250MB          │
│                  │      │                  │
│ - Firestore      │      │ - Functions      │
│   1GB + 50K/day  │      │   1M exec/mo     │
└──────────────────┘      └──────────────────┘
        │                         │
        └────────────┬────────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │ AWS (Storage/Queue)    │
        │ $30/mo FREE            │
        │                        │
        │ - DynamoDB             │
        │   25GB, 25 RCU/WCU     │
        │                        │
        │ - Lambda               │
        │   1M requests/mo       │
        │                        │
        │ - SQS                  │
        │   1M messages/mo       │
        └────────────────────────┘

TOTAL VALUE: ~$885/mo
TOTAL COST: $0/mo
```

## Service Allocation by Need

| Need | Best Free Service | Provider |
|------|------------------|----------|
| API Gateway | Workers (100K req/day) | Cloudflare |
| Python Compute | Cloud Functions (2M/mo) | GCP |
| Containers | Cloud Run (2M req/mo) | GCP |
| NoSQL Database | Cosmos DB (1000 RU/s) | Azure |
| Redis Cache | Redis Cache (250MB) | Azure |
| Object Storage | R2 (10GB, no egress) | Cloudflare |
| Time-Series | DynamoDB (25GB) | AWS |
| Message Queue | SQS (1M msg/mo) | AWS |
| Static Hosting | Pages (unlimited) | Cloudflare |
| CDN/DDoS | CDN (unlimited) | Cloudflare |
| DNS | DNS (unlimited) | Cloudflare |
| Logging | Cloud Logging (50GB/mo) | GCP |

## Cost at Scale

### Small Production (~100K req/day, ~1K users)
```
Cloudflare Workers Paid:   $5/mo
Everything else:           $0 (still under limits)
Total: $5/month
```

### Medium Production (~1M req/day, ~10K users)
```
Cloudflare Workers:        $30/mo
GCP Cloud Functions:       $40/mo
Azure Cosmos DB:           $60/mo
Azure Redis:               $75/mo
AWS DynamoDB:              $25/mo
Total: $230/month (vs $1,000+ single cloud)
```

## Recommended Approach

### For MVP (First 3 months):
**Single Cloud: Azure only**
- Fastest to deploy
- Lowest complexity
- Cosmos DB free tier is huge
- **Cost: $0/month**

### For Production (After validation):
**Hybrid: Cloudflare + Azure + GCP**
- Cloudflare edge (CDN, Workers, Pages)
- Azure data (Cosmos DB, Redis)
- GCP compute (Cloud Functions 2M free)
- **Cost: $0-30/month**

### For Scale (1M+ requests/day):
**Multi-Cloud: All four providers**
- Each provider for its strengths
- No single point of failure
- **Cost: $150-300/month** (vs $1,500+ single cloud)

## Comparison Table

| Need | Best Free | Provider | Monthly Value | Forever? |
|------|-----------|----------|---------------|----------|
| API Gateway | Workers | Cloudflare | $5 | Yes |
| Static Hosting | Pages | Cloudflare | $20 | Yes |
| CDN | CDN | Cloudflare | $200 | Yes |
| DDoS | Shield | Cloudflare | $500 | Yes |
| Python Compute | Cloud Functions | GCP | $40 | Yes |
| Containers | Cloud Run | GCP | $30 | Yes |
| NoSQL | Cosmos DB | Azure | $60 | Yes |
| Redis Cache | Redis Cache | Azure | $15 | Yes |
| Queue | SQS | AWS | $0.40 | Yes |
| Time-Series | DynamoDB | AWS | $6 | Yes |
| Object Storage | R2 | Cloudflare | $0.15 | Yes |
| **TOTAL** | **Multi-Cloud** | **All 4** | **~$917/mo** | **Yes** |

---

# END OF CONSOLIDATED DOCUMENT

**Original Source Files:**
1. CLOUDFLARE_PAID_PLAN_LIMITS.md
2. cloudflare-free-tier-maximization.md
3. free-tier-performance-analysis.md
4. multi-cloud-free-tier-optimization.md
# Coinswarm Deployment Guide

> **Comprehensive deployment documentation for the Coinswarm trading system.**

This guide covers deployment of both the Cloudflare Workers infrastructure (production) and optional Python components (local/cloud).

---

## Table of Contents

1. [Deployment Overview](#deployment-overview)
2. [Quick Start](#quick-start)
3. [Cloudflare Workers Deployment](#cloudflare-workers-deployment)
4. [GitHub Actions CI/CD](#github-actions-cicd)
5. [Manual Wrangler Deployment](#manual-wrangler-deployment)
6. [Environment Configuration](#environment-configuration)
7. [D1 Database Setup](#d1-database-setup)
8. [API Token Configuration](#api-token-configuration)
9. [Free Tier Optimization](#free-tier-optimization)
10. [GCP Cloud Run (Alternative)](#gcp-cloud-run-alternative)
11. [Verification & Monitoring](#verification--monitoring)
12. [Troubleshooting](#troubleshooting)
13. [Cost Analysis](#cost-analysis)

---

## Deployment Overview

### Production Architecture

Coinswarm uses a **hybrid architecture**:

```
                     ┌─────────────────────────────────────┐
                     │     CLOUDFLARE EDGE (Production)     │
                     │                                       │
                     │  ┌─────────────────────────────────┐ │
                     │  │ Evolution Agent (Durable Object) │ │
                     │  │  - Chaos trade generation        │ │
                     │  │  - Pattern discovery             │ │
                     │  │  - Agent competition             │ │
                     │  └─────────────────────────────────┘ │
                     │                  │                    │
                     │  ┌───────────────┴───────────────┐   │
                     │  │                               │   │
                     │  ▼                               ▼   │
                     │  ┌──────────┐         ┌──────────┐  │
                     │  │ D1 SQLite│         │ KV Cache │  │
                     │  │ Database │         │          │  │
                     │  └──────────┘         └──────────┘  │
                     └─────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
          ┌──────────────────┐           ┌──────────────────┐
          │  Data Sources    │           │ Python Agents    │
          │  (Binance, etc.) │           │ (Local/Optional) │
          └──────────────────┘           └──────────────────┘
```

### What's Deployed Where

| Component | Platform | Status | Notes |
|-----------|----------|--------|-------|
| Evolution Agent | Cloudflare Workers | **LIVE** | Primary chaos evolution system |
| Historical Data Worker | Cloudflare Workers | **LIVE** | 5-source data fetching |
| D1 Database | Cloudflare D1 | **LIVE** | `coinswarm-evolution` |
| News Sentiment | Cloudflare Workers | Optional | Requires API keys |
| Python Agents | Local/GCP | Optional | Committee voting system |

---

## Quick Start

### Prerequisites

```bash
# Install Node.js (18+)
node --version  # Should be v18+

# Install Wrangler CLI
npm install -g wrangler

# Login to Cloudflare
wrangler login
```

### Deploy in 5 Minutes

```bash
# 1. Clone repository
git clone https://github.com/TheAIGuyFromAR/Coinswarm.git
cd Coinswarm

# 2. Deploy evolution agent
cd cloudflare-agents
wrangler deploy

# 3. Verify deployment
curl https://coinswarm-evolution-agent.YOUR_SUBDOMAIN.workers.dev/
```

---

## Cloudflare Workers Deployment

### Active Workers

| Worker | Config File | Schedule | Purpose |
|--------|-------------|----------|---------|
| `coinswarm-evolution-agent` | `wrangler.toml` | Every minute | Core chaos evolution |
| `coinswarm-historical-data` | `wrangler-historical.toml` | Hourly | Data collection |
| `coinswarm-realtime-price-cron` | `wrangler-realtime-price-cron.toml` | Every minute | Price feeds |
| `coinswarm-technical-indicators` | `wrangler-technical-indicators.toml` | Hourly | TA calculations |
| `coinswarm-collection-alerts` | `wrangler-collection-alerts.toml` | Every 15 min | Alert monitoring |
| `coinswarm-data-monitor` | `wrangler-monitor.toml` | On-demand | Dashboard |

### Deploy Individual Workers

```bash
cd cloudflare-agents

# Evolution agent (primary)
wrangler deploy --config wrangler.toml

# Historical data collection
wrangler deploy --config wrangler-historical.toml

# Real-time prices
wrangler deploy --config wrangler-realtime-price-cron.toml

# Technical indicators
wrangler deploy --config wrangler-technical-indicators.toml

# Collection alerts
wrangler deploy --config wrangler-collection-alerts.toml

# Monitoring dashboard
wrangler deploy --config wrangler-monitor.toml
```

### Deploy All Workers

```bash
# Using the deployment script
./scripts/deploy-all-workers.sh

# Or manually deploy each
for config in cloudflare-agents/wrangler*.toml; do
  wrangler deploy --config "$config"
done
```

---

## GitHub Actions CI/CD

### Automatic Deployment

The repository uses GitHub Actions for CI/CD:

```yaml
# .github/workflows/deploy-evolution.yml
name: Deploy Evolution System
on:
  push:
    branches: [main]
    paths:
      - 'cloudflare-agents/**'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          workingDirectory: cloudflare-agents
```

### Required GitHub Secrets

Set these in your repository Settings → Secrets → Actions:

| Secret | Description | How to Get |
|--------|-------------|------------|
| `CLOUDFLARE_API_TOKEN` | API token with Workers permissions | See [API Token Configuration](#api-token-configuration) |
| `CLOUDFLARE_ACCOUNT_ID` | Your Cloudflare account ID | Dashboard → Overview → Account ID |
| `CRYPTOCOMPARE_API_KEY` | CryptoCompare API key (optional) | cryptocompare.com |
| `NEWSAPI_KEY` | News API key (optional) | newsapi.org |

### Trigger Manual Deployment

```bash
# Via GitHub CLI
gh workflow run "Deploy Evolution System" --ref main

# Via GitHub UI
# Go to: Actions → Deploy Evolution System → Run workflow
```

---

## Manual Wrangler Deployment

### Install Wrangler

```bash
npm install -g wrangler
```

### Authenticate

```bash
# Browser-based login (recommended)
wrangler login

# Or use API token
export CLOUDFLARE_API_TOKEN="your-token-here"
export CLOUDFLARE_ACCOUNT_ID="your-account-id"
```

### Deploy Commands

```bash
# Deploy with default config
wrangler deploy

# Deploy specific config
wrangler deploy --config wrangler-historical.toml

# Deploy to specific environment
wrangler deploy --env production

# Dry run (see what would be deployed)
wrangler deploy --dry-run

# View deployment logs
wrangler tail coinswarm-evolution-agent
```

### Common Wrangler Commands

```bash
# List all workers
wrangler deployments list

# View worker details
wrangler deployments list --name coinswarm-evolution-agent

# Rollback to previous version
wrangler rollback

# Set secrets
wrangler secret put CRYPTOCOMPARE_API_KEY

# View logs in real-time
wrangler tail
```

---

## Environment Configuration

### Wrangler Configuration Structure

```toml
# wrangler.toml
name = "coinswarm-evolution-agent"
main = "evolution-agent-simple.ts"
compatibility_date = "2025-01-01"
compatibility_flags = ["nodejs_compat"]

# Durable Objects for stateful agents
[durable_objects]
bindings = [
  { name = "EVOLUTION_AGENT", class_name = "EvolutionAgent" }
]

[[migrations]]
tag = "v1"
new_sqlite_classes = ["EvolutionAgent"]

# D1 Database binding
[[d1_databases]]
binding = "DB"
database_name = "coinswarm-evolution"
database_id = "ac4629b2-8240-4378-b3e3-e5262cd9b285"

# AI binding for pattern analysis
[ai]
binding = "AI"

# Cron triggers
[triggers]
crons = ["* * * * *"]  # Every minute

# Observability
[observability]
enabled = true
```

### Environment Variables vs Secrets

**Environment Variables** (public, in wrangler.toml):
```toml
[vars]
LOG_LEVEL = "INFO"
TOKENS = "BTC,ETH,SOL,BNB,ADA,DOT"
```

**Secrets** (private, set via CLI):
```bash
wrangler secret put CRYPTOCOMPARE_API_KEY
wrangler secret put NEWSAPI_KEY
wrangler secret put OPENAI_API_KEY
```

### Local Development

Create `.dev.vars` for local secrets:
```env
CRYPTOCOMPARE_API_KEY=your-key-here
NEWSAPI_KEY=your-key-here
```

Run locally:
```bash
wrangler dev
```

---

## D1 Database Setup

### Create Database

```bash
# Create new D1 database
wrangler d1 create coinswarm-evolution

# Output: Created database 'coinswarm-evolution'
# database_id = "xxxx-xxxx-xxxx"
```

### Apply Schema

```bash
# Apply schema migrations
wrangler d1 execute coinswarm-evolution --file=./database/schemas/core/price_data.sql
wrangler d1 execute coinswarm-evolution --file=./database/schemas/core/chaos_trades.sql
wrangler d1 execute coinswarm-evolution --file=./database/schemas/core/discovered_patterns.sql
```

### Core Tables

```sql
-- price_data: Historical OHLCV data
CREATE TABLE IF NOT EXISTS price_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    timeframe TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    source TEXT DEFAULT 'binance',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(token, timestamp, timeframe, source)
);

-- chaos_trades: Random trade experiments
CREATE TABLE IF NOT EXISTS chaos_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL,
    entry_time INTEGER NOT NULL,
    exit_time INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    profitable INTEGER NOT NULL,
    momentum_1 REAL,
    momentum_5 REAL,
    volatility REAL,
    volume_ratio REAL,
    created_at TEXT DEFAULT (datetime('now'))
);

-- discovered_patterns: Learned trading patterns
CREATE TABLE IF NOT EXISTS discovered_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    conditions TEXT NOT NULL,
    votes INTEGER DEFAULT 0,
    win_rate REAL,
    avg_return_pct REAL,
    annualized_roi_pct REAL,
    sample_size INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
```

### Query Database

```bash
# Run ad-hoc queries
wrangler d1 execute coinswarm-evolution --command="SELECT COUNT(*) FROM price_data"

# Export data
wrangler d1 execute coinswarm-evolution --command="SELECT * FROM chaos_trades LIMIT 100" --json > trades.json
```

---

## API Token Configuration

### Create Cloudflare API Token

1. Go to: https://dash.cloudflare.com/profile/api-tokens
2. Click **Create Token**
3. Select **"Edit Cloudflare Workers"** template

### Required Permissions

| Permission | Type | Access |
|------------|------|--------|
| Account → Workers Scripts | Edit | Deploy workers |
| Account → Workers KV Storage | Edit | Manage KV stores |
| Account → D1 | Edit | Manage databases |
| Account → Account Settings | Read | For `/memberships` endpoint |
| Zone → Workers Routes | Edit | Configure routes |

### Token Setup

```bash
# Method 1: Environment variable
export CLOUDFLARE_API_TOKEN="your-token-here"

# Method 2: Wrangler config
wrangler config

# Method 3: GitHub Secrets
# Go to: Repository Settings → Secrets → Actions
# Add: CLOUDFLARE_API_TOKEN
```

### Verify Token

```bash
# Test token access
curl -X GET "https://api.cloudflare.com/client/v4/accounts" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"

# Or via wrangler
wrangler whoami
```

---

## Free Tier Optimization

### Cloudflare Free Tier Limits

| Service | Free Limit | Strategy |
|---------|------------|----------|
| Workers | 100K req/day, 10ms CPU | Split across multiple workers |
| D1 | 5M reads/day, 100K writes/day | Use KV for hot cache |
| KV | 100K reads/day, 1K writes/day | Batch writes |
| R2 | 10GB storage | Archive historical data |
| Workers AI | 10K neurons/day | Limit AI calls |

### Architecture for Free Tier

```
┌───────────────────────────────────────────────────────┐
│            CLOUDFLARE FREE TIER ONLY                   │
├───────────────────────────────────────────────────────┤
│  Frontend: Pages (unlimited) ✓                        │
│  API: Workers (100K req/day) ✓                        │
│  Cache: KV (100K reads, 1K writes) ✓                  │
│  Database: D1 (5M reads, 100K writes) ✓               │
│  Storage: R2 (10GB) ✓                                 │
│  AI: Workers AI (10K neurons) - Limited               │
│                                                        │
│  Cost: $0/month                                       │
│  Limits: Good for MVP, ~1K users                      │
└───────────────────────────────────────────────────────┘
```

### Caching Strategy

```typescript
// worker.ts - Smart caching to stay under limits
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const cacheKey = request.url;

    // Check KV cache first
    const cached = await env.KV.get(cacheKey);
    if (cached) return new Response(cached);

    // Query D1
    const result = await env.DB.prepare('SELECT ...').all();

    // Cache for 5 seconds
    await env.KV.put(cacheKey, JSON.stringify(result), {
      expirationTtl: 5
    });

    return new Response(JSON.stringify(result));
  }
}
```

### When to Upgrade

| Trigger | Threshold | Cost to Upgrade |
|---------|-----------|-----------------|
| KV writes | >1K/day | Workers Paid: $5/mo |
| Requests | >100K/day | Workers Paid: $5/mo |
| D1 reads | >5M/day | D1 Paid: $5/mo |
| **Total** | Production scale | **~$15/month** |

---

## GCP Cloud Run (Alternative)

For Python agents or monolithic deployment:

### Prerequisites

```bash
# Install gcloud CLI
curl https://sdk.cloud.google.com | bash
gcloud auth login
export GCP_PROJECT_ID="your-project-id"
gcloud config set project $GCP_PROJECT_ID
```

### Deploy Python Agents

```bash
# Build and push image
docker build -f Dockerfile.agents -t gcr.io/$GCP_PROJECT_ID/coinswarm-agents .
docker push gcr.io/$GCP_PROJECT_ID/coinswarm-agents

# Deploy to Cloud Run
gcloud run deploy coinswarm-agents \
  --image=gcr.io/$GCP_PROJECT_ID/coinswarm-agents \
  --region=us-east4 \
  --memory=4Gi \
  --cpu=2 \
  --min-instances=1 \
  --max-instances=1
```

### GCP Free Tier Limits

| Resource | Free Limit |
|----------|------------|
| Cloud Run | 2M requests/mo |
| Container Registry | 50GB storage |
| Secret Manager | Included |

---

## Verification & Monitoring

### Test Worker Endpoints

```bash
# Evolution agent
curl https://coinswarm-evolution-agent.YOUR_SUBDOMAIN.workers.dev/

# Expected response:
{
  "status": "ok",
  "name": "Evolution Agent",
  "cycles": 1234,
  "patterns_discovered": 42
}

# Historical data
curl https://coinswarm-historical-data.YOUR_SUBDOMAIN.workers.dev/

# Data monitor dashboard
curl https://coinswarm-data-monitor.YOUR_SUBDOMAIN.workers.dev/
```

### View Logs

```bash
# Real-time logs
wrangler tail coinswarm-evolution-agent

# Filter errors only
wrangler tail coinswarm-evolution-agent --format=json | grep ERROR

# GitHub Actions logs
gh run view --log-failed
```

### Check Cron Schedules

```bash
# List deployments with cron info
wrangler deployments list --name coinswarm-evolution-agent

# Verify in Cloudflare Dashboard
# Workers & Pages → Your Worker → Triggers
```

### Monitor D1 Database

```bash
# Check row counts
wrangler d1 execute coinswarm-evolution \
  --command="SELECT
    (SELECT COUNT(*) FROM price_data) as prices,
    (SELECT COUNT(*) FROM chaos_trades) as trades,
    (SELECT COUNT(*) FROM discovered_patterns) as patterns"
```

---

## Troubleshooting

### Common Issues

#### "Worker not found"
**Cause:** Deployment failed or wrong URL
```bash
# Check deployed workers
wrangler deployments list

# Redeploy
wrangler deploy --config wrangler.toml
```

#### "Database binding error"
**Cause:** D1 database ID mismatch
```bash
# Verify database exists
wrangler d1 list

# Update database_id in wrangler.toml
```

#### "Unauthorized" API errors
**Cause:** Invalid or expired API token
```bash
# Test token
wrangler whoami

# Re-authenticate
wrangler login
```

#### "CPU time exceeded"
**Cause:** Worker doing too much computation
```bash
# Check worker metrics in dashboard
# Optimize hot paths, add caching
```

### GitHub Actions Failures

```bash
# View failed runs
gh run list --status=failure

# View logs for specific run
gh run view <run-id> --log-failed

# Manually trigger
gh workflow run "Deploy Evolution System"
```

### Rollback

```bash
# List previous deployments
wrangler deployments list --name coinswarm-evolution-agent

# Rollback to previous version
wrangler rollback --name coinswarm-evolution-agent
```

---

## Cost Analysis

### Monthly Cost Comparison

| Scenario | Traditional Cloud | Cloudflare Hybrid | Savings |
|----------|-------------------|-------------------|---------|
| **MVP** | ~$167/mo | ~$0-25/mo | **85-100%** |
| **Production** | ~$1,050/mo | ~$290/mo | **72%** |
| **Scale** | ~$4,200/mo | ~$920/mo | **78%** |

### MVP Cost Breakdown (Cloudflare Free)

| Component | Cost |
|-----------|------|
| Workers | $0 (100K req/day free) |
| D1 Database | $0 (5M reads/day free) |
| KV Storage | $0 (100K reads/day free) |
| R2 Storage | $0 (10GB free) |
| Workers AI | $0 (10K neurons/day free) |
| **Total** | **$0/month** |

### Production Cost Breakdown

| Component | Free Tier | Paid (~$25/mo) |
|-----------|-----------|----------------|
| Workers | 100K req/day | 10M req/month |
| D1 | 5M reads/day | 50M reads/month |
| KV | 1K writes/day | 1M writes/month |
| Durable Objects | Not included | Included |

---

## Related Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture overview
- [DATA_PIPELINE.md](DATA_PIPELINE.md) - Data collection details
- [AGENTS.md](AGENTS.md) - Agent implementation guide
- [DEVELOPMENT.md](DEVELOPMENT.md) - Local development setup

---

*Last Updated: 2025-11-29*
*Consolidated from 15+ deployment documents*
# Deployment Checklist

**Comprehensive deployment checklist for Coinswarm Evolution System updates**

Use this checklist when deploying new features, migrations, or system updates.

---

## Pre-Deployment Checklist

### 1. Code Review

- [ ] All code changes reviewed and approved
- [ ] No hardcoded secrets or API keys
- [ ] Error handling implemented
- [ ] Logging added for critical operations
- [ ] Performance optimizations applied

### 2. Testing

- [ ] Unit tests passing (`pytest pyswarm/tests/`)
- [ ] Integration tests passing
- [ ] Manual testing completed
- [ ] Edge cases tested
- [ ] Performance benchmarks acceptable

### 3. Documentation

- [ ] Code comments added
- [ ] API documentation updated (`docs/API_REFERENCE.md`)
- [ ] Architecture docs updated if needed
- [ ] Migration notes documented
- [ ] Rollback procedure documented

---

## Database Migrations

### Migrations to Run (in order)

Run these migrations against the `coinswarm-evolution` D1 database:

#### Core Metrics Migrations

- [ ] **013-advanced-metrics-safe.sql** - Add Sortino, Calmar, Ulcer Index columns
  ```bash
  wrangler d1 execute coinswarm-evolution --file=cloudflare-agents/migrations/013-advanced-metrics-safe.sql
  ```

#### Token & Regime Tracking

- [ ] **017-add-regime-column.sql** - Add regime column to chaos_trades
  ```bash
  wrangler d1 execute coinswarm-evolution --file=cloudflare-agents/migrations/017-add-regime-column.sql
  ```

- [ ] **028-token-specialization.sql** - Create agent_token_performance table
  ```bash
  wrangler d1 execute coinswarm-evolution --file=cloudflare-agents/migrations/028-token-specialization.sql
  ```

#### Agent Correlation

- [ ] **028-agent-correlation-matrix.sql** - Create correlation tracking tables
  ```bash
  wrangler d1 execute coinswarm-evolution --file=cloudflare-agents/migrations/028-agent-correlation-matrix.sql
  ```

#### Alpha Decay Tracking

- [ ] **029-alpha-decay-tracking.sql** - Add alpha_status and decay tracking
  ```bash
  wrangler d1 execute coinswarm-evolution --file=cloudflare-agents/migrations/029-alpha-decay-tracking.sql
  ```

#### Divergence Alerts

- [ ] **030-divergence-alerts.sql** - Create divergence_alerts table
  ```bash
  wrangler d1 execute coinswarm-evolution --file=cloudflare-agents/migrations/030-divergence-alerts.sql
  ```

#### Diversity Monitoring

- [ ] **031-diversity-snapshots.sql** - Create diversity_snapshots table
  ```bash
  wrangler d1 execute coinswarm-evolution --file=cloudflare-agents/migrations/031-diversity-snapshots.sql
  ```

---

## Worker Deployments

### 1. Evolution Agent

- [ ] Update `cloudflare-agents/evolution-agent-simple.ts` if needed
- [ ] Test locally with `wrangler dev`
- [ ] Deploy to production:
  ```bash
  cd cloudflare-agents
  wrangler deploy --config wrangler.toml
  ```
- [ ] Verify deployment:
  ```bash
  curl https://coinswarm-evolution-agent.workers.dev/health
  ```

### 2. Dashboards Worker

- [ ] Update `cloudflare-agents/dashboards-worker.ts` with new endpoints
- [ ] Test API endpoints locally
- [ ] Deploy:
  ```bash
  wrangler deploy dashboards-worker.ts
  ```
- [ ] Verify endpoints:
  ```bash
  curl https://coinswarm-dashboards.workers.dev/api/diversity
  curl https://coinswarm-dashboards.workers.dev/api/alerts
  curl https://coinswarm-dashboards.workers.dev/api/correlation-matrix
  ```

### 3. Cron Workers (if applicable)

- [ ] **correlation-matrix-cron.ts** - Daily correlation matrix updates
  ```bash
  wrangler deploy correlation-matrix-cron.ts
  ```

---

## R2 Buckets

### Create Required Buckets

- [ ] **coinswarm-agent-history** - Agent run history storage
  ```bash
  wrangler r2 bucket create coinswarm-agent-history
  ```

- [ ] Configure bucket access in `wrangler.toml`:
  ```toml
  [[r2_buckets]]
  binding = "AGENT_HISTORY"
  bucket_name = "coinswarm-agent-history"
  ```

---

## Configuration Updates

### Environment Variables

- [ ] Update secrets if needed:
  ```bash
  wrangler secret put AI_GATEWAY_TOKEN
  ```

### D1 Bindings

- [ ] Verify D1 bindings in `wrangler.toml`:
  ```toml
  [[d1_databases]]
  binding = "DB"
  database_name = "coinswarm-evolution"
  database_id = "your-database-id"
  ```

---

## Post-Deployment Verification

### 1. Database Health Check

- [ ] Verify migrations applied successfully:
  ```bash
  wrangler d1 execute coinswarm-evolution --command="
    SELECT name FROM sqlite_master WHERE type='table'
    ORDER BY name;
  "
  ```

- [ ] Check for new columns:
  ```bash
  wrangler d1 execute coinswarm-evolution --command="
    PRAGMA table_info(discovered_patterns);
  "
  ```

- [ ] Verify data integrity:
  ```bash
  wrangler d1 execute coinswarm-evolution --command="
    SELECT COUNT(*) as total_patterns,
           SUM(CASE WHEN alpha_status IS NOT NULL THEN 1 ELSE 0 END) as with_alpha_status
    FROM discovered_patterns;
  "
  ```

### 2. API Endpoint Testing

Test all new endpoints:

- [ ] **/api/diversity** - Diversity metrics
  ```bash
  curl https://coinswarm-dashboards.workers.dev/api/diversity
  ```

- [ ] **/api/alerts** - Divergence alerts
  ```bash
  curl https://coinswarm-dashboards.workers.dev/api/alerts
  ```

- [ ] **/api/correlation-matrix** - Agent correlations
  ```bash
  curl https://coinswarm-dashboards.workers.dev/api/correlation-matrix
  ```

- [ ] **/api/agents/{agent_id}/token-performance** - Token specialization
  ```bash
  curl https://coinswarm-dashboards.workers.dev/api/agents/agent_123/token-performance
  ```

- [ ] **/api/patterns/decay-analysis** - Alpha decay
  ```bash
  curl https://coinswarm-dashboards.workers.dev/api/patterns/decay-analysis
  ```

### 3. Dashboard Testing

- [ ] `/diversity` dashboard loads
- [ ] `/alerts` dashboard loads
- [ ] `/agents` dashboard shows new metrics (Sortino, Calmar)
- [ ] `/patterns` dashboard shows alpha decay status
- [ ] All charts/visualizations render correctly

### 4. Evolution Agent Testing

- [ ] Trigger evolution cycle:
  ```bash
  curl https://coinswarm-evolution-agent.workers.dev/trigger
  ```

- [ ] Monitor logs:
  ```bash
  wrangler tail coinswarm-evolution-agent
  ```

- [ ] Verify new metrics calculated:
  ```bash
  wrangler d1 execute coinswarm-evolution --command="
    SELECT agent_id, sortino_ratio, calmar_ratio, alpha_status
    FROM trading_agents
    WHERE sortino_ratio IS NOT NULL
    LIMIT 5;
  "
  ```

### 5. Alert System Testing

- [ ] Create test divergence condition
- [ ] Verify alert created in database
- [ ] Check alert appears in `/api/alerts`
- [ ] Test alert acknowledgement:
  ```bash
  curl -X POST https://coinswarm-dashboards.workers.dev/api/alerts/{alert_id}/acknowledge \
    -H "Content-Type: application/json" \
    -d '{"acknowledged_by":"test@example.com","notes":"Test"}'
  ```

### 6. Diversity Monitoring Testing

- [ ] Trigger diversity calculation
- [ ] Verify snapshot created
- [ ] Check health score calculated
- [ ] Verify warnings/recommendations generated

---

## Performance Monitoring

### 1. Response Times

- [ ] API endpoints respond < 500ms (P95)
- [ ] Database queries < 100ms (P95)
- [ ] Dashboard loads < 2s

### 2. Error Rates

- [ ] Error rate < 1% on all endpoints
- [ ] No 500 errors in logs
- [ ] Graceful degradation on failures

### 3. Resource Usage

- [ ] CPU usage within limits
- [ ] Memory usage stable
- [ ] D1 query count within quota
- [ ] R2 storage within limits

---

## Rollback Procedure

If issues are detected:

### 1. Identify Problem

- [ ] Check error logs:
  ```bash
  wrangler tail coinswarm-evolution-agent --format=json
  ```

- [ ] Check database state:
  ```bash
  wrangler d1 execute coinswarm-evolution --command="
    SELECT * FROM schema_version ORDER BY applied_at DESC LIMIT 5;
  "
  ```

### 2. Rollback Workers

- [ ] Revert to previous deployment:
  ```bash
  wrangler rollback coinswarm-evolution-agent
  wrangler rollback dashboards-worker
  ```

### 3. Rollback Migrations (if needed)

**WARNING: Data loss possible. Use with caution.**

For each migration, create reverse migration:

```sql
-- Reverse 031-diversity-snapshots.sql
DROP TABLE IF EXISTS diversity_snapshots;

-- Reverse 030-divergence-alerts.sql
DROP TABLE IF EXISTS divergence_alerts;
DROP TABLE IF EXISTS divergence_thresholds;

-- Reverse 029-alpha-decay-tracking.sql
ALTER TABLE discovered_patterns DROP COLUMN alpha_status;
ALTER TABLE discovered_patterns DROP COLUMN alpha_decay_ratio;
ALTER TABLE discovered_patterns DROP COLUMN last_positive_date;
```

Apply rollback:
```bash
wrangler d1 execute coinswarm-evolution --file=rollback-migrations.sql
```

### 4. Verify Rollback

- [ ] System functional
- [ ] No errors in logs
- [ ] Dashboards loading
- [ ] API endpoints responding

---

## Communication

### Stakeholder Notifications

- [ ] Notify team of deployment start
- [ ] Update status page (if applicable)
- [ ] Document any breaking changes
- [ ] Notify of deployment completion
- [ ] Share performance metrics

---

## Post-Deployment Tasks

### 1. Monitoring Setup

- [ ] Set up alerts for new metrics
- [ ] Configure dashboard monitoring
- [ ] Schedule regular diversity checks

### 2. Documentation Updates

- [ ] Update `CHANGELOG.md`
- [ ] Update version numbers
- [ ] Archive old deployment docs

### 3. Performance Baseline

- [ ] Record baseline metrics
- [ ] Document expected behavior
- [ ] Set monitoring thresholds

---

## Deployment Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Developer | | | |
| Reviewer | | | |
| Deployer | | | |

---

## Emergency Contacts

- **On-Call Engineer:** [Contact]
- **Database Admin:** [Contact]
- **Cloudflare Support:** https://dash.cloudflare.com/support

---

## Appendix: Common Issues

### Issue: Migration Fails with "Column Already Exists"

**Solution:** Safe migrations use `ADD COLUMN IF NOT EXISTS` or check existing columns first.

```sql
-- Safe migration
ALTER TABLE agents ADD COLUMN sortino_ratio REAL;
-- If fails, column already exists - OK to continue
```

### Issue: Worker Deployment Fails

**Solution:** Check `wrangler.toml` syntax and bindings:

```bash
wrangler deploy --dry-run
```

### Issue: API Returns 500 Errors

**Solution:** Check worker logs:

```bash
wrangler tail worker-name --format=pretty
```

### Issue: Metrics Not Calculating

**Solution:** Verify migration applied and trigger recalculation:

```bash
curl https://coinswarm-evolution-agent.workers.dev/recalculate-metrics
```

---

*Last Updated: 2025-12-05*

---

## Quick Deploy Commands

**Full deployment from scratch:**

```bash
# 1. Run all migrations
cd cloudflare-agents/migrations
for f in 013-advanced-metrics-safe.sql 028-token-specialization.sql 029-alpha-decay-tracking.sql 030-divergence-alerts.sql 031-diversity-snapshots.sql; do
  wrangler d1 execute coinswarm-evolution --file=$f
done

# 2. Deploy workers
cd ..
wrangler deploy evolution-agent-simple.ts
wrangler deploy dashboards-worker.ts

# 3. Create R2 buckets
wrangler r2 bucket create coinswarm-agent-history

# 4. Verify
curl https://coinswarm-dashboards.workers.dev/api/diversity
curl https://coinswarm-dashboards.workers.dev/api/alerts
```

---
# Data Collection Deployment & Monitoring Guide

## Current Deployment Status

**Branch**: `claude/full-code-review-011CUvqUcjpgrh9x49XzAs2v`

**Last Commits**:
- `26f8f88` - Run cron 24/7 every hour with exponential backoff
- `da30177` - Set rate limiting to 75% of max
- `41dd83b` - Add historical data collection cron worker

**Deployment**: In progress via GitHub Actions

---

## What's Been Deployed

### 1. Historical Data Collection Cron Worker
- **Name**: `coinswarm-historical-collection-cron`
- **URL**: https://coinswarm-historical-collection-cron.bamn86.workers.dev
- **Schedule**: Every hour (24/7)
- **Purpose**: Slowly collect 5 years of OHLCV data for 15 tokens

### 2. Historical Data Worker (Updated)
- **Name**: `coinswarm-historical-data`
- **URL**: https://coinswarm-historical-data.bamn86.workers.dev
- **Purpose**: On-demand historical data fetching with 5-tier fallback

---

## Monitoring Commands

### Check Cron Worker Status
```bash
# Get worker info
curl https://coinswarm-historical-collection-cron.bamn86.workers.dev/

# Check collection progress for all tokens
curl https://coinswarm-historical-collection-cron.bamn86.workers.dev/status | jq '.'

# Manual trigger (for testing)
curl https://coinswarm-historical-collection-cron.bamn86.workers.dev/collect | jq '.'
```

### Check Historical Data Worker
```bash
# Get worker info
curl https://coinswarm-historical-data.bamn86.workers.dev/

# Test data fetch for SOL
curl "https://coinswarm-historical-data.bamn86.workers.dev/fetch-fresh?symbol=SOLUSDT&limit=50" | jq '{success, source, candleCount}'

# Test data fetch for BTC
curl "https://coinswarm-historical-data.bamn86.workers.dev/fetch-fresh?symbol=BTCUSDT&limit=50" | jq '{success, source, candleCount}'
```

### Check Database (via Evolution Agent)
```bash
# Check price_data table
curl https://coinswarm-evolution-agent.bamn86.workers.dev/debug/db | jq '.tables'

# Query for collected data
# (Need to add a query endpoint or use D1 directly)
```

---

## Expected Progress Tracking

### Status Response Format
```json
{
  "success": true,
  "tokens": [
    {
      "symbol": "BTCUSDT",
      "coin_id": "bitcoin",
      "days_collected": 30,
      "total_days": 1825,
      "status": "pending",
      "error_count": 0,
      "last_run": 1762665308425
    },
    // ... more tokens
  ],
  "totalTokens": 15,
  "completedTokens": 0
}
```

### Status Values
- **`pending`**: Waiting to be processed
- **`in_progress`**: Currently collecting
- **`completed`**: Fully collected (1825 days)
- **`paused`**: Paused due to 3 consecutive errors

### Progress Calculation
```
Progress = (days_collected / total_days) * 100
```

Example:
- Token: BTC
- Days collected: 365
- Total days: 1825
- Progress: 20%

---

## Troubleshooting

### Error 1042
**Symptom**: Worker returns `error code: 1042`

**Possible Causes**:
1. D1 database binding not properly configured
2. Worker still deploying
3. API secret (COINGECKO) not set

**Fix**:
1. Wait 2-3 minutes for deployment to complete
2. Verify COINGECKO secret is set in GitHub repository secrets
3. Check GitHub Actions logs for deployment errors

### Worker Not Responding
**Symptom**: Worker returns TLS errors or timeouts

**Possible Causes**:
1. Deployment still in progress
2. Cloudflare experiencing issues

**Fix**:
1. Wait 5-10 minutes
2. Check Cloudflare status: https://www.cloudflarestatus.com/
3. Try again later

### Paused Tokens
**Symptom**: Token status shows `paused`

**Possible Causes**:
1. 3 consecutive API failures
2. Invalid coin_id for CoinGecko
3. Rate limit exceeded

**Fix**:
1. Check `last_error` field in status response
2. Verify coin_id is correct
3. Manually reset error count in database:
   ```sql
   UPDATE collection_progress
   SET error_count = 0, status = 'pending', last_error = NULL
   WHERE symbol = 'BTCUSDT';
   ```

### No Data Being Collected
**Symptom**: `days_collected` not increasing after multiple hours

**Possible Causes**:
1. Cron trigger not running
2. All tokens paused
3. API key invalid

**Fix**:
1. Manually trigger: `/collect` endpoint
2. Check status for paused tokens
3. Verify COINGECKO secret is valid
4. Check Cloudflare Workers logs (requires dashboard access)

---

## Collection Timeline

### Current Configuration
- **Tokens**: 15
- **Days per run**: 30
- **Total days**: 1825 (5 years)
- **Runs per token**: 1825 / 30 = 61 runs
- **Schedule**: Every hour
- **Completion**: ~40 days

### Timeline Breakdown
| Day | Expected Progress |
|-----|-------------------|
| 1   | ~15 tokens × 30 days = 450 days total |
| 7   | ~3150 days total (~12% complete) |
| 14  | ~6300 days total (~23% complete) |
| 21  | ~9450 days total (~35% complete) |
| 30  | ~13500 days total (~49% complete) |
| 40  | ~27375 days total (100% complete) |

---

## Rate Limiting Details

### CoinGecko API
- **Free tier**: 30 calls/min, 10k calls/month
- **Current usage**: 22.5 calls/min (75% of limit)
- **Monthly usage**: ~720 calls/month (7.2% of limit)

### Safety Margins
- **Per-minute**: 25% buffer (7.5 calls/min unused)
- **Monthly**: 92.8% buffer (9,280 calls/month unused)

---

## Data Quality Checks

### Verify Candle Count
```bash
# Should return ~30 candles per run
curl https://coinswarm-historical-collection-cron.bamn86.workers.dev/status | \
  jq '.tokens[] | select(.symbol == "BTCUSDT") | .days_collected'
```

### Check for Gaps
```sql
-- Query D1 database directly (requires wrangler)
SELECT symbol, COUNT(*) as candle_count, MIN(timestamp) as first, MAX(timestamp) as last
FROM price_data
GROUP BY symbol;
```

### Verify Data Freshness
```bash
# Check last run time
curl https://coinswarm-historical-collection-cron.bamn86.workers.dev/status | \
  jq '.tokens[] | {symbol, last_run, status}'
```

---

## Next Steps After Collection Completes

1. **Verify completeness**: All 15 tokens at 1825 days
2. **Build Technical Indicators Agent**: Calculate 50+ indicators
3. **Build Sentiment Analysis Agent**: Add news/Fear & Greed data
4. **Build Macroeconomic Agent**: Add FRED/Treasury data
5. **Generate Chaos Trades**: With full 150+ column context

---

## Quick Health Check Script

```bash
#!/bin/bash
# health-check.sh

echo "=== Data Collection Health Check ==="
echo ""

# Check worker status
echo "1. Checking cron worker..."
STATUS=$(curl -s https://coinswarm-historical-collection-cron.bamn86.workers.dev/status)

if [ $? -eq 0 ]; then
  echo "✅ Worker responding"

  COMPLETED=$(echo $STATUS | jq '.completedTokens')
  TOTAL=$(echo $STATUS | jq '.totalTokens')
  echo "   Completed: $COMPLETED / $TOTAL tokens"

  PAUSED=$(echo $STATUS | jq '[.tokens[] | select(.status == "paused")] | length')
  if [ "$PAUSED" -gt 0 ]; then
    echo "⚠️  $PAUSED tokens paused"
  fi
else
  echo "❌ Worker not responding"
fi

echo ""
echo "2. Checking historical data worker..."
TEST=$(curl -s "https://coinswarm-historical-data.bamn86.workers.dev/fetch-fresh?symbol=SOLUSDT&limit=10")

if echo $TEST | jq -e '.success' > /dev/null 2>&1; then
  SOURCE=$(echo $TEST | jq -r '.source')
  COUNT=$(echo $TEST | jq '.candleCount')
  echo "✅ Fetched $COUNT candles from $SOURCE"
else
  echo "❌ Data fetch failed"
fi

echo ""
echo "=== End Health Check ==="
```

---

## Contact & Support

If issues persist:
1. Check GitHub Actions logs for deployment errors
2. Verify all secrets are set correctly
3. Review Cloudflare Workers logs (dashboard required)
4. Wait 24 hours and check progress again

**Remember**: The system is designed to run slowly and safely. Don't worry if progress seems slow - that's by design to stay well under API rate limits.
# Historical Data Queue Deployment Guide

This guide shows you how to deploy the queue-based historical data ingestion system that solves your D1 write throughput problem.

## Problem Solved

**Before (Without Queues):**
- Fetching 10,000+ data points
- Each D1 INSERT takes 10-50ms
- Total time: 100-500 seconds ❌
- D1 gets overwhelmed, writes fail
- Cron times out

**After (With Queues):**
- Fetching 10,000+ data points
- Queue all data points: 1-2 seconds ✅
- D1 writes happen async in batches
- Throughput: 500-1000 rows/sec ✅
- No timeouts, no failures

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  PRODUCER (Fast - Completes in seconds)                     │
├─────────────────────────────────────────────────────────────┤
│  1. Cron triggers every 15 min                              │
│  2. Fetch from Binance/CoinGecko/CryptoCompare             │
│  3. Queue all data points (NO D1 writes)                   │
│  4. Return success immediately                              │
└─────────────────────────────────────────────────────────────┘
                              ↓
                    [Cloudflare Queue]
                   (Reliable, Durable)
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  CONSUMER (Efficient - Batch writes)                        │
├─────────────────────────────────────────────────────────────┤
│  1. Receives batches of 100 messages                        │
│  2. Deduplicates data points                                │
│  3. Batch INSERT to D1 (100x faster)                       │
│  4. Retries on D1 overload                                  │
│  5. Acks messages on success                                │
└─────────────────────────────────────────────────────────────┘
```

---

## Deployment Steps

### 1. Create D1 Database (if not exists)

```bash
cd cloudflare-agents

# Create D1 database
wrangler d1 create coinswarm-db

# Note the database_id from output
```

### 2. Apply D1 Schema

```bash
# Create tables and indexes
wrangler d1 execute coinswarm-db \
  --file=d1-schema-historical-prices-queue.sql \
  --remote
```

### 3. Create Queue

```bash
# Create the queue
wrangler queues create historical-data-queue

# Create dead letter queue (for failed messages)
wrangler queues create historical-data-dlq
```

### 4. Update wrangler.toml

Edit `wrangler-historical-queue.toml`:

```toml
# Replace YOUR_D1_DATABASE_ID with actual ID from step 1
database_id = "abc123-your-actual-database-id"

# Add your API keys
[vars]
COINGECKO = "CG-your-key"
CRYPTOCOMPARE_API_KEY = "your-cryptocompare-key"
```

### 5. Deploy Producer Worker

```bash
# Deploy the cron worker that fetches data
wrangler deploy \
  --config wrangler-historical-queue.toml \
  historical-data-queue-producer.ts
```

### 6. Deploy Consumer Worker

```bash
# Deploy the queue consumer that writes to D1
wrangler deploy \
  --config wrangler-historical-queue.toml \
  historical-data-queue-consumer.ts
```

### 7. Test the System

```bash
# Trigger the cron manually to test
wrangler cron trigger historical-data-queue-producer

# Check queue stats
wrangler queues list

# View queue metrics
wrangler queues consumer historical-data-queue
```

---

## Monitoring

### Check Producer Logs

```bash
wrangler tail historical-data-queue-producer --format pretty
```

**Expected output:**
```
✅ Queued 12,450 data points in 2,134ms
   Average: 0.17ms per point
   D1 writes will happen async via queue consumer
```

### Check Consumer Logs

```bash
wrangler tail historical-data-queue-consumer --format pretty
```

**Expected output:**
```
📥 Processing batch of 100 data points
   Deduplicated: 100 → 98 unique points
✅ Inserted 98 rows in 156ms
   Throughput: 628 rows/sec
```

### Query D1 to Verify Data

```bash
# Count rows
wrangler d1 execute coinswarm-db \
  --command "SELECT COUNT(*) FROM historical_prices" \
  --remote

# Check latest data
wrangler d1 execute coinswarm-db \
  --command "SELECT * FROM latest_prices ORDER BY latest_timestamp DESC LIMIT 10" \
  --remote

# View coverage stats
wrangler d1 execute coinswarm-db \
  --command "SELECT * FROM data_coverage ORDER BY data_points DESC" \
  --remote

# Check ingestion performance
wrangler d1 execute coinswarm-db \
  --command "SELECT * FROM ingestion_performance" \
  --remote
```

---

## Performance Expectations

### Producer Performance
- **Fetching**: 1-3 seconds for all sources
- **Queuing**: 200-500ms for 10,000 points
- **Total**: 2-4 seconds per cron run
- **Success Rate**: 99.9%+ (no D1 bottleneck)

### Consumer Performance
- **Throughput**: 500-1000 rows/sec
- **Batch Size**: 100 messages per batch
- **Processing Time**: 100-200ms per batch
- **10,000 points**: Processed in 10-20 seconds

### Cost Estimate

**Queue Operations** (1M included):
- 13 tokens × 1000 data points/run × 96 runs/day = 1,248,000 messages/day
- Each message = 3 operations (write, read, ack)
- Total: ~3.7M operations/day
- **Cost after free tier**: ~$1.10/day or ~$33/month

**D1 Usage** (25B reads, 50M writes included):
- Writes: ~1.2M rows/day = ~36M rows/month
- Reads: Minimal (only for dedup checks)
- **Under included limits**: $0

---

## Troubleshooting

### Queue is Backing Up

**Symptoms**: Queue depth keeps increasing

**Causes**:
- D1 overloaded
- Consumer not processing fast enough
- Too many retries

**Solutions**:
```bash
# Check queue depth
wrangler queues consumer historical-data-queue

# Increase consumer concurrency
# Edit wrangler-historical-queue.toml:
max_concurrency = 10  # Increase from 5

# Redeploy consumer
wrangler deploy historical-data-queue-consumer
```

### Messages Going to Dead Letter Queue

**Symptoms**: `historical-data-dlq` has messages

**Check failed messages**:
```bash
# Query failed ingestions
wrangler d1 execute coinswarm-db \
  --command "SELECT * FROM failed_ingestions ORDER BY failed_at DESC LIMIT 10" \
  --remote
```

**Common causes**:
- Duplicate key violations (normal, handled with INSERT OR IGNORE)
- D1 database locked for >30 seconds
- Invalid data format

### Producer Timing Out

**Symptoms**: Cron fails with timeout

**Solutions**:
- Reduce number of tokens fetched per run
- Decrease API request timeouts
- Split into multiple cron jobs

---

## Scaling Guidelines

### Current Setup
- **13 tokens**
- **3 sources** per token
- **~1000 points** per source
- **Total**: ~40,000 points per cron run

### If You Add More Tokens

| Tokens | Points/Run | Queue Ops/Day | Cost/Month |
|--------|------------|---------------|------------|
| 13     | 40,000     | 11.5M         | $4.20      |
| 25     | 75,000     | 21.6M         | $8.20      |
| 50     | 150,000    | 43.2M         | $16.80     |
| 100    | 300,000    | 86.4M         | $33.60     |

### Optimization Tips

1. **Reduce Fetch Frequency**: Change cron from 15min → 30min
2. **Increase Batch Size**: 100 → 500 messages per batch (if D1 can handle)
3. **Parallel Consumers**: Increase `max_concurrency` from 5 → 20
4. **Use KV for Deduplication**: Cache recent timestamps to skip already-fetched data

---

## Advanced Features

### Add Monitoring Dashboard

Create a dashboard worker to visualize ingestion stats:

```typescript
// dashboard.ts
export default {
  async fetch(request: Request, env: Env) {
    const stats = await env.DB.prepare(`
      SELECT * FROM ingestion_performance
    `).all();

    return new Response(JSON.stringify(stats), {
      headers: { 'Content-Type': 'application/json' }
    });
  }
}
```

### Add Alerts for Queue Backlog

```bash
# Set up alert (Cloudflare dashboard)
# Go to: Notifications → Create Notification
# Trigger: Queue depth > 10,000
# Action: Send email
```

### Add Rate Limiting

```typescript
// In producer, rate limit external API calls
const rateLimiter = new Map<string, number>();

async function fetchWithRateLimit(url: string) {
  const lastCall = rateLimiter.get(url) || 0;
  const now = Date.now();
  const minInterval = 100; // 100ms between calls

  if (now - lastCall < minInterval) {
    await sleep(minInterval - (now - lastCall));
  }

  rateLimiter.set(url, Date.now());
  return fetch(url);
}
```

---

## Migration from Old System

### Step 1: Deploy Queue System (Parallel)

Deploy the new queue-based system alongside your existing system. They can coexist.

### Step 2: Test with Subset

Start with 1-2 tokens to verify it works:

```typescript
// Temporarily reduce tokens for testing
const TOKENS = [
  { symbol: 'BTCUSDT', coinId: 'bitcoin' },
  { symbol: 'ETHUSDT', coinId: 'ethereum' },
];
```

### Step 3: Compare Results

Query both old and new tables to verify data consistency:

```sql
-- Compare data points
SELECT symbol, COUNT(*) as count
FROM historical_prices
GROUP BY symbol
ORDER BY count DESC;
```

### Step 4: Switch Over

Once verified, update cron to use queue-based producer:

```bash
# Disable old cron
wrangler cron trigger historical-data-collection-cron --disable

# Enable new cron
wrangler cron trigger historical-data-queue-producer --enable
```

### Step 5: Monitor for 24 Hours

Watch logs and queue depth to ensure system is stable.

---

## Support

If you encounter issues:

1. Check logs: `wrangler tail <worker-name>`
2. Check queue stats: `wrangler queues consumer <queue-name>`
3. Check D1 data: `wrangler d1 execute <db> --command "SELECT..."`
4. Review [Cloudflare Queues docs](https://developers.cloudflare.com/queues/)

---

## Summary

**What You Gain:**
✅ 100x faster data ingestion
✅ No more timeouts or failures
✅ Automatic retries on D1 overload
✅ Scales to millions of data points
✅ Only $4-8/month for 13-25 tokens

**What It Costs:**
- Setup time: 30 minutes
- Monthly cost: $4-8 (queue operations)
- Monitoring: Built-in via logs

**Next Steps:**
1. Deploy the system (follow steps above)
2. Test with 2-3 tokens
3. Scale to all tokens
4. Monitor performance
5. Optimize as needed
