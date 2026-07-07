"""Gathers dependency-manifest + registry-existence data for S3.

Fetches known manifest file paths from the repo root via the GitHub
Contents API (reusing the same rate-limit-aware REST client as S2), parses
whichever ones exist, and checks each declared dependency against its
registry (PyPI or npm).
"""

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone

from repovet.dependency_manifest import (
    parse_package_json_dependencies,
    parse_pyproject_dependencies,
    parse_requirements_txt,
)
from repovet.errors import InputError
from repovet.github_client import GitHubClient
from repovet.registry_client import (
    PackageInfo,
    RegistryClient,
    check_npm_package,
    check_pypi_package,
)
from repovet.targets import Target

# (path, ecosystem, parser) — every candidate that exists in the repo root
# gets parsed and merged; a repo with both a pyproject.toml and a
# package.json (e.g. a monorepo) gets both ecosystems checked.
_MANIFEST_CANDIDATES = (
    ("pyproject.toml", "pypi", parse_pyproject_dependencies),
    ("requirements.txt", "pypi", parse_requirements_txt),
    ("requirements-dev.txt", "pypi", parse_requirements_txt),
    ("requirements-test.txt", "pypi", parse_requirements_txt),
    ("package.json", "npm", parse_package_json_dependencies),
)


@dataclass
class RawDependencySignals:
    owner: str
    repo: str
    fetched_at: datetime
    manifests_found: list[str] = field(default_factory=list)
    packages: list[PackageInfo] = field(default_factory=list)


def _fetch_file(rest_client: GitHubClient, target: Target, path: str) -> str | None:
    try:
        data = rest_client.get(
            f"/repos/{target.owner}/{target.repo}/contents/{path}", ttl_seconds=3600
        )
    except InputError:
        return None  # file not present in this repo -- try the next candidate, not fatal

    if not isinstance(data, dict) or data.get("encoding") != "base64":
        return None
    return base64.b64decode(data["content"]).decode("utf-8", errors="replace")


def collect_dependency_signals(
    rest_client: GitHubClient, registry_client: RegistryClient, target: Target
) -> RawDependencySignals:
    now = datetime.now(timezone.utc)
    manifests_found: list[str] = []
    names_by_ecosystem: dict[str, str] = {}

    for path, ecosystem, parser in _MANIFEST_CANDIDATES:
        content = _fetch_file(rest_client, target, path)
        if content is None:
            continue
        manifests_found.append(path)
        for name in parser(content):
            names_by_ecosystem.setdefault(name, ecosystem)

    packages = [
        check_pypi_package(registry_client, name, now)
        if ecosystem == "pypi"
        else check_npm_package(registry_client, name, now)
        for name, ecosystem in names_by_ecosystem.items()
    ]

    return RawDependencySignals(
        owner=target.owner,
        repo=target.repo,
        fetched_at=now,
        manifests_found=manifests_found,
        packages=packages,
    )
