from repovet.dependency_collectors import RawDependencySignals
from repovet.dependency_scoring import compute_s3
from repovet.registry_client import PackageInfo


def _raw(packages, manifests=("requirements.txt",)):
    from datetime import datetime, timezone

    return RawDependencySignals(
        owner="acme",
        repo="lib",
        fetched_at=datetime.now(timezone.utc),
        manifests_found=list(manifests),
        packages=packages,
    )


def _healthy(name, ecosystem="pypi", age_days=2000, downloads=None):
    return PackageInfo(
        name=name, ecosystem=ecosystem, exists=True, age_days=age_days, weekly_downloads=downloads
    )


def test_all_healthy_deps_score_clean():
    packages = [_healthy("requests"), _healthy("flask"), _healthy("click")]
    result = compute_s3(_raw(packages))
    assert result.pattern == "clean"
    assert result.overall >= 90


def test_single_hallucinated_dependency_caps_score_hard():
    """The core M2 claim: even ONE nonexistent dependency out of many real
    ones should not be diluted away by a large healthy dependency tree."""
    packages = [_healthy(f"realpkg{i}") for i in range(30)]
    packages.append(PackageInfo(name="xyz-utils-hallucinated", ecosystem="pypi", exists=False))
    result = compute_s3(_raw(packages))
    assert result.pattern == "hallucinated-dependency"
    assert result.overall <= 40


def test_established_real_package_near_a_popular_name_is_not_flagged():
    """The exact case the coordinator called out: npm's `request` is a real,
    ~14-year-old package name-adjacent to nothing suspicious by itself, but
    it happens to be a near neighbor in edit-distance terms to some popular
    names conceptually. A long-established package must never be flagged
    purely because a string-distance check fires -- registry age wins."""
    old_and_established = PackageInfo(
        name="request", ecosystem="npm", exists=True, age_days=14 * 365, weekly_downloads=2_000_000
    )
    result = compute_s3(_raw([old_and_established, _healthy("lodash", "npm", age_days=4000)]))
    assert result.pattern == "clean"


def test_young_low_download_name_near_popular_package_is_flagged_typosquat():
    suspect = PackageInfo(
        name="reqeusts", ecosystem="pypi", exists=True, age_days=5, weekly_downloads=None
    )
    result = compute_s3(_raw([suspect, _healthy("flask")]))
    assert result.pattern == "typosquat-suspect"


def test_young_npm_package_far_from_any_popular_name_is_not_typosquat():
    """Being young alone isn't suspicious -- only young/obscure AND
    name-adjacent to something popular should escalate."""
    fresh_but_unrelated_name = PackageInfo(
        name="my-companys-internal-widget-lib",
        ecosystem="npm",
        exists=True,
        age_days=3,
        weekly_downloads=10,
    )
    result = compute_s3(_raw([fresh_but_unrelated_name]))
    assert result.pattern != "typosquat-suspect"


def test_no_dependencies_declared_is_neutral_not_penalized():
    result = compute_s3(_raw([]))
    assert result.overall >= 60


def test_pypi_packages_produce_a_no_download_signal_warning():
    result = compute_s3(_raw([_healthy("requests")]))
    assert any("download" in w for w in result.warnings)


def test_evidence_is_english_by_default_and_chinese_on_request():
    packages = [_healthy(f"realpkg{i}") for i in range(5)]
    packages.append(PackageInfo(name="xyz-hallucinated", ecosystem="pypi", exists=False))

    en_result = compute_s3(_raw(packages), lang="en")
    zh_result = compute_s3(_raw(packages), lang="zh")

    existence_en = next(s for s in en_result.sub_scores if s.name == "dependency existence")
    existence_zh = next(s for s in zh_result.sub_scores if s.name == "dependency existence")
    assert "don't exist" in existence_en.evidence
    assert "查無此套件" in existence_zh.evidence

    for en_sub, zh_sub in zip(en_result.sub_scores, zh_result.sub_scores, strict=True):
        assert en_sub.score == zh_sub.score
        assert en_sub.name == zh_sub.name
    assert en_result.overall == zh_result.overall
    assert en_result.pattern == zh_result.pattern
