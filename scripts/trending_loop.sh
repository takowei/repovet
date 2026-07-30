#!/usr/bin/env bash
# trending_loop.sh — daemonized trending scan + weekly digest.
#
# Every TRENDING_INTERVAL_SECONDS (default 86400 = daily), scans today's
# GitHub Trending list with the existing S1-S4 engine and writes a dated
# JSON file to /data/trending-scans/. Once a day it also checks whether a
# digest is due (one Monday-triggered markdown rollup per week, written to
# /data/digests/) -- content-curation input for outreach, not a live feed.
set -euo pipefail

INTERVAL="${TRENDING_INTERVAL_SECONDS:-86400}"
SCANS_DIR="${TRENDING_SCANS_DIR:-/data/trending-scans}"
DIGESTS_DIR="${TRENDING_DIGESTS_DIR:-/data/digests}"
LIMIT="${TRENDING_LIMIT:-25}"

echo "[trending_loop] starting -- scanning every ${INTERVAL}s -> ${SCANS_DIR}"

while true; do
    echo "[trending_loop] $(date -u '+%Y-%m-%dT%H:%M:%SZ') running scan_trending..."
    if ! python leaderboard/scan_trending.py --output-dir "$SCANS_DIR" --limit "$LIMIT"; then
        echo "[trending_loop] scan_trending exited non-zero -- will retry next interval" >&2
    fi

    # Weekly digest: only generate on Monday (UTC), and only once (skip if
    # today's digest file already exists) so an interval < 1 day can't spam.
    if [ "$(date -u '+%u')" = "1" ]; then
        today="$(date -u '+%Y-%m-%d')"
        if [ ! -f "${DIGESTS_DIR}/${today}.md" ]; then
            echo "[trending_loop] Monday -- generating weekly digest..."
            python leaderboard/generate_weekly_digest.py \
                --scans-dir "$SCANS_DIR" --output-dir "$DIGESTS_DIR" || \
                echo "[trending_loop] generate_weekly_digest exited non-zero" >&2
        fi
    fi

    sleep "$INTERVAL"
done
