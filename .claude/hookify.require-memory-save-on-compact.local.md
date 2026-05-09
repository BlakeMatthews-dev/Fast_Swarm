---
name: require-memory-save-on-compact
enabled: true
event: stop
action: warn
conditions:
  - field: transcript
    operator: regex_match
    pattern: context.*(compact|summariz)|PreCompact|running low on context
---

**Context compaction detected - save to memory!**

The conversation is being compacted and older messages will be lost.

Before continuing, IMMEDIATELY save critical context:

1. **KEY DECISIONS**: What was decided and WHY
2. **ERRORS & FIXES**: What broke and how it was fixed
3. **ARCHITECTURAL INSIGHTS**: Patterns or learnings discovered
4. **OPEN QUESTIONS**: Unresolved issues
5. **NEXT STEPS**: What we were working on

Use these tools NOW:
- `mcp__memory__add_observations` - Add to existing entities
- `mcp__memory__create_entities` - Create new knowledge entities

**This is your last chance to save this context before it's lost!**
