"""Batch-scan the leaderboard seed list using repovet's existing S1-S4 engine.

Reuses `repovet.cli._run_one` (the same per-target scan path the CLI itself
uses for `--batch`) instead of reimplementing any scoring logic. This script
only adds: reading the fixed seed list, looping over it, and writing a
single combined JSON result file with a generation timestamp.

Idempotent by design: rerunning this script against the same seed list
produces a fresh result file reflecting current repo state -- no local
mutable state carried between runs (the response cache is a read-through
TTL cache, not a source of truth). Safe to invoke from a future scheduler
without any manual step.

Usage:
    source ~/.claude/gw-keys && export GITHUB_TOKEN
    PYTHONPATH=../src python3 scan_leaderboard.py
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

from repovet.cache import ResponseCache  # noqa: E402
from repovet.cli import _run_one  # noqa: E402
from repovet.github_client import GitHubClient  # noqa: E402
from repovet.graphql_client import GraphQLClient  # noqa: E402
from repovet.registry_client import RegistryClient  # noqa: E402

LEADERBOARD_DIR = Path(__file__).resolve().parent
DEFAULT_SEED_FILE = LEADERBOARD_DIR / "seed-repos.json"
DEFAULT_OUTPUT_FILE = LEADERBOARD_DIR / "leaderboard-data.json"


def load_seed_repos(path: Path = DEFAULT_SEED_FILE) -> list[dict]:
    """Read the fixed seed list. Returns the list of repo entries (dicts with
    at least a "target" key), ignoring the "_meta" documentation block."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["repos"]


def scan_all(
    repo_entries: list[dict],
    issue_sample: int = 15,
    commit_days: int = 365,
    lang: str = "en",
) -> list[dict]:
    """Run the existing repovet engine (S1-S4) over every seed target.

    One shared cache/session across the whole run, same as CLI --batch mode.
    """
    token = os.environ.get("GITHUB_TOKEN")
    cache = ResponseCache()
    rest_client = GitHubClient(token=token, cache=cache)
    graphql_client = GraphQLClient(token=token, cache=cache) if token else None
    registry_client = RegistryClient(cache=cache)

    records = []
    for entry in repo_entries:
        record = _run_one(
            rest_client,
            graphql_client,
            registry_client,
            entry["target"],
            issue_sample,
            commit_days,
            lang,
        )
        record["_seed_meta"] = {k: v for k, v in entry.items() if k != "target"}
        records.append(record)
    return records


def run(seed_file: Path, output_file: Path) -> dict:
    repo_entries = load_seed_repos(seed_file)
    if not os.environ.get("GITHUB_TOKEN"):
        print(
            "warning: no GITHUB_TOKEN set; S1 will be skipped for every repo, "
            "S2/S3/S4 run anonymous (60 req/hr) -- see README 'Gotcha' about "
            "sourcing vs exporting the token",
            file=sys.stderr,
        )

    started = time.monotonic()
    records = scan_all(repo_entries)
    elapsed_seconds = round(time.monotonic() - started, 1)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed_file": seed_file.name,
        "repo_count": len(repo_entries),
        "elapsed_seconds": elapsed_seconds,
        "records": records,
    }
    output_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"scanned {len(repo_entries)} repos in {elapsed_seconds}s -> {output_file}",
        file=sys.stderr,
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-file", type=Path, default=DEFAULT_SEED_FILE)
    parser.add_argument("--output-file", type=Path, default=DEFAULT_OUTPUT_FILE)
    args = parser.parse_args(argv)
    run(args.seed_file, args.output_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
