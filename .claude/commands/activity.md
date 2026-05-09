---
description: Show what other Claude instances have been doing
---

# Activity Log

Show multi-instance Claude activity for coordination.

## Process

1. Read `.claude/activity.jsonl`
2. Parse recent activity (last 1 hour)
3. Show:
   - Active sessions (START without END)
   - Files being edited (INTENT without DONE)
   - Completed work summaries
   - Potential conflicts

## Event Types

| Type | Meaning |
|------|---------|
| START | Session began |
| INTENT | About to edit file |
| DONE | Finished editing file |
| END | Session ended |

## Output Format

```
=== ACTIVITY LOG ===
Last 1 hour | N sessions

ACTIVE SESSIONS:
🟢 Session [id] (started X min ago)
   Currently editing: [file] (INTENT Y min ago)

FILES IN PROGRESS:
⚠️ [file] - Session [id] (Y min ago)
   → Avoid editing until DONE logged

RECENT EDITS:
- HH:MM [file] ([session]) - [description]

CONFLICTS: None | ⚠️ [details]
```
