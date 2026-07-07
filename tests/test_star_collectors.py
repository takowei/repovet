import pytest

from repovet.cache import ResponseCache
from repovet.errors import InputError
from repovet.graphql_client import GraphQLClient
from repovet.star_collectors import FULL_SCAN_STAR_CAP, collect_star_signals
from repovet.targets import Target
from tests.conftest import FakeResponse, FakeSession, iso


def _gql_response(data, errors=None):
    body = {"data": data}
    if errors:
        body["errors"] = errors
    return FakeResponse(200, body)


def _stargazer_page(edges, has_next=False, end_cursor=None):
    return {
        "repository": {
            "stargazers": {
                "pageInfo": {"hasNextPage": has_next, "endCursor": end_cursor},
                "edges": edges,
            }
        }
    }


def _star_edge(login, starred_at_days_ago, created_days_before_star=0, followers=0, repos=0):
    created_at = iso(starred_at_days_ago + created_days_before_star)
    return {
        "starredAt": iso(starred_at_days_ago),
        "node": {
            "login": login,
            "createdAt": created_at,
            "followers": {"totalCount": followers},
            "repositories": {"totalCount": repos},
        },
    }


def _client(tmp_path, responses):
    return GraphQLClient(
        token="t", cache=ResponseCache(path=tmp_path / "c.sqlite3"), session=FakeSession(responses)
    )


def test_full_scan_for_small_repo(tmp_path):
    edges = [_star_edge(f"user{i}", i) for i in range(5)]
    responses = [
        _gql_response({"repository": {"stargazerCount": 5}}),
        _gql_response(_stargazer_page(edges, has_next=False)),
    ]
    client = _client(tmp_path, responses)
    signals = collect_star_signals(client, Target("gh", "acme", "lib"))

    assert signals.stargazer_count == 5
    assert len(signals.sample) == 5
    assert "full scan" in signals.sampling_note


def test_stratified_sample_for_large_repo(tmp_path):
    huge_count = FULL_SCAN_STAR_CAP + 1
    recent_edges = [_star_edge(f"recent{i}", i) for i in range(3)]
    earliest_edges = [_star_edge(f"earliest{i}", 1000 + i) for i in range(2)]
    responses = [
        _gql_response({"repository": {"stargazerCount": huge_count}}),
        _gql_response(_stargazer_page(recent_edges, has_next=False)),  # DESC page
        _gql_response(_stargazer_page(earliest_edges, has_next=False)),  # ASC page
    ]
    client = _client(tmp_path, responses)
    signals = collect_star_signals(client, Target("gh", "acme", "big-lib"))

    assert signals.stargazer_count == huge_count
    assert len(signals.sample) == 5
    assert "stratified sample" in signals.sampling_note
    assert "middle of the star history would be missed" in signals.sampling_note


def test_repo_not_found_raises_input_error(tmp_path):
    responses = [
        _gql_response({"repository": None}, errors=[{"type": "NOT_FOUND", "message": "nope"}])
    ]
    client = _client(tmp_path, responses)
    with pytest.raises(InputError):
        collect_star_signals(client, Target("gh", "acme", "ghost"))
