# Case study: reproducing a known fake-star campaign, and finding it's still running

**Date:** 2026-07-07
**Tool:** [repovet](https://github.com/takowei/repovet) v0.1.0 (S1 fake-star formula `s1.v1`, S2 maintenance formula `s2.v2`)

## Why this case

`DigitalPlatDev/FreeDomain` has been independently flagged as a suspected fake-star case by multiple outlets over the past few months — [CMU's own coverage of the ICSE 2026 fake-stars research](https://www.cs.cmu.edu/news/2025/fake-github-stars), and follow-up investigative pieces citing its abnormal fork-to-star and watcher-to-star ratios (17 forks / 1,000 stars vs. Flask's 235; a 0.001 watcher-to-star ratio, ~26x lower than Flask) and a stargazer sample where 81.3% had zero followers.

We picked it specifically because it's **already corroborated by third parties** — this isn't repovet originating a fresh accusation against an unverified target. The question we wanted to answer: does an independently-built, open-source tool — using only public GitHub API data and a rule-based scoring formula (no LLM judgment) — reproduce the same conclusion? And does it turn up anything the earlier coverage missed?

## Method

Four repos, one command each, no manual tuning per target:

```
repovet gh:DigitalPlatDev/FreeDomain
repovet gh:pallets/flask
repovet gh:fastapi/fastapi
repovet gh:psf/requests
```

`s1` (fake-star signal) scores 0-100 from three sub-signals: star-burst timing concentration, stargazer account-quality flags (zero-repo / zero-follower / account age at time of starring), and whether the burst window and suspicious-account rate correlate. `s2` (maintenance-health signal) is unrelated to star patterns — commit/release cadence, issue/PR responsiveness, bus factor, and recent maintainer activity.

## Results

| Repo                        | S1 (fake-star)                  | S2 (maintenance) |
| --------------------------- | ------------------------------- | ---------------- |
| `DigitalPlatDev/FreeDomain` | **24 — anomalous-star-pattern** | 80 — healthy     |
| `pallets/flask`             | 80 — organic-burst              | 88 — healthy     |
| `fastapi/fastapi`           | 78 — clean                      | 85 — healthy     |
| `psf/requests`              | 80 — organic-burst              | 86 — healthy     |

FreeDomain's S1 evidence, verbatim from the tool's output:

- Of 500 sampled stars, the single busiest 48-hour window (**2026-07-06 ~ 2026-07-07**) contains 300 stars (60% of the sample).
- 219/500 sampled starrers (44%) match ≥2 suspicious-account flags: 241/500 zero-repo, 276/500 zero-follower, 162/500 accounts created within 7 days of starring.
- Suspicious-account rate _inside_ the burst window: 64%. Baseline _outside_ it: 13%. A +51-point gap — the burst and the suspicious accounts co-occur, which looks like coordination rather than organic virality.
- Sampling note, stated honestly by the tool itself: this is a stratified sample (most recent 300 + earliest 200 of 183,611 total stars, ~0.3% coverage) — a campaign buried in the middle of the star history could be missed by this method.

## What's new here

The prior coverage of FreeDomain (CMU's write-up, the investigative pieces) is based on data from earlier in 2026 and before. **Our scan, run today (2026-07-07), found the single largest star-burst window sitting in the last 48 hours** — meaning that whatever produced FreeDomain's star inflation didn't stop after it became a publicly documented case study. It (or something with the same signature) was still active this week.

We're not claiming to know who's behind it or why. We're reporting what the tool measured, with the sampling caveat attached, same as it does for every target.

## Why this matters more than another demo

Anyone can build a tool that outputs a scary-looking number. The bar we're holding ourselves to: every score ships with the evidence that produced it, the sampling method is disclosed (including its blind spots), and the language is "anomalous pattern," never "fraud" — that's not hedging, it's the actual epistemic status of what star-timing statistics can tell you. The four numbers above are reproducible by anyone with a GitHub token and five minutes: `pip install` the tool, or read the source.

## Limitations, stated plainly

- N=1 positive case in this write-up. This is a spot-check against a well-documented example, not a new statistical study — the calibration set used to tune the S1 formula itself is documented in the [main README](../README.md) (precision 100% / recall 67% on n=5; small-sample caveat stated there too).
- The 0.3% star-history sample means older or lower-intensity campaigns could be under-counted.
- We did not attempt to determine intent, attribution, or legal characterization — only measured patterns and reported the evidence.
