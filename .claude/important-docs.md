# Critical Documentation for Claude Code

**⚠️ MUST READ before making changes to deployment configuration ⚠️**

## Essential Reading

### 1. Cloudflare Deployment Guide (CRITICAL)
**File:** `/CLOUDFLARE_DEPLOYMENT_GUIDE.md`

**When to read:**
- Before modifying any GitHub Actions workflows
- Before changing wrangler.toml configurations
- When debugging deployment issues
- When workers deploy but don't activate
- When setting up new workers

**Key Topics:**
- Versions vs Deployments (critical difference)
- Git Integration vs GitHub Actions (causes conflicts)
- Why deployed code might not be active
- How to troubleshoot version activation issues

### 2. Deployment Workflows
**File:** `.github/workflows/deploy-cloudflare-workers.yml`

**Purpose:**
- Unified deployment for all 14 Cloudflare Workers
- Conditional deployment (only deploys changed workers)
- Supports `claude/**` branch pattern

### 3. Worker Configurations
**Location:** `cloudflare-agents/wrangler-*.toml`

**Important:**
- Each worker has its own wrangler config
- Account ID should be set via environment variables
- Never hardcode secrets in toml files

## Common Issues & Quick Fixes

### Issue: "Deployed but not active"
**File to check:** `CLOUDFLARE_DEPLOYMENT_GUIDE.md` → "Common Problems"
**Quick fix:** Disable Git Integration in Cloudflare dashboard

### Issue: "Works on main, not on feature branches"
**File to check:** `CLOUDFLARE_DEPLOYMENT_GUIDE.md` → "Git Integration vs GitHub Actions"
**Quick fix:** Update production branch setting or disable Git Integration

### Issue: "How do I add a new worker?"
**Files to modify:**
1. Create `wrangler-[worker-name].toml` in `cloudflare-agents/`
2. Update `.github/workflows/deploy-cloudflare-workers.yml` (add to filters and deployment steps)
3. Reference: Search for "dashboards" in workflow to see example

## Project-Specific Context

### Account Details
- **Cloudflare Account ID:** `8a330fc6c339f031a73905d4ca2f3e5d`
- **Workers Count:** 14 (12 TypeScript + 2 JavaScript)
- **Deployment Method:** GitHub Actions (Git Integration should be disabled)

### Branch Strategy
- **Main branch:** `main`
- **Claude Code branches:** `claude/**` (all supported)
- **Deployment trigger:** Any push to supported branches

### Critical Don'ts
1. ❌ Don't enable both Git Integration AND GitHub Actions
2. ❌ Don't use `wrangler versions upload` in CI/CD
3. ❌ Don't hardcode account IDs in wrangler.toml files
4. ❌ Don't assume GitHub Actions success = version activated

### 🔒 SECURITY - API Keys & Secrets (CRITICAL)

**NEVER COMMIT SECRETS TO GIT - THIS IS A CRITICAL SECURITY VIOLATION**

#### When User Provides API Keys/Secrets:

**✅ DO:**
1. **Immediately** set them using `wrangler secret put` command
2. Use environment variables for the command (export CLOUDFLARE_API_TOKEN)
3. Verify secrets are set with `wrangler secret list --name [worker-name]`

**❌ NEVER:**
1. ❌ **NEVER** commit API keys to git (not even in temporary files)
2. ❌ **NEVER** create files containing secrets (API_KEYS.md, .env, etc.)
3. ❌ **NEVER** write secrets to any tracked file
4. ❌ **NEVER** suggest committing secrets "for documentation"

#### Correct Way to Set Secrets:

```bash
# Set via wrangler command (correct)
echo "[SECRET_VALUE]" | wrangler secret put SECRET_NAME --name worker-name

# Or set via Cloudflare Dashboard (also correct)
# Dashboard → Workers → [worker] → Settings → Variables and Secrets
```

#### If You Accidentally Commit Secrets:

1. **Immediately** remove the file with `git rm [filename]`
2. **Immediately** commit and push the removal
3. **Warn user** that secrets are in git history and must be rotated
4. **Tell user** to regenerate new API keys from provider
5. Git history cleanup is needed but rotation is URGENT

**REMEMBER:** Once committed to git, secrets are compromised forever in history. Prevention is critical.

## For AI Assistants

When helping with this repository:

1. **🔒 SECURITY FIRST:** NEVER commit secrets/API keys to git. Use `wrangler secret put` immediately when user provides them.
2. **Always check** `CLOUDFLARE_DEPLOYMENT_GUIDE.md` before suggesting deployment changes
3. **Always verify** that suggestions won't create version activation issues
4. **Always recommend** `wrangler deploy` over `wrangler versions upload`
5. **Always ask** about Git Integration status when debugging deployments
6. **Never create** files containing secrets, even temporarily

## Quick Links

- [Main Deployment Guide](../CLOUDFLARE_DEPLOYMENT_GUIDE.md)
- [Unified Workflow](../.github/workflows/deploy-cloudflare-workers.yml)
- [Example Worker Config](../cloudflare-agents/wrangler-dashboards.toml)
- [Cloudflare Dashboard](https://dash.cloudflare.com/8a330fc6c339f031a73905d4ca2f3e5d/workers)

---

**Last Updated:** 2025-11-10
**Importance:** CRITICAL
