"""Unit tests for trending-page parsing. Pure string-in/list-out, no network."""

from fetch_trending import parse_trending_html

_SAMPLE_ROW = """
<article class="Box-row">
  <h2 class="h3 lh-condensed">
    <a href="/{owner}/{repo}" data-view-component="true" class="Link">
      {owner} / {repo}
    </a>
  </h2>
</article>
"""


def _page(*slugs: str) -> str:
    rows = "\n".join(
        _SAMPLE_ROW.format(owner=slug.split("/")[0], repo=slug.split("/")[1]) for slug in slugs
    )
    return f"<html><body>{rows}</body></html>"


def test_parse_extracts_owner_repo_slugs_in_order():
    html = _page("torvalds/linux", "facebook/react")
    assert parse_trending_html(html) == ["torvalds/linux", "facebook/react"]


def test_parse_dedupes_repeated_links():
    html = _page("torvalds/linux", "torvalds/linux")
    assert parse_trending_html(html) == ["torvalds/linux"]


def test_parse_filters_known_non_repo_site_sections():
    html = _page("trending/daily", "sponsors/someone", "facebook/react")
    assert parse_trending_html(html) == ["facebook/react"]


def test_parse_returns_empty_list_when_markup_has_no_matches():
    assert parse_trending_html("<html><body>no repos here</body></html>") == []
