"""Unit tests for the weekly trending digest builder. Pure data-in/data-out,
no network, no filesystem beyond tmp_path fixtures."""

import json
from datetime import datetime, timedelta, timezone

from generate_weekly_digest import _flags_for, _load_scans, build_digest, render_markdown


def _record(slug, scan_date, s1=None, s2=None, s3=None):
    signals = {}
    if s2 is not None:
        signals["s2"] = {"status": "ok", "overall": s2[0], "pattern": s2[1]}
    if s1 is not None:
        signals["s1"] = {"status": "ok", "overall": s1[0], "pattern": s1[1]}
    if s3 is not None:
        signals["s3"] = {"status": "ok", "overall": s3[0], "pattern": s3[1]}
    return {"status": "ok", "target": slug, "signals": signals, "_scan_date": scan_date}


def test_flags_for_reports_non_clean_pattern():
    record = _record("gh:a/b", "2026-07-20", s1=(30, "star-farm-cluster"))
    assert _flags_for(record) == ["s1=star-farm-cluster (overall 30/100)"]


def test_flags_for_ignores_clean_patterns():
    record = _record("gh:a/b", "2026-07-20", s1=(90, "organic"), s2=(95, "healthy"))
    assert _flags_for(record) == []


def test_build_digest_sorts_lowest_composite_first():
    records = [
        _record("gh:a/b", "2026-07-20", s2=(90, "healthy")),
        _record("gh:c/d", "2026-07-20", s2=(10, "abandoned")),
    ]
    digest = build_digest(records, top_n=10)
    slugs = [slug for slug, _, _ in digest["lowest_composite"]]
    assert slugs == ["gh:c/d", "gh:a/b"]


def test_build_digest_dedupes_by_slug_keeping_most_recent_scan():
    records = [
        _record("gh:a/b", "2026-07-19", s2=(20, "abandoned")),
        _record("gh:a/b", "2026-07-21", s2=(90, "healthy")),
    ]
    digest = build_digest(records, top_n=10)
    assert digest["repo_count"] == 1
    assert digest["lowest_composite"][0][2] == 90.0


def test_build_digest_skips_error_records():
    records = [{"status": "network_error", "target": "gh:a/b", "_scan_date": "2026-07-20"}]
    digest = build_digest(records, top_n=10)
    assert digest["repo_count"] == 0


def test_render_markdown_lists_repo_links_and_scores():
    digest = {
        "lowest_composite": [("gh:c/d", _record("gh:c/d", "2026-07-20"), 10.0)],
        "pattern_flagged": [("gh:e/f", ["s1=star-farm-cluster (overall 20/100)"])],
        "repo_count": 2,
    }
    out = render_markdown(digest, window_days=7, generated_at="now")
    assert "[c/d](https://github.com/c/d)" in out
    assert "composite 10.0/100" in out
    assert "[e/f](https://github.com/e/f)" in out
    assert "star-farm-cluster" in out


def test_render_markdown_handles_empty_digest():
    digest = {"lowest_composite": [], "pattern_flagged": [], "repo_count": 0}
    out = render_markdown(digest, window_days=7, generated_at="now")
    assert "no scored repos" in out
    assert "no pattern flags" in out


def test_load_scans_filters_by_window_and_ignores_bad_filenames(tmp_path):
    now = datetime.now(timezone.utc)
    recent = now.strftime("%Y-%m-%d")
    old = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    (tmp_path / f"{recent}.json").write_text(
        json.dumps({"records": [{"target": "gh:a/b", "status": "ok"}]})
    )
    (tmp_path / f"{old}.json").write_text(
        json.dumps({"records": [{"target": "gh:old/repo", "status": "ok"}]})
    )
    (tmp_path / "not-a-date.json").write_text(json.dumps({"records": []}))

    records = _load_scans(tmp_path, since=now - timedelta(days=7))
    assert [r["target"] for r in records] == ["gh:a/b"]
