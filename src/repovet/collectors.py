"""Gathers the raw GitHub signals that scoring.py turns into an S2 score.

All timestamps are timezone-aware UTC datetimes. All API access goes through
GitHubClient (cached + rate-limit aware) — this module never calls requests
directly.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from repovet.github_client import GitHubClient
from repovet.targets import Target

COMMIT_LOOKBACK_DAYS = 365
COMMIT_MAX_PAGES = 3  # caps history read at ~300 commits/year; see README limitations
ISSUE_SAMPLE_SIZE = 15
ISSUE_FETCH_MULTIPLIER = 3  # over-fetch so we can drop too-fresh issues, see below
ISSUE_MIN_AGE_DAYS = 2  # issues younger than this haven't had time to get a response yet


@dataclass
class IssueSample:
    number: int
    created_at: datetime
    responded_at: datetime | None
    is_pr: bool


@dataclass
class RawSignals:
    owner: str
    repo: str
    fetched_at: datetime
    last_commit_at: datetime | None
    last_release_at: datetime | None
    author_commit_counts: dict[str, int]
    commit_sample_count: int
    commit_sample_since: datetime
    issue_sample: list[IssueSample] = field(default_factory=list)
    anonymous: bool = False


def _parse_ts(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _fetch_commits(client: GitHubClient, target: Target, since: datetime) -> list[dict]:
    commits: list[dict] = []
    for page in range(1, COMMIT_MAX_PAGES + 1):
        batch = client.get(
            f"/repos/{target.owner}/{target.repo}/commits",
            params={"since": since.isoformat(), "per_page": 100, "page": page},
        )
        if not batch:
            break
        commits.extend(batch)
        if len(batch) < 100:
            break
    return commits


def _author_key(commit: dict) -> str:
    author = commit.get("author")
    if author and author.get("login"):
        return author["login"]
    commit_author = commit.get("commit", {}).get("author", {})
    return commit_author.get("name") or commit_author.get("email") or "unknown"


def _fetch_issue_samples(
    client: GitHubClient, target: Target, sample_size: int, now: datetime
) -> list[IssueSample]:
    """Sample the most recent issues/PRs, but skip ones too young to have had a
    fair chance at a response yet — otherwise high-traffic repos look falsely
    unresponsive just because their newest issues are minutes old (see README
    limitations: this is a real bias we found during the M0 demo run)."""
    fetch_count = min(100, sample_size * ISSUE_FETCH_MULTIPLIER)
    issues = client.get(
        f"/repos/{target.owner}/{target.repo}/issues",
        params={
            "state": "all",
            "sort": "created",
            "direction": "desc",
            "per_page": fetch_count,
        },
    )

    min_age = now - timedelta(days=ISSUE_MIN_AGE_DAYS)
    eligible = [i for i in issues if _parse_ts(i["created_at"]) <= min_age][:sample_size]

    samples: list[IssueSample] = []
    for issue in eligible:
        created_at = _parse_ts(issue["created_at"])
        responded_at = None
        if issue.get("comments", 0) > 0:
            first_comment = client.get(
                f"/repos/{target.owner}/{target.repo}/issues/{issue['number']}/comments",
                params={"per_page": 1},
                ttl_seconds=6 * 3600,
            )
            if first_comment:
                responded_at = _parse_ts(first_comment[0]["created_at"])
        samples.append(
            IssueSample(
                number=issue["number"],
                created_at=created_at,
                responded_at=responded_at,
                is_pr="pull_request" in issue,
            )
        )
    return samples


def collect_signals(
    client: GitHubClient,
    target: Target,
    commit_days: int = COMMIT_LOOKBACK_DAYS,
    issue_sample_size: int = ISSUE_SAMPLE_SIZE,
) -> RawSignals:
    """Hit the GitHub API (through the cache) and assemble RawSignals for scoring."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=commit_days)

    repo_meta = client.get(f"/repos/{target.owner}/{target.repo}", ttl_seconds=900)
    last_commit_at = _parse_ts(repo_meta.get("pushed_at"))

    releases = client.get(
        f"/repos/{target.owner}/{target.repo}/releases", params={"per_page": 5}, ttl_seconds=900
    )
    last_release_at = _parse_ts(releases[0]["published_at"]) if releases else None

    commits = _fetch_commits(client, target, since)
    author_counts: dict[str, int] = {}
    for commit in commits:
        key = _author_key(commit)
        author_counts[key] = author_counts.get(key, 0) + 1

    issue_sample = _fetch_issue_samples(client, target, issue_sample_size, now)

    return RawSignals(
        owner=target.owner,
        repo=target.repo,
        fetched_at=now,
        last_commit_at=last_commit_at,
        last_release_at=last_release_at,
        author_commit_counts=author_counts,
        commit_sample_count=len(commits),
        commit_sample_since=since,
        issue_sample=issue_sample,
        anonymous=client.anonymous,
    )
