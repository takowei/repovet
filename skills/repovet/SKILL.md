---
name: repovet
description: >
  Trust-check a GitHub repo before depending on it. Use when the user asks
  "is this repo trustworthy / maintained / AI-slop?", pastes a GitHub URL and
  wants it vetted, or before adding a new dependency. Runs the repovet CLI
  (public, re-runnable checks — zombie maintenance, star anomalies,
  hallucinated dependencies, AI-slop hints) and reports 0-100 scores with
  evidence. Not for private repos or non-GitHub hosts.
---

# repovet — GitHub repo trust check

Wraps the `repovet` CLI: https://github.com/takowei/repovet

## Setup (once per machine)

```bash
pip install "git+https://github.com/takowei/repovet" 2>/dev/null \
  || { git clone --depth 1 https://github.com/takowei/repovet /tmp/repovet-cli && pip install /tmp/repovet-cli; }
```

If `pip install` is unavailable, run from a clone without installing:
`PYTHONPATH=/tmp/repovet-cli/src python3 -m repovet ...`

A `GITHUB_TOKEN` env var is **optional but recommended**: without it the S1
star-pattern signal is skipped and S2 runs at 60 req/hr anonymous. Never read
token files yourself — only use a token already exported in the environment.

## Usage

Target format is `gh:owner/repo` (convert pasted URLs like
`https://github.com/owner/repo` yourself).

```bash
repovet gh:owner/repo --json          # machine-readable, best for agents
repovet gh:owner/repo                 # human table view
repovet gh:owner/repo --reply         # pasteable summary for issues/HN/Reddit
repovet gh:owner/repo --lang zh       # Traditional Chinese evidence
repovet --batch targets.txt --json    # many repos, one per line
```

Exit codes: 0 = completed, 2 = bad target / repo not found, 3 = API or
network failure (often rate limit — suggest setting GITHUB_TOKEN).

## Interpreting results

Four signals, each 0-100 (higher = healthier), every sub-score comes with
evidence — quote the evidence, not just the number:

- **S2 zombie maintenance** — is anyone home? Issue responsiveness matters
  more than commit cadence; a stable, feature-complete repo can score well
  with old commits.
- **S1 star anomaly** — bursty/coordinated star patterns. Requires
  GITHUB_TOKEN; `signals.s1.status == "skipped"` without one.
- **S3 hallucinated dependencies** — declared deps that don't exist on the
  registry (slopsquatting risk). Any hit is serious; name it explicitly.
- **S4 AI-slop hints** — experimental heuristics, weakest signal. Present as
  "hints", never as a verdict on its own.

When reporting to the user: lead with an overall take (fine / caution /
avoid), then the one or two signals that drove it, with their evidence
lines. Low S2 + any S3 hit is the classic "do not depend on this" combo.
Scores are point-in-time public data, not a character judgment of the
authors — keep the framing factual.
