#!/usr/bin/env bash
# run.sh — Monthly sommelier session
# Launches Claude Code to browse retailers and pick a case of wines.
# Runs from cron on the 1st of each month, or manually.

set -euo pipefail

PROJECT="/home/henry/projects/sommelier-claude"
LOGFILE="$PROJECT/logs/$(date +%Y-%m).log"
mkdir -p "$PROJECT/logs"

# Don't run if another session is already active
LOCKFILE="$PROJECT/.sommelier-lock"
if [ -f "$LOCKFILE" ]; then
    AGE=$(( $(date +%s) - $(stat -c %Y "$LOCKFILE") ))
    # Stale lock (older than 60 min) — remove it
    if [ "$AGE" -gt 3600 ]; then
        rm -f "$LOCKFILE"
    else
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) — Skipping: another session is active" >> "$PROJECT/logs/sommelier.log"
        exit 0
    fi
fi
touch "$LOCKFILE"
trap "rm -f $LOCKFILE" EXIT

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) — Session starting" >> "$PROJECT/logs/sommelier.log"

cd "$PROJECT"
unset CLAUDECODE 2>/dev/null || true
/home/henry/.local/bin/claude \
    -p "Read CLAUDE.md and pick this month's wines. Today is $(date +%Y-%m-%d)." \
    --dangerously-skip-permissions \
    --verbose \
    > "$LOGFILE" 2>&1

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) — Session complete. Log: $LOGFILE" >> "$PROJECT/logs/sommelier.log"
