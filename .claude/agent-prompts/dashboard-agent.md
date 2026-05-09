# DASHBOARD AGENT

## Mission
Create the Decayed Patterns dashboard for human review and update the main swarm dashboard with new metrics.

## Repository
`c:\Users\Admin\Documents\Coinswarm-1`

## Tasks

### Task 1: Create Decayed Patterns Dashboard
Create `cloudflare-agents/dashboards/decayed-patterns.html`:

Features needed:
- List all patterns with decay_status = 'decayed' or 'monitoring'
- Show for each pattern:
  - Pattern ID and name
  - Lifetime alpha vs recent alpha
  - Days since positive alpha
  - Peak performance period
  - Best regime and tokens
  - Days until auto-archive (90 day limit)
- Action buttons:
  - Keep Monitoring (reset 90-day timer)
  - Retire (permanently archive)
  - Resurrect (queue for retesting)
- Notes field for human reviewer
- Filter by status, sort by decay duration

### Task 2: Add Dashboard API Endpoint
Modify `cloudflare-agents/dashboards-worker.ts`:
- Add `/api/decayed-patterns` endpoint
- Add `/api/decay-action` POST endpoint for actions
- Add `/api/human-notes` GET/POST for notes system

### Task 3: Update Swarm Dashboard
Modify `cloudflare-agents/dashboards/swarm.html`:
- Add Level display for agents (Level 1, 2, 3...)
- Add lineage info (root ancestor, depth)
- Add alpha metrics columns
- Add dynasty indicators for high-level agents

### Task 4: Create Diversity Metrics Section
Add to swarm dashboard:
- Lineage concentration chart
- Pattern usage distribution
- Trait variance metrics
- Alerts for low diversity

## Success Criteria
- [ ] Decayed patterns dashboard functional
- [ ] Actions work (monitor/retire/resurrect)
- [ ] Swarm dashboard shows levels and lineage
- [ ] API endpoints working
- [ ] Clean, readable UI matching existing style

## Output
Write completion log to `.state/agent-logs/dashboard-agent-{timestamp}.json`

## Commit Message Template
```
[DASHBOARDS] Add decayed patterns review + update swarm dashboard

- Create decayed-patterns.html with action buttons
- Add API endpoints for decay management
- Update swarm.html with level/lineage display
- Add diversity metrics section

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```
