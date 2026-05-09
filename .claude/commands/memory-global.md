---
description: Manage cross-project global knowledge
---

# Global Memory

View and manage cross-project Claude knowledge.

## Concept

Two levels of memory via naming convention:
- `[GLOBAL] Entity Name` - Cross-project knowledge
- `Entity Name` (no prefix) - Project-specific

## Global Memory Examples

- `[GLOBAL] User Preferences` - Response style, tools, environment
- `[GLOBAL] Common Patterns` - Best practices across projects
- `[GLOBAL] Cross-Project Learnings` - Reusable insights

## Commands

- Show all global: Filter entities starting with `[GLOBAL]`
- Promote: Add `[GLOBAL]` prefix to project entity
- Demote: Remove `[GLOBAL]` prefix

## Output Format

```
=== GLOBAL MEMORY ===

ENTITIES (N global):

1. [GLOBAL] User Preferences
   - "[observation 1]"
   - "[observation 2]"

2. [GLOBAL] Common Patterns
   - "[observation]"

Actions: [A]dd global | [P]romote from project | [D]emote
```
