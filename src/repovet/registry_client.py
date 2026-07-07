"""Cached HTTP client for the PyPI JSON API and npm registry API, used by S3
(hallucinated dependency detection).

Neither registry exposes X-RateLimit-style headers (verified empirically),
so unlike github_client.py/graphql_client.py there's no proactive budget
check here — just cache-first + honest handling of 404 (a real "this
package doesn't exist" data point, not an error) and 429/5xx (NetworkError).

PyPI download counts would come from pypistats.org in theory, but that API
429s on back-to-back requests (verified empirically: two calls a few
seconds apart, second one rate-limited) — unsuitable for checking N
dependencies in one repovet run. PyPI packages therefore carry no
weekly_downloads signal at all; this is disclosed in S3's evidence/README,
not silently treated as zero.
"""

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

import requests

from repovet.cache import ResponseCache
from repovet.errors import NetworkError

REQUEST_TIMEOUT_SECONDS = 15
PYPI_URL = "https://pypi.org/pypi/{name}/json"
NPM_PACKAGE_URL = "https://registry.npmjs.org/{name}"
NPM_DOWNLOADS_URL = "https://api.npmjs.org/downloads/point/last-week/{name}"

_NOT_FOUND_MARKER = {"__repovet_not_found__": True}


@dataclass
class PackageInfo:
    name: str
    ecosystem: str  # "pypi" | "npm"
    exists: bool
    age_days: int | None = None
    weekly_downloads: int | None = None


class RegistryClient:
    def __init__(self, cache: ResponseCache, session: requests.Session | None = None):
        self.cache = cache
        self.session = session or requests.Session()

    def get_json(self, url: str, ttl_seconds: int = 24 * 3600) -> dict | None:
        """Returns parsed JSON, or None if the URL 404s. A 404 is a real
        answer ("this name isn't registered"), not treated as failure."""
        cache_key = f"registry:{url}"
        cached = self.cache.get(cache_key, ttl_seconds=ttl_seconds)
        if cached is not None:
            return None if cached == _NOT_FOUND_MARKER else cached

        try:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"network error calling registry ({url}): {e}") from e

        if response.status_code == 404:
            self.cache.set(cache_key, _NOT_FOUND_MARKER)
            return None
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            hint = f", retry after {retry_after}s" if retry_after else ""
            raise NetworkError(f"registry rate limit hit for {url}{hint}")
        if not response.ok:
            raise NetworkError(
                f"registry API error {response.status_code} for {url}: {response.text[:200]}"
            )

        data = response.json()
        self.cache.set(cache_key, data)
        return data


def _pypi_age_days(data: dict, now: datetime) -> int | None:
    upload_times = [
        f["upload_time_iso_8601"]
        for files in data.get("releases", {}).values()
        for f in files
        if f.get("upload_time_iso_8601")
    ]
    if not upload_times:
        return None
    earliest = datetime.fromisoformat(min(upload_times).replace("Z", "+00:00"))
    return (now - earliest).days


def check_pypi_package(client: RegistryClient, name: str, now: datetime) -> PackageInfo:
    data = client.get_json(PYPI_URL.format(name=quote(name)), ttl_seconds=24 * 3600)
    if data is None:
        return PackageInfo(name=name, ecosystem="pypi", exists=False)
    return PackageInfo(name=name, ecosystem="pypi", exists=True, age_days=_pypi_age_days(data, now))


def check_npm_package(client: RegistryClient, name: str, now: datetime) -> PackageInfo:
    encoded = quote(name, safe="@")
    data = client.get_json(NPM_PACKAGE_URL.format(name=encoded), ttl_seconds=24 * 3600)
    if data is None:
        return PackageInfo(name=name, ecosystem="npm", exists=False)

    age_days = None
    created = data.get("time", {}).get("created")
    if created:
        age_days = (now - datetime.fromisoformat(created.replace("Z", "+00:00"))).days

    weekly_downloads = None
    try:
        downloads = client.get_json(NPM_DOWNLOADS_URL.format(name=encoded), ttl_seconds=12 * 3600)
        if downloads:
            weekly_downloads = downloads.get("downloads")
    except NetworkError:
        pass  # downloads are a nice-to-have signal, don't fail existence over it

    return PackageInfo(
        name=name,
        ecosystem="npm",
        exists=True,
        age_days=age_days,
        weekly_downloads=weekly_downloads,
    )
