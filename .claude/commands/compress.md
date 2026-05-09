---
description: Super thorough context extraction then double compaction
---

# Super Compress

Extract EVERYTHING valuable from current context, save to memory, then compact aggressively.

## Phase 1: Deep Extraction

Extract from current conversation:

1. **Decisions Made** - What, why, alternatives considered
2. **Code Changes** - Files modified, patterns established
3. **Errors & Fixes** - What broke, root cause, solution
4. **Discoveries** - Architecture insights, "aha" moments
5. **Open Questions** - Unresolved issues, blocked items
6. **Next Session Context** - Where we left off, next steps

## Phase 2: Save to Memory

Use MCP memory tools:
- `mcp__memory__create_entities` for new topics
- `mcp__memory__add_observations` for existing entities
- Create relationships between entities

## Phase 3: Double Compact

1. First compact - reduce by ~50%
2. Verify memory saved correctly
3. Second compact - minimal working context

## Output

```
=== SUPER COMPRESS COMPLETE ===

EXTRACTED:
- N decisions (saved)
- N code changes (saved)
- N bugs fixed (saved)
- N discoveries (saved)

MEMORY WRITES:
✓ Created "Session YYYY-MM-DD: [topic]"
✓ Added N observations to existing entities

Ready to continue. All context saved to memory.
```
