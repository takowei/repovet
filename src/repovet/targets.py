"""Parsing of repovet targets, e.g. `gh:owner/repo`.

M0 only supports GitHub repos. `npm:` / `pypi:` targets are future work (see spec S3).
"""

import re
from dataclasses import dataclass

from repovet.errors import InputError

_GH_PREFIX = "gh:"
_OWNER_RE = r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
_REPO_RE = r"[A-Za-z0-9_.-]+"
_OWNER_REPO_RE = re.compile(rf"^{_OWNER_RE}/{_REPO_RE}$")


@dataclass(frozen=True)
class Target:
    kind: str
    owner: str
    repo: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_target(raw: str) -> Target:
    """Parse a single target string. Raises InputError on anything malformed."""
    raw = raw.strip()
    if not raw:
        raise InputError("empty target")

    if not raw.startswith(_GH_PREFIX):
        raise InputError(f"unsupported target '{raw}': M0 only supports 'gh:owner/repo' targets")

    rest = raw[len(_GH_PREFIX) :]
    if not _OWNER_REPO_RE.match(rest):
        raise InputError(f"invalid target '{raw}': expected 'gh:owner/repo'")

    owner, repo = rest.split("/", 1)
    return Target(kind="gh", owner=owner, repo=repo)


def read_batch_file(path: str) -> list[str]:
    """Read one target per line. Blank lines and '#' comments are skipped."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        raise InputError(f"can't read batch file '{path}': {e}") from e

    targets = [line.strip() for line in lines]
    targets = [t for t in targets if t and not t.startswith("#")]
    if not targets:
        raise InputError(f"batch file '{path}' has no targets")
    return targets
