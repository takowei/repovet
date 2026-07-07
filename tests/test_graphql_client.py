import pytest

from repovet.errors import InputError, NetworkError
from repovet.graphql_client import GraphQLClient
from tests.conftest import FakeResponse, FakeSession


def _body(data=None, errors=None):
    out = {"data": data if data is not None else {}}
    if errors:
        out["errors"] = errors
    return out


def test_missing_token_raises_input_error(tmp_cache):
    client = GraphQLClient(token=None, cache=tmp_cache, session=FakeSession([]))
    with pytest.raises(InputError):
        client.query("query{ viewer { login } }", {})


def test_query_returns_data_and_caches(tmp_cache):
    session = FakeSession(
        [FakeResponse(200, _body({"hello": "world"}), {"X-RateLimit-Remaining": "4999"})]
    )
    client = GraphQLClient(token="t", cache=tmp_cache, session=session)

    result = client.query("query{ x }", {"a": 1})
    assert result == {"hello": "world"}
    assert len(session.calls) == 1

    result2 = client.query("query{ x }", {"a": 1})
    assert result2 == {"hello": "world"}
    assert len(session.calls) == 1  # served from cache


def test_not_found_error_raises_input_error(tmp_cache):
    session = FakeSession(
        [FakeResponse(200, _body({"repository": None}, errors=[{"type": "NOT_FOUND"}]))]
    )
    client = GraphQLClient(token="t", cache=tmp_cache, session=session)
    with pytest.raises(InputError):
        client.query("query{ repository { id } }", {})


def test_other_graphql_error_raises_network_error(tmp_cache):
    session = FakeSession(
        [FakeResponse(200, _body({}, errors=[{"type": "SOMETHING_ELSE", "message": "boom"}]))]
    )
    client = GraphQLClient(token="t", cache=tmp_cache, session=session)
    with pytest.raises(NetworkError):
        client.query("query{ x }", {})


def test_primary_rate_limit_raises_network_error(tmp_cache):
    session = FakeSession(
        [FakeResponse(403, {}, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "9999999999"})]
    )
    client = GraphQLClient(token="t", cache=tmp_cache, session=session)
    with pytest.raises(NetworkError):
        client.query("query{ x }", {})


def test_low_budget_aborts_before_request(tmp_cache):
    session = FakeSession([FakeResponse(200, _body({"x": 1}), {"X-RateLimit-Remaining": "2"})])
    client = GraphQLClient(token="t", cache=tmp_cache, session=session)
    client.query("query{ x }", {"v": 1})
    with pytest.raises(NetworkError):
        client.query("query{ x }", {"v": 2})
    assert len(session.calls) == 1
