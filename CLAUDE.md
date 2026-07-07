# repovet

Developer trust check for GitHub repos before you depend on them — one-shot
CLI that scores public, re-runnable trust signals with evidence, no LLM in
the scoring path. Spec: `../research/repovet-mvp-spec-2026-07.md`.

## 狀態（2026-07-07）

M0 done: CLI skeleton + S2 (zombie maintenance) signal. Real-repo demo run
against `psf/requests` / `request/request` / `moment/moment` — see README
"Known limitations" for two confounds found during that run (PR-flood
dilution, bot-vs-human "response").

## 技術棧

Python 3.10+ (declared as 3.10 because that's what's actually testable in
this sandbox; bump to 3.11 once verified elsewhere), stdlib sqlite3 +
`requests`, argparse. ruff lint, pytest 測試（全 mock，不打真網路）.

## 關鍵檔案

```
src/repovet/cli.py          ← entry point, argparse, exit codes 0/2/3
src/repovet/targets.py      ← gh:owner/repo parsing, batch file reading
src/repovet/github_client.py ← rate-limit-aware REST client (cache + budget check)
src/repovet/cache.py        ← sqlite response cache (~/.cache/repovet/)
src/repovet/collectors.py   ← raw signal gathering (commits/releases/issues)
src/repovet/scoring.py      ← S2 formula (constants + sub-scores), formula_version
src/repovet/output.py       ← table / --json rendering
tests/                      ← pytest, GitHub API fully mocked via conftest.py
README.md                   ← formula explanation + known limitations + demo output
```

## 目錄結構

```
src/repovet/  ← 主程式碼
tests/        ← pytest 測試
CLAUDE.md     ← 本文件
README.md     ← 對外文件（公式、限制、demo）
```

## 常用指令

```bash
python3 -m pytest
ruff check src tests
ruff format src tests
PYTHONPATH=src python3 -m repovet gh:owner/repo
```

## 下一步（M1，需主對話先決定的事）

- S1 假 star 偵測：需要 GraphQL（stargazers with timestamps REST 拿不到時間戳），
  待決定用哪個 GitHub 帳號的 PAT、以及要不要現在就衝校準集。
- 開公開 repo（對外發布）尚未做，遠端與發布仍是主對話/Root 的手。
- PR-flood confound（見 README）值得在 M1 一併解決：issue vs PR 分開評分。
