"""Batch-scan today's GitHub Trending repos using repovet's existing S1-S4
engine (same reuse pattern as scan_leaderboard.py -- this only adds the
trending-list source and dated output files).

Writes one dated JSON file per run into a directory (default
`trending-scans/`), so a week's worth of runs can later be rolled up into a
digest by generate_weekly_digest.py. Never overwrites a previous day's file
(reruns on the same day overwrite only that day's file, which is fine --
same idempotency posture as the rest of repovet's scan scripts).

Usage:
    source ~/.claude/gw-keys && export GITHUB_TOKEN
    PYTHONPATH=../src python3 scan_trending.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fetch_trending import fetch_trending_repos  # noqa: E402

from repovet.cache import ResponseCache  # noqa: E402
from repovet.cli import _run_one  # noqa: E402
from repovet.github_client import GitHubClient  # noqa: E402
from repovet.graphql_client import GraphQLClient  # noqa: E402
from repovet.registry_client import RegistryClient  # noqa: E402

LEADERBOARD_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = LEADERBOARD_DIR / "trending-scans"
DEFAULT_LIMIT = 25


def scan_all(slugs: list[str], issue_sample: int = 15, commit_days: int = 365, lang: str = "en"):
    token = os.environ.get("GITHUB_TOKEN")
    cache = ResponseCache()
    rest_client = GitHubClient(token=token, cache=cache)
    graphql_client = GraphQLClient(token=token, cache=cache) if token else None
    registry_client = RegistryClient(cache=cache)

    records = []
    for slug in slugs:
        record = _run_one(
            rest_client,
            graphql_client,
            registry_client,
            f"gh:{slug}",
            issue_sample,
            commit_days,
            lang,
        )
        records.append(record)
    return records


def run(output_dir: Path, limit: int) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    if not os.environ.get("GITHUB_TOKEN"):
        print(
            "warning: no GITHUB_TOKEN set; S1 will be skipped for every repo, "
            "S2/S3/S4 run anonymous (60 req/hr)",
            file=sys.stderr,
        )

    slugs = fetch_trending_repos(limit=limit)
    started = time.monotonic()
    records = scan_all(slugs)
    elapsed_seconds = round(time.monotonic() - started, 1)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "github-trending",
        "repo_count": len(slugs),
        "elapsed_seconds": elapsed_seconds,
        "records": records,
    }
    output_file = output_dir / f"{today}.json"
    output_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"scanned {len(slugs)} trending repos -> {output_file}", file=sys.stderr)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args(argv)
    run(args.output_dir, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
