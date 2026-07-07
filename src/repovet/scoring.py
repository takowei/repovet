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

M2.5: evidence prose is now English-native by default (`lang="en"`), with a
co-located Traditional Chinese string at every construction site
(`lang="zh"`) — the two live side by side in the same f-string branch so a
future change to the underlying facts can't update one language and forget
the other. `SubScore.name` (the sub-score label, e.g. "bus factor") and
`pattern` stay English-only regardless of `lang` — they're stable
identifiers other code/tests match against, not prose to localize.

Thresholds and weights below are fixed at design time (no post-hoc tuning per
target). Bump FORMULA_VERSION whenever the formula itself changes (text-only
changes, like this one, do not bump it), so past --json output stays
auditable against the version that produced it.
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


def score_cadence(last_commit_at, last_release_at, now, lang: str = "en") -> SubScore:
    candidates = [d for d in (last_commit_at, last_release_at) if d is not None]
    if not candidates:
        evidence = (
            "no commit or release history found" if lang != "zh" else "查無 commit 或 release 紀錄"
        )
        return SubScore("commit/release cadence", _CADENCE_FLOOR, evidence)

    last_activity = max(candidates)
    days = (now - last_activity).days
    score = _CADENCE_FLOOR
    for max_days, band_score in _CADENCE_BANDS:
        if days <= max_days:
            score = band_score
            break

    if lang == "zh":
        commit_str = (
            f"{last_commit_at.date()}（{(now - last_commit_at).days}天前）"
            if last_commit_at
            else "無紀錄"
        )
        release_str = (
            f"{last_release_at.date()}（{(now - last_release_at).days}天前）"
            if last_release_at
            else "無 release 紀錄"
        )
        evidence = f"最近 commit {commit_str}；最近 release {release_str}"
    else:
        commit_str = (
            f"{last_commit_at.date()} ({(now - last_commit_at).days} days ago)"
            if last_commit_at
            else "no record"
        )
        release_str = (
            f"{last_release_at.date()} ({(now - last_release_at).days} days ago)"
            if last_release_at
            else "no release on record"
        )
        evidence = f"last commit {commit_str}; last release {release_str}"
    return SubScore("commit/release cadence", score, evidence)


def _score_responsiveness(
    sample: list[IssueSample], label: str, noun: str, lang: str = "en"
) -> SubScore:
    """Shared scoring core for issue-only and PR-only responsiveness. Kept as
    two separate sub-scores (not blended) because their non-response has
    different meaning: an unanswered issue is a real warning sign, an
    unanswered PR often isn't (maintainers routinely ignore driveby/spam
    PRs) — see FORMULA_VERSION history above for why s2.v1 conflated them."""
    sample_size = len(sample)
    if sample_size == 0:
        evidence = (
            f"no recent {noun}s available to sample, can't assess responsiveness (neutral score)"
            if lang != "zh"
            else f"近期無 {noun} 可供抽樣，無法評估回應性（預設中性分數）"
        )
        return SubScore(label, 70, evidence)

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
    if lang == "zh":
        evidence = f"最近 {sample_size} 個{noun}中 {responded_count} 個獲得回應"
        if median_days is not None:
            evidence += f"，首次回應中位數 {median_days:.1f} 天"
    else:
        evidence = f"{responded_count}/{sample_size} recent {noun}s got a response"
        if median_days is not None:
            evidence += f", median first-response time {median_days:.1f} days"
    return SubScore(label, score, evidence)


def score_issue_response(issues: list[IssueSample], lang: str = "en") -> SubScore:
    return _score_responsiveness(issues, "issue responsiveness", "issue", lang)


def score_pr_response(prs: list[IssueSample], lang: str = "en") -> SubScore:
    note = (
        "可能含未經審核的自動/低品質 PR，非響應不必然代表維護者失聯"
        if lang == "zh"
        else "may include unreviewed/low-quality driveby PRs; non-response here "
        "doesn't necessarily mean the maintainer is gone"
    )
    sub = _score_responsiveness(prs, "PR responsiveness", "PR", lang)
    if prs:
        sub.evidence += f"（{note}）" if lang == "zh" else f" ({note})"
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


def score_bus_factor(author_counts: dict[str, int], lang: str = "en") -> SubScore:
    factor, total_authors, total_commits = _bus_factor(author_counts)
    if total_commits == 0:
        evidence = (
            "no commits in the past year, can't assess bus factor"
            if lang != "zh"
            else "近一年無 commit 紀錄，無法評估 bus factor"
        )
        return SubScore("bus factor", 50, evidence)

    score = min(100, 40 + factor * 20)
    if lang == "zh":
        evidence = (
            f"近一年 {total_commits} 筆 commit 中，前 {factor} 位貢獻者即佔 ≥50%"
            f"（共 {total_authors} 位貢獻者，bus factor={factor}）"
        )
    else:
        evidence = (
            f"of {total_commits} commits in the past year, the top {factor} contributor(s) "
            f"already account for ≥50% ({total_authors} total contributors, bus factor={factor})"
        )
    return SubScore("bus factor", score, evidence)


def score_maintainer_activity(raw: RawSignals, now: datetime, lang: str = "en") -> SubScore:
    candidates = [raw.last_commit_at, raw.last_release_at]
    candidates.extend(s.responded_at for s in raw.issue_sample if s.responded_at is not None)
    candidates = [c for c in candidates if c is not None]

    if not candidates:
        evidence = (
            "no detectable activity found (no commits, releases, or issue/PR responses)"
            if lang != "zh"
            else "查無任何可偵測活動（commit、release、issue 回應皆無）"
        )
        return SubScore("maintainer 90d activity", _MAINTAINER_FLOOR, evidence)

    last_activity = max(candidates)
    days = (now - last_activity).days
    score = _MAINTAINER_FLOOR
    for max_days, band_score in _MAINTAINER_BANDS:
        if days <= max_days:
            score = band_score
            break

    evidence = (
        f"最近一次可偵測活動（commit/release/issue 回應）距今 {days} 天"
        if lang == "zh"
        else f"most recent detectable activity (commit/release/issue response) was {days} days ago"
    )
    return SubScore("maintainer 90d activity", score, evidence)


def _classify_pattern(issue_score: int, maintainer_score: int, cadence_score: int) -> str:
    if issue_score < 30 and maintainer_score <= 20:
        return "anomalous-stalled"
    if issue_score >= 60 and maintainer_score >= 50:
        return "healthy" if cadence_score >= 70 else "stable-low-frequency"
    return "mixed"


def compute_s2(raw: RawSignals, lang: str = "en") -> S2Result:
    if raw.fetched_at.tzinfo:
        now = raw.fetched_at.astimezone(timezone.utc)
    else:
        now = raw.fetched_at.replace(tzinfo=timezone.utc)

    issues_only = [s for s in raw.issue_sample if not s.is_pr]
    prs_only = [s for s in raw.issue_sample if s.is_pr]

    cadence = score_cadence(raw.last_commit_at, raw.last_release_at, now, lang)
    issue_response = score_issue_response(issues_only, lang)
    pr_response = score_pr_response(prs_only, lang)
    bus_factor = score_bus_factor(raw.author_commit_counts, lang)
    maintainer = score_maintainer_activity(raw, now, lang)

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
