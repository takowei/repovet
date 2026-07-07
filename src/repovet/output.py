"""Rendering S2 results as a terminal table or machine-readable JSON.

This is the only module that formats human-facing text. CLI errors and
successes both flow through here so stdout stays parseable in --json mode
(warnings/errors go to a `warnings`/`error` field, not stray print calls).
"""

import json
from dataclasses import asdict
from typing import Any

from repovet.scoring import S2Result
from repovet.targets import Target

OK = "ok"
INPUT_ERROR = "input_error"
NETWORK_ERROR = "network_error"


def success_record(target: Target, result: S2Result) -> dict[str, Any]:
    return {
        "status": OK,
        "target": f"gh:{target.slug}",
        "formula_version": result.formula_version,
        "s2_overall": result.overall,
        "pattern": result.pattern,
        "sub_scores": [asdict(s) for s in result.sub_scores],
        "warnings": result.warnings,
    }


def error_record(raw_target: str, status: str, message: str) -> dict[str, Any]:
    return {"status": status, "target": raw_target, "error": message}


def render_json(records: list[dict[str, Any]], batch: bool) -> str:
    payload = records if batch else records[0]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _render_one_table(record: dict[str, Any]) -> str:
    lines = [f"repovet — {record['target']}"]

    if record["status"] != OK:
        lines.append(f"  ERROR ({record['status']}): {record['error']}")
        return "\n".join(lines)

    lines.append(
        f"Overall S2 (zombie-maintenance): {record['s2_overall']}/100 [{record['pattern']}]"
    )
    lines.append("")
    for sub in record["sub_scores"]:
        lines.append(f"  {sub['name']:<28} {sub['score']:>3}/100  {sub['evidence']}")
    lines.append("")
    lines.append(f"formula: {record['formula_version']}")
    if record["warnings"]:
        for w in record["warnings"]:
            lines.append(f"warning: {w}")
    return "\n".join(lines)


def render_table(records: list[dict[str, Any]]) -> str:
    return "\n\n".join(_render_one_table(r) for r in records)
