# Coinswarm Multi-Exchange Trading Strategy

> Last updated: December 2025

## Overview

This document defines the optimal exchange selection and routing strategy for Coinswarm's US-based trading operations (non-NY, non-TX resident).

---

## Exchange Selection

### Primary Exchanges (Ranked by Fee)

| Rank | Exchange | Maker | Taker | Role |
|------|----------|-------|-------|------|
| 1 | **Crypto.com** | 0.075% | 0.075% | Primary spot trading |
| 2 | **OKX US** | 0.08% | 0.10% | Secondary, arb entries, altcoins |
| 3 | **Kraken** | 0.16% | 0.26% | Large orders, deep liquidity |
| 4 | **Coinbase** | 0.40% | 0.60% | Transfer hub (Base L2), compliance |
| 5 | **Curve (DEX)** | 0.04% | 0.04% | Stablecoin swaps only |

### What's NOT Available (US Restrictions)

- **Margin trading**: Blocked on all exchanges (Kraken requires $10M+ assets)
- **Futures/Derivatives**: Not available for US retail
- **Binance Global, OKX Global, MEXC, Bitget**: Geo-blocked

---

## Trading Decision Matrix

### By Trade Size

| Size | Exchange | Reason |
|------|----------|--------|
| < $10K | Crypto.com | Lowest fees dominate |
| $10K - $50K | Crypto.com | Check spread vs Kraken |
| $50K - $100K | Kraken | Better liquidity |
| $100K+ | Kraken OTC | Negotiated rates, $100K min |

### By Asset Type

| Asset | Exchange | Reason |
|-------|----------|--------|
| BTC, ETH | Kraken or Crypto.com | Compare spreads |
| Top 20 alts | Crypto.com | Good liquidity + lowest fees |
| Mid-cap alts | OKX US | More listings |
| Stablecoins | Curve DEX | 0.04% fee |
| New listings | OKX US | Often lists first |

### By Strategy

| Strategy | Buy On | Sell On | Transfer Via |
|----------|--------|---------|--------------|
| Spot accumulation | Crypto.com (maker) | - | - |
| Swing trading | Crypto.com | Crypto.com | - |
| CEX-CEX arb | OKX US (0.10% taker) | Crypto.com (0.075% maker) | Solana USDC |
| DEX-CEX arb | DEX | Crypto.com (maker) | Native chain |
| Stablecoin rebalance | Curve | Curve | Polygon |

---

## Capital Allocation

```
Total Trading Capital: 100%

├── Crypto.com: 35%
│   └── Primary spot trading
│
├── OKX US: 25%
│   └── Arb entries, altcoins, fast API
│
├── Kraken: 20%
│   └── Large orders, backup liquidity
│
├── Coinbase: 10%
│   └── Transfer hub only (Base L2)
│
└── Hot Wallet (DEX): 10%
    └── Curve, 1inch opportunities
```

---

## Transfer Routing (Lowest Cost)

| From | To | Network | Cost | Time |
|------|-----|---------|------|------|
| Coinbase | Any | **Base** | <$0.03 | 2 min |
| OKX US | Any | **Solana** | <$0.01 | 10 sec |
| Kraken | Any | **Arbitrum** | <$0.10 | 2 min |
| Crypto.com | Any | **Polygon** | <$0.01 | 30 sec |

**Rule:** Never use ERC-20 mainnet. Always L2 or alt-L1.

---

## Quick Reference

```
STANDARD TRADE?
  └── Crypto.com (0.075%)

BIG ORDER ($50K+)?
  └── Kraken (check spread)

MOVING STABLES?
  └── Curve DEX (0.04%)

MOVING FUNDS BETWEEN CEX?
  └── Coinbase Base L2 (<$0.03)
  └── or Solana USDC (<$0.01)

ARB OPPORTUNITY?
  └── Buy: OKX US (0.10% taker)
  └── Sell: Crypto.com (0.075% maker)

NEED MARGIN?
  └── Not available in US
```

---

## Fee Comparison Summary

| Exchange | Maker | Taker | Round-Trip on $100K |
|----------|-------|-------|---------------------|
| Crypto.com | 0.075% | 0.075% | **$150** |
| OKX US | 0.08% | 0.10% | $180 |
| Kraken | 0.16% | 0.26% | $420 |
| Coinbase | 0.40% | 0.60% | $1,000 |
| Curve (stables) | 0.04% | 0.04% | $80 |

---

## Volume Tier Discounts

### Crypto.com (with CRO lockup for rebates)

| Volume/mo | Maker | Taker | CRO Lockup Maker |
|-----------|-------|-------|------------------|
| < $2.5M | 0.075% | 0.075% | - |
| $2.5M+ | 0.065% | 0.100% | **-0.01%** (rebate) |
| $10M+ | 0% | 0.050% | **-0.01%** |
| $25M+ | 0% | 0.040% | **-0.01%** |

### OKX US

| Volume/mo | Maker | Taker |
|-----------|-------|-------|
| < $100K | 0.08% | 0.10% |
| $100K+ | 0.07% | 0.09% |
| $1M+ | 0.06% | 0.08% |
| $5M+ | 0.05% | 0.07% |

### Kraken

| Volume/mo | Maker | Taker |
|-----------|-------|-------|
| < $50K | 0.25% | 0.40% |
| $50K+ | 0.16% | 0.26% |
| $100K+ | 0.14% | 0.24% |
| $1M+ | 0.10% | 0.18% |
| $10M+ | 0% | 0.08% |

---

## Key Constraints

1. **No margin/leverage** - US retail blocked everywhere
2. **Spot only** - All strategies must be spot-based
3. **No CRO staking required** - Base 0.075% fees without lockup
4. **State access** - OKX US available (not in NY/TX)

---

## State Restrictions

| Exchange | Blocked States |
|----------|----------------|
| Crypto.com | NY (limited) |
| OKX US | NY, TX, KY, NV, HI, WV |
| Kraken | NY, WA (limited) |
| Coinbase | None (all 50) |
| Gemini | None (all 50) |

---

## Insurance & Protection

| Exchange | USD Protection | Crypto Protection |
|----------|----------------|-------------------|
| Coinbase | FDIC $250K | Partial crime insurance |
| Gemini | FDIC $250K | Crime insurance |
| Kraken | None | None |
| Crypto.com | Varies | Crime insurance |
| OKX US | None | None |

---

## API Capabilities

| Exchange | Rate Limit | Sandbox | SDK |
|----------|------------|---------|-----|
| Coinbase | ~10-30/sec | Yes | Python, TS, Go, Java |
| Kraken | Tiered | Yes | Python, Go |
| OKX US | 500/sec | Yes | Python, TS |
| Crypto.com | Varies | Yes | Python |

---

## Implementation Notes

For Coinswarm V3 integration:
- Add exchange connectors for: Crypto.com, OKX US, Kraken, Coinbase
- Implement fee-aware order routing
- Build transfer optimizer using L2/Solana networks
- No margin/futures logic needed (not available)

---

## DEX Options (No KYC)

| DEX | Fee | Best For | US Legal |
|-----|-----|----------|----------|
| Curve | 0.04% | Stablecoins | Yes |
| Uniswap | 0.30% | ERC-20 swaps | Yes (SEC cleared Feb 2025) |
| 1inch | Variable | Best price routing | Yes |
| THORSwap | 0.50% | Cross-chain native | Check terms |

---

## Sources

- [Crypto.com Fees](https://crypto.com/exchange/document/fees-limits)
- [OKX US](https://www.okx.com/en-us)
- [Kraken Fees](https://www.kraken.com/features/fee-schedule)
- [Coinbase Advanced](https://www.coinbase.com/advanced-trade)
- [Curve Finance](https://curve.fi)
- [Kraken Margin ECP Requirements](https://support.kraken.com/articles/360061972272)
- [Crypto.com Margin Geo-Restrictions](https://help.crypto.com/en/articles/4475382-margin-trading-geo-restrictions)
