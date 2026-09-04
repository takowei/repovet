"""Unit tests for the digest publish HTML rendering. Pure string-in/
string-out, no network -- GitHubPublisher itself is a thin API wrapper and
is exercised manually against the real API (see trending-cron rollout
notes), matching this repo's convention of not mocking requests for thin
network wrappers (c.f. fetch_trending_repos)."""

from publish_digest import markdown_to_html_body, render_digest_page, render_index_html


def test_markdown_to_html_body_renders_headings():
    out = markdown_to_html_body("# Title\n\n## Section\n")
    assert "<h1>Title</h1>" in out
    assert "<h2>Section</h2>" in out


def test_markdown_to_html_body_renders_bullet_list_with_link():
    out = markdown_to_html_body("- [a/b](https://github.com/a/b) — composite 10/100\n")
    assert "<ul>" in out
    assert '<a href="https://github.com/a/b">a/b</a>' in out
    assert "composite 10/100" in out
    assert out.strip().endswith("</ul>")


def test_markdown_to_html_body_closes_list_before_paragraph():
    out = markdown_to_html_body("- item one\n\nplain paragraph\n")
    assert "</ul>\n<p>plain paragraph</p>" in out


def test_markdown_to_html_body_renders_whole_line_italic():
    out = markdown_to_html_body("_no scored repos in this window._")
    assert out == "<p><em>no scored repos in this window.</em></p>"


def test_markdown_to_html_body_escapes_html_special_chars():
    out = markdown_to_html_body("plain <script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_render_digest_page_includes_date_and_body():
    out = render_digest_page("# repovet weekly trending digest\n", "2026-08-10")
    assert "2026-08-10" in out
    assert "<h1>repovet weekly trending digest</h1>" in out
    assert '<a href="index.html">' in out


def test_render_index_html_lists_dates_newest_first():
    out = render_index_html(["2026-08-03", "2026-08-10", "2026-07-27"])
    idx_10 = out.index("2026-08-10.html")
    idx_03 = out.index("2026-08-03.html")
    idx_27 = out.index("2026-07-27.html")
    assert idx_10 < idx_03 < idx_27


def test_render_index_html_dedupes_dates():
    out = render_index_html(["2026-08-10", "2026-08-10"])
    assert out.count("2026-08-10.html") == 1


def test_render_index_html_handles_empty_list():
    out = render_index_html([])
    assert "No digests published yet" in out
