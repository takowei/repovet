#!/usr/bin/env bash
# scan_loop.sh — daemonized version of leaderboard/scan_leaderboard.py.
#
# Runs the existing (unchanged) leaderboard scan once, writes the result to
# /data/leaderboard-data.json (persisted via the repovet_data volume), then
# sleeps, forever. This replaces the session-bound cron the scan used to run
# under -- the container stays up (restart: unless-stopped) independent of
# any Claude Code session.
#
# SCAN_INTERVAL_SECONDS defaults to 86400 (daily). Override in .env.
set -euo pipefail

INTERVAL="${SCAN_INTERVAL_SECONDS:-86400}"
OUTPUT_FILE="${SCAN_OUTPUT_FILE:-/data/leaderboard-data.json}"

echo "[scan_loop] starting -- scanning every ${INTERVAL}s -> ${OUTPUT_FILE}"

while true; do
    echo "[scan_loop] $(date -u '+%Y-%m-%dT%H:%M:%SZ') running scan_leaderboard..."
    if ! python leaderboard/scan_leaderboard.py --output-file "$OUTPUT_FILE"; then
        echo "[scan_loop] scan_leaderboard exited non-zero -- will retry next interval" >&2
    fi
    sleep "$INTERVAL"
done
