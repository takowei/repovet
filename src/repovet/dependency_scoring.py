"""S3 (hallucinated dependency / slopsquatting) scoring.

For every dependency declared in a supported manifest, verify it actually
exists in its registry (PyPI / npm). A dependency that doesn't exist at all
is the single most severe, most directly verifiable signal this tool has —
it's the literal slopsquatting attack surface (an LLM hallucinates an
import, someone registers that exact name with malware, the next
`pip install`/`npm install` grabs it). Existence gets the heaviest weight
and a hard cap: even one missing dependency caps the score at
EXISTENCE_CAP_IF_ANY_MISSING, regardless of how many hundred others exist —
diluting a hallucinated import across a big dependency tree shouldn't make
it look "mostly fine".

Typosquat risk only escalates a name that's edit-distance-close to a
well-known package if the package *itself* also looks fresh/low-signal
(young account, or for npm, low downloads). A real, long-established
package that happens to be name-adjacent to a popular one (e.g. npm's
`request`, a genuine 2011-era package) must not be flagged just because a
string-distance check fired — registry data always wins over string
similarity alone.

PyPI has no download-count signal: pypistats.org 429s on back-to-back
requests (verified empirically), unsuitable for checking many dependencies
in one run. This is disclosed via a warning, not silently treated as zero.

M2.5: evidence is English-native by default (`lang="en"`), with a
co-located Traditional Chinese string at every construction site
(`lang="zh"`) — see scoring.py's module docstring for the rationale.
`SubScore.name` and `pattern` stay English-only regardless of `lang`.
"""

from dataclasses import dataclass, field

from repovet.dependency_collectors import RawDependencySignals
from repovet.popular_packages import POPULAR_NPM_PACKAGES, POPULAR_PYPI_PACKAGES
from repovet.registry_client import PackageInfo

FORMULA_VERSION = "s3.v1"

WEIGHT_EXISTENCE = 0.55
WEIGHT_TYPOSQUAT = 0.30
WEIGHT_MATURITY = 0.15

MAX_TYPO_EDIT_DISTANCE = 2
YOUNG_PACKAGE_DAYS = 30
LOW_WEEKLY_DOWNLOADS = 100  # npm only, see module docstring
EXISTENCE_CAP_IF_ANY_MISSING = 40
EVIDENCE_LIST_LIMIT = 5


@dataclass
class SubScore:
    name: str
    score: int
    evidence: str


@dataclass
class S3Result:
    formula_version: str
    overall: int
    pattern: str
    sub_scores: list[SubScore]
    manifests_found: list[str]
    warnings: list[str] = field(default_factory=list)


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def _popular_list(ecosystem: str) -> list[str]:
    return POPULAR_NPM_PACKAGES if ecosystem == "npm" else POPULAR_PYPI_PACKAGES


def _closest_popular_name(pkg: PackageInfo) -> str | None:
    lname = pkg.name.lower()
    best = None
    best_dist = MAX_TYPO_EDIT_DISTANCE + 1
    for popular in _popular_list(pkg.ecosystem):
        if lname == popular.lower():
            return None  # exact match IS the popular package, not a typosquat
        d = _levenshtein(lname, popular.lower())
        if d <= MAX_TYPO_EDIT_DISTANCE and d < best_dist:
            best, best_dist = popular, d
    return best


def _is_typosquat_suspect(pkg: PackageInfo) -> str | None:
    """Registry data (age/downloads) always wins over string distance alone."""
    target = _closest_popular_name(pkg)
    if target is None:
        return None
    is_young = pkg.age_days is not None and pkg.age_days < YOUNG_PACKAGE_DAYS
    is_low_download = (
        pkg.weekly_downloads is not None and pkg.weekly_downloads < LOW_WEEKLY_DOWNLOADS
    )
    has_no_signal_at_all = pkg.age_days is None and pkg.weekly_downloads is None
    if is_young or is_low_download or has_no_signal_at_all:
        return target
    return None


def score_existence(packages: list[PackageInfo], lang: str = "en") -> SubScore:
    if not packages:
        evidence = (
            "no dependencies to check (manifest declared none)"
            if lang != "zh"
            else "無可查驗的依賴（manifest 中沒有宣告任何依賴）"
        )
        return SubScore("dependency existence", 70, evidence)

    missing = [p for p in packages if not p.exists]
    total = len(packages)
    score = round((total - len(missing)) / total * 100)
    if missing:
        score = min(score, EXISTENCE_CAP_IF_ANY_MISSING)
        names = ", ".join(p.name for p in missing[:EVIDENCE_LIST_LIMIT])
        overflow = len(missing) - EVIDENCE_LIST_LIMIT
        if lang == "zh":
            more = f"（其餘 {overflow} 個略）" if overflow > 0 else ""
            evidence = f"{total} 個依賴中 {len(missing)} 個在 registry 查無此套件：{names}{more}"
        else:
            more = f" ({overflow} more omitted)" if overflow > 0 else ""
            evidence = (
                f"{len(missing)}/{total} dependencies don't exist in their registry: {names}{more}"
            )
    else:
        evidence = (
            f"{total} 個依賴全部存在於對應 registry"
            if lang == "zh"
            else f"all {total} dependencies exist in their registry"
        )
    return SubScore("dependency existence", score, evidence)


def score_typosquat(packages: list[PackageInfo], lang: str = "en") -> SubScore:
    existing = [p for p in packages if p.exists]
    if not existing:
        evidence = (
            "no existing dependencies to compare (neutral score)"
            if lang != "zh"
            else "無存在的依賴可供比對（預設中性分數）"
        )
        return SubScore("typosquat risk", 70, evidence)

    suspects = [(p, _is_typosquat_suspect(p)) for p in existing]
    suspects = [(p, target) for p, target in suspects if target]
    fraction = len(suspects) / len(existing)
    score = max(0, min(100, round(100 - fraction * 300)))

    if suspects:
        parts = []
        for p, target in suspects[:3]:
            if lang == "zh":
                age = f"建號 {p.age_days} 天" if p.age_days is not None else "年齡未知"
                downloads = (
                    f"、週下載 {p.weekly_downloads}" if p.weekly_downloads is not None else ""
                )
                parts.append(f"{p.name}（近似 {target}，{age}{downloads}）")
            else:
                age = f"{p.age_days} days old" if p.age_days is not None else "age unknown"
                downloads = (
                    f", {p.weekly_downloads} weekly downloads"
                    if p.weekly_downloads is not None
                    else ""
                )
                parts.append(f"{p.name} (close to {target}, {age}{downloads})")
        if lang == "zh":
            evidence = (
                f"{len(existing)} 個存在依賴中 {len(suspects)} 個疑似 typosquat：{'; '.join(parts)}"
            )
        else:
            evidence = (
                f"{len(suspects)}/{len(existing)} existing dependencies look like typosquat "
                f"candidates: {'; '.join(parts)}"
            )
    else:
        evidence = (
            f"{len(existing)} 個存在依賴，未發現疑似 typosquat 命名"
            if lang == "zh"
            else f"{len(existing)} existing dependencies checked, no typosquat-like names found"
        )
    return SubScore("typosquat risk", score, evidence)


def score_maturity(packages: list[PackageInfo], lang: str = "en") -> SubScore:
    existing = [p for p in packages if p.exists]
    known_ages = [p for p in existing if p.age_days is not None]
    if not known_ages:
        evidence = (
            "couldn't determine package age for any dependency (neutral score)"
            if lang != "zh"
            else "無法取得依賴的套件年齡資訊（預設中性分數）"
        )
        return SubScore("package maturity", 70, evidence)

    young = [p for p in known_ages if p.age_days < YOUNG_PACKAGE_DAYS]
    fraction = len(young) / len(known_ages)
    score = round((1 - fraction) * 100)
    if lang == "zh":
        evidence = (
            f"{len(known_ages)} 個已知年齡依賴中 {len(young)} 個建包 <{YOUNG_PACKAGE_DAYS} 天"
            "（資訊性訊號，年輕套件不必然有問題）"
        )
    else:
        evidence = (
            f"{len(young)}/{len(known_ages)} dependencies with known age are <{YOUNG_PACKAGE_DAYS} "
            "days old (informational signal only -- a young package isn't inherently a problem)"
        )
    return SubScore("package maturity", score, evidence)


def _classify_pattern(typosquat_score: int, maturity_score: int, any_missing: bool) -> str:
    if any_missing:
        return "hallucinated-dependency"
    if typosquat_score < 60:
        return "typosquat-suspect"
    if maturity_score < 50:
        return "many-young-dependencies"
    return "clean"


def compute_s3(raw: RawDependencySignals, lang: str = "en") -> S3Result:
    packages = raw.packages
    existence = score_existence(packages, lang)
    typosquat = score_typosquat(packages, lang)
    maturity = score_maturity(packages, lang)

    overall = round(
        existence.score * WEIGHT_EXISTENCE
        + typosquat.score * WEIGHT_TYPOSQUAT
        + maturity.score * WEIGHT_MATURITY
    )
    any_missing = any(not p.exists for p in packages)
    if any_missing:
        # A perfect typosquat/maturity score must not dilute a hallucinated
        # dependency back up to "looks mostly fine" -- the cap applies to
        # the whole verdict, not just the existence sub-score alone (found
        # via test_single_hallucinated_dependency_caps_score_hard).
        overall = min(overall, EXISTENCE_CAP_IF_ANY_MISSING)
    pattern = _classify_pattern(typosquat.score, maturity.score, any_missing)

    warnings = []
    if any(p.ecosystem == "pypi" for p in packages):
        warnings.append(
            "PyPI packages carry no download-count signal (pypistats API too rate-limited)"
        )

    return S3Result(
        formula_version=FORMULA_VERSION,
        overall=overall,
        pattern=pattern,
        sub_scores=[existence, typosquat, maturity],
        manifests_found=raw.manifests_found,
        warnings=warnings,
    )
