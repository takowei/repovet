from pathlib import Path

import pytest

from repovet.app_webhook import handle_event
from repovet.plan_store import PlanStore
from tests.conftest import FakeResponse, FakeSession, make_client


@pytest.fixture
def plan_store(tmp_path: Path) -> PlanStore:
    return PlanStore(path=tmp_path / "marketplace.sqlite3")


def _pr_payload(action="opened", repo="acme/widgets", pr_number=5, installation_id=42):
    return {
        "action": action,
        "installation": {"id": installation_id},
        "repository": {"full_name": repo},
        "pull_request": {"number": pr_number},
    }


def test_pull_request_opened_posts_scan_result(tmp_cache, plan_store):
    session = FakeSession([FakeResponse(201, {"id": 1}, {"X-RateLimit-Remaining": "50"})])
    client = make_client(tmp_cache, [], token="install-token")
    client.session = session

    calls = []

    def run_scan(target: str) -> str:
        calls.append(target)
        return "scan result"

    result = handle_event(
        "pull_request",
        _pr_payload(),
        rest_client_for_installation=lambda installation_id: client,
        plan_store=plan_store,
        run_scan=run_scan,
    )

    assert result["action"] == "commented"
    assert calls == ["gh:acme/widgets"]
    assert len(session.calls) == 1
    url, body = session.calls[0]
    assert url == "https://api.github.com/repos/acme/widgets/issues/5/comments"
    assert "scan result" in body["body"]
    assert "repovet" in body["body"]


@pytest.mark.parametrize("action", ["closed", "labeled", "assigned"])
def test_pull_request_unsupported_action_is_ignored(tmp_cache, plan_store, action):
    def run_scan(target: str) -> str:
        raise AssertionError("run_scan should not be called for unsupported PR actions")

    result = handle_event(
        "pull_request",
        _pr_payload(action=action),
        rest_client_for_installation=lambda installation_id: (_ for _ in ()).throw(
            AssertionError("should not need a client")
        ),
        plan_store=plan_store,
        run_scan=run_scan,
    )
    assert result["action"] == "ignored"


def test_pull_request_without_installation_id_is_skipped(plan_store):
    payload = _pr_payload()
    del payload["installation"]

    result = handle_event(
        "pull_request",
        payload,
        rest_client_for_installation=lambda installation_id: None,
        plan_store=plan_store,
        run_scan=lambda target: "unused",
    )
    assert result["action"] == "skipped"


def test_marketplace_purchase_upserts_plan(plan_store):
    payload = {
        "action": "purchased",
        "marketplace_purchase": {
            "account": {"login": "acme", "id": 999},
            "plan": {"id": 1, "name": "repovet-free"},
            "on_free_trial": False,
            "effective_date": "2026-07-21",
        },
    }

    result = handle_event(
        "marketplace_purchase",
        payload,
        rest_client_for_installation=lambda installation_id: None,
        plan_store=plan_store,
        run_scan=lambda target: "unused",
    )

    assert result["action"] == "plan_synced"
    plan = plan_store.get_plan("acme")
    assert plan["plan_name"] == "repovet-free"
    assert plan["account_id"] == 999


def test_marketplace_purchase_cancelled_removes_plan(plan_store):
    plan_store.upsert_plan("acme", 999, plan_id=1, plan_name="repovet-free")

    payload = {
        "action": "cancelled",
        "marketplace_purchase": {"account": {"login": "acme", "id": 999}},
    }

    handle_event(
        "marketplace_purchase",
        payload,
        rest_client_for_installation=lambda installation_id: None,
        plan_store=plan_store,
        run_scan=lambda target: "unused",
    )

    assert plan_store.get_plan("acme") is None


@pytest.mark.parametrize("event_name", ["installation", "installation_repositories", "ping"])
def test_lifecycle_events_are_no_ops(plan_store, event_name):
    result = handle_event(
        event_name,
        {},
        rest_client_for_installation=lambda installation_id: None,
        plan_store=plan_store,
        run_scan=lambda target: "unused",
    )
    assert result["action"] == "no-op"


def test_unsupported_event_is_ignored(plan_store):
    result = handle_event(
        "star",
        {},
        rest_client_for_installation=lambda installation_id: None,
        plan_store=plan_store,
        run_scan=lambda target: "unused",
    )
    assert result["action"] == "ignored"
