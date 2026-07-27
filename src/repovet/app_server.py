"""Entry point for the repovet GitHub App: a small stdlib-only webhook
server (no Flask/FastAPI dependency -- see CLAUDE.md for why).

Run with:
    REPOVET_APP_ID=... REPOVET_APP_PRIVATE_KEY="$(cat app-key.pem)" \\
    REPOVET_WEBHOOK_SECRET=... python3 -m repovet.app_server

All secrets come from the environment only -- never read from a file path
literal in this module, never logged, never persisted. See README
"GitHub App / Marketplace" for the full deployment write-up and the list of
manual GitHub-side steps (creating the App, setting the webhook URL, etc.)
that are out of scope for this module.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from repovet import output
from repovet.app_auth import create_app_jwt, get_installation_token
from repovet.app_webhook import handle_event
from repovet.bot_cli import COMMIT_DAYS_DEFAULT, ISSUE_SAMPLE_DEFAULT
from repovet.cache import ResponseCache
from repovet.cli import _run_one
from repovet.github_client import GitHubClient
from repovet.graphql_client import GraphQLClient
from repovet.plan_store import PlanStore
from repovet.registry_client import RegistryClient
from repovet.reply import render_reply
from repovet.webhook_security import verify_signature

DEFAULT_PORT = 8080

# Both paths are accepted for the same handler: "/webhook" is this module's
# original path (see tests/test_app_server.py), "/webhooks/github" is the
# path the bongo deploy docs/acceptance criteria standardize on. Same
# signature-verified handling either way.
WEBHOOK_PATHS = ("/webhook", "/webhooks/github")


def build_run_scan(cache: ResponseCache, token: str | None):
    """Return a `run_scan(raw_target) -> str` closure using an
    installation-scoped token, matching bot_cli.py's rendering contract."""
    rest_client = GitHubClient(token=token, cache=cache)
    graphql_client = GraphQLClient(token=token, cache=cache) if token else None
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

    return run_scan


class AppConfig:
    """Reads and validates the process's env-var secrets exactly once."""

    def __init__(self):
        self.app_id = os.environ.get("REPOVET_APP_ID")
        self.private_key_pem = os.environ.get("REPOVET_APP_PRIVATE_KEY")
        self.webhook_secret = os.environ.get("REPOVET_WEBHOOK_SECRET")
        missing = [
            name
            for name, value in (
                ("REPOVET_APP_ID", self.app_id),
                ("REPOVET_APP_PRIVATE_KEY", self.private_key_pem),
                ("REPOVET_WEBHOOK_SECRET", self.webhook_secret),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"missing required env vars: {', '.join(missing)}")


def make_rest_client_for_installation(config: AppConfig, cache: ResponseCache):
    """Return a `rest_client_for_installation(installation_id) -> GitHubClient`
    closure that mints a fresh app JWT and exchanges it for an installation
    token on every call (installation tokens expire in ~1 hour, so we don't
    cache them across requests)."""

    def rest_client_for_installation(installation_id: int) -> GitHubClient:
        app_jwt = create_app_jwt(config.app_id, config.private_key_pem)
        jwt_client = GitHubClient(token=app_jwt, cache=cache)
        installation_token = get_installation_token(jwt_client, installation_id)
        return GitHubClient(token=installation_token, cache=cache)

    return rest_client_for_installation


def make_handler(config: AppConfig, plan_store: PlanStore, cache: ResponseCache):
    rest_client_for_installation = make_rest_client_for_installation(config, cache)

    class WebhookHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quiet default stderr access log
            print(f"app_server: {fmt % args}", file=sys.stderr)

        def do_POST(self):
            if self.path not in WEBHOOK_PATHS:
                self._respond(404, {"error": "not found"})
                return

            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length)

            if not verify_signature(
                config.webhook_secret, raw_body, self.headers.get("X-Hub-Signature-256")
            ):
                self._respond(401, {"error": "invalid signature"})
                return

            event_name = self.headers.get("X-GitHub-Event", "")
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError:
                self._respond(400, {"error": "invalid JSON"})
                return

            run_scan = build_run_scan(cache, token=None)
            try:
                result = handle_event(
                    event_name,
                    payload,
                    rest_client_for_installation=rest_client_for_installation,
                    plan_store=plan_store,
                    run_scan=run_scan,
                )
            except Exception as e:  # never leak a 500 traceback to GitHub's retry logic
                print(f"app_server: error handling {event_name}: {e}", file=sys.stderr)
                self._respond(200, {"event": event_name, "action": "error", "error": str(e)})
                return

            self._respond(200, result)

        def do_GET(self):
            if self.path == "/health":
                self._respond(200, {"status": "ok"})
                return
            self._respond(404, {"error": "not found"})

        def _respond(self, status: int, body: dict):
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return WebhookHandler


def main() -> int:
    config = AppConfig()
    cache = ResponseCache()
    plan_store = PlanStore()
    handler_cls = make_handler(config, plan_store, cache)
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    server = ThreadingHTTPServer(("0.0.0.0", port), handler_cls)  # noqa: S104
    print(f"app_server: listening on :{port}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
