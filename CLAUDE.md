# repovet

Developer trust check for GitHub repos before you depend on them — one-shot
CLI that scores public, re-runnable trust signals with evidence, no LLM in
the scoring path. Spec: `../research/repovet-mvp-spec-2026-07.md`.

## 狀態（2026-07-09）

M4 done: GitHub Action automation layer on top of the M0-M3 engine — an
opt-in `/repovet-check` issue-comment bot in this repo
(`.github/workflows/issue-comment-bot.yml` → `bot_cli.py` → `bot.py`) and a
reusable `workflow_call` watchlist workflow other repos can adopt into
their own repo (`.github/workflows/reusable-watchlist.yml`, doc in
`docs/reusable-watchlist-workflow.md`). Both paths only ever post inside
the repo that invoked them — see README "Automation / bot" for the
full safety design (never comments on a repo that didn't opt in, uses
only the Action-scoped `GITHUB_TOKEN`, never a personal PAT). 17 new
tests (120 total).

## 狀態（2026-07-07）

M0+M1+M2+M2.5+M3 done: CLI + S2 (zombie maintenance, s2.v2) + S1 (anomalous
star pattern, s1.v1) + S3 (hallucinated dependency, s3.v1) + S4 (AI-slop
hints, v0, hints-only per spec) + `--reply` (`--lang en|zh`, now fully
native in both — M2.5 fixed the Chinese-evidence-embedded-in-English-reply
bug the coordinator flagged as a hard blocker). S1 recall miss (older
campaigns) is a documented, accepted limitation per coordinator ruling —
not being fixed. S4's own demo showed honest weak-to-no discriminating
power on the one pair tested (only commit-message uniformity pointed
weakly in the expected direction) — reported as-is, not tuned to look
better, per explicit instruction that this is an acceptable v0 outcome.

## 技術棧

Python 3.10+ (declared as 3.10 because that's what's actually testable in
this sandbox; bump to 3.11 once verified elsewhere), stdlib sqlite3 +
`requests` + `tomli` (only on <3.11, stdlib `tomllib` covers 3.11+),
argparse. ruff lint, pytest 測試（全 mock，不打真網路）.

## 關鍵檔案

```
src/repovet/cli.py            ← entry point, argparse, exit codes 0/2/3, runs S2+S1+S3+S4, --reply
src/repovet/targets.py        ← gh:owner/repo parsing, batch file reading
src/repovet/github_client.py  ← rate-limit-aware REST client (S2/S3/S4's GitHub data source)
src/repovet/graphql_client.py ← rate-limit-aware GraphQL client (S1's data source, needs token)
src/repovet/registry_client.py← PyPI/npm client for S3 (no rate-limit headers on either registry)
src/repovet/cache.py          ← sqlite response cache (~/.cache/repovet/), shared by all clients
src/repovet/collectors.py     ← S2 raw signal gathering (commits/releases/issues)
src/repovet/scoring.py        ← S2 formula (s2.v2): cadence/issue/PR/bus-factor/maintainer; en/zh evidence
src/repovet/star_collectors.py← S1 raw signal gathering (stargazers w/ starredAt)
src/repovet/star_scoring.py   ← S1 formula (s1.v1): burst/account-quality/correlation; en/zh evidence
src/repovet/dependency_manifest.py   ← pyproject.toml/requirements*.txt/package.json parsers
src/repovet/dependency_collectors.py ← S3 raw signal gathering (manifest fetch + registry checks)
src/repovet/dependency_scoring.py    ← S3 formula (s3.v1): existence/typosquat/maturity; en/zh evidence
src/repovet/popular_packages.py      ← curated allowlist for S3's typosquat check
src/repovet/ai_slop_collectors.py    ← S4 raw signal gathering (README/commits/dir listings)
src/repovet/ai_slop_hints.py         ← S4 (v0, hints only, no score/pattern); en/zh observations
src/repovet/reply.py           ← --reply rendering (en/zh, fully native since M2.5), --include-s4
src/repovet/output.py          ← table / --json rendering, nested signals.s1/s2/s3/s4
src/repovet/bot.py             ← M4: /repovet-check command parsing + comment-posting, opt-in only
src/repovet/bot_cli.py         ← M4: entry point the issue-comment-bot workflow invokes
.github/workflows/issue-comment-bot.yml     ← M4: opt-in trigger #1, this repo's issue comments
.github/workflows/reusable-watchlist.yml    ← M4: opt-in trigger #2, workflow_call for other repos
docs/reusable-watchlist-workflow.md         ← M4: copy-paste adoption guide for other repos
tests/                         ← pytest, all HTTP fully mocked via conftest.py (120 tests)
README.md                      ← all four signals, limitations, calibration, demo, --reply, bot, M2.5 note
```

## 目錄結構

```
src/repovet/  ← 主程式碼
tests/        ← pytest 測試
CLAUDE.md     ← 本文件
README.md     ← 對外文件（公式、限制、demo、校準）
```

## 常用指令

```bash
python3 -m pytest
ruff check src tests
ruff format src tests
PYTHONPATH=src python3 -m repovet gh:owner/repo
PYTHONPATH=src python3 -m repovet gh:owner/repo --lang zh
PYTHONPATH=src python3 -m repovet gh:owner/repo --reply --include-s4
```

## 語言設計慣例（M2.5 立下的模式，之後加訊號要沿用）

每個 `score_*`/hint 產生函式吃 `lang: str = "en"`，en/zh 兩版文字在**同一個
構造點並列**（不拆檔案），避免未來改事實只改一種語言、另一種漂移。
`SubScore.name`／`Hint.name`／`pattern` 永遠英文（穩定識別碼，不本地化）。

## 下一步（M3 後，需主對話先決定的事）

- S1 已知最大弱點（只看帳號現在狀態）維持 documented limitation，不修。
- S1 的 `sampling_note` 欄位仍只有英文（M2.5 沒動到，屬遺留小缺口，已在
  README 揭露）。
- 開公開 repo（對外發布）尚未做，遠端與發布仍是主對話/Root 的手。
- S4 v0 鑑別力弱（見 README「honest result」段）——是否投資做得更準
  （例如擴大 README 語料、換更好的 baseline 比較對象）需主對話評估
  投資報酬，目前就照 v0 定位（提示非判決）交付。
