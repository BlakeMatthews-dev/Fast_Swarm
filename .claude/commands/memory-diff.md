---
description: Show what changed in memory this session
---

# Memory Diff

Compare current memory state to session start snapshot.

## How It Works

SessionStart hook saves snapshot to `.claude/memory-snapshots/`.
This command compares current state to that snapshot.

## Process

1. Find most recent snapshot in `.claude/memory-snapshots/`
2. Load snapshot (JSON)
3. Get current state via `mcp__memory__read_graph`
4. Compute diff:
   - New entities created
   - Entities deleted
   - Observations added/removed
   - Relations changed

## Output Format

```
=== MEMORY DIFF ===
Session started: [timestamp]

+ CREATED ENTITIES:
  + "[Entity Name]" [Type] - N observations

+ ADDED OBSERVATIONS:
  + "[Entity]": "[new observation]"

~ MODIFIED:
  ~ "[Entity]": N → M observations

- DELETED:
  - "[Entity]" [Type]

SUMMARY: +N entities | -N entities | +N observations
```
