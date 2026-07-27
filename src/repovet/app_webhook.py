"""GitHub App webhook event handling: dispatch a verified webhook payload to
the right handler.

Signature verification happens one layer up (`app_server.py`, via
`webhook_security.verify_signature`) -- everything in this module assumes
the payload is authentic and only decides *what to do* with it.

Supported events (stage 1, free-tier-only listing):
- `pull_request` (opened/reopened/synchronize): run a repovet scan on the PR's
  base repo and post the result as an issue comment on the PR.
- `marketplace_purchase` (purchased/changed/pending_change/cancelled): keep
  `plan_store` in sync with GitHub's billing state. Stage 1 ships free-only,
  but this must exist before any paid plan can go live, per Marketplace
  requirements -- see README "GitHub App / Marketplace" section.
- `installation`, `installation_repositories`, `ping`: acknowledged, no-op.
"""

from repovet.bot import post_issue_comment
from repovet.github_client import GitHubClient
from repovet.plan_store import PlanStore

PR_ACTIONS_TO_SCAN = {"opened", "reopened", "synchronize"}
MARKETPLACE_REMOVE_ACTIONS = {"cancelled"}

REPLY_FOOTER = (
    "\n\n---\n*Posted automatically by "
    "[repovet](https://github.com/takowei/repovet) — GitHub App install "
    "scan. [What is this?](https://github.com/takowei/repovet#automation--bot)*"
)


def handle_pull_request(payload: dict, rest_client: GitHubClient, run_scan) -> dict | None:
    """Run a scan on the PR's repo and post it as a comment on that PR.

    `run_scan(raw_target: str) -> str` mirrors `bot_cli.py`'s contract so
    both entry points share the same rendering path.
    """
    action = payload.get("action")
    if action not in PR_ACTIONS_TO_SCAN:
        return None

    repo_full_name = payload["repository"]["full_name"]
    issue_number = payload["pull_request"]["number"]
    target = f"gh:{repo_full_name}"

    reply = run_scan(target) + REPLY_FOOTER
    post_issue_comment(rest_client, repo_full_name, issue_number, reply)
    return {"posted_to": repo_full_name, "issue_number": issue_number}


def handle_marketplace_purchase(payload: dict, plan_store: PlanStore) -> dict:
    """Keep `plan_store` in sync with a `marketplace_purchase` webhook.

    `cancelled` removes the row entirely (treat as "no plan" -- callers
    gating features on `plan_store.get_plan()` returning None is the
    intended pattern). Every other action (`purchased`, `changed`,
    `pending_change`, `pending_change_cancelled`) upserts the current plan.
    """
    action = payload.get("action")
    purchase = payload.get("marketplace_purchase") or {}
    account = purchase.get("account") or {}
    login = account.get("login")

    if action in MARKETPLACE_REMOVE_ACTIONS:
        if login:
            plan_store.remove_plan(login)
        return {"account": login, "plan_removed": True}

    plan = purchase.get("plan") or {}
    plan_store.upsert_plan(
        account_login=login,
        account_id=account.get("id"),
        plan_id=plan.get("id"),
        plan_name=plan.get("name"),
        on_free_trial=bool(purchase.get("on_free_trial", False)),
        effective_date=purchase.get("effective_date"),
    )
    return {"account": login, "plan_name": plan.get("name")}


def handle_event(
    event_name: str,
    payload: dict,
    *,
    rest_client_for_installation,
    plan_store: PlanStore,
    run_scan,
) -> dict:
    """Route one verified webhook delivery.

    `rest_client_for_installation(installation_id: int) -> GitHubClient` is
    injected so callers control how installation tokens are minted (real
    JWT exchange in production, a canned fake in tests).
    """
    if event_name == "pull_request":
        if payload.get("action") not in PR_ACTIONS_TO_SCAN:
            return {"event": event_name, "action": "ignored", "reason": "unhandled PR action"}
        installation_id = (payload.get("installation") or {}).get("id")
        if installation_id is None:
            return {"event": event_name, "action": "skipped", "reason": "no installation id"}
        rest_client = rest_client_for_installation(installation_id)
        result = handle_pull_request(payload, rest_client, run_scan)
        return {"event": event_name, "action": "commented", "result": result}

    if event_name == "marketplace_purchase":
        result = handle_marketplace_purchase(payload, plan_store)
        return {"event": event_name, "action": "plan_synced", "result": result}

    if event_name in ("installation", "installation_repositories", "ping"):
        return {"event": event_name, "action": "no-op"}

    return {"event": event_name, "action": "ignored", "reason": "unsupported event type"}
