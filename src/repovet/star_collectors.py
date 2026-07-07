"""Gathers stargazer data (with starredAt timestamps) for S1 fake-star
detection. GraphQL-only: REST doesn't expose star timestamps at all.

Sampling strategy (must stay honest about what it does and doesn't see):
- stargazerCount <= FULL_SCAN_STAR_CAP: fetch every stargazer. No blind spots.
- above that: stratified sample of the most recent RECENT_SAMPLE_PAGES pages
  (DESC) + the earliest EARLIEST_SAMPLE_PAGES pages (ASC). This catches
  "recent/ongoing campaign" and "inflated at launch" patterns, but a
  campaign buried in the *middle* of a large repo's history will be missed.
  That blind spot is real and is written into the evidence string, not
  hidden (see collect_star_signals' `sampling_note`).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from repovet.errors import InputError
from repovet.graphql_client import GraphQLClient
from repovet.targets import Target

FULL_SCAN_STAR_CAP = 2000
PAGE_SIZE = 100
RECENT_SAMPLE_PAGES = 3
EARLIEST_SAMPLE_PAGES = 2
MAX_FULL_SCAN_PAGES = FULL_SCAN_STAR_CAP // PAGE_SIZE

_META_QUERY = """
query($owner:String!,$name:String!){
  repository(owner:$owner,name:$name){ stargazerCount }
}
"""

_STARGAZERS_QUERY = """
query($owner:String!,$name:String!,$cursor:String,$dir:OrderDirection!){
  repository(owner:$owner,name:$name){
    stargazers(first:100, after:$cursor, orderBy:{field:STARRED_AT, direction:$dir}) {
      pageInfo { hasNextPage endCursor }
      edges {
        starredAt
        node {
          login
          createdAt
          followers { totalCount }
          repositories(ownerAffiliations: OWNER, isFork: false) { totalCount }
        }
      }
    }
  }
}
"""


@dataclass
class StarSample:
    login: str
    starred_at: datetime
    account_created_at: datetime
    followers: int
    owned_repos: int


@dataclass
class RawStarSignals:
    owner: str
    repo: str
    fetched_at: datetime
    stargazer_count: int
    sample: list[StarSample] = field(default_factory=list)
    sampling_note: str = ""


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _fetch_page(client: GraphQLClient, target: Target, cursor: str | None, direction: str) -> dict:
    return client.query(
        _STARGAZERS_QUERY,
        {"owner": target.owner, "name": target.repo, "cursor": cursor, "dir": direction},
        ttl_seconds=3600,
    )


def _edges_to_samples(edges: list[dict]) -> list[StarSample]:
    samples = []
    for edge in edges:
        node = edge["node"]
        samples.append(
            StarSample(
                login=node["login"],
                starred_at=_parse_ts(edge["starredAt"]),
                account_created_at=_parse_ts(node["createdAt"]),
                followers=node["followers"]["totalCount"],
                owned_repos=node["repositories"]["totalCount"],
            )
        )
    return samples


def _paginate(
    client: GraphQLClient, target: Target, direction: str, max_pages: int
) -> list[StarSample]:
    samples: list[StarSample] = []
    cursor = None
    for _ in range(max_pages):
        data = _fetch_page(client, target, cursor, direction)
        conn = data["repository"]["stargazers"]
        samples.extend(_edges_to_samples(conn["edges"]))
        if not conn["pageInfo"]["hasNextPage"]:
            break
        cursor = conn["pageInfo"]["endCursor"]
    return samples


def collect_star_signals(client: GraphQLClient, target: Target) -> RawStarSignals:
    now = datetime.now(timezone.utc)
    meta = client.query(_META_QUERY, {"owner": target.owner, "name": target.repo}, ttl_seconds=900)
    repository = meta.get("repository")
    if repository is None:
        raise InputError(f"not found on GitHub: {target.slug}")
    stargazer_count = repository["stargazerCount"]

    if stargazer_count <= FULL_SCAN_STAR_CAP:
        sample = _paginate(client, target, "DESC", MAX_FULL_SCAN_PAGES + 1)
        note = f"full scan: all {len(sample)} stargazers (stargazerCount={stargazer_count})"
    else:
        recent = _paginate(client, target, "DESC", RECENT_SAMPLE_PAGES)
        earliest = _paginate(client, target, "ASC", EARLIEST_SAMPLE_PAGES)
        sample = recent + earliest
        coverage = len(sample) / stargazer_count
        note = (
            f"stratified sample: most recent {len(recent)} + earliest {len(earliest)} "
            f"of {stargazer_count} total (~{coverage:.1%} coverage; a campaign buried in "
            f"the middle of the star history would be missed by this sample)"
        )

    return RawStarSignals(
        owner=target.owner,
        repo=target.repo,
        fetched_at=now,
        stargazer_count=stargazer_count,
        sample=sample,
        sampling_note=note,
    )
