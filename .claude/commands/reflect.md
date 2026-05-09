---
description: Review and curate the project's memory graph
---

# Reflect on Memory

Review and curate the project's knowledge graph stored in the memory MCP.

## Process

1. **Load Memory**: Call `mcp__memory__read_graph` to get all entities
2. **Display Summary**: Show each entity with observation count
3. **Cross-Check**:
   - Run `git log --oneline -10` to see recent work
   - Check if referenced files still exist
   - Verify dates are current (we're in Dec 2025)
4. **Identify Issues**:
   - Outdated info (wrong dates, old versions)
   - Contradictions between entities
   - Vague claims lacking specifics
   - Missing "why" rationale
5. **Propose Actions**:
   - DELETE: Remove outdated entities
   - UPDATE: Fix incorrect observations
   - ADD: Create missing entities/observations
6. **Execute**: Apply approved changes via MCP tools

## Output Format

```
=== MEMORY REFLECTION ===

ENTITIES (N total):
1. [Entity Name] (Type) - N observations
   ✓ Current | ⚠ Stale | ✗ Outdated

ISSUES FOUND:
- [Entity]: Issue description
  → Recommended action

PROPOSED CHANGES:
□ Delete "Old Entity"
□ Update "Entity X" observation about...

Approve changes? [y/n/selective]
```
