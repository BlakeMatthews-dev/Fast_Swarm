---
name: warn-interclaude-conflict
enabled: false
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: \.(ts|tsx|py|sql|json|md)$
---

**Inter-Claude Coordination Check**

Before editing this file, verify no other Claude session is working on it:

1. Check `.claude/activity.jsonl` for active sessions
2. Look for SESSION_START without matching SESSION_END
3. If another session is editing this file, coordinate or choose a different file

**Quick check command:**
```bash
grep -l "SESSION_START" .claude/activity.jsonl | tail -5
```

If you're the only active session, proceed with the edit.
