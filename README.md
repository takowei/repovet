# repovet

Developer trust check for GitHub repos before you depend on them.

`repovet` runs a small set of public, re-runnable checks against a GitHub
repo and reports a 0-100 score **with evidence for every sub-score** — no
opaque single number, no LLM in the scoring path. M0 ships one signal: **S2,
zombie maintenance detection**. See `../research/repovet-mvp-spec-2026-07.md`
for the full product spec (S1 fake-star, S3 hallucinated deps, S4 AI-slop are
future milestones).

## Install / run

```bash
cd repovet
pip install -e .
export GITHUB_TOKEN=...   # optional but recommended (60 req/hr anonymous vs 5000 req/hr)
repovet gh:psf/requests
repovet gh:psf/requests --json
repovet --batch targets.txt --json     # one target per line, '#' comments allowed
```

Without an install, you can also run it as `PYTHONPATH=src python3 -m repovet gh:owner/repo`.

## Exit codes (pipeline-friendly by design)

| Code | Meaning                                                                  |
| ---- | ------------------------------------------------------------------------ |
| 0    | Completed normally                                                       |
| 2    | Input error (bad target, repo not found, bad batch file)                 |
| 3    | API/network failure (rate limit, connection error, unexpected API error) |

In `--batch` mode the exit code reflects the _worst_ status across all
targets (3 beats 2 beats 0), so a caller can tell "retry me" from "fix your
input" without parsing the JSON body.

## S2 — zombie maintenance scoring (formula `s2.v1`)

**Philosophy**: a mature, feature-complete project can have a stale last
commit/release and still be perfectly healthy — as long as issues still get
a response and _someone_ still shows up occasionally. Raw commit/release
cadence is therefore only 20% of the score; issue/PR responsiveness (40%)
and recent maintainer activity (25%) do the real work of telling "stable" apart
from "abandoned". Bus factor (15%) is a standing risk factor, not a verdict —
plenty of good solo-maintained repos exist, so `bus factor = 1` costs points
but never zeroes the score.

Four sub-scores, each 0-100, weighted into an overall score:

| Sub-score                  | Weight | What it measures                                                                                                                                                      |
| -------------------------- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| commit/release cadence     | 20%    | Days since the more recent of last commit / last release, banded 100→10 (never hits 0 — silence alone isn't proof of death)                                           |
| issue/PR responsiveness    | 40%    | Of the most recent N (default 15) issues/PRs _old enough to have had a fair chance at a response_ (≥2 days), what fraction got a first comment, and how fast (median) |
| bus factor                 | 15%    | Commits in the last year, min. number of contributors needed to cover ≥50% of them                                                                                    |
| maintainer 90-day activity | 25%    | Days since the most recent of {commit, release, any issue/PR first response} — a genuine "is anyone touching this at all" proxy                                       |

Overall = weighted sum, rounded, 0-100. `pattern` label:

- **healthy**: responsive + active maintainer + good cadence
- **stable-low-frequency**: responsive + active maintainer, but stale cadence — "finished software", not abandoned
- **anomalous-stalled**: unresponsive AND no recent maintainer activity — the actual zombie signal
- **mixed**: doesn't cleanly fit either bucket

Thresholds/weights are fixed constants in `src/repovet/scoring.py`, not
tuned per repo. `--json` output includes `formula_version` so past output
stays auditable against the formula that produced it.

## Known limitations (read before trusting a low score)

1. **PR-flood confound.** Issue/PR responsiveness is sampled from the most
   recent N issues+PRs combined. On popular repos (e.g. `psf/requests`)
   this sample can be dominated by low-effort/automated driveby PRs that
   maintainers correctly ignore — this drags the score down even though the
   repo is genuinely healthy. The evidence string now reports how many of
   the sampled items were PRs so you can judge this yourself; we don't yet
   score issues and PRs separately (that's a reasonable M1 follow-up).
2. **"Response" doesn't distinguish humans from bots.** A repo whose only
   activity is a bot auto-commenting "this project is in maintenance mode"
   on every PR (e.g. `moment/moment`) scores as responsive. We think that's
   still meaningfully different from true abandonment (someone/something is
   actively triaging), but it is not verified human maintainer engagement.
3. **"Maintainer" isn't verified.** Activity is "any commit, release, or
   issue/PR first response by anyone" — not filtered to actual repo
   collaborators, since that requires elevated API scopes many tokens don't
   have. This is a stand-in for "is this project touched by anyone," not
   literally "is the maintainer active."
4. **Commit sampling is capped.** Bus factor and cadence only look back 365
   days, at most ~300 commits (3 pages × 100). Very high-commit-volume repos
   will under-count total annual commits, though contributor proportions
   should still be roughly representative.
5. **Releases via GitHub Releases API only.** Repos that tag versions in git
   without using GitHub's Releases feature (common on older projects) will
   show "no release record" even if they do ship versions.

## Testing

```bash
python3 -m pytest
```

All 31 tests mock the GitHub API (`FakeSession`/`FakeResponse` in
`tests/conftest.py`) — no real network calls in the test suite.

## Demo (real API calls, 2026-07-07)

```
$ repovet gh:psf/requests
Overall S2: 65/100 [mixed]
  cadence 100, issue-response 27 (13/15 sampled were PRs, spam-flood confound), bus-factor 60, maintainer 100

$ repovet gh:request/request     # deprecated npm HTTP client, last commit 2024-08
Overall S2: 30/100 [anomalous-stalled]
  cadence 35, issue-response 27 (median 9.5 days, still mostly unanswered), bus-factor 50, maintainer 20

$ repovet gh:moment/moment       # explicitly "maintenance mode" since ~2020
Overall S2: 80/100 [stable-low-frequency]
  cadence 35 (last commit 2024-08), issue-response 100 (auto-triaged), bus-factor 50, maintainer 100
```
