"""Thin, rate-limit-aware GitHub REST client with response caching.

Design notes:
- Reads GITHUB_TOKEN from the environment only. Never reads any key/secret
  file directly; the caller (shell) is responsible for sourcing it.
- Before every request we check the last known rate-limit state. If the
  remaining quota is at/under the safety buffer, we fail loudly
  (NetworkError) instead of silently returning partial/empty data.
"""

import time

import requests

from repovet.cache import ResponseCache
from repovet.errors import InputError, NetworkError

API_BASE = "https://api.github.com"
RATE_LIMIT_BUFFER = 3  # abort rather than risk exhausting the quota mid-run
REQUEST_TIMEOUT_SECONDS = 15


class GitHubClient:
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

    @property
    def anonymous(self) -> bool:
        return not self.token

    def _headers(self) -> dict:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

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
            f"GitHub rate limit nearly exhausted ({self.rate_limit_remaining} left"
            f"{wait_hint}); aborting rather than risk a partial/silent result"
        )

    def _record_rate_limit(self, response: requests.Response) -> None:
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset = response.headers.get("X-RateLimit-Reset")
        if remaining is not None:
            self.rate_limit_remaining = int(remaining)
        if reset is not None:
            self.rate_limit_reset = int(reset)

    def get(
        self, path: str, params: dict | None = None, ttl_seconds: int | None = None
    ) -> dict | list:
        """GET a GitHub API path, honoring cache + rate limit budget."""
        params = params or {}
        cache_key = path + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))

        cached = self.cache.get(
            cache_key, ttl_seconds=ttl_seconds if ttl_seconds is not None else 3600
        )
        if cached is not None:
            return cached

        self._check_budget()

        url = f"{API_BASE}{path}"
        try:
            response = self.session.get(
                url, headers=self._headers(), params=params, timeout=REQUEST_TIMEOUT_SECONDS
            )
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"network error calling GitHub API ({path}): {e}") from e

        self._record_rate_limit(response)

        if response.status_code == 404:
            raise InputError(f"not found on GitHub: {path}")

        if response.status_code in (403, 429):
            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining == "0":
                reset = response.headers.get("X-RateLimit-Reset")
                wait_seconds = max(0, int(reset) - int(time.time())) if reset else None
                hint = f", resets in {wait_seconds}s" if wait_seconds is not None else ""
                raise NetworkError(f"GitHub rate limit exceeded{hint}")
            retry_after = response.headers.get("Retry-After")
            hint = f", retry after {retry_after}s" if retry_after else ""
            raise NetworkError(f"GitHub secondary rate limit hit{hint}")

        if not response.ok:
            raise NetworkError(
                f"GitHub API error {response.status_code} for {path}: {response.text[:200]}"
            )

        data = response.json()
        self.cache.set(cache_key, data)
        return data

    def post(self, path: str, json_body: dict) -> dict:
        """POST a GitHub API path (e.g. creating an issue comment).

        Not cached -- a POST is a side effect, not an idempotent read. Still
        goes through the same rate-limit budget check and error mapping as
        get(), since POSTs share the same primary rate limit.
        """
        self._check_budget()

        url = f"{API_BASE}{path}"
        try:
            response = self.session.post(
                url, headers=self._headers(), json=json_body, timeout=REQUEST_TIMEOUT_SECONDS
            )
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"network error calling GitHub API ({path}): {e}") from e

        self._record_rate_limit(response)

        if response.status_code == 404:
            raise InputError(f"not found on GitHub: {path}")

        if response.status_code in (403, 429):
            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining == "0":
                reset = response.headers.get("X-RateLimit-Reset")
                wait_seconds = max(0, int(reset) - int(time.time())) if reset else None
                hint = f", resets in {wait_seconds}s" if wait_seconds is not None else ""
                raise NetworkError(f"GitHub rate limit exceeded{hint}")
            retry_after = response.headers.get("Retry-After")
            hint = f", retry after {retry_after}s" if retry_after else ""
            raise NetworkError(f"GitHub secondary rate limit hit{hint}")

        if not response.ok:
            raise NetworkError(
                f"GitHub API error {response.status_code} for {path}: {response.text[:200]}"
            )

        return response.json()
