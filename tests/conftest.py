from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from repovet.cache import ResponseCache
from repovet.github_client import GitHubClient


@pytest.fixture
def tmp_cache(tmp_path: Path) -> ResponseCache:
    return ResponseCache(path=tmp_path / "cache.sqlite3")


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None, text=""):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.headers = headers or {}
        self.text = text
        self.ok = 200 <= status_code < 400

    def json(self):
        return self._json_data


class FakeSession:
    """Records calls and replays canned responses keyed by URL substring match order."""

    def __init__(self, responses: list[FakeResponse]):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append((url, params))
        if not self._responses:
            raise AssertionError(f"FakeSession ran out of canned responses for {url}")
        return self._responses.pop(0)


def make_client(
    tmp_cache, responses: list[FakeResponse], token: str | None = "fake-token"
) -> GitHubClient:
    session = FakeSession(responses)
    return GitHubClient(token=token, cache=tmp_cache, session=session)


def iso(days_ago: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.isoformat().replace("+00:00", "Z")
