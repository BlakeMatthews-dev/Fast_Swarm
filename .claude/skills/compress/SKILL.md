# Super Compress

An extremely thorough context extraction followed by double compaction. Nothing is lost.

## What This Skill Does

This is the "nuclear option" for context management. It extracts EVERYTHING valuable from the current conversation context, saves it to memory, then performs aggressive double compaction.

### Phase 1: Deep Extraction (Before Any Compaction)

Extract EVERYTHING valuable from current context:

1. **Decisions Made**
   - What was decided
   - Why (full rationale with alternatives considered)
   - Who/what influenced the decision
   - Any tradeoffs accepted

2. **Code Changes**
   - Files modified and why
   - Key functions added/changed
   - Patterns established
   - Architecture decisions embedded in code

3. **Errors & Debugging**
   - What broke
   - Root cause analysis
   - How it was fixed
   - Prevention strategies learned

4. **Discoveries**
   - Codebase insights
   - Architecture learnings
   - "Aha" moments
   - Hidden dependencies found

5. **Open Questions**
   - Unresolved issues
   - Things to investigate later
   - Blocked items and why
   - Assumptions that need validation

6. **Context for Next Session**
   - What we were working on
   - Where we left off exactly
   - Next steps planned
   - Files that were open/relevant

### Phase 2: Save to Memory

Use MCP memory tools to persist everything:
- Create new entities for major topics discovered
- Add detailed observations with evidence
- Create relationships between entities
- Tag observations with timestamps

### Phase 3: Double Compact

1. First compact - reduce context by ~50%
2. Verify memory was saved correctly (read back key items)
3. Second compact - reduce to minimal working context

## When to Use

- Context getting very long (>50k tokens)
- Before switching to a completely different task
- End of major feature work
- When you want a "fresh start" but keep all learnings
- Before ending a long session

## Output

After compression:
```
=== SUPER COMPRESS COMPLETE ===

EXTRACTED:
- 3 decisions (saved to Decision entities)
- 5 code changes (saved to Session Log)
- 2 bugs fixed (saved to Bug Fix entities)
- 4 discoveries (saved to Architecture entity)
- 2 open questions (saved to Open Questions)

MEMORY WRITES:
✓ Created "Session 2025-12-30: Memory System Implementation"
✓ Added 8 observations to existing entities
✓ Created 2 new relationships

COMPACTION:
- Before: ~75k tokens
- After first compact: ~35k tokens
- After second compact: ~15k tokens

CONTEXT PRESERVED:
- Working on: Memory management system implementation
- Last completed: settings.json hooks
- Next: Create skill files
- Key files: .claude/settings.json, .claude/skills/

Ready to continue. All context saved to memory.
```

## Process

1. **Announce**: "Starting super compress - extracting all context..."
2. **Extract**: Go through conversation systematically
3. **Categorize**: Sort into the 6 categories above
4. **Save**: Use mcp__memory__* tools to persist
5. **Verify**: Read back critical items
6. **Compact**: Request compaction (user may need to trigger)
7. **Summarize**: Show what was saved and new context size
