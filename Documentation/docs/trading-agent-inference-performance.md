# Trading Agent Inference Performance Analysis

## Hardware Options

| GPU | VRAM | Memory BW | Architecture | Tensor Cores |
|-----|------|-----------|--------------|--------------|
| 2x P40 | 48GB total | 346 GB/s | Pascal (2016) | No |
| RTX 3070 | 8GB | 448 GB/s | Ampere (2020) | Yes |

**Key insight:** P40 has 3x the VRAM but RTX 3070 has Tensor Cores = faster per token.

---

## Models & VRAM Requirements

| Model | Parameters | Active Params | VRAM (FP16) | VRAM (Q4) | Notes |
|-------|------------|---------------|-------------|-----------|-------|
| **GPT-OSS 20B** | 21B | 3.6B (MoE) | 16GB | ~8GB | Best quality/speed ratio |
| Phi-4 | 14B | 14B | 28GB | ~11GB | Excellent reasoning |
| Llama 3.3 70B | 70B | 70B | 140GB | ~40GB | Needs both P40s |
| Llama 3.1 8B | 8B | 8B | 16GB | ~5GB | Good mid-range |
| Llama 3.2 3B | 3B | 3B | 6GB | ~2GB | Fast, fits 3070 |
| Llama 3.2 1B | 1B | 1B | 2GB | ~1GB | Fastest |

**Note:** Llama 3.2 has 1B and 3B variants (not 7B). The 8B is Llama 3.1.

---

## Estimated Inference Speed (with vLLM prefix caching)

### Your Prompt Structure (from our work)
```
Static prefix (CACHED):     ~1,500 tokens (94%)
Dynamic suffix (computed):  ~300-500 tokens
- Personality traits:       ~50 tokens
- Active patterns:          ~100-200 tokens
- Candle data (1D,1H,15m):  ~150-250 tokens
Output (generated):         ~50-100 tokens
```

### Tokens/Second Estimates

| Model | P40 (single) | 2x P40 | RTX 3070 |
|-------|--------------|--------|----------|
| GPT-OSS 20B | 40-60 tok/s | 50-70 tok/s | ❌ (16GB needed) |
| Phi-4 14B (Q4) | 30-50 tok/s | 40-60 tok/s | 25-35 tok/s |
| Llama 3.1 8B | 50-70 tok/s | 60-80 tok/s | 40-55 tok/s (Q4) |
| Llama 3.2 3B | 80-120 tok/s | 100-140 tok/s | 60-80 tok/s |
| Llama 3.2 1B | 150-250 tok/s | 200-300 tok/s | 150-200 tok/s |
| Llama 3.3 70B | ❌ | 10-20 tok/s | ❌ |

*P40 is slower than expected due to no Tensor Cores. 2x P40 helps with batch processing.*

---

## Time Per Trading Decision

With 94% prefix caching, you only compute:
- Dynamic input: ~400 tokens
- Output generation: ~75 tokens

| Model | Input Processing | Output Generation | **Total Decision Time** |
|-------|------------------|-------------------|-------------------------|
| GPT-OSS 20B | ~0.5s | ~1.5s | **~2 seconds** |
| Phi-4 14B | ~0.8s | ~2.0s | **~3 seconds** |
| Llama 3.1 8B | ~0.4s | ~1.2s | **~1.6 seconds** |
| Llama 3.2 3B | ~0.3s | ~0.8s | **~1.1 seconds** |
| Llama 3.2 1B | ~0.2s | ~0.4s | **~0.6 seconds** |

---

## Decisions Per Minute (Per Agent)

| Model | Decisions/Min | Agents @ 1 decision/min |
|-------|---------------|-------------------------|
| GPT-OSS 20B | 30 | 30 concurrent agents |
| Phi-4 14B | 20 | 20 concurrent agents |
| Llama 3.1 8B | 37 | 37 concurrent agents |
| Llama 3.2 3B | 54 | 54 concurrent agents |
| Llama 3.2 1B | 100 | 100 concurrent agents |

---

## Recommended Configuration

### For Quality (Best Decisions)
```
Model: GPT-OSS 20B (on P40)
Speed: ~30 decisions/minute
Quality: Matches o3-mini on benchmarks
```

### For Speed (Most Throughput)
```
Model: Llama 3.2 3B (on RTX 3070)
Speed: ~54 decisions/minute
Quality: Good for simple trade/no-trade
```

### Hybrid Approach (Best of Both)
```
Fast Filter: Llama 3.2 1B → "Should I even consider a trade?" (0.6s)
Deep Analysis: GPT-OSS 20B → "What exactly should I do?" (2s)

Result: Screen 100 opportunities/min, deeply analyze 30/min
```

---

## Optimal Prompt for Trading Decisions

Given your use case, here's the minimal prompt structure:

```
LEVEL 1-4: Static prefix (CACHED, ~1500 tokens)
├── Agent identity
├── Indicator definitions
├── Pattern format
└── Output format

LEVEL 5: Batch context (CACHED per batch, ~200 tokens)
├── Current candles: {"1d": [...], "1h": [...], "15m": [...]}
└── Order book snapshot: {"bids": [...], "asks": [...]}

LEVEL 6: Agent-specific (PER CALL, ~200 tokens)
├── Personality traits: {"risk_tolerance": 0.7, "momentum_vs_reversion": 0.3, ...}
├── Active patterns: ["rsi_oversold_bounce", "macd_crossover_v2"]
└── Question: "Should I enter a long position on BTC/USDT?"

OUTPUT: (~75 tokens)
{
  "decision": "enter_long",
  "confidence": 0.78,
  "entry_price": 42850,
  "stop_loss": 42100,
  "take_profit": 44500,
  "reasoning": "RSI oversold with bullish MACD cross..."
}
```

---

## Multi-Timeframe Data Sizing

| Timeframe | Candles | Tokens (compressed) |
|-----------|---------|---------------------|
| 1 day | 30 days | ~50 tokens |
| 1 hour | 168 hours (7 days) | ~100 tokens |
| 15 min | 96 candles (24h) | ~80 tokens |
| 5 min | 72 candles (6h) | ~60 tokens |
| 1 min | 60 candles (1h) | ~50 tokens |
| Ticks | Last 100 | ~40 tokens |
| Order book | Top 10 bids/asks | ~30 tokens |
| **Total** | | **~410 tokens** |

This fits well in the dynamic suffix with room to spare.

---

## Hardware Recommendation

**For your setup (2x P40 + 128GB RAM):**

1. **Primary model:** GPT-OSS 20B on P40 #1
   - Best quality, 16GB VRAM, 3.6B active params
   - ~30 high-quality decisions/minute

2. **Filter model:** Llama 3.2 3B on P40 #2
   - Fast pre-screening
   - ~50 quick screens/minute

3. **Batch processing:** Use 128GB RAM for
   - Candle data caching
   - Pattern fitness calculations
   - Agent state management

**Total throughput:** ~30 deep decisions/minute across all agents, with 50 pre-screens/minute for opportunity detection.

---

## Sources

- [OpenAI GPT-OSS announcement](https://openai.com/index/introducing-gpt-oss/)
- [GPT-OSS GitHub](https://github.com/openai/gpt-oss)
- [vLLM performance blog](https://blog.vllm.ai/2024/09/05/perf-update.html)
- [NVIDIA Llama 3.2 optimizations](https://developer.nvidia.com/blog/llama-3-2-full-stack-optimizations-unlock-high-performance-on-nvidia-gpus/)
