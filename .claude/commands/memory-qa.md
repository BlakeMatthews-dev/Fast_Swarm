---
description: Claude asks YOU to clarify fuzzy or uncertain memories
---

# Memory Q&A

Reverse Q&A session - Claude asks YOU questions to improve memory quality.

## Process

1. **Load Memory**: `mcp__memory__read_graph`
2. **Analyze** each observation for:
   - Vagueness (lacks specifics like numbers, file paths)
   - Staleness (old dates, outdated references)
   - Contradictions (conflicts with other memories)
   - Missing "why" (facts without rationale)
3. **Ask Questions** - One at a time, most important first
4. **Update Memory** with your answers

## Example Questions

- "Memory says 'chose PostgreSQL for performance' - what specific performance issue?"
- "Committee quorum is mentioned but unclear - is it 3 coaches or 3 agents?"
- "Memory mentions trailing stops but not percentages - what are they?"
- "V3 is marked dormant - should we delete V3 references entirely?"

## Output Format

```
=== MEMORY Q&A SESSION ===

QUESTION 1/N:
Memory: "[observation text]"
Issue: [why it's unclear]
Question: [specific question for you]

[You answer]

✓ Updated: Added "[new observation]"

...continue for each fuzzy item...

=== SESSION COMPLETE ===
Clarified: N items
```
