import argparse
import csv
import html
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.deadlines import (  # noqa: E402
    EXPIRED,
    INVALID_DEADLINE,
    OPEN_OR_UPCOMING,
    UNKNOWN_DEADLINE,
    classify_deadline,
)


SEARCH_API_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
API_KEY = "SEDIA"
HORIZON_EUROPE_ID = "43108390"

CURATED_CSV_PATH = PROJECT_ROOT / "data" / "imports" / "calls_seed_clean.csv"
RAW_STAGING_PATH = PROJECT_ROOT / "data" / "imports" / "eu_calls_raw_staging.csv"
RECOMMENDED_PATH = PROJECT_ROOT / "data" / "imports" / "eu_calls_recommended_expansion.csv"
LOG_PATH = PROJECT_ROOT / "data" / "evaluation_outputs" / "eu_dataset_expansion_log.json"

CSV_COLUMNS = [
    "call_id",
    "program",
    "pillar",
    "cluster",
    "call_title",
    "topic_title",
    "description",
    "objectives",
    "expected_impact",
    "action_type",
    "deadline_utc",
    "budget_min_eur",
    "budget_max_eur",
    "trl_min",
    "trl_max",
    "eligible_countries",
    "eligible_org_types",
    "consortium_required",
    "min_partners",
    "keywords",
    "source_url",
    "source_last_checked_utc",
]

THEME_KEYWORDS = {
    "maritime_port_logistics": (
        "maritime",
        "port",
        "ports",
        "shipping",
        "ship",
        "ships",
        "vessel",
        "vessels",
        "terminal",
        "logistics",
        "freight",
        "waterborne",
        "inland waterway",
    ),
    "hydrogen_green_energy": (
        "hydrogen",
        "renewable energy",
        "renewable energies",
        "green energy",
        "energy transition",
        "clean energy",
        "decarbonisation",
        "decarbonization",
        "electrification",
        "offshore wind",
        "wind energy",
        "solar energy",
        "energy storage",
        "shore power",
    ),
    "critical_materials_circularity": (
        "critical raw materials",
        "strategic raw materials",
        "raw materials",
        "battery",
        "batteries",
        "recycling",
        "circular economy",
        "circularity",
        "secondary raw materials",
        "resource efficiency",
        "waste recovery",
    ),
    "security_resilience_infrastructure": (
        "security",
        "cybersecurity",
        "critical infrastructure",
        "infrastructure resilience",
        "resilience",
        "disaster resilience",
        "civil protection",
        "border security",
        "crisis management",
    ),
    "digital_infrastructure_ai": (
        "digital infrastructure",
        "artificial intelligence",
        "ai",
        "data space",
        "data spaces",
        "automation",
        "digital twin",
        "cloud",
        "edge computing",
        "5g",
        "6g",
        "robotics",
    ),
    "sme_startup_scaleup": (
        "sme",
        "smes",
        "startup",
        "start-up",
        "scale-up",
        "scaleup",
        "entrepreneurship",
        "innovation ecosystem",
        "market uptake",
        "commercialisation",
        "commercialization",
    ),
    "transport_mobility_supply_chain": (
        "transport",
        "mobility",
        "supply chain",
        "supply chains",
        "multimodal",
        "rail",
        "road transport",
        "aviation",
        "logistics",
        "freight",
        "urban mobility",
    ),
}

MIN_THEME_GROUP_SCORE = 2


class ExpansionError(RuntimeError):
    pass


class _HTMLTextExtractor(HTMLParser):
    BLOCK_TAGS = {"br", "div", "h1", "h2", "h3", "h4", "h5", "li", "p", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        lines = []
        for line in "".join(self.parts).splitlines():
            cleaned = re.sub(r"\s+", " ", html.unescape(line)).strip()
            if cleaned:
                lines.append(cleaned)
        return "\n".join(lines)


def _first(value: Any, default: Any = "") -> Any:
    if isinstance(value, list):
        return value[0] if value else default
    return default if value is None else value


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(_first(value, "") or "")).strip()


def _plain_text(value: Any) -> str:
    raw = str(_first(value, "") or "")
    if not raw:
        return ""
    parser = _HTMLTextExtractor()
    parser.feed(raw)
    parser.close()
    return parser.text()


def _heading_key(line: str) -> str | None:
    normalized = re.sub(r"[^a-z ]", "", line.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    headings = {
        "expected outcome": "expected_outcome",
        "expected outcomes": "expected_outcome",
        "expected impact": "expected_impact",
        "expected impacts": "expected_impact",
        "objective": "objectives",
        "objectives": "objectives",
        "specific objective": "objectives",
        "scope": "scope",
        "cross cutting priorities": "stop",
        "general conditions": "stop",
        "destination": "stop",
    }
    return headings.get(normalized)


def extract_topic_sections(description_html: Any) -> dict[str, str]:
    full_text = _plain_text(description_html)
    sections: dict[str, list[str]] = {}
    current = "intro"

    for line in full_text.splitlines():
        heading = _heading_key(line)
        if heading:
            current = heading
            sections.setdefault(current, [])
            continue
        if current != "stop":
            sections.setdefault(current, []).append(line)

    def joined(name: str) -> str:
        return " ".join(sections.get(name, [])).strip()

    expected = joined("expected_outcome") or joined("expected_impact")
    scope = joined("scope")
    objectives = joined("objectives") or scope
    description = scope or full_text.replace("\n", " ")
    return {
        "description": re.sub(r"\s+", " ", description).strip(),
        "objectives": re.sub(r"\s+", " ", objectives).strip(),
        "expected_impact": re.sub(r"\s+", " ", expected).strip(),
    }


def _parse_portal_datetime(value: Any) -> datetime | None:
    text = _clean_text(value)
    if not text:
        return None

    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass

    for date_format in ("%d %B %Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, date_format).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _format_utc(parsed: datetime) -> str:
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json_value(value: Any, default: Any) -> Any:
    raw = _first(value, "")
    if isinstance(raw, (dict, list)):
        return raw
    if not raw:
        return default
    try:
        return json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def select_deadline(metadata: dict[str, Any], today: date | None = None) -> str:
    candidates: list[datetime] = []
    deadline_values = metadata.get("deadlineDate") or []
    if not isinstance(deadline_values, list):
        deadline_values = [deadline_values]
    for value in deadline_values:
        parsed = _parse_portal_datetime(value)
        if parsed:
            candidates.append(parsed)

    for action in _load_json_value(metadata.get("actions"), []):
        if not isinstance(action, dict):
            continue
        for value in action.get("deadlineDates") or []:
            parsed = _parse_portal_datetime(value)
            if parsed:
                candidates.append(parsed)

    if not candidates:
        return ""

    reference_date = today or date.today()
    upcoming = [candidate for candidate in candidates if candidate.date() >= reference_date]
    selected = min(upcoming) if upcoming else max(candidates)
    return _format_utc(selected)


def _programme_structure(call_id: str) -> tuple[str, str]:
    match = re.match(r"HORIZON-CL([1-6])-", call_id.upper())
    if match:
        cluster_number = match.group(1)
        return "Pillar II", f"Cluster {cluster_number}"
    if call_id.upper().startswith(("HORIZON-ERC", "HORIZON-MSCA", "HORIZON-INFRA")):
        return "Pillar I", ""
    if call_id.upper().startswith(("HORIZON-EIC", "HORIZON-EIE")):
        return "Pillar III", ""
    if call_id.upper().startswith("HORIZON-MISS"):
        return "Pillar II", "EU Missions"
    return "", ""


def _action_type(metadata: dict[str, Any]) -> str:
    raw = _clean_text(metadata.get("typesOfAction"))
    if not raw:
        actions = _load_json_value(metadata.get("actions"), [])
        if actions and isinstance(actions[0], dict):
            types = actions[0].get("types") or []
            if types and isinstance(types[0], dict):
                raw = _clean_text(types[0].get("typeOfAction"))

    upper = raw.upper()
    if "RESEARCH AND INNOVATION" in upper or "HORIZON-RIA" in upper:
        return "RIA"
    if "INNOVATION ACTION" in upper or "HORIZON-IA" in upper:
        return "IA"
    if "COORDINATION AND SUPPORT" in upper or "HORIZON-CSA" in upper:
        return "CSA"
    return raw


def _budget_range(metadata: dict[str, Any], call_id: str) -> tuple[str, str]:
    overview = _load_json_value(metadata.get("budgetOverview"), {})
    topic_map = overview.get("budgetTopicActionMap", {}) if isinstance(overview, dict) else {}
    matches: list[dict[str, Any]] = []
    for entries in topic_map.values() if isinstance(topic_map, dict) else []:
        for entry in entries or []:
            if isinstance(entry, dict) and str(entry.get("action", "")).upper().startswith(call_id.upper()):
                matches.append(entry)

    if not matches:
        return "", ""

    minimums = [entry.get("minContribution") for entry in matches if entry.get("minContribution") not in [None, ""]]
    maximums = [entry.get("maxContribution") for entry in matches if entry.get("maxContribution") not in [None, ""]]
    minimum = min(float(value) for value in minimums) if minimums else ""
    maximum = max(float(value) for value in maximums) if maximums else ""
    return minimum, maximum


def _metadata_terms(metadata: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for field in ("keywords", "tags", "crossCuttingPriorities"):
        value = metadata.get(field) or []
        values = value if isinstance(value, list) else [value]
        for item in values:
            cleaned = _clean_text(item)
            if cleaned and not cleaned.upper().startswith("HORIZON-") and cleaned not in terms:
                terms.append(cleaned)
    return terms


def normalize_api_result(
    api_result: dict[str, Any],
    *,
    checked_at: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    metadata = api_result.get("metadata") or {}
    call_id = _clean_text(metadata.get("identifier"))
    title = _clean_text(metadata.get("title")) or _clean_text(api_result.get("summary"))
    sections = extract_topic_sections(metadata.get("descriptionByte"))
    pillar, cluster = _programme_structure(call_id)
    budget_min, budget_max = _budget_range(metadata, call_id)
    source_url = _clean_text(metadata.get("url")) or _clean_text(metadata.get("esST_URL"))
    checked = checked_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    record = {column: "" for column in CSV_COLUMNS}
    record.update(
        {
            "call_id": call_id,
            "program": "Horizon Europe",
            "pillar": pillar,
            "cluster": cluster,
            # Existing application records use the topic title as the primary call title.
            "call_title": title,
            "topic_title": title,
            "description": sections["description"],
            "objectives": sections["objectives"],
            "expected_impact": sections["expected_impact"],
            "action_type": _action_type(metadata),
            "deadline_utc": select_deadline(metadata, today=today),
            "budget_min_eur": budget_min,
            "budget_max_eur": budget_max,
            "keywords": "; ".join(_metadata_terms(metadata)),
            "source_url": source_url,
            "source_last_checked_utc": checked,
        }
    )
    return record


def description_quality(record: dict[str, Any]) -> int:
    score = 0
    if len(str(record.get("description") or "")) >= 200:
        score += 2
    elif len(str(record.get("description") or "")) >= 60:
        score += 1
    if len(str(record.get("objectives") or "")) >= 100:
        score += 1
    if len(str(record.get("expected_impact") or "")) >= 100:
        score += 1
    return score


def source_completeness(record: dict[str, Any]) -> int:
    important_fields = (
        "call_id",
        "call_title",
        "description",
        "objectives",
        "expected_impact",
        "action_type",
        "deadline_utc",
        "source_url",
    )
    return sum(bool(str(record.get(field) or "").strip()) for field in important_fields)


def deduplicate_records(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    selected: dict[str, dict[str, Any]] = {}
    duplicates = 0
    for record in records:
        call_id = str(record.get("call_id") or "").strip()
        if not call_id:
            continue
        existing = selected.get(call_id)
        if existing is None:
            selected[call_id] = record
            continue
        duplicates += 1
        candidate_rank = (description_quality(record), source_completeness(record))
        existing_rank = (description_quality(existing), source_completeness(existing))
        if candidate_rank > existing_rank:
            selected[call_id] = record
    return list(selected.values()), duplicates


def filter_active_records(
    records: Iterable[dict[str, Any]],
    *,
    today: date | None = None,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    active: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for record in records:
        status = classify_deadline(record.get("deadline_utc"), today=today)
        if status == OPEN_OR_UPCOMING:
            active.append(record)
        else:
            skipped[status] += 1
    return active, skipped


def _normalized_match_text(value: Any) -> str:
    text = html.unescape(str(value or "")).lower().replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def _contains_term(text: str, term: str) -> bool:
    normalized_term = _normalized_match_text(term)
    return bool(re.search(rf"\b{re.escape(normalized_term)}\b", text))


def calculate_theme_score(record: dict[str, Any]) -> dict[str, Any]:
    title_text = _normalized_match_text(
        " ".join([str(record.get("call_title") or ""), str(record.get("topic_title") or "")])
    )
    body_text = _normalized_match_text(
        " ".join(
            str(record.get(field) or "")
            for field in ("description", "objectives", "expected_impact", "keywords")
        )
    )
    breakdown: dict[str, int] = {}
    matched_terms: dict[str, list[str]] = {}

    for theme, terms in THEME_KEYWORDS.items():
        theme_score = 0
        theme_terms: list[str] = []
        for term in terms:
            phrase = " " in _normalized_match_text(term)
            if _contains_term(title_text, term):
                theme_score += 3 if phrase else 2
                theme_terms.append(term)
            elif _contains_term(body_text, term):
                theme_score += 2 if phrase else 1
                theme_terms.append(term)
        # A lone generic metadata tag should not be presented as a meaningful
        # theme match; require either a phrase, a title hit, or multiple terms.
        if theme_score >= MIN_THEME_GROUP_SCORE:
            breakdown[theme] = theme_score
            matched_terms[theme] = theme_terms

    matched_themes = sorted(breakdown, key=lambda theme: (-breakdown[theme], theme))
    return {
        "theme_score": sum(breakdown.values()),
        "matched_themes": matched_themes,
        "theme_breakdown": breakdown,
        "matched_terms": matched_terms,
    }


def _is_valid_staging_record(record: dict[str, Any]) -> bool:
    return bool(
        str(record.get("call_id") or "").strip()
        and str(record.get("call_title") or "").strip()
        and len(str(record.get("description") or "").strip()) > 20
        and str(record.get("deadline_utc") or "").strip()
        and str(record.get("source_url") or "").strip()
    )


def _review_sort_key(review: dict[str, Any]) -> tuple[Any, ...]:
    deadline = _parse_portal_datetime(review["record"].get("deadline_utc"))
    deadline_key = deadline or datetime.max.replace(tzinfo=timezone.utc)
    return (
        -review["theme_score"],
        deadline_key,
        -review["description_quality"],
        -review["source_completeness"],
        review["record"].get("call_id", ""),
    )


def _read_curated_records(path: Path = CURATED_CSV_PATH) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            row["call_id"].strip(): row
            for row in csv.DictReader(handle, delimiter=";")
            if row.get("call_id", "").strip()
        }


def _update_reasons(api_record: dict[str, Any], curated_record: dict[str, str]) -> list[str]:
    reasons = []
    for field in ("call_title", "deadline_utc", "source_url"):
        if str(api_record.get(field) or "").strip() != str(curated_record.get(field) or "").strip():
            reasons.append(field)
    return reasons


def _build_query() -> dict[str, Any]:
    return {
        "bool": {
            "must": [
                {"terms": {"type": ["1", "2", "8"]}},
                {"terms": {"status": ["31094501", "31094502"]}},
                {"term": {"programmePeriod": "2021 - 2027"}},
                {"terms": {"frameworkProgramme": [HORIZON_EUROPE_ID]}},
                {"term": {"language": "en"}},
            ]
        }
    }


def fetch_api_page(
    page_number: int,
    page_size: int,
    *,
    timeout: int = 60,
    max_attempts: int = 3,
) -> dict[str, Any]:
    params = {
        "apiKey": API_KEY,
        "text": "***",
        "pageSize": page_size,
        "pageNumber": page_number,
        "language": "en",
    }
    query_json = json.dumps(_build_query(), separators=(",", ":"))
    sort_json = json.dumps([{"field": "identifier", "order": "ASC"}], separators=(",", ":"))
    payload: dict[str, Any] | None = None
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(
                SEARCH_API_URL,
                params=params,
                files={
                    "query": ("query.json", query_json, "application/json"),
                    "sort": ("sort.json", sort_json, "application/json"),
                },
                headers={
                    "Accept": "application/json",
                    "User-Agent": "eu-funding-dss-dataset-expansion/1.0",
                },
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            break
        except requests.HTTPError as exc:
            last_error = exc
            status_code = exc.response.status_code if exc.response is not None else None
            retryable = status_code in {429, 500, 502, 503, 504}
            if not retryable or attempt == max_attempts:
                break
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt == max_attempts:
                break
        time.sleep(attempt * 2)

    if payload is None:
        raise ExpansionError(
            f"EU Funding & Tenders API request failed on page {page_number} after {max_attempts} attempts: "
            f"{last_error}"
        ) from last_error

    if payload.get("type") == "throwable":
        raise ExpansionError(f"EU Funding & Tenders API rejected page {page_number}: {payload.get('message')}")
    if not isinstance(payload.get("results"), list):
        raise ExpansionError(f"EU Funding & Tenders API returned an unexpected response on page {page_number}.")
    return payload


def fetch_api_records(*, limit: int, page_size: int, max_pages: int) -> tuple[list[dict[str, Any]], int]:
    results: list[dict[str, Any]] = []
    total_available = 0
    for page_number in range(1, max_pages + 1):
        payload = fetch_api_page(page_number, page_size)
        page_results = payload.get("results") or []
        total_available = int(payload.get("totalResults") or total_available or 0)
        results.extend(page_results)

        if limit > 0 and len(results) >= limit:
            return results[:limit], total_available
        if not page_results or len(results) >= total_available:
            break
    return results, total_available


def _atomic_write_csv(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({column: record.get(column, "") for column in CSV_COLUMNS})
    os.replace(temporary, path)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def _missing_field_counts(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    records_list = list(records)
    return {
        field: sum(not str(record.get(field) or "").strip() for record in records_list)
        for field in CSV_COLUMNS
    }


def build_expansion(
    api_results: list[dict[str, Any]],
    *,
    theme_threshold: int,
    today: date | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    checked = checked_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    normalized = [normalize_api_result(result, checked_at=checked, today=today) for result in api_results]
    deduplicated, duplicate_count = deduplicate_records(normalized)
    active, deadline_skipped = filter_active_records(deduplicated, today=today)
    valid_active = [record for record in active if _is_valid_staging_record(record)]
    invalid_active_count = len(active) - len(valid_active)

    curated = _read_curated_records()
    review_records: list[dict[str, Any]] = []
    existing_skipped = 0
    update_candidates: list[dict[str, Any]] = []

    for record in valid_active:
        score = calculate_theme_score(record)
        review = {
            "record": record,
            **score,
            "description_quality": description_quality(record),
            "source_completeness": source_completeness(record),
        }
        if record["call_id"] in curated:
            existing_skipped += 1
            reasons = _update_reasons(record, curated[record["call_id"]])
            if reasons:
                update_candidates.append(
                    {
                        "call_id": record["call_id"],
                        "changed_fields": reasons,
                        "theme_score": score["theme_score"],
                        "matched_themes": score["matched_themes"],
                    }
                )
            continue
        if score["theme_score"] >= theme_threshold:
            review_records.append(review)

    review_records.sort(key=_review_sort_key)
    recommended = [review["record"] for review in review_records]
    theme_counts: Counter[str] = Counter()
    for review in review_records:
        theme_counts.update(review["matched_themes"])

    return {
        "raw_staging": sorted(valid_active, key=lambda record: (record["deadline_utc"], record["call_id"])),
        "recommended": recommended,
        "review_records": review_records,
        "duplicate_skipped": duplicate_count,
        "deadline_skipped": dict(deadline_skipped),
        "invalid_active_skipped": invalid_active_count,
        "existing_curated_skipped": existing_skipped,
        "update_candidates": update_candidates,
        "top_matched_themes": dict(theme_counts.most_common()),
        "missing_fields": _missing_field_counts(valid_active),
        "normalized_count": len(normalized),
        "deduplicated_count": len(deduplicated),
    }


def _review_log_entry(review: dict[str, Any]) -> dict[str, Any]:
    record = review["record"]
    return {
        "call_id": record["call_id"],
        "call_title": record["call_title"],
        "deadline_utc": record["deadline_utc"],
        "theme_score": review["theme_score"],
        "matched_themes": review["matched_themes"],
        "theme_breakdown": review["theme_breakdown"],
        "matched_terms": review["matched_terms"],
        "description_quality": review["description_quality"],
        "source_completeness": review["source_completeness"],
        "source_url": record["source_url"],
    }


def _build_log(
    expansion: dict[str, Any],
    *,
    args: argparse.Namespace,
    fetched_count: int,
    total_available: int,
) -> dict[str, Any]:
    deadline_skipped = expansion["deadline_skipped"]
    return {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": {
            "endpoint": SEARCH_API_URL,
            "api_key": API_KEY,
            "framework_programme": "Horizon Europe",
            "framework_programme_id": HORIZON_EUROPE_ID,
            "statuses": {"31094501": "Forthcoming", "31094502": "Open for submission"},
            "language": "en",
        },
        "configuration": {
            "limit": args.limit,
            "page_size": args.page_size,
            "max_pages": args.max_pages,
            "theme_threshold": args.theme_threshold,
            "dry_run": args.dry_run,
            "write_staging": args.write_staging,
            "write_recommended": args.write_recommended,
        },
        "counts": {
            "api_total_available": total_available,
            "api_results_fetched": fetched_count,
            "normalized": expansion["normalized_count"],
            "deduplicated": expansion["deduplicated_count"],
            "raw_staging": len(expansion["raw_staging"]),
            "recommended_expansion": len(expansion["recommended"]),
            "expired_skipped": deadline_skipped.get(EXPIRED, 0),
            "unknown_deadline_skipped": deadline_skipped.get(UNKNOWN_DEADLINE, 0),
            "invalid_deadline_skipped": deadline_skipped.get(INVALID_DEADLINE, 0),
            "invalid_active_skipped": expansion["invalid_active_skipped"],
            "duplicate_skipped": expansion["duplicate_skipped"],
            "existing_curated_skipped": expansion["existing_curated_skipped"],
            "update_candidates": len(expansion["update_candidates"]),
        },
        "top_matched_themes": expansion["top_matched_themes"],
        "missing_fields": expansion["missing_fields"],
        "update_candidates": expansion["update_candidates"],
        "recommended_review": [_review_log_entry(review) for review in expansion["review_records"]],
        "outputs": {
            "raw_staging": str(RAW_STAGING_PATH.relative_to(PROJECT_ROOT)),
            "recommended_expansion": str(RECOMMENDED_PATH.relative_to(PROJECT_ROOT)),
            "log": str(LOG_PATH.relative_to(PROJECT_ROOT)),
        },
        "safety_note": (
            "This pipeline does not modify calls_seed_clean.csv or eu_funding.sqlite. "
            "Recommended records require manual review before promotion."
        ),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch and stage Horizon Europe calls from the official Funding & Tenders Search API."
    )
    parser.add_argument("--limit", type=int, default=0, help="Maximum API results to inspect; 0 means no limit.")
    parser.add_argument("--page-size", type=int, default=50, help="Number of API records requested per page.")
    parser.add_argument("--max-pages", type=int, default=20, help="Maximum number of API pages to request.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and analyse without writing output files.")
    parser.add_argument("--write-staging", action="store_true", help="Write the broad active staging CSV.")
    parser.add_argument("--write-recommended", action="store_true", help="Write the themed recommended CSV.")
    parser.add_argument(
        "--theme-threshold",
        type=int,
        default=5,
        help="Minimum transparent keyword score required for the recommended expansion.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.limit < 0 or args.page_size < 1 or args.max_pages < 1 or args.theme_threshold < 0:
        print("Invalid CLI values: limits and thresholds must be non-negative, and page sizes must be positive.")
        return 2

    try:
        api_results, total_available = fetch_api_records(
            limit=args.limit,
            page_size=args.page_size,
            max_pages=args.max_pages,
        )
        expansion = build_expansion(api_results, theme_threshold=args.theme_threshold)
        log = _build_log(
            expansion,
            args=args,
            fetched_count=len(api_results),
            total_available=total_available,
        )
    except ExpansionError as exc:
        print(f"Dataset expansion stopped safely: {exc}")
        return 1

    if not args.dry_run:
        if args.write_staging:
            _atomic_write_csv(RAW_STAGING_PATH, expansion["raw_staging"])
        if args.write_recommended:
            _atomic_write_csv(RECOMMENDED_PATH, expansion["recommended"])
        _atomic_write_json(LOG_PATH, log)

    counts = log["counts"]
    print("EU Funding & Tenders dataset expansion summary")
    print(f"API records available: {counts['api_total_available']}")
    print(f"API records fetched: {counts['api_results_fetched']}")
    print(f"Raw active staging records: {counts['raw_staging']}")
    print(f"Recommended new records: {counts['recommended_expansion']}")
    print(f"Expired skipped: {counts['expired_skipped']}")
    print(f"Duplicate skipped: {counts['duplicate_skipped']}")
    print(f"Existing curated records skipped: {counts['existing_curated_skipped']}")
    print(f"Top matched themes: {log['top_matched_themes']}")
    if args.dry_run:
        print("Dry run complete; no files were written.")
    else:
        print(f"Expansion log: {LOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
