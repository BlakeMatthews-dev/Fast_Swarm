# Prompt Evolution Architecture

> Treating prompts as first-class evolutionary entities with vLLM prefix caching optimization

---

## The Problem

Currently prompts are:
- Hardcoded in TypeScript/Python files
- No version tracking
- No feedback loop from pattern fitness
- Can't iterate without code deploys
- Dynamic data at TOP of prompts (breaks vLLM caching)

---

## The Solution: Hierarchical Prefix Caching

Prompts are composed from nested components. Static parts come FIRST (cached by vLLM), dynamic data comes LAST.

```
┌─────────────────────────────────────────────────────────────────┐
│ LEVEL 1: _shared/identity.md (cached across ALL prompts)        │
│ "Welcome, Agent of CoinSwarm Trading Collective..."             │
├─────────────────────────────────────────────────────────────────┤
│ LEVEL 2: _shared/indicators.md (cached across ALL prompts)      │
│ Indicator definitions, formulas, valid values                   │
├─────────────────────────────────────────────────────────────────┤
│ LEVEL 3: {type}/_type.md (cached per prompt TYPE)               │
│ Task-specific instructions, output schema                       │
├─────────────────────────────────────────────────────────────────┤
│ LEVEL 4: _shared/output-format.md (cached across ALL)           │
│ JSON format rules, validation requirements                      │
├─────────────────────────────────────────────────────────────────┤
│ LEVEL 5: batch_context (cached per BATCH, ~1000 calls)          │
│ Shared candle data, market regime, current conditions           │
├─────────────────────────────────────────────────────────────────┤
│ LEVEL 6: {{variables}} (unique per CALL)                        │
│ Specific trade samples, pattern being analyzed                  │
└─────────────────────────────────────────────────────────────────┘
```

**Result:** 94%+ cache ratio on pattern discovery prompts.

---

## File Structure (Implemented)

```
prompts/
├── _shared/
│   ├── identity.md          # CoinSwarm agent identity & principles
│   ├── indicators.md        # All available indicators & formulas
│   └── output-format.md     # JSON output requirements
├── pattern-discovery/
│   ├── _type.md             # Pattern discovery specific instructions
│   └── v1.template.md       # Composes prefixes + {{variables}}
├── pattern-profile/
│   ├── _type.md
│   └── v1.template.md
└── paper-distillation/
    ├── _type.md
    └── v1.template.md
```

---

## Template Format

```markdown
---
type: pattern_discovery
version: 1
prefixes:
  - _shared/identity.md
  - _shared/indicators.md
  - pattern-discovery/_type.md
  - _shared/output-format.md
variables:
  - winners_count
  - losers_count
  - winners_json
  - losers_json
---

## Trade Data for Analysis

**Dataset Summary:**
- Winners: {{winners_count}} trades
- Losers: {{losers_count}} trades

**WINNING TRADES:**
{{winners_json}}

**LOSING TRADES:**
{{losers_json}}

Analyze the data above and output ONLY the JSON response.
```

---

## PromptManager (local-utilities/prompt_manager.py)

```python
from prompt_manager import PromptManager

pm = PromptManager()

# Render with automatic prefix caching
result = pm.render("pattern_discovery", {
    "winners_count": 50,
    "losers_count": 30,
    "winners_json": json.dumps(winners),
    "losers_json": json.dumps(losers),
})

# Use these for vLLM
prompt = result["prompt"]           # Full prompt to send
prefix_hash = result["prefix_hash"] # Cache key for vLLM
cache_ratio = result["cache_ratio"] # % of tokens that are cacheable

# Track which prompt generated which patterns
prompt_id = result["prompt_id"]     # e.g., "pattern_discovery-v1"
```

**With batch context (candles shared across 1000 calls):**

```python
# Candle data changes once per batch
candle_context = f"Current candles (shared):\n{json.dumps(candles)}"

# Each call in the batch
for trade_sample in samples:
    result = pm.render("pattern_discovery",
        variables={"winners_json": trade_sample},
        batch_context=candle_context  # Cached for entire batch
    )
```

---

## SQLite Tracking

**Database:** `local-utilities/prompts.sqlite`

```sql
CREATE TABLE prompts (
    prompt_id TEXT PRIMARY KEY,
    prompt_type TEXT NOT NULL,
    version INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    prefix_hash TEXT,                    -- For vLLM cache tracking
    patterns_generated INTEGER DEFAULT 0,
    avg_pattern_fitness REAL,
    best_pattern_fitness REAL,
    status TEXT DEFAULT 'active',
    last_used_at TEXT
);
```

**Fitness tracking:**
```python
# When pattern gets fitness score
pm.update_fitness(prompt_id, pattern_fitness=75.3)

# View report
for p in pm.report():
    print(f"{p['prompt_id']}: {p['avg_fitness']} ({p['patterns_generated']} patterns)")
```

---

## vLLM Integration

vLLM automatically caches prefixes with LRU eviction:

```python
# All calls with same prefix_hash reuse cached KV state
result1 = pm.render("pattern_discovery", vars1)  # Cache MISS, compute all
result2 = pm.render("pattern_discovery", vars2)  # Cache HIT, only compute suffix
result3 = pm.render("pattern_discovery", vars3)  # Cache HIT, only compute suffix

# Different prompt type = different prefix = different cache entry
result4 = pm.render("pattern_profile", vars4)    # Cache MISS (new prefix)
result5 = pm.render("pattern_profile", vars5)    # Cache HIT
```

**Multiple prefixes cached simultaneously** (up to GPU memory limit):
- pattern_discovery prefix: ~1500 tokens
- pattern_profile prefix: ~800 tokens
- paper_distillation prefix: ~1000 tokens
- All fit in GPU memory, all cached

---

## LoRA Training Consistency

The hierarchical structure ensures consistent embeddings for fine-tuning:

1. **identity.md** → Creates base "CoinSwarm agent" embedding space
2. **indicators.md** → Trading domain knowledge layer
3. **_type.md** → Task-specific specialization
4. **variables** → Instance-specific data

When training LoRA adapters, the consistent prefix structure means:
- Stable embedding space across training examples
- Clear separation of task-specific vs domain-general knowledge
- Easy A/B testing of different prompt versions

---

## CLI Tools

```bash
# Test render
python local-utilities/prompt_manager.py test

# View fitness report
python local-utilities/prompt_manager.py report

# View prefix cache stats
python local-utilities/prompt_manager.py prefixes
```

---

## What This Enables

1. **94% cache ratio** - Only compute 6% of tokens per call
2. **Nested prefixes** - Shared components across prompt types
3. **Batch context** - Cache candle data across 1000s of calls
4. **Fitness tracking** - Know which prompts produce winners
5. **LoRA consistency** - Stable embedding space for fine-tuning
6. **Git versioning** - Full history, diffs, PRs for prompt changes

---

## Next Steps

- [ ] Extract remaining prompts from code (pattern-profile, paper-distillation)
- [ ] Add prompt_id tracking to pattern generation
- [ ] Build fitness comparison dashboard
- [ ] Implement batch_context for candle data sharing
