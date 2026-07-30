"""Fetch today's GitHub Trending repo list (all languages, daily window).

GitHub has no public trending API -- this scrapes the public
https://github.com/trending HTML page, same page a logged-out browser sees.
No auth, no scraping of anything gated or rate-limited beyond a normal page
load. Parsing is intentionally permissive (regex, not a full HTML parser)
since the page markup is not a stable contract -- if GitHub changes it, this
degrades to "found 0 repos" rather than crashing the scan loop.
"""

from __future__ import annotations

import re

import requests

TRENDING_URL = "https://github.com/trending"

# Matches repo links inside trending rows, e.g.
#   href="/owner/repo" data-view-component="true" ...
# Deliberately anchored on the data-view-component attribute that trending
# repo-name links carry, to avoid matching nav/footer links elsewhere on
# the page.
_REPO_LINK_RE = re.compile(r'href="/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)"\s+data-view-component')

# Path segments that look like "owner/repo" but are actually GitHub site
# sections, not real repos -- filter these out defensively.
_NON_REPO_OWNERS = {"trending", "topics", "sponsors", "collections", "marketplace"}


def parse_trending_html(html: str) -> list[str]:
    """Extract deduplicated "owner/repo" slugs from a trending page's HTML,
    preserving first-seen (i.e. ranked) order."""
    seen: dict[str, None] = {}
    for owner, repo in _REPO_LINK_RE.findall(html):
        if owner.lower() in _NON_REPO_OWNERS:
            continue
        slug = f"{owner}/{repo}"
        seen.setdefault(slug, None)
    return list(seen.keys())


def fetch_trending_repos(limit: int = 25, timeout: int = 15) -> list[str]:
    """Fetch today's trending page and return up to `limit` "owner/repo"
    slugs. Raises requests.RequestException on network failure -- caller
    decides whether that's fatal for this run."""
    resp = requests.get(
        TRENDING_URL,
        timeout=timeout,
        headers={"User-Agent": "Mozilla/5.0 (repovet trending scan; research use)"},
    )
    resp.raise_for_status()
    return parse_trending_html(resp.text)[:limit]
