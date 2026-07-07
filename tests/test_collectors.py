from repovet.cache import ResponseCache
from repovet.collectors import collect_signals
from repovet.github_client import GitHubClient
from repovet.targets import Target
from tests.conftest import FakeResponse, FakeSession, iso


def _client(tmp_path, responses):
    return GitHubClient(
        token="t", cache=ResponseCache(path=tmp_path / "c.sqlite3"), session=FakeSession(responses)
    )


def test_comments_endpoint_only_called_when_comment_count_positive(tmp_path):
    responses = [
        FakeResponse(200, {"pushed_at": iso(1)}),  # repo meta
        FakeResponse(200, []),  # releases
        FakeResponse(200, []),  # commits page 1 (empty, stop)
        FakeResponse(
            200,
            [
                {"number": 1, "created_at": iso(10), "comments": 0},
                {"number": 2, "created_at": iso(20), "comments": 2},
            ],
        ),  # issue list
        FakeResponse(200, [{"created_at": iso(15)}]),  # first comment for issue #2 only
    ]
    client = _client(tmp_path, responses)
    signals = collect_signals(client, Target("gh", "acme", "lib"))

    assert len(signals.issue_sample) == 2
    no_comment_issue = next(s for s in signals.issue_sample if s.number == 1)
    commented_issue = next(s for s in signals.issue_sample if s.number == 2)
    assert no_comment_issue.responded_at is None
    assert commented_issue.responded_at is not None
    # exactly 5 calls: repo, releases, commits, issues, one comments lookup
    assert len(client.session.calls) == 5


def test_commit_author_prefers_login_over_raw_name(tmp_path):
    responses = [
        FakeResponse(200, {"pushed_at": iso(1)}),
        FakeResponse(200, []),
        FakeResponse(
            200,
            [
                {"author": {"login": "alice-gh"}, "commit": {"author": {"name": "Alice Smith"}}},
                {
                    "author": None,
                    "commit": {"author": {"name": "Bot Commit", "email": "bot@x.com"}},
                },
            ],
        ),
        FakeResponse(200, []),  # no issues
    ]
    client = _client(tmp_path, responses)
    signals = collect_signals(client, Target("gh", "acme", "lib"))

    assert signals.author_commit_counts["alice-gh"] == 1
    assert signals.author_commit_counts["Bot Commit"] == 1


def test_commit_pagination_stops_on_short_page(tmp_path):
    full_page = [{"author": {"login": "a"}, "commit": {"author": {"name": "a"}}}] * 100
    responses = [
        FakeResponse(200, {"pushed_at": iso(1)}),
        FakeResponse(200, []),
        FakeResponse(200, full_page),  # page 1: full, keep going
        FakeResponse(200, full_page[:5]),  # page 2: short, stop here
        FakeResponse(200, []),  # issues
    ]
    client = _client(tmp_path, responses)
    signals = collect_signals(client, Target("gh", "acme", "lib"))

    assert signals.commit_sample_count == 105
    # 5 calls total: repo, releases, commits page1, commits page2, issues (no page 3)
    assert len(client.session.calls) == 5
