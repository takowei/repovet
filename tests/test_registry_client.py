from datetime import datetime, timezone

import pytest

from repovet.errors import NetworkError
from repovet.registry_client import (
    RegistryClient,
    check_npm_package,
    check_pypi_package,
)
from tests.conftest import FakeResponse, FakeSession

NOW = datetime.now(timezone.utc)


def _client(responses, tmp_path):
    from repovet.cache import ResponseCache

    return RegistryClient(
        cache=ResponseCache(path=tmp_path / "reg.sqlite3"), session=FakeSession(responses)
    )


def test_get_json_404_returns_none_not_error(tmp_path):
    client = _client([FakeResponse(404, {})], tmp_path)
    assert client.get_json("https://example.com/x") is None


def test_get_json_caches_result(tmp_path):
    client = _client([FakeResponse(200, {"a": 1})], tmp_path)
    assert client.get_json("https://example.com/x") == {"a": 1}
    assert client.get_json("https://example.com/x") == {"a": 1}
    assert len(client.session.calls) == 1


def test_get_json_caches_not_found_too(tmp_path):
    client = _client([FakeResponse(404, {})], tmp_path)
    assert client.get_json("https://example.com/x") is None
    assert client.get_json("https://example.com/x") is None
    assert len(client.session.calls) == 1


def test_429_raises_network_error(tmp_path):
    client = _client([FakeResponse(429, {}, {"Retry-After": "30"})], tmp_path)
    with pytest.raises(NetworkError):
        client.get_json("https://example.com/x")


def test_check_pypi_package_exists_computes_age(tmp_path):
    data = {
        "releases": {
            "1.0.0": [{"upload_time_iso_8601": "2020-01-01T00:00:00.000000Z"}],
            "2.0.0": [{"upload_time_iso_8601": "2021-06-01T00:00:00.000000Z"}],
        }
    }
    client = _client([FakeResponse(200, data)], tmp_path)
    info = check_pypi_package(client, "somepkg", NOW)
    assert info.exists is True
    assert info.age_days > 365 * 4  # earliest release (2020) is the oldest, several years old
    assert info.weekly_downloads is None  # pypi never has a download signal


def test_check_pypi_package_missing(tmp_path):
    client = _client([FakeResponse(404, {})], tmp_path)
    info = check_pypi_package(client, "doesnotexist", NOW)
    assert info.exists is False
    assert info.age_days is None


def test_check_npm_package_exists_with_age_and_downloads(tmp_path):
    responses = [
        FakeResponse(200, {"time": {"created": "2015-01-01T00:00:00.000Z"}}),
        FakeResponse(200, {"downloads": 5000}),
    ]
    client = _client(responses, tmp_path)
    info = check_npm_package(client, "somepkg", NOW)
    assert info.exists is True
    assert info.age_days > 365 * 8
    assert info.weekly_downloads == 5000


def test_check_npm_package_missing(tmp_path):
    client = _client([FakeResponse(404, {})], tmp_path)
    info = check_npm_package(client, "doesnotexist", NOW)
    assert info.exists is False


def test_check_npm_package_downloads_failure_does_not_fail_existence(tmp_path):
    responses = [
        FakeResponse(200, {"time": {"created": "2015-01-01T00:00:00.000Z"}}),
        FakeResponse(500, {}, text="boom"),
    ]
    client = _client(responses, tmp_path)
    info = check_npm_package(client, "somepkg", NOW)
    assert info.exists is True
    assert info.weekly_downloads is None
