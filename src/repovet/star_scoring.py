"""S1 (fake-star / anomalous star pattern) scoring.

Method basis: CMU/NCSU "Six Million (Suspected) Fake Stars on GitHub"
(arXiv:2412.13459, ICSE'26) and its StarScout tool (github.com/hehao98/
StarScout). That tool runs two heuristics at GitHub-Archive scale: a
low-activity heuristic (throwaway accounts) and a CopyCatch lockstep
heuristic (dense bipartite cores of accounts starring many repos in
lockstep across *all of GitHub*). We can't replicate the cross-repo
lockstep heuristic in a single-repo CLI query without a full star-event
graph — this module adapts the *spirit* of both heuristics to what a
single live GraphQL query can see:

1. burst score       - is the star timeline itself anomalously bursty
                        (matches "low-activity heuristic" timing signal)
2. account quality    - what fraction of sampled starrers look like
                        throwaway accounts (zero owned repos / zero
                        followers / created within days of starring)
3. burst correlation  - are the suspicious accounts concentrated *inside*
                        the burst window specifically? This is the closest
                        single-repo proxy for "lockstep": organic virality
                        (e.g. a Hacker News front-page hit) also bursts,
                        but with real, diverse accounts; a bought campaign
                        bursts with a spike of throwaway accounts. This is
                        the strongest, most specific signal of the three.

Known false-positive risk (write this down, don't discover it in prod):
a beginner-friendly tutorial repo can genuinely attract many brand-new
GitHub accounts (their first star ever) without any fraud — but those
accounts should trickle in over time, not burst. That's exactly why
burst correlation is weighted highest, not raw account quality alone.

Known false-negative risk (found during M1 calibration, see README): we
only see an account's *current* profile, not its state at the time it
starred. An account that was a genuine throwaway a year ago but has since
built up repos/followers will no longer look suspicious to us. This is
why older campaigns are harder for us to detect than fresh ones.

Score direction matches S2: 100 = no evidence of anomalous star activity,
0 = strong evidence. Bump FORMULA_VERSION whenever weights/bands change
(text-only changes, like M2.5's English-native evidence prose, do not).

M2.5: evidence is English-native by default (`lang="en"`), with a
co-located Traditional Chinese string at every construction site
(`lang="zh"`) — see scoring.py's module docstring for the rationale.
`SubScore.name` and `pattern` stay English-only regardless of `lang`.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from repovet.star_collectors import RawStarSignals, StarSample

FORMULA_VERSION = "s1.v1"

WEIGHT_BURST = 0.25
WEIGHT_ACCOUNT_QUALITY = 0.40
WEIGHT_BURST_CORRELATION = 0.35

YOUNG_ACCOUNT_DAYS = 7
BURST_WINDOW = timedelta(hours=48)
MIN_SAMPLE_FOR_SIGNAL = 10

# (max_fraction, score) bands, checked in order; fraction = share of sample
# inside the single busiest 48h window
_BURST_BANDS = (
    (0.10, 100),
    (0.20, 85),
    (0.35, 65),
    (0.50, 45),
    (0.70, 25),
)
_BURST_FLOOR = 10  # a raw burst alone can be organic virality; never zero it out alone

_ACCOUNT_QUALITY_BANDS = (
    (0.05, 100),
    (0.15, 85),
    (0.30, 60),
    (0.50, 35),
    (0.75, 15),
)
_ACCOUNT_QUALITY_FLOOR = 5

# bands on (in-window suspicious fraction - baseline suspicious fraction)
_CORRELATION_BANDS = (
    (0.05, 100),
    (0.15, 80),
    (0.30, 55),
    (0.50, 30),
)
_CORRELATION_FLOOR = 10


@dataclass
class SubScore:
    name: str
    score: int
    evidence: str


@dataclass
class S1Result:
    formula_version: str
    overall: int
    pattern: str
    sub_scores: list[SubScore]
    sampling_note: str
    warnings: list[str] = field(default_factory=list)


def _account_flags(s: StarSample) -> tuple[bool, bool, bool]:
    zero_repo = s.owned_repos == 0
    zero_follower = s.followers == 0
    young = (s.starred_at - s.account_created_at).days <= YOUNG_ACCOUNT_DAYS
    return zero_repo, zero_follower, young


def _is_suspicious(s: StarSample) -> bool:
    return sum(_account_flags(s)) >= 2


def _band_score(value: float, bands: tuple[tuple[float, int], ...], floor: int) -> int:
    for threshold, score in bands:
        if value <= threshold:
            return score
    return floor


def score_account_quality(sample: list[StarSample], lang: str = "en") -> SubScore:
    n = len(sample)
    if n == 0:
        evidence = (
            "no starrers in the sample to evaluate (neutral score)"
            if lang != "zh"
            else "抽樣中無 star 者可供評估（預設中性分數）"
        )
        return SubScore("account quality", 70, evidence)

    suspicious = [s for s in sample if _is_suspicious(s)]
    zero_repo_n = sum(1 for s in sample if _account_flags(s)[0])
    zero_follower_n = sum(1 for s in sample if _account_flags(s)[1])
    young_n = sum(1 for s in sample if _account_flags(s)[2])
    fraction = len(suspicious) / n

    score = _band_score(fraction, _ACCOUNT_QUALITY_BANDS, _ACCOUNT_QUALITY_FLOOR)
    if lang == "zh":
        evidence = (
            f"抽樣 {n} 位 star 者中 {len(suspicious)} 位（{fraction:.0%}）符合可疑帳號特徵"
            f"（zero-repo {zero_repo_n}/{n}、zero-follower {zero_follower_n}/{n}、"
            f"建號後 {YOUNG_ACCOUNT_DAYS} 天內即 star {young_n}/{n}；需至少符合兩項才算可疑）"
        )
        if n < MIN_SAMPLE_FOR_SIGNAL:
            evidence += f"；樣本數過小（n={n}），信心較低"
    else:
        evidence = (
            f"{len(suspicious)}/{n} sampled starrers ({fraction:.0%}) match ≥2 suspicious-account "
            f"flags (zero-repo {zero_repo_n}/{n}, zero-follower {zero_follower_n}/{n}, "
            f"account created within {YOUNG_ACCOUNT_DAYS} days of starring {young_n}/{n})"
        )
        if n < MIN_SAMPLE_FOR_SIGNAL:
            evidence += f"; sample too small (n={n}), lower confidence"
    return SubScore("account quality", score, evidence)


def _max_burst_window(sample_sorted: list[StarSample]) -> tuple[int, int]:
    """Two-pointer sliding window over sorted starredAt. Returns (start_idx,
    end_idx) inclusive of the densest BURST_WINDOW-wide window."""
    n = len(sample_sorted)
    left = 0
    best = (0, 0)
    best_count = 1
    for right in range(n):
        while sample_sorted[right].starred_at - sample_sorted[left].starred_at > BURST_WINDOW:
            left += 1
        count = right - left + 1
        if count > best_count:
            best_count = count
            best = (left, right)
    return best


def score_burst(sample: list[StarSample], lang: str = "en") -> tuple[SubScore, tuple[int, int]]:
    n = len(sample)
    if n < MIN_SAMPLE_FOR_SIGNAL:
        evidence = (
            f"sample too small (n={n}) to reliably assess burst pattern"
            if lang != "zh"
            else f"樣本數過小（n={n}），無法可靠評估爆量模式"
        )
        return SubScore("star-burst timing", 70, evidence), (0, max(n - 1, 0))

    sample_sorted = sorted(sample, key=lambda s: s.starred_at)
    start, end = _max_burst_window(sample_sorted)
    window_count = end - start + 1
    fraction = window_count / n

    score = _band_score(fraction, _BURST_BANDS, _BURST_FLOOR)
    window_start = sample_sorted[start].starred_at
    window_end = sample_sorted[end].starred_at
    if lang == "zh":
        evidence = (
            f"抽樣 {n} 顆 star 中，最密集的 48 小時窗口"
            f"（{window_start.date()}~{window_end.date()}）"
            f"內集中了 {window_count} 顆（{fraction:.0%}）"
        )
    else:
        evidence = (
            f"of {n} sampled stars, the single busiest 48h window "
            f"({window_start.date()}~{window_end.date()}) contains {window_count} ({fraction:.0%})"
        )
    return SubScore("star-burst timing", score, evidence), (start, end)


def score_burst_correlation(
    sample_sorted: list[StarSample], window: tuple[int, int], lang: str = "en"
) -> SubScore:
    n = len(sample_sorted)
    start, end = window
    in_window = sample_sorted[start : end + 1]
    outside = sample_sorted[:start] + sample_sorted[end + 1 :]

    if n < MIN_SAMPLE_FOR_SIGNAL or not outside or not in_window:
        evidence = (
            "not enough sample to compare account quality inside vs outside the burst "
            "window (neutral score)"
            if lang != "zh"
            else "樣本不足以比較爆量窗口內外的帳號品質（預設中性分數）"
        )
        return SubScore("burst/account correlation", 70, evidence)

    in_fraction = sum(1 for s in in_window if _is_suspicious(s)) / len(in_window)
    baseline_fraction = sum(1 for s in outside if _is_suspicious(s)) / len(outside)
    delta = in_fraction - baseline_fraction

    score = _band_score(max(delta, 0.0), _CORRELATION_BANDS, _CORRELATION_FLOOR)
    if lang == "zh":
        evidence = (
            f"爆量窗口內可疑帳號比例 {in_fraction:.0%}，窗口外基準比例 {baseline_fraction:.0%}"
            f"（差距 {delta:+.0%}；差距越大代表爆量與可疑帳號同時發生，越像協同操作而非自然爆紅）"
        )
    else:
        evidence = (
            f"suspicious-account rate inside the burst window: {in_fraction:.0%}, "
            f"baseline outside it: {baseline_fraction:.0%} (gap {delta:+.0%}; a bigger gap "
            "means the burst and the suspicious accounts co-occur, more like coordination "
            "than organic virality)"
        )
    return SubScore("burst/account correlation", score, evidence)


_OVERWHELMING_ACCOUNT_SCORE = 20  # see below
_NO_BURST_AT_ALL_SCORE = 90  # burst_score this high means "no timing concentration at all"


def _classify_pattern(burst_score: int, account_score: int, correlation_score: int) -> str:
    if account_score < 50 and correlation_score < 50:
        return "anomalous-star-pattern"
    # Correlation compares "inside the burst window" vs "outside it" — but if
    # almost the entire sampled star history is throwaway accounts (not just
    # a narrow burst), there's no clean baseline left, so correlation weakens
    # even though account quality alone is already damning. Found during M1
    # calibration on sidetrip-ai/ici-core (93% suspicious accounts scored
    # account_score=5, but correlation only 55 since the "outside window"
    # baseline was itself ~84% suspicious). Require *some* timing
    # concentration (burst_score not maxed out) so this doesn't swallow the
    # "beginner tutorial repo, new accounts trickle in steadily over a year"
    # false-positive case, which has no burst at all.
    if account_score < _OVERWHELMING_ACCOUNT_SCORE and burst_score < _NO_BURST_AT_ALL_SCORE:
        return "anomalous-star-pattern"
    if burst_score < 50 and account_score >= 70:
        return "organic-burst"
    if account_score < 50:
        return "elevated-suspicious-accounts"
    return "clean"


def compute_s1(raw: RawStarSignals, lang: str = "en") -> S1Result:
    sample = raw.sample
    account_quality = score_account_quality(sample, lang)
    burst, window = score_burst(sample, lang)
    sample_sorted = sorted(sample, key=lambda s: s.starred_at)
    correlation = score_burst_correlation(sample_sorted, window, lang)

    overall = round(
        burst.score * WEIGHT_BURST
        + account_quality.score * WEIGHT_ACCOUNT_QUALITY
        + correlation.score * WEIGHT_BURST_CORRELATION
    )
    pattern = _classify_pattern(burst.score, account_quality.score, correlation.score)

    warnings = []
    if len(sample) < MIN_SAMPLE_FOR_SIGNAL:
        warnings.append(f"star sample too small for a confident read (n={len(sample)})")

    return S1Result(
        formula_version=FORMULA_VERSION,
        overall=overall,
        pattern=pattern,
        sub_scores=[burst, account_quality, correlation],
        sampling_note=raw.sampling_note,
        warnings=warnings,
    )
