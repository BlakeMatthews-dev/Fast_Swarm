# Reflect on Memory

Review and curate the project's knowledge graph stored in the memory MCP.

## What This Skill Does

1. Reads the entire memory graph using `mcp__memory__read_graph`
2. Shows a summary of all entities and their observations
3. Identifies potential issues:
   - Outdated information (references to old dates/versions)
   - Contradictions between entities
   - Missing relationships
   - Vague claims lacking specifics
4. Cross-references with current codebase state (git log, key files)
5. Offers to update/delete/add based on findings

## When to Use

- After major refactoring
- When memory seems stale or inaccurate
- Periodic maintenance (weekly recommended)
- After significant architectural changes
- When Claude seems confused about project state

## Process

1. **Load Memory**: Call `mcp__memory__read_graph` to get all entities
2. **Display Summary**: Show each entity with observation count and types
3. **Cross-Check**:
   - Run `git log --oneline -10` to see recent work
   - Check key files mentioned in memory still exist
   - Verify dates and versions are current
4. **Identify Issues**:
   - Mark outdated (wrong dates, old versions)
   - Mark contradictions (conflicting observations)
   - Mark incomplete (missing "why" or evidence)
5. **Propose Actions**:
   - DELETE: Remove outdated entities
   - UPDATE: Modify incorrect observations
   - ADD: Create missing entities/observations
   - RELATE: Add relationships between entities
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
□ Add observation to "Entity Y"

Approve changes? [y/n/selective]
```

## Example Usage

```
/reflect

Claude will:
1. Load all 7 memory entities
2. Check git log for recent activity
3. Verify "Dec 2025" dates are current
4. Cross-check PostgreSQL/Python claims against codebase
5. Report any stale V3 Cloudflare references
6. Propose cleanup actions
```
