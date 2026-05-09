---
name: require-significant-edit-memory
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: \.(ts|tsx|py|sql|md)$
  - field: new_text
    operator: regex_match
    pattern: (TODO|FIXME|HACK|XXX|BREAKING|DEPRECATED|@deprecated)
---

**Significant code marker detected!**

You've added a TODO, FIXME, HACK, or deprecation marker. Consider capturing this in memory:

1. **What's the issue?** Document the problem being deferred
2. **Why not fix now?** Record the blocking reason
3. **What's the plan?** Note the intended resolution

Use `mcp__memory__add_observations` to add this to a relevant entity (or create one).

This helps future sessions understand pending work and technical debt.
