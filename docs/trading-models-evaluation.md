# Trading LLM Models Evaluation

## VRAM Constraints

RTX 3070 = 8GB VRAM

- **Can fit FP16**: Models up to ~3B parameters
- **Can fit 4-bit**: Models up to ~14B parameters
- **Target**: 50 candidates, select 30 most promising for testing

---

## 50 Candidate Models (Fit 8GB VRAM)

### Tier 1: General Small Instruction Models (vLLM Native)

| # | Model | Size | Type | Notes |
|---|-------|------|------|-------|
| 1 | Qwen/Qwen2.5-0.5B-Instruct | 0.5B | FP16 | Baseline, fastest |
| 2 | Qwen/Qwen2.5-1.5B-Instruct | 1.5B | FP16 | Current production |
| 3 | Qwen/Qwen2-0.5B-Instruct | 0.5B | FP16 | Previous gen |
| 4 | meta-llama/Llama-3.2-1B-Instruct | 1B | FP16 | Meta official |
| 5 | meta-llama/Llama-3.2-3B-Instruct | 3B | FP16 | Larger Llama 3.2 |
| 6 | unsloth/Llama-3.2-1B-Instruct | 1B | FP16 | Unsloth optimized |
| 7 | unsloth/Llama-3.2-3B-Instruct | 3B | FP16 | Unsloth optimized |
| 8 | google/gemma-2b-it | 2B | FP16 | Google Gemma v1 |
| 9 | google/gemma-2-2b-it | 2.6B | FP16 | Google Gemma v2 |
| 10 | TinyLlama/TinyLlama-1.1B-Chat-v1.0 | 1.1B | FP16 | Ultra-lightweight |
| 11 | microsoft/Phi-3-mini-4k-instruct | 3.8B | FP16 | Microsoft Phi-3 |

### Tier 2: SmolLM Family (HuggingFace Official)

| # | Model | Size | Type | Notes |
|---|-------|------|------|-------|
| 12 | HuggingFaceTB/SmolLM-135M-Instruct | 135M | FP16 | Tiny baseline |
| 13 | HuggingFaceTB/SmolLM-360M-Instruct | 360M | FP16 | Small |
| 14 | HuggingFaceTB/SmolLM-1.7B-Instruct | 1.7B | FP16 | SmolLM v1 |
| 15 | HuggingFaceTB/SmolLM2-135M | 135M | FP16 | SmolLM v2 tiny |
| 16 | HuggingFaceTB/SmolLM2-1.7B-Instruct | 1.7B | FP16 | SmolLM v2 best |

### Tier 3: StableLM / Other Small

| # | Model | Size | Type | Notes |
|---|-------|------|------|-------|
| 17 | stabilityai/stablelm-2-zephyr-1_6b | 1.6B | FP16 | Chat-tuned |
| 18 | stabilityai/stablelm-zephyr-3b | 3B | FP16 | Larger StableLM |

### Tier 4: 4-bit Quantized 7B Models (AWQ/GPTQ)

| # | Model | Size | Type | Notes |
|---|-------|------|------|-------|
| 19 | TheBloke/Mistral-7B-Instruct-v0.2-AWQ | 7B | AWQ 4-bit | ~4GB VRAM |
| 20 | TheBloke/Mistral-7B-v0.1-AWQ | 7B | AWQ 4-bit | Base Mistral |
| 21 | TheBloke/Mistral-7B-OpenOrca-AWQ | 7B | AWQ 4-bit | OpenOrca fine-tune |
| 22 | neuralmagic/Llama-3.2-1B-Instruct-FP8-dynamic | 1B | FP8 | NeuralMagic optimized |
| 23 | RedHatAI/Llama-3.2-1B-Instruct-FP8-dynamic | 1B | FP8 | RedHat version |
| 24 | twinkle-ai/Llama-3.2-3B-F1-Instruct | 3B | FP16 | F1 fine-tuned |

### Tier 5: Finance/Sentiment BERT Models (Classification)

| # | Model | Size | Type | Notes |
|---|-------|------|------|-------|
| 25 | ProsusAI/finbert | ~110M | BERT | Financial sentiment |
| 26 | yiyanghkust/finbert-tone | ~110M | BERT | Analyst report tone |
| 27 | ahmedrachid/FinancialBERT-Sentiment-Analysis | ~110M | BERT | Financial news |
| 28 | ElKulako/cryptobert | ~110M | BERT | Crypto sentiment |
| 29 | kk08/CryptoBERT | ~110M | BERT | Crypto-specific |
| 30 | AfterRain007/cryptobertRefined | ~110M | BERT | Refined CryptoBERT |
| 31 | mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis | ~80M | DistilRoBERTa | Fast sentiment |
| 32 | peejm/finbert-financial-sentiment | ~110M | BERT | Financial sentiment v2 |
| 33 | kdave/FineTuned_Finbert | ~110M | BERT | India-focused |

### Tier 6: Trading-Specific Models (From User List)

| # | Model | Size | Type | Notes |
|---|-------|------|------|-------|
| 34 | RichardErkhov/KRX-Trader_-_qwen2.5-test-4bits | ~7B | 4-bit | Korean market trader |
| 35 | Caliban-17/Adaptive-Trader | ? | ? | Adaptive trading |
| 36 | xianghe-ai/trader-cot | ? | ? | Chain-of-thought |
| 37 | agarkovv/CryptoTrader-LM | 8B LoRA | LoRA | Crypto decisions |
| 38 | TigerTrading/TradingBot | ? | ? | Financial news sentiment |

### Tier 7: Additional Qwen/Gemma Variants

| # | Model | Size | Type | Notes |
|---|-------|------|------|-------|
| 39 | Qwen/Qwen2.5-3B-Instruct | 3B | FP16 | Mid-size Qwen |
| 40 | Qwen/Qwen2.5-Coder-1.5B-Instruct | 1.5B | FP16 | Code-focused |
| 41 | google/gemma-2b | 2B | FP16 | Base Gemma |
| 42 | embedl/Llama-3.2-1B-Instruct-FlashHead | 1B | FP16 | 1.75x faster |

### Tier 8: FinGPT Models (LoRA Adapters)

| # | Model | Size | Type | Notes |
|---|-------|------|------|-------|
| 43 | FinGPT/fingpt-sentiment_llama2-13b_lora | 13B | LoRA | Too large alone |
| 44 | FinGPT/fingpt-forecaster_dow30_llama2-7b_lora | 7B | LoRA | Forecasting |

### Tier 9: Miscellaneous Small Models

| # | Model | Size | Type | Notes |
|---|-------|------|------|-------|
| 45 | WiroAI/WiroAI-Finance-Qwen-1.5B | 1.5B | FP16 | Finance Qwen |
| 46 | TinyLlama/TinyLlama_v1.1 | 1.1B | FP16 | TinyLlama base |
| 47 | Qwen/Qwen2.5-0.5B | 0.5B | FP16 | Base (not instruct) |
| 48 | llmware/bling-tiny-llama-onnx | 1.1B | ONNX | RAG-optimized |
| 49 | cloudqi/crypto_trading_insights | LSTM | N/A | Not LLM (time-series) |
| 50 | solanaexpert/RandomForestBTCUSDTModel | RF | N/A | Not LLM (sklearn) |

---

## Selected 30 Models for Testing

Based on:
1. **vLLM compatibility** (native HF format, not GGUF)
2. **Known working sizes** (verified <8GB)
3. **Relevance** (instruction-following or finance-specific)
4. **Diversity** (different architectures for comparison)

### Priority Selection

| Rank | Model | Rationale |
|------|-------|-----------|
| 1 | Qwen/Qwen2.5-1.5B-Instruct | Current baseline, known working |
| 2 | Qwen/Qwen2.5-0.5B-Instruct | Speed baseline |
| 3 | meta-llama/Llama-3.2-1B-Instruct | Meta's latest small |
| 4 | meta-llama/Llama-3.2-3B-Instruct | Larger Llama for comparison |
| 5 | google/gemma-2-2b-it | Google's latest 2B |
| 6 | microsoft/Phi-3-mini-4k-instruct | Microsoft's 3.8B |
| 7 | HuggingFaceTB/SmolLM2-1.7B-Instruct | HF's latest small |
| 8 | TinyLlama/TinyLlama-1.1B-Chat-v1.0 | Ultra-fast baseline |
| 9 | stabilityai/stablelm-2-zephyr-1_6b | Stability AI small |
| 10 | TheBloke/Mistral-7B-Instruct-v0.2-AWQ | 4-bit 7B quality |
| 11 | ProsusAI/finbert | Finance sentiment |
| 12 | ElKulako/cryptobert | Crypto sentiment |
| 13 | yiyanghkust/finbert-tone | Analyst tone |
| 14 | RichardErkhov/KRX-Trader_-_qwen2.5-test-4bits | Trading-specific |
| 15 | Qwen/Qwen2.5-3B-Instruct | Mid-size quality |
| 16 | HuggingFaceTB/SmolLM-360M-Instruct | Tiny but capable |
| 17 | HuggingFaceTB/SmolLM-135M-Instruct | Smallest baseline |
| 18 | google/gemma-2b-it | Gemma v1 comparison |
| 19 | unsloth/Llama-3.2-1B-Instruct | Unsloth optimized |
| 20 | ahmedrachid/FinancialBERT-Sentiment-Analysis | Alt finance BERT |
| 21 | mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis | Fast sentiment |
| 22 | Caliban-17/Adaptive-Trader | Trading-focused |
| 23 | xianghe-ai/trader-cot | CoT trading |
| 24 | twinkle-ai/Llama-3.2-3B-F1-Instruct | F1 tuned |
| 25 | neuralmagic/Llama-3.2-1B-Instruct-FP8-dynamic | FP8 optimized |
| 26 | Qwen/Qwen2-0.5B-Instruct | Qwen v2 baseline |
| 27 | HuggingFaceTB/SmolLM-1.7B-Instruct | SmolLM v1 |
| 28 | stabilityai/stablelm-zephyr-3b | Larger StableLM |
| 29 | kk08/CryptoBERT | Alt crypto BERT |
| 30 | embedl/Llama-3.2-1B-Instruct-FlashHead | Speed optimized |

---

## Test Results

| Model | Accuracy | Speed (dec/s) | VRAM Used | Notes |
|-------|----------|---------------|-----------|-------|
| Qwen2.5-0.5B | TBD | 28/s | ~1.5GB | Baseline |
| Qwen2.5-1.5B | TBD | TBD | ~3.5GB | Current |
| ... | ... | ... | ... | ... |

---

*Last updated: 2026-01-12*
