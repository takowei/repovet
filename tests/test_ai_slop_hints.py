from repovet.ai_slop_collectors import RawSlopSignals
from repovet.ai_slop_hints import compute_s4

_NORMAL_README = """# Demo Project

[![Build](https://img.shields.io/github/actions/workflow/status/acme/demo/ci.yml)](x)

A small utility library for doing X.

## Installation

pip install demo

## Usage

See the docs.
"""

_SLOPPY_README = """# 🚀 Awesome Demo Project ✨

[![badge](https://img.shields.io/badge/one-blue)](x)
[![badge](https://img.shields.io/badge/two-green)](x)
[![badge](https://img.shields.io/badge/three-red)](x)
[![badge](https://img.shields.io/badge/four-yellow)](x)

## ✨ Features

This project aims to solve all your problems.

## 🚀 Getting Started

In this repository, you will find everything you need.

## 🤝 Contributing

Feel free to contribute! Contributions are welcome.
"""


def _raw(readme=None, commit_messages=(), root_entries=(), github_entries=()):
    return RawSlopSignals(
        owner="acme",
        repo="demo",
        readme_text=readme,
        commit_messages=list(commit_messages),
        root_entries=list(root_entries),
        github_dir_entries=list(github_entries),
    )


def test_no_score_or_pattern_fields():
    """The core v0 constraint: hints only, no 0-100 score, no pattern verdict."""
    result = compute_s4(_raw(readme=_NORMAL_README))
    assert not hasattr(result, "overall")
    assert not hasattr(result, "pattern")
    assert result.formula_version == "s4.v0"


def test_every_hint_has_a_disclaimer():
    result = compute_s4(_raw(readme=_SLOPPY_README, root_entries=["LICENSE"]))
    for hint in result.hints:
        assert hint.disclaimer  # never empty
        assert hint.observation
        assert hint.raw_value is not None


def test_sloppy_readme_shows_more_badges_emoji_and_boilerplate_than_normal():
    """Directional check, not a verdict: a README stuffed with badges/emoji/
    boilerplate should show higher raw values than a plain one."""
    normal = compute_s4(_raw(readme=_NORMAL_README))
    sloppy = compute_s4(_raw(readme=_SLOPPY_README))

    def hint_value(result, name):
        return next(h.raw_value for h in result.hints if h.name == name)

    assert hint_value(sloppy, "readme badge density") > hint_value(normal, "readme badge density")
    assert hint_value(sloppy, "README emoji-header density") > hint_value(
        normal, "README emoji-header density"
    )
    assert hint_value(sloppy, "README boilerplate phrase hits") > hint_value(
        normal, "README boilerplate phrase hits"
    )


def test_shell_comments_in_code_fences_are_not_counted_as_headers():
    """Regression test for a real bug found during the S4 live demo
    (sidetrip-ai/ici-core): naive '#'-line counting inflated the header
    count to 60 by counting bash comments inside ```-fenced setup
    snippets. Only real markdown headers outside code fences should count."""
    readme = """# Real Header

## Getting Started

```bash
# 1. Clone the repository
# 2. Run the setup script
# 3. Activate venv
```

## Usage
"""
    result = compute_s4(_raw(readme=readme))
    hint = next(h for h in result.hints if h.name == "README emoji-header density")
    assert "/3" in hint.observation  # 3 real headers, not 6 (3 real + 3 fenced comments)


def test_missing_readme_warns_and_skips_readme_hints():
    result = compute_s4(_raw(readme=None))
    hint_names = {h.name for h in result.hints}
    assert "readme badge density" not in hint_names
    assert any("README" in w for w in result.warnings)


def test_scaffolding_hint_counts_known_markers():
    result = compute_s4(
        _raw(
            readme=_NORMAL_README,
            root_entries=["LICENSE", "CONTRIBUTING.md", "src"],
            github_entries=["workflows", "ISSUE_TEMPLATE"],
        )
    )
    scaffold = next(h for h in result.hints if h.name == "repo scaffolding completeness")
    assert scaffold.raw_value == 4  # LICENSE, CONTRIBUTING.md, workflows, issue templates


def test_too_few_commits_warns_instead_of_computing_uniformity_hint():
    result = compute_s4(_raw(readme=_NORMAL_README, commit_messages=["a", "b", "c"]))
    hint_names = {h.name for h in result.hints}
    assert "commit message length uniformity" not in hint_names
    assert any("too few commits" in w for w in result.warnings)


def test_uniform_commit_messages_score_low_cv():
    uniform = [f"chore: update dependency {i:03d}" for i in range(10)]
    result = compute_s4(_raw(readme=_NORMAL_README, commit_messages=uniform))
    hint = next(h for h in result.hints if h.name == "commit message length uniformity")
    assert hint.raw_value < 0.1  # nearly identical lengths -> near-zero variation


def test_lang_zh_produces_chinese_observations():
    result = compute_s4(_raw(readme=_NORMAL_README, root_entries=["LICENSE"]), lang="zh")
    badge_hint = next(h for h in result.hints if h.name == "readme badge density")
    assert "找到" in badge_hint.observation
    assert "badge" in badge_hint.observation.lower() or "圖片" in badge_hint.observation
