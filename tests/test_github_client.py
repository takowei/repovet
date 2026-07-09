import pytest

from repovet.errors import InputError, NetworkError
from repovet.github_client import GitHubClient
from tests.conftest import FakeResponse, FakeSession


def test_get_returns_json_and_caches(tmp_cache):
    session = FakeSession([FakeResponse(200, {"hello": "world"}, {"X-RateLimit-Remaining": "59"})])
    client = GitHubClient(token="t", cache=tmp_cache, session=session)

    result = client.get("/repos/acme/lib")
    assert result == {"hello": "world"}
    assert len(session.calls) == 1

    # second call should be served from cache, no new HTTP call
    result2 = client.get("/repos/acme/lib")
    assert result2 == {"hello": "world"}
    assert len(session.calls) == 1


def test_get_404_raises_input_error(tmp_cache):
    session = FakeSession([FakeResponse(404, {}, {})])
    client = GitHubClient(token="t", cache=tmp_cache, session=session)
    with pytest.raises(InputError):
        client.get("/repos/acme/does-not-exist")


def test_primary_rate_limit_raises_network_error(tmp_cache):
    session = FakeSession(
        [FakeResponse(403, {}, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "9999999999"})]
    )
    client = GitHubClient(token="t", cache=tmp_cache, session=session)
    with pytest.raises(NetworkError):
        client.get("/repos/acme/lib")


def test_low_remaining_budget_aborts_before_request(tmp_cache):
    session = FakeSession([FakeResponse(200, {}, {"X-RateLimit-Remaining": "2"})])
    client = GitHubClient(token="t", cache=tmp_cache, session=session)
    # first call succeeds and records remaining=2 (at/under buffer of 3)
    client.get("/repos/acme/a")
    # second call should abort locally, no HTTP call made
    with pytest.raises(NetworkError):
        client.get("/repos/acme/b")
    assert len(session.calls) == 1


def test_anonymous_client_has_no_auth_header(tmp_cache):
    client = GitHubClient(token=None, cache=tmp_cache, session=FakeSession([]))
    assert client.anonymous is True
    assert "Authorization" not in client._headers()


def test_network_exception_raises_network_error(tmp_cache):
    class ExplodingSession:
        def get(self, *a, **k):
            import requests

            raise requests.exceptions.ConnectionError("boom")

    client = GitHubClient(token="t", cache=tmp_cache, session=ExplodingSession())
    with pytest.raises(NetworkError):
        client.get("/repos/acme/lib")


def test_post_returns_json_and_is_never_cached(tmp_cache):
    session = FakeSession(
        [
            FakeResponse(201, {"id": 1}, {"X-RateLimit-Remaining": "59"}),
            FakeResponse(201, {"id": 2}, {"X-RateLimit-Remaining": "58"}),
        ]
    )
    client = GitHubClient(token="t", cache=tmp_cache, session=session)

    result1 = client.post("/repos/acme/lib/issues/1/comments", {"body": "hi"})
    result2 = client.post("/repos/acme/lib/issues/1/comments", {"body": "hi"})

    assert result1 == {"id": 1}
    assert result2 == {"id": 2}
    assert len(session.calls) == 2  # no caching on POST, unlike get()


def test_post_404_raises_input_error(tmp_cache):
    session = FakeSession([FakeResponse(404, {}, {})])
    client = GitHubClient(token="t", cache=tmp_cache, session=session)
    with pytest.raises(InputError):
        client.post("/repos/acme/does-not-exist/issues/1/comments", {"body": "hi"})


def test_post_rate_limit_raises_network_error(tmp_cache):
    session = FakeSession(
        [FakeResponse(403, {}, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "9999999999"})]
    )
    client = GitHubClient(token="t", cache=tmp_cache, session=session)
    with pytest.raises(NetworkError):
        client.post("/repos/acme/lib/issues/1/comments", {"body": "hi"})
