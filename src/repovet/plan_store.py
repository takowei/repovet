"""Local sqlite store mapping a GitHub Marketplace installation to its plan.

Populated exclusively by `marketplace_purchase` webhook events (see
`app_webhook.py`). This is intentionally the simplest thing that can work for
stage 1 (free-tier-only listing): a single table, no external DB. If/when a
paid plan ships, `get_plan` is the one place feature gating reads from.
"""

import sqlite3
import time
from pathlib import Path

DEFAULT_STORE_DIR = Path.home() / ".cache" / "repovet"
DEFAULT_STORE_PATH = DEFAULT_STORE_DIR / "marketplace.sqlite3"


class PlanStore:
    def __init__(self, path: Path = DEFAULT_STORE_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: app_server.py handles each webhook
        # delivery on its own thread (ThreadingHTTPServer); sqlite3 still
        # serializes access internally, which is fine at webhook volume.
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS installations (
                account_login TEXT PRIMARY KEY,
                account_id INTEGER NOT NULL,
                plan_id INTEGER NOT NULL,
                plan_name TEXT NOT NULL,
                on_free_trial INTEGER NOT NULL DEFAULT 0,
                effective_date TEXT,
                updated_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def upsert_plan(
        self,
        account_login: str,
        account_id: int,
        plan_id: int,
        plan_name: str,
        on_free_trial: bool = False,
        effective_date: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO installations
                (account_login, account_id, plan_id, plan_name, on_free_trial,
                 effective_date, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_login) DO UPDATE SET
                account_id=excluded.account_id,
                plan_id=excluded.plan_id,
                plan_name=excluded.plan_name,
                on_free_trial=excluded.on_free_trial,
                effective_date=excluded.effective_date,
                updated_at=excluded.updated_at
            """,
            (
                account_login,
                account_id,
                plan_id,
                plan_name,
                int(on_free_trial),
                effective_date,
                time.time(),
            ),
        )
        self._conn.commit()

    def remove_plan(self, account_login: str) -> None:
        self._conn.execute("DELETE FROM installations WHERE account_login = ?", (account_login,))
        self._conn.commit()

    def get_plan(self, account_login: str) -> dict | None:
        row = self._conn.execute(
            """
            SELECT account_id, plan_id, plan_name, on_free_trial, effective_date, updated_at
            FROM installations WHERE account_login = ?
            """,
            (account_login,),
        ).fetchone()
        if row is None:
            return None
        return {
            "account_login": account_login,
            "account_id": row[0],
            "plan_id": row[1],
            "plan_name": row[2],
            "on_free_trial": bool(row[3]),
            "effective_date": row[4],
            "updated_at": row[5],
        }

    def close(self) -> None:
        self._conn.close()
