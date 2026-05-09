# Pattern Leaderboard — Investigation & Fix Plan

Status: DRAFT — created for team handoff

Summary
-------
- Problem: The `Pattern Rankings` dashboard shows stale and incorrect counts that don't match the underlying `discovered_patterns` data. The UI statistics and pattern table appear out-of-sync and do not update as new patterns or votes are written to the DB.
- High-level root causes found:
  1. Origin value case mismatch — producers sometimes write `origin` as `CHAOS` (uppercase) while API queries expect `chaos` (lowercase). This causes counts (e.g., chaos/academic/technical) to be computed incorrectly.
  2. Multiple deployments / dashboards target different worker URLs or different DB instances (some UI assets reference absolute URLs to older worker deployments) leading to stale data being shown.

This document outlines a prioritized, step-by-step engineering plan for fixing the problem, verifying the fix, and rolling it out safely.

Goals & Acceptance Criteria ✅
-------------------------------
- Dashboard counts and table must match the real-time values in the `discovered_patterns` D1 table.
- UI should auto-refresh and reflect changes made by backend jobs (evolution, head-to-head testing, academic agents) within a short delay (30 seconds or less when the worker and DB are operating normally).
- All producers of pattern rows must follow normalized schema (origin/status lowercase) and tests should prevent regressions.

Quick Proof-of-Root-Cause (what we found)
----------------------------------------
- `cloudflare-agents/evolution-agent-simple.ts` stores patterns using `p.origin || 'CHAOS'` (uppercase). (Fix: store `chaos` lowercased.)
- `/api/patterns` query in the same worker counts origins using `origin = 'chaos'` (lowercase), so uppercase origins won't be counted.
- Dashboards exist in multiple places and some pages fetch absolute worker URLs (e.g., `coinswarm-evolution-agent.bamn86.workers.dev`) which can point at older workers/DB instances.

Step-by-step Technical Plan (Prioritized)
---------------------------------------

Phase 0 — Safety & discovery (fast checks)
1) Confirm which worker and D1 instance the live dashboard is calling (check all variants of `patterns.html`/`architecture.html` and `public/patterns.html`).
   - Search deployed asset references for `https://*.workers.dev/api/patterns` — unify or update to canonical API URL.
2) Capture current DB state for an audit: backup or run export:
   - SELECT origin, status, count(*) GROUP BY origin, status;

Phase 1 — Small immediate fixes (low-risk, quick)
1) Normalize write-time values: change any code that inserts or updates `origin` or `status` to use lowercase values (e.g., `'chaos'`, `'academic'`, `'technical'` and `'testing'`/`'winning'` as statuses).
   - Files to update: 
     - `cloudflare-agents/evolution-agent-simple.ts` (storePatterns, other inserts)
     - `cloudflare-agents/technical-patterns-agent.ts` (INSERT/UPDATE statements)
     - `cloudflare-agents/academic-papers-agent.ts` (INSERT/UPDATE statements)
     - `cloudflare-agents/pattern-explainability-agent.ts` (if it writes to discovered_patterns)
   - Make writes use `.toLowerCase()` or explicitly set lowercase strings.

2) Make API queries defensive so they will correctly count regardless of case (short-term): use LOWER(origin) and LOWER(status) in SELECT COUNT() queries.
   - `SELECT COUNT(*) FROM discovered_patterns WHERE LOWER(origin) = 'chaos'` etc.

Phase 2 — Data migration (fix historical rows)
1) Add a migration SQL to normalize existing DB rows — run it once and verify.
   - Example SQL (run on D1 / local copy):

```
UPDATE discovered_patterns SET origin = LOWER(origin) WHERE origin IS NOT NULL;
UPDATE discovered_patterns SET status = LOWER(status) WHERE status IS NOT NULL;

-- Optional data cleanups / sanity checks
DELETE FROM discovered_patterns WHERE TRIM(pattern_id) = '' OR pattern_id IS NULL;
-- Verify
SELECT origin, status, COUNT(*) FROM discovered_patterns GROUP BY origin, status;
```

2) If the table contains multiple environment copies or duplicates (e.g., same pattern_id across different DBs), identify canonical D1 DB and ensure dashboards point there.

Phase 3 — UI & endpoint unification
1) Update all dashboard assets to use relative API fetches (unless absolute canonical URL is required) — this reduces cross-deployment confusion.
   - `cloudflare-agents/dashboards/patterns.html` & `cloudflare-agents/public/patterns.html` should fetch `/api/patterns` relative to current origin or use a single canonical worker base URL stored in a configuration block.
2) Add a redirect/proxy or update routing so all dashboard hosts call the correct, canonical worker and D1 instance.

Phase 4 — Tests & CI
1) Add unit & integration tests for both writers and the API endpoints:
   - Test that `storePatterns()` stores origin lowercase.
   - Test `/api/patterns` and `/api/stats` return counts consistent with direct DB queries.
2) Add a quick end-to-end smoke test in `scripts/test-workers.sh` or test suite that validates `/api/patterns` and `/api/stats` for expected keys and count consistency after a small test insert.

Phase 5 — Monitoring, rollout & rollback
1) Deploy the fixes to staging (or `claude/**` branch) and validate.
2) Run migration on staging D1 and confirm no surprises.
3) Deploy to production during a scheduled maintenance window (if production DB is shared).
4) Add monitoring/alerting: track errors, and add a periodic integration test to verify the API and UI counts match.

Detailed Developer Tasks (suggested PR breakdown)
-----------------------------------------------
PR 1 — Normalization and defensive queries (small)
- Normalize origin/status at write-time.
- Update API queries to use LOWER() where necessary.
- Add unit tests for write/read.

PR 2 — Migration & verification (one-off D1 migration)
- Add migration SQL (as a single file / migration script).
- Add a verification script to run after migration.

PR 3 — UI canonicalization & smoke tests
- Make all dashboards fetch the canonical API endpoint consistently.
- Add an E2E smoke test (curl + jq or a node script) to verify live responses.

PR 4 — CI/Monitoring
- Add automated tests that run against the D1 test environment.
- Add an automated smoke-check (e.g., in `scripts/test-workers.sh`) to run after deploy.

Migration & DB Update Example (safe approach)
-------------------------------------------
1) Make a staging migration first:

```
npx wrangler d1 execute coinswarm-evolution --command "UPDATE discovered_patterns SET origin = LOWER(origin) WHERE origin IS NOT NULL;"
npx wrangler d1 execute coinswarm-evolution --command "UPDATE discovered_patterns SET status = LOWER(status) WHERE status IS NOT NULL;"

-- Validate
npx wrangler d1 execute coinswarm-evolution --command "SELECT origin, status, COUNT(*) FROM discovered_patterns GROUP BY origin, status;"
```

2) After validation, apply same in production (coordinate with DB owner/team).

Testing / Validation Checklist
------------------------------
Functional checks
- After normalization and migration: counts shown on dashboard must equal DB counts for the same queries.
- Test insert: create a test pattern with origin `chaos` and status `testing` and verify UI updates within ~30s.

Automated tests to add
- Unit tests for storePatterns() to assert lowercase `origin`/`status`.
- Integration test hitting `/api/patterns` and `/api/stats` validating returned stats vs DB.

Deployment instructions
-----------------------
1) Deploy PR 1 to staging worker and run unit tests.
2) Run staging DB migration and verify results.
3) Deploy PR 2 and PR 3 to staging and perform E2E smoke tests.
4) Deploy to production (off-peak), run migration, validate, and monitor.

Rollback plan
-------------
- If the migration creates unexpected issues, the concise rollback is:
  1) Revert the code change (PR) by deploying previous version.
  2) If necessary, rollback DB to pre-migration snapshot (if one exists) or run targeted SQL to revert the origin/status fields to prior values.

Security & operational notes (critical) ⚠️
--------------------------------------
- Do not hardcode Cloudflare account IDs / API tokens into any files. Use the deployment docs and `wrangler secret put` for secrets.
- Follow the repo's deployment guide (`CLOUDFLARE_DEPLOYMENT_GUIDE.md`) — prefer `wrangler deploy` and verify that the version is active (watch for Git Integration vs GitHub Actions conflicts).

Owners & Suggested Assignments
------------------------------
- Pattern DB and API fixes: evolution-agent / backend engineer (owner)
- UI canonicalization and smoke tests: frontend/dashboards engineer
- Migration and DB validation: data/DB team (approval required for production migration)

Timeline & Priority
-------------------
- Priority: High — dashboards are critical to monitoring system health.
- Target ETA: 2–4 working days across a small team (split across PRs and one staged migration).

Appendix: concrete code snippets
--------------------------------
1) Write-time normalization (example change):

```ts
// BEFORE
p.origin || 'CHAOS'

// AFTER
(p.origin ? String(p.origin).toLowerCase() : 'chaos')
```

2) Defensive DB count (example):

```sql
SELECT COUNT(*) AS count FROM discovered_patterns WHERE LOWER(origin) = 'chaos';
```

3) Add a smoke-test (curl) example for `/api/patterns`:

```bash
curl -s "https://YOUR-WORKER.workers.dev/api/patterns?origin=all&status=all&min_runs=3&limit=50" | jq '.'
```

If you'd like, next I can:
- Draft the concrete PR for `evolution-agent-simple.ts` (storePatterns fix + unit tests), or
- Draft a migration SQL file and a small verification script to run on staging.

---
Generated: 2025-11-30
