# Coinswarm Annotated Bibliography

> **Last Updated:** 2025-12-28
> **Status:** Living document - updated as new sources are processed
> **Location:** `docs/ANNOTATED_BIBLIOGRAPHY.md`
> **Total Papers:** 180+ (40 newly added 2025-12-28, 40 added 2025-12-27)

This document catalogs all research papers, books, methodologies, and external sources that have influenced Coinswarm's architecture and trading logic. Sources are organized by category with annotations explaining their relevance to our system.

---

## Table of Contents

1. [Core Methodology](#1-core-methodology)
2. [Bitcoin & Cryptocurrency Research](#2-bitcoin--cryptocurrency-research)
3. [Portfolio Theory & Risk Management](#3-portfolio-theory--risk-management)
4. [Market Microstructure & Execution](#4-market-microstructure--execution)
5. [Trading Strategies & Algorithms](#5-trading-strategies--algorithms)
6. [Machine Learning in Finance](#6-machine-learning-in-finance)
7. [Volatility & Time Series Modeling](#7-volatility--time-series-modeling)
8. [Sentiment Analysis & Behavioral Finance](#8-sentiment-analysis--behavioral-finance)
9. [DeFi & Blockchain Research](#9-defi--blockchain-research)
10. [Reinforcement Learning for Trading](#10-reinforcement-learning-for-trading)
11. [Foundation Models for Finance](#11-foundation-models-for-finance)
12. [Books & Comprehensive References](#12-books--comprehensive-references)
13. [External APIs & Data Sources](#13-external-apis--data-sources)
14. [Distillation Pipeline Details](#14-distillation-pipeline-details)
15. [NEW: Order Book & Limit Order Book Dynamics](#15-order-book--limit-order-book-dynamics)
16. [NEW: Market Manipulation & Pump-and-Dump Detection](#16-market-manipulation--pump-and-dump-detection)
17. [NEW: Multi-Agent Trading Systems](#17-multi-agent-trading-systems)
18. [NEW: Market Regime Detection](#18-market-regime-detection)
19. [NEW: Position Sizing & Kelly Criterion](#19-position-sizing--kelly-criterion)
20. [NEW: Cross-Asset Correlation & Contagion](#20-cross-asset-correlation--contagion)
21. [NEW: On-Chain Analytics & Whale Tracking](#21-on-chain-analytics--whale-tracking)
22. [NEW: Social Media Sentiment & NLP](#22-social-media-sentiment--nlp)
23. [NEW: Candlestick Pattern Recognition](#23-candlestick-pattern-recognition)
24. [NEW: Perpetual Futures & Funding Rates](#24-perpetual-futures--funding-rates)
25. [NEW: Execution Algorithms (VWAP/TWAP)](#25-execution-algorithms-vwaptwap)
26. [NEW: Transformer & LSTM Models](#26-transformer--lstm-models)
27. [NEW: Stop-Loss & Risk Management](#27-stop-loss--risk-management)
28. [NEW: Genetic & Evolutionary Algorithms](#28-genetic--evolutionary-algorithms)
29. [NEW: AMM & DEX Market Making](#29-amm--dex-market-making)
30. [NEW: Backtesting & Overfitting Prevention](#30-backtesting--overfitting-prevention)
31. [NEW: LLMs for Trading](#31-llms-for-trading)
32. [NEW 2: Deep RL Portfolio Optimization](#32-deep-rl-portfolio-optimization)
33. [NEW 2: Attention & Transformer Finance](#33-attention--transformer-finance)
34. [NEW 2: High-Frequency & Market Microstructure](#34-high-frequency--market-microstructure)
35. [NEW 2: DeFi Security & Flash Loans](#35-defi-security--flash-loans)
36. [NEW 2: Risk Parity & Dynamic Allocation](#36-risk-parity--dynamic-allocation)
37. [NEW 2: Multi-Agent LLM Trading](#37-multi-agent-llm-trading)
38. [NEW 2: Regime Detection & Classification](#38-regime-detection--classification)
39. [NEW 2: GARCH-Neural Hybrid Volatility](#39-garch-neural-hybrid-volatility)
40. [NEW 2: Option Hedging with Deep Learning](#40-option-hedging-with-deep-learning)
41. [NEW 2: Optimal Execution (VWAP/TWAP)](#41-optimal-execution-vwaptwap)
42. [NEW 2: Graph Neural Networks for Finance](#42-graph-neural-networks-for-finance)
43. [NEW 2: Explainable AI (XAI) in Trading](#43-explainable-ai-xai-in-trading)
44. [NEW 2: Stablecoin Depegging & Risk](#44-stablecoin-depegging--risk)
45. [NEW 2: Memory-Augmented Trading Networks](#45-memory-augmented-trading-networks)
46. [NEW 2: Genetic Algorithm Trading Strategies](#46-genetic-algorithm-trading-strategies)
47. [NEW 2: AMM Liquidity Optimization](#47-amm-liquidity-optimization)

---

## 1. Core Methodology

### First Principles Framework (FPF)

**Source:** Anatoly Levenchuk
**Repository:** https://github.com/m0n0x41d/quint-code
**Status:** Future implementation (high priority)

**Relevance to Coinswarm:**
The FPF methodology provides the theoretical foundation for our reasoning-based trading approach. Rather than traditional RL that learns "BUY worked," FPF enables learning "*why* BUY worked."

**Key Concepts Applied:**
- **Knowledge Layers (L0-L2):** Maps to confidence tiers in trading decisions
  - L0 (Unverified) → Signal detected, no confirmation
  - L1 (Logically verified) → Multiple indicators align
  - L2 (Empirically verified) → Pattern has historical edge
- **Evidence Types:** Adapted for trading (backtest, live_trade, paper_trade, sentiment)
- **Congruence Levels:** How well external evidence matches current trading context
- **Decay Functions:** Evidence reliability decays exponentially over time

**Implementation Location:** `.claude/future-concepts/fpf-trading-reasoning.md`

---

### Evidence-Driven Development (EDD)

**Source:** Internal methodology
**Status:** Active

**Relevance to Coinswarm:**
EDD extends Test-Driven Development with economic validation. Every commit must pass both functional tests AND soundness tests.

**Seven Categories of Soundness:**
1. Determinism Tests - Same inputs → same outputs
2. Statistical Sanity Tests - Sharpe 0.5-3.0 realistic, >3.0 suspicious
3. Safety Invariant Tests - Position limits, loss limits
4. Latency & Throughput Tests - P99 < 100ms
5. Economic Realism Tests - No lookahead bias, realistic slippage
6. Memory Stability Tests - Patterns converge, weights don't oscillate
7. Consensus Integrity Tests - Quorum requires matching votes

**Implementation Location:** `.claude/rules/testing/evidence-driven-development.md`

---

## 2. Bitcoin & Cryptocurrency Research

### arxiv:1812.09452 - "The Price of Bitcoin: GARCH Evidence from High-Frequency Data"

**Authors:** (See arXiv)
**Published:** 2018
**URL:** https://arxiv.org/abs/1812.09452
**Distillation:** `local-utilities/data-ingest/academic_pipeline/distillations/arxiv_1812.09452/`

**Abstract:**
First application of GARCH framework to hourly Bitcoin observations (2013-2018). Combines theoretical model of Bitcoin price formation with empirical GARCH analysis.

**Key Findings Applied to Coinswarm:**
- Transaction demand and speculative demand both drive Bitcoin prices
- Bitcoin velocity, stock, and interest rate reduce returns
- Bitcoin volume and user count increase returns
- GARCH coefficient > ARCH coefficient (past volatility predicts current volatility)

**Implementation Impact:**
- Influenced our decision to use hourly OHLCV as primary timeframe
- Supports inclusion of volume metrics in pattern conditions
- Validates GARCH-style volatility modeling in indicators

---

### arxiv:1405.4498 - "The Economics of Bitcoin Price Formation"

**Authors:** Pavel Ciaian, Miroslava Rajcaniova, d'Artis Kancs
**Published:** 2014-05-18
**URL:** https://arxiv.org/abs/1405.4498

**Abstract:**
Analyzes relationship between Bitcoin price and supply-demand fundamentals, global macro-financial indicators, and Bitcoin attractiveness for investors using daily data (2009-2014).

**Key Findings Applied to Coinswarm:**
- Bitcoin market fundamentals significantly impact price
- Investor attractiveness (sentiment) matters
- Macro-financial developments have less impact than previously thought

**Implementation Impact:**
- Supports our 40% Technical + 30% Sentiment + 30% Fundamental weighting
- Validates focus on on-chain metrics over macro indicators

---

### arxiv:1908.05419 - "Modelling Crypto Asset Price Dynamics: Optimal Crypto Portfolio Optimization"

**URL:** https://arxiv.org/abs/1908.05419
**Distillation:** Available

**Relevance:**
Portfolio optimization across crypto assets. Informs our multi-asset allocation strategies.

---

### arxiv:2305.06961 - "Copula-Based Trading of Cointegrated Cryptocurrency Pairs"

**URL:** https://arxiv.org/abs/2305.06961

**Relevance:**
Statistical arbitrage between cointegrated crypto pairs. Potential pattern source for pairs trading.

---

### arxiv:2511.05512 - "Estimating the Impact of the Bitcoin Halving on Its Price"

**URL:** https://arxiv.org/abs/2511.05512

**Relevance:**
Quantifies halving effects. Useful for long-term macro regime classification.

---

### arxiv:1812.00595 - "Building Trust Takes Time: Limits to Arbitrage for Blockchain"

**URL:** https://arxiv.org/abs/1812.00595
**Distillation:** Available

**Relevance:**
Explains why arbitrage opportunities persist in crypto. Informs execution timing.

---

## 3. Portfolio Theory & Risk Management

### arxiv:1505.05491 - "Portfolio Optimization"

**URL:** https://arxiv.org/abs/1505.05491
**Distillation:** Available
**Classification:** FACTOR_BASED, PARTIAL implementability

**Abstract:**
Application of Markowitz portfolio theory to multi-asset universe. Illustrates efficient frontier, minimum-variance portfolio, tangency portfolio, and optimal Markowitz portfolio.

**Key Concepts Applied:**
- Expected return calculation: μᵢ = (1/T)∑rᵢ,ₜ
- Covariance matrix estimation
- Risk-free rate integration
- Portfolio weight optimization

**Implementation Impact:**
- Foundation for future multi-asset allocation
- Provides framework for agent-level portfolio construction

---

### arxiv:0910.2367 - "Risk Concentration and Diversification: Second-Order Properties"

**URL:** https://arxiv.org/abs/0910.2367
**Distillation:** Available

**Relevance:**
Advanced risk diversification framework. Informs how we think about correlation between patterns.

---

### arxiv:1506.00166 - "Optimal Investment to Minimize the Probability of Drawdown"

**URL:** https://arxiv.org/abs/1506.00166
**Distillation:** Available

**Relevance:**
Directly relevant to our max drawdown constraints (<15% for Tier 1). Provides mathematical foundation for drawdown minimization.

---

### arxiv:1507.08713 - "Minimizing the Probability of Lifetime Drawdown under Constant Consumption"

**URL:** https://arxiv.org/abs/1507.08713
**Distillation:** Available

**Relevance:**
Extension of drawdown minimization with consumption. Relevant for capital management.

---

### arxiv:1003.4216 - "Minimizing the Probability of Lifetime Ruin under Stochastic Volatility"

**URL:** https://arxiv.org/abs/1003.4216
**Distillation:** Available

**Relevance:**
Risk management under volatile conditions. Directly applicable to crypto trading.

---

### arxiv:2007.08829 - "Adjusted Expected Shortfall"

**URL:** https://arxiv.org/abs/2007.08829
**Distillation:** Available

**Relevance:**
Advanced risk metric. Potential enhancement to fitness calculation beyond VaR.

---

## 4. Market Microstructure & Execution

### arxiv:1409.2618 - "Optimal Execution with Dynamic Order Flow Imbalance"

**URL:** https://arxiv.org/abs/1409.2618
**Distillation:** Available

**Relevance:**
Optimal execution algorithms considering order flow. Critical for minimizing slippage in real trading.

---

### arxiv:1802.06101 - "Market Impact in a Latent Order Book"

**URL:** https://arxiv.org/abs/1802.06101
**Distillation:** Available

**Relevance:**
Understanding market impact of trades. Informs position sizing and execution strategy.

---

### arxiv:1407.3390 - "Slow Decay of Impact in Equity Markets"

**URL:** https://arxiv.org/abs/1407.3390
**Distillation:** Available

**Relevance:**
Long-term market impact analysis. Explains why large trades affect price persistently.

---

### arxiv:1710.03870 - "A High Frequency Trade Execution Model for Supervised Learning"

**URL:** https://arxiv.org/abs/1710.03870
**Distillation:** Available

**Relevance:**
ML-based trade execution. Potential enhancement for execution layer.

---

### arxiv:2511.20606 - "Limit Order Book Dynamics in Matching Markets: Microstructure"

**URL:** https://arxiv.org/abs/2511.20606

**Relevance:**
Order book dynamics for execution optimization.

---

### arxiv:2512.04603 - "FX Market Making with Internal Liquidity"

**URL:** https://arxiv.org/abs/2512.04603

**Relevance:**
Market making strategies. Relevant for Layer 8 (Market Making) implementation.

---

### arxiv:1705.09827 - "Mini-Flash Crashes: Model Risk and Optimal Execution"

**URL:** https://arxiv.org/abs/1705.09827
**Distillation:** Available

**Relevance:**
Understanding flash crashes for risk management. Informs circuit breaker logic.

---

## 5. Trading Strategies & Algorithms

### arxiv:1912.04492 - "151 Trading Strategies" (Book)

**Authors:** Zura Kakushadze and Juan Andrés Serur
**URL:** https://arxiv.org/abs/1912.04492
**Distillation:** Multiple versions available (20B, 120B, custom, phi4)
**Classification:** BLACK_BOX_ML, NOT directly implementable (TOC only in PDF)

**Description:**
Comprehensive book containing 150+ trading strategies with 550+ mathematical formulas covering stocks, bonds, derivatives, ETFs, volatility products, structured assets, convertible bonds, distressed assets, and cryptocurrencies.

**Significance:**
Central reference for strategy inspiration. The diversity of approaches informed our pattern diversity requirements.

**Note:** The distillation only captured the table of contents; the full book provides detailed formulas and implementations.

---

### arxiv:1412.5558 - "Backtest of Trading Systems on Candle Charts"

**URL:** https://arxiv.org/abs/1412.5558
**Distillation:** Available

**Relevance:**
Methodology for backtesting candle-based strategies. Validates our OHLCV-centric approach.

---

### arxiv:2512.12924 - "Interpretable Hypothesis-Driven Trading: A Rigorous Walk-Forward Validation"

**URL:** https://arxiv.org/abs/2512.12924

**Relevance:**
Walk-forward validation methodology. Directly addresses our Phase 1 gap (70% train, 30% test split).

---

### arxiv:2506.11921 - "Dynamic Grid Trading Strategy: From Zero Expectation to Market Reality"

**URL:** https://arxiv.org/abs/2506.11921

**Relevance:**
Grid trading strategies. Potential pattern source for ranging markets.

---

### arxiv:1707.05552 - "Wax and Wane of Cross-Sectional Momentum and Contrarian"

**URL:** https://arxiv.org/abs/1707.05552
**Distillation:** Available

**Relevance:**
Momentum vs contrarian dynamics. Informs our `momentum_vs_reversion` agent trait (trait #7).

---

## 6. Machine Learning in Finance

### arxiv:2103.02016 - "Machine Learning in Finance"

**URL:** https://arxiv.org/abs/2103.02016
**Distillation:** Available

**Relevance:**
General ML framework for finance. Provides context for our approach.

---

### arxiv:1803.02421 - "Masked Conditional Neural Networks"

**URL:** https://arxiv.org/abs/1803.02421
**Distillation:** Available

**Relevance:**
Neural network architecture for sequential data. Potential model enhancement.

---

### arxiv:1806.06632 - "Exploring the Interconnectedness of Cryptocurrencies using Correlation Networks"

**URL:** https://arxiv.org/abs/1806.06632
**Distillation:** Available

**Relevance:**
Cryptocurrency correlation analysis. Informs our `correlation_awareness` agent trait (trait #16).

---

### arxiv:2505.16136 - "Interpretable Machine Learning for Macro Alpha: A News Sentiment Approach"

**URL:** https://arxiv.org/abs/2505.16136

**Relevance:**
Sentiment-based alpha generation with interpretability. Aligns with our 30% sentiment pillar.

---

### arxiv:2505.16287 - "Machine Learning Approach to Stock Price Crash Risk"

**URL:** https://arxiv.org/abs/2505.16287

**Relevance:**
Crash prediction. Potential enhancement for risk management.

---

### arxiv:1303.1152 - "An Equivalence between the Lasso and Support Vector Machines"

**URL:** https://arxiv.org/abs/1303.1152
**Distillation:** Available

**Relevance:**
Feature selection methodology. Relevant for pattern feature engineering.

---

## 7. Volatility & Time Series Modeling

### arxiv:1512.01676 - "Forecasting Crude Oil Market Volatility: Can the Regime Switching..."

**URL:** https://arxiv.org/abs/1512.01676
**Distillation:** Available

**Relevance:**
Regime-switching volatility models. Informs market regime detection (bull/bear/crab).

---

### arxiv:2512.12250 - "Stochastic Volatility Modelling with LSTM Networks: A Hybrid..."

**URL:** https://arxiv.org/abs/2512.12250

**Relevance:**
Hybrid stochastic volatility with LSTM. Modern approach to volatility forecasting.

---

### arxiv:2512.02352 - "Visibility-Graph Asymmetry as a Structural Indicator of Volatility"

**URL:** https://arxiv.org/abs/2512.02352

**Relevance:**
Novel volatility indicator. Potential addition to technical indicators suite.

---

### arxiv:2504.09380 - "Unified GARCH-Recurrent Neural Network in Financial Volatility Forecasting"

**URL:** https://arxiv.org/abs/2504.09380

**Relevance:**
Combines classical GARCH with RNN. Hybrid approach for volatility prediction.

---

### arxiv:1209.0697 - "Variance Swaps on Defaultable Assets and Market Implied Time-Changes"

**URL:** https://arxiv.org/abs/1209.0697
**Distillation:** Available

**Relevance:**
Advanced variance modeling. Relevant for options and volatility strategies.

---

## 8. Sentiment Analysis & Behavioral Finance

### arxiv:2305.16632 - "Causality between Investor Sentiment and the Shares Return"

**URL:** https://arxiv.org/abs/2305.16632

**Relevance:**
Causal analysis of sentiment impact. Validates our sentiment weighting.

---

### arxiv:1912.02387 - "SemEval-2015 Task 10: Sentiment Analysis in Twitter"

**URL:** https://arxiv.org/abs/1912.02387
**Distillation:** Available

**Relevance:**
Social media sentiment methodology. Foundation for news/social sentiment integration.

---

### arxiv:1908.11492 - "Culture and the Disposition Effect"

**URL:** https://arxiv.org/abs/1908.11492
**Distillation:** Available

**Relevance:**
Behavioral finance - disposition effect. Informs agent psychology traits.

---

### arxiv:2010.12415 - "Exploring Investor Behavior in Bitcoin: A Study of the Disposition Effect"

**URL:** https://arxiv.org/abs/2010.12415
**Distillation:** Available

**Relevance:**
Bitcoin-specific behavioral analysis. Validates behavioral assumptions.

---

## 9. DeFi & Blockchain Research

### arxiv:2304.11010 - "Invariance Properties of Maximal Extractable Value"

**URL:** https://arxiv.org/abs/2304.11010

**Relevance:**
MEV analysis. Critical for on-chain execution understanding.

---

### arxiv:2503.21967 - "Pool Value Replication, CPM and Impermanent Loss Hedging"

**URL:** https://arxiv.org/abs/2503.21967

**Relevance:**
Impermanent loss mitigation for AMM LP positions.

---

### arxiv:2512.11976 - "Institutionalizing Risk Curation in Decentralized Credit"

**URL:** https://arxiv.org/abs/2512.11976

**Relevance:**
DeFi risk frameworks. Relevant for on-chain lending strategies.

---

### arxiv:2205.14699 - "Managing Risk in DeFi Portfolios"

**URL:** https://arxiv.org/abs/2205.14699
**Distillation:** Available

**Relevance:**
DeFi portfolio risk management. Directly applicable to crypto allocation.

---

## 10. Reinforcement Learning for Trading

### arxiv:2011.09607 - "FinRL: A Deep Reinforcement Learning Library for Automated Stock Trading"

**URL:** https://arxiv.org/abs/2011.09607
**Distillation:** Available

**Description:**
FinRL provides a fully-extensible, educational and reproducible framework coupling a realistic market simulator, DRL agents (PPO, DDPG, TD3, etc.), and comprehensive backtesting tools.

**Relevance:**
Reference implementation for DRL-based trading. Informs our agent architecture.

---

### arxiv:2205.15056 - "Stock Trading Optimization through Model-based Reinforcement Learning"

**URL:** https://arxiv.org/abs/2205.15056

**Relevance:**
Model-based RL for trading. Alternative to model-free approaches.

---

### Wei et al. (2024) - "Multi-Agent RL for High-Frequency Trading"

**Citation:** Referenced in META_LEARNING.md
**Reported Sharpe:** 2.87

**Relevance:**
State-of-the-art multi-agent RL results. Benchmark for our system.

---

### arxiv:1908.01478 - "Reusability and Transferability of Macro Actions for Reinforcement Learning"

**URL:** https://arxiv.org/abs/1908.01478
**Distillation:** Available

**Relevance:**
Transfer learning in RL. Relevant for pattern/trait transfer between agents.

---

## 11. Foundation Models for Finance

### TimesFM (Microsoft)

**Description:** Time series foundation model
**Status:** Actively searched in Meta-Learning Layer

**Relevance:**
State-of-the-art time series forecasting. Potential replacement for current indicators.

---

### Chronos (Amazon)

**Description:** Time series prediction models
**Status:** Actively searched in Meta-Learning Layer

**Relevance:**
Foundation model for time series. Benchmark for forecasting quality.

---

### FinGPT

**Description:** LLM trained on financial data
**URL:** Open source
**Status:** Actively searched in Meta-Learning Layer

**Relevance:**
Finance-specific language model. Potential for pattern analysis and reasoning.

---

### FinBERT

**Description:** BERT fine-tuned for financial text
**Status:** Actively searched in Meta-Learning Layer

**Relevance:**
Financial sentiment analysis. Already conceptually integrated in sentiment pillar.

---

### BloombergGPT

**Description:** Bloomberg's financial language model
**Status:** Tracked (not publicly available)

**Relevance:**
Represents state-of-the-art in financial NLP. Benchmark for news analysis.

---

### TFT - Temporal Fusion Transformer (Google)

**Description:** Interpretable time series model
**Status:** Actively searched in Meta-Learning Layer

**Relevance:**
Combines recurrence and attention. Potential model for multi-horizon forecasting.

---

## 12. Books & Comprehensive References

### "151 Trading Strategies" by Kakushadze & Serur

**arXiv:** 1912.04492
**Coverage:** 150+ strategies, 550+ formulas

**Categories Covered:**
- Stocks and equity indices
- Bonds and fixed income
- Derivatives (options, futures)
- ETFs
- Volatility products
- Structured assets
- Convertible bonds
- Distressed assets
- Cryptocurrencies

**Significance:** The diversity of approach categories influenced our pattern entry points (CHAOS, ACADEMIC, TECHNICAL, AI, HYBRID).

---

## 13. External APIs & Data Sources

### Exchange APIs

| API | Purpose | Documentation |
|-----|---------|---------------|
| **Jupiter V6** | Solana DEX aggregation | https://quote-api.jup.ag/v6 |
| **Coinbase Advanced Trade** | CEX trading | https://api.coinbase.com/api/v3/brokerage |
| **Binance US** | CEX data/trading | https://api.binance.us |
| **LI.FI** | Cross-chain bridges | https://li.quest/v1 |
| **1inch** | DEX aggregation | https://api.1inch.dev |

### Data APIs

| API | Purpose | Documentation |
|-----|---------|---------------|
| **CryptoCompare** | Market data | cryptocompare.com |
| **Alternative.me** | Fear & Greed Index | https://api.alternative.me/fng/ |
| **Santiment** | On-chain analytics | https://api.santiment.net/ |
| **CoinGlass** | Derivatives data | https://docs.coinglass.com |
| **NewsAPI** | News sentiment | newsapi.org |

### Academic Research APIs

| API | Purpose | Query Format |
|-----|---------|--------------|
| **arXiv** | Research papers | http://export.arxiv.org/api/query?search_query=all:{query} |
| **SSRN** | Finance papers | Search URLs constructed |
| **NBER** | Economics papers | https://www.nber.org/api/v1/working_page_listing |
| **HuggingFace** | Model search | https://huggingface.co/api/models?search={query} |

### Blockchain Infrastructure

| Service | Purpose | Documentation |
|---------|---------|---------------|
| **Helius** | Solana RPC/indexing | https://docs.helius.dev |
| **Solana Cookbook** | Development reference | https://solanacookbook.com |

---

## 14. Distillation Pipeline Details

### Overview

The academic pipeline automatically processes research papers through LLM distillation to extract actionable trading logic.

**Location:** `local-utilities/data-ingest/academic_pipeline/`

### Models Used for Distillation

| Model | Size | Performance Notes |
|-------|------|-------------------|
| GPT-OSS 20B | 20B params | Default distillation model |
| GPT-OSS 120B | 120B params | Higher quality, slower |
| Phi-4 14B | 14B params | Fast, good for initial pass |
| DeepSeek-R1 14B | 14B params | Alternative reasoning |
| Qwen QwQ 32B | 32B params | Chinese model, good math |

### Distillation Output Format

```markdown
# Distillation: arxiv_{ID}_{TITLE}
## Model: {model_name}
## Time: {seconds}s
## Generated: {timestamp}

---

**Classification**
- **Paper type:** BLACK_BOX_ML | FACTOR_BASED | HYBRID
- **IMPLEMENTABLE:** YES | PARTIAL | NO
- **Reason:** {explanation}

## Paper Summary
{summary}

## Core Trading Logic
{if disclosed}

## Features / Inputs Table
| Feature Name | Formula/Definition | Lookback | Transform | Available Proxy |
|--------------|-------------------|----------|-----------|-----------------|

## Key Equations
{exact equations from paper}

## Signal Generation Rules
- **Entry:** {conditions}
- **Exit:** {conditions}

## Position Sizing
{if disclosed}

## Empirical Results
- Return: {if disclosed}
- Sharpe: {if disclosed}
- Period: {if disclosed}
- Universe: {assets tested}

## Implementation Verdict
CAN_IMPLEMENT: YES | PARTIAL | NO
BLOCKERS: {list}
```

### Processed Paper Statistics

As of 2025-12-27:
- **Total Papers Processed:** 100+
- **Fully Implementable:** ~15%
- **Partially Implementable:** ~40%
- **Not Directly Implementable:** ~45%

### Paper Queue

Location: `local-utilities/data-ingest/academic_pipeline/reports/queued_papers/`

Contains 50+ papers awaiting distillation, each with:
- PDF file
- JSON metadata (title, authors, abstract, URL, fetch date)
- TXT extracted text

---

## Appendix: arXiv IDs Quick Reference

### By Category

**Bitcoin/Crypto:**
- 1405.4498, 1812.00595, 1812.09452, 1908.05419, 2010.12415, 2304.11010, 2305.06961, 2511.05512

**Portfolio/Risk:**
- 0910.2367, 1003.4216, 1303.1152, 1505.05491, 1506.00166, 1507.08713, 2007.08829, 2205.14699

**Execution:**
- 1407.3390, 1409.2618, 1705.09827, 1710.03870, 1802.06101

**ML/AI:**
- 1803.02421, 1806.06632, 2011.09607, 2103.02016, 2505.16136, 2505.16287

**Volatility:**
- 1209.0697, 1512.01676, 2504.09380, 2512.02352, 2512.12250

**Strategy:**
- 1412.5558, 1707.05552, 1912.04492, 2506.11921, 2512.12924

---

## Contributing to This Bibliography

When adding new sources:

1. **Papers:** Add full arXiv ID, title, URL, and relevance annotation
2. **Books:** Include authors, publication year, and key chapters used
3. **APIs:** Document endpoint, authentication requirements, rate limits
4. **Methodologies:** Link to implementation location in codebase

**Update procedure:**
1. Add entry to appropriate section
2. Update statistics in Section 14 if paper was distilled
3. Update "Last Updated" date at top

---

## 15. Order Book & Limit Order Book Dynamics

### arxiv:2506.05764 - "Exploring Microstructural Dynamics in Cryptocurrency Limit Order Books"

**Published:** June 2025
**URL:** https://arxiv.org/abs/2506.05764

**Abstract:**
Examines whether adding extra hidden layers genuinely enhances short-term price forecasting, or if gains are primarily from data preprocessing. Benchmarks logistic regression, XGBoost, DeepLOB, Conv1D+LSTM on BTC/USDT LOB snapshots.

**Key Finding:** With proper data preprocessing and hyperparameter tuning, simpler models can match or exceed complex networks, offering faster inference and greater interpretability.

**Relevance:** Validates our approach of starting simple before adding complexity. Better inputs > more layers.

---

### arxiv:2403.09267 - "Deep Limit Order Book Forecasting"

**Published:** March 2024
**URL:** https://arxiv.org/abs/2403.09267

**Abstract:**
Exploits deep learning to explore predictability of high-frequency LOB mid-price changes. Links stocks' predictability rate to microstructural properties.

**Relevance:** Bridges gap between market microstructure analysis and LOB forecasting.

---

### arxiv:2312.16190 - "Hawkes-based Cryptocurrency Forecasting via Limit Order Book Data"

**Published:** December 2023
**URL:** https://arxiv.org/abs/2312.16190

**Abstract:**
Novel prediction algorithm using LOB data rooted in Hawkes point processes. Captures LOB self-excitation phenomena.

**Relevance:** When new orders placed, market hype increases → probability of more orders increases. Self-reinforcing dynamics.

---

### arxiv:2010.01241 - "Deep Learning for Digital Asset Limit Order Books"

**URL:** https://arxiv.org/abs/2010.01241

**Key Finding:** Temporal CNNs achieve 71% walk-forward accuracy predicting bitcoin spot price from LOB data on 2-second horizon (Coinbase).

---

## 16. Market Manipulation & Pump-and-Dump Detection

### arxiv:2412.18848 - "Machine Learning-Based Detection of Pump-and-Dump Schemes in Real-Time"

**Published:** December 2024
**URL:** https://arxiv.org/abs/2412.18848

**Dataset:** 2,079 P&D events (Dec 2017 - Sep 2024), 91,295+ labeled Telegram messages.

**Key Finding:** Most events on CEXes (Hotbit, LATOKEN, XT, Poloniex). Shifted from defunct exchanges to active ones.

**Relevance:** Critical for avoiding manipulation traps. Could inform pattern rejection criteria.

---

### arxiv:2504.15790 - "Microstructure and Manipulation: Quantifying Pump-and-Dump Dynamics"

**Published:** April 2025
**URL:** https://arxiv.org/abs/2504.15790

**Key Findings:**
- 70% of pre-event volume transacts within 1 hour of pump announcement
- Median insider returns >100%, upper quartile >2000%
- 1,021 tokens with flagged events (6-month sample)

**Relevance:** Helps identify and avoid manipulation patterns. Informs our anomaly detection.

---

### arxiv:2510.00836 - "Improving Pump-and-Dump Detection through Ensemble Models and SMOTE"

**Published:** October 2025
**URL:** https://arxiv.org/abs/2510.00836

**Results:** XGBoost and LightGBM achieved 94.87% and 93.59% recall with strong F1-scores. Fast enough for near real-time surveillance.

**Relevance:** Potential addition to our pattern validation layer.

---

### arxiv:2005.06610 - "Pump and Dumps in the Bitcoin Era: Real Time Detection"

**URL:** https://arxiv.org/abs/2005.06610

**Relevance:** Foundational paper on crypto manipulation detection.

---

## 17. Multi-Agent Trading Systems

### arxiv:2402.00515 - "MASA: Multi-Agent Self-Adaptive Framework for Dynamic Portfolio Risk Management"

**Published:** February 2024 (Updated September 2024)
**URL:** https://arxiv.org/abs/2402.00515

**Description:**
Two cooperating and reactive agents dynamically balance portfolio returns vs risks. Includes proactive market observer agent for estimated market trends.

**Tested On:** CSI 300, Dow Jones Industrial Average, S&P 500 (10 years).

**Relevance:** Direct inspiration for our Layer 7 committee voting system. Multi-agent cooperation pattern.

---

### arxiv:2501.06832 - "Hierarchical Deep Reinforcement Learning for Dynamic Portfolio Optimization"

**Published:** January 2025
**URL:** https://arxiv.org/abs/2501.06832

**Problem Addressed:** Sparsity in positive rewards and curse of dimensionality prevent DRL agents from comprehensively learning asset price patterns.

**Solution:** Hierarchical DRL approach.

**Relevance:** Informs our agent tier/hierarchy design (Planners → Committee → Agents).

---

### arxiv:2303.11959 - "Optimizing Trading Strategies using Multi-Agent Reinforcement Learning"

**URL:** https://arxiv.org/abs/2303.11959

**Innovation:** Fuses CPPI and TIPP financial strategies with MADDPG framework.

**Relevance:** Combining classical finance with modern RL - matches our hybrid approach.

---

### arxiv:2405.19982 - "Multi-Agent Asynchronous A3C for Forex Trading"

**Published:** May 2024
**URL:** https://arxiv.org/abs/2405.19982

**Description:** Parallel learning across multiple asynchronous workers, each specialized in different currency pairs.

**Relevance:** Model for parallel agent training in our architecture.

---

## 18. Market Regime Detection

### arxiv:2502.04027 - "High-Frequency Market Manipulation Detection with Markov-modulated Hawkes Process"

**Published:** February 2025
**URL:** https://arxiv.org/abs/2502.04027

**Innovation:** Self-exciting point process with hidden Markov switching mechanism. Detects anomalous bursts of trades on illiquid cryptocurrencies.

**Relevance:** Dual purpose - regime detection AND manipulation detection.

---

### arxiv:2301.09722 - "Expectile Hidden Markov Regression Models for Cryptocurrency Returns"

**Published:** January 2024
**URL:** https://arxiv.org/abs/2301.09722

**Focus:** Extreme returns in risk management framework. Describes temporal evolution of tail risk.

**Relevance:** Informs our drawdown and tail risk calculations.

---

### Giudici & Hashish (2020) - "A Hidden Markov Model to Detect Regime Changes in Cryptoasset Markets"

**Publication:** Quality and Reliability Engineering International

**Description:** Explains Bitcoin price evolution through unobserved states (bull/stable/bear). Includes likelihood ratio test for comparing models.

**Relevance:** Foundation for our market regime detection (Layer 7).

---

## 19. Position Sizing & Kelly Criterion

### arxiv:2402.15588 - "Sizing the Bets in a Focused Portfolio"

**Published:** February 2024
**URL:** https://arxiv.org/html/2402.15588v1

**Description:** Generalized Kelly Criterion with constraints: no shorting, limited leverage, maximum permanent loss risk, maximum individual allocation.

**Based On:** Buffett/Munger focused investing strategy.

**Relevance:** Direct implementation candidate for our `kelly-criterion.ts`.

---

### arxiv:2503.17927 - "Optimal Betting: Beyond the Long-Term Growth"

**Published:** March 2025
**URL:** https://arxiv.org/html/2503.17927

**Key Contribution:** Shows every fractional Kelly strategy can be realized using CLT-based risk measure. Introduces asymptotic variance as risk penalty.

**New Metrics:** Asymptotic Sharpe Ratio, ridge coefficient.

**Relevance:** Enhances Kelly with risk-adjusted variants.

---

### arxiv:2508.16598 - "Sizing the Risk: Kelly, VIX, and Hybrid Approaches"

**Published:** 2025
**URL:** https://arxiv.org/pdf/2508.16598

**Key Insight:** Kelly requires precise variance estimates. Volatility regime-based sizing using VIX works better when implied volatility elevated.

**Relevance:** Hybrid approach combining Kelly with volatility awareness.

---

### arxiv:2508.18868 - "Tackling Estimation Risk in Kelly Investing Using Options"

**Published:** November 2025
**URL:** https://arxiv.org/html/2508.18868v2

**Problem:** Kelly highly sensitive to estimation errors.

**Solution:** Adding European options provides Kelly strategies robust to estimation risk.

**Relevance:** Addresses our concern about parameter estimation in Kelly.

---

## 20. Cross-Asset Correlation & Contagion

### arxiv:2507.08915 - "Quantifying Crypto Portfolio Risk: Simulation-Based Framework"

**Published:** July 2025
**URL:** https://arxiv.org/html/2507.08915v1

**Components:**
1. Volatility stress testing
2. Stablecoin hedging
3. Contagion modeling (rolling correlations)
4. Monte Carlo simulation

**Data:** 2020-2024 USDT, ETH, BTC.

**Relevance:** Comprehensive risk framework for our portfolio layer.

---

### arxiv:2412.19983 - "Dynamic Spillover Effect Investigation on Cryptocurrency Market"

**Published:** December 2024
**URL:** https://arxiv.org/html/2412.19983

**Key Finding:** Risk spillovers increased by order of magnitude during pandemic vs 2019.

**Metric:** Conditional Expected Loss (CoES) for tail risk.

**Relevance:** Informs our correlation_awareness trait (#16).

---

### arxiv:2509.15232 - "Community-level Contagion among Diverse Financial Assets"

**Published:** September 2025
**URL:** https://arxiv.org/html/2509.15232v1

**Key Findings:**
- Very little spillover between crypto and traditional assets
- NFTs show no contagion with other types
- Information Technology assets are major contagion transmitters

**Relevance:** Crypto is somewhat isolated - good for diversification narrative.

---

## 21. On-Chain Analytics & Whale Tracking

### arxiv:2503.09165 - "Blockchain Data Analytics: Review and Challenges"

**Published:** March 2025
**URL:** https://arxiv.org/html/2503.09165v1

**Scale:** Ethereum full archive node = 21,358 GB. Solana ledger = 150+ TB.

**Relevance:** Understanding data scale challenges for on-chain analysis.

---

### arxiv:2403.17081 - "Machine Learning on Blockchain Data: A Systematic Mapping Study"

**Published:** May 2024
**URL:** https://arxiv.org/html/2403.17081v1

**Use Case Distribution:**
- Anomaly Detection: 49.7%
- Price Prediction: 18.9%
- Address Classification: 17.6%

**Relevance:** Validates focus areas for on-chain ML.

---

### Finance Research Letters (2025) - "Bitcoin Whale Contagion"

**Key Finding:** Whale signals (wallet→exchange transfers) show significant contagion on top 15 cryptocurrencies mainly after 6 and 24 hours.

**Relevance:** Timing window for whale-based signals.

---

## 22. Social Media Sentiment & NLP

### arxiv:2508.15825 - "Enhancing Cryptocurrency Sentiment Analysis with Multimodal Features"

**Published:** August 2025
**URL:** https://arxiv.org/html/2508.15825v1

**Data:** 519,208 tweets (Nov 2021 - Mar 2024).
**Model:** Meta-Llama-3-8B for sentiment annotation.

**Key Finding:** Twitter sentiment shows initial negative coherence with Bitcoin returns (counter-cyclical).

**Relevance:** Contrarian sentiment signals may work better.

---

### arxiv:2403.06036 - "Deciphering Crypto Twitter"

**Published:** March 2024 (ACM Web Science)
**URL:** https://arxiv.org/html/2403.06036v1

**Innovation:** Detects crypto events from social signals. Discovered FTX incident indicators.

**Relevance:** Social media as early warning system.

---

### arxiv:2501.09777 - "Sentiment Analysis in Twitter for Cryptocurrencies Using Machine Learning"

**Published:** January 2025
**URL:** https://arxiv.org/html/2501.09777v1

**Methods:** BOW, FastText, KNN, SVM, Adaboost, LSTM, BERT on Persian tweets.

**Relevance:** Multi-language sentiment may differ.

---

### Electronic Markets (July 2025) - "Wisdom of the Crowd Signals"

**Key Insight:** Tweet volume (not sentiment polarity) more reliable predictor of price direction.

**Relevance:** Volume of discussion > sentiment direction.

---

## 23. Candlestick Pattern Recognition

### PeerJ Computer Science (2025) - "CNN for Japanese Candlestick Patterns"

**Results:** 99.3% prediction accuracy (vs 56-91% baseline). 19M parameters, validated on 15-min data (Oct-Nov 2024).

**Relevance:** State-of-the-art for pattern recognition.

---

### arxiv:1901.05237 - "Encoding Candlesticks as Images for Pattern Classification"

**URL:** https://arxiv.org/abs/1901.05237

**Method:** GAF-CNN (Gramian Angular Field + CNN).
**Result:** 90.7% accuracy on 8 candlestick patterns.

**Relevance:** Image encoding approach for candlestick data.

---

### arxiv:2201.08669 - "Dynamic Deep Convolutional Candlestick Learner"

**URL:** https://arxiv.org/abs/2201.08669

**Innovation:** YOLO-based detection for candlestick patterns.

**Relevance:** Object detection for financial patterns.

---

## 24. Perpetual Futures & Funding Rates

### arxiv:2506.08573 - "Designing Funding Rates for Perpetual Futures in Cryptocurrency Markets"

**Published:** June 2025
**URL:** https://arxiv.org/abs/2506.08573
**Authors:** Jaehyun Kim & Hyungbin Park

**Innovation:** Path-dependent funding rates keep perpetual price aligned with target. Develops replicating portfolios for hedging.

**Relevance:** Critical for funding rate sensitivity trait (#15).

---

### arxiv:2212.06888 - "Fundamentals of Perpetual Futures"

**Updated:** August 2024
**URL:** https://arxiv.org/abs/2212.06888

**Key Findings:**
- Crypto perpetual deviations from no-arbitrage prices > traditional markets
- Deviations diminish over time as markets mature
- Simple trading strategy generates large Sharpe ratios even with highest Binance fees

**Relevance:** Perpetual futures arbitrage opportunities are real and tradeable.

---

### arxiv:2510.14435 - "Cryptocurrency as an Investable Asset Class"

**Published:** October 2025
**URL:** https://arxiv.org/html/2510.14435v1

**Statistics:**
- Perpetuals = 98%+ of Bitcoin futures volume
- Carry strategy annualized Sharpe: 6.45 (2020-2025), falling to 4.06 in 2024
- Funding rate mean return ~8% with 0.8% volatility

**Relevance:** Funding rate carry is a viable strategy but declining.

---

## 25. Execution Algorithms (VWAP/TWAP)

### arxiv:2502.13722 - "Deep Learning for VWAP Execution in Crypto Markets"

**Published:** February 2025
**URL:** https://arxiv.org/abs/2502.13722

**Innovation:** Bypasses intermediate volume curve prediction, directly optimizes VWAP objective.

**Relevance:** End-to-end learning for execution - matches our pattern discovery philosophy.

---

### arxiv:2502.18177 - "Recurrent Neural Networks for Dynamic VWAP Execution"

**Published:** February 2025
**URL:** https://arxiv.org/html/2502.18177v1

**Data:** BTC, ETH, BNB, ADA, XRP hourly data from Binance perpetuals (inception to July 2024).

**Relevance:** Direct crypto execution research.

---

### arxiv:2212.14670 - "Hierarchical Deep Reinforcement Learning for VWAP (M3T)"

**URL:** https://arxiv.org/pdf/2212.14670

**Result:** Average cost saving of 1.16 basis points vs optimal baseline.

**Architecture:** Macro-Meta-Micro Trader captures patterns across temporal scales.

**Relevance:** Multi-scale execution matches our multi-timeframe approach.

---

## 26. Transformer & LSTM Models

### arxiv:2412.14529 - "Temporal Fusion Transformers for Cryptocurrency Price Forecasting"

**Published:** December 2024
**URL:** https://arxiv.org/html/2412.14529v1

**Architecture:** 4 LSTM layers + 4 attention heads.

**Relevance:** TFT competitive with hybrid models for crypto.

---

### arxiv:2504.16361 - "Comparing Transformer Structures for Stock Prediction"

**Published:** April 2025
**URL:** https://arxiv.org/html/2504.16361v1

**Result:** Decoder-only structure outperforms all other variants.

**Relevance:** Architecture guidance for future model enhancements.

---

### arxiv:2506.22055 - "Crypto Price Prediction Using LSTM+XGBoost"

**Published:** June 2025
**URL:** https://arxiv.org/html/2506.22055v1

**Finding:** Hybrid LSTM+XGBoost consistently outperforms individual models.

**Relevance:** Validates ensemble approaches.

---

## 27. Stop-Loss & Risk Management

### arxiv:1701.03960 - "Optimal Trading with a Trailing Stop"

**URL:** https://arxiv.org/abs/1701.03960

**Definition:** Trailing stop sells when price experiences pre-specified percentage drawdown.

**Relevance:** Mathematical foundation for our stop-loss logic.

---

### SSRN (2021) - "Risk Reduction Using Trailing Stop-Loss Rules"

**Authors:** Dai, Marshall, Nguyen, Visaltanachoti

**Key Finding:**
- Fixed-stop: average Sharpe 0.92
- Trailing-stop: average Sharpe 1.28

**Relevance:** Trailing > fixed for risk-adjusted returns.

---

### Xiang & Deng (2024) - "Optimal Stop-Loss Rules in Markets with Long-Range Dependence"

**Publication:** Quantitative Finance

**Finding:** Stop losses improve risk-adjusted returns in trending markets, reduce returns in mean-reverting regimes.

**Relevance:** Stop-loss effectiveness depends on regime - ties to our regime detection.

---

## 28. Genetic & Evolutionary Algorithms

### arxiv:2510.07943 - "CGA-Agent: Agent-Based Genetic Algorithm for Crypto Trading Strategy Optimization"

**Published:** October 2025
**URL:** https://arxiv.org/abs/2510.07943

**Innovation:** Hybrid GA + intelligent multi-agent coordination for adaptive parameter optimization.

**Data:** BTC, ETH, BNB 5-minute data (Dec 2024 - Sep 2025).

**Relevance:** Direct competitor/inspiration for our evolution system.

---

### arxiv:2504.05418 - "Evolving Financial Trading Strategies with Vectorial Genetic Programming"

**Published:** April 2025
**URL:** https://arxiv.org/abs/2504.05418

**Finding:** Strongly-typed VGP always among best performers, standard GP among worst.

**Relevance:** Type constraints improve GP for trading.

---

### arxiv:2504.21095 - "EvoPort: Evolutionary Framework for Portfolio Optimization"

**Published:** April 2025
**URL:** https://arxiv.org/html/2504.21095v1

**Data:** S&P 500 (2016-2025), 1,265 features including options data and news sentiment.

**Relevance:** Large-scale evolutionary portfolio optimization.

---

### arxiv:2401.02710 - "Synergistic Formulaic Alpha Generation using Reinforcement Learning"

**Published:** January 2024
**URL:** https://arxiv.org/html/2401.02710v1

**Innovation:** Enhanced initialization with pregenerated seed formulaic alpha set.

**Relevance:** Better initialization for alpha discovery.

---

## 29. AMM & DEX Market Making

### arxiv:2508.08152 - "Optimal Fees for Liquidity Provision in Automated Market Makers"

**Published:** 2025
**URL:** https://arxiv.org/html/2508.08152v1

**Key Trade-off:** Fees must be low enough for volume, high enough for revenue and arbitrage protection.

**Finding:** Threshold-type dynamic fee schedule is robust and improves LP outcomes.

**Relevance:** Informs our Layer 8 market making strategy.

---

### arxiv:2501.07828 - "Automated Market Makers: Toward More Profitable Liquidity Provisioning"

**Published:** January 2025
**URL:** https://arxiv.org/html/2501.07828v1

**Finding:** Narrow position ranges increase returns due to capital concentration, but increase volatility risk.

**Relevance:** Range selection for concentrated liquidity.

---

### arxiv:2506.02869 - "Optimal Dynamic Fees in Automated Market Makers"

**URL:** https://arxiv.org/html/2506.02869

**Finding:** Impermanent loss can be fully hedged using European put/call options (Sepp et al. 2024).

**Relevance:** IL hedging strategies.

---

## 30. Backtesting & Overfitting Prevention

### arxiv:2512.12924 - "Interpretable Hypothesis-Driven Trading: Walk-Forward Validation Framework"

**Published:** December 2025
**URL:** https://arxiv.org/abs/2512.12924

**Features:**
- Strict information set discipline
- 34 independent rolling window test periods
- Natural language hypothesis explanations
- Realistic transaction costs

**Relevance:** Gold standard for our walk-forward validation implementation.

---

### Bailey & Borwein - "The Probability of Backtest Overfitting"

**URL:** https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf

**Key Contribution:** Deflated Sharpe Ratio, Combinatorially Symmetric Cross-Validation (CSCV).

**Statistic:** 90%+ of academic strategies fail with real capital.

**Relevance:** Essential reading for avoiding overfitting.

---

### arxiv:1905.05023 - "Avoiding Backtesting Overfitting by Covariance-Penalties"

**URL:** https://arxiv.org/abs/1905.05023

**Relevance:** Mathematical framework for penalizing overfit strategies.

---

## 31. LLMs for Trading

### arxiv:2504.10789 - "Can Large Language Models Trade?"

**Published:** April 2025
**URL:** https://arxiv.org/abs/2504.10789

**Setup:** LLMs as heterogeneous competing trading agents in simulated market.

**Key Findings:**
1. LLMs demonstrate consistent strategy adherence
2. Markets exhibit real features: price discovery, bubbles, underreaction
3. Strategic liquidity provision emerges

**Relevance:** Validates LLM-based trading agents.

---

### arxiv:2406.11903 - "A Survey of Large Language Models for Financial Applications"

**Published:** June 2024
**URL:** https://arxiv.org/html/2406.11903v1

**Relevance:** Comprehensive survey of LLM finance applications.

---

### arxiv:2510.05533 - "The New Quant: LLMs in Financial Prediction and Trading"

**URL:** https://arxiv.org/html/2510.05533v1

**Definition:** New paradigm where LLMs "read and reason over disclosures, generate auditable hypotheses, interact with tools, translate understanding into positions."

**Relevance:** Vision for our Layer 7 committee reasoning.

---

### arxiv:2303.17564 - "BloombergGPT: A Large Language Model for Finance"

**URL:** https://arxiv.org/abs/2303.17564

**Scale:** 50B parameters, 363B token financial dataset + 345B general.

**Relevance:** Benchmark for domain-specific financial LLMs.

---

### arxiv:2408.06361 - "Large Language Model Agent in Financial Trading: A Survey"

**Published:** August 2024
**URL:** https://arxiv.org/html/2408.06361v1

**Key Pattern:** LLM as Alpha Miner - generates alpha factors instead of direct decisions.

**Relevance:** Alternative to direct LLM trading - use for signal generation.

---

## 32. Deep RL Portfolio Optimization

### arXiv:2412.18563 - "A Deep Reinforcement Learning Framework for Dynamic Portfolio Optimization"

**Published:** December 2024
**URL:** https://arxiv.org/abs/2412.18563

**Abstract:**
Introduces a novel Sharpe ratio reward function for Actor-Critic DRL algorithms. Validates on CSI 300 Index constituent stocks with stable convergence and positive Sharpe ratios.

**Key Innovation:**
- Direct Sharpe ratio optimization in reward function
- Actor-Critic architecture stability improvements

**Relevance to Coinswarm:**
- Validates our fitness function using Sharpe/Sortino
- Actor-Critic could inform agent decision architecture

---

### arXiv:2403.07916 - "Advancing Investment Frontiers: Industry-grade Deep RL for Portfolio Optimization"

**Published:** February 2024
**URL:** https://arxiv.org/abs/2403.07916

**Abstract:**
First study integrating financial RL with sim-to-real methodologies from robotics. Introduces AlphaOptimizerNet achieving strong risk-return optimization across asset classes.

**Key Findings:**
- Sim-to-real transfer critical for deployment
- Asset-class agnostic approaches possible
- Industry compliance integration

**Relevance:** Validates transfer from backtest (sim) to live (real) - our core challenge.

---

### arXiv:2501.06832 - "Multi-Agent Dynamic Portfolio Optimization with Hierarchical Deep RL"

**Published:** January 2025
**URL:** https://arxiv.org/abs/2501.06832

**Abstract:**
Multi-agent HDRL framework where auxiliary agent works with executive agent for optimal policy exploration in portfolio optimization.

**Relevance:**
- **DIRECT VALIDATION** of our 5-layer cognitive hierarchy
- Auxiliary agent = our Coaches layer
- Executive agent = our Agent layer
- Hierarchical structure empirically validated

---

### arXiv:2511.11481 - "Risk-Aware Deep Reinforcement Learning for Dynamic Portfolio Optimization"

**Published:** November 2025
**URL:** https://arxiv.org/abs/2511.11481

**Abstract:**
PPO with direct risk control (max drawdown + volatility constraints). Found DRL stabilizes volatility but can suffer from over-conservative policy convergence.

**Key Finding:** Need improved reward shaping + hybrid risk-aware strategies.

**Relevance:**
- Informs our #1 risk_tolerance trait implementation
- Validates constraint-based approach to max drawdown limits

---

## 33. Attention & Transformer Finance

### arXiv:2407.13806 - "Revisiting Attention for Multivariate Time Series Forecasting"

**Published:** July 2024
**URL:** https://arxiv.org/abs/2407.13806

**Abstract:**
Proposes FSatten (Frequency Spectrum attention) using Fourier transform in attention mechanism. Demonstrates superiority over conventional attention for MTSF.

**Key Innovation:**
- Frequency domain attention mapping
- Head-Coupling Convolution (HCC) for neighboring similarity

**Relevance:** Could enhance our multi-asset pattern correlation detection.

---

### arXiv:2310.01232 - "Modality-aware Transformer for Financial Time Series Forecasting"

**Published:** October 2023 (updated March 2024)
**URL:** https://arxiv.org/abs/2310.01232

**Abstract:**
MAT (Modality-aware Transformer) for multimodal financial forecasting combining categorical text + numerical time series.

**Key Architecture:**
- Intra-modal MHA for within-modality
- Inter-modal MHA for cross-modality fusion
- Feature-level attention layers

**Relevance:**
- Validates our Three Pillars architecture
- Text (sentiment) + Numbers (technical) fusion approach

---

### arXiv:2411.05793 - "A Comprehensive Survey of Time Series Forecasting: Architectural Diversity"

**Published:** November 2024
**URL:** https://arxiv.org/abs/2411.05793

**Abstract:**
Comprehensive survey covering state-space models, attention mechanisms, GNNs, and foundation models for time series.

**Relevance:** Reference for model selection in pattern discovery.

---

## 34. High-Frequency & Market Microstructure

### arXiv:2407.21025 - "Reinforcement Learning in High-frequency Market Making"

**Published:** July 2024
**URL:** https://arxiv.org/abs/2407.21025

**Abstract:**
Bridges RL theory with continuous-time statistical models for HF market making. Identifies tradeoff: smaller time increments → smaller error but larger complexity.

**Key Finding:**
- Error-complexity tradeoff is fundamental
- Continuous-time models essential for HF

**Relevance:**
- Informs Phase 4 market making implementation
- Validates RL approach for quote optimization

---

### arXiv:2405.08101 - "Data-Driven Measures of High-Frequency Trading"

**Published:** May 2024
**URL:** https://arxiv.org/abs/2405.08101

**Abstract:**
ML approach to measuring HFT activity from public data. HFT firms execute ~50% of US equity volume.

**Relevance:** Benchmarking for identifying HFT patterns to avoid.

---

### arXiv:2510.25929 - "Multi-Agent Reinforcement Learning for Market Making: Competition without Collusion"

**Published:** October 2025
**URL:** https://arxiv.org/abs/2510.25929

**Abstract:**
MARL framework with layered architecture, non-trading adversary reshapes market environment, competing market makers face heterogeneous strategic pressures.

**Relevance:**
- Validates multi-agent market making approach
- Adversarial training concept for robustness

---

## 35. DeFi Security & Flash Loans

### arXiv:2411.01230 - "FlashDeFier: Static Analysis for Flash Loan Vulnerabilities"

**Published:** November 2024
**URL:** https://arxiv.org/abs/2411.01230

**Abstract:**
Static taint analyzer extending DeFiTainter for detecting price manipulation vulnerabilities in smart contracts.

**Key Innovation:**
- Taint analysis on decompiled contracts
- Price manipulation detection

**Relevance:** Security awareness for DeFi interactions in Phase 4+.

---

### arXiv:2311.17715 - "Market Misconduct in Decentralized Finance"

**Published:** November 2023 (updated 2024)
**URL:** https://arxiv.org/abs/2311.17715

**Abstract:**
Analyzes how mixing services, flash loans, FaaS (Flashbots-as-a-Service), and transaction auctions enable market misconduct in DeFi.

**Key Concepts:**
- Zero-collateralized flash loans enable instant billions access
- MEV exploitation mechanisms

**Relevance:** Understanding adversarial environment for DEX trading.

---

### FlashSyn (ICSE '24) - "Flash Loan Attack Synthesis via Counter Example Driven Approximation"

**Published:** April 2024
**URL:** https://arxiv.org/abs/2206.10708

**Abstract:**
Automated synthesis of adversarial flash loan transactions using polynomial regression and nearest-neighbor interpolation to approximate DeFi protocol behaviors.

**Relevance:** Defensive awareness - understanding attack vectors.

---

## 36. Risk Parity & Dynamic Allocation

### arXiv:2402.15994 - "Optimizing Portfolio Management and Risk Assessment in Digital Assets Using Deep Learning"

**Published:** February 2024
**URL:** https://arxiv.org/abs/2402.15994

**Abstract:**
DQN algorithm for digital asset portfolio management, greatly exceeds benchmark performance. Addresses limitation of ignoring whole market risk.

**Relevance:** Validates DRL for crypto portfolio optimization.

---

### arXiv:2305.17523 - "Portfolio Optimization: Mean-Variance, HRP, and Reinforcement Learning"

**Published:** May 2023
**URL:** https://arxiv.org/abs/2305.17523

**Abstract:**
Comparative analysis of MVP, Hierarchical Risk Parity (HRP), and RL-based portfolios on NIFTY50 stocks.

**Key Finding:** HRP provides robustness against fluctuating covariances.

**Relevance:**
- HRP could inform our multi-pattern allocation
- Benchmark approaches for agent portfolio construction

---

### arXiv:2402.00515 - "MASA: Multi-Agent Self-Adaptive Framework for Dynamic Portfolio Risk Management"

**Published:** February 2024 (AAMAS 2024)
**URL:** https://arxiv.org/abs/2402.00515

**Abstract:**
Two cooperating reactive agents dynamically balance portfolio returns vs risks under turbulent conditions.

**CRITICAL:** This is the MASA paper referenced in our hierarchy comparison! Our 5-layer extends their 2-agent architecture.

**Relevance:** **FOUNDATIONAL REFERENCE** for cognitive hierarchy validation.

---

## 37. Multi-Agent LLM Trading

### arXiv:2412.20138 - "TradingAgents: Multi-Agents LLM Financial Trading Framework"

**Published:** December 2024
**URL:** https://arxiv.org/abs/2412.20138

**Abstract:**
LLM agents in specialized roles: fundamental analysts, sentiment analysts, technical analysts, traders with varied risk profiles. Includes Bull/Bear researchers, risk management team.

**Key Architecture:**
- Role specialization (analysts, traders, risk)
- Debate mechanism for decision synthesis
- Historical data integration

**Relevance:**
- **VALIDATES** our Committee voting architecture
- Bull/Bear = our pattern affinity specialization
- Risk team = our Coaches layer

---

### arXiv:2512.02227 - "FinAgent: Orchestration Framework for Financial Agents"

**Published:** December 2025
**URL:** https://arxiv.org/abs/2512.02227

**Abstract:**
Agent pools for each stage: data, alpha, risk, portfolio, execution. Maps traditional algo trading to agents including planner, orchestrator, memory agent.

**Key Architecture:**
- Planner agent (strategic)
- Orchestrator (coordination)
- Memory agent (wisdom accumulation)

**Relevance:**
- **DIRECT PARALLEL** to our 5-layer hierarchy
- Memory agent = our Semantic Memory layer
- Planner = our Layer 6 Coaches/Planners

---

### arXiv:2510.08068 - "An Adaptive Multi-Agent Bitcoin Trading System"

**Published:** October 2025
**URL:** https://arxiv.org/abs/2510.08068

**Abstract:**
Reflect agent provides daily/weekly natural-language critiques. Textual evaluations injected into future prompts - no weight updates needed.

**Key Innovation:**
- Verbal feedback mechanism
- Natural language reflection loop
- Prompt-based adaptation without fine-tuning

**Relevance:**
- **VALIDATES** our wisdom extraction concept
- WHEN-DO-BECAUSE rules as textual feedback
- Agent self-reflection architecture

---

### arXiv:2502.13165 - "HedgeAgents: A Balanced-aware Multi-agent Financial Trading System"

**Published:** February 2025
**URL:** https://arxiv.org/abs/2502.13165

**Abstract:**
Multi-agent system with fund manager + specialized experts (Stocks, Forex, Bitcoin). LLM acts as brain.

**Relevance:**
- Specialization per asset class
- Fund manager = our Coach/Planner layer

---

## 38. Regime Detection & Classification

### arXiv:2410.22346 - "Representation Learning for Regime Detection in Block Hierarchical Financial Markets"

**Published:** October 2024
**URL:** https://arxiv.org/abs/2410.22346

**Abstract:**
Deep representation learning using hierarchical correlation structure for market state classification. Tests SPDNet variants on JSE Top 60 data.

**Key Finding:** Riemannian batchnorm layers improve market state classification accuracy.

**Relevance:** Advanced regime detection for market condition awareness.

---

### arXiv:2503.11499 - "Tactical Asset Allocation with Macroeconomic Regime Detection"

**Published:** March 2025
**URL:** https://arxiv.org/abs/2503.11499

**Abstract:**
K-means clustering with probabilistic regime assignments. Regime-based portfolios significantly outperform random classifications.

**Relevance:**
- Validates regime-conditional strategy selection
- Informs #11 lookback_preference trait adaptation

---

### arXiv:2306.15835 - "Non-parametric Online Market Regime Detection"

**Published:** June 2023
**URL:** https://arxiv.org/abs/2306.15835

**Abstract:**
Online regime detection using path signatures and MMD-based similarity on path space. Applied to equities and crypto baskets.

**Key Innovation:**
- Non-parametric approach
- Path signature feature mapping
- Online (real-time) detection

**Relevance:**
- Real-time regime shift detection
- Applicable to our multi-asset patterns

---

## 39. GARCH-Neural Hybrid Volatility

### arXiv:2410.00288 - "GARCH-Informed Neural Networks for Volatility Prediction"

**Published:** September 2024
**URL:** https://arxiv.org/abs/2410.00288

**Abstract:**
Hybrid model combining GARCH with LSTM. GARCH serves as regularization in loss function, guarding against overfitting. Superior out-of-sample performance.

**Key Innovation:**
- Physics-Informed NN approach for finance
- GARCH as inductive bias
- Regularization through domain knowledge

**Relevance:**
- Informs volatility indicators
- Model architecture for volatility prediction

---

### arXiv:2402.06642 - "From GARCH to Neural Network for Volatility Forecast"

**Published:** January 2024
**URL:** https://arxiv.org/abs/2402.06642

**Abstract:**
Establishes equivalence between GARCH family models and NN counterparts. Introduces GARCH-NN construction approach.

**Key Finding:** GARCH models have direct NN equivalents.

**Relevance:** Bridges econometric and ML approaches for our hybrid indicators.

---

### arXiv:2504.09380 - "Unified GARCH-Recurrent Neural Network for Financial Volatility Forecasting"

**Published:** April 2025
**URL:** https://arxiv.org/abs/2504.09380

**Abstract:**
GARCH-GRU and GARCH-LSTM architectures embedding GARCH(1,1) into RNN gates. GARCH-GRU trains 3x faster with comparable accuracy.

**Relevance:**
- Efficient volatility forecasting
- Interpretable hybrid architecture

---

## 40. Option Hedging with Deep Learning

### arXiv:2407.21791 - "Deep Learning for Options Trading: An End-To-End Approach"

**Published:** July 2024
**URL:** https://arxiv.org/abs/2407.21791

**Abstract:**
Deep learning models for portfolio of options management. No simulation or market process assumptions required. Scales with historical data.

**Relevance:** End-to-end learning approach applicable to our pattern discovery.

---

### arXiv:2405.08602 - "Optimizing Deep RL for American Put Option Hedging"

**Published:** May 2024
**URL:** https://arxiv.org/abs/2405.08602

**Abstract:**
DRL agents re-trained weekly outperform sale-date training. Both single and weekly-train DRL beat Black-Scholes Delta at 1-3% transaction costs.

**Relevance:**
- Continuous retraining validates our evolution cycles
- Transaction cost handling

---

### arXiv:2407.19367 - "Enhancing Black-Scholes Delta Hedging via Deep Learning"

**Published:** August 2024
**URL:** https://arxiv.org/abs/2407.19367

**Abstract:**
Deep learning learns correction terms to Black-Scholes framework. Hybrid model-based + data-driven approach validated on 10 years S&P 500 options.

**Key Innovation:** Correction terms rather than replacement.

**Relevance:** Hybrid approach paradigm for our AI enhancement of traditional indicators.

---

## 41. Optimal Execution (VWAP/TWAP)

### arXiv:2502.13722 - "Deep Learning for VWAP Execution in Crypto Markets"

**Published:** February 2025
**URL:** https://arxiv.org/abs/2502.13722

**Abstract:**
Deep learning framework directly optimizing VWAP execution objective, bypassing intermediate volume curve prediction step.

**Key Innovation:** End-to-end VWAP optimization without explicit volume prediction.

**Relevance:**
- Directly applicable to Phase 4 execution
- Crypto-specific VWAP research

---

### arXiv:2411.06645 - "Two Learning Algorithms for Continuous-Time VWAP Targeting Execution"

**Published:** November 2024
**URL:** https://arxiv.org/abs/2411.06645

**Abstract:**
ML-AC and MO-AC Actor-Critic algorithms for VWAP targeting with entropy regularization for exploration.

**Relevance:** RL algorithms for execution optimization.

---

### arXiv:2212.14670 - "Hierarchical Deep RL for VWAP" (M3T)

**Published:** December 2022
**URL:** https://arxiv.org/abs/2212.14670

**Abstract:**
Macro-Meta-Micro Trader (M3T) architecture capturing market patterns at different temporal scales. LSTM for improved volume forecasting.

**CRITICAL:** This is the M3T paper our 5-layer hierarchy extends!

**Relevance:**
- **FOUNDATIONAL REFERENCE** for cognitive hierarchy
- Our architecture adds Planners above + Patterns below M3T's 3 layers

---

## 42. Graph Neural Networks for Finance

### arXiv:2507.12787 - "Multi-Channel GNN for Financial Risk Prediction"

**Published:** July 2025
**URL:** https://arxiv.org/abs/2507.12787

**Abstract:**
Triple-Channel GNN (GIN-based) integrating numeric, textual, and graph-based inputs for NEEQ enterprise risk prediction.

**Relevance:** Multi-modal architecture for risk assessment.

---

### arXiv:2305.08740 - "Temporal and Heterogeneous GNN for Financial Time Series Prediction"

**Published:** May 2023
**URL:** https://arxiv.org/abs/2305.08740

**Abstract:**
THGNN generates dynamic company relation graphs per trading day from historic prices. No handcraft labeling needed.

**Relevance:**
- Dynamic relationship discovery
- Could inform cross-asset correlation detection

---

### arXiv:2403.06482 - "Financial Default Prediction via Motif-preserving GNN with Curriculum Learning"

**Published:** March 2024
**URL:** https://arxiv.org/abs/2403.06482

**Abstract:**
MotifGNN learning higher-order structures from motif-based graphs with curriculum learning for default prediction.

**Relevance:** Higher-order pattern structures concept.

---

### arXiv:2410.16858 - "Dynamic GNN for Volatility Prediction in Financial Markets"

**Published:** October 2024
**URL:** https://arxiv.org/abs/2410.16858

**Abstract:**
Temporal GAT combining GCN and GAT for capturing temporal and structural dynamics of volatility spillovers. Outperforms GARCH on 15-year study of 8 global indices.

**Relevance:**
- Volatility spillover detection
- Cross-market contagion modeling

---

## 43. Explainable AI (XAI) in Trading

### arXiv:2407.15909 - "A Survey of XAI in Financial Time Series Forecasting"

**Published:** July 2024
**URL:** https://arxiv.org/abs/2407.15909

**Abstract:**
Comprehensive survey categorizing XAI approaches for financial time series. Distinguishes explainability vs interpretability.

**Key Insight:** Interpretable models are transparent by design; explainable models use separate explanation methods.

**Relevance:**
- Framework for explaining agent decisions
- SHAP/LIME applicability to our patterns

---

### arXiv:2510.26353 - "Towards Explainable and Reliable AI in Finance"

**Published:** October 2025
**URL:** https://arxiv.org/abs/2510.26353

**Abstract:**
Meta-labeling as "Corrective AI" - secondary model as reliability estimator. Symbolic reasoning for accept/abstain decisions.

**Key Concept:**
- Primary model forecasts
- Secondary model estimates reliability
- Symbolic rules for transparency

**Relevance:**
- Meta-labeling for pattern confidence
- Validates our WHEN-DO-BECAUSE rules concept

---

### arXiv:2503.05966 - "A Systematic Review of Explainable AI in Finance"

**Published:** March 2025
**URL:** https://arxiv.org/abs/2503.05966

**Abstract:**
SHAP, attention mechanisms, and feature importance most commonly used. Strong correlation between post-hoc interpretability and tree-based models.

**Relevance:** XAI technique selection for agent introspection.

---

## 44. Stablecoin Depegging & Risk

### arXiv:2512.00893 - "Early-Warning Signals of Political Risk in Stablecoin Markets"

**Published:** December 2025
**URL:** https://arxiv.org/abs/2512.00893

**Abstract:**
2024 US election impact on crypto. Human-driven transactions shifted 2 days before election; algorithmic activity adjusted much later (January 2025).

**Key Finding:** Humans react faster to political events than algorithms.

**Relevance:**
- Event-driven strategy timing
- Human vs algorithmic reaction speed differential

---

### arXiv:2408.07227 - "Stablecoin Runs and Disclosure Policy"

**Published:** August 2024
**URL:** https://arxiv.org/abs/2408.07227

**Abstract:**
Global game model showing large sales increase selling pressure. Precise public knowledge reduces run probability when fundamentals strong; precise private signals can increase run probability.

**Key Finding:** Opaque stablecoins can be more stable (counterintuitive).

**Relevance:** Risk management for stablecoin positions.

---

### arXiv:2410.21446 - "Improving DeFi Mechanisms with Dynamic Games: Stablecoins"

**Published:** October 2024
**URL:** https://arxiv.org/abs/2410.21446

**Abstract:**
Algorithmic stablecoins rely on seigniorage shares for peg maintenance. Backing with volatile crypto introduces additional risk.

**Relevance:** Understanding algorithmic stablecoin fragility.

---

## 45. Memory-Augmented Trading Networks

### arXiv:2406.14537 - "MacroHFT: Memory Augmented Context-aware RL for High Frequency Trading"

**Published:** June 2024
**URL:** https://arxiv.org/abs/2406.14537

**Abstract:**
Memory-augmented neural network storing and retrieving information for trading decisions. Context-aware RL adapts to current market conditions.

**Key Innovation:**
- Long-term memory component for pattern recognition
- Context-aware decision making
- Combines memory + context + RL

**Relevance:**
- **VALIDATES** our three-tier memory architecture (Episodic, Semantic, Wisdom)
- Memory retrieval for informed decisions concept
- Context awareness for regime adaptation

---

### arXiv:2312.06141 - "Survey on Memory-Augmented Neural Networks"

**Published:** December 2023
**URL:** https://arxiv.org/abs/2312.06141

**Abstract:**
Covers memory types (sensory, short-term, long-term) linking psychological theories with AI. Explores Hopfield Networks, Neural Turing Machines, Memformer.

**Relevance:**
- Theoretical foundation for our memory architecture
- Memory type distinctions validate our Episodic/Semantic/Wisdom split

---

## 46. Genetic Algorithm Trading Strategies

### arXiv:2510.07943 - "CGA-Agent: Genetic Algorithm for Crypto Trading Strategy Optimization"

**Published:** October 2025
**URL:** https://arxiv.org/abs/2510.07943

**Abstract:**
Hybrid GA + multi-agent coordination for adaptive trading strategy parameter optimization. Real-time market microstructure intelligence. Returns improved 29% (BTC), 550% (ETH), 169% (BNB).

**Key Innovation:**
- Genetic algorithm + intelligent agents
- Adaptive parameter optimization
- Market microstructure integration

**Relevance:**
- **VALIDATES** our evolutionary pattern discovery
- GA for parameter optimization in our patterns
- Multi-agent coordination concept

---

### arXiv:2504.05418 - "Evolving Financial Trading Strategies with Vectorial Genetic Programming"

**Published:** April 2025
**URL:** https://arxiv.org/abs/2504.05418

**Abstract:**
Strongly-typed VGP outperforms standard GP for evolving trading rules using technical analysis indicators.

**Key Finding:** Strongly-typed GP consistently among best performers.

**Relevance:**
- Validates GP for trading rule evolution
- Type constraints improve results

---

### arXiv:2401.02710 - "Synergistic Formulaic Alpha Generation for Quantitative Trading based on RL"

**Published:** January 2024
**URL:** https://arxiv.org/abs/2401.02710

**Abstract:**
Combining alpha factors with low correlations using RL. Single alpha insufficient for complex stock market.

**Relevance:**
- Multi-pattern combination strategy
- Low-correlation pattern selection

---

## 47. AMM Liquidity Optimization

### arXiv:2508.08152 - "Optimal Fees for Liquidity Provision in AMMs"

**Published:** August 2025
**URL:** https://arxiv.org/abs/2508.08152

**Abstract:**
Studies optimal AMM fees in dynamic models with parallel CEX. Key tradeoff: fees must be low enough for volume, high enough for revenues and arbitrage mitigation.

**Key Finding:** Optimal fee is competitive with CEX in normal conditions; high fees protect LPs in high volatility.

**Relevance:**
- Phase 4 market making fee optimization
- Volatility-adaptive fee strategy

---

### arXiv:2504.16542 - "AMMs: Stochastic Optimization for Profitable Liquidity Concentration"

**Published:** April 2025
**URL:** https://arxiv.org/abs/2504.16542

**Abstract:**
Closed-form solutions for optimal liquidity provision intervals based on price volatility, drift, and pool profitability.

**Relevance:**
- Optimal interval calculation for concentrated liquidity
- Mathematical framework for LP positioning

---

### arXiv:2501.07828 - "AMMs: Toward More Profitable Liquidity Provisioning Strategies"

**Published:** January 2025
**URL:** https://arxiv.org/abs/2501.07828

**Abstract:**
Analysis of LP profitability. Stable-stable pools low-risk marginally profitable. Narrow positions increase returns but also volatility risk.

**Key Findings:**
- LP returns vary by pool type
- Narrow ranges: higher returns, higher risk
- Position range optimization critical

**Relevance:**
- Pool selection criteria for Phase 4
- Risk/return tradeoffs in LP

---

### arXiv:2403.03367 - "am-AMM: Auction-Managed Automated Market Maker"

**Published:** March 2024
**URL:** https://arxiv.org/abs/2403.03367

**Abstract:**
Auction for right to capture arbitrage profit. Manager selects fees and collects them. Higher equilibrium liquidity than standard AMMs.

**Key Innovation:** MEV capturing AMM (McAMM) concept.

**Relevance:** Understanding advanced AMM designs for Phase 4+.

---

## Appendix: New Papers Quick Reference (80 Total)

### Batch 1 (Added 2025-12-27) - 40 Papers

**Order Book/LOB (4):** 2506.05764, 2403.09267, 2312.16190, 2010.01241

**Manipulation/P&D (4):** 2412.18848, 2504.15790, 2510.00836, 2005.06610

**Multi-Agent (4):** 2402.00515, 2501.06832, 2303.11959, 2405.19982

**Regime Detection (3):** 2502.04027, 2301.09722, Giudici2020

**Kelly/Position Sizing (4):** 2402.15588, 2503.17927, 2508.16598, 2508.18868

**Correlation/Contagion (3):** 2507.08915, 2412.19983, 2509.15232

**On-Chain (3):** 2503.09165, 2403.17081, FinResLett2025

**Social/NLP (4):** 2508.15825, 2403.06036, 2501.09777, ElecMarkets2025

**Candlestick (3):** PeerJ2025, 1901.05237, 2201.08669

**Perpetuals (3):** 2506.08573, 2212.06888, 2510.14435

**Execution (3):** 2502.13722, 2502.18177, 2212.14670

**Transformer/LSTM (3):** 2412.14529, 2504.16361, 2506.22055

**Stop-Loss (3):** 1701.03960, SSRN2021, XiangDeng2024

**Genetic/Evolutionary (4):** 2510.07943, 2504.05418, 2504.21095, 2401.02710

**AMM/DEX (3):** 2508.08152, 2501.07828, 2506.02869

**Backtesting (3):** 2512.12924, BaileyBorwein, 1905.05023

**LLM Trading (5):** 2504.10789, 2406.11903, 2510.05533, 2303.17564, 2408.06361

---

### Batch 2 (Added 2025-12-28) - 40 Papers

**Deep RL Portfolio (4):** 2412.18563, 2403.07916, 2501.06832, 2511.11481

**Attention/Transformer (3):** 2407.13806, 2310.01232, 2411.05793

**HF Market Microstructure (3):** 2407.21025, 2405.08101, 2510.25929

**DeFi Security/Flash Loans (3):** 2411.01230, 2311.17715, FlashSyn-ICSE24

**Risk Parity/Allocation (3):** 2402.15994, 2305.17523, 2402.00515 (MASA)

**Multi-Agent LLM Trading (4):** 2412.20138, 2512.02227, 2510.08068, 2502.13165

**Regime Detection (3):** 2410.22346, 2503.11499, 2306.15835

**GARCH-Neural Hybrid (3):** 2410.00288, 2402.06642, 2504.09380

**Option Hedging DL (3):** 2407.21791, 2405.08602, 2407.19367

**Optimal Execution (3):** 2502.13722, 2411.06645, 2212.14670 (M3T)

**Graph Neural Networks (4):** 2507.12787, 2305.08740, 2403.06482, 2410.16858

**Explainable AI (3):** 2407.15909, 2510.26353, 2503.05966

**Stablecoin Risk (3):** 2512.00893, 2408.07227, 2410.21446

**Memory-Augmented (2):** 2406.14537 (MacroHFT), 2312.06141

**Genetic Algo Trading (3):** 2510.07943 (CGA-Agent), 2504.05418, 2401.02710

**AMM Liquidity (4):** 2508.08152, 2504.16542, 2501.07828, 2403.03367

---

### Key Foundational References (Papers Our Architecture Validates/Extends)

| Paper | Our Component | Relationship |
|-------|---------------|--------------|
| M3T (2212.14670) | 5-Layer Hierarchy | We EXTEND (add Planners + Patterns layers) |
| MASA (2402.00515) | Multi-Agent | We EXTEND (5 layers vs 2 agents) |
| MacroHFT (2406.14537) | Memory System | VALIDATES our Episodic/Semantic/Wisdom |
| TradingAgents (2412.20138) | Committee | VALIDATES voting architecture |
| FinAgent (2512.02227) | Planner/Memory | DIRECT PARALLEL to our architecture |
| CGA-Agent (2510.07943) | Evolution | VALIDATES evolutionary pattern discovery |
| XAI-Finance (2510.26353) | Wisdom Rules | VALIDATES WHEN-DO-BECAUSE concept |

---

*This document is part of Coinswarm's knowledge management system. For implementation details, see the referenced source files.*
