# Adopting the repovet watchlist workflow (opt-in, self-hosted)

This lets **your own repo** get a periodic repovet trust-check report on a
list of dependencies/repos **you** choose, posted as a new issue in **your
own repo**. repovet never touches a repo unless that repo's maintainer
added this file themselves -- there is no scheduled or automatic path that
reaches into a repo that didn't opt in.

## 1. Add a watchlist file to your repo

`.repovet/watchlist.txt` (one target per line, same format as `--batch`):

```
gh:owner/repo-a
gh:owner/repo-b
```

## 2. Add a workflow that calls the reusable one

`.github/workflows/repovet-watchlist.yml` in **your** repo:

```yaml
name: repovet watchlist

on:
  schedule:
    - cron: "0 6 * * 1" # every Monday 06:00 UTC -- pick your own cadence
  workflow_dispatch: {} # lets you also trigger it manually

jobs:
  watchlist:
    uses: takowei/repovet/.github/workflows/reusable-watchlist.yml@main
    with:
      watchlist_path: ".repovet/watchlist.txt"
      lang: "en" # or "zh"
    permissions:
      contents: read
      issues: write
```

That's it. GitHub runs this using **your repo's own** Action-scoped
`GITHUB_TOKEN` (auto-injected, no secret to configure) -- results are
posted as a new issue in your repo, nowhere else. Nothing here posts to
the repos listed in your watchlist; it only _reads_ public data about them
and reports back to you.

## Why this design (and not "scan any repo automatically")

A bot that comments on arbitrary repos it wasn't invited into is spam and
gets rate-limited/blocked by GitHub quickly (see Snyk/Socket's own
opt-in-only comment policies). repovet's automation surface is
deliberately limited to two opt-in paths:

1. **`/repovet-check gh:owner/repo` in an issue comment on
   `takowei/repovet` itself** -- the reply goes back to that same issue in
   that same repo, never to `owner/repo`. See the main README's
   "Automation / bot" section.
2. **This reusable watchlist workflow** -- only runs where a maintainer
   explicitly added it to their own repo, over their own chosen targets,
   posting to their own repo.

There is no third path. If you want repovet to comment inside a _different_
repo's issues or PRs automatically, that repo's maintainer needs to add
one of the above to their own repo -- repovet will not do it unprompted.
