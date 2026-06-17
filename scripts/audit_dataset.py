import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = PROJECT_ROOT / "data" / "imports" / "calls_seed_clean.csv"
REPORT_PATH = PROJECT_ROOT / "data" / "evaluation_outputs" / "dataset_audit_summary.json"

ENCODING_ARTIFACT_MARKERS = ("Ã", "â€”", "�", "Â", "â€", "â€™")


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_date(value: Any) -> datetime | None:
    text = _clean_value(value)
    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def is_valid_date(value: Any) -> bool:
    return _parse_date(value) is not None


def detect_encoding_artifacts(text: Any) -> list[str]:
    value = str(text or "")
    return [marker for marker in ENCODING_ARTIFACT_MARKERS if marker in value]


def classify_deadline(value: Any, today: date | datetime | None = None) -> str:
    parsed = _parse_date(value)
    if parsed is None:
        return "unknown"

    reference = today or date.today()
    reference_date = reference.date() if isinstance(reference, datetime) else reference
    return "expired" if parsed.date() < reference_date else "active_future"


def _is_missing(value: Any) -> bool:
    return not _clean_value(value)


def _looks_suspicious_deadline(value: Any) -> bool:
    text = _clean_value(value)
    return bool(text and re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text))


def _issue(row_number: int, row: pd.Series, **details: Any) -> dict[str, Any]:
    issue = {
        "row_number": row_number,
        "call_id": _clean_value(row.get("call_id")),
    }
    issue.update(details)
    return issue


def audit_dataset(csv_path: Path = CSV_PATH, today: date | datetime | None = None) -> dict[str, Any]:
    dataframe = pd.read_csv(
        csv_path,
        sep=";",
        encoding="utf-8-sig",
        dtype=str,
        keep_default_na=False,
    )

    issue_names = [
        "missing_call_id",
        "missing_call_title",
        "missing_topic_title",
        "missing_title_and_topic_title",
        "missing_deadline",
        "invalid_deadline",
        "suspicious_deadline",
        "expired_deadline",
        "active_future_deadline",
        "unknown_deadline",
        "duplicate_call_id",
        "missing_eligible_countries",
        "missing_eligible_org_types",
        "missing_trl_min",
        "missing_trl_max",
        "missing_source_url",
        "encoding_artifacts",
    ]
    issues: dict[str, list[dict[str, Any]]] = {name: [] for name in issue_names}

    call_ids = dataframe.get("call_id", pd.Series(dtype=str)).map(_clean_value)
    duplicate_ids = set(call_ids[call_ids.ne("") & call_ids.duplicated(keep=False)])

    for index, row in dataframe.iterrows():
        row_number = int(index) + 2  # CSV header occupies row 1.
        call_id = _clean_value(row.get("call_id"))
        call_title = _clean_value(row.get("call_title"))
        topic_title = _clean_value(row.get("topic_title"))
        deadline = _clean_value(row.get("deadline_utc"))

        if not call_id:
            issues["missing_call_id"].append(_issue(row_number, row))
        if not call_title:
            issues["missing_call_title"].append(_issue(row_number, row))
        if not topic_title:
            issues["missing_topic_title"].append(_issue(row_number, row))
        if not call_title and not topic_title:
            issues["missing_title_and_topic_title"].append(_issue(row_number, row))

        if not deadline:
            issues["missing_deadline"].append(_issue(row_number, row, value=deadline))
        elif not is_valid_date(deadline):
            issues["invalid_deadline"].append(_issue(row_number, row, value=deadline))

        if _looks_suspicious_deadline(deadline):
            issues["suspicious_deadline"].append(_issue(row_number, row, value=deadline))

        deadline_class = classify_deadline(deadline, today=today)
        issues[f"{deadline_class}_deadline"].append(_issue(row_number, row, value=deadline))

        if call_id in duplicate_ids:
            issues["duplicate_call_id"].append(_issue(row_number, row))

        for field, issue_name in [
            ("eligible_countries", "missing_eligible_countries"),
            ("eligible_org_types", "missing_eligible_org_types"),
            ("trl_min", "missing_trl_min"),
            ("trl_max", "missing_trl_max"),
            ("source_url", "missing_source_url"),
        ]:
            if _is_missing(row.get(field)):
                issues[issue_name].append(_issue(row_number, row))

        affected_fields: dict[str, list[str]] = {}
        for field_name, value in row.items():
            artifacts = detect_encoding_artifacts(value)
            if artifacts:
                affected_fields[str(field_name)] = artifacts
        if affected_fields:
            issues["encoding_artifacts"].append(
                _issue(row_number, row, affected_fields=affected_fields)
            )

    reference = today or date.today()
    reference_date = reference.date() if isinstance(reference, datetime) else reference
    counts = {name: len(rows) for name, rows in issues.items()}

    return {
        "source_file": str(csv_path.relative_to(PROJECT_ROOT)),
        "audit_date": reference_date.isoformat(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_rows": int(len(dataframe)),
        "counts": counts,
        "issues": issues,
    }


def write_json_report(report: dict[str, Any], output_path: Path = REPORT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def print_terminal_summary(
    report: dict[str, Any],
    output_path: Path = REPORT_PATH,
) -> None:
    counts = report["counts"]
    print("Dataset Audit Summary")
    print("=====================")
    print(f"Source: {report['source_file']}")
    print(f"Audit date: {report['audit_date']}")
    print(f"Total rows: {report['total_rows']}")
    print()

    labels = [
        ("Missing call_id", "missing_call_id"),
        ("Missing call title", "missing_call_title"),
        ("Missing topic title", "missing_topic_title"),
        ("Missing both title fields", "missing_title_and_topic_title"),
        ("Missing deadlines", "missing_deadline"),
        ("Invalid deadlines", "invalid_deadline"),
        ("Suspicious deadlines", "suspicious_deadline"),
        ("Expired deadlines", "expired_deadline"),
        ("Active/future deadlines", "active_future_deadline"),
        ("Unknown deadlines", "unknown_deadline"),
        ("Duplicate call_id rows", "duplicate_call_id"),
        ("Missing eligible countries", "missing_eligible_countries"),
        ("Missing eligible organisation types", "missing_eligible_org_types"),
        ("Missing TRL minimum", "missing_trl_min"),
        ("Missing TRL maximum", "missing_trl_max"),
        ("Missing source URLs", "missing_source_url"),
        ("Rows with encoding artifacts", "encoding_artifacts"),
    ]
    for label, key in labels:
        print(f"{label}: {counts[key]}")

    problem_keys = [
        "missing_call_id",
        "missing_title_and_topic_title",
        "invalid_deadline",
        "suspicious_deadline",
        "duplicate_call_id",
        "missing_source_url",
        "encoding_artifacts",
    ]
    print("\nPriority rows")
    print("-------------")
    found_priority_issue = False
    for key in problem_keys:
        for item in report["issues"][key]:
            found_priority_issue = True
            details = [f"row {item['row_number']}", f"call_id={item['call_id'] or '<missing>'}"]
            if "value" in item:
                details.append(f"value={item['value']!r}")
            if "affected_fields" in item:
                details.append(f"fields={','.join(item['affected_fields'])}")
            print(f"- {key}: " + "; ".join(details))
    if not found_priority_issue:
        print("No priority structural issues detected.")

    try:
        display_path = output_path.relative_to(PROJECT_ROOT)
    except ValueError:
        display_path = output_path
    print(f"\nJSON report: {display_path}")


def main() -> None:
    report = audit_dataset()
    write_json_report(report)
    print_terminal_summary(report, REPORT_PATH)


if __name__ == "__main__":
    main()
