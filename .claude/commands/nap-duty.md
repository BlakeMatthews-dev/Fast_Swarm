---
description: Automated nap-check-commit-push cycle (runs indefinitely)
---

# Nap Duty

Automated monitoring cycle: nap → check for changes → commit & push → repeat.

## The Cycle

```
┌─────────────────────────────────────────────────┐
│  1. SLEEP for 15 minutes                        │
│     sleep 900                                   │
├─────────────────────────────────────────────────┤
│  2. WAKE and check for changes                  │
│     git status --short                          │
├─────────────────────────────────────────────────┤
│  3. If changes exist:                           │
│     a. Analyze each changed file (git diff)     │
│     b. Generate detailed changelog              │
│     c. Commit with comprehensive message        │
│     d. Push to remote                           │
├─────────────────────────────────────────────────┤
│  4. REPEAT indefinitely                         │
└─────────────────────────────────────────────────┘
```

## Commit Message Format

Every commit follows this structure:

```
<type>: <one-line summary>

CHANGELOG:
- <file1>: <what changed>
  - <specific detail> (+N lines)
- <file2>: <what changed>
- Removed <file3> (reason)

<optional explanation>

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

## Process Per Cycle

### 1. Nap
```bash
sleep 900 && echo "Nap #N complete - $(date)"
```

### 2. Check Changes
```bash
git status --short
```

If no changes, go back to nap.

### 3. Analyze Changes
```bash
# Overview
git diff --stat HEAD -- "*.py" "*.json" "*.ts"

# Per-file analysis (for significant files)
git diff HEAD -- <file> | head -100
```

### 4. Generate Changelog
For each changed file:
- What was added/modified/removed
- Function names, class names, key changes
- Line counts for significant additions
- The "why" not just the "what"

### 5. Commit & Push
```bash
git add -A && git commit -m "<message>"
git push origin main
```

### 6. Track Progress
- Increment nap counter: #N → #N+1
- Increment commit counter: #M → #M+1
- Log database sizes if monitoring data collection
- Note any errors or warnings

## Health Checks (Optional)

If monitoring live data collection:
```bash
# Check database size (should grow over time)
ls -lh live_data.db | awk '{print $5}'

# Check for stuck processes
# Check WAL file sizes
```

## Example Session Output

```
Starting nap #227. Continuing the automated monitoring cycle.
[sleep 900]
Nap #227 complete - 29 Dec 2025 17:20:50

Waking up from nap #227. Checking for code changes.
[git status --short]
 M local-utilities/committee/coach.py
 M local-utilities/daemon/evolution_daemon.py
?? local-utilities/mass_test_patterns.json

Changes detected! Analyzing...
[git diff analysis]

Committing #107...
feat: crucible-coach integration and genesis fallback
[commit details]

Pushed successfully. Starting nap #228.
```

## To Start Nap Duty

Just say: "back to commit + nap duty" or "nap for 15 then commit"

The cycle will run indefinitely until you stop it or context runs out.

## Useful Statistics to Track

- Nap count: How many cycles completed
- Commit count: How many commits made
- Database size: If monitoring data collection
- Lines added/removed: Running totals
- Time elapsed: Total monitoring duration
