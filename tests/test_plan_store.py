from pathlib import Path

import pytest

from repovet.plan_store import PlanStore


@pytest.fixture
def store(tmp_path: Path) -> PlanStore:
    return PlanStore(path=tmp_path / "marketplace.sqlite3")


def test_get_plan_returns_none_for_unknown_account(store):
    assert store.get_plan("nobody") is None


def test_upsert_then_get_plan_round_trips(store):
    store.upsert_plan(
        account_login="acme",
        account_id=123,
        plan_id=1,
        plan_name="repovet-free",
        on_free_trial=False,
        effective_date="2026-07-21",
    )
    plan = store.get_plan("acme")
    assert plan["account_login"] == "acme"
    assert plan["account_id"] == 123
    assert plan["plan_id"] == 1
    assert plan["plan_name"] == "repovet-free"
    assert plan["on_free_trial"] is False
    assert plan["effective_date"] == "2026-07-21"


def test_upsert_overwrites_existing_plan(store):
    store.upsert_plan("acme", 123, plan_id=1, plan_name="repovet-free")
    store.upsert_plan("acme", 123, plan_id=2, plan_name="repovet-pro", on_free_trial=True)

    plan = store.get_plan("acme")
    assert plan["plan_id"] == 2
    assert plan["plan_name"] == "repovet-pro"
    assert plan["on_free_trial"] is True


def test_remove_plan_deletes_the_row(store):
    store.upsert_plan("acme", 123, plan_id=1, plan_name="repovet-free")
    store.remove_plan("acme")
    assert store.get_plan("acme") is None


def test_remove_plan_on_unknown_account_is_a_no_op(store):
    store.remove_plan("nobody")  # should not raise
    assert store.get_plan("nobody") is None
