# Memory Q&A (Clarification Session)

Claude reviews memories and asks YOU for clarifications on things that are unclear, outdated, or potentially wrong.

## What This Skill Does

This is a **reverse Q&A** - instead of you asking Claude questions, Claude asks YOU questions to improve memory quality.

1. Reads all memory entities
2. Identifies fuzzy/uncertain items:
   - Observations that seem contradictory
   - Old info that may be stale
   - Vague statements lacking specifics
   - Missing context or rationale
   - Claims without evidence
3. Asks YOU targeted questions to clarify
4. Updates memory with your answers

## Example Questions Claude Might Ask

- "Memory says 'chose PostgreSQL for performance' - what specific performance issue drove this decision?"
- "The committee quorum is mentioned but I'm unclear - is it 3 coaches or 3 agents per coach?"
- "Memory mentions trailing stops but not the specific percentages - what are they?"
- "There's a note about 'V3 being dormant' - is this still true? Should we delete V3 references?"
- "I see 'position management with scale-out' - what are the scale-out thresholds?"
- "The 7-layer hierarchy mentions 'Coaches/Planners under selection pressure' - how exactly are coaches selected/culled?"

## Process

1. **Load Memory**: Call `mcp__memory__read_graph`
2. **Analyze Each Entity** for:
   - **Vagueness**: Lacks specifics (numbers, names, files)
   - **Staleness**: Old timestamps, outdated references
   - **Contradictions**: Conflicts with other memories
   - **Missing "why"**: Facts without rationale
   - **No evidence**: Claims without proof
3. **Prioritize Questions**: Most important/impactful first
4. **Present Questions**: One at a time with context
5. **Capture Answers**: User responds
6. **Update Memory**: Add clarified observations
7. **Mark as Clarified**: Add timestamp to show when verified

## Output Format

```
=== MEMORY Q&A SESSION ===

I found 5 items that need clarification. Let me ask about each:

QUESTION 1/5:
Memory: "Committee uses weighted voting"
Issue: Missing details - what are the weights? How computed?
Question: What determines a coach's voting weight in the committee?

[User answers]

✓ Updated: Added "Voting weights based on recent performance..."

QUESTION 2/5:
...

=== SESSION COMPLETE ===
Clarified: 5 items
Memory reliability improved from 0.65 → 0.82
```

## When to Use

- After `/reflect` shows issues
- When Claude seems confused about project details
- Periodically (weekly) for maintenance
- After major changes to the project
- When starting work in an unfamiliar area of the codebase

## Question Categories

| Category | Trigger | Example Question |
|----------|---------|------------------|
| Missing numbers | Vague quantities | "What's the exact threshold?" |
| Missing rationale | No "why" | "Why was X chosen over Y?" |
| Outdated refs | Old dates/versions | "Is this still accurate?" |
| Contradictions | Conflicting claims | "Which is correct: A or B?" |
| Missing files | References without paths | "Where is this implemented?" |
| Jargon | Project-specific terms | "What exactly is a 'coach' in this system?" |
