"""Dependency manifest parsers for S3.

MVP supports exactly two ecosystems: Python (pyproject.toml PEP 621
`dependencies`/`optional-dependencies` + requirements*.txt) and JS
(package.json `dependencies`/`devDependencies`). Any other ecosystem (Go,
Rust, Ruby, ...) is explicitly unsupported — dependency_collectors.py
reports "no supported manifest found" rather than guessing at one.

Known limitation: requirements.txt `-r other.txt` includes are not
followed recursively — only the manifest files repovet looks for directly
(see _MANIFEST_CANDIDATES in dependency_collectors.py) are read.
"""

import json
import re
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

# A PEP 508 requirement starts with a distribution name: letters/digits,
# then any run of letters/digits/./-/_. Everything after that (version
# specifiers, environment markers, extras) is ignored — we only need the
# name to look it up in a registry.
_REQUIREMENT_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def parse_requirements_txt(content: str) -> list[str]:
    names = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue  # comments and -r/-e/--hash/... directives are skipped, not followed
        match = _REQUIREMENT_NAME_RE.match(line)
        if match:
            names.append(match.group(1))
    return names


def parse_pyproject_dependencies(content: str) -> list[str]:
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return []

    project = data.get("project", {})
    names = []
    for spec in project.get("dependencies", []):
        match = _REQUIREMENT_NAME_RE.match(spec.strip())
        if match:
            names.append(match.group(1))
    for group_deps in project.get("optional-dependencies", {}).values():
        for spec in group_deps:
            match = _REQUIREMENT_NAME_RE.match(spec.strip())
            if match:
                names.append(match.group(1))
    return names


def parse_package_json_dependencies(content: str) -> list[str]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []

    names = []
    for key in ("dependencies", "devDependencies"):
        names.extend((data.get(key) or {}).keys())
    return names
