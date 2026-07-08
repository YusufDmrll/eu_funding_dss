import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


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
from scripts.audit_dataset import audit_dataset, detect_encoding_artifacts  # noqa: E402
from scripts.expand_dataset_from_eu_api import CSV_COLUMNS  # noqa: E402


MAIN_CSV = PROJECT_ROOT / "data" / "imports" / "calls_seed_clean.csv"
SQLITE_DB = PROJECT_ROOT / "data" / "eu_funding.sqlite"
CANDIDATES_CSV = PROJECT_ROOT / "data" / "imports" / "eu_calls_promotion_candidates_enriched.csv"
CSV_BACKUP_DIR = PROJECT_ROOT / "data" / "imports" / "backups"
SQLITE_BACKUP_DIR = PROJECT_ROOT / "data" / "backups"
ARCHIVE_DIR = PROJECT_ROOT / "data" / "imports" / "archives"
LOG_PATH = PROJECT_ROOT / "data" / "evaluation_outputs" / "active_call_library_promotion_log.json"
DEFAULT_TARGET_ACTIVE = 300


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


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
            writer.writerow({field: record.get(field, "") for field in CSV_COLUMNS})
    os.replace(temporary, path)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def _row_has_encoding_artifacts(record: dict[str, Any]) -> bool:
    return any(detect_encoding_artifacts(value) for value in record.values())


def _has_required_fields(record: dict[str, Any]) -> bool:
    has_title = bool(str(record.get("call_title") or record.get("topic_title") or "").strip())
    return all(
        [
            str(record.get("call_id") or "").strip(),
            has_title,
            len(str(record.get("description") or "").strip()) > 20,
            str(record.get("source_url") or "").strip(),
        ]
    )


def _schema_matches(path: Path) -> bool:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=";")
        header = next(reader, [])
    return header == CSV_COLUMNS


def _split_main_records(records: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]], Counter[str]]:
    active: list[dict[str, str]] = []
    archived: list[dict[str, str]] = []
    status_counts: Counter[str] = Counter()
    for record in records:
        status = classify_deadline(record.get("deadline_utc"))
        status_counts[status] += 1
        if status == OPEN_OR_UPCOMING:
            active.append(record)
        else:
            archived.append(record)
    return active, archived, status_counts


def _select_candidates(
    candidates: list[dict[str, str]],
    *,
    existing_ids: set[str],
    needed: int,
) -> tuple[list[dict[str, str]], Counter[str]]:
    selected: list[dict[str, str]] = []
    skipped: Counter[str] = Counter()
    seen = set(existing_ids)

    if needed <= 0:
        skipped["not_needed_after_target_reached"] = len(candidates)
        return selected, skipped

    for record in candidates:
        call_id = str(record.get("call_id") or "").strip()
        if not call_id:
            skipped["missing_call_id"] += 1
            continue
        if call_id in seen:
            skipped["duplicate_or_existing_call_id"] += 1
            continue
        if not _has_required_fields(record):
            skipped["missing_required_field"] += 1
            continue
        if _row_has_encoding_artifacts(record):
            skipped["encoding_artifact"] += 1
            continue

        deadline_status = classify_deadline(record.get("deadline_utc"))
        if deadline_status != OPEN_OR_UPCOMING:
            skipped[deadline_status] += 1
            continue

        selected.append({field: record.get(field, "") for field in CSV_COLUMNS})
        seen.add(call_id)
        if len(selected) >= needed:
            break

    skipped["not_needed_after_target_reached"] += max(0, len(candidates) - len(selected) - sum(skipped.values()))
    return selected, skipped


def build_active_library(
    *,
    main_csv: Path = MAIN_CSV,
    candidates_csv: Path = CANDIDATES_CSV,
    target_active: int = DEFAULT_TARGET_ACTIVE,
    apply: bool = False,
    log_path: Path = LOG_PATH,
) -> dict[str, Any]:
    if target_active <= 0:
        raise ValueError("target_active must be positive.")
    if not _schema_matches(main_csv):
        raise ValueError(f"Main CSV schema does not match expected schema: {main_csv}")
    if not _schema_matches(candidates_csv):
        raise ValueError(f"Candidate CSV schema does not match expected schema: {candidates_csv}")

    main_records = _read_csv(main_csv)
    candidate_records = _read_csv(candidates_csv)
    main_active, main_archived, pre_status_counts = _split_main_records(main_records)
    existing_active_ids = {record["call_id"] for record in main_active if record.get("call_id")}
    needed = max(0, target_active - len(main_active))
    selected, skipped = _select_candidates(candidate_records, existing_ids=existing_active_ids, needed=needed)
    updated_records = main_active + selected
    post_status_counts = Counter(classify_deadline(record.get("deadline_utc")) for record in updated_records)

    stamp = _timestamp()
    csv_backup = CSV_BACKUP_DIR / f"calls_seed_clean_before_active_library_{stamp}.csv"
    sqlite_backup = SQLITE_BACKUP_DIR / f"eu_funding_before_active_library_{stamp}.sqlite"
    archive_file = ARCHIVE_DIR / f"calls_seed_expired_archive_{stamp}.csv"

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "applied": apply,
        "target_active_records": target_active,
        "source_files": {
            "main_csv": str(main_csv.relative_to(PROJECT_ROOT)),
            "candidates_csv": str(candidates_csv.relative_to(PROJECT_ROOT)),
            "sqlite": str(SQLITE_DB.relative_to(PROJECT_ROOT)),
        },
        "hashes_before": {
            "main_csv": _sha256(main_csv),
            "sqlite": _sha256(SQLITE_DB),
            "candidates_csv": _sha256(candidates_csv),
        },
        "pre_counts": {
            "main_rows": len(main_records),
            "main_deadline_status": dict(pre_status_counts),
            "candidate_rows": len(candidate_records),
        },
        "promotion": {
            "active_records_preserved": len(main_active),
            "archived_non_active_records": len(main_archived),
            "new_records_selected": len(selected),
            "target_reached": len(updated_records) >= target_active,
            "candidate_skip_reasons": dict(skipped),
        },
        "post_counts_planned": {
            "main_rows": len(updated_records),
            "deadline_status": dict(post_status_counts),
        },
        "created_files": {},
        "notes": [
            "Expired or invalid-deadline records are removed from the active CSV and written to an archive file.",
            "Uncertain TRL, eligibility, consortium, partner, and budget values are preserved as blank when not officially supported.",
            "Run scripts/import_calls.py --replace after applying so SQLite exactly matches the active CSV.",
        ],
    }

    if apply:
        CSV_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        SQLITE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(main_csv, csv_backup)
        if SQLITE_DB.exists():
            shutil.copy2(SQLITE_DB, sqlite_backup)
        if main_archived:
            _atomic_write_csv(archive_file, main_archived)
        _atomic_write_csv(main_csv, updated_records)
        payload["created_files"] = {
            "main_csv_backup": str(csv_backup.relative_to(PROJECT_ROOT)),
            "sqlite_backup": str(sqlite_backup.relative_to(PROJECT_ROOT)) if sqlite_backup.exists() else "",
            "expired_archive": str(archive_file.relative_to(PROJECT_ROOT)) if main_archived else "",
        }
        payload["hashes_after"] = {
            "main_csv": _sha256(main_csv),
            "sqlite": _sha256(SQLITE_DB),
            "candidates_csv": _sha256(candidates_csv),
        }
        payload["post_audit"] = {
            "total_rows": audit_dataset(main_csv)["total_rows"],
            "counts": audit_dataset(main_csv)["counts"],
        }

    _atomic_write_json(log_path, payload)
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely promote active/upcoming EU call candidates into the main active library."
    )
    parser.add_argument("--main-csv", type=Path, default=MAIN_CSV)
    parser.add_argument("--candidates", type=Path, default=CANDIDATES_CSV)
    parser.add_argument("--target-active", type=int, default=DEFAULT_TARGET_ACTIVE)
    parser.add_argument("--log", type=Path, default=LOG_PATH)
    parser.add_argument("--apply", action="store_true", help="Actually update the main CSV and write backups/archives.")
    return parser


def main() -> int:
    args = _parser().parse_args()
    payload = build_active_library(
        main_csv=args.main_csv,
        candidates_csv=args.candidates,
        target_active=args.target_active,
        apply=args.apply,
        log_path=args.log,
    )
    mode = "APPLIED" if payload["applied"] else "DRY RUN"
    print(f"Active call library promotion: {mode}")
    print(f"Target active records: {payload['target_active_records']}")
    print(f"Active records preserved: {payload['promotion']['active_records_preserved']}")
    print(f"Archived non-active records: {payload['promotion']['archived_non_active_records']}")
    print(f"New records selected: {payload['promotion']['new_records_selected']}")
    print(f"Planned/updated main rows: {payload['post_counts_planned']['main_rows']}")
    print(f"Target reached: {payload['promotion']['target_reached']}")
    print(f"Log: {args.log}")
    if not payload["applied"]:
        print("No main dataset files were modified. Re-run with --apply to promote.")
    return 0 if payload["promotion"]["target_reached"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
