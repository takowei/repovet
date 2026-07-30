"""Roll up a week of scan_trending.py output into a markdown digest of the
most concerning / interesting repos seen, for manual review before any
outreach/content use.

Reads every dated JSON file in --scans-dir (default trending-scans/),
keeps only ok-status repos with at least one scored signal, and reports:
  - lowest composite score (same S1/S2/S3 average as generate_site.py --
    S4 excluded per its own documented weak discriminating power)
  - any repo where a signal's `pattern` field is not in a small allowlist
    of "nothing to see here" pattern names, surfaced as a flag worth a
    human look

This is a *pointer to evidence*, not a verdict -- every line links back to
the actual repo and states the signal name + pattern string repovet itself
produced, per the same conservative-wording convention as generate_site.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_site import _composite_score  # noqa: E402

LEADERBOARD_DIR = Path(__file__).resolve().parent
DEFAULT_SCANS_DIR = LEADERBOARD_DIR / "trending-scans"
DEFAULT_OUTPUT_DIR = LEADERBOARD_DIR / "digests"
DEFAULT_WINDOW_DAYS = 7
DEFAULT_TOP_N = 10

# Patterns that mean "nothing unusual" for each signal -- anything else is
# surfaced as a flag. Deliberately conservative allowlists so a new/unknown
# pattern name defaults to "flagged" rather than silently ignored.
_CLEAN_PATTERNS = {
    "s1": {"organic", "organic-burst", "insufficient-sample"},
    "s2": {"healthy", "stable-low-frequency"},
    "s3": {"clean"},
}


def _load_scans(scans_dir: Path, since: datetime) -> list[dict]:
    records = []
    if not scans_dir.exists():
        return records
    for path in sorted(scans_dir.glob("*.json")):
        try:
            file_date = datetime.strptime(path.stem, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if file_date < since:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for record in payload.get("records", []):
            record["_scan_date"] = path.stem
            records.append(record)
    return records


def _flags_for(record: dict) -> list[str]:
    flags = []
    for key, allowed in _CLEAN_PATTERNS.items():
        block = record.get("signals", {}).get(key, {})
        if block.get("status") != "ok":
            continue
        pattern = block.get("pattern")
        if pattern and pattern not in allowed:
            flags.append(f"{key}={pattern} (overall {block.get('overall')}/100)")
    return flags


def build_digest(records: list[dict], top_n: int) -> dict:
    """Dedupe by repo slug keeping the most recent scan, then split into
    the lowest-composite-score list and the pattern-flagged list."""
    latest_by_slug: dict[str, dict] = {}
    for record in records:
        if record.get("status") != "ok":
            continue
        slug = record.get("target", "")
        existing = latest_by_slug.get(slug)
        if existing is None or record["_scan_date"] > existing["_scan_date"]:
            latest_by_slug[slug] = record

    scored = [
        (slug, r, _composite_score(r))
        for slug, r in latest_by_slug.items()
        if _composite_score(r) is not None
    ]
    scored.sort(key=lambda item: item[2])
    lowest = scored[:top_n]

    flagged = []
    for slug, r in latest_by_slug.items():
        flags = _flags_for(r)
        if flags:
            flagged.append((slug, flags))

    return {
        "lowest_composite": lowest,
        "pattern_flagged": flagged,
        "repo_count": len(latest_by_slug),
    }


def render_markdown(digest: dict, window_days: int, generated_at: str) -> str:
    lines = [
        "# repovet weekly trending digest",
        "",
        f"Generated: {generated_at} · window: last {window_days} days · "
        f"{digest['repo_count']} distinct trending repos scanned",
        "",
        "Automated signals only, not verified findings -- every line traces back to "
        "repovet's own evidence. Low score / unusual pattern means the signal's formula "
        "found something worth a human look, not proof of anything. See repovet README "
        "for each signal's known limitations.",
        "",
        "## Lowest composite score (S1/S2/S3 average, S4 excluded)",
        "",
    ]
    if not digest["lowest_composite"]:
        lines.append("_no scored repos in this window._")
    for slug, record, score in digest["lowest_composite"]:
        repo = slug.removeprefix("gh:")
        lines.append(f"- [{repo}](https://github.com/{repo}) — composite {score}/100")

    lines += ["", "## Pattern flags (signal reported a non-clean pattern)", ""]
    if not digest["pattern_flagged"]:
        lines.append("_no pattern flags in this window._")
    for slug, flags in digest["pattern_flagged"]:
        repo = slug.removeprefix("gh:")
        flags_str = "; ".join(flags)
        lines.append(f"- [{repo}](https://github.com/{repo}) — {flags_str}")

    lines.append("")
    return "\n".join(lines)


def run(scans_dir: Path, output_dir: Path, window_days: int, top_n: int) -> Path:
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    records = _load_scans(scans_dir, since)
    digest = build_digest(records, top_n)
    generated_at = datetime.now(timezone.utc).isoformat()
    markdown = render_markdown(digest, window_days, generated_at)

    output_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_file = output_dir / f"{today}.md"
    output_file.write_text(markdown, encoding="utf-8")
    print(f"wrote digest ({digest['repo_count']} repos) -> {output_file}", file=sys.stderr)
    return output_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scans-dir", type=Path, default=DEFAULT_SCANS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    args = parser.parse_args(argv)
    run(args.scans_dir, args.output_dir, args.window_days, args.top_n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
