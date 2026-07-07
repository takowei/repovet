# repovet

Developer trust check for GitHub repos before you depend on them — one-shot
CLI that scores public, re-runnable trust signals with evidence, no LLM in
the scoring path. Spec: `../research/repovet-mvp-spec-2026-07.md`.

## 狀態（2026-07-07）

M0+M1+M2 done: CLI + S2 (zombie maintenance, s2.v2) + S1 (anomalous star
pattern, s1.v1) + S3 (hallucinated dependency, s3.v1) + `--reply`
(`--lang en|zh`). S1 recall miss (older campaigns) is a documented, accepted
limitation per coordinator ruling — not being fixed now. S3's biggest known
gap: PyPI has no download-count signal (pypistats API too rate-limited to
check per-dependency), and typosquat detection uses a curated ~60-name
allowlist, not a live feed. `--reply` (English) embeds the existing
Chinese-authored evidence strings verbatim — facts are legible, prose isn't
English-native; `--reply --lang zh` is the more polished of the two today.

## 技術棧

Python 3.10+ (declared as 3.10 because that's what's actually testable in
this sandbox; bump to 3.11 once verified elsewhere), stdlib sqlite3 +
`requests` + `tomli` (only on <3.11, stdlib `tomllib` covers 3.11+),
argparse. ruff lint, pytest 測試（全 mock，不打真網路）.

## 關鍵檔案

```
src/repovet/cli.py            ← entry point, argparse, exit codes 0/2/3, runs S2+S1+S3, --reply
src/repovet/targets.py        ← gh:owner/repo parsing, batch file reading
src/repovet/github_client.py  ← rate-limit-aware REST client (S2+S3's GitHub data source)
src/repovet/graphql_client.py ← rate-limit-aware GraphQL client (S1's data source, needs token)
src/repovet/registry_client.py← PyPI/npm client for S3 (no rate-limit headers on either registry)
src/repovet/cache.py          ← sqlite response cache (~/.cache/repovet/), shared by all clients
src/repovet/collectors.py     ← S2 raw signal gathering (commits/releases/issues)
src/repovet/scoring.py        ← S2 formula (s2.v2): cadence/issue/PR/bus-factor/maintainer
src/repovet/star_collectors.py← S1 raw signal gathering (stargazers w/ starredAt)
src/repovet/star_scoring.py   ← S1 formula (s1.v1): burst/account-quality/correlation
src/repovet/dependency_manifest.py   ← pyproject.toml/requirements*.txt/package.json parsers
src/repovet/dependency_collectors.py ← S3 raw signal gathering (manifest fetch + registry checks)
src/repovet/dependency_scoring.py    ← S3 formula (s3.v1): existence/typosquat/maturity
src/repovet/popular_packages.py      ← curated allowlist for S3's typosquat check
src/repovet/reply.py           ← --reply rendering (en/zh)
src/repovet/output.py          ← table / --json rendering, nested signals.s1/s2/s3
tests/                         ← pytest, all HTTP fully mocked via conftest.py (86 tests)
README.md                      ← all three formulas, limitations, calibration, demo, --reply
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
PYTHONPATH=src python3 -m repovet gh:owner/repo --reply --lang zh
```

## 下一步（M3+，需主對話先決定的事）

- S4 AI-slop 特徵是原規格最後一個里程碑（v0 只出提示不出分數，誤判風險高）。
- `--reply`（English）目前嵌入既有中文 evidence 字串——若要對外大量發文
  (HN/Reddit)，值得考慮把 evidence 語料改成英文原生（會動到已驗收的
  M0/M1 程式碼），需主對話拍板是否投資。
- 開公開 repo（對外發布）尚未做，遠端與發布仍是主對話/Root 的手。
