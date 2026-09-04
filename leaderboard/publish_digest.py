"""Publish a generate_weekly_digest.py markdown file as a static HTML page
under docs/digests/ on the takowei/repovet GitHub Pages site, so the
trending-cron container's weekly digest goes live with no human step.

Two pure, testable pieces (no network):
  - markdown_to_html_body(): converts the small, fixed markdown subset
    generate_weekly_digest.py produces (h1/h2, "- [text](url) — ..."
    bullets, whole-line "_italic_") into HTML fragments.
  - render_index_html(): builds the docs/digests/index.html listing page
    from a set of already-published dates.

One network-touching piece (GitHubPublisher, thin wrapper over the GitHub
Contents API -- same env-only-token convention as github_client.py) that
does the actual read-sha/compare/write dance:
  - Skips the commit entirely if the rendered content is byte-identical to
    what's already on `main` (idempotent: rerunning against the same
    digest file, e.g. after a transient failure, does not spam commits).
  - Uses the Contents API instead of a local git clone + push -- no git
    identity/SSH needed inside the container, and commits are attributed
    to whichever token is configured.

Usage (inside the trending-cron container, GITHUB_TOKEN from env):
    python leaderboard/publish_digest.py --digest-file /data/digests/2026-08-10.md

--dry-run renders the page(s) to --local-out on disk instead of calling the
GitHub API, so this is testable without a token or network access.
"""

from __future__ import annotations

import argparse
import base64
import html
import os
import re
import sys
from pathlib import Path

import requests

DEFAULT_REPO = "takowei/repovet"
DEFAULT_BRANCH = "main"
DEFAULT_DOCS_DIR = "docs/digests"
REQUEST_TIMEOUT_SECONDS = 15

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_WHOLE_LINE_ITALIC_RE = re.compile(r"^_(.*)_$")

CSS = """
:root { color-scheme: light; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       max-width: 800px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; line-height: 1.6; }
h1 { margin-bottom: 0.2rem; }
h2 { margin-top: 2rem; border-top: 1px solid #e2e2e2; padding-top: 1rem; }
ul { padding-left: 1.3rem; }
li { margin: 0.3rem 0; }
a { color: #0b5fa5; }
.back-link { font-size: 0.9rem; }
footer { margin-top: 2.5rem; font-size: 0.82rem; color: #666;
         border-top: 1px solid #e2e2e2; padding-top: 1rem; }
"""


class PublishError(RuntimeError):
    """Raised when the GitHub Contents API doesn't behave as expected."""


def _inline_html(text: str) -> str:
    """Render the small inline markdown subset used in digest text:
    [text](url) links and whole-line _italic_ wrapping. Everything else is
    HTML-escaped verbatim."""
    whole_italic = _WHOLE_LINE_ITALIC_RE.match(text)
    if whole_italic:
        return f"<em>{_inline_html(whole_italic.group(1))}</em>"

    pieces = []
    last_end = 0
    for match in _LINK_RE.finditer(text):
        pieces.append(html.escape(text[last_end : match.start()]))
        link_text, url = match.group(1), match.group(2)
        pieces.append(f'<a href="{html.escape(url)}">{html.escape(link_text)}</a>')
        last_end = match.end()
    pieces.append(html.escape(text[last_end:]))
    return "".join(pieces)


def markdown_to_html_body(markdown_text: str) -> str:
    """Convert generate_weekly_digest.py's markdown output into an HTML
    fragment (no <html>/<body> wrapper). Handles exactly the subset that
    generator emits: '# ', '## ', '- ' bullet lists, blank-line paragraph
    breaks, and plain text lines."""
    out_lines: list[str] = []
    list_open = False

    def _close_list():
        nonlocal list_open
        if list_open:
            out_lines.append("</ul>")
            list_open = False

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if not line:
            _close_list()
            continue
        if line.startswith("# "):
            _close_list()
            out_lines.append(f"<h1>{_inline_html(line[2:])}</h1>")
        elif line.startswith("## "):
            _close_list()
            out_lines.append(f"<h2>{_inline_html(line[3:])}</h2>")
        elif line.startswith("- "):
            if not list_open:
                out_lines.append("<ul>")
                list_open = True
            out_lines.append(f"<li>{_inline_html(line[2:])}</li>")
        else:
            _close_list()
            out_lines.append(f"<p>{_inline_html(line)}</p>")
    _close_list()
    return "\n".join(out_lines)


def render_digest_page(markdown_text: str, date_str: str) -> str:
    body = markdown_to_html_body(markdown_text)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>repovet trending digest -- {html.escape(date_str)}</title>
<style>{CSS}</style>
</head>
<body>
<p class="back-link"><a href="index.html">&larr; all digests</a> &middot;
   <a href="../index.html">repovet leaderboard</a></p>
{body}
<footer>
  <p>Generated automatically by
     <a href="https://github.com/{DEFAULT_REPO}" target="_blank" rel="noopener">repovet</a>'s
     trending-cron job. Automated signals only, not verified findings.</p>
</footer>
</body>
</html>
"""


def render_index_html(dates: list[str]) -> str:
    """dates: any iterable of 'YYYY-MM-DD' strings (already published).
    Renders newest-first regardless of input order."""
    ordered = sorted(set(dates), reverse=True)
    if ordered:
        items = "\n".join(f'  <li><a href="{d}.html">{d}</a></li>' for d in ordered)
        list_html = f"<ul>\n{items}\n</ul>"
    else:
        list_html = "<p><em>No digests published yet.</em></p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>repovet trending digests</title>
<style>{CSS}</style>
</head>
<body>
<p class="back-link"><a href="../index.html">&larr; repovet leaderboard</a></p>
<h1>repovet weekly trending digests</h1>
<p>One entry per Monday, rolling up the previous 7 days of GitHub Trending
repos scored by repovet's S1-S4 engine. Automated signals only, not
verified findings.</p>
{list_html}
</body>
</html>
"""


class GitHubPublisher:
    """Thin wrapper over the GitHub Contents API. Env-only token, same
    convention as repovet.github_client.GitHubClient -- never reads a
    secret file directly."""

    def __init__(
        self,
        repo: str,
        token: str,
        branch: str = DEFAULT_BRANCH,
        session: requests.Session | None = None,
    ):
        self.repo = repo
        self.token = token
        self.branch = branch
        self.session = session or requests.Session()

    def _headers(self) -> dict:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _contents_url(self, path: str) -> str:
        return f"https://api.github.com/repos/{self.repo}/contents/{path}"

    def get_file(self, path: str) -> tuple[str | None, str | None]:
        """Returns (decoded_text, sha), or (None, None) if the file does
        not exist yet on this branch."""
        resp = self.session.get(
            self._contents_url(path),
            headers=self._headers(),
            params={"ref": self.branch},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if resp.status_code == 404:
            return None, None
        if resp.status_code != 200:
            raise PublishError(f"GET {path} failed: {resp.status_code} {resp.text[:300]}")
        data = resp.json()
        return base64.b64decode(data["content"]).decode("utf-8"), data["sha"]

    def put_file(self, path: str, content: str, message: str, sha: str | None) -> None:
        body = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": self.branch,
        }
        if sha is not None:
            body["sha"] = sha
        resp = self.session.put(
            self._contents_url(path),
            headers=self._headers(),
            json=body,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if resp.status_code not in (200, 201):
            raise PublishError(f"PUT {path} failed: {resp.status_code} {resp.text[:300]}")

    def list_digest_dates(self, docs_dir: str) -> list[str]:
        """Lists 'YYYY-MM-DD' dates already published under docs_dir, based
        on <date>.html filenames (index.html excluded)."""
        resp = self.session.get(
            self._contents_url(docs_dir),
            headers=self._headers(),
            params={"ref": self.branch},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if resp.status_code == 404:
            return []
        if resp.status_code != 200:
            raise PublishError(f"GET {docs_dir} failed: {resp.status_code} {resp.text[:300]}")
        dates = []
        for entry in resp.json():
            name = entry.get("name", "")
            if name.endswith(".html") and name != "index.html":
                dates.append(name[: -len(".html")])
        return dates


def publish(publisher: GitHubPublisher, docs_dir: str, date_str: str, page_html: str) -> None:
    """Writes docs_dir/{date_str}.html (skipping the commit if content is
    unchanged) then rebuilds docs_dir/index.html from the resulting set of
    published dates."""
    digest_path = f"{docs_dir}/{date_str}.html"
    existing_content, existing_sha = publisher.get_file(digest_path)
    if existing_content == page_html:
        print(f"[publish_digest] {digest_path} unchanged, skipping commit", file=sys.stderr)
    else:
        publisher.put_file(
            digest_path,
            page_html,
            message=f"docs: publish trending digest {date_str}",
            sha=existing_sha,
        )
        print(f"[publish_digest] published {digest_path}", file=sys.stderr)

    known_dates = set(publisher.list_digest_dates(docs_dir)) | {date_str}
    index_html = render_index_html(list(known_dates))
    index_path = f"{docs_dir}/index.html"
    existing_index, index_sha = publisher.get_file(index_path)
    if existing_index == index_html:
        print(f"[publish_digest] {index_path} unchanged, skipping commit", file=sys.stderr)
    else:
        publisher.put_file(
            index_path,
            index_html,
            message=f"docs: update digest index ({date_str})",
            sha=index_sha,
        )
        print(f"[publish_digest] updated {index_path}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--digest-file", type=Path, required=True)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--docs-dir", default=DEFAULT_DOCS_DIR)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render page(s) under --local-out instead of calling the GitHub API "
        "(no token/network needed).",
    )
    parser.add_argument("--local-out", type=Path, default=Path("./_digest_publish_preview"))
    args = parser.parse_args(argv)

    date_str = args.digest_file.stem
    markdown_text = args.digest_file.read_text(encoding="utf-8")
    page_html = render_digest_page(markdown_text, date_str)

    if args.dry_run:
        args.local_out.mkdir(parents=True, exist_ok=True)
        digest_out = args.local_out / f"{date_str}.html"
        digest_out.write_text(page_html, encoding="utf-8")
        index_out = args.local_out / "index.html"
        index_out.write_text(render_index_html([date_str]), encoding="utf-8")
        print(f"[dry-run] wrote {digest_out} and {index_out}", file=sys.stderr)
        return 0

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("error: GITHUB_TOKEN not set -- cannot publish", file=sys.stderr)
        return 1

    publisher = GitHubPublisher(repo=args.repo, token=token, branch=args.branch)
    try:
        publish(publisher, args.docs_dir, date_str, page_html)
    except PublishError as exc:
        print(f"error: publish failed -- {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
