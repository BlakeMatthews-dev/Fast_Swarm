# Smart Commit Skill

Generate comprehensive commit messages with detailed changelogs by analyzing git diffs.

## When This Skill Activates

This skill is automatically used when:
- User asks to commit changes
- User asks to push code
- User asks for a commit message
- Context suggests code has been modified and needs committing

## Commit Message Structure

```
<type>: <concise summary of ALL changes>

CHANGELOG:
- <file1.py>: <category of change>
  - <specific change 1>
  - <specific change 2> (+N lines)
- <file2.py>: <category of change>
  - <details with actual names, values, functions>
- Removed <file3>: <reason for removal>
- Added <file4>: <purpose> (+N lines)

<optional paragraph explaining the broader "why" or context>

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

## Commit Types

| Type | Use When |
|------|----------|
| `feat` | Adding new functionality |
| `fix` | Fixing a bug |
| `refactor` | Restructuring without behavior change |
| `perf` | Performance improvement |
| `docs` | Documentation changes |
| `test` | Test additions or fixes |
| `chore` | Maintenance, deps, config |
| `style` | Formatting only |

## Analysis Process

1. **Run**: `git status --short` to see all changes
2. **Run**: `git diff --stat HEAD` for line count overview
3. **For each significant file**: `git diff HEAD -- <file> | head -100`
4. **Extract**:
   - Function/class names added or modified
   - Specific values, thresholds, configurations changed
   - Files deleted and why
   - New files and their purpose
   - Line counts for significant additions

## Quality Standards

### EXCELLENT Changelog Entry
```
- agent_state.py: Expanded from 16 to 22 heritable traits (V3 parity)
  - uncertainty_anchor: Center point for decision thresholds
  - ai_assist_range: Zone width for AI assistance requests
  - min_threshold: Minimum confidence for autonomous decisions
  - Updated random() generator for all 22 traits
  - Coupled derivation: ai_assist_range from uncertainty_anchor (+45 lines)
```

### POOR Changelog Entry
```
- agent_state.py: Updated traits
```

## What to Include

- **File names** with the category of change
- **Specific names**: functions, classes, variables, constants
- **Actual values**: thresholds, percentages, counts
- **Line counts**: (+N lines) for additions, deletions noted
- **Relationships**: "X now uses Y" or "moved from A to B"
- **The why**: Brief explanation of purpose or reason

## What to Exclude

- Trivial whitespace changes (unless that's ALL the commit is)
- Temporary/generated files (*.db-shm, *.db-wal, __pycache__)
- Secrets or sensitive values (mask them)

## Example Commits

### Feature Addition
```
feat: accurate net PnL with round-trip fee tracking

CHANGELOG:
- live_committee_trader.py: Net PnL calculation improvement
  - Track entry_fees_usd and entry_fee_pct in open positions
  - Calculate gross_pnl_pct (price movement only)
  - Calculate net_pnl_pct = gross - entry_fee - exit_fee (round-trip)
  - Use entry_cost and exit_proceeds for accurate USD PnL
  - Add profit marker (✓/✗) to exit logs
  - Log both gross and net PnL for transparency (+46 lines)

This ensures honest profitability tracking - a 0.5% price gain
with 0.1% round-trip fees is actually +0.4%, not +0.5%.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

### Cleanup/Refactor
```
feat: crucible-coach integration and genesis fallback

CHANGELOG:
- committee/coach.py: Added Crucible integration for roster selection
  - select_roster_from_crucible(): Load rosters from Crucible leaderboard
  - select_roster_for_regime(): Regime-specific agent selection
  - ELO boosting based on coach preferences (+113 lines)
- daemon/evolution_daemon.py: Genesis fallback for robustness
  - HAS_GENESIS flag for optional genesis-based agents
  - _wrap_agent_record(): Compatibility wrapper for legacy Agent
  - Fallback to agent_state when genesis unavailable (+258 lines)
- Removed redundant pattern files (52k lines):
  - patterns_for_paper_trading.json (22k lines)
  - top_500_patterns_for_agents.json (29k lines)

Total: +3,311 insertions, -53,070 deletions (cleanup)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

## Execution

After generating the message:
```bash
git add -A && git commit -m "<message>"
git push origin main
```

Report success with commit hash and any push status.
