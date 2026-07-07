# repovet

Developer trust check for GitHub repos before you depend on them.

`repovet` runs a small set of public, re-runnable checks against a GitHub
repo and reports 0-100 scores **with evidence for every sub-score** — no
opaque single number, no LLM in the scoring path. Ships three signals so
far: **S2** (zombie maintenance, M0), **S1** (anomalous star pattern, M1),
**S3** (hallucinated dependency / slopsquatting, M2) — plus `--reply`, a
one-command pasteable summary for GitHub issues / HN / Reddit. See
`../research/repovet-mvp-spec-2026-07.md` for the full product spec (S4
AI-slop is the remaining future milestone).

## Install / run

```bash
cd repovet
pip install -e .
export GITHUB_TOKEN=...   # required for S1 (GraphQL has no anonymous tier)
                          # optional for S2 (60 req/hr anonymous vs 5000 req/hr)
repovet gh:psf/requests
repovet gh:psf/requests --json
repovet gh:psf/requests --reply             # pasteable English summary
repovet gh:psf/requests --reply --lang zh   # pasteable Traditional Chinese summary
repovet --batch targets.txt --json          # one target per line, '#' comments allowed
```

Without an install, you can also run it as `PYTHONPATH=src python3 -m repovet gh:owner/repo`.

Without `GITHUB_TOKEN`, S2 still runs (anonymous REST) but S1 is skipped
entirely — `signals.s1.status == "skipped"` in `--json`, clearly marked in
the table view too.

**Gotcha**: `repovet` reads `GITHUB_TOKEN` from the process environment, not
from any file. If you keep your token in a secrets file and `source` it into
your shell, that alone does **not** make it visible to `repovet` (or any
other subprocess) unless the variable is actually exported — sourcing a
file just sets a shell variable. If `repovet` warns "no GITHUB_TOKEN set"
right after you sourced your secrets file, run `export GITHUB_TOKEN` (no
value needed if it's already set in your shell) before invoking `repovet`.

## Exit codes (pipeline-friendly by design)

| Code | Meaning                                                                  |
| ---- | ------------------------------------------------------------------------ |
| 0    | Completed normally                                                       |
| 2    | Input error (bad target, repo not found, bad batch file)                 |
| 3    | API/network failure (rate limit, connection error, unexpected API error) |

In `--batch` mode the exit code reflects the _worst_ status across all
targets (3 beats 2 beats 0). The top-level exit code is governed by **S2
only** — if S2 succeeds but S1 fails or is skipped, the record is still
`"status": "ok"` overall; S1's own outcome is visible at
`signals.s1.status` for anything reading the JSON that cares.

## S2 — zombie maintenance scoring (formula `s2.v2`)

**Philosophy**: a mature, feature-complete project can have a stale last
commit/release and still be perfectly healthy — as long as issues still get
a response and _someone_ still shows up occasionally. Raw commit/release
cadence is therefore only 20% of the score; issue responsiveness (30%) and
recent maintainer activity (25%) do the real work of telling "stable" apart
from "abandoned". Bus factor (15%) is a standing risk factor, not a verdict.

**v1 → v2 change**: issue and PR responsiveness are now scored (and
weighted) separately, instead of one blended "issue/PR" score. On popular
repos (e.g. `psf/requests`) the combined sample was dominated by low-effort
driveby PRs that maintainers correctly ignore, which dragged the score down
even on a genuinely healthy repo — found during the M0 demo, fixed before
this could mislead anyone. Real user-filed issues keep the larger weight
(30%); PR non-response is weaker/more ambiguous and gets a smaller one (10%).

Five sub-scores, each 0-100, weighted into an overall score:

| Sub-score                  | Weight | What it measures                                                                                                                                                 |
| -------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| commit/release cadence     | 20%    | Days since the more recent of last commit / last release, banded 100→10 (never hits 0 — silence alone isn't proof of death)                                      |
| issue responsiveness       | 30%    | Of the most recent N (default 15) issues+PRs _old enough to have had a fair chance at a response_ (≥2 days), filtered to plain issues: response fraction + speed |
| PR responsiveness          | 10%    | Same, filtered to PRs only. Evidence explicitly flags this may include unreviewed/low-quality driveby PRs — non-response here is a weaker signal                 |
| bus factor                 | 15%    | Commits in the last year, min. number of contributors needed to cover ≥50% of them                                                                               |
| maintainer 90-day activity | 25%    | Days since the most recent of {commit, release, any issue/PR first response} — a genuine "is anyone touching this at all" proxy                                  |

`pattern` label (driven off **issue** responsiveness specifically, not the
old PR-diluted blend): `healthy` / `stable-low-frequency` ("finished
software", not abandoned) / `anomalous-stalled` (the actual zombie signal) /
`mixed`.

## S1 — anomalous star pattern scoring (formula `s1.v1`)

**Method basis**: CMU/NCSU "Six Million (Suspected) Fake Stars on GitHub"
(arXiv:2412.13459, ICSE'26) and its [StarScout](https://github.com/hehao98/StarScout)
tool. StarScout runs at GitHub-Archive scale with two heuristics: a
low-activity heuristic (throwaway accounts) and a CopyCatch lockstep
heuristic (dense bipartite cores of accounts starring many repos together
across _all of GitHub_). A single-repo CLI query can't replicate the
cross-repo lockstep heuristic (it needs a full star-event graph), so S1
adapts the spirit of both to what one live GraphQL query can see:

| Sub-score                 | Weight | What it measures                                                                                                          |
| ------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------- |
| star-burst timing         | 25%    | Max fraction of the sample inside any single 48h window — is the timeline itself anomalously bursty                       |
| account quality           | 40%    | Fraction of sampled starrers matching ≥2 of {zero owned repos, zero followers, account created within 7 days of the star} |
| burst/account correlation | 35%    | Are suspicious accounts concentrated _inside_ the burst window specifically, vs the rest of the sample (the baseline)?    |

Score direction matches S2: 100 = no evidence of anomalous star activity, 0
= strong evidence. Language is always "anomalous star pattern", never
"fraud"/"fake" as a factual claim about the repo owner.

**Why burst/account correlation is weighted highest**: a beginner-friendly
tutorial repo can genuinely attract many brand-new GitHub accounts (their
first star ever) without any fraud — but real new-user adoption trickles in
over time, it doesn't burst. A Hacker-News-style organic viral spike _does_
burst, but with real, diverse accounts. A bought campaign does both at
once: burst timing _and_ throwaway accounts, concentrated together. That
co-occurrence is the most specific signal we have.

**Sampling strategy** (always stated in the evidence, never silent):

- `stargazerCount <= 2000`: full scan, no blind spots.
- above that: stratified sample of the most recent ~300 stars (DESC) +
  earliest ~200 (ASC). Catches "recent/ongoing campaign" and "inflated at
  launch" patterns. **A campaign buried in the middle of a large repo's
  star history will be missed** — this is a real, disclosed blind spot, not
  hidden in the score.

### Calibration (small sample, directional only — see caveat below)

Positives from StarScout's own published Jan-2025 low-activity results
([gist](https://gist.github.com/heathdutton/e09693d7f8b18df8df3061a57105b112),
derived from the ICSE'26 paper's tool). Most of the originally-flagged repos
in that dataset have since been removed by GitHub (spam takedowns); these
three still existed and were small enough for a **full scan** (no sampling
blind spot):

| Repo                            | Published fake-star % | repovet S1 result               | Verdict       |
| ------------------------------- | --------------------- | ------------------------------- | ------------- |
| `sidetrip-ai/ici-core`          | 82%                   | 28/100 `anomalous-star-pattern` | **hit**       |
| `pEgaSuShoOFtR/APP-HyperDefi`   | 85%                   | 40/100 `anomalous-star-pattern` | **hit**       |
| `AceDataCloud/Nexior`           | 81%                   | 90/100 `clean`                  | **miss (FN)** |
| `psf/requests` (known healthy)  | n/a                   | 80/100 `organic-burst`          | correct (TN)  |
| `pallets/flask` (known healthy) | n/a                   | 80/100 `organic-burst`          | correct (TN)  |

**n=5 (3 positive, 2 negative): precision = 2/2 = 100%, recall = 2/3 ≈ 67%.**
This is far too small a sample to claim a real precision/recall number —
treat it as directional evidence the method works, not a validated
statistic. Every other originally-flagged repo we tried to use for
calibration had already been deleted by GitHub, which is itself informative
(GitHub's own abuse detection got there first) but shrank our usable set.

**Why the miss happened (found during calibration, not hidden)**: we only
see a starrer's _current_ account profile (current repo count, current
follower count), not their state at the time they starred. `Nexior`'s
campaign was mid-2024; those accounts may have built up real activity since
then and no longer look like throwaways today. `ici-core`'s campaign was
March-May 2025, recent enough that the accounts still look exactly like what
they were. **S1 is structurally weaker at detecting older campaigns** — this
is the single biggest known limitation of the current formula.

### Known limitations

1. **Current-state-only account features** (see miss above) — the biggest
   one. Detection strength decays as a campaign ages.
2. **Stratified sampling blind spot** on large repos (see sampling strategy
   above) — a mid-history campaign on a 50k+ star repo would be invisible
   to the default sample.
3. **Burst/account correlation weakens when almost the whole sample is
   fake**, not just a narrow window (no clean "baseline" left to compare
   against). Fixed with a floor rule (`account quality < 20` alone is
   enough to call it anomalous, provided there's _some_ timing
   concentration — see `_classify_pattern` in `star_scoring.py`), but it's
   a real edge case worth knowing about.
4. **No cross-repo lockstep detection.** The paper's strongest signal (the
   same group of accounts coordinating across _many_ repos) needs a
   full star-event graph we don't have in a single-repo query.

## S3 — hallucinated dependency scoring (formula `s3.v1`)

**What it checks**: for every dependency declared in a supported manifest,
does it actually exist in its registry? A dependency that doesn't exist at
all is the single most severe, most directly verifiable signal repovet has
— it's the literal slopsquatting attack surface (an LLM hallucinates an
import name, someone registers that exact name with malware, the next
`pip install`/`npm install` grabs it).

**Supported ecosystems (MVP, explicitly limited)**: Python
(`pyproject.toml`'s PEP 621 `dependencies`/`optional-dependencies` +
`requirements*.txt`) and JS (`package.json`'s `dependencies`/
`devDependencies`). Any other ecosystem (Go, Rust, Ruby, ...) reports S3 as
`skipped: no supported dependency manifest found` rather than guessing.

| Sub-score            | Weight | What it measures                                                                                                                                                                                    |
| -------------------- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| dependency existence | 55%    | Fraction of declared dependencies that exist in their registry. **Capped hard** at 40/100 if even one is missing — a hallucinated import shouldn't be diluted away by a big healthy dependency tree |
| typosquat risk       | 30%    | Fraction of existing dependencies that are name-adjacent (edit distance ≤2) to a well-known package **and** themselves look fresh/low-signal (age <30 days or, npm only, <100 weekly downloads)     |
| package maturity     | 15%    | Informational: fraction of dependencies younger than 30 days. Being young isn't inherently bad, so this is the lightest-weighted sub-score                                                          |

**Typosquat detection always defers to registry data over string
similarity.** A real, long-established package that happens to be
name-adjacent to a popular one (e.g. npm's `request`, a genuine 2011-era
package) must never be flagged just because an edit-distance check fired —
only a name-adjacent package that is _also_ young or low-download gets
flagged. Verified with a unit test using exactly this case.

**Known limitations**:

- The "well-known package" list is a curated ~60-name-per-ecosystem
  allowlist (`popular_packages.py`), not a live top-N-by-downloads feed —
  squatting against a popular name that isn't on this list won't be caught.
- **PyPI packages carry no download-count signal at all.** pypistats.org
  (the obvious source) 429s on back-to-back requests — verified
  empirically, unsuitable for checking N dependencies in one run. This is
  disclosed via a warning in the output, not silently treated as zero.
- `requirements.txt` `-r other.txt` includes are not followed recursively.

### S3 demo

Against a real healthy repo (`psf/requests`, `--json` excerpt):

```
S3 hallucinated dependency: 100/100 [clean]
  dependency existence   100/100  12 個依賴全部存在於對應 registry
  typosquat risk         100/100  12 個存在依賴，未發現疑似 typosquat 命名
  package maturity       100/100  12 個已知年齡依賴中 0 個建包 <30 天
  manifests: pyproject.toml, requirements-dev.txt
  warning: PyPI packages carry no download-count signal (pypistats API too rate-limited)
```

Against a self-made fixture (3 real deps checked live against PyPI +
1 confirmed-nonexistent name + 1 synthetic typosquat-style entry — see
"why synthetic" note below):

```
overall: 40/100  pattern: hallucinated-dependency  formula: s3.v1
  dependency existence      40/100  5 個依賴中 1 個在 registry 查無此套件：zzz-repovet-hallucinated-fixture-test-9f3k2
  typosquat risk            25/100  4 個存在依賴中 1 個疑似 typosquat：reqeusts（近似 requests，建號 3 天）
  package maturity          75/100  4 個已知年齡依賴中 1 個建包 <30 天
```

_Why one entry is synthetic_: finding a **real, currently-existing,
young/low-download package name that's also a live typosquat attempt**
would mean deliberately hunting for and then naming an actual attack
package in a public demo — not something we're going to do. The
nonexistent-package half of the fixture (the more severe, heavier-weighted
signal) is 100% real: `zzz-repovet-hallucinated-fixture-test-9f3k2` was
verified live against the PyPI JSON API (HTTP 404) before use. The
typosquat half uses a hand-constructed `PackageInfo` fed straight into
`compute_s3` — the scoring logic itself doesn't care whether the data came
from a live lookup or not, and this is disclosed here rather than implied
to be a live finding.

## `--reply`

`repovet gh:owner/repo --reply` renders a neutral, evidence-first summary
meant to be pasted as-is into a GitHub issue, Hacker News, or Reddit thread
answering "is this repo legit?" — three signal scores, the 3-5
lowest-scoring (most decision-relevant) sub-scores as evidence, a one-line
method/limitations statement, and a tool signature. Never uses accusatory
language ("anomalous pattern", never "fraud"/"fake") — that discipline
lives in the underlying evidence strings already; `--reply` only assembles
what's already there, it doesn't generate new claims. `--reply --lang zh`
renders the same content in Traditional Chinese.

**Known scope limit, disclosed rather than hidden**: S1/S2/S3's evidence
strings were authored in Chinese from day one (M0/M1), before an English
default `--reply` was a known requirement. The English reply reuses those
evidence strings verbatim — the underlying facts (counts, package/repo
names, dates, percentages) are legible in either language, but the
connecting prose is Chinese. The **Chinese** `--reply --lang zh` output is
therefore the more natively polished of the two today. Rewriting the
evidence corpus to be English-native would touch already-accepted M0/M1
code across three modules — a real, reasonable follow-up, not done here
without a separate go-ahead, since `--reply` (English) being used for wide
public posting is where this would actually matter.

## Testing

```bash
python3 -m pytest
```

All 86 tests mock the GitHub REST/GraphQL APIs and the PyPI/npm registry
APIs (`FakeSession`/`FakeResponse` in `tests/conftest.py`) — no real
network calls in the test suite.

## Demo (real API calls, 2026-07-07)

```
$ repovet gh:psf/requests
S2: 86/100 [healthy]       (issue-response 100 real issues answered fast;
                             PR-response 15 — driveby PR flood, correctly de-weighted)
S1: 80/100 [organic-burst] (burst is the repo's 2011 launch day; accounts
                             in that window are cleaner than baseline, not fakes)
S3: 100/100 [clean]        (12 deps, all exist, no typosquat suspects)

$ repovet gh:sidetrip-ai/ici-core   # AI-assistant repo, known 82% fake stars
S2: 20/100 [anomalous-stalled]      (0/7 issues answered, no activity in 429 days)
S1: 28/100 [anomalous-star-pattern] (93% of stargazers are throwaway accounts,
                                     concentrated in a 3-day burst)
S3: skipped (no supported dependency manifest found)

$ repovet gh:moment/moment   # explicitly "maintenance mode" since ~2020
S2: 80/100 [stable-low-frequency]  (stale cadence, but still triaged)
```

See `--reply` above for the full pasteable-summary demo output (both
languages), and the S3 section above for the self-made fixture demo. The
three original S2 demo repos (psf/requests, request/request, moment/moment)
are unchanged in spirit from M0 — see git history for request/request's
full numbers.
