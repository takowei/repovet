"""Local sqlite cache for raw GitHub API responses.

Keyed by the full request URL (path + sorted query params). Avoids re-hitting
the API for repeat queries within the TTL window.
"""

import json
import sqlite3
import time
from pathlib import Path

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "repovet"
DEFAULT_CACHE_PATH = DEFAULT_CACHE_DIR / "cache.sqlite3"
DEFAULT_TTL_SECONDS = 3600


class ResponseCache:
    def __init__(self, path: Path = DEFAULT_CACHE_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS responses (
                cache_key TEXT PRIMARY KEY,
                json_blob TEXT NOT NULL,
                fetched_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def get(self, cache_key: str, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        row = self._conn.execute(
            "SELECT json_blob, fetched_at FROM responses WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if row is None:
            return None
        json_blob, fetched_at = row
        if time.time() - fetched_at > ttl_seconds:
            return None
        return json.loads(json_blob)

    def set(self, cache_key: str, value) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO responses (cache_key, json_blob, fetched_at) VALUES (?, ?, ?)",
            (cache_key, json.dumps(value), time.time()),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
