from typing import Any
from urllib.parse import quote


EU_TOPIC_DETAILS_BASE_URL = (
    "https://ec.europa.eu/info/funding-tenders/opportunities/portal/"
    "screen/opportunities/topic-details"
)


def canonical_official_topic_url(call_id: Any, source_url: Any = "") -> str:
    """Return a readable official topic-details URL when the topic id is available."""
    topic_id = str(call_id or "").strip()
    if topic_id:
        return f"{EU_TOPIC_DETAILS_BASE_URL}/{quote(topic_id, safe='')}"
    return str(source_url or "").strip()


def official_source_label(call_id: Any) -> str:
    topic_id = str(call_id or "").strip()
    return f"Open official topic page ({topic_id})" if topic_id else "Open official source"
