import csv
import json
import os
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.deadlines import OPEN_OR_UPCOMING, classify_deadline


PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMPORTS_DIR = PROJECT_ROOT / "data" / "imports"
EVALUATION_OUTPUTS_DIR = PROJECT_ROOT / "data" / "evaluation_outputs"

MAIN_CSV_PATH = IMPORTS_DIR / "calls_seed_clean.csv"
RAW_STAGING_PATH = IMPORTS_DIR / "eu_calls_raw_staging.csv"
RECOMMENDED_EXPANSION_PATH = IMPORTS_DIR / "eu_calls_recommended_expansion.csv"
PROMOTION_CANDIDATES_PATH = IMPORTS_DIR / "eu_calls_promotion_candidates.csv"
ENRICHED_PROMOTION_CANDIDATES_PATH = IMPORTS_DIR / "eu_calls_promotion_candidates_enriched.csv"
PRIORITY_ENRICHED_CANDIDATES_PATH = IMPORTS_DIR / "calls_seed_priority_enriched_candidates.csv"
APPROVED_PROMOTION_PATH = IMPORTS_DIR / "eu_calls_approved_promotion.csv"
APPROVAL_LOG_PATH = EVALUATION_OUTPUTS_DIR / "eu_calls_approval_log.json"
PROMOTION_REVIEW_LOG_PATH = EVALUATION_OUTPUTS_DIR / "eu_calls_promotion_review_log.json"
EXPANSION_LOG_PATH = EVALUATION_OUTPUTS_DIR / "eu_dataset_expansion_log.json"

DECISION_APPROVE = "approve"
DECISION_HOLD = "hold"
DECISION_REJECT = "reject"
VALID_DECISIONS = {DECISION_APPROVE, DECISION_HOLD, DECISION_REJECT}

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

REQUIRED_PROMOTION_FIELDS = ("call_id", "call_title", "description", "deadline_utc", "source_url")
IMPORTANT_METADATA_FIELDS = (
    "trl_min",
    "trl_max",
    "eligible_countries",
    "eligible_org_types",
    "consortium_required",
    "min_partners",
)

REVIEW_SOURCE_OPTIONS = {
    "Recommended expansion": RECOMMENDED_EXPANSION_PATH,
    "Promotion candidates": PROMOTION_CANDIDATES_PATH,
    "Enriched promotion candidates": ENRICHED_PROMOTION_CANDIDATES_PATH,
    "Priority enriched candidates": PRIORITY_ENRICHED_CANDIDATES_PATH,
    "Raw staging": RAW_STAGING_PATH,
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def read_csv_records(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def write_csv_records(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in CSV_COLUMNS})
    os.replace(temporary, path)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def schema_issues(records: list[Mapping[str, Any]]) -> list[str]:
    if not records:
        return []
    available = set(records[0].keys())
    missing = [field for field in CSV_COLUMNS if field not in available]
    extra = [field for field in records[0].keys() if field not in CSV_COLUMNS]
    issues: list[str] = []
    if missing:
        issues.append("missing columns: " + ", ".join(missing))
    if extra:
        issues.append("extra columns ignored on export: " + ", ".join(extra))
    return issues


def current_call_ids(path: Path = MAIN_CSV_PATH) -> set[str]:
    return {
        _clean(record.get("call_id"))
        for record in read_csv_records(path)
        if _clean(record.get("call_id"))
    }


def missing_metadata_fields(record: Mapping[str, Any]) -> list[str]:
    return [field for field in IMPORTANT_METADATA_FIELDS if not _clean(record.get(field))]


def promotion_blockers(
    record: Mapping[str, Any],
    *,
    existing_call_ids: set[str],
    today: date | None = None,
) -> list[str]:
    blockers: list[str] = []
    call_id = _clean(record.get("call_id"))
    if not call_id:
        blockers.append("missing call_id")
    elif call_id in existing_call_ids:
        blockers.append("already exists in main dataset")

    missing_required = [field for field in REQUIRED_PROMOTION_FIELDS if not _clean(record.get(field))]
    if missing_required:
        blockers.append("missing required fields: " + ", ".join(missing_required))

    deadline_status = classify_deadline(record.get("deadline_utc"), today=today)
    if deadline_status != OPEN_OR_UPCOMING:
        blockers.append(f"deadline is {deadline_status}")

    return blockers


def review_flags(
    record: Mapping[str, Any],
    *,
    existing_call_ids: set[str],
    today: date | None = None,
) -> list[str]:
    flags = promotion_blockers(record, existing_call_ids=existing_call_ids, today=today)
    missing_metadata = missing_metadata_fields(record)
    if missing_metadata:
        flags.append("metadata to verify: " + ", ".join(missing_metadata[:4]))
    if len(_clean(record.get("description"))) < 120:
        flags.append("short description")
    if not _clean(record.get("expected_impact")):
        flags.append("missing expected impact")
    return flags


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_review_metadata(
    *,
    promotion_review_log_path: Path = PROMOTION_REVIEW_LOG_PATH,
    expansion_log_path: Path = EXPANSION_LOG_PATH,
) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}

    expansion_log = _load_json(expansion_log_path)
    for item in expansion_log.get("recommended_review", []) or []:
        call_id = _clean(item.get("call_id"))
        if not call_id:
            continue
        metadata.setdefault(call_id, {}).update(
            {
                "theme_score": item.get("theme_score", ""),
                "matched_themes": item.get("matched_themes", []),
            }
        )

    promotion_log = _load_json(promotion_review_log_path)
    for item in promotion_log.get("selected_records", []) or []:
        call_id = _clean(item.get("call_id"))
        if not call_id:
            continue
        metadata.setdefault(call_id, {}).update(
            {
                "promotion_readiness_score": item.get("promotion_readiness_score", ""),
                "matched_themes": item.get("matched_themes", metadata.get(call_id, {}).get("matched_themes", [])),
                "reason_for_selection": item.get("reason_for_selection", ""),
                "caution_notes": item.get("caution_notes", []),
            }
        )
    return metadata


def build_review_rows(
    records: Iterable[Mapping[str, Any]],
    *,
    existing_call_ids: set[str] | None = None,
    review_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    today: date | None = None,
) -> list[dict[str, Any]]:
    existing = existing_call_ids if existing_call_ids is not None else current_call_ids()
    metadata = review_metadata or {}
    rows: list[dict[str, Any]] = []

    for record in records:
        call_id = _clean(record.get("call_id"))
        meta = metadata.get(call_id, {})
        blockers = promotion_blockers(record, existing_call_ids=existing, today=today)
        flags = review_flags(record, existing_call_ids=existing, today=today)
        rows.append(
            {
                "decision": DECISION_HOLD,
                "can_approve": not blockers,
                "call_id": call_id,
                "title": _clean(record.get("call_title") or record.get("topic_title")),
                "deadline_status": classify_deadline(record.get("deadline_utc"), today=today),
                "deadline_utc": _clean(record.get("deadline_utc")),
                "action_type": _clean(record.get("action_type")),
                "cluster": _clean(record.get("cluster")),
                "theme_score": meta.get("theme_score", ""),
                "promotion_score": meta.get("promotion_readiness_score", ""),
                "matched_themes": ", ".join(meta.get("matched_themes") or []),
                "missing_metadata_count": len(missing_metadata_fields(record)),
                "flags": "; ".join(flags),
                "blockers": "; ".join(blockers),
                "source_url": _clean(record.get("source_url")),
            }
        )
    return rows


def _normalise_decision(value: Any) -> str:
    decision = _clean(value).lower()
    return decision if decision in VALID_DECISIONS else DECISION_HOLD


def prepare_approval_batch(
    records: Iterable[Mapping[str, Any]],
    decisions: Mapping[str, Any],
    *,
    existing_call_ids: set[str] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    existing = existing_call_ids if existing_call_ids is not None else current_call_ids()
    approved: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    held_or_rejected: list[dict[str, Any]] = []
    seen_approved: set[str] = set()

    for record in records:
        call_id = _clean(record.get("call_id"))
        decision = _normalise_decision(decisions.get(call_id))
        if decision != DECISION_APPROVE:
            held_or_rejected.append({"call_id": call_id, "decision": decision})
            continue

        blockers = promotion_blockers(record, existing_call_ids=existing, today=today)
        if call_id in seen_approved:
            blockers.append("duplicate approval in this batch")

        if blockers:
            blocked.append({"call_id": call_id, "title": _clean(record.get("call_title")), "blockers": blockers})
            continue

        approved.append({field: record.get(field, "") for field in CSV_COLUMNS})
        seen_approved.add(call_id)

    return {
        "approved_records": approved,
        "blocked_records": blocked,
        "held_or_rejected_records": held_or_rejected,
        "summary": {
            "approved": len(approved),
            "blocked": len(blocked),
            "held_or_rejected": len(held_or_rejected),
        },
    }


def write_approval_batch(
    source_path: Path,
    decisions: Mapping[str, Any],
    *,
    output_path: Path = APPROVED_PROMOTION_PATH,
    log_path: Path = APPROVAL_LOG_PATH,
    main_csv_path: Path = MAIN_CSV_PATH,
    today: date | None = None,
) -> dict[str, Any]:
    records = read_csv_records(source_path)
    existing = current_call_ids(main_csv_path)
    batch = prepare_approval_batch(records, decisions, existing_call_ids=existing, today=today)
    approved_records = batch["approved_records"]

    write_csv_records(output_path, approved_records)

    decision_counts = Counter(_normalise_decision(value) for value in decisions.values())
    log = {
        "generated_at_utc": _utc_now(),
        "source_file": _relative(source_path),
        "main_dataset": _relative(main_csv_path),
        "output_file": _relative(output_path),
        "main_dataset_modified": False,
        "sqlite_modified": False,
        "schema_issues": schema_issues(records),
        "decision_counts": dict(decision_counts),
        "summary": batch["summary"],
        "approved_call_ids": [record["call_id"] for record in approved_records],
        "blocked_records": batch["blocked_records"],
        "next_steps": [
            "Review the approved promotion CSV before touching the main dataset.",
            "Back up calls_seed_clean.csv and data/eu_funding.sqlite before promotion.",
            "Run dataset audit, import, tests, semantic health, and retrieval QA after explicit promotion.",
        ],
    }
    write_json(log_path, log)
    return log
