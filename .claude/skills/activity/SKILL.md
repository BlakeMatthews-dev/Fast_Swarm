# Activity Log

Show what all Claude instances have been doing. Essential for multi-instance coordination.

## What This Skill Does

1. Reads `.claude/activity.jsonl`
2. Parses and displays recent activity (last 1 hour by default)
3. Shows active sessions (START without END)
4. Shows files currently being edited (INTENT without DONE)
5. Highlights potential conflicts
6. Shows completed work summaries

## Activity Log Format

The activity log uses JSONL (one JSON object per line):

```jsonl
{"ts": "2025-12-30T14:23:00Z", "session": "abc123", "type": "START", "scope": "trading/*.py"}
{"ts": "2025-12-30T14:23:05Z", "session": "abc123", "type": "INTENT", "file": "position_manager.py"}
{"ts": "2025-12-30T14:23:30Z", "session": "abc123", "type": "DONE", "file": "position_manager.py", "desc": "Added trailing stops"}
{"ts": "2025-12-30T14:25:00Z", "session": "abc123", "type": "END", "summary": "Improved position management"}
```

## Event Types

| Type | Meaning | When Logged |
|------|---------|-------------|
| `START` | Session began | SessionStart hook |
| `INTENT` | About to edit file | PreToolUse hook (Edit/Write) |
| `DONE` | Finished editing file | PostToolUse hook (Edit/Write) |
| `END` | Session ended | Stop hook |

## Output Format

```
=== ACTIVITY LOG ===
Last 1 hour | 3 sessions found

ACTIVE SESSIONS:
🟢 Session abc123 (started 15 min ago)
   Scope: trading/*.py
   Currently editing: position_manager.py (INTENT 2 min ago)

🟢 Session def456 (started 45 min ago)
   Scope: dashboard/
   No active edits

COMPLETED SESSIONS:
⚫ Session ghi789 (ended 30 min ago)
   Summary: Fixed committee voting quorum bug
   Files touched: committee.py, voting.py

FILES IN PROGRESS:
⚠️ position_manager.py - Session abc123 (2 min ago)
   → Avoid editing this file until DONE logged

RECENT EDITS:
- 14:23 committee.py (ghi789) - Fixed quorum calculation
- 14:15 voting.py (ghi789) - Added weight validation
- 14:10 dashboard.py (def456) - Updated metrics display

NO CONFLICTS DETECTED ✓
```

## Conflict Detection

A conflict exists when:
- Two sessions have INTENT on same file within 5 minutes
- INTENT exists without DONE for >10 minutes (stale lock)

```
⚠️ CONFLICT WARNING:
position_manager.py has INTENT from:
  - Session abc123 (2 min ago) ← ACTIVE
  - Session xyz999 (3 min ago) ← POTENTIAL CONFLICT

Recommendation: Coordinate with other session before editing
```

## Arguments

```
/activity              # Last 1 hour
/activity --hours 4    # Last 4 hours
/activity --session abc123  # Specific session
/activity --file position_manager.py  # Activity on specific file
/activity --conflicts  # Only show conflicts
```

## When to Use

- Start of session to see what others are doing
- Before editing a file to check for locks
- To find who made recent changes
- To coordinate parallel work
- Debug "who changed what" questions
