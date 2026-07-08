import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.deadlines import OPEN_OR_UPCOMING, classify_deadline  # noqa: E402
from scripts.expand_dataset_from_eu_api import CSV_COLUMNS  # noqa: E402


DEFAULT_BEFORE = PROJECT_ROOT / "data" / "evaluation_outputs" / "calls_seed_clean_before_refresh.csv"
DEFAULT_AFTER = PROJECT_ROOT / "data" / "imports" / "calls_seed_clean.csv"
DEFAULT_JSON = PROJECT_ROOT / "data" / "evaluation_outputs" / "call_library_change_summary.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "data" / "evaluation_outputs" / "call_library_change_summary.md"

IMPORTANT_METADATA_FIELDS = (
    "trl_min",
    "trl_max",
    "eligible_countries",
    "eligible_org_types",
    "consortium_required",
    "min_partners",
)

THEME_KEYWORDS = {
    "Maritime / ports / logistics": (
        "maritime",
        "port",
        "ports",
        "harbour",
        "shipping",
        "ship",
        "vessel",
        "terminal",
        "logistics",
        "freight",
        "waterborne",
    ),
    "Green energy / hydrogen": (
        "hydrogen",
        "renewable",
        "green energy",
        "clean energy",
        "energy transition",
        "decarbon",
        "electrification",
        "offshore wind",
        "solar",
        "storage",
        "shore power",
    ),
    "Critical materials / circularity": (
        "critical raw material",
        "strategic raw material",
        "raw material",
        "battery",
        "batteries",
        "recycling",
        "circular",
        "secondary raw materials",
        "resource efficiency",
    ),
    "Security / resilience": (
        "security",
        "cybersecurity",
        "critical infrastructure",
        "resilience",
        "disaster",
        "civil protection",
        "crisis management",
        "emergency",
    ),
    "Digital / AI / automation": (
        "digital infrastructure",
        "artificial intelligence",
        " ai ",
        "automation",
        "data space",
        "digital twin",
        "cloud",
        "robotics",
    ),
    "SME / start-up / scale-up": (
        "sme",
        "smes",
        "startup",
        "start-up",
        "scale-up",
        "innovation ecosystem",
        "market uptake",
        "commercialisation",
        "commercialization",
    ),
    "Transport / mobility / supply chain": (
        "transport",
        "mobility",
        "supply chain",
        "multimodal",
        "rail",
        "road transport",
        "aviation",
        "urban mobility",
    ),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def read_records(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def _record_by_id(records: Iterable[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {
        _clean(record.get("call_id")): record
        for record in records
        if _clean(record.get("call_id"))
    }


def _record_text(record: dict[str, Any]) -> str:
    fields = ("call_title", "topic_title", "description", "objectives", "expected_impact", "keywords")
    return " ".join(_clean(record.get(field)).lower() for field in fields)


def detect_record_themes(record: dict[str, Any]) -> list[str]:
    text = " " + _record_text(record).replace("-", " ") + " "
    themes = [
        theme
        for theme, terms in THEME_KEYWORDS.items()
        if any(term in text for term in terms)
    ]
    return themes or ["Other / needs review"]


def missing_metadata_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in IMPORTANT_METADATA_FIELDS if not _clean(record.get(field))]


def _title(record: dict[str, Any]) -> str:
    return _clean(record.get("call_title") or record.get("topic_title") or record.get("call_id"))


def _short_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "call_id": _clean(record.get("call_id")),
        "title": _title(record),
        "deadline_utc": _clean(record.get("deadline_utc")),
        "deadline_status": classify_deadline(record.get("deadline_utc")),
        "themes": detect_record_themes(record)[:3],
        "source_url": _clean(record.get("source_url")),
    }


def _deadline_counts(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(classify_deadline(record.get("deadline_utc")) for record in records))


def _theme_counts(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for record in records:
        for theme in detect_record_themes(record):
            counter[theme] += 1
    return dict(counter.most_common())


def _metadata_missing_counts(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for record in records:
        for field in missing_metadata_fields(record):
            counter[field] += 1
    return dict(counter)


def _changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return [
        field
        for field in CSV_COLUMNS
        if _clean(before.get(field)) != _clean(after.get(field))
    ]


def summarize_changes(before_path: Path, after_path: Path) -> dict[str, Any]:
    before_records = read_records(before_path)
    after_records = read_records(after_path)
    before_by_id = _record_by_id(before_records)
    after_by_id = _record_by_id(after_records)

    before_ids = set(before_by_id)
    after_ids = set(after_by_id)
    added_ids = sorted(after_ids - before_ids)
    removed_ids = sorted(before_ids - after_ids)
    kept_ids = sorted(before_ids & after_ids)
    modified = [
        {
            "call_id": call_id,
            "title": _title(after_by_id[call_id]),
            "changed_fields": _changed_fields(before_by_id[call_id], after_by_id[call_id]),
        }
        for call_id in kept_ids
        if _changed_fields(before_by_id[call_id], after_by_id[call_id])
    ]

    added_records = [after_by_id[call_id] for call_id in added_ids]
    removed_records = [before_by_id[call_id] for call_id in removed_ids]
    after_active = [
        record for record in after_records if classify_deadline(record.get("deadline_utc")) == OPEN_OR_UPCOMING
    ]
    added_active = [
        record for record in added_records if classify_deadline(record.get("deadline_utc")) == OPEN_OR_UPCOMING
    ]

    return {
        "generated_at_utc": _utc_now(),
        "source_files": {
            "before": _relative(before_path),
            "after": _relative(after_path),
        },
        "counts": {
            "before_rows": len(before_records),
            "after_rows": len(after_records),
            "active_after_rows": len(after_active),
            "added": len(added_records),
            "added_active": len(added_active),
            "removed_or_archived": len(removed_records),
            "modified_existing": len(modified),
        },
        "deadline_status_after": _deadline_counts(after_records),
        "added_theme_counts": _theme_counts(added_records),
        "after_theme_counts": _theme_counts(after_records),
        "added_missing_metadata": _metadata_missing_counts(added_records),
        "after_missing_metadata": _metadata_missing_counts(after_records),
        "added_examples": [_short_record(record) for record in added_records[:12]],
        "removed_or_archived_examples": [_short_record(record) for record in removed_records[:12]],
        "modified_examples": modified[:12],
        "quality_flags": build_quality_flags(added_records, after_records),
    }


def build_quality_flags(added_records: list[dict[str, Any]], after_records: list[dict[str, Any]]) -> list[str]:
    flags: list[str] = []
    deadline_counts = Counter(classify_deadline(record.get("deadline_utc")) for record in after_records)
    if deadline_counts.get(OPEN_OR_UPCOMING, 0) != len(after_records):
        flags.append("The refreshed active CSV contains non-active deadline records; review before merging.")

    missing_sources = [record for record in after_records if not _clean(record.get("source_url"))]
    if missing_sources:
        flags.append(f"{len(missing_sources)} refreshed records are missing official source URLs.")

    low_signal_added = [
        record
        for record in added_records
        if detect_record_themes(record) == ["Other / needs review"]
    ]
    if low_signal_added:
        flags.append(f"{len(low_signal_added)} added records did not match the core theme keywords.")

    if not flags:
        flags.append("No blocking quality flags detected by the automated summary.")
    return flags


def _markdown_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "_None._"
    lines = ["| Call ID | Title | Deadline | Themes |", "|---|---|---:|---|"]
    for row in rows:
        title = _clean(row["title"])
        if len(title) > 95:
            title = title[:92].rstrip() + "..."
        lines.append(
            "| "
            + " | ".join(
                [
                    _clean(row["call_id"]),
                    title.replace("|", "/"),
                    _clean(row["deadline_utc"]),
                    ", ".join(row["themes"]).replace("|", "/"),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def render_markdown(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    added_themes = summary["added_theme_counts"]
    top_added_themes = ", ".join(
        f"{theme}: {count}" for theme, count in list(added_themes.items())[:6]
    ) or "No added records"
    quality_flags = "\n".join(f"- {flag}" for flag in summary["quality_flags"])
    missing = summary["added_missing_metadata"]
    missing_text = ", ".join(f"{field}: {count}" for field, count in sorted(missing.items())) or "No added metadata gaps"

    return f"""## Active call library change summary

**Rows:** {counts['before_rows']} -> {counts['after_rows']}  
**Active/upcoming rows after refresh:** {counts['active_after_rows']}  
**Added active records:** {counts['added_active']}  
**Removed or archived records:** {counts['removed_or_archived']}  
**Modified existing records:** {counts['modified_existing']}

### Added theme mix

{top_added_themes}

### Added-record metadata gaps

{missing_text}

### Automated quality flags

{quality_flags}

### Added record examples

{_markdown_table(summary['added_examples'][:8])}

### Removed or archived examples

{_markdown_table(summary['removed_or_archived_examples'][:8])}
"""


def write_outputs(summary: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(render_markdown(summary), encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize changes between two EU call-library CSV files.")
    parser.add_argument("--before", type=Path, default=DEFAULT_BEFORE)
    parser.add_argument("--after", type=Path, default=DEFAULT_AFTER)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    return parser


def main() -> int:
    args = _parser().parse_args()
    summary = summarize_changes(args.before, args.after)
    write_outputs(summary, args.json, args.markdown)
    print(render_markdown(summary))
    print(f"JSON: {args.json}")
    print(f"Markdown: {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
