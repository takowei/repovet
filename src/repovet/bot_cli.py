"""Entry point invoked by the `.github/workflows/issue-comment-bot.yml`
Action step. Reads the triggering `issue_comment` event out of environment
variables the workflow sets from `github.event.*`, extracts a
`/repovet-check gh:owner/repo` command, runs the scan, and posts the reply
back to the same issue.

Never fails the workflow: missing context or a non-command comment are
both treated as a no-op (exit 0), not an error, so a normal conversation
comment on the issue doesn't turn the Action run red.
"""

import os
import sys

from repovet import output
from repovet.bot import build_reply_for_command, post_issue_comment
from repovet.cache import ResponseCache
from repovet.cli import _run_one
from repovet.github_client import GitHubClient
from repovet.graphql_client import GraphQLClient
from repovet.registry_client import RegistryClient
from repovet.reply import render_reply

ISSUE_SAMPLE_DEFAULT = 15
COMMIT_DAYS_DEFAULT = 365


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY")
    issue_number = os.environ.get("REPOVET_ISSUE_NUMBER")
    comment_body = os.environ.get("REPOVET_COMMENT_BODY", "")
    token = os.environ.get("GITHUB_TOKEN")

    if not repo or not issue_number or not token:
        print(
            "bot_cli: missing GITHUB_REPOSITORY/REPOVET_ISSUE_NUMBER/GITHUB_TOKEN, "
            "treating as no-op",
            file=sys.stderr,
        )
        return 0

    cache = ResponseCache()
    rest_client = GitHubClient(token=token, cache=cache)
    graphql_client = GraphQLClient(token=token, cache=cache)
    registry_client = RegistryClient(cache=cache)

    def run_scan(raw_target: str) -> str:
        record = _run_one(
            rest_client,
            graphql_client,
            registry_client,
            raw_target,
            ISSUE_SAMPLE_DEFAULT,
            COMMIT_DAYS_DEFAULT,
            "en",
        )
        if record["status"] != output.OK:
            return f"repovet: scan failed for `{raw_target}`: {record.get('error')}"
        return render_reply(record, lang="en", include_s4=False)

    reply = build_reply_for_command(comment_body, run_scan)
    if reply is None:
        print("bot_cli: no /repovet-check command found in comment; no-op")
        return 0

    reply += (
        "\n\n---\n*Posted automatically by "
        "[repovet](https://github.com/takowei/repovet) in response to a "
        "`/repovet-check` command in this issue. "
        "[What is this?](https://github.com/takowei/repovet#automation--bot)*"
    )
    post_issue_comment(rest_client, repo, int(issue_number), reply)
    print(f"bot_cli: posted reply to {repo}#{issue_number}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
