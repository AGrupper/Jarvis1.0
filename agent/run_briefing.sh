#!/bin/bash
# Jarvis 1.0 — morning briefing wrapper for launchd / Shortcuts automation.
# Activates venv, runs briefing, logs output, de-dups within 60 min.

LOGFILE="$HOME/jarvis-venv/briefing.log"
LOCKFILE="$HOME/jarvis-venv/briefing.lastrun"

# De-dup: skip if a run completed in the last 60 min
if [ -f "$LOCKFILE" ] && [ $(( $(date +%s) - $(cat "$LOCKFILE") )) -lt 3600 ]; then
  echo "[$(date)] Skipping — ran recently" >> "$LOGFILE"
  exit 0
fi

echo "=== Run at $(date) ===" >> "$LOGFILE"
cd /Users/amitgrupper/Jarvis1.0/agent

# 10-minute hard timeout prevents a hung process from blocking future launchd runs.
# Uses perl alarm since macOS doesn't ship GNU timeout.
if /usr/bin/perl -e 'alarm 600; exec @ARGV' -- \
    /Users/amitgrupper/jarvis-venv/bin/python personalhq/morning_briefing.py >> "$LOGFILE" 2>&1; then
  date +%s > "$LOCKFILE"
  echo "=== Completed at $(date) ===" >> "$LOGFILE"
else
  echo "=== FAILED at $(date) (exit code $?) ===" >> "$LOGFILE"
fi
