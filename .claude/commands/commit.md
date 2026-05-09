---
description: Generate detailed commit with changelog from current changes
---

# Smart Commit

Analyze all staged/unstaged changes and generate a comprehensive commit with detailed changelog.

## Process

1. **Check for changes**: `git status --short`
2. **Analyze each changed file**:
   - `git diff --stat HEAD` for overview
   - `git diff HEAD -- <file>` for each changed file
   - Understand WHAT changed and WHY
3. **Generate commit message** with this structure:

```
<type>: <one-line summary>

CHANGELOG:
- <file1>: <what changed>
  - <specific change 1>
  - <specific change 2> (+N lines)
- <file2>: <what changed>
  - <details>
- Removed <file3> (reason)
- Added <file4>: <purpose> (+N lines)

<optional context paragraph explaining the "why">

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

4. **Stage and commit**: `git add -A && git commit -m "..."`
5. **Optionally push**: Ask user or push automatically

## Commit Types

| Type | When to Use |
|------|-------------|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `refactor` | Code restructuring without behavior change |
| `perf` | Performance improvement |
| `docs` | Documentation only |
| `test` | Adding or fixing tests |
| `chore` | Maintenance, dependencies, config |
| `style` | Formatting, whitespace |

## Changelog Quality Guidelines

### GOOD Changelog Entry
```
- tick_replay_trader.py: Realistic volume-based fee tiers
  - binance: Tier I ($50K-100K vol) 0.1425%/0.2375%
  - binance_mid: Tier I ($10K-50K vol) 0.2375%/0.38%
  - Fixed crypto_zero: BTC NOT eligible for Zero Maker promo!
  - WARNING comments added for promotional limitations (+43 lines)
```

### BAD Changelog Entry
```
- tick_replay_trader.py: Updated fees
```

## Include in Changelog

- File names with what category of change
- Specific functions/classes added or modified
- Line counts for significant additions (+N lines)
- Deletions with reason (Removed X because Y)
- New files with their purpose
- Config changes with actual values

## Example Output

```
feat: V3 parity traits and Crypto.com zero-maker fees

CHANGELOG:
- agent_state.py: Expanded from 16 to 22 heritable traits (V3 parity)
  - uncertainty_anchor: Center point for decision thresholds
  - ai_assist_range: Zone width for AI assistance requests
  - min_threshold: Minimum confidence for autonomous decisions
  - ai_threshold: Threshold above which AI assistance requested
  - memory_condensation: Rate episodic → semantic compression
  - inheritance_decay: Rate inherited wisdom decays per generation
  - Updated random() generator for all 22 traits (+45 lines)
- daemon/evolution_daemon.py: Agent spawning with expanded traits
  - Handle genesis and legacy trait systems
  - Compatibility layer for V3 traits (+113 lines)
- tick_replay_trader.py: Crypto.com fee structure update
  - crypto: Updated to accurate Level 1 fees (0.25%/0.50%)
  - crypto_zero: Zero Maker Fee promo (0% maker, 0.04% taker)
  - crypto_zero_deriv: Zero Maker perps (0% maker, 0.02% taker)
  - Critical for sats accumulation - 12x cheaper than normal

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

## Flags

- `--push`: Automatically push after commit
- `--dry-run`: Show commit message without committing
- `--amend`: Amend previous commit (only if safe)
