#!/bin/bash
# Jarvis 1.0 — morning briefing wrapper for launchd / Shortcuts automation.
# Activates venv, runs briefing, logs output, de-dups within 60 min.
set -e

LOGFILE="$HOME/jarvis-venv/briefing.log"
LOCKFILE="$HOME/jarvis-venv/briefing.lastrun"

# De-dup: skip if a run completed in the last 60 min
if [ -f "$LOCKFILE" ] && [ $(( $(date +%s) - $(cat "$LOCKFILE") )) -lt 3600 ]; then
  echo "[$(date)] Skipping — ran recently" >> "$LOGFILE"
  exit 0
fi

echo "=== Run at $(date) ===" >> "$LOGFILE"
cd /Users/amitgrupper/Jarvis1.0/agent
/Users/amitgrupper/jarvis-venv/bin/python personalhq/morning_briefing.py >> "$LOGFILE" 2>&1
date +%s > "$LOCKFILE"
echo "=== Completed at $(date) ===" >> "$LOGFILE"
