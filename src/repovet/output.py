"""Rendering S1/S2 results as a terminal report or machine-readable JSON.

This is the only module that formats human-facing text. CLI errors and
successes both flow through here so stdout stays parseable in --json mode
(warnings/errors go to a `warnings`/`error` field, not stray print calls).

Each signal (s1, s2, ...) gets its own status inside `signals`, independent
of the top-level record status: S1 needs a GITHUB_TOKEN (GraphQL has no
anonymous tier) and can be legitimately `skipped` while S2 still succeeds.
The top-level record status/exit code is governed by S2 alone (see cli.py) —
a partial S1 failure doesn't fail the whole target, it just shows up inside
`signals.s1.status` for whoever's reading the JSON to notice.
"""

import json
from dataclasses import asdict
from typing import Any

from repovet.targets import Target

OK = "ok"
SKIPPED = "skipped"
INPUT_ERROR = "input_error"
NETWORK_ERROR = "network_error"

_SIGNAL_TITLES = {
    "s2": "S2 zombie-maintenance",
    "s1": "S1 anomalous star pattern",
    "s3": "S3 hallucinated dependency",
    "s4": "S4 AI-slop hints (v0, experimental, hints only -- not a verdict)",
}

# Result dataclasses can carry one signal-specific extra field beyond the
# common shape (S1Result.sampling_note, S3Result.manifests_found) -- surface
# it under its own name in the JSON/table if present, rather than dropping it.
_EXTRA_FIELDS = ("sampling_note", "manifests_found")


def signal_block(result) -> dict[str, Any]:
    """Serialize a *Result (S1Result/S2Result/S3Result) into the JSON signal shape."""
    block = {
        "status": OK,
        "formula_version": result.formula_version,
        "overall": result.overall,
        "pattern": result.pattern,
        "sub_scores": [asdict(s) for s in result.sub_scores],
        "warnings": result.warnings,
    }
    for field_name in _EXTRA_FIELDS:
        value = getattr(result, field_name, None)
        if value:
            block[field_name] = value
    return block


def s4_signal_block(result) -> dict[str, Any]:
    """S4Result has no overall/pattern (v0 is hints-only, see ai_slop_hints.py) --
    a distinct shape from signal_block(), not shoehorned into the same one."""
    return {
        "status": OK,
        "formula_version": result.formula_version,
        "hints": [asdict(h) for h in result.hints],
        "warnings": result.warnings,
    }


def signal_unavailable(status: str, message: str) -> dict[str, Any]:
    """A signal that couldn't run: status is SKIPPED (opt-in degrade, e.g. no
    token) or INPUT_ERROR/NETWORK_ERROR (this signal specifically failed)."""
    return {"status": status, "message": message}


def success_record(target: Target, signals: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"status": OK, "target": f"gh:{target.slug}", "signals": signals}


def error_record(raw_target: str, status: str, message: str) -> dict[str, Any]:
    return {"status": status, "target": raw_target, "error": message}


def render_json(records: list[dict[str, Any]], batch: bool) -> str:
    payload = records if batch else records[0]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _render_hints(title: str, block: dict[str, Any]) -> list[str]:
    lines = [f"{title}:"]
    for hint in block["hints"]:
        lines.append(f"  {hint['name']}: {hint['observation']}")
        lines.append(f"    disclaimer: {hint['disclaimer']}")
    lines.append(f"  formula: {block['formula_version']}")
    for w in block["warnings"]:
        lines.append(f"  warning: {w}")
    return lines


def _render_signal(key: str, block: dict[str, Any]) -> list[str]:
    title = _SIGNAL_TITLES.get(key, key)
    if block["status"] == SKIPPED:
        return [f"{title}: skipped ({block['message']})"]
    if block["status"] != OK:
        return [f"{title}: ERROR ({block['status']}): {block['message']}"]

    if "hints" in block:
        return _render_hints(title, block)

    lines = [f"{title}: {block['overall']}/100 [{block['pattern']}]"]
    for sub in block["sub_scores"]:
        lines.append(f"  {sub['name']:<28} {sub['score']:>3}/100  {sub['evidence']}")
    if block.get("sampling_note"):
        lines.append(f"  sampling: {block['sampling_note']}")
    if block.get("manifests_found"):
        lines.append(f"  manifests: {', '.join(block['manifests_found'])}")
    lines.append(f"  formula: {block['formula_version']}")
    for w in block["warnings"]:
        lines.append(f"  warning: {w}")
    return lines


def _render_one_table(record: dict[str, Any]) -> str:
    lines = [f"repovet — {record['target']}"]

    if record["status"] != OK:
        lines.append(f"  ERROR ({record['status']}): {record['error']}")
        return "\n".join(lines)

    lines.append("")
    for key, block in record["signals"].items():
        lines.extend(_render_signal(key, block))
        lines.append("")
    return "\n".join(lines).rstrip()


def render_table(records: list[dict[str, Any]]) -> str:
    return "\n\n".join(_render_one_table(r) for r in records)
