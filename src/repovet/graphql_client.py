"""Rate-limit-aware GitHub GraphQL client, mirroring github_client.py's REST
client but for the /graphql endpoint (needed for S1: stargazers with
starredAt timestamps aren't available via REST at all).

GitHub's GraphQL API has no usable anonymous tier (verified empirically:
an unauthenticated request gets HTTP 403 "rate limit exceeded" almost
immediately) — so this client refuses to run without a token, rather than
pretending to degrade gracefully like the REST client does.
"""

import hashlib
import json
import time

import requests

from repovet.cache import ResponseCache
from repovet.errors import InputError, NetworkError

GRAPHQL_URL = "https://api.github.com/graphql"
RATE_LIMIT_BUFFER = 3
REQUEST_TIMEOUT_SECONDS = 30


class GraphQLClient:
    def __init__(
        self,
        token: str | None,
        cache: ResponseCache,
        session: requests.Session | None = None,
    ):
        self.token = token
        self.cache = cache
        self.session = session or requests.Session()
        self.rate_limit_remaining: int | None = None
        self.rate_limit_reset: int | None = None

    def _check_budget(self) -> None:
        if self.rate_limit_remaining is None:
            return
        if self.rate_limit_remaining > RATE_LIMIT_BUFFER:
            return
        wait_hint = ""
        if self.rate_limit_reset:
            wait_seconds = max(0, int(self.rate_limit_reset - time.time()))
            wait_hint = f", resets in {wait_seconds}s"
        raise NetworkError(
            f"GitHub GraphQL rate limit nearly exhausted ({self.rate_limit_remaining} left"
            f"{wait_hint}); aborting rather than risk a partial/silent result"
        )

    def _record_rate_limit(self, response: requests.Response) -> None:
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset = response.headers.get("X-RateLimit-Reset")
        if remaining is not None:
            self.rate_limit_remaining = int(remaining)
        if reset is not None:
            self.rate_limit_reset = int(reset)

    def query(self, query: str, variables: dict, ttl_seconds: int = 3600) -> dict:
        """Run a GraphQL query, honoring cache + rate-limit budget. Returns the
        `data` object. Raises InputError for NOT_FOUND, NetworkError for
        anything else that stops us getting a usable result."""
        if not self.token:
            raise InputError("GraphQL requires GITHUB_TOKEN (no anonymous access)")

        cache_key = (
            "graphql:"
            + hashlib.sha256((query + json.dumps(variables, sort_keys=True)).encode()).hexdigest()
        )
        cached = self.cache.get(cache_key, ttl_seconds=ttl_seconds)
        if cached is not None:
            return cached

        self._check_budget()

        try:
            response = self.session.post(
                GRAPHQL_URL,
                headers={"Authorization": f"Bearer {self.token}"},
                json={"query": query, "variables": variables},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"network error calling GitHub GraphQL API: {e}") from e

        self._record_rate_limit(response)

        if response.status_code in (403, 429):
            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining == "0":
                reset = response.headers.get("X-RateLimit-Reset")
                wait_seconds = max(0, int(reset) - int(time.time())) if reset else None
                hint = f", resets in {wait_seconds}s" if wait_seconds is not None else ""
                raise NetworkError(f"GitHub GraphQL rate limit exceeded{hint}")
            raise NetworkError(f"GitHub GraphQL request forbidden: {response.text[:200]}")

        if not response.ok:
            raise NetworkError(
                f"GitHub GraphQL API error {response.status_code}: {response.text[:200]}"
            )

        body = response.json()
        errors = body.get("errors") or []
        if any(e.get("type") == "NOT_FOUND" for e in errors):
            raise InputError(f"not found on GitHub (GraphQL): {errors[0].get('message')}")
        if errors:
            raise NetworkError(f"GitHub GraphQL returned errors: {errors[0].get('message')}")

        data = body["data"]
        self.cache.set(cache_key, data)
        return data
