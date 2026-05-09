# AGENT DECISION & LLM CONSULTATION AUDIT
**Date**: 2026-01-21
**Status**: PRODUCTION-READY

## EXECUTIVE SUMMARY

**NO CRITICAL BUGS FOUND** - Well-designed system with proper error handling.

## 3-ZONE DECISION MODEL

| Zone | Confidence | Action |
|------|------------|--------|
| SKIP | < 0.35 | Never trade |
| AI_REFLECT | 0.35 - 0.65 | Consult LLM |
| EXECUTE | >= 0.65 | Auto-trade |

Thresholds are **per-agent configurable traits**.

## LLM CONSULTATION FLOW

1. Pattern evaluates → confidence calculated
2. If in AI_REFLECT zone → call Ollama
3. LLM receives: confidence, RSI, MACD, ADX, agent traits, recent performance
4. LLM responds: `{"decision": "TAKE/SKIP", "reasoning": "..."}`
5. On error → **defaults to SKIP** (conservative)

## LLM UNAVAILABILITY FALLBACK

When Ollama is down:
1. Check server (5s timeout)
2. If NO: Return `entry_aggression >= 0.5` (heuristic)
3. Retry 2x with exponential backoff
4. Mark as `ai_consulted=False`

## AI CONSULTATION TRACKING

Per-pattern metrics tracked:
- `total_decisions`
- `ai_consultations`
- `consultation_rate`

**Fitness Penalty**: High consultation rate = -15 fitness points max
(Creates selection pressure toward self-sufficient patterns)

## CONFIGURATION

```python
OLLAMA_MODEL = "koshtenco/agi-trader-kz50-quantum:latest"
LLM_TIMEOUT = 30 seconds
TEMPERATURE = 0.1 (low = consistent)
```
