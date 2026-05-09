# Memory Diff

Show what changed in memory during this session.

## What This Skill Does

1. Loads memory snapshot from session start (saved by SessionStart hook)
2. Gets current memory state via `mcp__memory__read_graph`
3. Computes diff between snapshots
4. Shows:
   - New entities created
   - Entities deleted
   - Observations added
   - Observations removed
   - Relations changed

## How Snapshots Work

The SessionStart hook saves a snapshot:
```
.claude/memory-snapshots/
├── 20251230_142300.json   # Session started at 14:23
├── 20251230_091500.json   # Earlier session
└── ...
```

Each snapshot contains the full memory graph state at session start.

## Output Format

```
=== MEMORY DIFF ===
Session: Started 2 hours ago (14:23)
Snapshot: .claude/memory-snapshots/20251230_142300.json

CHANGES THIS SESSION:

+ CREATED ENTITIES:
  + "Session 2025-12-30: Memory System" [Session Log]
    - 3 observations

+ ADDED OBSERVATIONS:
  + "Committee System":
    + "Fixed quorum to require 3 coaches minimum"
    + "Voting weights now decay over time"

  + "Position Management System":
    + "Added scale-out at 2x, 3x, 5x profit targets"

~ MODIFIED ENTITIES:
  ~ "Coinswarm Current Architecture (Dec 2025)":
    Changed: 5 observations → 7 observations

- DELETED:
  - "V3 Architecture Details" [Architecture]
    Reason: Outdated, V3 is dormant

RELATIONS:
  + "Session 2025-12-30" --created_during--> "Memory System Implementation"

SUMMARY:
  +2 entities | -1 entity | +5 observations | +1 relation
```

## Arguments

```
/memory-diff                    # Compare to session start
/memory-diff --snapshot <file>  # Compare to specific snapshot
/memory-diff --sessions 2       # Compare last 2 sessions
```

## Process

1. Find most recent snapshot for current session
2. Load snapshot (JSON file)
3. Call `mcp__memory__read_graph` for current state
4. Compute diff:
   - Set difference on entity names
   - Compare observations within matching entities
   - Compare relations
5. Format and display changes

## When to Use

- End of session to see what was learned
- Before `/compress` to verify extraction
- After `/memory-qa` to see clarifications added
- Audit trail of memory evolution

## Snapshot Management

Snapshots are kept for 7 days by default. Older snapshots can be archived or deleted:

```
/memory-diff --cleanup         # Delete snapshots older than 7 days
/memory-diff --archive 30      # Archive last 30 days to .claude/grounding/
```
