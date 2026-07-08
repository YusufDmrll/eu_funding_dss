from datetime import date, datetime
from typing import Any


OPEN_OR_UPCOMING = "open_or_upcoming"
CLOSING_SOON = "closing_soon"
EXPIRED = "expired"
UNKNOWN_DEADLINE = "unknown_deadline"
INVALID_DEADLINE = "invalid_deadline"
DEFAULT_CLOSING_SOON_DAYS = 90
URGENT_DEADLINE_DAYS = 14
NEAR_TERM_DEADLINE_DAYS = 30


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


def days_until_deadline(value: Any, today: date | datetime | None = None) -> int | None:
    parsed = parse_deadline(value)
    if parsed is None:
        return None
    reference = today or date.today()
    reference_date = reference.date() if isinstance(reference, datetime) else reference
    return (parsed.date() - reference_date).days


def _format_deadline_date(parsed: datetime | None) -> str:
    return parsed.strftime("%d %b %Y") if parsed is not None else ""


def _days_phrase(days_remaining: int) -> str:
    if days_remaining == 0:
        return "Closes today"
    if days_remaining == 1:
        return "Closes tomorrow"
    return f"Closes in {days_remaining} days"


def build_deadline_urgency(
    value: Any,
    today: date | datetime | None = None,
) -> dict[str, Any]:
    parsed = parse_deadline(value)
    status = classify_deadline(value, today=today)
    date_text = _format_deadline_date(parsed)

    if status == UNKNOWN_DEADLINE:
        return {
            "status": status,
            "urgency": "needs_confirmation",
            "label": "Deadline not listed",
            "short_text": "Deadline not listed",
            "detail": "Confirm timing on the official source",
            "date_text": date_text,
            "days_remaining": None,
            "needs_attention": True,
            "action": "Confirm the official deadline before shortlisting this call.",
        }

    if status == INVALID_DEADLINE:
        return {
            "status": status,
            "urgency": "needs_confirmation",
            "label": "Deadline needs confirmation",
            "short_text": "Deadline needs confirmation",
            "detail": "Confirm timing on the official source",
            "date_text": date_text,
            "days_remaining": None,
            "needs_attention": True,
            "action": "Confirm the official deadline before shortlisting this call.",
        }

    if status == EXPIRED:
        return {
            "status": status,
            "urgency": "archived",
            "label": "Archived",
            "short_text": "Archived",
            "detail": f"Expired - {date_text}" if date_text else "Expired",
            "date_text": date_text,
            "days_remaining": days_until_deadline(value, today=today),
            "needs_attention": True,
            "action": "Do not treat this as a current opportunity unless the official source has reopened it.",
        }

    days_remaining = days_until_deadline(value, today=today)
    if days_remaining is None:
        return {
            "status": status,
            "urgency": "needs_confirmation",
            "label": "Deadline needs confirmation",
            "short_text": "Deadline needs confirmation",
            "detail": "Confirm timing on the official source",
            "date_text": date_text,
            "days_remaining": None,
            "needs_attention": True,
            "action": "Confirm the official deadline before shortlisting this call.",
        }

    phrase = _days_phrase(days_remaining)
    if days_remaining <= URGENT_DEADLINE_DAYS:
        return {
            "status": status,
            "urgency": "urgent",
            "label": "Urgent deadline",
            "short_text": phrase,
            "detail": f"{phrase} - {date_text}",
            "date_text": date_text,
            "days_remaining": days_remaining,
            "needs_attention": True,
            "action": "Check scope and team capacity immediately; only pursue if proposal work can start now.",
        }
    if days_remaining <= NEAR_TERM_DEADLINE_DAYS:
        return {
            "status": status,
            "urgency": "closing_soon",
            "label": "Closing soon",
            "short_text": phrase,
            "detail": f"{phrase} - {date_text}",
            "date_text": date_text,
            "days_remaining": days_remaining,
            "needs_attention": True,
            "action": "Check the official deadline and decide quickly whether this belongs in the active shortlist.",
        }
    if days_remaining <= DEFAULT_CLOSING_SOON_DAYS:
        return {
            "status": status,
            "urgency": "review_timing",
            "label": "Review timing soon",
            "short_text": phrase,
            "detail": f"{phrase} - {date_text}",
            "date_text": date_text,
            "days_remaining": days_remaining,
            "needs_attention": True,
            "action": "Review the deadline early and set a go/no-go decision before deeper proposal work.",
        }

    return {
        "status": status,
        "urgency": "normal",
        "label": "Open or upcoming",
        "short_text": f"Deadline {date_text}" if date_text else "Open or upcoming",
        "detail": date_text or "Open or upcoming",
        "date_text": date_text,
        "days_remaining": days_remaining,
        "needs_attention": False,
        "action": "Check the official deadline as part of normal shortlisting.",
    }


def classify_deadline_window(
    value: Any,
    today: date | datetime | None = None,
    *,
    closing_soon_days: int = DEFAULT_CLOSING_SOON_DAYS,
) -> str:
    base_status = classify_deadline(value, today=today)
    if base_status != OPEN_OR_UPCOMING:
        return base_status

    remaining_days = days_until_deadline(value, today=today)
    if remaining_days is not None and remaining_days <= closing_soon_days:
        return CLOSING_SOON
    return OPEN_OR_UPCOMING


def should_include_call(
    deadline_value: Any,
    *,
    include_expired: bool = False,
    today: date | datetime | None = None,
) -> bool:
    status = classify_deadline(deadline_value, today=today)
    return include_expired or status != EXPIRED
