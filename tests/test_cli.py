import json

import pytest

from repovet import cli
from tests.conftest import FakeResponse, FakeSession, iso


def _healthy_repo_responses(n_issues=3):
    responses = [
        FakeResponse(200, {"pushed_at": iso(1)}, {"X-RateLimit-Remaining": "100"}),  # repo meta
        FakeResponse(200, [{"published_at": iso(5)}], {"X-RateLimit-Remaining": "99"}),  # releases
        FakeResponse(200, [], {"X-RateLimit-Remaining": "98"}),  # commits page 1 (empty -> stop)
    ]
    issues = [{"number": i, "created_at": iso(10), "comments": 0} for i in range(n_issues)]
    responses.append(FakeResponse(200, issues, {"X-RateLimit-Remaining": "97"}))  # issue list
    return responses


@pytest.fixture
def patched_client(monkeypatch, tmp_path):
    """Route GitHubClient construction in cli.main to a FakeSession-backed instance."""
    captured = {}

    def fake_get_client(token, responses):
        from repovet.cache import ResponseCache
        from repovet.github_client import GitHubClient

        cache = ResponseCache(path=tmp_path / "cache.sqlite3")
        session = FakeSession(responses)
        client = GitHubClient(token=token, cache=cache, session=session)
        captured["client"] = client
        return client

    return fake_get_client, captured


def test_missing_token_warns_but_still_runs(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def fake_client_ctor(token, cache):
        from repovet.cache import ResponseCache
        from repovet.github_client import GitHubClient

        return GitHubClient(
            token=token,
            cache=ResponseCache(path=tmp_path / "c.sqlite3"),
            session=FakeSession(_healthy_repo_responses()),
        )

    monkeypatch.setattr(cli, "GitHubClient", fake_client_ctor)
    monkeypatch.setattr(cli, "ResponseCache", lambda: None)

    exit_code = cli.main(["gh:acme/lib", "--json"])
    captured = capsys.readouterr()

    assert "no GITHUB_TOKEN" in captured.err
    assert exit_code == cli.EXIT_OK
    payload = json.loads(captured.out)
    assert payload["status"] == "ok"


def test_invalid_target_exits_2(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("GITHUB_TOKEN", "x")

    def fake_client_ctor(token, cache):
        from repovet.cache import ResponseCache
        from repovet.github_client import GitHubClient

        return GitHubClient(
            token=token, cache=ResponseCache(path=tmp_path / "c.sqlite3"), session=FakeSession([])
        )

    monkeypatch.setattr(cli, "GitHubClient", fake_client_ctor)
    monkeypatch.setattr(cli, "ResponseCache", lambda: None)

    exit_code = cli.main(["npm:left-pad", "--json"])
    assert exit_code == cli.EXIT_INPUT_ERROR
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "input_error"


def test_rate_limit_exits_3(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("GITHUB_TOKEN", "x")

    def fake_client_ctor(token, cache):
        from repovet.cache import ResponseCache
        from repovet.github_client import GitHubClient

        responses = [
            FakeResponse(403, {}, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "9999999999"})
        ]
        return GitHubClient(
            token=token,
            cache=ResponseCache(path=tmp_path / "c.sqlite3"),
            session=FakeSession(responses),
        )

    monkeypatch.setattr(cli, "GitHubClient", fake_client_ctor)
    monkeypatch.setattr(cli, "ResponseCache", lambda: None)

    exit_code = cli.main(["gh:acme/lib", "--json"])
    assert exit_code == cli.EXIT_NETWORK_ERROR
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "network_error"


def test_batch_mode_aggregates_worst_exit_code(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    batch_file = tmp_path / "batch.txt"
    batch_file.write_text("gh:acme/good\nnpm:bad-target\n")

    responses = _healthy_repo_responses()

    def fake_client_ctor(token, cache):
        from repovet.cache import ResponseCache
        from repovet.github_client import GitHubClient

        return GitHubClient(
            token=token,
            cache=ResponseCache(path=tmp_path / "c.sqlite3"),
            session=FakeSession(responses),
        )

    monkeypatch.setattr(cli, "GitHubClient", fake_client_ctor)
    monkeypatch.setattr(cli, "ResponseCache", lambda: None)

    exit_code = cli.main(["--batch", str(batch_file), "--json"])
    assert exit_code == cli.EXIT_INPUT_ERROR  # one bad target, no network errors
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 2
    assert payload[0]["status"] == "ok"
    assert payload[1]["status"] == "input_error"


def test_both_target_and_batch_is_input_error(capsys, tmp_path):
    batch_file = tmp_path / "b.txt"
    batch_file.write_text("gh:a/b\n")
    exit_code = cli.main(["gh:x/y", "--batch", str(batch_file)])
    assert exit_code == cli.EXIT_INPUT_ERROR


def test_neither_target_nor_batch_is_input_error():
    assert cli.main([]) == cli.EXIT_INPUT_ERROR
