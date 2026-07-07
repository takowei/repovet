import base64

from repovet.ai_slop_collectors import collect_slop_signals
from repovet.cache import ResponseCache
from repovet.github_client import GitHubClient
from repovet.targets import Target
from tests.conftest import FakeResponse, FakeSession


def _contents_response(text: str) -> FakeResponse:
    return FakeResponse(
        200,
        {"encoding": "base64", "content": base64.b64encode(text.encode("utf-8")).decode("ascii")},
    )


def _dir_response(names: list[str]) -> FakeResponse:
    return FakeResponse(200, [{"name": n, "type": "dir"} for n in names])


def _client(tmp_path, responses):
    return GitHubClient(
        token="t", cache=ResponseCache(path=tmp_path / "c.sqlite3"), session=FakeSession(responses)
    )


def test_collects_readme_commits_and_root_listing(tmp_path):
    responses = [
        _contents_response("# Demo\n\nHello"),  # README.md found
        FakeResponse(200, [{"commit": {"message": "fix: bug\nmore"}}]),  # commits
        _dir_response(["LICENSE", ".github", "src"]),  # root listing
        _dir_response(["workflows"]),  # .github listing
    ]
    client = _client(tmp_path, responses)
    signals = collect_slop_signals(client, Target("gh", "acme", "demo"))

    assert signals.readme_text == "# Demo\n\nHello"
    assert signals.commit_messages == ["fix: bug"]
    assert signals.root_entries == ["LICENSE", ".github", "src"]
    assert signals.github_dir_entries == ["workflows"]


def test_missing_readme_and_no_github_dir(tmp_path):
    responses = [
        FakeResponse(404, {}),  # README.md
        FakeResponse(404, {}),  # README.rst
        FakeResponse(404, {}),  # README
        FakeResponse(404, {}),  # readme.md
        FakeResponse(200, []),  # commits (empty)
        _dir_response(["src", "LICENSE"]),  # root listing, no .github
    ]
    client = _client(tmp_path, responses)
    signals = collect_slop_signals(client, Target("gh", "acme", "demo"))

    assert signals.readme_text is None
    assert signals.commit_messages == []
    assert signals.github_dir_entries == []
