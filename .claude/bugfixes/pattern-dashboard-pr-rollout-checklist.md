# Pattern Dashboard — PR & Rollout Checklist

Use this checklist when creating PRs and performing staged rollouts for the pattern dashboard fixes.

Pre-PR — Development checklist
- [ ] Branch from `main` or a `claude/**` feature branch (per repo policy). Avoid direct pushes to `main`.
- [ ] Add unit tests for any code that writes to `discovered_patterns` ensuring origin/status are stored lowercase.
- [ ] Add integration test(s) for endpoints `/api/patterns` and `/api/stats` validating returned stats vs DB queries.
- [ ] Add or update migration file: `cloudflare-agents/migrations/003-normalize-discovered_patterns-origin-status.sql` already present — include tests that cover migration (staging only).
- [ ] Add script(s) to `scripts/` for verification (`scripts/verify-patterns-migration.sh`). Document usage.

PR description — required content
- Summary: short description of the problem and fix.
- Root cause(s) discovered and reference this plan document: `docs/bugfixes/pattern-dashboard-fix-plan.md`.
- Files changed (highlight producers of `discovered_patterns` and API handlers).
- Migration steps required (include 'staging-first' instructions), including the `wrangler d1 execute` commands.
- Test instructions and smoke test commands used to validate.
- Backout/rollback plan if something goes wrong.

Code review guide
- Confirm all pattern writes explicitly set origin/status to lowercase.
- Confirm API queries are defensive (use LOWER(...) or rely on normalized DB values).
- Confirm any SQL statements include `WHERE` clauses to prevent unintended full-table changes.
- Confirm no secrets or hard-coded worker account IDs are added.
- Confirm unit and integration tests pass.

Staging rollout (recommended order)
1) Deploy PR to staging worker (use `wrangler deploy` / GH Actions for the `claude/**` branch).
2) Run migration on the *staging* D1 database:

```bash
# Run migration script (staging):
npx wrangler d1 execute coinswarm-evolution-staging --file=cloudflare-agents/migrations/003-normalize-discovered_patterns-origin-status.sql

# Validate with the verification script (connect to staging worker):
WORKER_URL=https://coinswarm-evolution-agent-staging.workers.dev ./scripts/verify-patterns-migration.sh
```

3) Run the smoke tests and confirm the dashboard reflects correct counts.

Production rollout (after successful staging)
1) Schedule a maintenance window if production is sensitive.
2) Merge PR to `main` and deploy to production worker using GitHub Actions (ensure production `wrangler.toml` and account settings are correct).
3) Run migration on the production D1 instance:

```bash
npx wrangler d1 execute coinswarm-evolution --file=cloudflare-agents/migrations/003-normalize-discovered_patterns-origin-status.sql
```

4) Run verification script against production (set WORKER_URL to production worker) and validate.

Automated verification (CI)
- Add a job that runs integration queries against a CI D1 test database (or spin up a disposable D1 instance in pipeline) and checks:
  - storePatterns writes lowercase origin/status
  - /api/patterns returns a stats object with keys: total, winning, chaos, academic, technical

Rollback plan (if production issues)
- Code rollback: Revert the deployed worker to the previous version (use GitHub Actions to revert or `wrangler deploy` with the previous tag).
- DB rollback: If the migration caused regressions and there's a DB snapshot, restore snapshot; otherwise revert using corrective SQL (e.g., set origin/status back to previous values if recorded in an audit table). Always coordinate with DB owner.

Communication & approvals
- DB migration must be approved by the DB steward/owner. Tag them on the PR.
- Auto-schedule a short follow-up check 30 minutes after deployment to confirm dashboard behavior.

Post-deploy monitoring
- Confirm the dashboard counts equal the DB counts every 5 minutes for the next 2 hours.
- Check worker error/exception logs for any unexpected failures.
- Verify smoke-test script passes on CI after deploying.

Notes
- Please refer to `docs/bugfixes/pattern-dashboard-fix-plan.md` for full context and recommended code changes.
