#!/bin/bash
# Nap Duty - Automated commit cycle with Claude-generated messages
# Usage: ./scripts/nap_duty.sh [nap_minutes]

NAP_MINUTES=${1:-15}
NAP_SECONDS=$((NAP_MINUTES * 60))
CYCLE=0

cd "$(dirname "$0")/.." || exit 1

echo "🛏️ Nap Duty started - checking every ${NAP_MINUTES} minutes"
echo "Press Ctrl+C to stop"
echo ""

while true; do
  CYCLE=$((CYCLE + 1))

  # Check for changes
  changes=$(git status --short)

  if [ -n "$changes" ]; then
    echo "=== Cycle #${CYCLE}: Changes detected at $(date) ==="
    echo "$changes"
    echo ""

    # Get diff stats for context
    diff_stats=$(git diff --stat HEAD 2>/dev/null)
    diff_content=$(git diff HEAD 2>/dev/null | head -500)

    # Stage all changes
    git add -A

    # Call Claude to generate commit message
    echo "🤖 Generating commit message with Claude..."

    commit_msg=$(claude -p --dangerously-skip-permissions "You are generating a git commit message. Here are the staged changes:

FILES CHANGED:
$changes

DIFF STATS:
$diff_stats

DIFF CONTENT (truncated):
$diff_content

Generate a commit message in this EXACT format (no other text):

<type>: <short summary>

CHANGELOG:
- <file1>: <what changed>
- <file2>: <what changed>
...

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>

Types: feat, fix, refactor, chore, docs, test, perf
Be specific about what changed in each file.")

    if [ -n "$commit_msg" ]; then
      echo "--- Commit Message ---"
      echo "$commit_msg"
      echo "----------------------"

      # Commit with the generated message
      git commit -m "$commit_msg"

      # Push
      git push && echo "✅ Pushed successfully" || echo "❌ Push failed"
    else
      echo "❌ Failed to generate commit message, skipping..."
      git reset HEAD
    fi
  else
    echo "=== Cycle #${CYCLE}: No changes at $(date) ==="
  fi

  echo "😴 Napping for ${NAP_MINUTES} minutes..."
  echo ""
  sleep $NAP_SECONDS
done
