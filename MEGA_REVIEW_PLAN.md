# MEGA CODE QUALITY REVIEW PLAN

## THE ULTIMATE CODE QUALITY APOCALYPSE

**Target Codebase**: `c:\fast_swarm\src\Fast_Swarm`
**Execution Strategy**: Massive parallel deployment of Haiku-powered sub-agents
**Philosophy**: LEAVE NO STONE UNTURNED. Every file. Every line. Every possibility.

---

## TABLE OF CONTENTS

1. [Executive Summary](#executive-summary)
2. [Wave Structure Overview](#wave-structure-overview)
3. [Wave 0: Reconnaissance](#wave-0-reconnaissance)
4. [Wave 1: Security Apocalypse](#wave-1-security-apocalypse)
5. [Wave 2: Database & Query Carnage](#wave-2-database--query-carnage)
6. [Wave 3: Async & Concurrency Warfare](#wave-3-async--concurrency-warfare)
7. [Wave 4: Type Safety Inquisition](#wave-4-type-safety-inquisition)
8. [Wave 5: Trading Logic Validation](#wave-5-trading-logic-validation)
9. [Wave 6: Error Handling Crusade](#wave-6-error-handling-crusade)
10. [Wave 7: Performance Annihilation](#wave-7-performance-annihilation)
11. [Wave 8: Test Coverage Blitz](#wave-8-test-coverage-blitz)
12. [Wave 9: Code Quality Purge](#wave-9-code-quality-purge)
13. [Wave 10: Documentation Audit](#wave-10-documentation-audit)
14. [Wave 11: Frontend Security & Quality](#wave-11-frontend-security--quality)
15. [Wave 12: Configuration & Secrets](#wave-12-configuration--secrets)
16. [Wave 13: Dependency Analysis](#wave-13-dependency-analysis)
17. [Wave 14: Integration & Contract Testing](#wave-14-integration--contract-testing)
18. [Wave 15: Final Synthesis](#wave-15-final-synthesis)

---

## EXECUTIVE SUMMARY

This plan deploys **200+ independent review tasks** across **16 waves** of parallel execution. Each task is designed to be:

- **Atomic**: Completable by a single Haiku agent in isolation
- **Specific**: Clear file paths, patterns, and success criteria
- **Actionable**: Produces concrete findings with severity ratings

### Domain Coverage

| Domain | Files | Primary Concerns |
|--------|-------|------------------|
| Agents/ | 35 files | Evolution logic, trait mutation, fitness calculations |
| Patterns/ | 8 files | Pattern matching, discovery, condition evaluation |
| Infrastructure/ | 22 files | WebSocket streams, market data, bear protection |
| Trading/ | 9 files | Paper trading, live execution, approval queues |
| Evolution/ | 3 files | Evolution cycles, monitoring |
| System/ | 15 files | Orchestrator, robustness, wisdom extraction |
| Dashboard/ | 6 files | HTML/JS/CSS cyberpunk UI |
| Tests/ | 78 files | Unit, soundness, triage, property tests |
| exchanges/ | 5 files | WebSocket clients for 4 exchanges |

---

## WAVE STRUCTURE OVERVIEW

```
WAVE 0:  RECONNAISSANCE (5 tasks)
         |
         v
WAVE 1:  SECURITY (25 tasks) ----+
WAVE 2:  DATABASE (20 tasks) ----+--- Run in parallel
WAVE 3:  ASYNC (15 tasks) -------+
         |
         v
WAVE 4:  TYPE SAFETY (20 tasks) --+
WAVE 5:  TRADING LOGIC (25 tasks) +--- Run in parallel
         |
         v
WAVE 6:  ERROR HANDLING (15 tasks) --+
WAVE 7:  PERFORMANCE (20 tasks) -----+--- Run in parallel
         |
         v
WAVE 8:  TEST COVERAGE (20 tasks) ---+
WAVE 9:  CODE QUALITY (25 tasks) ----+--- Run in parallel
         |
         v
WAVE 10: DOCUMENTATION (10 tasks) ---+
WAVE 11: FRONTEND (15 tasks) --------+--- Run in parallel
         |
         v
WAVE 12: CONFIGURATION (10 tasks) ---+
WAVE 13: DEPENDENCIES (10 tasks) ----+--- Run in parallel
         |
         v
WAVE 14: INTEGRATION (15 tasks)
         |
         v
WAVE 15: FINAL SYNTHESIS (5 tasks)
```

---

## WAVE 0: RECONNAISSANCE

**Objective**: Map the entire codebase structure and identify all entry points, dependencies, and data flows.

### Task 0.1: File Inventory
- **Agent ID**: RECON-001
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\**\*.py`
- **Action**: Generate complete file tree with line counts and last modified dates
- **Output**: `inventory.json` with file metadata
- **Success Criteria**: All Python files catalogued with accurate metrics

### Task 0.2: Import Graph Analysis
- **Agent ID**: RECON-002
- **Scope**: All Python files
- **Action**: Build dependency graph showing which modules import which
- **Pattern**: Search for `^from|^import` in all .py files
- **Output**: Import dependency graph identifying circular imports
- **Success Criteria**: All circular imports identified and documented

### Task 0.3: API Endpoint Inventory
- **Agent ID**: RECON-003
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\**\*router*.py`
- **Action**: List all FastAPI endpoints with methods, paths, and parameters
- **Pattern**: Search for `@router\.(get|post|put|delete|patch)`
- **Output**: Complete API surface inventory
- **Success Criteria**: All 50+ endpoints documented

### Task 0.4: Database Model Inventory
- **Agent ID**: RECON-004
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\**\*models*.py`
- **Action**: List all SQLModel classes with their fields and relationships
- **Pattern**: Search for `class.*SQLModel.*table=True`
- **Output**: Complete database schema documentation
- **Success Criteria**: All tables and columns documented

### Task 0.5: Background Task Inventory
- **Agent ID**: RECON-005
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Main.py`, `*service*.py`
- **Action**: Document all background loops, asyncio.create_task calls, and scheduled operations
- **Pattern**: Search for `asyncio.create_task|async def.*loop`
- **Output**: Background task registry
- **Success Criteria**: All async background operations documented

---

## WAVE 1: SECURITY APOCALYPSE

**Objective**: Identify every possible security vulnerability using OWASP Top 10 as baseline plus trading-specific threats.

### INJECTION ATTACKS

#### Task 1.1: SQL Injection - Raw Queries
- **Agent ID**: SEC-001
- **Scope**: All .py files
- **Action**: Find all raw SQL execution without parameterization
- **Patterns**:
  - `text\(f"` (f-string in text())
  - `execute\(f"` (f-string in execute)
  - `\.format\(.*\).*execute` (string formatting before execute)
  - `%s.*%` followed by execute (old-style string formatting)
- **Files to Prioritize**:
  - `c:\fast_swarm\src\Fast_Swarm\Database.py`
  - `c:\fast_swarm\src\Fast_Swarm\Agents\Services\*.py`
  - `c:\fast_swarm\src\Fast_Swarm\Patterns\Services\*.py`
- **Severity**: CRITICAL
- **Success Criteria**: Zero unparameterized dynamic SQL

#### Task 1.2: SQL Injection - ORM Filters
- **Agent ID**: SEC-002
- **Scope**: All service files
- **Action**: Find SQLModel/SQLAlchemy queries with dynamic filter construction
- **Patterns**:
  - `where\(.*format`
  - `filter\(.*\+.*\)`
  - `select.*where.*{`
- **Severity**: HIGH
- **Success Criteria**: All dynamic filters use bound parameters

#### Task 1.3: Command Injection
- **Agent ID**: SEC-003
- **Scope**: All .py files
- **Action**: Find shell command execution with user input
- **Patterns**:
  - `subprocess\.(run|call|Popen)`
  - `os\.system\(`
  - `os\.popen\(`
  - `eval\(`
  - `exec\(`
- **Files to Prioritize**:
  - `c:\fast_swarm\src\Fast_Swarm\System\Services\pytest_orchestrator.py`
  - `c:\fast_swarm\src\Fast_Swarm\System\Services\robustness_service.py`
- **Severity**: CRITICAL
- **Success Criteria**: All subprocess calls use shell=False with arg lists

#### Task 1.4: JSONB Injection
- **Agent ID**: SEC-004
- **Scope**: All files using JSONB columns
- **Action**: Find unsanitized JSON construction for JSONB queries
- **Patterns**:
  - `traits\[.*\]` with dynamic keys
  - `JSONB.*->.*format`
  - `pattern_weights\[`
- **Files**:
  - `c:\fast_swarm\src\Fast_Swarm\Agents\Models\agent_models.py`
  - `c:\fast_swarm\src\Fast_Swarm\Agents\Services\trait_service.py`
- **Severity**: HIGH
- **Success Criteria**: All JSONB operations use safe accessors

### AUTHENTICATION & AUTHORIZATION

#### Task 1.5: Missing Authentication
- **Agent ID**: SEC-005
- **Scope**: All router files
- **Action**: Identify endpoints without authentication dependencies
- **Patterns**:
  - `@router\.(post|put|delete|patch)` without `Depends(verify_auth)`
  - Sensitive operations without auth checks
- **Files**:
  - `c:\fast_swarm\src\Fast_Swarm\Agents\Routers\actions_router.py`
  - `c:\fast_swarm\src\Fast_Swarm\Trading\Routers\trading_router.py`
  - `c:\fast_swarm\src\Fast_Swarm\System\Routers\system_router.py`
- **Severity**: HIGH
- **Success Criteria**: All mutation endpoints require authentication

#### Task 1.6: Missing Authorization
- **Agent ID**: SEC-006
- **Scope**: Router and service files
- **Action**: Find operations that don't verify ownership/permissions
- **Patterns**:
  - `delete.*agent_id` without owner check
  - `update.*pattern_id` without permission check
- **Severity**: MEDIUM
- **Success Criteria**: All resource operations verify ownership

#### Task 1.7: CORS Misconfiguration
- **Agent ID**: SEC-007
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Main.py`
- **Action**: Analyze CORS middleware configuration
- **Check**:
  - `allow_origins=["*"]` is too permissive
  - `allow_credentials=True` with wildcard origin
- **Severity**: MEDIUM
- **Success Criteria**: CORS properly restricts origins

### DATA EXPOSURE

#### Task 1.8: Sensitive Data in Logs
- **Agent ID**: SEC-008
- **Scope**: All .py files
- **Action**: Find logging of sensitive information
- **Patterns**:
  - `print\(.*password`
  - `print\(.*secret`
  - `print\(.*api_key`
  - `logging\..*password`
  - `print\(.*token`
- **Severity**: MEDIUM
- **Success Criteria**: No sensitive data in logs

#### Task 1.9: API Response Data Leakage
- **Agent ID**: SEC-009
- **Scope**: All router files
- **Action**: Find endpoints returning full database models without filtering
- **Patterns**:
  - `return agent` (returning full SQLModel)
  - `return pattern` (returning full model)
  - Without Pydantic response_model filtering
- **Severity**: MEDIUM
- **Success Criteria**: All endpoints use response models

#### Task 1.10: Error Message Information Disclosure
- **Agent ID**: SEC-010
- **Scope**: All .py files
- **Action**: Find stack traces or detailed errors exposed to clients
- **Patterns**:
  - `HTTPException.*str\(e\)`
  - `return.*traceback`
  - `detail=.*exception`
- **Severity**: LOW
- **Success Criteria**: Errors sanitized before client response

### WEBSOCKET SECURITY

#### Task 1.11: WebSocket Origin Validation
- **Agent ID**: SEC-011
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\exchanges\*.py`
- **Action**: Verify WebSocket connections validate origin
- **Check**: Origin header validation in connection handlers
- **Severity**: MEDIUM
- **Success Criteria**: All WebSocket connections verify origin

#### Task 1.12: WebSocket Message Validation
- **Agent ID**: SEC-012
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\exchanges\*.py`
- **Action**: Find message parsing without validation
- **Patterns**:
  - `json\.loads` without try/except
  - Missing schema validation on incoming messages
- **Files**:
  - `c:\fast_swarm\src\Fast_Swarm\exchanges\binance_ws.py`
  - `c:\fast_swarm\src\Fast_Swarm\exchanges\coinbase_ws.py`
  - `c:\fast_swarm\src\Fast_Swarm\exchanges\dydx_ws.py`
  - `c:\fast_swarm\src\Fast_Swarm\exchanges\hyperliquid_ws.py`
- **Severity**: MEDIUM
- **Success Criteria**: All WebSocket messages validated

#### Task 1.13: WebSocket Reconnection Security
- **Agent ID**: SEC-013
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\exchanges\base_ws.py`
- **Action**: Analyze reconnection logic for security issues
- **Check**:
  - Exponential backoff to prevent DoS
  - State reset on reconnection
  - Re-authentication requirements
- **Severity**: MEDIUM
- **Success Criteria**: Secure reconnection patterns

### RATE LIMITING & DOS

#### Task 1.14: Rate Limiting
- **Agent ID**: SEC-014
- **Scope**: All router files, Main.py
- **Action**: Check for rate limiting on all endpoints
- **Pattern**: Search for `RateLimiter|slowapi|throttle`
- **Severity**: HIGH
- **Success Criteria**: All endpoints have rate limits

#### Task 1.15: Resource Exhaustion
- **Agent ID**: SEC-015
- **Scope**: All .py files
- **Action**: Find unbounded operations
- **Patterns**:
  - `while True` without break conditions
  - `for.*in.*` without limits on user-controlled input
  - Missing pagination on list endpoints
- **Severity**: MEDIUM
- **Success Criteria**: All loops bounded, all lists paginated

### CRYPTOGRAPHIC ISSUES

#### Task 1.16: Weak Randomness
- **Agent ID**: SEC-016
- **Scope**: All .py files
- **Action**: Find use of weak random for security purposes
- **Patterns**:
  - `import random` (not secrets)
  - `random\.(random|randint|choice)` for IDs/tokens
- **Files to Check**:
  - `c:\fast_swarm\src\Fast_Swarm\Agents\Services\spawn_service.py`
  - `c:\fast_swarm\src\Fast_Swarm\local_agents\shared\rng.py`
- **Severity**: MEDIUM
- **Note**: random is OK for evolution/chaos (by design) but not for auth
- **Success Criteria**: Secrets used for security-sensitive randomness

#### Task 1.17: Hardcoded Secrets
- **Agent ID**: SEC-017
- **Scope**: All .py files
- **Action**: Find hardcoded credentials, API keys, secrets
- **Patterns**:
  - `password\s*=\s*["']`
  - `api_key\s*=\s*["']`
  - `secret\s*=\s*["']`
  - `token\s*=\s*["']`
- **Severity**: CRITICAL
- **Success Criteria**: Zero hardcoded secrets

### FILE SYSTEM SECURITY

#### Task 1.18: Path Traversal
- **Agent ID**: SEC-018
- **Scope**: All .py files
- **Action**: Find file operations with user-controlled paths
- **Patterns**:
  - `open\(.*\+` (concatenated paths)
  - `Path\(.*\+`
  - `os\.path\.join.*request`
- **Severity**: HIGH
- **Success Criteria**: All file paths sanitized

#### Task 1.19: Unsafe File Operations
- **Agent ID**: SEC-019
- **Scope**: All .py files
- **Action**: Find file operations without proper error handling
- **Patterns**:
  - `open\(` without context manager
  - Missing file existence checks
- **Severity**: LOW
- **Success Criteria**: All file ops use context managers

### DESERIALIZATION

#### Task 1.20: Unsafe Deserialization
- **Agent ID**: SEC-020
- **Scope**: All .py files
- **Action**: Find unsafe deserialization (NOTE: This task checks for security vulnerabilities)
- **Patterns**:
  - Unsafe loading of serialized data
  - `yaml\.load` (without safe_load)
  - `marshal\.load`
- **Severity**: CRITICAL
- **Success Criteria**: No unsafe deserialization

#### Task 1.21: JSON Schema Validation
- **Agent ID**: SEC-021
- **Scope**: All router files
- **Action**: Find JSON parsing without Pydantic validation
- **Patterns**:
  - `json\.loads` in routers without subsequent validation
  - `request\.json\(\)` without model parsing
- **Severity**: MEDIUM
- **Success Criteria**: All JSON inputs validated via Pydantic

### DEPENDENCY INJECTION SECURITY

#### Task 1.22: Dependency Override Exposure
- **Agent ID**: SEC-022
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Main.py`, `Dependencies.py`
- **Action**: Check if dependency overrides are exposed in production
- **Check**: `app.dependency_overrides` not modifiable in production
- **Severity**: LOW
- **Success Criteria**: Dependency injection secure in production

### API SECURITY

#### Task 1.23: HTTP Method Confusion
- **Agent ID**: SEC-023
- **Scope**: All router files
- **Action**: Find mutations allowed via GET requests
- **Patterns**:
  - `@router\.get` with database writes
  - GET endpoints that modify state
- **Severity**: MEDIUM
- **Success Criteria**: All mutations use POST/PUT/DELETE

#### Task 1.24: Mass Assignment
- **Agent ID**: SEC-024
- **Scope**: All router and service files
- **Action**: Find models updated from raw request data
- **Patterns**:
  - `model\.\*\*dict\(\)`
  - `update\(\*\*request\.dict\(\)\)`
- **Severity**: MEDIUM
- **Success Criteria**: Explicit field assignment for updates

#### Task 1.25: Request Size Limits
- **Agent ID**: SEC-025
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Main.py`
- **Action**: Check for request body size limits
- **Check**: Middleware for max content length
- **Severity**: MEDIUM
- **Success Criteria**: Request size limits configured

---

## WAVE 2: DATABASE & QUERY CARNAGE

**Objective**: Find all database-related issues including N+1 queries, connection leaks, transaction problems, and data integrity issues.

### CONNECTION MANAGEMENT

#### Task 2.1: Connection Pool Configuration
- **Agent ID**: DB-001
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Database.py`
- **Action**: Analyze connection pool settings
- **Check**:
  - Pool size appropriate for workload
  - pool_pre_ping enabled
  - pool_recycle set for long-running connections
  - Overflow limits reasonable
- **Success Criteria**: Optimal pool configuration documented

#### Task 2.2: Session Lifecycle
- **Agent ID**: DB-002
- **Scope**: All files using `get_session`
- **Action**: Verify all sessions properly closed
- **Patterns**:
  - `async_session_maker\(\)` without try/finally
  - Missing `await session.close()`
- **Success Criteria**: All sessions have proper cleanup

#### Task 2.3: Connection Leaks
- **Agent ID**: DB-003
- **Scope**: All service files
- **Action**: Find potential connection leaks
- **Patterns**:
  - Session created but not yielded/closed
  - Early returns before session cleanup
  - Exception handlers that don't close connections
- **Success Criteria**: No connection leak possibilities

### N+1 QUERY DETECTION

#### Task 2.4: Agents N+1 Queries
- **Agent ID**: DB-004
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Agents\Services\*.py`
- **Action**: Find loops that execute queries
- **Patterns**:
  - `for agent in agents:.*select`
  - `for.*in.*:.*await session\.exec`
  - `.refresh\(` inside loops
- **Success Criteria**: Zero N+1 patterns in agent services

#### Task 2.5: Patterns N+1 Queries
- **Agent ID**: DB-005
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Patterns\Services\*.py`
- **Action**: Find loops that execute queries
- **Patterns**: Same as above
- **Success Criteria**: Zero N+1 patterns in pattern services

#### Task 2.6: Trades N+1 Queries
- **Agent ID**: DB-006
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Trades\*.py`
- **Action**: Find loops that execute queries
- **Success Criteria**: Zero N+1 patterns in trade queries

#### Task 2.7: Relationship Loading
- **Agent ID**: DB-007
- **Scope**: All model files
- **Action**: Analyze relationship loading strategies
- **Check**:
  - Lazy loading in loops (causes N+1)
  - Missing `selectinload`/`joinedload` where needed
- **Success Criteria**: Proper eager loading configured

### TRANSACTION MANAGEMENT

#### Task 2.8: Transaction Boundaries
- **Agent ID**: DB-008
- **Scope**: All service files
- **Action**: Find operations that should be atomic but aren't
- **Patterns**:
  - Multiple `session.commit()` calls in single operation
  - Missing transaction wrapper for multi-step operations
- **Success Criteria**: All atomic operations properly transacted

#### Task 2.9: Isolation Level Issues
- **Agent ID**: DB-009
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Database.py`, services
- **Action**: Check for race conditions due to isolation level
- **Check**:
  - Read-then-write patterns without proper locking
  - `SELECT ... FOR UPDATE` where needed
- **Success Criteria**: Proper isolation for concurrent operations

#### Task 2.10: Rollback Handling
- **Agent ID**: DB-010
- **Scope**: All service files
- **Action**: Verify rollback on exceptions
- **Patterns**:
  - `try:.*commit.*except` without rollback
  - Missing rollback in error handlers
- **Success Criteria**: All exceptions trigger rollback

### QUERY OPTIMIZATION

#### Task 2.11: Missing Indexes
- **Agent ID**: DB-011
- **Scope**: Model files, Database.py migrations
- **Action**: Find queries on non-indexed columns
- **Check**:
  - `WHERE` clauses on columns without indexes
  - `ORDER BY` on non-indexed columns
  - Foreign keys without indexes
- **Files**:
  - `c:\fast_swarm\src\Fast_Swarm\Agents\Models\agent_models.py`
  - `c:\fast_swarm\src\Fast_Swarm\Patterns\Models\pattern_models.py`
- **Success Criteria**: All frequently queried columns indexed

#### Task 2.12: Unbounded Queries
- **Agent ID**: DB-012
- **Scope**: All service files
- **Action**: Find SELECT without LIMIT
- **Patterns**:
  - `select\(.*\)` without `.limit(`
  - `session\.exec\(select` without pagination
- **Success Criteria**: All list queries have limits

#### Task 2.13: SELECT * Anti-pattern
- **Agent ID**: DB-013
- **Scope**: All service files
- **Action**: Find queries fetching unnecessary columns
- **Patterns**:
  - `select\(Model\)` when only few columns needed
  - Missing column specification for large tables
- **Success Criteria**: Column selection optimized

#### Task 2.14: Count Query Optimization
- **Agent ID**: DB-014
- **Scope**: All service files
- **Action**: Find inefficient count operations
- **Patterns**:
  - `len\(await session\.exec\(` (fetches all rows to count)
  - Missing `func.count()` usage
- **Success Criteria**: All counts use SQL COUNT

### DATA INTEGRITY

#### Task 2.15: Missing Foreign Key Constraints
- **Agent ID**: DB-015
- **Scope**: All model files
- **Action**: Find relationships without FK constraints
- **Check**: All `parent_a_id`, `parent_b_id`, `agent_id` have FKs
- **Success Criteria**: All relationships have FK constraints

#### Task 2.16: Missing NOT NULL Constraints
- **Agent ID**: DB-016
- **Scope**: All model files
- **Action**: Find columns that should be NOT NULL but aren't
- **Check**: Required business fields have constraints
- **Success Criteria**: Critical columns are NOT NULL

#### Task 2.17: Missing Unique Constraints
- **Agent ID**: DB-017
- **Scope**: All model files
- **Action**: Find business keys without unique constraints
- **Check**: Natural keys like `symbol+timeframe+time` are unique
- **Success Criteria**: All business keys have unique constraints

#### Task 2.18: JSONB Schema Drift
- **Agent ID**: DB-018
- **Scope**: Files using JSONB columns (traits, pattern_weights)
- **Action**: Find inconsistent JSONB structures
- **Check**:
  - `traits` field structure varies
  - Missing keys in JSONB that code expects
- **Success Criteria**: JSONB schemas documented and validated

### MIGRATION SAFETY

#### Task 2.19: Migration Idempotency
- **Agent ID**: DB-019
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Database.py` (_run_migrations)
- **Action**: Verify all migrations are idempotent
- **Check**:
  - `IF NOT EXISTS` for all DDL
  - No data loss on re-run
- **Success Criteria**: All migrations safely re-runnable

#### Task 2.20: Migration Order Dependencies
- **Agent ID**: DB-020
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Database.py`
- **Action**: Check migration execution order
- **Check**:
  - FK references exist before FK creation
  - Column exists before index creation
- **Success Criteria**: No ordering issues in migrations

---

## WAVE 3: ASYNC & CONCURRENCY WARFARE

**Objective**: Eliminate race conditions, deadlocks, and async anti-patterns.

### RACE CONDITIONS

#### Task 3.1: Read-Modify-Write Races
- **Agent ID**: ASYNC-001
- **Scope**: All service files
- **Action**: Find read-then-write without locking
- **Patterns**:
  - `agent = await get_agent\(.*\).*agent\.fitness = .*commit`
  - Increment operations without atomicity
- **Files to Prioritize**:
  - `c:\fast_swarm\src\Fast_Swarm\Agents\Services\fitness_service.py`
  - `c:\fast_swarm\src\Fast_Swarm\Agents\Services\ranking_service.py`
  - `c:\fast_swarm\src\Fast_Swarm\Agents\Hivemind\Services\elo_transfer_service.py`
- **Success Criteria**: All counter updates are atomic

#### Task 3.2: Evolution Race Conditions
- **Agent ID**: ASYNC-002
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Agents\Services\evolution_service.py`
- **Action**: Find races in evolution loop
- **Check**:
  - `_evolution_running` flag without proper locking
  - Concurrent spawn/cull operations
- **Success Criteria**: Evolution operations are serialized

#### Task 3.3: WebSocket State Races
- **Agent ID**: ASYNC-003
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\exchanges\*.py`
- **Action**: Find shared state without locks in WS handlers
- **Patterns**:
  - Instance variables modified from multiple coroutines
  - Missing `asyncio.Lock()` for shared state
- **Success Criteria**: All shared WS state protected by locks

#### Task 3.4: Singleton Initialization Races
- **Agent ID**: ASYNC-004
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Dependencies.py`
- **Action**: Verify thread-safe singleton initialization
- **Check**: `@lru_cache` is thread-safe but verify
- **Success Criteria**: Singletons safely initialized under concurrency

### DEADLOCK DETECTION

#### Task 3.5: Lock Ordering
- **Agent ID**: ASYNC-005
- **Scope**: All files with locks
- **Action**: Find potential lock ordering issues
- **Patterns**:
  - Multiple `async with lock` in different orders
  - Nested lock acquisitions
- **Success Criteria**: Consistent lock ordering documented

#### Task 3.6: Database Deadlocks
- **Agent ID**: ASYNC-006
- **Scope**: All service files
- **Action**: Find potential database deadlock patterns
- **Check**:
  - Long-running transactions
  - Multiple tables updated in inconsistent order
- **Success Criteria**: No deadlock-prone patterns

### ASYNC ANTI-PATTERNS

#### Task 3.7: Blocking Calls in Async
- **Agent ID**: ASYNC-007
- **Scope**: All async functions
- **Action**: Find sync blocking calls in async code
- **Patterns**:
  - `time\.sleep` (should be `asyncio.sleep`)
  - `requests\.` (should be `httpx` or `aiohttp`)
  - `open\(` file operations (should use `aiofiles`)
  - `input\(` in async context
- **Success Criteria**: Zero blocking calls in async functions

#### Task 3.8: Missing Await
- **Agent ID**: ASYNC-008
- **Scope**: All async functions
- **Action**: Find coroutines called without await
- **Patterns**:
  - `session\.exec\(` without `await`
  - `service\.\w+\(` async methods without await
- **Note**: Python usually warns but doesn't error
- **Success Criteria**: All coroutines awaited

#### Task 3.9: Await in Comprehensions
- **Agent ID**: ASYNC-009
- **Scope**: All .py files
- **Action**: Find await in list comprehensions (blocks)
- **Patterns**:
  - `\[await.*for.*in`
  - Should use `asyncio.gather`
- **Success Criteria**: Parallel operations use gather

#### Task 3.10: Task Cancellation Handling
- **Agent ID**: ASYNC-010
- **Scope**: All files with `asyncio.create_task`
- **Action**: Verify proper cancellation handling
- **Check**:
  - Tasks stored for later cancellation
  - `CancelledError` properly handled
- **Files**:
  - `c:\fast_swarm\src\Fast_Swarm\Main.py`
  - `c:\fast_swarm\src\Fast_Swarm\Infrastructure\Services\task_supervisor.py`
- **Success Criteria**: All tasks can be cleanly cancelled

### CONCURRENCY PRIMITIVES

#### Task 3.11: Semaphore Usage
- **Agent ID**: ASYNC-011
- **Scope**: All .py files
- **Action**: Find unbounded concurrent operations
- **Check**:
  - Batch operations without semaphore limits
  - Missing backpressure mechanisms
- **Success Criteria**: All concurrent ops bounded by semaphores

#### Task 3.12: Event/Condition Usage
- **Agent ID**: ASYNC-012
- **Scope**: All .py files
- **Action**: Analyze async coordination primitives
- **Check**:
  - Proper Event/Condition usage
  - No busy-waiting patterns
- **Success Criteria**: Efficient async coordination

### SHUTDOWN HANDLING

#### Task 3.13: Graceful Shutdown
- **Agent ID**: ASYNC-013
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Main.py`
- **Action**: Verify graceful shutdown sequence
- **Check**:
  - All tasks cancelled in order
  - Database connections closed
  - WebSockets disconnected cleanly
- **Success Criteria**: Clean shutdown without warnings

#### Task 3.14: Background Task Cleanup
- **Agent ID**: ASYNC-014
- **Scope**: All background tasks
- **Action**: Verify tasks are tracked and cancellable
- **Pattern**: `asyncio.create_task` results stored
- **Success Criteria**: All background tasks tracked

#### Task 3.15: Resource Cleanup on Error
- **Agent ID**: ASYNC-015
- **Scope**: All async context managers
- **Action**: Verify cleanup runs on exceptions
- **Check**: `finally` blocks properly clean up
- **Success Criteria**: Resources released on any exit path

---

## WAVE 4: TYPE SAFETY INQUISITION

**Objective**: Ensure complete type coverage and Pydantic model validation.

### TYPE ANNOTATION COMPLETENESS

#### Task 4.1: Missing Function Types
- **Agent ID**: TYPE-001
- **Scope**: All .py files
- **Action**: Find functions without type annotations
- **Pattern**: `def \w+\([^:]*\):` (no return type)
- **Success Criteria**: 100% type annotation coverage

#### Task 4.2: Missing Variable Types
- **Agent ID**: TYPE-002
- **Scope**: All .py files
- **Action**: Find variables with complex types but no annotation
- **Pattern**: Untyped dict/list assignments
- **Success Criteria**: All complex variables typed

#### Task 4.3: Any Type Usage
- **Agent ID**: TYPE-003
- **Scope**: All .py files
- **Action**: Find excessive `Any` type usage
- **Patterns**:
  - `Dict\[str, Any\]`
  - `List\[Any\]`
  - `: Any` parameter types
- **Success Criteria**: Minimize Any usage with specific types

#### Task 4.4: Optional vs Union
- **Agent ID**: TYPE-004
- **Scope**: All .py files
- **Action**: Find inconsistent optional handling
- **Check**:
  - `Optional[X]` vs `X | None` consistency
  - Missing `None` checks for Optional types
- **Success Criteria**: Consistent optional handling

### PYDANTIC MODEL VALIDATION

#### Task 4.5: Model Field Validators
- **Agent ID**: TYPE-005
- **Scope**: All model files
- **Action**: Find models missing validators
- **Check**:
  - Numeric fields without range validators
  - String fields without length validators
  - Enum fields with raw strings
- **Files**:
  - `c:\fast_swarm\src\Fast_Swarm\Agents\Models\*.py`
  - `c:\fast_swarm\src\Fast_Swarm\Patterns\Models\*.py`
  - `c:\fast_swarm\src\Fast_Swarm\Trading\Models\*.py`
- **Success Criteria**: All critical fields have validators

#### Task 4.6: Request Model Validation
- **Agent ID**: TYPE-006
- **Scope**: All router files
- **Action**: Find endpoints with missing request validation
- **Patterns**:
  - `@router\.post` without Pydantic body model
  - `request: dict` instead of typed model
- **Success Criteria**: All request bodies use Pydantic models

#### Task 4.7: Response Model Completeness
- **Agent ID**: TYPE-007
- **Scope**: All router files
- **Action**: Find endpoints without response_model
- **Pattern**: `@router\.(get|post).*\)$` (no response_model)
- **Success Criteria**: All endpoints have response_model

#### Task 4.8: Model Serialization
- **Agent ID**: TYPE-008
- **Scope**: All model files
- **Action**: Check for serialization issues
- **Check**:
  - DateTime serialization format
  - UUID serialization
  - JSONB field serialization
- **Success Criteria**: All models serialize correctly

### SQLMODEL SPECIFICS

#### Task 4.9: SQLModel Field Definitions
- **Agent ID**: TYPE-009
- **Scope**: All SQLModel files
- **Action**: Verify proper Field usage
- **Check**:
  - Primary keys properly defined
  - Foreign keys properly typed
  - Default factories for mutable defaults
- **Success Criteria**: All SQLModel fields correctly defined

#### Task 4.10: SQLModel vs Pydantic
- **Agent ID**: TYPE-010
- **Scope**: All model files
- **Action**: Verify correct base class usage
- **Check**:
  - `table=True` only for DB models
  - Schema-only models use pure Pydantic
- **Success Criteria**: Correct inheritance patterns

### TYPE NARROWING

#### Task 4.11: None Guard Patterns
- **Agent ID**: TYPE-011
- **Scope**: All .py files
- **Action**: Find Optional access without None checks
- **Patterns**:
  - `\.attribute` on Optional without `if x is not None`
  - `result\.` without checking query result
- **Success Criteria**: All Optional values guarded

#### Task 4.12: Union Type Handling
- **Agent ID**: TYPE-012
- **Scope**: All .py files
- **Action**: Find Union types without discrimination
- **Check**: `isinstance` checks before Union member access
- **Success Criteria**: All Unions properly discriminated

### GENERIC TYPES

#### Task 4.13: Generic Service Patterns
- **Agent ID**: TYPE-013
- **Scope**: All service files
- **Action**: Find generic patterns without type parameters
- **Check**: Generic functions properly parameterized
- **Success Criteria**: All generics properly typed

#### Task 4.14: Collection Type Specificity
- **Agent ID**: TYPE-014
- **Scope**: All .py files
- **Action**: Find vague collection types
- **Patterns**:
  - `list` instead of `list[Agent]`
  - `dict` instead of `dict[str, float]`
- **Success Criteria**: All collections have element types

### CALLBACK TYPES

#### Task 4.15: Callback Function Types
- **Agent ID**: TYPE-015
- **Scope**: All files with callbacks
- **Action**: Find untyped callback parameters
- **Pattern**: `callback` parameter without Callable type
- **Files**:
  - `c:\fast_swarm\src\Fast_Swarm\Infrastructure\Services\stream_manager_service.py`
- **Success Criteria**: All callbacks have Callable types

### ENUM VALIDATION

#### Task 4.16: String Literal vs Enum
- **Agent ID**: TYPE-016
- **Scope**: All files
- **Action**: Find string literals that should be enums
- **Patterns**:
  - `status = "active"` (should be Enum)
  - `phase = "running"` (should be Enum)
- **Success Criteria**: All categorical values use Enums

### NUMERIC TYPES

#### Task 4.17: Float vs Decimal
- **Agent ID**: TYPE-017
- **Scope**: All files with money/price calculations
- **Action**: Find float usage for financial calculations
- **Check**: Should use Decimal for money
- **Note**: May be acceptable for trading backtests
- **Success Criteria**: Document financial type decisions

#### Task 4.18: Int Overflow Potential
- **Agent ID**: TYPE-018
- **Scope**: All files with counters
- **Action**: Find large number operations
- **Check**: Trade counts, iteration counts that might overflow
- **Success Criteria**: No overflow-prone patterns

### TYPE EXPORTS

#### Task 4.19: __all__ Definitions
- **Agent ID**: TYPE-019
- **Scope**: All `__init__.py` files
- **Action**: Verify type exports are complete
- **Check**: All public types in `__all__`
- **Success Criteria**: Clean public API surface

#### Task 4.20: Protocol Classes
- **Agent ID**: TYPE-020
- **Scope**: All service interfaces
- **Action**: Find implicit interfaces that should be Protocols
- **Check**: Duck-typed parameters that should have Protocol
- **Success Criteria**: Structural typing via Protocols where appropriate

---

## WAVE 5: TRADING LOGIC VALIDATION

**Objective**: Verify trading system correctness, especially division safety, fitness calculations, and economic validity.

### DIVISION BY ZERO GUARDS

#### Task 5.1: Fitness Calculation Division
- **Agent ID**: TRADE-001
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Agents\Services\fitness_service.py`
- **Action**: Find all divisions and verify guards
- **Patterns**:
  - `/ std` (std can be 0)
  - `/ drawdown` (drawdown can be 0)
  - `/ total_trades` (can be 0)
  - `/ win_rate` (can be 0)
- **Success Criteria**: ALL divisions guarded with `if x > 0 else default`

#### Task 5.2: Metric Calculation Division
- **Agent ID**: TRADE-002
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\local_agents\shared\metrics.py`
- **Action**: Find all divisions and verify guards
- **Check**:
  - Sharpe: `mean / std`
  - Sortino: `mean / downside_std`
  - Calmar: `return / max_drawdown`
- **Success Criteria**: Zero divisions fully guarded

#### Task 5.3: Pattern Matching Division
- **Agent ID**: TRADE-003
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Patterns\Services\pattern_matching_service.py`
- **Action**: Find divisions in pattern evaluation
- **Check**: Percentage calculations, ratios
- **Success Criteria**: All pattern divisions guarded

#### Task 5.4: Backtest Division Safety
- **Agent ID**: TRADE-004
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Agents\Services\backtest_service.py`
- **Action**: Find divisions in backtest calculations
- **Check**: Position sizing, P&L calculations
- **Success Criteria**: Backtest math fully guarded

#### Task 5.5: Indicator Division Safety
- **Agent ID**: TRADE-005
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\local_agents\shared\indicators.py`
- **Action**: Find divisions in technical indicators
- **Check**:
  - RSI formula
  - Bollinger Bands std
  - ATR calculations
- **Success Criteria**: All indicator formulas guarded

### ECONOMIC VALIDITY

#### Task 5.6: Sortino vs Sharpe Usage
- **Agent ID**: TRADE-006
- **Scope**: All fitness and ranking files
- **Action**: Verify Sortino is primary metric (not Sharpe)
- **Pattern**: Search for `sharpe_ratio` used in fitness
- **Note**: Per CLAUDE.md, Sortino is primary
- **Success Criteria**: Sortino used for primary fitness

#### Task 5.7: Alpha Calculation
- **Agent ID**: TRADE-007
- **Scope**: Fitness and metrics files
- **Action**: Verify Alpha = Agent CAGR - Buy&Hold CAGR
- **Check**: Benchmark comparison is correct
- **Success Criteria**: Alpha correctly computed

#### Task 5.8: Win Rate Thresholds
- **Agent ID**: TRADE-008
- **Scope**: All fitness files
- **Action**: Verify win rate bounds (0-1 or 0-100%)
- **Check**: No win rates > 100% or < 0%
- **Success Criteria**: Win rate always in valid range

#### Task 5.9: Drawdown Calculations
- **Agent ID**: TRADE-009
- **Scope**: Metrics and fitness files
- **Action**: Verify max drawdown calculation
- **Check**:
  - Peak tracking is correct
  - Drawdown is always negative or zero
  - Percentage calculation is correct
- **Success Criteria**: Drawdown math verified

#### Task 5.10: Position Sizing Limits
- **Agent ID**: TRADE-010
- **Scope**: Backtest and trading files
- **Action**: Verify position limits enforced
- **Check**:
  - No positions > 100% of capital (unless leverage intended)
  - Kelly criterion bounded
  - Risk per trade limited
- **Success Criteria**: Position sizing safe

### LOOKAHEAD BIAS

#### Task 5.11: Future Data Usage
- **Agent ID**: TRADE-011
- **Scope**: Backtest service files
- **Action**: Find potential lookahead bias
- **Patterns**:
  - `candles\[i+1\]` type access
  - Using data with future timestamps
  - Exit decisions using entry price arrays
- **Success Criteria**: Zero lookahead bias

#### Task 5.12: Indicator Lookahead
- **Agent ID**: TRADE-012
- **Scope**: Indicator calculation files
- **Action**: Find indicators using future values
- **Check**: All indicators use only past/current data
- **Success Criteria**: No indicator lookahead

### EVOLUTION LOGIC

#### Task 5.13: Fitness Score Range
- **Agent ID**: TRADE-013
- **Scope**: Fitness calculation files
- **Action**: Verify fitness score bounds
- **Check**:
  - Fitness in reasonable range (e.g., -10 to 10)
  - No NaN or Inf values
- **Success Criteria**: Fitness always valid number

#### Task 5.14: Quintile Ranking
- **Agent ID**: TRADE-014
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Agents\Services\ranking_service.py`
- **Action**: Verify 5-tier quintile system
- **Check**:
  - Tiers 0-4 (not 1-5)
  - Percentile calculation correct
- **Success Criteria**: Quintile system correct

#### Task 5.15: ELO Calculations
- **Agent ID**: TRADE-015
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Agents\Hivemind\Services\elo_transfer_service.py`
- **Action**: Verify ELO math
- **Check**:
  - K-factor appropriate
  - Expected score calculation correct
  - ELO updates symmetric
- **Note**: ELO only for Hivemind voting
- **Success Criteria**: ELO math correct

### TRAIT MUTATION

#### Task 5.16: Mutation Bounds
- **Agent ID**: TRADE-016
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Agents\Services\trait_service.py`
- **Action**: Verify trait mutations stay in bounds
- **Check**:
  - Risk tolerance in [0, 1]
  - Timeframe preferences valid
  - Pattern weights sum correctly
- **Success Criteria**: All traits bounded

#### Task 5.17: Crossover Logic
- **Agent ID**: TRADE-017
- **Scope**: Evolution and trait services
- **Action**: Verify genetic crossover is correct
- **Check**:
  - Two parents combined correctly
  - Offspring traits valid
- **Success Criteria**: Crossover produces valid agents

### PATTERN VALIDATION

#### Task 5.18: Pattern Condition Bounds
- **Agent ID**: TRADE-018
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Patterns\Models\pattern_models.py`
- **Action**: Verify pattern conditions valid
- **Check**:
  - RSI ranges in [0, 100]
  - Price comparisons valid
  - Indicator thresholds reasonable
- **Success Criteria**: All pattern conditions bounded

#### Task 5.19: Pattern Signal Generation
- **Agent ID**: TRADE-019
- **Scope**: Pattern matching and discovery files
- **Action**: Verify signal generation logic
- **Check**:
  - Entry signals have exit conditions
  - No contradictory signals
- **Success Criteria**: Pattern signals coherent

### TRADING EXECUTION

#### Task 5.20: Paper Trading Logic
- **Agent ID**: TRADE-020
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Trading\Services\agent_paper_trading_service.py`
- **Action**: Verify paper trading simulation
- **Check**:
  - Slippage modeling
  - Fill assumptions
  - Position tracking
- **Success Criteria**: Paper trading realistic

#### Task 5.21: Approval Queue Logic
- **Agent ID**: TRADE-021
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Trading\Services\approval_queue_service.py`
- **Action**: Verify trade approval flow
- **Check**:
  - Queue ordering correct
  - Expiration handled
  - Duplicate prevention
- **Success Criteria**: Approval queue reliable

#### Task 5.22: Live Execution Guards
- **Agent ID**: TRADE-022
- **Scope**: `c:\fast_swarm\src\Fast_Swarm\Trading\Services\live_execution_service.py`
- **Action**: Verify live trading safeguards
- **Check**:
  - Position limits enforced
  - Loss limits in place
  - Kill switches exist
- **Success Criteria**: Live trading has safety rails

### MARKET DATA VALIDATION

#### Task 5.23: Price Validation
- **Agent ID**: TRADE-023
- **Scope**: Infrastructure/Services market data files
- **Action**: Verify price data validation
- **Check**:
  - No negative prices
  - No zero prices (for divisors)
  - OHLC consistency (H >= L, etc.)
- **Success Criteria**: Price data validated

#### Task 5.24: Volume Validation
- **Agent ID**: TRADE-024
- **Scope**: Market data and candle files
- **Action**: Verify volume handling
- **Check**:
  - No negative volume
  - Zero volume handled correctly
- **Success Criteria**: Volume data validated

#### Task 5.25: Timestamp Validation
- **Agent ID**: TRADE-025
- **Scope**: All market data files
- **Action**: Verify timestamp handling
- **Check**:
  - Timezone consistency (UTC expected)
  - No future timestamps
  - Monotonic sequence for candles
- **Success Criteria**: Timestamp data valid

---

## WAVES 6-15: REMAINING REVIEW CATEGORIES

For brevity, the remaining waves follow the same detailed structure:

### WAVE 6: ERROR HANDLING CRUSADE (15 tasks)
- Exception coverage
- HTTP error handling
- Database error handling
- WebSocket error handling
- External service errors
- Async error handling

### WAVE 7: PERFORMANCE ANNIHILATION (20 tasks)
- Algorithm complexity
- Memory efficiency
- Database performance
- Async performance
- Network optimization
- Caching strategy
- Resource loading
- Profiling targets

### WAVE 8: TEST COVERAGE BLITZ (20 tasks)
- Coverage analysis by domain
- Test quality
- Edge case coverage
- Integration test gaps
- Soundness test gaps
- Property-based testing
- Fixture quality
- Mocking review

### WAVE 9: CODE QUALITY PURGE (25 tasks)
- Code smells
- Anti-patterns
- Naming conventions
- Import organization
- Comment quality
- Code consistency
- Design patterns
- SOLID principles

### WAVE 10: DOCUMENTATION AUDIT (10 tasks)
- Docstring coverage
- API documentation
- Type documentation
- README and guides

### WAVE 11: FRONTEND SECURITY & QUALITY (15 tasks)
- XSS vulnerabilities
- CSRF protection
- Input validation
- Sensitive data handling
- CSS quality
- HTML quality
- JavaScript quality

### WAVE 12: CONFIGURATION & SECRETS (10 tasks)
- Secret management
- Configuration validation
- Feature flags
- Database config
- Logging config
- Runtime config

### WAVE 13: DEPENDENCY ANALYSIS (10 tasks)
- Dependency inventory
- Security analysis
- License compliance
- Version management
- Import analysis

### WAVE 14: INTEGRATION & CONTRACT TESTING (15 tasks)
- API contract validation
- WebSocket contracts
- Database contracts
- Service contracts
- LLM integration
- Exchange integration
- Orchestrator contracts

### WAVE 15: FINAL SYNTHESIS (5 tasks)
- Critical issues summary
- High priority summary
- Technical debt inventory
- Remediation roadmap
- Final report generation

---

## EXECUTION INSTRUCTIONS

### For Haiku Sub-Agents

Each task should:

1. **Read the specific files** mentioned in the task scope
2. **Apply the patterns/checks** described
3. **Document findings** with:
   - File path
   - Line number (if applicable)
   - Code snippet
   - Severity (CRITICAL/HIGH/MEDIUM/LOW)
   - Suggested fix
4. **Report success criteria** status

### Output Format

Each agent produces JSON:

```json
{
  "task_id": "SEC-001",
  "status": "completed",
  "files_scanned": 45,
  "findings": [
    {
      "file": "c:\\fast_swarm\\src\\Fast_Swarm\\path\\to\\file.py",
      "line": 123,
      "severity": "HIGH",
      "category": "SQL Injection",
      "description": "Raw SQL with f-string interpolation",
      "code_snippet": "text(f\"SELECT * FROM {table}\")",
      "suggested_fix": "Use parameterized query"
    }
  ],
  "success_criteria_met": true,
  "summary": "Found 3 potential SQL injection vulnerabilities"
}
```

### Parallelization Rules

1. **Wave N+1** cannot start until **Wave N** completes
2. **Within a wave**, all tasks run in parallel
3. **Synthesis wave** requires all previous waves
4. Each task is **independent** - no inter-task dependencies within a wave

### Estimated Execution

| Wave | Tasks | Parallel Agents | Est. Time |
|------|-------|-----------------|-----------|
| 0 | 5 | 5 | 2 min |
| 1 | 25 | 25 | 5 min |
| 2 | 20 | 20 | 4 min |
| 3 | 15 | 15 | 3 min |
| 4 | 20 | 20 | 4 min |
| 5 | 25 | 25 | 5 min |
| 6 | 15 | 15 | 3 min |
| 7 | 20 | 20 | 4 min |
| 8 | 20 | 20 | 4 min |
| 9 | 25 | 25 | 5 min |
| 10 | 10 | 10 | 2 min |
| 11 | 15 | 15 | 3 min |
| 12 | 10 | 10 | 2 min |
| 13 | 10 | 10 | 2 min |
| 14 | 15 | 15 | 3 min |
| 15 | 5 | 5 | 5 min |
| **Total** | **230** | **255 agent-tasks** | **~56 min** |

---

## SUCCESS METRICS

The review is successful when:

1. **Zero CRITICAL** issues remain unaddressed
2. **All HIGH** issues have remediation plans
3. **Test coverage gaps** are documented with priorities
4. **Security vulnerabilities** are catalogued and triaged
5. **Performance bottlenecks** are identified and documented
6. **Documentation gaps** are filled or ticketed
7. **Final report** is comprehensive and actionable

---

## APPENDIX: FILE INVENTORY

### Python Files by Domain

```
Agents/ (35 files)
  Services/ (14 files)
  Models/ (3 files)
  Routers/ (3 files)
  Hivemind/
    Services/ (9 files)
    Models/ (2 files)
    Routers/ (1 file)

Patterns/ (8 files)
Infrastructure/ (22 files)
Trading/ (9 files)
Evolution/ (3 files)
System/ (15 files)
exchanges/ (5 files)
Dashboard/ (7 files)
Tests/ (78 files)
```

---

*END OF MEGA REVIEW PLAN*
*Total Tasks: 230*
*Estimated Agent-Tasks: 255*
*THE FIREWALLS WILL QUAKE*
