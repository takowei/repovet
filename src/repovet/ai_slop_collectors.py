"""Gathers raw data for S4 (AI-slop feature hints, v0): README text, recent
commit messages, and top-level repo/`.github` directory listings. Reuses
the same rate-limit-aware REST client as S2/S3 -- no new API surface.
"""

import base64
from dataclasses import dataclass, field

from repovet.errors import InputError
from repovet.github_client import GitHubClient
from repovet.targets import Target

README_CANDIDATES = ("README.md", "README.rst", "README", "readme.md")
COMMIT_MESSAGE_SAMPLE = 30


@dataclass
class RawSlopSignals:
    owner: str
    repo: str
    readme_text: str | None = None
    commit_messages: list[str] = field(default_factory=list)
    root_entries: list[str] = field(default_factory=list)
    github_dir_entries: list[str] = field(default_factory=list)


def _fetch_readme(rest_client: GitHubClient, target: Target) -> str | None:
    for path in README_CANDIDATES:
        try:
            data = rest_client.get(
                f"/repos/{target.owner}/{target.repo}/contents/{path}", ttl_seconds=3600
            )
        except InputError:
            continue
        if isinstance(data, dict) and data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    return None


def _fetch_commit_messages(rest_client: GitHubClient, target: Target, limit: int) -> list[str]:
    try:
        commits = rest_client.get(
            f"/repos/{target.owner}/{target.repo}/commits",
            params={"per_page": limit},
            ttl_seconds=3600,
        )
    except InputError:
        return []
    if not isinstance(commits, list):
        return []
    return [c["commit"]["message"].splitlines()[0] for c in commits if c.get("commit")]


def _fetch_dir_listing(rest_client: GitHubClient, target: Target, path: str) -> list[str]:
    try:
        entries = rest_client.get(
            f"/repos/{target.owner}/{target.repo}/contents/{path}", ttl_seconds=3600
        )
    except InputError:
        return []
    if not isinstance(entries, list):
        return []
    return [e["name"] for e in entries]


def collect_slop_signals(rest_client: GitHubClient, target: Target) -> RawSlopSignals:
    readme_text = _fetch_readme(rest_client, target)
    commit_messages = _fetch_commit_messages(rest_client, target, COMMIT_MESSAGE_SAMPLE)
    root_entries = _fetch_dir_listing(rest_client, target, "")
    github_entries = (
        _fetch_dir_listing(rest_client, target, ".github") if ".github" in root_entries else []
    )
    return RawSlopSignals(
        owner=target.owner,
        repo=target.repo,
        readme_text=readme_text,
        commit_messages=commit_messages,
        root_entries=root_entries,
        github_dir_entries=github_entries,
    )
