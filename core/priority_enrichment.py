import re
from datetime import date, datetime
from typing import Any, Iterable, Mapping

from core.deadlines import OPEN_OR_UPCOMING, classify_deadline
from core.theme_coherence import THEME_TERMS


PRIORITY_THEMES = (
    "critical_materials_circularity",
    "port_energy_hydrogen",
    "maritime_ports_logistics",
    "security_resilience_infrastructure",
    "transport_mobility_supply_chain",
    "sme_startup_ecosystem",
)

PRIORITY_THEME_LABELS = {
    "critical_materials_circularity": "Critical materials / circularity",
    "port_energy_hydrogen": "Port energy / hydrogen",
    "maritime_ports_logistics": "Maritime / ports / logistics",
    "security_resilience_infrastructure": "Security / resilience",
    "transport_mobility_supply_chain": "Transport / supply chain",
    "sme_startup_ecosystem": "SME / start-up ecosystem",
}

METADATA_FIELDS_TO_ENRICH = (
    "trl_min",
    "trl_max",
    "eligible_countries",
    "eligible_org_types",
    "consortium_required",
    "min_partners",
    "action_type",
    "budget_min_eur",
    "budget_max_eur",
    "objectives",
    "expected_impact",
)

TEXT_FIELDS = (
    "call_title",
    "topic_title",
    "description",
    "objectives",
    "expected_impact",
    "keywords",
)


def _normalise(value: Any) -> str:
    text = str(value or "").lower().replace("-", " ")
    cleaned = re.sub(r"\s+", " ", text).strip()
    return f" {cleaned} "


def _contains_term(text: str, term: str) -> bool:
    needle = _normalise(term).strip()
    if not needle:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", text) is not None


def record_text(record: Mapping[str, Any]) -> str:
    return _normalise(" ".join(str(record.get(field) or "") for field in TEXT_FIELDS))


def detect_priority_themes(record: Mapping[str, Any]) -> list[str]:
    text = record_text(record)
    matched: list[tuple[int, str]] = []
    for theme in PRIORITY_THEMES:
        terms = THEME_TERMS.get(theme, ())
        score = sum(2 if " " in term.strip() else 1 for term in terms if _contains_term(text, term))
        if score:
            matched.append((score, theme))
    return [theme for _, theme in sorted(matched, key=lambda item: (-item[0], item[1]))]


def missing_metadata_fields(record: Mapping[str, Any]) -> list[str]:
    return [field for field in METADATA_FIELDS_TO_ENRICH if not str(record.get(field) or "").strip()]


def is_priority_enrichment_candidate(
    record: Mapping[str, Any],
    *,
    today: date | datetime | None = None,
) -> bool:
    if classify_deadline(record.get("deadline_utc"), today=today) != OPEN_OR_UPCOMING:
        return False
    if not str(record.get("call_id") or "").strip():
        return False
    if not str(record.get("source_url") or "").strip():
        return False
    if not detect_priority_themes(record):
        return False
    return bool(missing_metadata_fields(record))


def priority_enrichment_score(
    record: Mapping[str, Any],
    *,
    today: date | datetime | None = None,
) -> int:
    if not is_priority_enrichment_candidate(record, today=today):
        return 0

    themes = detect_priority_themes(record)
    missing = missing_metadata_fields(record)
    description_length = len(str(record.get("description") or ""))
    expected_impact_length = len(str(record.get("expected_impact") or ""))

    score = 30
    score += min(30, len(themes) * 8)
    score += min(18, len(missing) * 2)
    if description_length >= 500:
        score += 8
    elif description_length >= 200:
        score += 5
    elif description_length < 80:
        score -= 10
    if expected_impact_length >= 150:
        score += 5
    elif expected_impact_length == 0:
        score -= 5
    if "eligible_countries" in missing or "eligible_org_types" in missing:
        score += 5
    if "consortium_required" in missing or "min_partners" in missing:
        score += 4
    return min(score, 100)


def select_priority_enrichment_records(
    records: Iterable[Mapping[str, Any]],
    *,
    limit: int = 40,
    today: date | datetime | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not is_priority_enrichment_candidate(record, today=today):
            continue
        copied = dict(record)
        copied["_priority_enrichment_score"] = priority_enrichment_score(record, today=today)
        copied["_priority_themes"] = detect_priority_themes(record)
        copied["_missing_metadata_fields"] = missing_metadata_fields(record)
        copied["_source_row_index"] = index
        candidates.append(copied)

    return sorted(
        candidates,
        key=lambda record: (
            -int(record["_priority_enrichment_score"]),
            len(record["_missing_metadata_fields"]),
            str(record.get("deadline_utc") or ""),
            str(record.get("call_id") or ""),
        ),
    )[:limit]


def priority_theme_distribution(records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = {label: 0 for label in PRIORITY_THEME_LABELS.values()}
    for record in records:
        for theme in detect_priority_themes(record):
            counts[PRIORITY_THEME_LABELS[theme]] += 1
    return {theme: count for theme, count in counts.items() if count}
