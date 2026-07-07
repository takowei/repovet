# repovet

Developer trust check for GitHub repos before you depend on them — one-shot
CLI that scores public, re-runnable trust signals with evidence, no LLM in
the scoring path. Spec: `../research/repovet-mvp-spec-2026-07.md`.

## 狀態（2026-07-07）

M0+M1 done: CLI + S2 (zombie maintenance, formula s2.v2) + S1 (anomalous
star pattern, formula s1.v1). S2 fixed a real PR-flood confound found on
`psf/requests` during M0 (issue vs PR responsiveness now scored/weighted
separately). S1 calibrated against StarScout's own published fake-star
list (arXiv:2412.13459 / ICSE'26): n=5 small calibration set, precision
100% (2/2), recall ~67% (2/3) — see README for the known false-negative
(current-state-only account features miss older campaigns).

## 技術棧

Python 3.10+ (declared as 3.10 because that's what's actually testable in
this sandbox; bump to 3.11 once verified elsewhere), stdlib sqlite3 +
`requests`, argparse. ruff lint, pytest 測試（全 mock，不打真網路）.

## 關鍵檔案

```
src/repovet/cli.py           ← entry point, argparse, exit codes 0/2/3, runs S2+S1 per target
src/repovet/targets.py       ← gh:owner/repo parsing, batch file reading
src/repovet/github_client.py ← rate-limit-aware REST client (S2's data source)
src/repovet/graphql_client.py ← rate-limit-aware GraphQL client (S1's data source, needs token)
src/repovet/cache.py         ← sqlite response cache (~/.cache/repovet/), shared by both clients
src/repovet/collectors.py    ← S2 raw signal gathering (commits/releases/issues)
src/repovet/scoring.py       ← S2 formula (s2.v2): cadence/issue/PR/bus-factor/maintainer
src/repovet/star_collectors.py ← S1 raw signal gathering (stargazers w/ starredAt, full-scan-or-stratified)
src/repovet/star_scoring.py  ← S1 formula (s1.v1): burst/account-quality/correlation
src/repovet/output.py        ← table / --json rendering, nested `signals.s1`/`signals.s2`
tests/                       ← pytest, GitHub REST+GraphQL fully mocked via conftest.py
README.md                    ← both formulas, known limitations, calibration table, demo output
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
```

## 下一步（M2，需主對話先決定的事）

- S3 幻覺依賴（slopsquatting）+ `--reply` 是原規格 M2 範圍。
- S1 已知最大弱點＝只看帳號「現在」狀態，對舊活動campaign偵測力弱（見
  README AceDataCloud/Nexior 案例）；若要補強需要更多校準樣本或改抓帳號
  歷史特徵，成本待評估。
- 開公開 repo（對外發布）尚未做，遠端與發布仍是主對話/Root 的手。
