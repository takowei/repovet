"""Turn a leaderboard-data.json scan result into a static HTML report.

Plain HTML+CSS, no build step, no JS framework -- matches the CLI's own
"no opaque single number, no LLM in the scoring path" ethos: every score on
the page traces back to the same evidence the CLI prints.

Wording is deliberately conservative throughout (see WORDING NOTE below):
repovet's signals are described in its own README as having known false
negatives and, for S4, weak-to-no discriminating power. This page must never
imply a signal is proof of wrongdoing by a real project or maintainer.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

LEADERBOARD_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_FILE = LEADERBOARD_DIR / "leaderboard-data.json"
DEFAULT_OUTPUT_FILE = LEADERBOARD_DIR / "index.html"

# Signals that produce a 0-100 "overall" trust score. S4 is intentionally
# excluded: per repovet's own README it is v0/hints-only with no overall
# score and documented weak discriminating power -- folding it into a
# ranking number would overstate its reliability.
SCORED_SIGNAL_KEYS = ("s1", "s2", "s3")

WORDING_NOTE = (
    "This page reports repovet's automated signals, not verified findings. "
    "A low score means the signal's evidence looks unusual by repovet's "
    "formulas -- it is not proof of fake stars, abandonment, or malicious "
    "intent, and every formula has documented false-negative and "
    "false-positive limitations (see below). Always read the evidence, "
    "not just the number."
)

KNOWN_LIMITATIONS = [
    "S1 (star pattern) is structurally weaker at detecting older fake-star "
    "campaigns -- it only sees each account's current state, not its state "
    "at the time it starred. This is repovet's biggest documented gap.",
    "S1's sampling methodology note is currently only published in English "
    "regardless of the report language.",
    "S3 (dependency) typosquat detection only checks against a curated "
    "~60-name allowlist per ecosystem, and PyPI dependencies carry no "
    "download-count signal (pypistats.org rate-limits repeated calls).",
    "S4 (AI-slop hints) is v0 and, per repovet's own demo results, showed "
    "weak-to-no discriminating power -- it is excluded from this page's "
    "ranking score for that reason and is not shown here.",
    "This leaderboard uses a small, fixed seed list of well-known projects "
    "(see seed-repos.json for selection criteria), not a live or "
    "exhaustive scan of GitHub.",
]


def _overall_scores(record: dict) -> list[tuple[str, int]]:
    scores = []
    for key in SCORED_SIGNAL_KEYS:
        block = record.get("signals", {}).get(key, {})
        if block.get("status") == "ok" and "overall" in block:
            scores.append((key, block["overall"]))
    return scores


def _composite_score(record: dict) -> float | None:
    scores = _overall_scores(record)
    if not scores:
        return None
    return round(sum(v for _, v in scores) / len(scores), 1)


def _score_class(score: float) -> str:
    if score >= 70:
        return "score-ok"
    if score >= 40:
        return "score-mixed"
    return "score-low"


def _e(text: object) -> str:
    return html.escape(str(text))


def _signal_summary(key: str, block: dict) -> str:
    title = {
        "s1": "S1 star pattern",
        "s2": "S2 maintenance",
        "s3": "S3 dependency",
    }.get(key, key)
    status = block.get("status")
    if status == "skipped":
        message = _e(block.get("message", ""))
        return f'<span class="sig sig-skip">{_e(title)}: skipped ({message})</span>'
    if status != "ok":
        return f'<span class="sig sig-err">{_e(title)}: {_e(status)}</span>'
    overall = block.get("overall")
    pattern = block.get("pattern", "")
    cls = _score_class(overall) if overall is not None else "score-mixed"
    return f'<span class="sig {cls}">{_e(title)}: {_e(overall)}/100 <em>[{_e(pattern)}]</em></span>'


def _repo_row(record: dict) -> str:
    target = record.get("target", "?")
    slug = target.removeprefix("gh:")
    meta = record.get("_seed_meta", {})
    if record.get("status") != "ok":
        return (
            f'<tr class="error-row"><td><a href="https://github.com/{_e(slug)}" '
            f'target="_blank" rel="noopener">{_e(slug)}</a></td>'
            f'<td colspan="3">could not scan: {_e(record.get("error", "unknown error"))}</td></tr>'
        )

    composite = _composite_score(record)
    composite_display = f"{composite}/100" if composite is not None else "n/a"
    signal_spans = " &nbsp;·&nbsp; ".join(
        _signal_summary(k, record["signals"][k])
        for k in ("s2", "s1", "s3")
        if k in record["signals"]
    )
    composite_cls = _score_class(composite) if composite is not None else "score-mixed"
    return f"""<tr>
      <td class="repo-cell">
        <a href="https://github.com/{_e(slug)}" target="_blank" rel="noopener">{_e(slug)}</a>
        <div class="meta">{_e(meta.get("language", ""))} &middot; {_e(meta.get("tier", ""))}</div>
      </td>
      <td class="composite {composite_cls}">{_e(composite_display)}</td>
      <td class="signals">{signal_spans}</td>
    </tr>"""


CSS = """
:root { color-scheme: light; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; line-height: 1.5; }
h1 { margin-bottom: 0.2rem; }
.subtitle { color: #555; margin-top: 0; }
.notice { background: #fff8e6; border: 1px solid #e8c468; border-radius: 6px;
          padding: 0.9rem 1.1rem; margin: 1.2rem 0; font-size: 0.95rem; }
table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
th, td { text-align: left; padding: 0.6rem 0.7rem; border-bottom: 1px solid #e2e2e2;
         vertical-align: top; }
th { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.03em; color: #666; }
.repo-cell a { font-weight: 600; text-decoration: none; color: #0b5fa5; }
.repo-cell a:hover { text-decoration: underline; }
.meta { font-size: 0.8rem; color: #777; }
.composite { font-weight: 700; font-variant-numeric: tabular-nums; }
.score-ok { color: #1a7f37; }
.score-mixed { color: #9a6700; }
.score-low { color: #c0341d; }
.sig { display: inline-block; white-space: nowrap; font-size: 0.85rem; }
.sig-skip, .sig-err { color: #888; font-style: italic; }
.error-row td { color: #888; font-style: italic; }
footer { margin-top: 2.5rem; font-size: 0.82rem; color: #666;
         border-top: 1px solid #e2e2e2; padding-top: 1rem; }
footer ul { padding-left: 1.2rem; }
code { background: #f4f4f4; padding: 0.1rem 0.3rem; border-radius: 3px; }
"""


def render_html(payload: dict) -> str:
    records = payload.get("records", [])
    scored = [r for r in records if _composite_score(r) is not None]
    unscored = [r for r in records if _composite_score(r) is None]
    scored.sort(key=lambda r: _composite_score(r), reverse=True)
    rows = "\n".join(_repo_row(r) for r in scored + unscored)

    limitations_html = "\n".join(f"<li>{_e(item)}</li>" for item in KNOWN_LIMITATIONS)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>repovet leaderboard -- automated repo trust signals</title>
<style>{CSS}</style>
</head>
<body>
<h1>repovet leaderboard</h1>
<p class="subtitle">Automated, re-runnable trust signals for a fixed set of well-known
open source projects, generated by
<a href="https://github.com/takowei/repovet" target="_blank" rel="noopener">repovet</a>.</p>

<div class="notice">{_e(WORDING_NOTE)}</div>

<table>
  <thead>
    <tr><th>repo</th><th>composite score</th>
        <th>signals (S2 maintenance &middot; S1 star pattern &middot; S3 dependency)</th></tr>
  </thead>
  <tbody>
    {rows}
  </tbody>
</table>

<footer>
  <p><strong>Generated:</strong> {_e(payload.get("generated_at", "unknown"))} &middot;
     <strong>Repos scanned:</strong> {_e(payload.get("repo_count", len(records)))} &middot;
     <strong>Seed list:</strong> <code>{_e(payload.get("seed_file", "seed-repos.json"))}</code></p>
  <p><strong>Known limitations of the signals shown here:</strong></p>
  <ul>{limitations_html}</ul>
  <p>Composite score = simple average of S1/S2/S3 "overall" scores that returned status "ok"
     for that repo (S4 is excluded -- see limitations). Full per-signal evidence is available
     by running <code>repovet gh:owner/repo</code> yourself.</p>
</footer>
</body>
</html>
"""


def run(data_file: Path, output_file: Path) -> None:
    payload = json.loads(data_file.read_text(encoding="utf-8"))
    output_file.write_text(render_html(payload), encoding="utf-8")
    print(f"wrote {output_file}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA_FILE)
    parser.add_argument("--output-file", type=Path, default=DEFAULT_OUTPUT_FILE)
    args = parser.parse_args(argv)
    run(args.data_file, args.output_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
