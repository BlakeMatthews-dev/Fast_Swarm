# CLAUDE: Cloudflare $5 Plan — Next Steps (automation & tasks)

Purpose: instructions and a compact task list for the CLAUDE agent to complete post-merge work related to Cloudflare $5 optimizations.

Checklist (actionable tasks for CLAUDE or CI-driven agent flows)
1. Run repo telemetry tool to collect: ai.run counts, Vectorize queries/day, D1 reads/writes per worker.
2. Create `ai-client` skeleton and a stub adapter for Cloudflare Workers AI in `cloudflare-agents/lib/ai-client.ts` (tests should use a fake adapter).
3. Add Vectorize batching and dedupe logic to news-sentiment/ai-pattern pipelines (non-destructive; add feature-flag).
4. Create job to record daily neuron consumption in D1 (table: ai_usage_by_day) for budget enforcement.
5. Optional: wire a small Durable Object per external API source for token-bucket rate limiting (PoC only).

Safe-run notes
- Always test in `claude/**` branches and deploy to staging worker with `AI_BUDGET_PER_DAY` lowered (e.g. 1000) before enabling wide rollout.

When done, push results to the issue tracker and mark the tasks completed so a human reviewer can review telemetry.
