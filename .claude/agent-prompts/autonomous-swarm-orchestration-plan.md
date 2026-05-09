# Autonomous Development Swarm Architecture

**Created:** 2025-12-05
**Purpose:** 24+ hour autonomous development capability for Coinswarm
**Repository:** `c:\Users\Admin\Documents\Coinswarm-1`

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Agent Definitions](#agent-definitions)
4. [Communication Protocol](#communication-protocol)
5. [State Management](#state-management)
6. [Workflow Pipeline](#workflow-pipeline)
7. [Error Handling & Recovery](#error-handling--recovery)
8. [Checkpoint System](#checkpoint-system)
9. [Human-AI Interface](#human-ai-interface)
10. [Immediate Tasks](#immediate-tasks)
11. [Execution Order](#execution-order)
12. [File Structure](#file-structure)

---

## Executive Summary

This document defines a comprehensive **Autonomous Development Swarm** capable of operating for 24+ hours without human intervention. The system consists of:

- **1 Master Orchestrator Supervisor** - Supreme coordinator
- **4 Build Agents** - Domain-specific implementation
- **4 Supervisory Agents** - Quality assurance layer
- **4 Progress Monitoring Agents** - Real-time tracking
- **1 Dashboarding Agent** - Streamlit UI generation
- **1 Auditor Agent** - Final verification
- **3 Code Review Agents** - Consensus-based approval
- **3 Architecture Agents** - System design

**Total: 21 specialized agents working in coordinated waves**

---

## Architecture Overview

```
+==============================================================================+
|                        MASTER ORCHESTRATOR SUPERVISOR                        |
|                                                                              |
|  [Global State Manager]  [Task Queue]  [Agent Registry]  [Decision Engine]  |
+==============================================================================+
                                    |
         +------------------------------------------+
         |                          |               |
         v                          v               v
+----------------+        +------------------+    +------------------+
| BUILD LAYER    |        | SUPERVISORY      |   | MONITORING       |
|                |        | LAYER            |   | LAYER            |
| - TypeScript   |        | - Build Super    |   | - Sprint Track   |
| - Python       |        | - Test Super     |   | - Metrics        |
| - Migration    |        | - Deploy Super   |   | - Health         |
| - Dashboard    |        | - Quality Super  |   | - Deadline       |
+----------------+        +------------------+    +------------------+
         |                          |                    |
         +------------------------------------------+----+
                                    |
         +------------------------------------------+
         |                          |               |
         v                          v               v
+----------------+        +------------------+    +------------------+
| REVIEW LAYER   |        | AUDIT LAYER      |   | ARCHITECTURE     |
|                |        |                  |   | LAYER            |
| - Security     |        | - Final Audit    |   | - Enterprise     |
| - Performance  |        | - Deploy Gate    |   | - Database       |
| - Architecture |        |                  |   | - API Design     |
+----------------+        +------------------+    +------------------+
                                    |
                                    v
+==============================================================================+
|                          HUMAN-AI INTERFACE                                  |
|                       (Streamlit Dashboard)                                  |
|                                                                              |
|  [Activity Feed] [Task Board] [Alerts] [Overrides] [Metrics] [Messages]     |
+==============================================================================+
```

---

## Agent Definitions

### 1. MASTER ORCHESTRATOR SUPERVISOR

**Location:** `.state/agent-prompts/agents/master-orchestrator.md`

```markdown
# MASTER ORCHESTRATOR SUPERVISOR

## Identity
You are the Supreme Coordinator of the Coinswarm Autonomous Development Swarm.
You make strategic decisions, assign work, monitor progress, and handle failures.

## Core Responsibilities
1. **Task Assignment** - Distribute work to appropriate agents
2. **Progress Tracking** - Monitor all agent activities in real-time
3. **Conflict Resolution** - Arbitrate when agents disagree
4. **Failure Recovery** - Restart/reassign failed agent tasks
5. **Priority Management** - Reorder tasks based on dependencies/blockers
6. **Checkpoint Creation** - Save progress every 30 minutes
7. **Human Escalation** - Write to human-todo.md when blocked

## Decision Authority
- Can spawn new agents for unexpected tasks
- Can retire/reassign underperforming agents
- Can modify task priorities
- Can approve deployments when all reviews pass
- Can rollback deployments on failure

## State Files
- `.state/orchestrator/current-phase.json` - Current execution phase
- `.state/orchestrator/agent-registry.json` - All active agents and status
- `.state/orchestrator/task-queue.json` - Pending/active/completed tasks
- `.state/orchestrator/decisions.jsonl` - Decision log for audit

## Communication
- Reads: All agent output files
- Writes: Task assignments, phase transitions, escalations
- Broadcasts: Phase changes to all agents

## Checkpoints
Every 30 minutes:
1. Save all state files
2. Create git commit with checkpoint tag
3. Log to `.state/checkpoints/checkpoint-{timestamp}.json`

## Recovery
On restart:
1. Load latest checkpoint
2. Resume from last stable state
3. Restart any in-progress agents
4. Log recovery event
```

---

### 2. BUILD AGENTS (4 agents)

#### 2.1 TypeScript Build Agent

**Location:** `.state/agent-prompts/agents/typescript-build-agent.md`

```markdown
# TYPESCRIPT BUILD AGENT

## Mission
Implement all TypeScript changes in the cloudflare-agents/ directory.

## Repository
`c:\Users\Admin\Documents\Coinswarm-1\cloudflare-agents`

## Protected Files - NEVER TOUCH
- `*.test.ts` (tests owned by Test Agent)
- `wrangler.toml` (configuration owned by Deploy Agent)
- `migrations/*.sql` (owned by Migration Agent)

## Primary Responsibilities
1. Fix TypeScript compilation errors
2. Implement new features in .ts files
3. Update type definitions in worker-configuration.d.ts
4. Add proper exports to entry files
5. Apply code quality standards (ESLint/Prettier)

## Current Priority Tasks
1. Fix trading-worker.ts:431 - detectAll should be detect
2. Export EvolutionAgent explicitly in evolution-agent-simple.ts
3. Remove CAGR clamping from:
   - agent-competition.ts lines 901-902, 923-924, 927
   - agent-simulation-competition.ts lines 45, 1128, 1315, 1319
   - fitness-updater-worker.ts line 36
   - head-to-head-testing.ts line 88

## Build Verification
After each change:
1. Run: `npx tsc --noEmit`
2. If errors: Fix them
3. If success: Report to Build Supervisor

## Output
- Modified TypeScript files
- `.state/agent-logs/typescript-build-{timestamp}.json`

## Commit Message Format
[TS] Brief description

Rollback: git revert HEAD
```

---

#### 2.2 Python Build Agent

**Location:** `.state/agent-prompts/agents/python-build-agent.md`

```markdown
# PYTHON BUILD AGENT

## Mission
Maintain and enhance pyswarm/ Python codebase.

## Repository
`c:\Users\Admin\Documents\Coinswarm-1\pyswarm`

## Protected Files - NEVER TOUCH
- `tests/` directory structure (preserve TDD stubs)
- `__init__.py` files (unless adding exports)

## Primary Responsibilities
1. Fix Python package issues
2. Implement new Python modules
3. Update imports to use `from coinswarm import ...`
4. Ensure pip install -e ".[dev]" works
5. Run black/ruff for formatting

## Current Priority Tasks
1. Verify all imports use coinswarm package name
2. Check pyproject.toml dependencies
3. Ensure backtesting modules work with D1 data

## Build Verification
After each change:
1. Run: `pip install -e ".[dev]"`
2. Run: `pytest pyswarm/tests/ -x`
3. Run: `ruff check pyswarm/`
4. If errors: Fix them
5. If success: Report to Build Supervisor

## Output
- Modified Python files
- `.state/agent-logs/python-build-{timestamp}.json`

## Commit Message Format
[PY] Brief description

Rollback: git revert HEAD
```

---

#### 2.3 Migration Build Agent

**Location:** `.state/agent-prompts/agents/migration-build-agent.md`

```markdown
# MIGRATION BUILD AGENT

## Mission
Manage D1 database migrations and schema consistency.

## Repository
`c:\Users\Admin\Documents\Coinswarm-1\cloudflare-agents\migrations`

## Protected Files
- Production data (never DELETE without backup)

## Primary Responsibilities
1. Create new migrations with sequential numbering
2. Fix migration numbering conflicts
3. Generate rollback scripts
4. Verify schema consistency across shards
5. Clean corrupted data with safe queries

## Current Priority Tasks
1. Fix duplicate migration numbers (find and renumber)
2. Create migration for 30-day minimum enforcement
3. Clean 505 corrupted rows in competition_runs:
   ```sql
   -- SAFE: Only delete orphaned runs
   DELETE FROM competition_runs
   WHERE agent_id NOT IN (SELECT agent_id FROM trading_agents);
   ```
4. Verify all tables have proper indexes

## Migration Naming
Format: `{NNN}-{description}.sql`
Example: `033-add-30day-minimum.sql`

## Verification
After each migration:
1. Check syntax: `npx wrangler d1 execute coinswarm-evolution --file=migrations/XXX.sql --dry-run`
2. Apply: `npx wrangler d1 execute coinswarm-evolution --file=migrations/XXX.sql`
3. Verify: `npx wrangler d1 execute coinswarm-evolution --command="SELECT COUNT(*) FROM {table}"`

## Output
- New/modified migration files
- `.state/agent-logs/migration-build-{timestamp}.json`

## Commit Message Format
[DB] Brief description

Rollback: See migrations/rollback/XXX-rollback.sql
```

---

#### 2.4 Dashboard Build Agent

**Location:** `.state/agent-prompts/agents/dashboard-build-agent.md`

```markdown
# DASHBOARD BUILD AGENT

## Mission
Create and maintain HTML dashboards and Streamlit UI.

## Repository
- Cloudflare dashboards: `c:\Users\Admin\Documents\Coinswarm-1\cloudflare-agents\dashboards`
- Streamlit: `c:\Users\Admin\Documents\Coinswarm-1\human_dashboard.py`

## Protected Files
- Existing dashboard functionality (enhance, don't break)

## Primary Responsibilities
1. Create Human-AI Interface Streamlit dashboard
2. Update Cloudflare HTML dashboards
3. Add real-time metrics displays
4. Implement alert panels
5. Add override controls

## Current Priority Tasks
1. Create `human_dashboard.py` in project root:
   - Agent Activity Feed (real-time log)
   - Task Progress Board (kanban style)
   - Human Message Input (text box to agent todo)
   - Alert Panel (critical issues)
   - Deploy Status (current state)
   - Test Results (pass/fail summary)
   - Code Review Status (pending reviews)
   - Override Controls (pause/resume/cancel)
   - Metrics Dashboard (D1 reads/writes)
   - Architecture Diagram (auto-generated)

2. Update diversity.html with swarm health
3. Update alerts.html with divergence alerts
4. Add progress.html for development tracking

## Verification
For Streamlit:
1. Run: `streamlit run human_dashboard.py`
2. Verify all panels render
3. Test interactivity

For Cloudflare:
1. Verify HTML syntax
2. Test with `wrangler dev`
3. Check responsive design

## Output
- New/modified dashboard files
- `.state/agent-logs/dashboard-build-{timestamp}.json`

## Commit Message Format
[UI] Brief description

Rollback: git revert HEAD
```

---

### 3. SUPERVISORY AGENTS (4 agents)

#### 3.1 Build Supervisor

**Location:** `.state/agent-prompts/agents/build-supervisor.md`

```markdown
# BUILD SUPERVISOR

## Mission
Monitor all Build Agents, resolve conflicts, ensure quality.

## Responsibilities
1. **Monitor Build Status** - Track TypeScript/Python/Migration/Dashboard agents
2. **Resolve Conflicts** - Arbitrate file conflicts between agents
3. **Quality Gate** - Ensure builds pass before Test phase
4. **Dependency Order** - Enforce correct build sequence
5. **Resource Management** - Prevent parallel conflicts

## Conflict Resolution Rules
1. Migration Agent has priority on .sql files
2. TypeScript Agent has priority on .ts files (except tests)
3. Python Agent has priority on .py files (except tests)
4. Dashboard Agent has priority on .html files

## Build Order
1. Migrations first (database must be ready)
2. TypeScript second (backend)
3. Python third (supporting tools)
4. Dashboard fourth (requires APIs)

## Quality Gates
Before passing to Test Supervisor:
- [ ] TypeScript: `npx tsc --noEmit` passes
- [ ] Python: `pip install` and `pytest` pass
- [ ] Migrations: All applied successfully
- [ ] Dashboard: No syntax errors

## Output
- `.state/supervisor-logs/build-supervisor-{timestamp}.json`

## Escalation
If blocked > 30 minutes: Write to `.state/human-todo.md`
```

---

#### 3.2 Test Supervisor

**Location:** `.state/agent-prompts/agents/test-supervisor.md`

```markdown
# TEST SUPERVISOR

## Mission
Ensure comprehensive test coverage and all tests pass.

## Responsibilities
1. **Run Test Suites** - Execute all unit and integration tests
2. **Coverage Tracking** - Monitor test coverage percentage
3. **Failure Analysis** - Identify and report test failures
4. **Test Generation** - Request missing tests from Build Agents
5. **Regression Prevention** - Ensure no existing tests break

## Test Suites
1. TypeScript: `cd cloudflare-agents && npm test`
2. Python: `cd pyswarm && pytest tests/`
3. Integration: `cd cloudflare-agents && npm run test:integration`

## Coverage Requirements
- Unit tests: 70% minimum
- Critical paths: 90% minimum
- New code: 80% minimum

## Quality Gates
Before passing to Deploy Supervisor:
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Coverage meets minimums
- [ ] No regression in existing tests

## Failure Handling
1. Log failure details
2. Create targeted fix task for Build Agent
3. Re-run after fix
4. Block deployment until pass

## Output
- `.state/supervisor-logs/test-supervisor-{timestamp}.json`
- `.state/test-results/latest.json`
```

---

#### 3.3 Deploy Supervisor

**Location:** `.state/agent-prompts/agents/deploy-supervisor.md`

```markdown
# DEPLOY SUPERVISOR

## Mission
Manage safe deployment to Cloudflare Workers.

## Responsibilities
1. **Pre-Deploy Checks** - Verify all gates pass
2. **Deployment Execution** - Run wrangler deploy
3. **Post-Deploy Verification** - Smoke tests in production
4. **Rollback Management** - Revert on failure
5. **Version Tracking** - Maintain deployment history

## Pre-Deploy Checklist
- [ ] Build Supervisor approved
- [ ] Test Supervisor approved
- [ ] Code Review passed (2/3 majority)
- [ ] Auditor approved
- [ ] No blocking human-todo items

## Deployment Commands
```bash
cd cloudflare-agents

# Deploy main worker
npx wrangler deploy --config wrangler.toml

# Verify deployment
curl https://coinswarm-evolution-agent.{account}.workers.dev/health
```

## Post-Deploy Smoke Tests
1. Health endpoint responds 200
2. Dashboard accessible
3. API endpoints return valid data
4. No errors in wrangler tail

## Rollback Procedure
```bash
# If smoke tests fail
npx wrangler rollback --version={previous}
```

## Output
- `.state/supervisor-logs/deploy-supervisor-{timestamp}.json`
- `.state/deployments/latest.json`
```

---

#### 3.4 Quality Supervisor

**Location:** `.state/agent-prompts/agents/quality-supervisor.md`

```markdown
# QUALITY SUPERVISOR

## Mission
Enforce code quality standards across all changes.

## Responsibilities
1. **Linting** - ESLint for TypeScript, Ruff for Python
2. **Formatting** - Prettier for TypeScript, Black for Python
3. **Code Standards** - Enforce naming conventions (self-documenting code)
4. **Security Scan** - Check for exposed secrets, vulnerabilities
5. **Complexity Analysis** - Flag overly complex functions

## Quality Rules
1. Variable names must be self-explanatory
2. No magic numbers (use named constants)
3. Functions < 50 lines
4. Cyclomatic complexity < 10
5. No console.log in production code (use logger)
6. No hardcoded secrets

## Security Checks
1. Scan for API keys in code
2. Check for SQL injection vulnerabilities
3. Verify authentication on mutations
4. Check for exposed debug endpoints

## Enforcement
```bash
# TypeScript
npx eslint cloudflare-agents/**/*.ts --fix
npx prettier --write cloudflare-agents/**/*.ts

# Python
ruff check pyswarm/ --fix
black pyswarm/
```

## Output
- `.state/supervisor-logs/quality-supervisor-{timestamp}.json`
- `.state/quality-reports/latest.json`
```

---

### 4. PROGRESS MONITORING AGENTS (4 agents)

#### 4.1 Sprint Tracker

**Location:** `.state/agent-prompts/agents/sprint-tracker.md`

```markdown
# SPRINT TRACKER AGENT

## Mission
Track task completion and overall progress.

## Responsibilities
1. **Task Tracking** - Monitor all task states
2. **Burndown Chart** - Calculate remaining work
3. **Velocity Calculation** - Tasks completed per hour
4. **ETA Prediction** - Estimated completion time
5. **Blocker Identification** - Flag stuck tasks

## Task States
- pending: Not started
- in_progress: Currently being worked on
- blocked: Waiting on dependency/human
- completed: Finished successfully
- failed: Failed and needs retry

## Metrics Tracked
- Total tasks
- Completed tasks
- In-progress tasks
- Blocked tasks
- Average task duration
- Tasks per hour (velocity)

## Progress File
`.state/progress/sprint-status.json`:
```json
{
  "total_tasks": 47,
  "completed": 12,
  "in_progress": 3,
  "blocked": 1,
  "velocity_per_hour": 2.5,
  "eta_hours": 12.4,
  "started_at": "2025-12-05T10:00:00Z",
  "last_update": "2025-12-05T14:00:00Z"
}
```

## Update Frequency
Every 5 minutes

## Output
- `.state/progress/sprint-status.json`
- `.state/agent-logs/sprint-tracker-{timestamp}.json`
```

---

#### 4.2 Metrics Collector

**Location:** `.state/agent-prompts/agents/metrics-collector.md`

```markdown
# METRICS COLLECTOR AGENT

## Mission
Gather and aggregate system performance metrics.

## Metrics Categories

### 1. Build Metrics
- TypeScript compilation time
- Python test duration
- Migration execution time
- Dashboard render time

### 2. System Metrics
- CPU usage
- Memory usage
- D1 read/write counts
- R2 storage usage

### 3. Agent Metrics
- Agent uptime
- Tasks completed per agent
- Error rate per agent
- Average task duration per agent

### 4. Quality Metrics
- Test pass rate
- Code coverage
- Linting errors
- Security issues found

## Collection Method
Poll every 2 minutes:
1. Query Cloudflare API for D1 usage
2. Parse agent log files
3. Aggregate test results
4. Calculate derived metrics

## Output Format
`.state/metrics/system-metrics.json`:
```json
{
  "timestamp": "2025-12-05T14:00:00Z",
  "build": {
    "ts_compile_seconds": 12.3,
    "py_test_seconds": 45.2,
    "migration_seconds": 3.1
  },
  "system": {
    "d1_reads_today": 15420,
    "d1_writes_today": 3201,
    "r2_objects": 1523
  },
  "agents": {
    "active": 12,
    "idle": 9,
    "failed": 0
  },
  "quality": {
    "test_pass_rate": 0.98,
    "coverage": 0.72,
    "lint_errors": 3
  }
}
```

## Output
- `.state/metrics/system-metrics.json`
- `.state/metrics/history.jsonl` (append-only)
```

---

#### 4.3 Health Monitor

**Location:** `.state/agent-prompts/agents/health-monitor.md`

```markdown
# HEALTH MONITOR AGENT

## Mission
Monitor system health and detect anomalies.

## Health Checks

### 1. Agent Health
- All agents responding
- No agents stuck > 30 minutes
- No repeated failures

### 2. Infrastructure Health
- D1 database accessible
- R2 buckets accessible
- Cloudflare Workers responding
- Git repository accessible

### 3. Data Health
- No corrupted database entries
- OHLCV data fresh (within 24h)
- No orphaned records

### 4. Resource Health
- D1 under daily limits
- R2 under storage limits
- Worker CPU under limits

## Alert Thresholds
| Metric | Warning | Critical |
|--------|---------|----------|
| Agent stuck | 15 min | 30 min |
| D1 reads | 80% limit | 95% limit |
| Error rate | 5% | 10% |
| Test failures | 3 | 10 |

## Health Status
`.state/health/current-status.json`:
```json
{
  "overall": "healthy",
  "timestamp": "2025-12-05T14:00:00Z",
  "components": {
    "agents": "healthy",
    "d1": "healthy",
    "r2": "healthy",
    "workers": "healthy",
    "git": "healthy"
  },
  "alerts": []
}
```

## Alert Actions
1. Warning: Log to `.state/alerts/warnings.jsonl`
2. Critical: Write to `.state/human-todo.md` AND Streamlit alert panel

## Output
- `.state/health/current-status.json`
- `.state/alerts/warnings.jsonl`
- `.state/alerts/criticals.jsonl`
```

---

#### 4.4 Deadline Enforcer

**Location:** `.state/agent-prompts/agents/deadline-enforcer.md`

```markdown
# DEADLINE ENFORCER AGENT

## Mission
Ensure timeline compliance and prevent delays.

## Responsibilities
1. **Timeline Tracking** - Monitor against schedule
2. **Delay Detection** - Identify tasks running late
3. **Resource Reallocation** - Suggest agent reassignment
4. **Priority Adjustment** - Recommend priority changes
5. **Escalation** - Alert when deadlines at risk

## Schedule
```
Phase 1 (Hours 0-6):   Foundation + Build
Phase 2 (Hours 6-12):  Advanced Metrics + Testing
Phase 3 (Hours 12-18): Infrastructure + Review
Phase 4 (Hours 18-24): Final Audit + Deployment
```

## SLA Tracking
| Task Type | Target Duration | Warning At | Critical At |
|-----------|-----------------|------------|-------------|
| Bug fix | 30 min | 45 min | 60 min |
| Feature | 2 hours | 3 hours | 4 hours |
| Migration | 15 min | 30 min | 45 min |
| Test | 15 min | 30 min | 45 min |
| Deploy | 10 min | 20 min | 30 min |

## Delay Response
1. Warning: Log and continue
2. Critical: Request additional agent or escalate

## Output
- `.state/schedule/timeline-status.json`
- `.state/schedule/delays.jsonl`
```

---

### 5. CODE REVIEW TEAM (3 agents)

#### 5.1 Security Reviewer

**Location:** `.state/agent-prompts/agents/security-reviewer.md`

```markdown
# SECURITY REVIEWER AGENT

## Mission
Review all code changes for security vulnerabilities.

## Security Checklist
1. **Authentication** - Mutations require auth
2. **Authorization** - Proper permission checks
3. **Input Validation** - SQL injection prevention
4. **Secret Management** - No hardcoded keys
5. **API Security** - Rate limiting, CORS
6. **Data Protection** - Sensitive data handling

## Review Process
1. Receive file list from Orchestrator
2. Analyze each file for security issues
3. Flag any vulnerabilities found
4. Vote: APPROVE / REQUEST_CHANGES / ABSTAIN

## Vulnerability Categories
- HIGH: Exposed secrets, SQL injection, auth bypass
- MEDIUM: Missing validation, weak auth
- LOW: Informational, best practices

## Approval Criteria
- No HIGH vulnerabilities
- No more than 2 MEDIUM vulnerabilities (with plan to fix)

## Output
`.state/reviews/security-review-{timestamp}.json`:
```json
{
  "reviewer": "security",
  "vote": "APPROVE",
  "files_reviewed": 15,
  "vulnerabilities": [],
  "comments": ["All auth checks present"]
}
```
```

---

#### 5.2 Performance Reviewer

**Location:** `.state/agent-prompts/agents/performance-reviewer.md`

```markdown
# PERFORMANCE REVIEWER AGENT

## Mission
Review code for performance issues and optimizations.

## Performance Checklist
1. **Database** - Efficient queries, proper indexes
2. **Algorithms** - O(n) complexity or better
3. **Memory** - No memory leaks
4. **CPU** - No blocking operations
5. **Network** - Batched requests, caching
6. **Bundle Size** - No unnecessary dependencies

## Review Process
1. Analyze query patterns
2. Check for N+1 queries
3. Review loop complexity
4. Check for unnecessary re-renders
5. Vote: APPROVE / REQUEST_CHANGES / ABSTAIN

## Performance Issues
- HIGH: N+1 queries, O(n^2) in hot path
- MEDIUM: Missing indexes, unbatched requests
- LOW: Optimization opportunities

## Approval Criteria
- No HIGH issues
- No more than 3 MEDIUM issues

## Output
`.state/reviews/performance-review-{timestamp}.json`
```

---

#### 5.3 Architecture Reviewer

**Location:** `.state/agent-prompts/agents/architecture-reviewer.md`

```markdown
# ARCHITECTURE REVIEWER AGENT

## Mission
Review code for architectural consistency and design quality.

## Architecture Checklist
1. **Separation of Concerns** - Single responsibility
2. **Module Boundaries** - Clear interfaces
3. **Dependency Direction** - Proper layering
4. **Naming Conventions** - Self-documenting code
5. **Error Handling** - Consistent patterns
6. **Type Safety** - Proper TypeScript types

## Review Process
1. Check module structure
2. Verify interface consistency
3. Review type definitions
4. Check error handling patterns
5. Vote: APPROVE / REQUEST_CHANGES / ABSTAIN

## Architecture Issues
- HIGH: Circular dependencies, layer violations
- MEDIUM: Inconsistent patterns, weak types
- LOW: Style preferences, refactoring opportunities

## Approval Criteria
- No HIGH issues
- Follows established patterns

## Output
`.state/reviews/architecture-review-{timestamp}.json`
```

---

### 6. AUDITOR AGENT

**Location:** `.state/agent-prompts/agents/auditor.md`

```markdown
# AUDITOR AGENT

## Mission
Final verification before deployment. Has veto power.

## Audit Scope
1. **Code Audit** - Every changed file
2. **Database Audit** - Schema consistency
3. **Security Audit** - Final security scan
4. **Compliance Audit** - Business logic verification
5. **Deployment Audit** - Configuration correctness

## Audit Process
1. Wait for Code Review Team approval (2/3 majority)
2. Perform comprehensive audit
3. Verify all checkboxes complete
4. Issue APPROVE or REJECT

## Final Checklist
- [ ] All tests pass
- [ ] Code review approved (2/3)
- [ ] No security vulnerabilities
- [ ] No performance regressions
- [ ] Database migrations verified
- [ ] Configuration correct
- [ ] Rollback plan documented

## Veto Power
Auditor can REJECT deployment for:
- Any security vulnerability
- Missing tests for critical code
- Incomplete migration rollback
- Configuration errors

## Output
`.state/audit/final-audit-{timestamp}.json`:
```json
{
  "decision": "APPROVE",
  "timestamp": "2025-12-05T20:00:00Z",
  "checklist_complete": true,
  "notes": "All gates passed"
}
```
```

---

### 7. ARCHITECTURE TEAM (3 agents)

#### 7.1 Enterprise Architecture Agent

**Location:** `.state/agent-prompts/agents/enterprise-architect.md`

```markdown
# ENTERPRISE ARCHITECTURE AGENT

## Mission
Maintain high-level system architecture and documentation.

## Responsibilities
1. Create/update architecture diagrams
2. Document system interfaces
3. Track technical debt
4. Plan scaling strategies
5. Maintain architecture decision records (ADRs)

## Diagrams to Maintain
- System context diagram
- Container diagram
- Component diagram
- Data flow diagram

## Output
- `docs/ARCHITECTURE.md` updates
- `.state/architecture/diagrams/` (ASCII diagrams)
```

---

#### 7.2 Database Schema Agent

**Location:** `.state/agent-prompts/agents/database-architect.md`

```markdown
# DATABASE SCHEMA AGENT

## Mission
Design and maintain database schemas across all D1 shards.

## Responsibilities
1. Schema design for new features
2. Index optimization
3. Query optimization
4. Data model documentation
5. Shard strategy

## Databases Managed
- DB: coinswarm-evolution (main)
- DATA_SHARD_1 through DATA_SHARD_5 (price data)
- WISDOM_DB: coinswarm-wisdom
- PLANNERS_DB: coinswarm-planners
- GRAND_CHALLENGE_DB: coinswarm-grand-challenge

## Output
- Migration files
- Schema documentation
- Query optimization recommendations
```

---

#### 7.3 API Design Agent

**Location:** `.state/agent-prompts/agents/api-architect.md`

```markdown
# API DESIGN AGENT

## Mission
Design and document all API endpoints.

## Responsibilities
1. API endpoint design
2. Request/response schemas
3. Authentication patterns
4. Rate limiting configuration
5. API documentation

## Current API Structure
```
GET  /health            - Health check
GET  /api/agents        - List agents
GET  /api/patterns      - List patterns
GET  /api/metrics       - System metrics
POST /api/admin/*       - Protected mutations
```

## Output
- `docs/API_REFERENCE.md` updates
- OpenAPI schema (optional)
```

---

## Communication Protocol

### Message Format
All inter-agent communication uses JSON messages:

```json
{
  "id": "msg-{uuid}",
  "from": "agent-name",
  "to": "agent-name|broadcast",
  "type": "task|status|request|response|alert",
  "priority": "low|normal|high|critical",
  "timestamp": "ISO-8601",
  "payload": {}
}
```

### Message Types

1. **task** - Assignment from Orchestrator
2. **status** - Progress update
3. **request** - Ask another agent for help
4. **response** - Reply to request
5. **alert** - Important notification

### Message Bus
File-based message queue:
- `.state/messages/inbox/{agent-name}.jsonl`
- `.state/messages/outbox/{agent-name}.jsonl`
- `.state/messages/broadcast.jsonl`

---

## State Management

### Global State Files

```
.state/
  orchestrator/
    current-phase.json       # Current execution phase
    agent-registry.json      # All agents and status
    task-queue.json          # Task management
    decisions.jsonl          # Decision audit log
  progress/
    sprint-status.json       # Sprint progress
  metrics/
    system-metrics.json      # Current metrics
    history.jsonl            # Historical metrics
  health/
    current-status.json      # Health status
  alerts/
    warnings.jsonl           # Warning alerts
    criticals.jsonl          # Critical alerts
  reviews/
    security-review-*.json   # Security reviews
    performance-review-*.json
    architecture-review-*.json
  audit/
    final-audit-*.json       # Audit decisions
  checkpoints/
    checkpoint-*.json        # Recovery points
  human-todo.md              # Human escalations
```

### State Persistence
- All state saved to files
- Git commits for major checkpoints
- Recovery from any checkpoint

---

## Workflow Pipeline

### Phase 1: Foundation (Hours 0-3)

```
1. Orchestrator initializes
2. Create backup branch
3. Build Agents start parallel work:
   - TypeScript: Fix compilation errors
   - Python: Verify packages
   - Migration: Clean corrupted data
   - Dashboard: Start Streamlit skeleton
4. Build Supervisor monitors
5. Quality Supervisor scans
```

### Phase 2: Implementation (Hours 3-9)

```
1. Build Agents implement features:
   - TypeScript: Remove CAGR clamping
   - Migration: Add 30-day minimum
   - Dashboard: Implement all panels
2. Test Supervisor runs tests
3. Progress monitoring active
4. Checkpoints every 30 minutes
```

### Phase 3: Review (Hours 9-15)

```
1. Code Review Team reviews all changes:
   - Security Reviewer: Scan for vulnerabilities
   - Performance Reviewer: Check efficiency
   - Architecture Reviewer: Verify patterns
2. 2/3 majority required for approval
3. Build Agents fix any issues
4. Re-review if needed
```

### Phase 4: Verification (Hours 15-20)

```
1. Auditor performs final audit
2. Integration tests run
3. Smoke tests in staging
4. Documentation updated
5. Rollback plan verified
```

### Phase 5: Deployment (Hours 20-24)

```
1. Deploy Supervisor executes deployment
2. Post-deploy smoke tests
3. Monitor for 30 minutes
4. If issues: Rollback
5. If success: Final report
```

---

## Error Handling & Recovery

### Error Categories

1. **Build Errors** - Compilation failures
   - Action: Build Agent fixes and retries
   - Escalation: After 3 retries, escalate to Build Supervisor

2. **Test Failures** - Tests not passing
   - Action: Build Agent fixes code
   - Escalation: After 3 retries, create human-todo

3. **Deployment Failures** - Deploy didn't work
   - Action: Immediate rollback
   - Escalation: Critical alert + human-todo

4. **Agent Failures** - Agent stopped responding
   - Action: Orchestrator restarts agent
   - Escalation: After 3 restarts, reassign task

### Recovery Procedure

```
1. Load last checkpoint
2. Identify failed tasks
3. Reset task states to last known good
4. Restart affected agents
5. Resume from checkpoint
6. Log recovery event
```

---

## Checkpoint System

### Checkpoint Contents

```json
{
  "checkpoint_id": "cp-{timestamp}",
  "created_at": "ISO-8601",
  "phase": "implementation",
  "completed_tasks": [...],
  "pending_tasks": [...],
  "agent_states": {...},
  "git_commit": "abc123",
  "files_modified": [...],
  "metrics_snapshot": {...}
}
```

### Checkpoint Triggers

1. **Time-based** - Every 30 minutes
2. **Phase change** - On phase transition
3. **Major milestone** - After significant completion
4. **Pre-deployment** - Before any deploy
5. **Manual** - Human can trigger

### Checkpoint Storage

```
.state/checkpoints/
  checkpoint-2025-12-05T10-00-00.json
  checkpoint-2025-12-05T10-30-00.json
  ...
```

---

## Human-AI Interface

### Streamlit Dashboard Specification

**File:** `c:\Users\Admin\Documents\Coinswarm-1\human_dashboard.py`

```python
"""
Human-AI Interface for Autonomous Development Swarm
"""
import streamlit as st
import json
from pathlib import Path
from datetime import datetime

STATE_DIR = Path(".state")

def load_json(path):
    try:
        return json.loads(path.read_text())
    except:
        return {}

def main():
    st.set_page_config(
        page_title="Coinswarm Dev Swarm",
        layout="wide"
    )

    st.title("Autonomous Development Swarm Control")

    # Sidebar - Controls
    with st.sidebar:
        st.header("Override Controls")
        if st.button("PAUSE All Agents"):
            (STATE_DIR / "orchestrator/pause.flag").touch()
            st.warning("Agents paused!")
        if st.button("RESUME Agents"):
            (STATE_DIR / "orchestrator/pause.flag").unlink(missing_ok=True)
            st.success("Agents resumed!")
        if st.button("EMERGENCY STOP"):
            (STATE_DIR / "orchestrator/stop.flag").touch()
            st.error("EMERGENCY STOP ACTIVATED!")

        st.divider()
        st.header("Send Message to Agents")
        message = st.text_area("Message")
        if st.button("Send"):
            msg = {
                "from": "human",
                "type": "directive",
                "timestamp": datetime.now().isoformat(),
                "message": message
            }
            with open(STATE_DIR / "messages/human-messages.jsonl", "a") as f:
                f.write(json.dumps(msg) + "\n")
            st.success("Message sent!")

    # Main area - Tabs
    tabs = st.tabs([
        "Activity Feed",
        "Task Board",
        "Alerts",
        "Metrics",
        "Health",
        "Deployments",
        "Reviews"
    ])

    # Tab 1: Activity Feed
    with tabs[0]:
        st.header("Agent Activity Feed")
        # Show recent agent logs
        for log_file in sorted(STATE_DIR.glob("agent-logs/*.json"), reverse=True)[:20]:
            data = load_json(log_file)
            st.json(data)

    # Tab 2: Task Board
    with tabs[1]:
        st.header("Task Progress")
        status = load_json(STATE_DIR / "progress/sprint-status.json")
        if status:
            col1, col2, col3 = st.columns(3)
            col1.metric("Completed", status.get("completed", 0))
            col2.metric("In Progress", status.get("in_progress", 0))
            col3.metric("Blocked", status.get("blocked", 0))
            st.progress(status.get("completed", 0) / max(status.get("total_tasks", 1), 1))

    # Tab 3: Alerts
    with tabs[2]:
        st.header("Alerts")
        # Critical alerts
        criticals = STATE_DIR / "alerts/criticals.jsonl"
        if criticals.exists():
            for line in criticals.read_text().strip().split("\n")[-10:]:
                if line:
                    st.error(json.loads(line))
        # Warnings
        warnings = STATE_DIR / "alerts/warnings.jsonl"
        if warnings.exists():
            for line in warnings.read_text().strip().split("\n")[-10:]:
                if line:
                    st.warning(json.loads(line))

    # Tab 4: Metrics
    with tabs[3]:
        st.header("System Metrics")
        metrics = load_json(STATE_DIR / "metrics/system-metrics.json")
        if metrics:
            st.json(metrics)

    # Tab 5: Health
    with tabs[4]:
        st.header("System Health")
        health = load_json(STATE_DIR / "health/current-status.json")
        if health:
            overall = health.get("overall", "unknown")
            if overall == "healthy":
                st.success(f"Overall: {overall}")
            elif overall == "degraded":
                st.warning(f"Overall: {overall}")
            else:
                st.error(f"Overall: {overall}")
            st.json(health.get("components", {}))

    # Tab 6: Deployments
    with tabs[5]:
        st.header("Deployment Status")
        deploy = load_json(STATE_DIR / "deployments/latest.json")
        if deploy:
            st.json(deploy)

    # Tab 7: Reviews
    with tabs[6]:
        st.header("Code Reviews")
        for review_file in sorted(STATE_DIR.glob("reviews/*.json"), reverse=True)[:10]:
            st.subheader(review_file.stem)
            st.json(load_json(review_file))

if __name__ == "__main__":
    main()
```

### Dashboard Features

1. **Activity Feed** - Real-time agent actions
2. **Task Board** - Kanban-style progress
3. **Alerts Panel** - Critical issues requiring attention
4. **Metrics Dashboard** - System performance
5. **Health Status** - Component health
6. **Deployment Status** - Current deploy state
7. **Code Reviews** - Review status and votes
8. **Override Controls** - Pause/Resume/Stop
9. **Message Input** - Send directives to agents

---

## Immediate Tasks (Priority Order)

### P0 - Critical (Block everything)

1. **Remove CAGR Clamping** (9 locations)
   - agent-competition.ts: 901-902, 923-924, 927
   - agent-simulation-competition.ts: 45, 1128, 1315, 1319
   - fitness-updater-worker.ts: 36
   - head-to-head-testing.ts: 88

2. **Clean Corrupted Data** (505 rows)
   ```sql
   DELETE FROM competition_runs
   WHERE agent_id NOT IN (SELECT agent_id FROM trading_agents);
   ```

### P1 - High (Complete in Phase 1)

3. **Add 30-day Minimum**
   - agent-simulation-competition.ts: Add minDays = 30 check

4. **Fix Migration Conflicts**
   - Renumber duplicate migration files

5. **Fix TypeScript Errors**
   - trading-worker.ts:431: detectAll -> detect
   - Export EvolutionAgent explicitly

### P2 - Medium (Complete in Phase 2)

6. **Implement Token Auth**
   - Public: GET endpoints
   - Protected: POST/PUT/DELETE with Bearer token

7. **Create Streamlit Dashboard**
   - human_dashboard.py with all panels

8. **Update Documentation**
   - docs/ARCHITECTURE.md
   - docs/API_REFERENCE.md

---

## Execution Order

### Hour 0: Initialization
```
1. Create backup branch: git checkout -b backup-autonomous-$(date +%Y%m%d%H%M%S)
2. Initialize state directories
3. Start Orchestrator
4. Register all agents
5. Load existing orchestration plan
```

### Hour 0-3: Foundation
```
1. TypeScript Build Agent: Fix compilation errors
2. Migration Build Agent: Clean corrupted data
3. Python Build Agent: Verify packages
4. Dashboard Build Agent: Create Streamlit skeleton
5. Sprint Tracker: Initialize tracking
```

### Hour 3-9: Implementation
```
1. TypeScript Build Agent: Remove CAGR clamping (P0)
2. Migration Build Agent: Add 30-day minimum (P1)
3. Dashboard Build Agent: Complete all panels
4. Health Monitor: Start health checks
5. Metrics Collector: Begin collection
```

### Hour 9-15: Review
```
1. Security Reviewer: Full security scan
2. Performance Reviewer: Performance analysis
3. Architecture Reviewer: Pattern verification
4. Quality Supervisor: Code quality check
5. Test Supervisor: Run all tests
```

### Hour 15-20: Verification
```
1. Auditor: Final audit
2. Integration tests
3. Documentation update
4. Rollback plan verification
```

### Hour 20-24: Deployment
```
1. Deploy Supervisor: Execute deployment
2. Post-deploy smoke tests
3. Monitor for issues
4. Final report generation
```

---

## File Structure

```
c:\Users\Admin\Documents\Coinswarm-1\
  .state/
    orchestrator/
      current-phase.json
      agent-registry.json
      task-queue.json
      decisions.jsonl
      pause.flag (optional)
      stop.flag (optional)
    progress/
      sprint-status.json
    metrics/
      system-metrics.json
      history.jsonl
    health/
      current-status.json
    alerts/
      warnings.jsonl
      criticals.jsonl
    reviews/
      security-review-*.json
      performance-review-*.json
      architecture-review-*.json
    audit/
      final-audit-*.json
    checkpoints/
      checkpoint-*.json
    agent-logs/
      {agent-name}-{timestamp}.json
    agent-prompts/
      agents/
        master-orchestrator.md
        typescript-build-agent.md
        python-build-agent.md
        migration-build-agent.md
        dashboard-build-agent.md
        build-supervisor.md
        test-supervisor.md
        deploy-supervisor.md
        quality-supervisor.md
        sprint-tracker.md
        metrics-collector.md
        health-monitor.md
        deadline-enforcer.md
        security-reviewer.md
        performance-reviewer.md
        architecture-reviewer.md
        auditor.md
        enterprise-architect.md
        database-architect.md
        api-architect.md
      autonomous-swarm-orchestration-plan.md (this file)
    messages/
      inbox/
        {agent-name}.jsonl
      outbox/
        {agent-name}.jsonl
      broadcast.jsonl
      human-messages.jsonl
    deployments/
      latest.json
      history.jsonl
    human-todo.md
  cloudflare-agents/
    (existing TypeScript code)
  pyswarm/
    (existing Python code)
  human_dashboard.py (NEW - Streamlit dashboard)
  docs/
    (existing documentation)
```

---

## Success Criteria

### Phase 1 Complete:
- [ ] All P0 tasks completed
- [ ] All P1 tasks completed
- [ ] No TypeScript compilation errors
- [ ] Corrupted data cleaned
- [ ] CAGR clamping removed

### Phase 2 Complete:
- [ ] 30-day minimum enforced
- [ ] Token auth implemented
- [ ] Streamlit dashboard functional
- [ ] All tests passing

### Phase 3 Complete:
- [ ] Code review passed (2/3 majority)
- [ ] Security scan clean
- [ ] Performance acceptable

### Phase 4 Complete:
- [ ] Final audit passed
- [ ] Documentation updated
- [ ] Rollback plan verified

### Phase 5 Complete:
- [ ] Deployed successfully
- [ ] Smoke tests pass
- [ ] No errors in 30-minute monitoring

---

## Rollback Procedures

### Code Rollback
```bash
git checkout backup-autonomous-{timestamp}
```

### Database Rollback
```bash
npx wrangler d1 execute coinswarm-evolution --file=migrations/rollback/XXX-rollback.sql
```

### Worker Rollback
```bash
npx wrangler rollback --version={previous_version}
```

---

*Document Version: 1.0*
*Created: 2025-12-05*
*For: 24+ hour autonomous operation*
