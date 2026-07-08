import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.deadlines import (
    CLOSING_SOON,
    EXPIRED,
    INVALID_DEADLINE,
    OPEN_OR_UPCOMING,
    UNKNOWN_DEADLINE,
    classify_deadline,
    classify_deadline_window,
    days_until_deadline,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "eu_funding.sqlite"


def _is_missing(value: Any) -> bool:
    return value is None or not str(value).strip()


def calculate_dataset_status(
    records: Iterable[Mapping[str, Any]],
    *,
    today: date | datetime | None = None,
) -> dict[str, int]:
    status = {
        "total_records": 0,
        "open_or_upcoming_records": 0,
        "closing_soon_records": 0,
        "due_within_30_days_records": 0,
        "expired_records": 0,
        "unknown_deadline_records": 0,
        "invalid_deadline_records": 0,
        "missing_eligible_countries": 0,
        "missing_eligible_org_types": 0,
        "missing_trl_min": 0,
        "missing_trl_max": 0,
    }

    deadline_count_keys = {
        OPEN_OR_UPCOMING: "open_or_upcoming_records",
        EXPIRED: "expired_records",
        UNKNOWN_DEADLINE: "unknown_deadline_records",
        INVALID_DEADLINE: "invalid_deadline_records",
    }

    for record in records:
        status["total_records"] += 1
        deadline_status = classify_deadline(record.get("deadline_utc"), today=today)
        status[deadline_count_keys[deadline_status]] += 1
        if classify_deadline_window(record.get("deadline_utc"), today=today) == CLOSING_SOON:
            status["closing_soon_records"] += 1
        days_remaining = days_until_deadline(record.get("deadline_utc"), today=today)
        if deadline_status == OPEN_OR_UPCOMING and days_remaining is not None and days_remaining <= 30:
            status["due_within_30_days_records"] += 1

        for field in (
            "eligible_countries",
            "eligible_org_types",
            "trl_min",
            "trl_max",
        ):
            if _is_missing(record.get(field)):
                status[f"missing_{field}"] += 1

    return status


def get_dataset_status(
    *,
    db_path: Path = DB_PATH,
    today: date | datetime | None = None,
) -> dict[str, int]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                deadline_utc,
                eligible_countries,
                eligible_org_types,
                trl_min,
                trl_max
            FROM funding_calls
            """
        ).fetchall()

    return calculate_dataset_status((dict(row) for row in rows), today=today)
