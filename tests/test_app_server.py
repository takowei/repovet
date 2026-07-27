import hmac
import json
import threading
from pathlib import Path

import pytest
import requests

from repovet.app_server import AppConfig, make_handler
from repovet.cache import ResponseCache
from repovet.plan_store import PlanStore

WEBHOOK_SECRET = "test-secret"


@pytest.fixture
def running_server(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("REPOVET_APP_ID", "app-123")
    monkeypatch.setenv("REPOVET_APP_PRIVATE_KEY", "unused-in-these-tests")
    monkeypatch.setenv("REPOVET_WEBHOOK_SECRET", WEBHOOK_SECRET)

    from http.server import ThreadingHTTPServer

    config = AppConfig()
    cache = ResponseCache(path=tmp_path / "cache.sqlite3")
    plan_store = PlanStore(path=tmp_path / "marketplace.sqlite3")
    handler_cls = make_handler(config, plan_store, cache)

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    yield f"http://127.0.0.1:{port}", plan_store

    server.shutdown()
    thread.join(timeout=5)


def sign(payload: bytes) -> str:
    return "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), payload, "sha256").hexdigest()


def test_health_endpoint(running_server):
    base_url, _ = running_server
    response = requests.get(f"{base_url}/health", timeout=5)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_rejects_bad_signature(running_server):
    base_url, _ = running_server
    body = json.dumps({"action": "ping"}).encode()
    response = requests.post(
        f"{base_url}/webhook",
        data=body,
        headers={"X-Hub-Signature-256": "sha256=deadbeef", "X-GitHub-Event": "ping"},
        timeout=5,
    )
    assert response.status_code == 401


def test_webhook_accepts_ping_with_valid_signature(running_server):
    base_url, _ = running_server
    body = json.dumps({"zen": "hello"}).encode()
    response = requests.post(
        f"{base_url}/webhook",
        data=body,
        headers={"X-Hub-Signature-256": sign(body), "X-GitHub-Event": "ping"},
        timeout=5,
    )
    assert response.status_code == 200
    assert response.json() == {"event": "ping", "action": "no-op"}


def test_webhooks_github_alias_rejects_bad_signature(running_server):
    """The bongo deploy exposes this path publicly; verify the alias enforces
    the same signature check as /webhook (fail case)."""
    base_url, _ = running_server
    body = json.dumps({"action": "ping"}).encode()
    response = requests.post(
        f"{base_url}/webhooks/github",
        data=body,
        headers={"X-Hub-Signature-256": "sha256=deadbeef", "X-GitHub-Event": "ping"},
        timeout=5,
    )
    assert response.status_code == 401


def test_webhooks_github_alias_accepts_valid_signature(running_server):
    """Same as above, pass case -- proves the alias isn't just a 404 bypass."""
    base_url, _ = running_server
    body = json.dumps({"zen": "hello"}).encode()
    response = requests.post(
        f"{base_url}/webhooks/github",
        data=body,
        headers={"X-Hub-Signature-256": sign(body), "X-GitHub-Event": "ping"},
        timeout=5,
    )
    assert response.status_code == 200
    assert response.json() == {"event": "ping", "action": "no-op"}


def test_webhook_marketplace_purchase_updates_plan_store(running_server):
    base_url, plan_store = running_server
    payload = {
        "action": "purchased",
        "marketplace_purchase": {
            "account": {"login": "acme", "id": 1},
            "plan": {"id": 1, "name": "repovet-free"},
        },
    }
    body = json.dumps(payload).encode()
    response = requests.post(
        f"{base_url}/webhook",
        data=body,
        headers={"X-Hub-Signature-256": sign(body), "X-GitHub-Event": "marketplace_purchase"},
        timeout=5,
    )
    assert response.status_code == 200
    assert plan_store.get_plan("acme")["plan_name"] == "repovet-free"


def test_unknown_path_returns_404(running_server):
    base_url, _ = running_server
    response = requests.get(f"{base_url}/nope", timeout=5)
    assert response.status_code == 404
