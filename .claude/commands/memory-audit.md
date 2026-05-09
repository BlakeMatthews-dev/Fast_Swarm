---
description: Audit memory reliability and find weak claims
---

# Memory Audit

Evaluate reliability of each memory observation. Inspired by Quint-Code's First Principles Framework.

## Reliability Scoring (0.0 - 1.0)

| Factor | Impact |
|--------|--------|
| Has evidence | +0.20 |
| Fresh (< 7 days) | +0.10 |
| Validated by user | +0.15 |
| From code observation | +0.15 |
| Stale (> 90 days) | -0.10 per 30 days |
| Contradicted | -0.30 |
| Vague (no specifics) | -0.15 |

## Process

1. Load all memory via `mcp__memory__read_graph`
2. Score each observation
3. Identify:
   - Low reliability (< 0.5)
   - Contradictions
   - Missing evidence
   - Expiring validity
4. Recommend actions

## Output Format

```
=== MEMORY RELIABILITY AUDIT ===

OVERALL HEALTH: N% reliable

🔴 LOW RELIABILITY (< 0.5):
1. "[observation]"
   Reliability: 0.XX
   Issues: [list]
   → Recommend: [action]

🟡 MEDIUM (0.5-0.7):
...

🟢 HIGH (> 0.7):
...

⚠️ CONTRADICTIONS:
- "[claim A]" vs "[claim B]"
  → Recommend: [resolution]

RECOMMENDED ACTIONS:
□ Validate N claims with user (/memory-qa)
□ Delete N contradicted claims
□ Add evidence to N claims
```
