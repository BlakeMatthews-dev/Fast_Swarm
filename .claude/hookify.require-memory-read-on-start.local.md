---
name: require-memory-read-on-start
enabled: true
event: stop
action: block
conditions:
  - field: transcript
    operator: not_contains
    pattern: mcp__memory__read_graph|mcp__memory__search_nodes|mcp__memory__open_nodes
---

**Memory not loaded at session start!**

You haven't read from the memory graph this session. This means you're working without project context.

Before continuing, you should have:
1. Called `mcp__memory__search_nodes` with query 'Coinswarm' to load context
2. Or called `mcp__memory__read_graph` to see all entities
3. Or called `mcp__memory__open_nodes` to load specific entities

**Why this matters:** Without loading memory, you may:
- Repeat decisions already made
- Miss important architectural context
- Contradict established patterns

**Bypass:** If this is a trivial task that truly doesn't need context, acknowledge that explicitly.
