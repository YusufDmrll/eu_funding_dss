from datetime import date, datetime
from typing import Any


OPEN_OR_UPCOMING = "open_or_upcoming"
EXPIRED = "expired"
UNKNOWN_DEADLINE = "unknown_deadline"
INVALID_DEADLINE = "invalid_deadline"


def parse_deadline(value: Any) -> datetime | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def classify_deadline(value: Any, today: date | datetime | None = None) -> str:
    if value is None or not str(value).strip():
        return UNKNOWN_DEADLINE

    parsed = parse_deadline(value)
    if parsed is None:
        return INVALID_DEADLINE

    reference = today or date.today()
    reference_date = reference.date() if isinstance(reference, datetime) else reference
    return EXPIRED if parsed.date() < reference_date else OPEN_OR_UPCOMING


def should_include_call(
    deadline_value: Any,
    *,
    include_expired: bool = False,
    today: date | datetime | None = None,
) -> bool:
    status = classify_deadline(deadline_value, today=today)
    return include_expired or status != EXPIRED
