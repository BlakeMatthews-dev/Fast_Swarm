---
description: Execute all pending todos using parallel Task agents with TDD+EDD quality gates
---

# Todo Loop (Parallel + TDD+EDD)

Spawns up to 5 concurrent agents for non-conflicting tasks. Tests must exist and pass. Gatekeeper reviews quality.

## Usage

```
/todo-loop
```

## What It Does

1. **SYNTHESIZE** - Reads plan/context/conversation, generates detailed todo list
2. **INITIALIZE** - Reads state files, finds pending tasks
3. **ANALYZE** - Detects file scopes per task (regex + haiku fallback)
4. **BATCH** - Finds non-conflicting tasks safe to parallelize
5. **SPAWN** - Launches background agents with TDD+EDD protocol
6. **GATE** - Tests must exist, pass, and survive Gatekeeper review
7. **LOOP** - Poll, update, repeat until done

## Agent Labeling

Tasks get claimed with `[@TASK_ID]` labels. No two agents touch the same task.

## See Also

- Full docs: `.claude/skills/todo-loop/SKILL.md`
- Quick mode (no tests): `/todo-loop-quick`
- State file: `.claude/parallel-todo-state.md`
- Shared context: `.claude/shared-context.md`
