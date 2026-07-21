from dataclasses import dataclass, field

from repovet import output
from repovet.targets import Target


@dataclass
class _FakeSubScore:
    name: str
    score: int
    evidence: str


@dataclass
class _FakeResult:
    formula_version: str
    overall: int
    pattern: str
    sub_scores: list
    warnings: list = field(default_factory=list)
    sampling_note: str = ""
    manifests_found: list = field(default_factory=list)


@dataclass
class _FakeHint:
    name: str
    observation: str
    disclaimer: str


@dataclass
class _FakeS4Result:
    formula_version: str
    hints: list
    warnings: list = field(default_factory=list)


def _sub(name="cadence", score=80, evidence="recent commit"):
    return _FakeSubScore(name=name, score=score, evidence=evidence)


def test_signal_block_has_common_shape():
    result = _FakeResult(
        formula_version="s2.v2",
        overall=86,
        pattern="healthy",
        sub_scores=[_sub()],
        warnings=["stale cache"],
    )
    block = output.signal_block(result)
    assert block["status"] == output.OK
    assert block["formula_version"] == "s2.v2"
    assert block["overall"] == 86
    assert block["pattern"] == "healthy"
    assert block["sub_scores"] == [{"name": "cadence", "score": 80, "evidence": "recent commit"}]
    assert block["warnings"] == ["stale cache"]
    assert "sampling_note" not in block
    assert "manifests_found" not in block


def test_signal_block_surfaces_extra_fields_when_present():
    result = _FakeResult(
        formula_version="s1.v1",
        overall=90,
        pattern="normal",
        sub_scores=[_sub()],
        sampling_note="sampled 40/500 stargazers",
    )
    block = output.signal_block(result)
    assert block["sampling_note"] == "sampled 40/500 stargazers"
    assert "manifests_found" not in block

    result2 = _FakeResult(
        formula_version="s3.v1",
        overall=70,
        pattern="ok",
        sub_scores=[_sub()],
        manifests_found=["pyproject.toml"],
    )
    block2 = output.signal_block(result2)
    assert block2["manifests_found"] == ["pyproject.toml"]


def test_s4_signal_block_has_no_overall_or_pattern():
    result = _FakeS4Result(
        formula_version="s4.v0",
        hints=[_FakeHint(name="readme-tone", observation="uniform", disclaimer="not a verdict")],
    )
    block = output.s4_signal_block(result)
    assert block["status"] == output.OK
    assert "overall" not in block
    assert "pattern" not in block
    assert block["hints"] == [
        {"name": "readme-tone", "observation": "uniform", "disclaimer": "not a verdict"}
    ]


def test_signal_unavailable():
    block = output.signal_unavailable(output.SKIPPED, "no GITHUB_TOKEN")
    assert block == {"status": output.SKIPPED, "message": "no GITHUB_TOKEN"}


def test_success_record_and_error_record():
    target = Target(kind="gh", owner="acme", repo="lib")
    record = output.success_record(target, {"s2": {"status": output.OK}})
    assert record == {
        "status": output.OK,
        "target": "gh:acme/lib",
        "signals": {"s2": {"status": output.OK}},
    }

    err = output.error_record("gh:bad/repo", output.INPUT_ERROR, "not found")
    assert err == {"status": output.INPUT_ERROR, "target": "gh:bad/repo", "error": "not found"}


def test_render_json_single_vs_batch():
    records = [{"status": output.OK, "target": "gh:acme/lib", "signals": {}}]
    single = output.render_json(records, batch=False)
    assert single.startswith("{")
    assert '"target": "gh:acme/lib"' in single

    batch = output.render_json(records, batch=True)
    assert batch.startswith("[")


def test_render_table_ok_signal_with_sub_scores():
    block = output.signal_block(
        _FakeResult(
            formula_version="s2.v2",
            overall=86,
            pattern="healthy",
            sub_scores=[_sub("issue responsiveness", 20, "0/5 answered")],
            warnings=["cache stale"],
        )
    )
    record = {"status": output.OK, "target": "gh:acme/lib", "signals": {"s2": block}}
    text = output.render_table([record])
    assert "repovet — gh:acme/lib" in text
    assert "S2 zombie-maintenance: 86/100 [healthy]" in text
    assert "issue responsiveness" in text
    assert "0/5 answered" in text
    assert "formula: s2.v2" in text
    assert "warning: cache stale" in text


def test_render_table_shows_sampling_note_and_manifests_found():
    s1_block = output.signal_block(
        _FakeResult(
            formula_version="s1.v1",
            overall=90,
            pattern="normal",
            sub_scores=[_sub()],
            sampling_note="sampled 40/500 stargazers",
        )
    )
    s3_block = output.signal_block(
        _FakeResult(
            formula_version="s3.v1",
            overall=70,
            pattern="ok",
            sub_scores=[_sub()],
            manifests_found=["pyproject.toml", "requirements.txt"],
        )
    )
    record = {
        "status": output.OK,
        "target": "gh:acme/lib",
        "signals": {"s1": s1_block, "s3": s3_block},
    }
    text = output.render_table([record])
    assert "sampling: sampled 40/500 stargazers" in text
    assert "manifests: pyproject.toml, requirements.txt" in text


def test_render_table_skipped_and_error_signal_status():
    record = {
        "status": output.OK,
        "target": "gh:acme/lib",
        "signals": {
            "s1": output.signal_unavailable(output.SKIPPED, "no GITHUB_TOKEN"),
            "s3": output.signal_unavailable(output.NETWORK_ERROR, "registry timeout"),
        },
    }
    text = output.render_table([record])
    assert "S1 anomalous star pattern: skipped (no GITHUB_TOKEN)" in text
    assert "S3 hallucinated dependency: ERROR (network_error): registry timeout" in text


def test_render_table_s4_hints_block():
    s4_block = output.s4_signal_block(
        _FakeS4Result(
            formula_version="s4.v0",
            hints=[
                _FakeHint(
                    name="readme-tone",
                    observation="uniform phrasing",
                    disclaimer="not a verdict",
                )
            ],
            warnings=["low sample"],
        )
    )
    record = {"status": output.OK, "target": "gh:acme/lib", "signals": {"s4": s4_block}}
    text = output.render_table([record])
    assert "AI-slop hints" in text
    assert "readme-tone: uniform phrasing" in text
    assert "disclaimer: not a verdict" in text
    assert "formula: s4.v0" in text
    assert "warning: low sample" in text


def test_render_table_top_level_error_record():
    record = {"status": output.INPUT_ERROR, "target": "gh:bad/repo", "error": "not found"}
    text = output.render_table([record])
    assert "repovet — gh:bad/repo" in text
    assert "ERROR (input_error): not found" in text


def test_render_table_joins_multiple_records_with_blank_line():
    record_a = {"status": output.INPUT_ERROR, "target": "gh:a/a", "error": "boom"}
    record_b = {"status": output.INPUT_ERROR, "target": "gh:b/b", "error": "boom"}
    text = output.render_table([record_a, record_b])
    assert "gh:a/a" in text
    assert "gh:b/b" in text
    assert "\n\n" in text
