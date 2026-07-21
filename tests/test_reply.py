from repovet.reply import render_reply, render_reply_en, render_reply_zh

_RECORD = {
    "status": "ok",
    "target": "gh:acme/lib",
    "signals": {
        "s2": {
            "status": "ok",
            "formula_version": "s2.v2",
            "overall": 86,
            "pattern": "healthy",
            "sub_scores": [
                {"name": "commit/release cadence", "score": 100, "evidence": "recent commit"},
                {"name": "issue responsiveness", "score": 20, "evidence": "0/5 issues answered"},
            ],
            "warnings": [],
        },
        "s1": {"status": "skipped", "message": "no GITHUB_TOKEN"},
        "s3": {"status": "network_error", "message": "registry timeout"},
    },
}


def test_render_reply_en_contains_all_signal_lines():
    text = render_reply_en(_RECORD)
    assert "Zombie maintenance (S2): 86/100 (healthy)" in text
    assert "skipped (no GITHUB_TOKEN)" in text
    assert "network_error — registry timeout" in text


def test_render_reply_en_picks_lowest_scoring_evidence_first():
    text = render_reply_en(_RECORD)
    lines = text.splitlines()
    evidence_start = lines.index("Key evidence:")
    first_bullet = lines[evidence_start + 1]
    assert "issue responsiveness" in first_bullet  # score 20, lower than 100


def test_render_reply_en_includes_method_note_and_signature():
    text = render_reply_en(_RECORD)
    assert "Method:" in text or "s2.v2" in text
    assert "not a verdict" in text


def test_render_reply_zh_is_in_chinese():
    text = render_reply_zh(_RECORD)
    assert "信任體檢" in text
    assert "關鍵證據" in text
    assert "判決" in text


def test_render_reply_dispatches_on_lang():
    assert render_reply(_RECORD, lang="en") == render_reply_en(_RECORD)
    assert render_reply(_RECORD, lang="zh") == render_reply_zh(_RECORD)
    assert render_reply(_RECORD) == render_reply_en(_RECORD)  # default


def test_render_reply_no_signals_ok_does_not_crash():
    record = {
        "target": "gh:acme/empty",
        "signals": {
            "s2": {"status": "network_error", "message": "boom"},
            "s1": {"status": "skipped", "message": "no token"},
            "s3": {"status": "skipped", "message": "no manifest"},
        },
    }
    text = render_reply_en(record)
    assert "Key evidence:" in text


_RECORD_WITH_S4 = {
    **_RECORD,
    "signals": {
        **_RECORD["signals"],
        "s4": {
            "status": "ok",
            "formula_version": "s4.v0",
            "hints": [
                {
                    "name": "readme-tone",
                    "observation": "uniform phrasing",
                    "disclaimer": "not a verdict",
                }
            ],
            "warnings": [],
        },
    },
}


def test_render_reply_en_include_s4_adds_hints_block():
    without = render_reply_en(_RECORD_WITH_S4, include_s4=False)
    assert "AI-slop hints" not in without

    with_s4 = render_reply_en(_RECORD_WITH_S4, include_s4=True)
    assert "AI-slop hints (S4, v0" in with_s4
    assert "readme-tone: uniform phrasing" in with_s4
    assert "(not a verdict)" in with_s4


def test_render_reply_zh_include_s4_adds_hints_block():
    with_s4 = render_reply_zh(_RECORD_WITH_S4, include_s4=True)
    assert "AI-slop 特徵提示" in with_s4
    assert "readme-tone: uniform phrasing" in with_s4


def test_render_reply_include_s4_no_effect_when_s4_missing_or_not_ok():
    # _RECORD has no "s4" key at all -- include_s4 must not crash or add a block.
    text = render_reply_en(_RECORD, include_s4=True)
    assert "AI-slop hints" not in text


def test_render_reply_skips_signal_key_entirely_absent_from_dict():
    # Only s2 present; s1/s3 not in the dict at all (distinct from status=skipped).
    record = {
        "target": "gh:acme/lib",
        "signals": {
            "s2": {
                "status": "ok",
                "formula_version": "s2.v2",
                "overall": 86,
                "pattern": "healthy",
                "sub_scores": [{"name": "cadence", "score": 100, "evidence": "recent commit"}],
                "warnings": [],
            },
        },
    }
    text = render_reply_en(record)
    assert "Zombie maintenance (S2): 86/100 (healthy)" in text
    assert "Anomalous star pattern (S1)" not in text
    assert "Hallucinated dependency (S3)" not in text
