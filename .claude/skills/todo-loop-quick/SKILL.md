# Parallel Todo Loop (Quick)

Execute all pending todos by spawning up to 5 concurrent Task agents. No test gates, no Gatekeeper. Just parallel execution with file locking.

## First Invocation: SYNTHESIZE

Same as the TDD+EDD version - read context, plan, conversation and generate a detailed todo list in shared-todos.md before spawning agents.

---

## Algorithm

Same as the TDD+EDD version (.claude/skills/todo-loop/SKILL.md) with these differences:

1. **Skip STEP 7** entirely (no test gate, no gatekeeper)
2. **Agent prompt** uses the QUICK AGENT PROMPT below (no TDD requirements)
3. When an agent completes, mark done immediately (no quality review)

Everything else is identical: file locking, parallel scheduling, agent labeling, progress logs.

## Completion Signal

When ALL tasks are `[x]` and no agents running, display a BIG celebratory message with personality. Vary it each time but follow this vibe:

```
===============================================================
    SPEED RUN COMPLETE. NO BRAKES. ALL GREEN.
===============================================================

    [N] tasks OBLITERATED by [M] parallel agents
    Quick mode = pure velocity. Zero friction.

    Time: [duration] - that's [X] tasks per minute.

    The swarm doesn't sleep. The swarm delivers.
===============================================================
```

Be creative - reference the specific work, throw in relevant flavor. Keep it ASCII-safe (no emoji/unicode). Make it feel like a speedrun achievement.

Then use AskUserQuestion: "The swarm blitzed through everything! What's next?"
- Option 1: "Run again" (re-synthesize and keep going)
- Option 2: "New tasks" (fresh work incoming)
- Option 3: "We're done here" (end session gracefully)

---

## QUICK AGENT PROMPT

```
===============================================================
PARALLEL TODO AGENT - QUICK MODE
===============================================================

YOUR TASK:
{TASK_TEXT}

TASK ID: {TASK_ID}

YOUR LABEL: [@{TASK_ID}] - this is YOUR claim on the task in shared-todos.md.
Other tasks labeled with different IDs are OFF LIMITS.

===============================================================
COORDINATION FILES
===============================================================

1. YOUR PROGRESS LOG (create immediately):
   c:\fast_swarm\.claude\agent-progress\{TASK_ID}.md

2. SHARED TODO LIST (your task is labeled [@{TASK_ID}]):
   c:\fast_swarm\.claude\shared-todos.md

3. SHARED CONTEXT (read first, append when done):
   c:\fast_swarm\.claude\shared-context.md

4. STATE FILE (read-only, see locks):
   c:\fast_swarm\.claude\parallel-todo-state.md

===============================================================
PROTOCOL
===============================================================

ON START:
1. Read shared-context.md for prior discoveries
2. Read parallel-todo-state.md for locked files
3. Create progress log with Status: IN_PROGRESS

WHILE WORKING:
4. Update progress log as you go
5. Add files to "Files Modified" as you edit them

ON COMPLETION:
6. Update progress log: Status: COMPLETED
7. Change your task in shared-todos.md from [@{TASK_ID}] to [x][@{TASK_ID}]
8. Append discoveries to shared-context.md

ON ERROR:
9. Update progress log: Status: FAILED
10. Change label back to [ ] in shared-todos.md
11. Log warning in shared-context.md

===============================================================
CONTEXT FROM OTHER AGENTS
===============================================================

{SHARED_CONTEXT_CONTENTS}

===============================================================
RULES
===============================================================

- Work autonomously - do not ask questions
- Complete the task fully before marking done
- ONLY modify files in your scope (check locked files!)
- ONLY touch tasks labeled [@{TASK_ID}] (yours)
- Plain ASCII only (Windows cp1252)
- Read CLAUDE.md at project root before starting
```
