---
name: warn-memory-deletion
enabled: true
event: stop
action: warn
conditions:
  - field: transcript
    operator: contains
    pattern: mcp__memory__delete
---

**Memory was deleted this session!**

You called a memory deletion function during this session. Before stopping:

1. **Was this intentional?** Verify the deletion was user-requested
2. **Document what was removed** - Note in your response what was deleted and why
3. **Consider if you should restore** - If accidental, you may need to recreate the entity

This is a post-hoc check since MCP calls cannot be intercepted before execution.
