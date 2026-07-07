"""repovet CLI entry point.

Exit codes: 0 = completed normally, 2 = input error, 3 = API/network failure.
In --batch mode, the worst status across all targets decides the exit code
(3 beats 2 beats 0), so a pipeline can tell "something needs a retry" (3)
apart from "fix your input" (2) without inspecting the JSON.
"""

import argparse
import os
import sys

from repovet import output
from repovet.cache import ResponseCache
from repovet.collectors import collect_signals
from repovet.errors import InputError, NetworkError
from repovet.github_client import GitHubClient
from repovet.graphql_client import GraphQLClient
from repovet.scoring import compute_s2
from repovet.star_collectors import collect_star_signals
from repovet.star_scoring import compute_s1
from repovet.targets import parse_target, read_batch_file

EXIT_OK = 0
EXIT_INPUT_ERROR = 2
EXIT_NETWORK_ERROR = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repovet", description="GitHub repo trust check before you depend on it."
    )
    parser.add_argument("target", nargs="?", help="e.g. gh:owner/repo")
    parser.add_argument("--batch", metavar="FILE", help="file with one target per line")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--issue-sample", type=int, default=15, help="issues to sample for S2")
    parser.add_argument("--commit-days", type=int, default=365, help="commit lookback window")
    return parser


def _run_s1(graphql_client: GraphQLClient | None, target) -> dict:
    if graphql_client is None:
        return output.signal_unavailable(
            output.SKIPPED, "no GITHUB_TOKEN: S1 needs GraphQL, which has no anonymous tier"
        )
    try:
        raw_star_signals = collect_star_signals(graphql_client, target)
        return output.signal_block(compute_s1(raw_star_signals))
    except InputError as e:
        return output.signal_unavailable(output.INPUT_ERROR, str(e))
    except NetworkError as e:
        return output.signal_unavailable(output.NETWORK_ERROR, str(e))


def _run_one(
    rest_client: GitHubClient,
    graphql_client: GraphQLClient | None,
    raw_target: str,
    issue_sample: int,
    commit_days: int,
) -> dict:
    try:
        target = parse_target(raw_target)
        raw_signals = collect_signals(
            rest_client, target, commit_days=commit_days, issue_sample_size=issue_sample
        )
        s2_result = compute_s2(raw_signals)
    except InputError as e:
        return output.error_record(raw_target, output.INPUT_ERROR, str(e))
    except NetworkError as e:
        return output.error_record(raw_target, output.NETWORK_ERROR, str(e))

    signals = {
        "s2": output.signal_block(s2_result),
        "s1": _run_s1(graphql_client, target),
    }
    return output.success_record(target, signals)


def _exit_code_for(records: list[dict]) -> int:
    statuses = {r["status"] for r in records}
    if output.NETWORK_ERROR in statuses:
        return EXIT_NETWORK_ERROR
    if output.INPUT_ERROR in statuses:
        return EXIT_INPUT_ERROR
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if bool(args.target) == bool(args.batch):
        parser.print_usage(sys.stderr)
        print("error: give exactly one of TARGET or --batch FILE", file=sys.stderr)
        return EXIT_INPUT_ERROR

    try:
        raw_targets = [args.target] if args.target else read_batch_file(args.batch)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print(
            "warning: no GITHUB_TOKEN set; S2 runs anonymous (60 req/hr), S1 is skipped entirely",
            file=sys.stderr,
        )

    cache = ResponseCache()
    rest_client = GitHubClient(token=token, cache=cache)
    graphql_client = GraphQLClient(token=token, cache=cache) if token else None
    records = [
        _run_one(rest_client, graphql_client, t, args.issue_sample, args.commit_days)
        for t in raw_targets
    ]

    is_batch = bool(args.batch)
    if args.json:
        print(output.render_json(records, batch=is_batch))
    else:
        print(output.render_table(records))

    return _exit_code_for(records)


if __name__ == "__main__":
    sys.exit(main())
