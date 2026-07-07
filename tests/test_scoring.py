from datetime import datetime, timedelta, timezone

from repovet.collectors import IssueSample, RawSignals
from repovet.scoring import compute_s2

NOW = datetime.now(timezone.utc)


def _days_ago(n):
    return NOW - timedelta(days=n)


def _issue(days_ago_created, response_delay_days=None, is_pr=False):
    created = _days_ago(days_ago_created)
    responded = (
        created + timedelta(days=response_delay_days) if response_delay_days is not None else None
    )
    return IssueSample(number=1, created_at=created, responded_at=responded, is_pr=is_pr)


def _pr(days_ago_created, response_delay_days=None):
    return _issue(days_ago_created, response_delay_days, is_pr=True)


def test_stable_low_frequency_is_not_flagged_as_zombie():
    """Old last commit/release, but issues still get answered and someone showed up
    recently -> should read as stable, not abandoned."""
    raw = RawSignals(
        owner="acme",
        repo="mature-lib",
        fetched_at=NOW,
        last_commit_at=_days_ago(500),
        last_release_at=_days_ago(600),
        author_commit_counts={"alice": 20, "bob": 5},
        commit_sample_count=25,
        commit_sample_since=_days_ago(365),
        issue_sample=[_issue(100, response_delay_days=3) for _ in range(10)],
        anonymous=False,
    )
    result = compute_s2(raw)
    assert result.pattern in ("stable-low-frequency", "healthy")
    assert result.overall >= 60


def test_abandoned_repo_is_flagged_anomalous_stalled():
    """No commits/releases in years, issues pile up unanswered, nobody active
    recently -> should be flagged as the anomalous/stalled pattern."""
    raw = RawSignals(
        owner="acme",
        repo="dead-lib",
        fetched_at=NOW,
        last_commit_at=_days_ago(2000),
        last_release_at=_days_ago(2200),
        author_commit_counts={"alice": 30},
        commit_sample_count=0,
        commit_sample_since=_days_ago(365),
        issue_sample=[_issue(300) for _ in range(10)],  # never responded
        anonymous=False,
    )
    result = compute_s2(raw)
    assert result.pattern == "anomalous-stalled"
    assert result.overall < 40


def test_active_healthy_repo_scores_high():
    raw = RawSignals(
        owner="acme",
        repo="active-lib",
        fetched_at=NOW,
        last_commit_at=_days_ago(1),
        last_release_at=_days_ago(10),
        author_commit_counts={"alice": 10, "bob": 8, "carol": 7, "dave": 5},
        commit_sample_count=30,
        commit_sample_since=_days_ago(365),
        issue_sample=[_issue(2, response_delay_days=1) for _ in range(15)],
        anonymous=False,
    )
    result = compute_s2(raw)
    assert result.pattern == "healthy"
    assert result.overall >= 85


def test_pr_flood_does_not_drag_down_a_healthy_repo():
    """Regression test for the psf/requests confound found during M0 demo:
    a healthy repo whose real issues are answered quickly should not be
    dragged into 'mixed'/'anomalous' just because most of the recent
    activity is driveby PRs that get no response."""
    real_issues = [_issue(20, response_delay_days=1) for _ in range(2)]
    driveby_prs = [_pr(5) for _ in range(13)]  # never responded, 0 comments
    raw = RawSignals(
        owner="acme",
        repo="popular-lib",
        fetched_at=NOW,
        last_commit_at=_days_ago(0),
        last_release_at=_days_ago(5),
        author_commit_counts={"a": 10, "b": 8, "c": 7},
        commit_sample_count=25,
        commit_sample_since=_days_ago(365),
        issue_sample=real_issues + driveby_prs,
        anonymous=False,
    )
    result = compute_s2(raw)
    issue_sub = next(s for s in result.sub_scores if s.name == "issue responsiveness")
    pr_sub = next(s for s in result.sub_scores if s.name == "PR responsiveness")

    assert issue_sub.score >= 90  # real issues got answered fast
    assert pr_sub.score < 30  # PR non-response is visible, just weighted low
    assert result.pattern in ("healthy", "stable-low-frequency")


def test_no_issue_sample_gives_neutral_score_not_zero():
    raw = RawSignals(
        owner="acme",
        repo="quiet-lib",
        fetched_at=NOW,
        last_commit_at=_days_ago(10),
        last_release_at=_days_ago(20),
        author_commit_counts={"alice": 5},
        commit_sample_count=5,
        commit_sample_since=_days_ago(365),
        issue_sample=[],
        anonymous=False,
    )
    result = compute_s2(raw)
    issue_sub = next(s for s in result.sub_scores if s.name == "issue responsiveness")
    pr_sub = next(s for s in result.sub_scores if s.name == "PR responsiveness")
    assert issue_sub.score == 70
    assert pr_sub.score == 70


def test_anonymous_access_produces_warning():
    raw = RawSignals(
        owner="acme",
        repo="lib",
        fetched_at=NOW,
        last_commit_at=_days_ago(1),
        last_release_at=None,
        author_commit_counts={"alice": 1},
        commit_sample_count=1,
        commit_sample_since=_days_ago(365),
        issue_sample=[],
        anonymous=True,
    )
    result = compute_s2(raw)
    assert any("anonymous" in w for w in result.warnings)


def test_solo_maintainer_bus_factor_evidence_string():
    raw = RawSignals(
        owner="acme",
        repo="solo-lib",
        fetched_at=NOW,
        last_commit_at=_days_ago(1),
        last_release_at=_days_ago(5),
        author_commit_counts={"solo-dev": 42},
        commit_sample_count=42,
        commit_sample_since=_days_ago(365),
        issue_sample=[],
        anonymous=False,
    )
    result = compute_s2(raw)
    bus_sub = next(s for s in result.sub_scores if s.name == "bus factor")
    assert "bus factor=1" in bus_sub.evidence
    # solo maintenance is a risk factor but shouldn't zero the score out
    assert bus_sub.score > 0


def test_evidence_is_english_by_default_and_chinese_on_request():
    raw = RawSignals(
        owner="acme",
        repo="lib",
        fetched_at=NOW,
        last_commit_at=_days_ago(1),
        last_release_at=_days_ago(5),
        author_commit_counts={"solo-dev": 10},
        commit_sample_count=10,
        commit_sample_since=_days_ago(365),
        issue_sample=[_issue(20, response_delay_days=2)],
        anonymous=False,
    )
    en_result = compute_s2(raw, lang="en")
    zh_result = compute_s2(raw, lang="zh")

    cadence_en = next(s for s in en_result.sub_scores if s.name == "commit/release cadence")
    cadence_zh = next(s for s in zh_result.sub_scores if s.name == "commit/release cadence")
    assert "last commit" in cadence_en.evidence
    assert "最近 commit" in cadence_zh.evidence

    # scores must be identical across languages -- only the prose changes
    for en_sub, zh_sub in zip(en_result.sub_scores, zh_result.sub_scores, strict=True):
        assert en_sub.score == zh_sub.score
        assert en_sub.name == zh_sub.name  # names/labels are never localized
    assert en_result.overall == zh_result.overall
    assert en_result.pattern == zh_result.pattern
