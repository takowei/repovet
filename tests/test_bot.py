import pytest

from repovet.bot import build_reply_for_command, extract_command, post_issue_comment
from repovet.errors import NetworkError
from tests.conftest import FakeResponse, FakeSession, make_client


def test_extract_command_finds_target():
    assert extract_command("please /repovet-check gh:owner/repo now") == "gh:owner/repo"


def test_extract_command_no_command_returns_none():
    assert extract_command("just a normal comment, no command here") is None


def test_extract_command_empty_body_returns_none():
    assert extract_command("") is None
    assert extract_command(None) is None


def test_build_reply_runs_scan_for_valid_command():
    calls = []

    def run_scan(raw_target: str) -> str:
        calls.append(raw_target)
        return "scan result text"

    reply = build_reply_for_command("/repovet-check gh:owner/repo", run_scan)
    assert reply == "scan result text"
    assert calls == ["gh:owner/repo"]


def test_build_reply_returns_none_when_no_command():
    def run_scan(raw_target: str) -> str:
        raise AssertionError("run_scan should not be called when there's no command")

    assert build_reply_for_command("hey, any updates?", run_scan) is None


def test_build_reply_reports_malformed_target_without_calling_scan():
    def run_scan(raw_target: str) -> str:
        raise AssertionError("run_scan should not be called for a malformed target")

    # matches the command regex's coarse shape but fails targets.py's
    # stricter owner validation (leading '-' isn't a valid GitHub owner)
    reply = build_reply_for_command("/repovet-check gh:-bad-owner/repo", run_scan)
    assert reply is not None
    assert "couldn't parse" in reply


def test_build_reply_surfaces_network_error_as_text_not_exception():
    def run_scan(raw_target: str) -> str:
        raise NetworkError("rate limit exceeded")

    reply = build_reply_for_command("/repovet-check gh:owner/repo", run_scan)
    assert reply is not None
    assert "scan failed" in reply
    assert "rate limit exceeded" in reply


def test_post_issue_comment_posts_to_the_triggering_repo_only(tmp_cache):
    session = FakeSession([FakeResponse(201, {"id": 1}, {"X-RateLimit-Remaining": "50"})])
    client = make_client(tmp_cache, [], token="fake-token")
    client.session = session

    result = post_issue_comment(client, "takowei/repovet", 42, "hello from the bot")

    assert result == {"id": 1}
    assert len(session.calls) == 1
    url, body = session.calls[0]
    assert url == "https://api.github.com/repos/takowei/repovet/issues/42/comments"
    assert body == {"body": "hello from the bot"}


@pytest.mark.parametrize(
    "comment",
    [
        "/repovet-check gh:some-other-org/some-other-repo",
        "hey can you check gh:some-other-org/some-other-repo for me?",
    ],
)
def test_reply_never_targets_a_repo_other_than_the_one_passed_in(tmp_cache, comment):
    """The scanned repo (the subject of the check) must never become the
    posting destination -- posting destination is always an explicit,
    separate argument supplied by the caller (the triggering issue's repo)."""
    session = FakeSession([FakeResponse(201, {"id": 2}, {})])
    client = make_client(tmp_cache, [], token="fake-token")
    client.session = session

    post_issue_comment(client, "takowei/repovet", 7, comment)

    url, _ = session.calls[0]
    assert "takowei/repovet" in url
    assert "some-other-org/some-other-repo" not in url
