import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.expand_dataset_from_eu_api import (  # noqa: E402
    CSV_COLUMNS,
    ExpansionError,
    _clean_text,
    _plain_text,
    fetch_api_page,
    normalize_api_result,
)


INPUT_PATH = PROJECT_ROOT / "data" / "imports" / "eu_calls_promotion_candidates.csv"
OUTPUT_PATH = PROJECT_ROOT / "data" / "imports" / "eu_calls_promotion_candidates_enriched.csv"
LOG_PATH = PROJECT_ROOT / "data" / "evaluation_outputs" / "eu_calls_promotion_enrichment_log.json"
CURATED_PATH = PROJECT_ROOT / "data" / "imports" / "calls_seed_clean.csv"
DATABASE_PATH = PROJECT_ROOT / "data" / "eu_funding.sqlite"

TARGET_FIELDS = (
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
    "keywords",
    "pillar",
    "cluster",
)

TEXT_FIELDS = ("description", "objectives", "expected_impact")
OFFICIAL_CACHED_SOURCE = "Official EU Search API record retained in the promotion candidate dataset"


def _normalized_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _evidence_snippet(text: str, match: re.Match[str] | None = None, limit: int = 320) -> str:
    clean = _normalized_space(text)
    if not clean:
        return ""
    if match is None:
        return clean[:limit]
    start = max(0, match.start() - 90)
    end = min(len(clean), match.end() + 180)
    return clean[start:end].strip()[:limit]


def _record_text(record: dict[str, Any]) -> str:
    return " ".join(_normalized_space(record.get(field)) for field in TEXT_FIELDS if record.get(field))


def extract_explicit_trl(text: str) -> dict[str, Any]:
    clean = _normalized_space(text)
    if not clean:
        return {"trl_min": "", "trl_max": "", "evidence": "", "reason": "not_found"}

    start_matches = list(
        re.finditer(
            r"(?i)\b(?:start(?:ing)?|begin(?:ning)?)\s+(?:at|from)\s+TRL\s*([1-9])"
            r"(?:\s*(?:-|to)\s*(?:TRL\s*)?([1-9]))?\b",
            clean,
        )
    )
    end_matches = list(
        re.finditer(
            r"(?i)\b(?:reach|achieve|attain|finish|end)\w*\s+(?:at\s+)?TRL\s*([1-9])"
            r"(?:\s*(?:-|to)\s*(?:TRL\s*)?([1-9]))?\b",
            clean,
        )
    )
    start_ranges = {
        (int(match.group(1)), int(match.group(2) or match.group(1))) for match in start_matches
    }
    end_ranges = {
        (int(match.group(1)), int(match.group(2) or match.group(1))) for match in end_matches
    }
    if len(start_ranges) > 1 or len(end_ranges) > 1:
        return {"trl_min": "", "trl_max": "", "evidence": "", "reason": "ambiguous"}
    if start_ranges or end_ranges:
        start_range = next(iter(start_ranges), None)
        end_range = next(iter(end_ranges), None)
        minimum = start_range[0] if start_range else (end_range[0] if end_range and end_range[0] != end_range[1] else None)
        maximum = end_range[1] if end_range else (start_range[1] if start_range else None)
        if minimum is not None and maximum is not None and minimum > maximum:
            return {"trl_min": "", "trl_max": "", "evidence": "", "reason": "ambiguous"}
        evidence_match = (start_matches or end_matches)[0]
        evidence_end = (end_matches or start_matches)[-1]
        combined = clean[max(0, evidence_match.start() - 90) : min(len(clean), evidence_end.end() + 180)]
        return {
            "trl_min": str(minimum) if minimum is not None else "",
            "trl_max": str(maximum) if maximum is not None else "",
            "evidence": _normalized_space(combined)[:320],
            "reason": "explicit",
        }

    range_matches = list(
        re.finditer(r"(?i)\bTRL\s*([1-9])\s*(?:-|to)\s*(?:TRL\s*)?([1-9])\b", clean)
    )
    ranges = {(int(match.group(1)), int(match.group(2))) for match in range_matches}
    if len(ranges) == 1:
        minimum, maximum = next(iter(ranges))
        if minimum <= maximum:
            return {
                "trl_min": str(minimum),
                "trl_max": str(maximum),
                "evidence": _evidence_snippet(clean, range_matches[0]),
                "reason": "explicit",
            }
    if len(ranges) > 1:
        return {"trl_min": "", "trl_max": "", "evidence": "", "reason": "ambiguous"}

    return {"trl_min": "", "trl_max": "", "evidence": "", "reason": "not_found"}


def extract_explicit_consortium(text: str) -> dict[str, Any]:
    clean = _normalized_space(text)
    if not clean:
        return {
            "consortium_required": "",
            "min_partners": "",
            "evidence": "",
            "reason": "not_found",
        }

    single_match = re.search(
        r"(?i)\b(?:single applicant|single legal entity)\s+(?:is|shall be|may be)\s+(?:eligible|allowed|permitted)\b",
        clean,
    )
    minimum_match = re.search(
        r"(?i)\b(?:at least|minimum of)\s+([2-9]|two|three|four|five|six|seven|eight|nine)\s+"
        r"(?:independent\s+)?(?:legal entities|partners|participants|beneficiaries)\b",
        clean,
    )
    required_match = re.search(
        r"\b(?:the\s+)?consortium\s+(?:must|shall|should|is expected to)\b|"
        r"\b(?:must|shall|should)\s+be\s+(?:submitted|implemented|driven)\s+by\s+(?:a\s+)?consortium\b|"
        r"\bdriven\s+by\s+(?:a\s+)?consortium\b",
        clean,
        flags=re.IGNORECASE,
    )

    if single_match and (minimum_match or required_match):
        return {
            "consortium_required": "",
            "min_partners": "",
            "evidence": "",
            "reason": "ambiguous",
        }
    if single_match:
        return {
            "consortium_required": "0",
            "min_partners": "1",
            "evidence": _evidence_snippet(clean, single_match),
            "reason": "explicit",
        }

    if minimum_match:
        number_words = {
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
        }
        token = minimum_match.group(1).lower()
        minimum = int(token) if token.isdigit() else number_words[token]
        return {
            "consortium_required": "1",
            "min_partners": str(minimum),
            "evidence": _evidence_snippet(clean, minimum_match),
            "reason": "explicit",
        }
    if required_match:
        return {
            "consortium_required": "1",
            "min_partners": "",
            "evidence": _evidence_snippet(clean, required_match),
            "reason": "explicit",
        }

    return {
        "consortium_required": "",
        "min_partners": "",
        "evidence": "",
        "reason": "not_found",
    }


def extract_explicit_eligibility(text: str) -> dict[str, Any]:
    clean = _normalized_space(text)
    if not clean:
        return {
            "eligible_countries": "",
            "eligible_org_types": "",
            "evidence": "",
            "reason": "not_found",
        }

    target_match = re.search(
        r"(?i)\bthis topic targets\s+(.{3,180}?)\s+in\s+EU Member States and Associated Countries\b",
        clean,
    )
    only_match = re.search(
        r"(?i)\bonly\s+(SMEs|public authorities|research organisations|research organizations|universities)\s+"
        r"(?:are|shall be)\s+eligible\b",
        clean,
    )
    country_list_match = re.search(r"(?i)\beligible countries\s*:\s*([^.;]{3,220})", clean)

    countries = ""
    organisations = ""
    matches: list[re.Match[str]] = []
    if target_match:
        organisations = _normalized_space(target_match.group(1))
        countries = "EU Member States; Horizon Europe Associated Countries"
        matches.append(target_match)
    if only_match:
        label_map = {
            "smes": "SME",
            "public authorities": "Public authorities",
            "research organisations": "Research organisations",
            "research organizations": "Research organisations",
            "universities": "Universities",
        }
        extracted = label_map[only_match.group(1).lower()]
        if organisations and organisations.lower() != extracted.lower():
            return {
                "eligible_countries": "",
                "eligible_org_types": "",
                "evidence": "",
                "reason": "ambiguous",
            }
        organisations = extracted
        matches.append(only_match)
    if country_list_match:
        listed = _normalized_space(country_list_match.group(1))
        if any(term in listed.lower() for term in ("annex", "see conditions", "call document")):
            return {
                "eligible_countries": "",
                "eligible_org_types": organisations,
                "evidence": _evidence_snippet(clean, matches[0]) if matches else "",
                "reason": "ambiguous",
            }
        countries = listed
        matches.append(country_list_match)

    if countries or organisations:
        return {
            "eligible_countries": countries,
            "eligible_org_types": organisations,
            "evidence": _evidence_snippet(clean, matches[0]),
            "reason": "explicit",
        }
    return {
        "eligible_countries": "",
        "eligible_org_types": "",
        "evidence": "",
        "reason": "not_found",
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _metadata_text(api_result: dict[str, Any]) -> str:
    metadata = api_result.get("metadata") or {}
    preferred_keys = (
        "descriptionByte",
        "topicConditions",
        "conditions",
        "eligibilityConditions",
        "supportInfo",
        "title",
    )
    parts: list[str] = []
    for key in preferred_keys:
        value = metadata.get(key)
        if isinstance(value, list):
            value = " ".join(str(item) for item in value)
        if value:
            parts.append(_plain_text(value))
    return _normalized_space(" ".join(parts))


def fetch_live_official_records(
    candidate_ids: set[str],
    *,
    page_size: int = 50,
    max_pages: int = 20,
) -> tuple[dict[str, dict[str, Any]], str]:
    try:
        fetch_api_page(1, 1, timeout=15, max_attempts=1)
    except ExpansionError as exc:
        return {}, str(exc)

    found: dict[str, dict[str, Any]] = {}
    try:
        for page_number in range(1, max_pages + 1):
            payload = fetch_api_page(page_number, page_size, timeout=45, max_attempts=2)
            results = payload.get("results") or []
            for result in results:
                identifier = _clean_text((result.get("metadata") or {}).get("identifier"))
                if identifier in candidate_ids:
                    found[identifier] = result
            if found.keys() >= candidate_ids or not results:
                break
            total = int(payload.get("totalResults") or 0)
            if page_number * page_size >= total:
                break
    except ExpansionError as exc:
        return found, str(exc)
    return found, ""


def _field_review(
    field: str,
    old_value: Any,
    new_value: Any,
    *,
    evidence: str,
    source: str,
    confidence: str,
    reason: str = "",
) -> dict[str, str]:
    return {
        "field_name": field,
        "old_value": str(old_value or ""),
        "new_value": str(new_value or ""),
        "evidence_snippet": _normalized_space(evidence)[:320],
        "source_used": source,
        "confidence": confidence,
        "reason": reason,
    }


def _completeness_score(record: dict[str, Any]) -> int:
    populated = sum(bool(str(record.get(field) or "").strip()) for field in TARGET_FIELDS)
    return round(100 * populated / len(TARGET_FIELDS))


def enrich_record(
    record: dict[str, str],
    api_result: dict[str, Any] | None = None,
    *,
    api_unavailable: bool = False,
) -> tuple[dict[str, str], dict[str, Any]]:
    enriched = {column: str(record.get(column) or "") for column in CSV_COLUMNS}
    source_url = enriched.get("source_url") or "Official EU Funding & Tenders Search API"
    source_label = source_url if api_result else OFFICIAL_CACHED_SOURCE
    official_text = _metadata_text(api_result) if api_result else _record_text(enriched)
    normalized_live = normalize_api_result(api_result) if api_result else {}
    reviews: dict[str, dict[str, str]] = {}
    changed_fields: list[str] = []

    # Prefer fresh official API values when they are more complete, but never erase curated candidate values.
    for field in ("action_type", "budget_min_eur", "budget_max_eur", "objectives", "expected_impact", "pillar", "cluster"):
        old = enriched.get(field, "")
        fresh = str(normalized_live.get(field) or "").strip()
        new = fresh if fresh and (not old or len(fresh) > len(old)) else old
        if new != old:
            enriched[field] = new
            changed_fields.append(field)
        evidence = fresh or old
        reviews[field] = _field_review(
            field,
            old,
            new,
            evidence=evidence,
            source=source_label,
            confidence="explicit" if evidence else "not_found",
            reason="" if evidence else ("source_unavailable" if api_unavailable else "not_found"),
        )

    trl = extract_explicit_trl(official_text)
    for field in ("trl_min", "trl_max"):
        old = enriched.get(field, "")
        extracted = trl[field]
        new = old or extracted
        if new != old:
            enriched[field] = new
            changed_fields.append(field)
        reason = "" if new else trl["reason"]
        reviews[field] = _field_review(
            field,
            old,
            new,
            evidence=trl["evidence"],
            source=source_label,
            confidence="explicit" if extracted else "not_found",
            reason=reason,
        )

    consortium = extract_explicit_consortium(official_text)
    for field in ("consortium_required", "min_partners"):
        old = enriched.get(field, "")
        extracted = consortium[field]
        new = old or extracted
        if new != old:
            enriched[field] = new
            changed_fields.append(field)
        reviews[field] = _field_review(
            field,
            old,
            new,
            evidence=consortium["evidence"],
            source=source_label,
            confidence="explicit" if extracted else "not_found",
            reason="" if new else consortium["reason"],
        )

    eligibility = extract_explicit_eligibility(official_text)
    for field in ("eligible_countries", "eligible_org_types"):
        old = enriched.get(field, "")
        extracted = eligibility[field]
        new = old or extracted
        if new != old:
            enriched[field] = new
            changed_fields.append(field)
        reviews[field] = _field_review(
            field,
            old,
            new,
            evidence=eligibility["evidence"],
            source=source_label,
            confidence="explicit" if extracted else "not_found",
            reason="" if new else eligibility["reason"],
        )

    old_keywords = enriched.get("keywords", "")
    reviews["keywords"] = _field_review(
        "keywords",
        old_keywords,
        old_keywords,
        evidence=old_keywords,
        source=source_label,
        confidence="explicit" if old_keywords else "not_found",
        reason="" if old_keywords else ("source_unavailable" if api_unavailable else "not_found"),
    )

    if changed_fields:
        verification_status = "enriched_official" if api_result else "partially_enriched"
    elif official_text:
        verification_status = "source_checked_no_metadata"
    else:
        verification_status = "source_unavailable"

    log_entry = {
        "call_id": enriched.get("call_id", ""),
        "title": enriched.get("call_title") or enriched.get("topic_title", ""),
        "verification_status": verification_status,
        "metadata_completeness_score": _completeness_score(enriched),
        "changed_fields": changed_fields,
        "official_source_url": source_url,
        "live_api_record_found": bool(api_result),
        "field_evidence": [reviews[field] for field in TARGET_FIELDS],
    }
    return enriched, log_entry


def run_enrichment(
    input_path: Path = INPUT_PATH,
    output_path: Path = OUTPUT_PATH,
    log_path: Path = LOG_PATH,
    *,
    skip_live_api: bool = False,
) -> dict[str, Any]:
    candidates = _read_csv(input_path)
    candidate_ids = {row.get("call_id", "") for row in candidates if row.get("call_id")}
    hashes_before = {"main_csv": _sha256(CURATED_PATH), "sqlite": _sha256(DATABASE_PATH)}

    live_records: dict[str, dict[str, Any]] = {}
    api_error = "Live API check skipped by command-line option." if skip_live_api else ""
    if not skip_live_api:
        live_records, api_error = fetch_live_official_records(candidate_ids)

    enriched_records: list[dict[str, str]] = []
    record_logs: list[dict[str, Any]] = []
    for candidate in candidates:
        call_id = candidate.get("call_id", "")
        enriched, entry = enrich_record(
            candidate,
            live_records.get(call_id),
            api_unavailable=bool(api_error),
        )
        enriched_records.append(enriched)
        record_logs.append(entry)

    _atomic_write_csv(output_path, enriched_records)
    hashes_after = {"main_csv": _sha256(CURATED_PATH), "sqlite": _sha256(DATABASE_PATH)}

    field_changes = Counter(
        field
        for entry in record_logs
        for field in entry.get("changed_fields", [])
    )
    missing_counts = Counter(
        field
        for record in enriched_records
        for field in TARGET_FIELDS
        if not str(record.get(field) or "").strip()
    )
    status_counts = Counter(entry["verification_status"] for entry in record_logs)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "input_file": str(input_path.relative_to(PROJECT_ROOT)),
        "output_file": str(output_path.relative_to(PROJECT_ROOT)),
        "official_api": {
            "live_records_found": len(live_records),
            "error": api_error,
            "fallback_used": bool(api_error),
            "fallback_description": OFFICIAL_CACHED_SOURCE,
        },
        "summary": {
            "candidates_processed": len(candidates),
            "records_with_new_enrichment": sum(bool(entry["changed_fields"]) for entry in record_logs),
            "field_changes": dict(sorted(field_changes.items())),
            "fields_still_missing": dict(sorted(missing_counts.items())),
            "verification_status_distribution": dict(sorted(status_counts.items())),
        },
        "protected_file_hashes": {
            "before": hashes_before,
            "after": hashes_after,
            "unchanged": hashes_before == hashes_after,
        },
        "records": record_logs,
    }
    _atomic_write_json(log_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich EU promotion candidates using explicit official evidence.")
    parser.add_argument("--input", type=Path, default=INPUT_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--log", type=Path, default=LOG_PATH)
    parser.add_argument("--skip-live-api", action="store_true")
    args = parser.parse_args()

    report = run_enrichment(args.input, args.output, args.log, skip_live_api=args.skip_live_api)
    summary = report["summary"]
    print("EU promotion candidate enrichment")
    print(f"Candidates processed: {summary['candidates_processed']}")
    print(f"Records enriched: {summary['records_with_new_enrichment']}")
    print(f"Live API records found: {report['official_api']['live_records_found']}")
    if report["official_api"]["error"]:
        print(f"Live API note: {report['official_api']['error']}")
    print(f"Field changes: {summary['field_changes']}")
    print(f"Verification statuses: {summary['verification_status_distribution']}")
    print(f"Protected files unchanged: {report['protected_file_hashes']['unchanged']}")
    print(f"Wrote: {args.output}")
    print(f"Log: {args.log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
