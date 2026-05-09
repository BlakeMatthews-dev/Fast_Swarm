---
description: Execute all pending todos using parallel Task agents (no test gates)
---

# Todo Loop Quick

Same parallel orchestrator as `/todo-loop` but skips TDD+EDD gates. No test requirements, no Gatekeeper. Just fast parallel execution with file locking.

## Usage

```
/todo-loop-quick
```

## Differences from /todo-loop

| Feature | /todo-loop | /todo-loop-quick |
|---------|-----------|-----------------|
| Parallel agents | Yes (up to 5) | Yes (up to 5) |
| File locking | Yes | Yes |
| Agent labeling | Yes | Yes |
| Tests required | Yes | No |
| Gatekeeper review | Yes | No |
| Progress logs | Yes | Yes |

## When to Use

- Rapid prototyping or exploration
- Non-critical tasks (docs, config, cleanup)
- When you want speed over quality assurance

## See Also

- Full docs: `.claude/skills/todo-loop-quick/SKILL.md`
- TDD+EDD mode: `/todo-loop`
