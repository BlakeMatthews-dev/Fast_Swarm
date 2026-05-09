# Memory Audit

Audit memory reliability and identify weak claims. Inspired by Quint-Code's First Principles Framework.

## Core Concept: Memories Are Claims

Not all memories are equally trustworthy. This skill evaluates each observation's **reliability** based on evidence, age, and validation.

## Reliability Scoring (0.0 - 1.0)

| Factor | Impact |
|--------|--------|
| Has evidence | +0.20 |
| Fresh (< 7 days) | +0.10 |
| Validated by user | +0.15 |
| From code observation | +0.15 |
| Stale (> 90 days) | -0.10 per 30 days |
| Contradicted by other memory | -0.30 |
| Vague (no specifics) | -0.15 |
| Assumption (no source) | -0.10 |

**Calculation:**
```
Base: 0.50 (neutral)
+ evidence bonuses
- penalties
= Final score (capped 0.1 - 1.0)
```

## Evidence Types

| Type | Reliability Boost | Example |
|------|-------------------|---------|
| `benchmark` | +0.25 | Performance test results |
| `user_stated` | +0.20 | User explicitly confirmed |
| `code_observed` | +0.15 | Verified in codebase |
| `git_history` | +0.15 | Seen in commits |
| `inferred` | +0.05 | Claude deduced |
| `assumption` | +0.00 | No direct evidence |

## Output Format

```
=== MEMORY RELIABILITY AUDIT ===

OVERALL HEALTH: 72% reliable (7 entities, 23 observations)

🔴 LOW RELIABILITY (< 0.5):

1. "Committee quorum is 3"
   Reliability: 0.35
   Issues:
   - No evidence (assumption)
   - 45 days old without refresh
   - No file reference
   → Recommend: Ask user to confirm

2. "V3 uses Durable Objects for state"
   Reliability: 0.40
   Issues:
   - V3 marked as dormant (contradiction?)
   - 60 days old
   → Recommend: Delete or clarify scope

🟡 MEDIUM RELIABILITY (0.5 - 0.7):

3. "PostgreSQL is primary database"
   Reliability: 0.65
   Evidence: code_observed (75 files use psycopg2)
   → Could improve: Add benchmark evidence

🟢 HIGH RELIABILITY (> 0.7):

4. "7-layer intelligence hierarchy"
   Reliability: 0.85
   Evidence: user_stated, code_observed
   Last validated: 2 days ago
   → Good standing

⚠️ CONTRADICTIONS DETECTED:

- "V3 Cloudflare is primary" vs "Python/PostgreSQL is primary"
  Resolution: V3 is dormant, Python is current active
  → Recommend: Update V3 entity to clarify dormant status

📅 EXPIRING SOON (validity ending):

- "Trailing stops at 2%" - expires in 15 days
  → Recommend: Validate still accurate

RECOMMENDED ACTIONS:
□ Validate 2 low-reliability claims with user (/memory-qa)
□ Delete 1 contradicted claim
□ Refresh 3 stale observations
□ Add evidence to 2 medium-reliability claims

Run /memory-qa to address these issues interactively.
```

## Weakest-Link Principle

A claim built on weak foundations inherits that weakness:

```
"Committee voting works correctly" (R: 0.9)
  └── depends on "Quorum is 3 coaches" (R: 0.4)
      └── Final effective reliability: 0.4

Even if the voting logic is well-tested, if we're uncertain
about the quorum requirement, the whole claim is weak.
```

## Process

1. Load all memory via `mcp__memory__read_graph`
2. For each observation, calculate reliability:
   - Check for evidence markers
   - Calculate age penalty
   - Check for contradictions
   - Check for vagueness
3. Identify dependency chains (if observable)
4. Apply weakest-link to dependent claims
5. Rank by severity (low reliability + high importance)
6. Generate action recommendations

## When to Use

- Weekly maintenance
- After major codebase changes
- When Claude seems to have wrong information
- Before important decisions
- After importing/migrating memories

## Integration with Grounding Layer

High-value claims should have evidence in `.claude/grounding/`:

```
.claude/grounding/
├── evidence/
│   ├── bench_pg_performance_20251215.md  # Benchmark results
│   └── user_decision_committee_quorum.md  # User confirmation
├── sessions/
│   └── 2025-12-30_memory_system.jsonl    # Full session transcript
└── decisions/
    └── 2025-12-15_database_choice.md     # Decision rationale
```

When auditing, check if evidence files exist for claims that need them.
