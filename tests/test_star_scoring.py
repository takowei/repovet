from datetime import datetime, timedelta, timezone

from repovet.star_collectors import RawStarSignals, StarSample
from repovet.star_scoring import compute_s1

NOW = datetime.now(timezone.utc)


def _throwaway(starred_at) -> StarSample:
    """Zero repos, zero followers, account created same day it starred."""
    return StarSample(
        login="throwaway",
        starred_at=starred_at,
        account_created_at=starred_at - timedelta(hours=2),
        followers=0,
        owned_repos=0,
    )


def _real_dev(starred_at, years_old=3) -> StarSample:
    return StarSample(
        login="real-dev",
        starred_at=starred_at,
        account_created_at=starred_at - timedelta(days=365 * years_old),
        followers=50,
        owned_repos=12,
    )


def _raw(sample: list[StarSample]) -> RawStarSignals:
    return RawStarSignals(
        owner="acme",
        repo="lib",
        fetched_at=NOW,
        stargazer_count=len(sample),
        sample=sample,
        sampling_note="full scan (test)",
    )


def test_coordinated_fake_star_burst_is_flagged_anomalous():
    """305-ish throwaway accounts all starring within a 48h window -> the
    real-world sidetrip-ai/ici-core pattern found during M1 calibration."""
    burst_time = NOW - timedelta(days=60)
    sample = [_throwaway(burst_time + timedelta(minutes=i)) for i in range(40)]
    # a trickle of older, unrelated real stars outside the burst window
    sample += [_real_dev(NOW - timedelta(days=200 + i * 10)) for i in range(10)]

    result = compute_s1(_raw(sample))
    assert result.pattern == "anomalous-star-pattern"
    assert result.overall < 40


def test_pervasive_fake_stars_flagged_even_without_a_clean_baseline():
    """Regression test for a real edge case found on sidetrip-ai/ici-core:
    when almost the WHOLE sample is throwaway accounts (not just a narrow
    burst), the "outside the window" baseline is itself mostly fake too, so
    the correlation signal weakens -- but account quality alone (93%
    suspicious) should still be enough to call this anomalous."""
    burst_time = NOW - timedelta(days=60)
    sample = [_throwaway(burst_time + timedelta(minutes=i)) for i in range(60)]
    # the "outside window" trickle is also mostly throwaway accounts
    sample += [_throwaway(NOW - timedelta(days=200 + i * 5)) for i in range(30)]
    sample += [_real_dev(NOW - timedelta(days=300 + i * 5)) for i in range(5)]

    result = compute_s1(_raw(sample))
    assert result.pattern == "anomalous-star-pattern"


def test_organic_burst_with_real_accounts_is_not_flagged():
    """A Hacker News-style viral spike: many stars in 48h, but from real,
    established accounts -> should NOT read as fake."""
    burst_time = NOW - timedelta(days=10)
    sample = [_real_dev(burst_time + timedelta(minutes=i * 5)) for i in range(40)]
    sample += [_real_dev(NOW - timedelta(days=200 + i * 10)) for i in range(10)]

    result = compute_s1(_raw(sample))
    assert result.pattern == "organic-burst"
    assert result.overall >= 60


def test_steady_organic_growth_is_clean():
    sample = [_real_dev(NOW - timedelta(days=i * 20)) for i in range(30)]

    result = compute_s1(_raw(sample))
    assert result.pattern == "clean"
    assert result.overall >= 80


def test_beginner_repo_false_positive_risk_documented_not_silently_flagged():
    """Many new-account stargazers, but spread out over a year (not a burst)
    -> should land in 'elevated-suspicious-accounts', not 'anomalous', since
    there's no timing correlation to suggest coordination."""
    sample = [
        _throwaway(NOW - timedelta(days=i * 12)) for i in range(30)
    ]  # spread ~1/year, not a burst

    result = compute_s1(_raw(sample))
    assert result.pattern == "elevated-suspicious-accounts"


def test_tiny_sample_gets_neutral_scores_not_confident_verdict():
    sample = [_throwaway(NOW), _throwaway(NOW - timedelta(hours=1))]
    result = compute_s1(_raw(sample))
    assert any("too small" in w for w in result.warnings)


def test_empty_sample_does_not_crash():
    result = compute_s1(_raw([]))
    assert result.overall >= 0
