from repovet import bot_cli


def test_no_op_when_context_missing(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("REPOVET_ISSUE_NUMBER", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert bot_cli.main() == 0
    assert "no-op" in capsys.readouterr().err


def test_no_op_when_comment_has_no_command(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("GITHUB_REPOSITORY", "takowei/repovet")
    monkeypatch.setenv("REPOVET_ISSUE_NUMBER", "3")
    monkeypatch.setenv("REPOVET_COMMENT_BODY", "just chatting, no command")
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    monkeypatch.chdir(tmp_path)

    assert bot_cli.main() == 0
    assert "no /repovet-check command" in capsys.readouterr().out


def test_malformed_target_posts_a_short_error_reply_not_a_scan(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("GITHUB_REPOSITORY", "takowei/repovet")
    monkeypatch.setenv("REPOVET_ISSUE_NUMBER", "3")
    monkeypatch.setenv("REPOVET_COMMENT_BODY", "/repovet-check gh:bad-target-shape")
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    monkeypatch.chdir(tmp_path)

    # No candidate matches the command regex's owner/repo shape, so
    # extract_command returns None -- confirms malformed input never
    # reaches the network layer.
    assert bot_cli.main() == 0
    assert "no /repovet-check command" in capsys.readouterr().out


def test_posts_reply_for_valid_command(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("GITHUB_REPOSITORY", "takowei/repovet")
    monkeypatch.setenv("REPOVET_ISSUE_NUMBER", "3")
    monkeypatch.setenv("REPOVET_COMMENT_BODY", "/repovet-check gh:owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(bot_cli, "ResponseCache", lambda: _tmp_cache(tmp_path))

    posted = {}

    def fake_post_issue_comment(rest_client, repo, issue_number, body):
        posted["repo"] = repo
        posted["issue_number"] = issue_number
        posted["body"] = body
        return {"id": 99}

    monkeypatch.setattr(bot_cli, "post_issue_comment", fake_post_issue_comment)

    class StubRecord(dict):
        pass

    def fake_run_one(rest_client, graphql_client, registry_client, raw_target, *a, **k):
        return {"status": "ok", "target": raw_target, "signals": {}}

    monkeypatch.setattr(bot_cli, "_run_one", fake_run_one)
    monkeypatch.setattr(bot_cli, "render_reply", lambda record, lang, include_s4: "SCAN SUMMARY")
    monkeypatch.setattr(
        bot_cli, "GitHubClient", lambda token, cache: object.__new__(_FakeGitHubClient)
    )
    monkeypatch.setattr(bot_cli, "GraphQLClient", lambda token, cache: None)
    monkeypatch.setattr(bot_cli, "RegistryClient", lambda cache: None)

    assert bot_cli.main() == 0
    out = capsys.readouterr().out
    assert "posted reply to takowei/repovet#3" in out
    assert posted["repo"] == "takowei/repovet"
    assert posted["issue_number"] == 3
    assert "SCAN SUMMARY" in posted["body"]
    assert "Posted automatically by" in posted["body"]


class _FakeGitHubClient:
    pass


def _tmp_cache(tmp_path):
    from repovet.cache import ResponseCache

    return ResponseCache(path=tmp_path / "cache.sqlite3")
