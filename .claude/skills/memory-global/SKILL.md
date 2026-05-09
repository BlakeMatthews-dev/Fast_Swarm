# Global Memory

View and manage cross-project Claude knowledge.

## Concept: Two-Level Memory

```
~/.claude/                      # GLOBAL (cross-project)
├── global-memory.json          # Via entity naming convention
└── settings.json               # Global hooks

<project>/.claude/              # PROJECT-SPECIFIC
├── local settings              # Project hooks
└── memory via MCP              # Project knowledge
```

## What Goes Where?

| Level | Contains | Examples |
|-------|----------|----------|
| **Global** | Cross-project knowledge | Best practices, user preferences, common patterns |
| **Project** | Project-specific context | Architecture decisions, bug fixes, file purposes |

### Global Memory Examples
- "User Preferences": "Prefers concise responses, uses Windows, likes TypeScript"
- "Common Patterns": "Always run tests before commit, use conventional commits"
- "Cross-Project Learnings": "PostgreSQL better than SQLite for >1M rows"

### Project Memory Examples
- "Coinswarm Architecture": "7-layer hierarchy, PostgreSQL primary..."
- "Committee System": "Weighted voting, 3-coach quorum..."
- "Recent Bug Fix": "Trailing stop percentage was inverted..."

## Implementation

Since MCP memory server uses a single file, we use **naming convention**:

```
[GLOBAL] User Preferences           # Global entity
[GLOBAL] Common Patterns            # Global entity
Coinswarm Current Architecture      # Project entity (no prefix)
Position Management System          # Project entity (no prefix)
```

## Commands

```
/memory-global                      # Show all global memories
/memory-global search <query>       # Search global only
/memory-global add <entity>         # Create global entity
/memory-global promote <entity>     # Move project entity to global
/memory-global demote <entity>      # Move global to project-specific
```

## Output Format

```
=== GLOBAL MEMORY ===

ENTITIES (3 global):

1. [GLOBAL] User Preferences
   - "Prefers concise responses over verbose explanations"
   - "Uses Windows with WSL for development"
   - "Favors TypeScript over JavaScript"

2. [GLOBAL] Common Patterns
   - "Always run tests before committing"
   - "Use conventional commit format"
   - "Prefer composition over inheritance"

3. [GLOBAL] Cross-Project Learnings
   - "PostgreSQL scales better than SQLite for >1M rows"
   - "Cloudflare Workers have 128MB memory limit"
   - "Always use parameterized SQL queries"

Actions:
[A]dd to global | [P]romote from project | [D]emote to project | [S]earch
```

## When to Promote to Global

Promote when:
- Pattern works across multiple projects
- User preference (not project-specific)
- General best practice discovered
- Tool/framework knowledge applicable everywhere

```
/memory-global promote "PostgreSQL Performance Tips"

Converting "PostgreSQL Performance Tips" to global...
New name: [GLOBAL] PostgreSQL Performance Tips
✓ Promoted successfully
```

## When to Use

- Start of new project (load global knowledge)
- End of project (promote learnings)
- When making decisions that apply broadly
- Periodic review of cross-project patterns
