"""S2 (zombie maintenance) scoring.

Design philosophy (spec: distinguish "stable/complete" from "abandoned"):
A mature, feature-complete project can have low commit/release cadence and
still be perfectly healthy, as long as issues still get a human response and
*someone* still shows up occasionally. So issue responsiveness and recent
maintainer activity are weighted far higher than raw commit/release cadence.
Raw inactivity alone is deliberately capped so it can't tank the score by
itself (see score_cadence floor).

s2.v1 -> s2.v2: issue and PR responsiveness are now scored (and weighted)
separately. On popular repos, "most recent N issues+PRs" was dominated by
low-effort driveby PRs that maintainers correctly ignore, which dragged the
combined score down even on genuinely healthy repos (found during the M0
demo on psf/requests). Real user-filed issues are the truer "is anyone
listening" signal, so they keep the larger weight; PR non-response is a
weaker, more ambiguous signal and is weighted lower. The stable-vs-abandoned
pattern classification now keys off issue responsiveness specifically, not
the PR-diluted blend.

Thresholds and weights below are fixed at design time (no post-hoc tuning per
target). Bump FORMULA_VERSION whenever the formula itself changes, so past
--json output stays auditable against the version that produced it.
"""

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone

from repovet.collectors import IssueSample, RawSignals

FORMULA_VERSION = "s2.v2"

WEIGHT_CADENCE = 0.20
WEIGHT_ISSUE_RESPONSE = 0.30
WEIGHT_PR_RESPONSE = 0.10
WEIGHT_BUS_FACTOR = 0.15
WEIGHT_MAINTAINER_ACTIVITY = 0.25

# score_issue_response: multiplier applied when issues DO get answered, but slowly
_SLOW_RESPONSE_PENALTIES = (
    (180, 0.6),
    (60, 0.8),
    (14, 0.95),
)

# score_cadence: (max_days_since_last_activity, score) checked in order
_CADENCE_BANDS = (
    (30, 100),
    (90, 90),
    (180, 75),
    (365, 55),
    (730, 35),
    (1095, 20),
)
_CADENCE_FLOOR = 10  # even years of silence isn't proof of abandonment by itself

# score_maintainer_activity: (max_days_since_any_activity, score)
_MAINTAINER_BANDS = (
    (90, 100),
    (180, 50),
    (365, 20),
)
_MAINTAINER_FLOOR = 0


@dataclass
class SubScore:
    name: str
    score: int
    evidence: str


@dataclass
class S2Result:
    formula_version: str
    overall: int
    pattern: str
    sub_scores: list[SubScore]
    warnings: list[str] = field(default_factory=list)


def _days_since(dt: datetime | None, now: datetime) -> int | None:
    if dt is None:
        return None
    return (now - dt).days


def score_cadence(last_commit_at, last_release_at, now) -> SubScore:
    candidates = [d for d in (last_commit_at, last_release_at) if d is not None]
    if not candidates:
        return SubScore("commit/release cadence", _CADENCE_FLOOR, "查無 commit 或 release 紀錄")

    last_activity = max(candidates)
    days = (now - last_activity).days
    score = _CADENCE_FLOOR
    for max_days, band_score in _CADENCE_BANDS:
        if days <= max_days:
            score = band_score
            break

    if last_commit_at:
        commit_str = f"{last_commit_at.date()}（{(now - last_commit_at).days}天前）"
    else:
        commit_str = "無紀錄"
    if last_release_at:
        release_str = f"{last_release_at.date()}（{(now - last_release_at).days}天前）"
    else:
        release_str = "無 release 紀錄"
    evidence = f"最近 commit {commit_str}；最近 release {release_str}"
    return SubScore("commit/release cadence", score, evidence)


def _score_responsiveness(sample: list[IssueSample], label: str, noun: str) -> SubScore:
    """Shared scoring core for issue-only and PR-only responsiveness. Kept as
    two separate sub-scores (not blended) because their non-response has
    different meaning: an unanswered issue is a real warning sign, an
    unanswered PR often isn't (maintainers routinely ignore driveby/spam
    PRs) — see FORMULA_VERSION history above for why s2.v1 conflated them."""
    sample_size = len(sample)
    if sample_size == 0:
        return SubScore(label, 70, f"近期無 {noun} 可供抽樣，無法評估回應性（預設中性分數）")

    responded = [s for s in sample if s.responded_at is not None]
    response_days = [(s.responded_at - s.created_at).days for s in responded]
    responded_count = len(responded)
    base = (responded_count / sample_size) * 100

    median_days = statistics.median(response_days) if response_days else None
    if median_days is not None:
        for threshold, multiplier in _SLOW_RESPONSE_PENALTIES:
            if median_days > threshold:
                base *= multiplier
                break

    score = round(min(100, max(0, base)))
    evidence = f"最近 {sample_size} 個{noun}中 {responded_count} 個獲得回應"
    if median_days is not None:
        evidence += f"，首次回應中位數 {median_days:.1f} 天"
    return SubScore(label, score, evidence)


def score_issue_response(issues: list[IssueSample]) -> SubScore:
    return _score_responsiveness(issues, "issue responsiveness", "issue")


def score_pr_response(prs: list[IssueSample]) -> SubScore:
    evidence_note = "可能含未經審核的自動/低品質 PR，非響應不必然代表維護者失聯"
    sub = _score_responsiveness(prs, "PR responsiveness", "PR")
    if prs:
        sub.evidence += f"（{evidence_note}）"
    return sub


def _bus_factor(author_counts: dict[str, int]) -> tuple[int, int, int]:
    total = sum(author_counts.values())
    if total == 0:
        return 0, 0, 0
    counts_desc = sorted(author_counts.values(), reverse=True)
    cumulative = 0
    factor = 0
    for c in counts_desc:
        cumulative += c
        factor += 1
        if cumulative >= total / 2:
            break
    return factor, len(author_counts), total


def score_bus_factor(author_counts: dict[str, int]) -> SubScore:
    factor, total_authors, total_commits = _bus_factor(author_counts)
    if total_commits == 0:
        return SubScore("bus factor", 50, "近一年無 commit 紀錄，無法評估 bus factor")

    score = min(100, 40 + factor * 20)
    evidence = (
        f"近一年 {total_commits} 筆 commit 中，前 {factor} 位貢獻者即佔 ≥50%"
        f"（共 {total_authors} 位貢獻者，bus factor={factor}）"
    )
    return SubScore("bus factor", score, evidence)


def score_maintainer_activity(raw: RawSignals, now: datetime) -> SubScore:
    candidates = [raw.last_commit_at, raw.last_release_at]
    candidates.extend(s.responded_at for s in raw.issue_sample if s.responded_at is not None)
    candidates = [c for c in candidates if c is not None]

    if not candidates:
        return SubScore(
            "maintainer 90d activity",
            _MAINTAINER_FLOOR,
            "查無任何可偵測活動（commit、release、issue 回應皆無）",
        )

    last_activity = max(candidates)
    days = (now - last_activity).days
    score = _MAINTAINER_FLOOR
    for max_days, band_score in _MAINTAINER_BANDS:
        if days <= max_days:
            score = band_score
            break

    evidence = f"最近一次可偵測活動（commit/release/issue 回應）距今 {days} 天"
    return SubScore("maintainer 90d activity", score, evidence)


def _classify_pattern(issue_score: int, maintainer_score: int, cadence_score: int) -> str:
    if issue_score < 30 and maintainer_score <= 20:
        return "anomalous-stalled"
    if issue_score >= 60 and maintainer_score >= 50:
        return "healthy" if cadence_score >= 70 else "stable-low-frequency"
    return "mixed"


def compute_s2(raw: RawSignals) -> S2Result:
    if raw.fetched_at.tzinfo:
        now = raw.fetched_at.astimezone(timezone.utc)
    else:
        now = raw.fetched_at.replace(tzinfo=timezone.utc)

    issues_only = [s for s in raw.issue_sample if not s.is_pr]
    prs_only = [s for s in raw.issue_sample if s.is_pr]

    cadence = score_cadence(raw.last_commit_at, raw.last_release_at, now)
    issue_response = score_issue_response(issues_only)
    pr_response = score_pr_response(prs_only)
    bus_factor = score_bus_factor(raw.author_commit_counts)
    maintainer = score_maintainer_activity(raw, now)

    overall = round(
        cadence.score * WEIGHT_CADENCE
        + issue_response.score * WEIGHT_ISSUE_RESPONSE
        + pr_response.score * WEIGHT_PR_RESPONSE
        + bus_factor.score * WEIGHT_BUS_FACTOR
        + maintainer.score * WEIGHT_MAINTAINER_ACTIVITY
    )
    pattern = _classify_pattern(issue_response.score, maintainer.score, cadence.score)

    target_sample_size = 15
    warnings = []
    if raw.anonymous:
        warnings.append("anonymous GitHub API access (no GITHUB_TOKEN): lower rate limit")
    sample_count = len(raw.issue_sample)
    if 0 < sample_count < target_sample_size:
        warnings.append(
            f"issue+PR sample smaller than target (got {sample_count}, wanted {target_sample_size})"
        )

    return S2Result(
        formula_version=FORMULA_VERSION,
        overall=overall,
        pattern=pattern,
        sub_scores=[cadence, issue_response, pr_response, bus_factor, maintainer],
        warnings=warnings,
    )
