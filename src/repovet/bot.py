"""GitHub bot glue: parse an issue-comment command, run a scan, and post the
reply back.

Safety/opt-in design (see README "Automation / bot" section for the full
writeup):

- This module only ever posts a comment back to the SAME issue that
  triggered it, in the repo the triggering workflow is running in. It has
  no code path that reaches out to a repo other than the one the command
  was written in. Scanning `gh:owner/repo` (the *subject* of the check)
  never causes a comment to be posted *to* owner/repo -- the reply always
  goes back to the issue where `/repovet-check` was typed.
- The only supported trigger is an explicit `/repovet-check gh:owner/repo`
  command typed by a human in an issue comment. There is no scheduled or
  push-triggered path in this module that posts anywhere without a human
  asking for it in that issue, first.
- A repo-wide watchlist (scan N repos on a schedule) is a separate,
  explicitly opt-in mechanism: see docs/reusable-watchlist-workflow.md --
  it only runs if a repo's own maintainer copies the reusable workflow
  into their own repo and lists their own targets, and results are posted
  as an issue in THEIR OWN repo, never a third party's.
"""

import re

from repovet.errors import InputError, NetworkError
from repovet.github_client import GitHubClient
from repovet.targets import parse_target

COMMAND_RE = re.compile(r"/repovet-check\s+(gh:[\w.-]+/[\w.-]+)")


def extract_command(comment_body: str) -> str | None:
    """Return the raw target string (e.g. 'gh:owner/repo') if `comment_body`
    contains a `/repovet-check` command, else None (not a command -- no-op,
    not an error)."""
    match = COMMAND_RE.search(comment_body or "")
    return match.group(1) if match else None


def build_reply_for_command(comment_body: str, run_scan) -> str | None:
    """Parse a `/repovet-check` command out of `comment_body` and, if found,
    run it via `run_scan(raw_target: str) -> str` and return the reply text.

    Returns None if the comment contains no command at all (the caller
    should treat that as a silent no-op, not an error -- most comments on
    an issue won't be bot commands).
    """
    raw_target = extract_command(comment_body)
    if raw_target is None:
        return None

    try:
        parse_target(raw_target)  # fail fast on a malformed target, no API call spent
    except InputError as e:
        return f"repovet: couldn't parse `{raw_target}`: {e}"

    try:
        return run_scan(raw_target)
    except NetworkError as e:
        return f"repovet: scan failed for `{raw_target}`: {e}"


def post_issue_comment(rest_client: GitHubClient, repo: str, issue_number: int, body: str) -> dict:
    """POST `body` as a comment on issue `issue_number` in `repo` (owner/repo).

    Callers must only pass the repo the triggering event came from -- see
    module docstring for why that invariant is what keeps this from being
    a spam bot.
    """
    return rest_client.post(f"/repos/{repo}/issues/{issue_number}/comments", {"body": body})
