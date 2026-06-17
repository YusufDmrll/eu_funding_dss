import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.deadlines import OPEN_OR_UPCOMING, classify_deadline, parse_deadline  # noqa: E402
from scripts.audit_dataset import audit_dataset  # noqa: E402
from scripts.expand_dataset_from_eu_api import CSV_COLUMNS  # noqa: E402


RECOMMENDED_PATH = PROJECT_ROOT / "data" / "imports" / "eu_calls_recommended_expansion.csv"
EXPANSION_LOG_PATH = PROJECT_ROOT / "data" / "evaluation_outputs" / "eu_dataset_expansion_log.json"
CURATED_PATH = PROJECT_ROOT / "data" / "imports" / "calls_seed_clean.csv"
OUTPUT_PATH = PROJECT_ROOT / "data" / "imports" / "eu_calls_promotion_candidates.csv"
REVIEW_LOG_PATH = PROJECT_ROOT / "data" / "evaluation_outputs" / "eu_calls_promotion_review_log.json"

MAX_CANDIDATES = 50
MIN_PROMOTION_SCORE = 65

THEME_WEIGHTS = {
    "maritime_port_logistics": 12,
    "critical_materials_circularity": 11,
    "hydrogen_green_energy": 11,
    "transport_mobility_supply_chain": 10,
    "security_resilience_infrastructure": 9,
    "digital_infrastructure_ai": 5,
    "sme_startup_scaleup": 5,
}

CORE_THEMES = {
    "maritime_port_logistics",
    "critical_materials_circularity",
    "hydrogen_green_energy",
    "transport_mobility_supply_chain",
    "security_resilience_infrastructure",
}

INDUSTRY_LINK_TERMS = (
    "port",
    "maritime",
    "shipping",
    "vessel",
    "logistics",
    "transport",
    "mobility",
    "supply chain",
    "energy",
    "hydrogen",
    "renewable",
    "battery",
    "raw material",
    "recycling",
    "circular",
    "security",
    "critical infrastructure",
    "resilience",
    "industrial",
    "industry",
    "manufacturing",
    "factory",
    "freight",
)

OFF_THEME_TERMS = (
    "healthcare",
    "health research",
    "disease",
    "clinical",
    "patient",
    "rare diseases",
    "cultural heritage",
    "cultural tourism",
    "creative industries",
    "agriculture",
    "agrobiodiversity",
    "farm2fork",
    "food and nutrition",
    "biomedical",
)

OFF_THEME_TITLE_TERMS = (
    "agriculture",
    "farmer",
    "farmers",
    "forestry",
    "food",
    "seafood",
    "biodiversity",
    "nature positive",
    "social cohesion",
    "health",
    "disease",
    "cancer",
    "clinical",
    "cultural",
    "heritage",
    "tourism",
    "democracy",
    "human rights",
    "social transformation",
)

LOW_VALUE_TITLE_PATTERNS = (
    "support for dissemination events",
    "conference support",
    "access to research infrastructure services",
)

TITLE_PRIORITY_TERMS = (
    "maritime",
    "port",
    "harbour",
    "shipping",
    "vessel",
    "logistics",
    "freight",
    "transport",
    "mobility",
    "supply chain",
    "hydrogen",
    "renewable",
    "energy",
    "battery",
    "raw material",
    "recycling",
    "circular",
    "critical infrastructure",
    "cybersecurity",
    "security",
    "disaster",
    "emergency",
    "multi hazard",
    "climate resilience",
    "data centre",
    "cloud infrastructure",
    "industrial",
    "manufacturing",
    "factory",
    "ccus",
    "carbon capture",
    "wastewater",
    "photovoltaic",
    "solar",
    "renewable fuel",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def _normalize_text(value: Any) -> str:
    text = str(value or "").lower().replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def _record_text(record: dict[str, Any]) -> str:
    return _normalize_text(
        " ".join(
            str(record.get(field) or "")
            for field in ("call_title", "topic_title", "description", "objectives", "expected_impact", "keywords")
        )
    )


def _title_tokens(title: Any) -> set[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "for",
        "in",
        "of",
        "on",
        "the",
        "to",
        "towards",
        "through",
        "with",
        "eu",
        "european",
        "horizon",
        "partnership",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _normalize_text(title))
        if len(token) > 2 and token not in stopwords
    }


def title_similarity(left: Any, right: Any) -> float:
    left_text = _normalize_text(left)
    right_text = _normalize_text(right)
    if not left_text or not right_text:
        return 0.0

    left_tokens = _title_tokens(left_text)
    right_tokens = _title_tokens(right_text)
    union = left_tokens | right_tokens
    jaccard = (len(left_tokens & right_tokens) / len(union)) if union else 0.0
    sequence = SequenceMatcher(None, left_text, right_text).ratio()
    return max(jaccard, sequence)


def find_nearest_curated_title(
    record: dict[str, Any],
    curated_records: Iterable[dict[str, Any]],
) -> tuple[float, str, str]:
    best_score = 0.0
    best_id = ""
    best_title = ""
    for curated in curated_records:
        score = title_similarity(record.get("call_title"), curated.get("call_title"))
        if score > best_score:
            best_score = score
            best_id = str(curated.get("call_id") or "")
            best_title = str(curated.get("call_title") or "")
    return best_score, best_id, best_title


def _missing_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in CSV_COLUMNS if not str(record.get(field) or "").strip()]


def _future_deadline_score(value: Any, today: date) -> tuple[int, int | None]:
    if classify_deadline(value, today=today) != OPEN_OR_UPCOMING:
        return 0, None
    parsed = parse_deadline(value)
    if parsed is None:
        return 0, None
    days_remaining = (parsed.date() - today).days
    if days_remaining >= 45:
        return 10, days_remaining
    if days_remaining >= 14:
        return 7, days_remaining
    return 4, days_remaining


def _scope_quality_score(record: dict[str, Any]) -> int:
    description_length = len(str(record.get("description") or "").strip())
    objectives_length = len(str(record.get("objectives") or "").strip())
    if description_length >= 500:
        score = 10
    elif description_length >= 250:
        score = 8
    elif description_length >= 100:
        score = 5
    elif description_length >= 40:
        score = 2
    else:
        score = 0
    if objectives_length >= 150:
        score += 2
    return min(score, 12)


def _title_clarity_score(record: dict[str, Any]) -> int:
    title = str(record.get("call_title") or "").strip()
    call_id = str(record.get("call_id") or "").strip()
    if not title or title.upper() == call_id.upper():
        return 0
    score = 3
    if 20 <= len(title) <= 220:
        score += 2
    if len(_title_tokens(title)) >= 4:
        score += 2
    return min(score, 7)


def review_record(
    record: dict[str, Any],
    expansion_review: dict[str, Any],
    curated_records: Iterable[dict[str, Any]],
    *,
    today: date | None = None,
) -> dict[str, Any]:
    reference_date = today or date.today()
    matched_themes = list(expansion_review.get("matched_themes") or [])
    theme_score = int(expansion_review.get("theme_score") or 0)
    text = _record_text(record)
    title_text = _normalize_text(record.get("call_title"))
    has_core_theme = bool(CORE_THEMES.intersection(matched_themes))
    has_industry_link = any(term in text for term in INDUSTRY_LINK_TERMS)

    theme_points = 0
    for theme in matched_themes:
        weight = THEME_WEIGHTS.get(theme, 0)
        if theme in {"digital_infrastructure_ai", "sme_startup_scaleup"} and not has_industry_link:
            weight = 1
        theme_points += weight
    theme_points = min(theme_points, 32) + min(8, theme_score // 2)

    deadline_points, days_remaining = _future_deadline_score(record.get("deadline_utc"), reference_date)
    scope_points = _scope_quality_score(record)
    source_points = 5 if str(record.get("source_url") or "").startswith("https://") else 0
    action_points = 5 if str(record.get("action_type") or "").strip() else 0
    impact_points = 8 if len(str(record.get("expected_impact") or "").strip()) >= 100 else 3 if record.get("expected_impact") else 0
    title_points = _title_clarity_score(record)

    duplicate_similarity, duplicate_id, duplicate_title = find_nearest_curated_title(record, curated_records)
    if duplicate_similarity >= 0.90:
        duplicate_points = 0
    elif duplicate_similarity >= 0.78:
        duplicate_points = 3
    else:
        duplicate_points = 8

    penalties: list[tuple[str, int]] = []
    only_broad_themes = bool(matched_themes) and set(matched_themes).issubset(
        {"digital_infrastructure_ai", "sme_startup_scaleup"}
    )
    if only_broad_themes and not has_industry_link:
        penalties.append(("Only broad AI/digital or SME ecosystem signals were detected", 22))

    off_theme_hits = [term for term in OFF_THEME_TERMS if term in text]
    if off_theme_hits and not has_core_theme:
        penalties.append((f"The topic is primarily outside Gillis focus ({off_theme_hits[0]})", 18))

    title_off_theme_hits = [term for term in OFF_THEME_TITLE_TERMS if term in title_text]
    if title_off_theme_hits:
        penalties.append((f"The title indicates an off-theme domain ({title_off_theme_hits[0]})", 28))

    low_value_title_hits = [term for term in LOW_VALUE_TITLE_PATTERNS if term in title_text]
    if low_value_title_hits:
        penalties.append(("The topic is primarily a dissemination or event-support action", 18))

    title_has_priority_signal = any(term in title_text for term in TITLE_PRIORITY_TERMS)
    if has_core_theme and not title_has_priority_signal:
        penalties.append(("Priority-theme signals appear mainly in broad scope text rather than the topic title", 18))

    if duplicate_similarity >= 0.90:
        penalties.append(("The title is very similar to an existing curated topic", 20))
    elif duplicate_similarity >= 0.78:
        penalties.append(("The title may overlap with an existing curated topic", 8))

    if record.get("call_title", "").strip().upper() == record.get("call_id", "").strip().upper():
        penalties.append(("The API title is not descriptive enough for client-facing use", 10))

    if deadline_points == 0:
        penalties.append(("The deadline is not currently actionable", 30))

    raw_score = (
        theme_points
        + deadline_points
        + scope_points
        + source_points
        + action_points
        + impact_points
        + title_points
        + duplicate_points
    )
    final_score = max(0, min(100, raw_score - sum(value for _, value in penalties)))

    reasons = []
    priority_themes = [theme for theme in matched_themes if theme in CORE_THEMES]
    if priority_themes:
        reasons.append("Strong alignment with " + ", ".join(theme.replace("_", " ") for theme in priority_themes[:2]))
    elif has_industry_link:
        reasons.append("Digital or SME innovation is linked to an industrial Gillis use case")
    if scope_points >= 10:
        reasons.append("The official topic provides a detailed scope and objectives")
    if impact_points == 8:
        reasons.append("Expected outcomes or impact are sufficiently described")
    if days_remaining is not None and days_remaining >= 45:
        reasons.append("The deadline leaves practical review time")

    cautions = [reason for reason, _ in penalties]
    missing = _missing_fields(record)
    for field in (
        "trl_min",
        "trl_max",
        "eligible_countries",
        "eligible_org_types",
        "consortium_required",
        "min_partners",
    ):
        if field in missing:
            caution = "TRL, eligibility, and consortium metadata require manual verification"
            if caution not in cautions:
                cautions.append(caution)
            break
    if not record.get("expected_impact"):
        cautions.append("Expected impact text is missing and should be checked in the official topic")

    return {
        "record": record,
        "call_id": record.get("call_id", ""),
        "title": record.get("call_title", ""),
        "promotion_readiness_score": final_score,
        "matched_themes": matched_themes,
        "reason_for_selection": "; ".join(reasons) if reasons else "Useful metadata quality but thematic fit requires closer review",
        "missing_metadata_fields": missing,
        "caution_notes": cautions,
        "score_components": {
            "theme_relevance": theme_points,
            "deadline": deadline_points,
            "scope_quality": scope_points,
            "source_url": source_points,
            "action_type": action_points,
            "expected_impact": impact_points,
            "title_clarity": title_points,
            "duplicate_safety": duplicate_points,
            "penalties": {reason: value for reason, value in penalties},
        },
        "nearest_curated_match": {
            "similarity": round(duplicate_similarity, 3),
            "call_id": duplicate_id,
            "title": duplicate_title,
        },
        "days_until_deadline": days_remaining,
        "theme_score_from_expansion": theme_score,
        "hold_reasons": [reason for reason, _ in penalties],
    }


def select_promotion_candidates(
    reviewed: Iterable[dict[str, Any]],
    *,
    limit: int = MAX_CANDIDATES,
    minimum_score: int = MIN_PROMOTION_SCORE,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ordered = sorted(
        reviewed,
        key=lambda item: (
            -item["promotion_readiness_score"],
            -(item.get("theme_score_from_expansion") or 0),
            item.get("days_until_deadline") if item.get("days_until_deadline") is not None else 10**9,
            item["call_id"],
        ),
    )
    selected = [item for item in ordered if item["promotion_readiness_score"] >= minimum_score][:limit]
    selected_ids = {item["call_id"] for item in selected}
    held_back = [item for item in ordered if item["call_id"] not in selected_ids]
    return selected, held_back


def _atomic_write_csv(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in CSV_COLUMNS})
    os.replace(temporary, path)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def _held_back_summary(held_back: list[dict[str, Any]]) -> dict[str, Any]:
    reasons: Counter[str] = Counter()
    for item in held_back:
        if item["promotion_readiness_score"] < MIN_PROMOTION_SCORE:
            reasons["Promotion-readiness score below the quality threshold"] += 1
        for reason in item.get("hold_reasons") or []:
            reasons[reason] += 1

    examples = []
    for item in sorted(held_back, key=lambda entry: (entry["promotion_readiness_score"], entry["call_id"]))[:12]:
        examples.append(
            {
                "call_id": item["call_id"],
                "title": item["title"],
                "promotion_readiness_score": item["promotion_readiness_score"],
                "matched_themes": item["matched_themes"],
                "reasons": item.get("hold_reasons")
                or ["Promotion-readiness score below the quality threshold"],
            }
        )
    return {
        "count": len(held_back),
        "common_reasons": dict(reasons.most_common()),
        "examples": examples,
    }


def build_review() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    recommended = _read_csv(RECOMMENDED_PATH)
    curated = _read_csv(CURATED_PATH)
    expansion_log = json.loads(EXPANSION_LOG_PATH.read_text(encoding="utf-8"))
    expansion_by_id = {
        item["call_id"]: item for item in expansion_log.get("recommended_review", [])
    }

    reviewed = [
        review_record(record, expansion_by_id.get(record["call_id"], {}), curated)
        for record in recommended
    ]
    selected, held_back = select_promotion_candidates(reviewed)
    _atomic_write_csv(OUTPUT_PATH, [item["record"] for item in selected])

    audit = audit_dataset(OUTPUT_PATH)
    selected_themes = Counter(theme for item in selected for theme in item["matched_themes"])
    missing_fields = Counter(field for item in selected for field in item["missing_metadata_fields"])

    log = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_files": {
            "recommended_expansion": str(RECOMMENDED_PATH.relative_to(PROJECT_ROOT)),
            "expansion_log": str(EXPANSION_LOG_PATH.relative_to(PROJECT_ROOT)),
            "curated_dataset": str(CURATED_PATH.relative_to(PROJECT_ROOT)),
        },
        "selection_policy": {
            "maximum_candidates": MAX_CANDIDATES,
            "minimum_promotion_readiness_score": MIN_PROMOTION_SCORE,
            "principle": "Prioritise strong Gillis-theme relevance and usable official metadata; penalise broad tag-only and off-theme matches.",
        },
        "counts": {
            "recommended_records_reviewed": len(recommended),
            "selected_for_promotion": len(selected),
            "held_back": len(held_back),
        },
        "top_selected_themes": dict(selected_themes.most_common()),
        "selected_missing_metadata": dict(missing_fields.most_common()),
        "selected_records": [
            {
                key: value
                for key, value in item.items()
                if key != "record" and key != "hold_reasons"
            }
            for item in selected
        ],
        "held_back": _held_back_summary(held_back),
        "candidate_audit": {
            "total_rows": audit["total_rows"],
            "counts": audit["counts"],
        },
        "output_file": str(OUTPUT_PATH.relative_to(PROJECT_ROOT)),
        "safety_note": "The curated CSV and SQLite database were not modified by this review process.",
    }
    _atomic_write_json(REVIEW_LOG_PATH, log)
    return selected, log


def main() -> int:
    selected, log = build_review()
    print("EU expansion promotion review")
    print(f"Recommended records reviewed: {log['counts']['recommended_records_reviewed']}")
    print(f"Selected for promotion candidates: {len(selected)}")
    print(f"Held back: {log['counts']['held_back']}")
    print(f"Top selected themes: {log['top_selected_themes']}")
    print(f"Candidate CSV: {OUTPUT_PATH}")
    print(f"Review log: {REVIEW_LOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
