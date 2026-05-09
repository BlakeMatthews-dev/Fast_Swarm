# Parallel Todo Loop (TDD+EDD)

Execute all pending todos by spawning up to 5 concurrent Task agents for non-conflicting work. Tests must exist and pass. Gatekeeper reviews quality.

## First Invocation: SYNTHESIZE

The FIRST thing this skill does on invocation is synthesize context into a detailed todo list. Read the plan file, recent conversation, and any existing todos - then generate an epically detailed breakdown in shared-todos.md.

---

## Coordination Files (Absolute Paths)

| File | Purpose |
|------|---------|
| `c:\fast_swarm\.claude\shared-todos.md` | Master task list with agent labeling |
| `c:\fast_swarm\.claude\shared-context.md` | Shared discoveries, warnings, request tracker |
| `c:\fast_swarm\.claude\parallel-todo-state.md` | Runtime state: running agents, locks, config |
| `c:\fast_swarm\.claude\agent-progress\<TASK_ID>.md` | Per-agent progress logs |

---

## Agent Labeling Protocol

Tasks in shared-todos.md use this format:
- `- [ ]` = Unclaimed, available
- `- [@TASK_ID]` = Claimed by agent TASK_ID (in progress)
- `- [x]` = Completed
- `- [x][@TASK_ID]` = Completed by specific agent
- `- [!]` = BLOCKED - needs human intervention

When an agent claims a task, it changes `[ ]` to `[@its-task-id]`.
Other agents MUST NOT touch tasks labeled with another agent's ID.
The orchestrator enforces this via file locks AND label checking.

---

## Algorithm

### STEP 0 - SYNTHESIZE (First Invocation Only)

On first invocation, before any agents are spawned:

1. Read the plan file (if one exists in `C:\Users\Admin\.claude\plans\`)
2. Review recent conversation context and decisions
3. Read current `.claude/shared-todos.md`
4. Generate a detailed, hierarchical todo list that captures ALL work needed:
   - Break high-level goals into atomic, actionable tasks
   - Group by domain/module (trading, patterns, agents, etc.)
   - Each task should be completable by a single agent in one session
   - Include file paths where known
   - Include test requirements for each task
5. Write the synthesized list to `.claude/shared-todos.md` under `## Active Todos`
6. Proceed to STEP 1

### STEP 1 - INITIALIZE

1. Read `.claude/shared-todos.md` - find all `- [ ]` tasks
2. Read `.claude/parallel-todo-state.md` - check for resumed agents
3. Read `.claude/shared-context.md` - load shared context
4. Note `MAX_PARALLEL` from config (default 5)

### STEP 2 - CHECK RUNNING AGENTS

For each agent in the state file's "Running Agents" table:

1. Use `Read` tool to check the agent's output file path
2. If output shows the agent has completed:
   - Read the agent's progress log at `agent-progress/<TASK_ID>.md`
   - Run TDD+EDD gate (STEP 7) BEFORE marking done
   - If gate passed:
     - Change task label from `[@TASK_ID]` to `[x][@TASK_ID]` in shared-todos.md
     - Remove from Running Agents table
     - Add to Completed This Session table
     - Append discoveries to shared-context.md
   - If gate FAILED:
     - Change label back from `[@TASK_ID]` to `[ ]`
     - Append "[NEEDS TESTS]" to the task line
     - Remove from Running Agents, release locks
     - Log failure in shared-context.md Warnings
3. If output shows error or agent failed:
   - Log error in shared-context.md under Warnings
   - Change label back to `[ ]`
   - Remove from Running Agents, release locks
   - Increment retry count (if retry_limit exceeded, change to `[!]`)

### STEP 3 - ANALYZE PENDING TASKS (Hybrid File Scope Detection)

For each pending `- [ ]` task (skipping `[!]` tasks):

**Fast path (regex):**
- Check if task contains explicit file paths
- Map module keywords to directories:
  - "trading" -> `src/Fast_Swarm/Trading/`
  - "pattern" -> `src/Fast_Swarm/Patterns/`
  - "agent" -> `src/Fast_Swarm/Agents/`
  - "infrastructure" -> `src/Fast_Swarm/Infrastructure/`
  - "system" -> `src/Fast_Swarm/System/`
  - "backtest" -> `src/Fast_Swarm/Backtest/`, `src/Fast_Swarm/local_agents/backtest/`
  - "exchange" -> `src/Fast_Swarm/exchanges/`
  - "dashboard" -> `src/Fast_Swarm/Dashboard/`, `Dashboard/`
  - "metric" -> `src/Fast_Swarm/Metrics/`
  - "database" -> `src/Fast_Swarm/Database.py`
  - "main" -> `src/Fast_Swarm/Main.py`
  - "skill/command/hook" -> `.claude/`

**Smart path (haiku fallback):**
- If regex finds nothing, spawn a haiku-model Task agent to identify files
- Store predicted file set per task

### STEP 4 - DETERMINE NON-CONFLICTING BATCH

1. Get currently locked files from Running Agents table
2. For each pending task (in order):
   - If predicted_files INTERSECTS locked_files -> SKIP
   - If no conflict AND running_count < MAX_PARALLEL -> QUEUE for spawn
   - Add task's predicted files to locked_files
3. Result: batch of tasks safe to run in parallel

### STEP 5 - SPAWN AGENTS

For each task in the batch:

1. Generate TASK_ID (8-char hash of task text)
2. Update shared-todos.md: change `- [ ]` to `- [@TASK_ID]` for this task
3. Spawn Task agent with `run_in_background: true`, `subagent_type: 'general-purpose'`
4. Use the TDD+EDD AGENT PROMPT template (below)
5. Record in parallel-todo-state.md Running Agents table

### STEP 6 - WAIT AND LOOP

1. If running agents > 0: wait ~15 seconds
2. If ALL tasks are `[x]`: output completion and stop
3. Otherwise: go to STEP 2

### STEP 7 - TDD+EDD GATE

When an agent reports completion:

1. Read its progress log for modified files
2. For each modified source file, verify test file exists:
   - `src/Fast_Swarm/X/Services/foo.py` -> `Tests/Unit/X/test_foo.py`
   - `src/Fast_Swarm/X/foo.py` -> `Tests/Unit/X/test_foo.py`
   - `src/Fast_Swarm/foo.py` -> `Tests/Unit/test_foo.py`
3. Run pytest on found test files
4. If tests missing or failing: FAIL
5. If tests pass: spawn GATEKEEPER AGENT to review quality
6. If Gatekeeper APPROVED: pass
7. If Gatekeeper REJECTED: fail (after 2 rejections, mark task `[!]`)

---

## PROMPT TEMPLATES

---

### TDD+EDD AGENT PROMPT

```
===============================================================
PARALLEL TODO AGENT - TDD+EDD MODE
===============================================================

YOUR TASK:
{TASK_TEXT}

TASK ID: {TASK_ID}

YOUR LABEL: [@{TASK_ID}] - this is YOUR claim on the task in shared-todos.md.
Other tasks labeled with different IDs are OFF LIMITS.

===============================================================
TDD+EDD REQUIREMENTS
===============================================================

WORKFLOW (strict order):
1. Write tests FIRST that define expected behavior
2. Implement the feature/fix to make tests pass
3. Verify all tests pass before marking complete

TEST LOCATIONS:
- Tests/Unit/<Domain>/test_<filename>.py (unit tests)
- Tests/Soundness/<Domain>/test_<filename>.py (EDD evidence)

EDD EVIDENCE (include where applicable):
a) DETERMINISM - same inputs -> same outputs (call twice, compare)
b) DIVISION SAFETY - zero/empty inputs don't crash
c) BOUNDARY CONDITIONS - edge cases handled (min/max, empty, negative)
d) STATISTICAL SANITY - outputs in reasonable ranges
e) ECONOMIC VALIDITY - no impossible trading results

WHAT GETS REJECTED:
- Excessive mock.patch hiding real logic
- assert True, assert x is not None, assert len(x) >= 0
- Tests that pass regardless of implementation
- Missing EDD evidence for metrics/trading code

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

TDD WORKFLOW:
4. Write test file FIRST
5. Implement to make tests pass
6. Run: python -m pytest <test_file> -v
7. Fix failures until green

ON COMPLETION:
8. Update progress log: Status: COMPLETED, all files listed
9. Change your task in shared-todos.md from [@{TASK_ID}] to [x][@{TASK_ID}]
10. Append discoveries to shared-context.md

ON ERROR:
11. Update progress log: Status: FAILED
12. Change label back to [ ] in shared-todos.md
13. Log warning in shared-context.md

===============================================================
CONTEXT FROM OTHER AGENTS
===============================================================

{SHARED_CONTEXT_CONTENTS}

===============================================================
RULES
===============================================================

- Work autonomously - do not ask questions
- TESTS FIRST - always
- ONLY modify files in your scope (check locked files!)
- ONLY touch tasks labeled [@{TASK_ID}] (yours)
- Plain ASCII only (Windows cp1252)
- Read CLAUDE.md at project root before starting
```

---

### GATEKEEPER AGENT PROMPT

```
===============================================================
TEST QUALITY GATEKEEPER
===============================================================

Review test quality for task {TASK_ID}. REJECT sham tests.

TASK: {TASK_TEXT}
FILES MODIFIED: {MODIFIED_FILES_LIST}
TEST FILES: {TEST_FILES_LIST}

===============================================================
CHECKS (all required)
===============================================================

1. MOCK ABUSE
   - > 50% functions using mocks = SUSPICIOUS
   - Mocking the function under test = REJECT
   - Mocking external I/O only = ACCEPTABLE

2. TRIVIAL ASSERTIONS (auto-reject if found)
   - assert True / assert x is not None / assert len(x) >= 0
   - assert isinstance(x, object) / assert x == x
   - Anything that CANNOT FAIL

3. EDD EVIDENCE (required for metrics/trading/backtest)
   a) Determinism: PRESENT | MISSING
   b) Division Safety: PRESENT | MISSING | N/A
   c) Boundary Conditions: PRESENT | MISSING
   d) Statistical Sanity: PRESENT | MISSING | N/A
   e) Economic Validity: PRESENT | MISSING | N/A

4. COVERAGE
   - Happy path: YES | NO
   - Error path: YES | NO
   - Edge cases: YES | NO

===============================================================
OUTPUT
===============================================================

Write to: c:\fast_swarm\.claude\agent-progress\{TASK_ID}-gatekeeper.md

Format:
# Gatekeeper Review: {TASK_ID}
## Verdict: APPROVED | REJECTED
## Issues Found
[list or "None"]
## Recommendations
[fixes needed if REJECTED]

===============================================================
RULES
===============================================================

- Read BOTH test files AND source files
- Be strict but fair
- A test that can never fail is worse than no test
- Plain ASCII only (Windows cp1252)
```

---

### HAIKU FILE ANALYZER PROMPT

```
Analyze this task for a Python FastAPI codebase at c:\fast_swarm.
Task: "{TASK_TEXT}"

Structure:
- src/Fast_Swarm/ (Agents/, Patterns/, Trading/, Infrastructure/, System/, Backtest/, Metrics/, exchanges/, Dashboard/)
- Tests/ (Unit/, Soundness/, Triage/)
- .claude/ (skills, commands, scripts)

Which files would be WRITTEN TO? Return JSON array of absolute paths.
Be conservative. Include test files if applicable.
```

---

## Completion Signal

When ALL tasks in shared-todos.md are `[x]` and no agents running:

1. Count total tasks completed and agents spawned
2. Display a BIG celebratory success message with personality. Be creative and vary it each time, but follow this vibe:

```
===============================================================
    THE SWARM HAS SPOKEN. VICTORY IS OURS.
===============================================================

    [N] tasks DEMOLISHED by [M] agents working in parallel
    [G] Gatekeeper reviews passed - quality is BULLETPROOF
    All tests GREEN. Every gate CLEARED. Zero compromises.

    Time from first spawn to last completion: [duration]

    Your codebase just leveled up. The hive mind delivered.
===============================================================
```

Feel free to vary the flavor text each run - reference the specific work done, throw in relevant metaphors (evolution, swarm intelligence, trading). Make it feel like an achievement unlocked. Keep it ASCII-safe (no emoji, no unicode).

3. Use AskUserQuestion to ask: "The swarm crushed it! What's the next mission?"
   - Option 1: "Run again" (re-synthesize and keep going)
   - Option 2: "New tasks" (fresh work incoming)
   - Option 3: "We're done here" (end session gracefully)

---

## Edge Cases

1. All tasks conflict: sequential fallback (1 at a time)
2. Agent hangs: 10 min no progress update = failed
3. Gatekeeper rejects twice: mark task `[!]` and skip
4. New todos added: picked up on next loop iteration
5. Shared context too large: truncate to last 50 entries
