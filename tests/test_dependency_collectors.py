import base64
import json

from repovet.cache import ResponseCache
from repovet.dependency_collectors import collect_dependency_signals
from repovet.github_client import GitHubClient
from repovet.registry_client import RegistryClient
from repovet.targets import Target
from tests.conftest import FakeResponse, FakeSession


def _contents_response(content_str: str) -> FakeResponse:
    return FakeResponse(
        200,
        {
            "encoding": "base64",
            "content": base64.b64encode(content_str.encode("utf-8")).decode("ascii"),
        },
    )


def _rest_client(tmp_path, responses):
    return GitHubClient(
        token="t",
        cache=ResponseCache(path=tmp_path / "rest.sqlite3"),
        session=FakeSession(responses),
    )


def _registry_client(tmp_path, responses):
    return RegistryClient(
        cache=ResponseCache(path=tmp_path / "reg.sqlite3"), session=FakeSession(responses)
    )


def test_no_supported_manifest_found(tmp_path):
    # 5 candidate paths, all 404 (e.g. a Rust/Cargo-only repo)
    rest_client = _rest_client(tmp_path, [FakeResponse(404, {}) for _ in range(5)])
    registry_client = _registry_client(tmp_path, [])

    signals = collect_dependency_signals(
        rest_client, registry_client, Target("gh", "acme", "rustlib")
    )
    assert signals.manifests_found == []
    assert signals.packages == []


def test_pyproject_toml_deps_are_parsed_and_checked(tmp_path):
    pyproject = """
[project]
name = "demo"
dependencies = ["requests>=2.31"]
"""
    rest_responses = [
        _contents_response(pyproject),  # pyproject.toml found
        FakeResponse(404, {}),  # requirements.txt
        FakeResponse(404, {}),  # requirements-dev.txt
        FakeResponse(404, {}),  # requirements-test.txt
        FakeResponse(404, {}),  # package.json
    ]
    rest_client = _rest_client(tmp_path, rest_responses)

    pypi_data = {"releases": {"1.0": [{"upload_time_iso_8601": "2020-01-01T00:00:00Z"}]}}
    registry_client = _registry_client(tmp_path, [FakeResponse(200, pypi_data)])

    signals = collect_dependency_signals(
        rest_client, registry_client, Target("gh", "acme", "pylib")
    )
    assert signals.manifests_found == ["pyproject.toml"]
    assert len(signals.packages) == 1
    assert signals.packages[0].name == "requests"
    assert signals.packages[0].exists is True


def test_package_json_deps_are_parsed_and_checked(tmp_path):
    package_json = json.dumps({"dependencies": {"lodash": "^4.0.0"}})
    rest_responses = [
        FakeResponse(404, {}),  # pyproject.toml
        FakeResponse(404, {}),  # requirements.txt
        FakeResponse(404, {}),  # requirements-dev.txt
        FakeResponse(404, {}),  # requirements-test.txt
        _contents_response(package_json),  # package.json found
    ]
    rest_client = _rest_client(tmp_path, rest_responses)

    npm_data = {"time": {"created": "2015-01-01T00:00:00Z"}}
    registry_client = _registry_client(
        tmp_path, [FakeResponse(200, npm_data), FakeResponse(200, {"downloads": 10})]
    )

    signals = collect_dependency_signals(
        rest_client, registry_client, Target("gh", "acme", "jslib")
    )
    assert signals.manifests_found == ["package.json"]
    assert signals.packages[0].name == "lodash"
    assert signals.packages[0].ecosystem == "npm"
