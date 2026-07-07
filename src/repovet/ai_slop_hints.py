"""S4 (AI-slop feature hints) -- v0.

Per spec, this signal is deliberately NOT a 0-100 score with a pattern
verdict like S1/S2/S3. README template similarity, commit-message
homogeneity, and scaffolding similarity are all things completely
legitimate, human-run projects exhibit too -- this is the highest
false-positive-risk signal in the whole tool. v0 therefore only emits
hints: an observation + a raw number + an explicit "this also happens in
normal repos" disclaimer, per hint. No aggregation, no verdict, and never
included in `--reply` unless `--include-s4` is passed.

M2.5-consistent: hint text is English-native by default (`lang="en"`) with
a co-located Traditional Chinese string at each construction site
(`lang="zh"`), same pattern as S1/S2/S3's evidence strings. `Hint.name`
stays English-only (a stable identifier, not prose).
"""

import re
import statistics
from dataclasses import dataclass, field

from repovet.ai_slop_collectors import RawSlopSignals

FORMULA_VERSION = "s4.v0"  # "v0" is part of the version on purpose: hints-only, not scored

# Badge-hosting domains / URL substrings seen in practice (shields.io,
# pepy.tech, readthedocs, codecov, travis, GitHub Actions status badges).
_BADGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*(?:badge|shields\.io)[^)]*\)", re.IGNORECASE)
_EMOJI_RE = re.compile(
    "[\U0001f300-\U0001faff\U00002600-\U000026ff\U00002700-\U000027bf\U0001f000-\U0001f2ff]"
)
_AI_BOILERPLATE_PHRASES = (
    "this project aims to",
    "feel free to contribute",
    "in this repository, you will find",
    "contributions are welcome",
    "this is a comprehensive solution",
    "we welcome contributions",
    "don't hesitate to open an issue",
    "star this repo if you find it useful",
    "this repository contains",
)

COMMIT_UNIFORMITY_MIN_SAMPLE = 8
SCAFFOLD_MARKERS = ("LICENSE", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md")


@dataclass
class Hint:
    name: str
    observation: str
    raw_value: float | int
    disclaimer: str


@dataclass
class S4Result:
    formula_version: str
    hints: list[Hint] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _hint_readme_badges(readme: str, lang: str) -> Hint:
    count = len(_BADGE_RE.findall(readme))
    if lang == "zh":
        observation = f"README 中找到 {count} 個 badge 樣式圖片（shields.io/badge 類服務）"
        disclaimer = (
            "成熟、維護良好的專案也常見大量 badge（CI/覆蓋率/授權）——數量本身不代表任何事。"
        )
    else:
        observation = f"{count} shields.io/badge-style images found in the README"
        disclaimer = (
            "Badge walls are common in professionally maintained projects too "
            "(CI/coverage/license badges) -- count alone is not evidence of anything."
        )
    return Hint("readme badge density", observation, count, disclaimer)


def _lines_outside_code_fences(text: str) -> list[str]:
    """Skip lines inside ``` fenced code blocks -- a shell comment like
    `# 1. Clone the repository` inside a setup snippet is not a markdown
    header. Found via a real README (sidetrip-ai/ici-core) during the S4
    demo: naive '#'-counting inflated its header count to 60, most of them
    bash comments in code fences, not actual section headers."""
    lines = []
    in_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append(line)
    return lines


def _hint_readme_emoji_headers(readme: str, lang: str) -> Hint:
    headers = [line for line in _lines_outside_code_fences(readme) if line.strip().startswith("#")]
    emoji_headers = [h for h in headers if _EMOJI_RE.search(h)]
    fraction = len(emoji_headers) / len(headers) if headers else 0.0
    if lang == "zh":
        observation = f"{len(headers)} 個標題中 {len(emoji_headers)} 個含 emoji（{fraction:.0%}）"
        disclaimer = "許多人類作者也偏好用 emoji 裝飾標題——這是常見風格選擇，不代表任何事。"
    else:
        observation = (
            f"{len(emoji_headers)}/{len(headers)} section headers contain an emoji ({fraction:.0%})"
        )
        disclaimer = (
            "Many human-written READMEs use emoji headers by stylistic choice -- "
            "this is common decoration, not a sign of anything."
        )
    return Hint("README emoji-header density", observation, round(fraction, 2), disclaimer)


def _hint_readme_boilerplate(readme: str, lang: str) -> Hint:
    text = readme.lower()
    hits = [p for p in _AI_BOILERPLATE_PHRASES if p in text]
    examples = f": {', '.join(hits[:5])}" if hits else ""
    if lang == "zh":
        observation = f"{len(hits)}/{len(_AI_BOILERPLATE_PHRASES)} 個常見模板句式命中{examples}"
        disclaimer = (
            "這些句式也普遍出現在正常、由人類撰寫的 README 中"
            "（包括來自 cookiecutter 等範本工具）——命中本身不能證明任何事。"
        )
    else:
        observation = (
            f"{len(hits)}/{len(_AI_BOILERPLATE_PHRASES)} common templated phrases found{examples}"
        )
        disclaimer = (
            "These phrases are generic boilerplate seen across many legitimately "
            "human-written READMEs (including from templates like cookiecutter) -- "
            "presence alone proves nothing."
        )
    return Hint("README boilerplate phrase hits", observation, len(hits), disclaimer)


def _hint_commit_message_uniformity(commit_messages: list[str], lang: str) -> Hint | None:
    if len(commit_messages) < COMMIT_UNIFORMITY_MIN_SAMPLE:
        return None
    lengths = [len(m) for m in commit_messages]
    mean_len = statistics.mean(lengths)
    stdev_len = statistics.pstdev(lengths)
    cv = (stdev_len / mean_len) if mean_len else 0.0
    n = len(commit_messages)
    if lang == "zh":
        observation = f"近 {n} 筆 commit 訊息長度變異係數：{cv:.2f}（數值越低代表越均質）"
        disclaimer = (
            "變異低也可能只是團隊嚴格遵守 commit 規範"
            "（如 Conventional Commits）——不必然代表 AI 產出。"
        )
    else:
        observation = (
            f"coefficient of variation of {n} recent commit message lengths: {cv:.2f} "
            "(lower = more uniform)"
        )
        disclaimer = (
            "Low variation can also come from a disciplined team following a strict "
            "commit convention (e.g. Conventional Commits) -- this alone doesn't "
            "indicate AI-generated commits."
        )
    return Hint("commit message length uniformity", observation, round(cv, 3), disclaimer)


def _hint_scaffolding_markers(
    root_entries: list[str], github_entries: list[str], lang: str
) -> Hint:
    present = [m for m in SCAFFOLD_MARKERS if m in root_entries]
    if any("ISSUE_TEMPLATE" in e for e in github_entries):
        present.append("issue templates")
    if "workflows" in github_entries:
        present.append(".github/workflows")

    if lang == "zh":
        listing = "、".join(present) if present else "無"
        observation = f"找到 {len(present)} 項常見專業專案骨架標記：{listing}"
        disclaimer = (
            "完整骨架（LICENSE/CONTRIBUTING/CI/issue 範本）對認真的專案是完全正常的，"
            "本身不代表任何事；只有搭配 S2 顯示的低齡/低活躍度才值得留意。"
        )
    else:
        listing = ", ".join(present) if present else "none"
        observation = (
            f"{len(present)} common professional-project scaffolding markers present: {listing}"
        )
        disclaimer = (
            "A fully scaffolded repo (LICENSE/CONTRIBUTING/CI/issue templates) is "
            "completely normal for serious projects -- it is not itself a sign of "
            "anything; it's only worth cross-referencing against how young/inactive "
            "the repo otherwise looks (see S2)."
        )
    return Hint("repo scaffolding completeness", observation, len(present), disclaimer)


def compute_s4(raw: RawSlopSignals, lang: str = "en") -> S4Result:
    hints: list[Hint] = []
    warnings: list[str] = []

    if raw.readme_text is not None:
        hints.append(_hint_readme_badges(raw.readme_text, lang))
        hints.append(_hint_readme_emoji_headers(raw.readme_text, lang))
        hints.append(_hint_readme_boilerplate(raw.readme_text, lang))
    else:
        warnings.append("no README found, README-based hints skipped")

    commit_hint = _hint_commit_message_uniformity(raw.commit_messages, lang)
    if commit_hint:
        hints.append(commit_hint)
    elif raw.commit_messages:
        warnings.append(
            f"too few commits sampled (n={len(raw.commit_messages)}) for the commit-uniformity hint"
        )

    hints.append(_hint_scaffolding_markers(raw.root_entries, raw.github_dir_entries, lang))

    return S4Result(formula_version=FORMULA_VERSION, hints=hints, warnings=warnings)
