"""Unit tests for the leaderboard HTML generator. Pure data-in/data-out,
no network -- mirrors the rest of the suite's "all HTTP mocked" discipline
by simply never touching HTTP at all here.
"""

from generate_site import _composite_score, _score_class, render_html
from scan_leaderboard import load_seed_repos


def _ok_record(target, s1=None, s2=None, s3=None):
    signals = {}
    if s2 is not None:
        signals["s2"] = {"status": "ok", "overall": s2, "pattern": "healthy"}
    if s1 is not None:
        signals["s1"] = {"status": "ok", "overall": s1, "pattern": "organic-burst"}
    if s3 is not None:
        signals["s3"] = {"status": "ok", "overall": s3, "pattern": "clean"}
    return {"status": "ok", "target": target, "signals": signals, "_seed_meta": {}}


def test_composite_score_averages_ok_signals_only():
    record = _ok_record("gh:a/b", s1=80, s2=90, s3=100)
    assert _composite_score(record) == 90.0


def test_composite_score_ignores_skipped_signal():
    record = _ok_record("gh:a/b", s2=80, s3=100)
    record["signals"]["s1"] = {"status": "skipped", "message": "no token"}
    assert _composite_score(record) == 90.0


def test_composite_score_none_when_all_signals_unavailable():
    record = {"status": "ok", "target": "gh:a/b", "signals": {}, "_seed_meta": {}}
    assert _composite_score(record) is None


def test_score_class_bands():
    assert _score_class(90) == "score-ok"
    assert _score_class(70) == "score-ok"
    assert _score_class(55) == "score-mixed"
    assert _score_class(10) == "score-low"


def test_render_html_escapes_hostile_repo_data():
    record = _ok_record("gh:a/<script>alert(1)</script>", s2=50)
    payload = {"generated_at": "now", "repo_count": 1, "records": [record]}
    out = render_html(payload)
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out


def test_render_html_never_uses_accusatory_language():
    payload = {"generated_at": "now", "repo_count": 0, "records": []}
    out = render_html(payload).lower()
    for banned in ("fraud", "fake project", "scam", "confirmed fake"):
        assert banned not in out


def test_render_html_puts_error_records_in_their_own_row():
    record = {"status": "input_error", "target": "gh:bad/target", "error": "boom"}
    payload = {"generated_at": "now", "repo_count": 1, "records": [record]}
    out = render_html(payload)
    assert "could not scan" in out
    assert "boom" in out


def test_load_seed_repos_returns_target_entries(tmp_path):
    import json

    seed_path = tmp_path / "seed.json"
    seed_path.write_text(
        json.dumps({"_meta": {"description": "x"}, "repos": [{"target": "gh:a/b"}]})
    )
    repos = load_seed_repos(seed_path)
    assert repos == [{"target": "gh:a/b"}]
