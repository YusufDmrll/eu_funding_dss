import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.priority_enrichment import (  # noqa: E402
    PRIORITY_THEME_LABELS,
    missing_metadata_fields,
    priority_theme_distribution,
    select_priority_enrichment_records,
)
from scripts.enrich_eu_promotion_candidates import (  # noqa: E402
    TARGET_FIELDS,
    enrich_record,
    fetch_live_official_records,
)
from scripts.expand_dataset_from_eu_api import CSV_COLUMNS  # noqa: E402


MAIN_CSV_PATH = PROJECT_ROOT / "data" / "imports" / "calls_seed_clean.csv"
DATABASE_PATH = PROJECT_ROOT / "data" / "eu_funding.sqlite"
OUTPUT_PATH = PROJECT_ROOT / "data" / "imports" / "calls_seed_priority_enriched_candidates.csv"
LOG_PATH = PROJECT_ROOT / "data" / "evaluation_outputs" / "priority_call_metadata_enrichment_log.json"


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


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _strip_internal_fields(record: dict[str, Any]) -> dict[str, Any]:
    return {column: record.get(column, "") for column in CSV_COLUMNS}


def _field_changes(records: Iterable[dict[str, Any]]) -> Counter[str]:
    return Counter(field for entry in records for field in entry.get("changed_fields", []))


def _missing_field_counts(records: Iterable[dict[str, Any]]) -> Counter[str]:
    return Counter(field for record in records for field in missing_metadata_fields(record))


def run_priority_enrichment(
    *,
    input_path: Path = MAIN_CSV_PATH,
    output_path: Path = OUTPUT_PATH,
    log_path: Path = LOG_PATH,
    limit: int = 40,
    skip_live_api: bool = False,
) -> dict[str, Any]:
    source_records = _read_csv(input_path)
    selected_records = select_priority_enrichment_records(source_records, limit=limit)
    selected_ids = {str(record.get("call_id") or "") for record in selected_records if record.get("call_id")}

    hashes_before = {
        "main_csv": _sha256(MAIN_CSV_PATH),
        "sqlite": _sha256(DATABASE_PATH),
    }

    live_records: dict[str, dict[str, Any]] = {}
    api_error = "Live API check skipped by command-line option." if skip_live_api else ""
    if selected_ids and not skip_live_api:
        live_records, api_error = fetch_live_official_records(selected_ids)

    enriched_records: list[dict[str, Any]] = []
    record_logs: list[dict[str, Any]] = []
    for selected in selected_records:
        clean_record = _strip_internal_fields(selected)
        call_id = str(clean_record.get("call_id") or "")
        enriched, entry = enrich_record(
            clean_record,
            live_records.get(call_id),
            api_unavailable=bool(api_error),
        )
        entry["selection"] = {
            "priority_enrichment_score": selected.get("_priority_enrichment_score"),
            "priority_themes": [
                PRIORITY_THEME_LABELS.get(theme, theme)
                for theme in selected.get("_priority_themes", [])
            ],
            "missing_metadata_before": selected.get("_missing_metadata_fields", []),
            "source_row_index": selected.get("_source_row_index"),
        }
        enriched_records.append(enriched)
        record_logs.append(entry)

    _atomic_write_csv(output_path, enriched_records)
    hashes_after = {
        "main_csv": _sha256(MAIN_CSV_PATH),
        "sqlite": _sha256(DATABASE_PATH),
    }

    status_counts = Counter(entry["verification_status"] for entry in record_logs)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_file": _relative(input_path),
        "output_file": _relative(output_path),
        "main_dataset_modified": False,
        "sqlite_modified": False,
        "selection_policy": {
            "limit": limit,
            "themes": list(PRIORITY_THEME_LABELS.values()),
            "principle": "Select active priority-theme records with missing metadata and enrich only from explicit official evidence.",
        },
        "official_api": {
            "live_records_found": len(live_records),
            "error": api_error,
            "fallback_used": bool(api_error),
        },
        "summary": {
            "source_records": len(source_records),
            "priority_records_selected": len(selected_records),
            "records_with_new_enrichment": sum(bool(entry["changed_fields"]) for entry in record_logs),
            "field_changes": dict(sorted(_field_changes(record_logs).items())),
            "fields_still_missing": dict(sorted(_missing_field_counts(enriched_records).items())),
            "verification_status_distribution": dict(sorted(status_counts.items())),
            "selected_theme_distribution": priority_theme_distribution(selected_records),
        },
        "protected_file_hashes": {
            "before": hashes_before,
            "after": hashes_after,
            "unchanged": hashes_before == hashes_after,
        },
        "records": record_logs,
        "target_fields": list(TARGET_FIELDS),
        "next_steps": [
            "Review the enrichment log and evidence snippets.",
            "Approve enriched records through the internal dataset review panel only if the evidence is acceptable.",
            "Back up the main CSV and SQLite database before any later promotion.",
            "Run dataset audit, import, unit tests, semantic health, and retrieval QA after promotion.",
        ],
    }
    _atomic_write_json(log_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Select priority active calls from the main dataset and create an official-evidence "
            "metadata enrichment candidate file. The main CSV and SQLite database are not modified."
        )
    )
    parser.add_argument("--input", type=Path, default=MAIN_CSV_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--log", type=Path, default=LOG_PATH)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--skip-live-api", action="store_true")
    args = parser.parse_args()

    report = run_priority_enrichment(
        input_path=args.input,
        output_path=args.output,
        log_path=args.log,
        limit=args.limit,
        skip_live_api=args.skip_live_api,
    )
    summary = report["summary"]
    print("Priority call metadata enrichment")
    print(f"Source records: {summary['source_records']}")
    print(f"Priority records selected: {summary['priority_records_selected']}")
    print(f"Records with new enrichment: {summary['records_with_new_enrichment']}")
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
