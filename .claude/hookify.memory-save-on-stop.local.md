---
name: require-memory-save-on-stop
enabled: true
event: stop
action: block
conditions:
  - field: transcript
    operator: not_contains
    pattern: mcp__memory__add_observations|mcp__memory__create_entities
---

**Memory not saved before stopping!**

You haven't saved any learnings to memory this session. Before ending:

1. **Review what was accomplished** - What decisions were made? What was learned?
2. **Save to memory** using:
   - `mcp__memory__add_observations` - Add insights to existing entities
   - `mcp__memory__create_entities` - Create new knowledge entities

This ensures continuity between Claude sessions on this project.

**Bypass:** If this session truly had nothing worth remembering, acknowledge that explicitly.
