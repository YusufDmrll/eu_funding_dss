import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.client_experience import (
    build_call_strategy,
    build_review_status_reason,
    prioritize_client_results,
)
from core.deadlines import build_deadline_urgency
from core.input_quality import evaluate_project_description
from core.retrieval import DEFAULT_END_USER_RETRIEVAL_MODE, execute_retrieval
from core.scoring import determine_client_review_status


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WATCHLIST_PATH = PROJECT_ROOT / "data" / "watchlist" / "gillis_watchlist.json"
STATUS_ORDER = {
    "Needs more detail": 0,
    "Worth reviewing": 1,
    "Strong match": 2,
}
ENCODING_REPLACEMENTS = {
    "\u00e2\u20ac\u201c": "-",
    "\u00e2\u20ac\u201d": "-",
    "\u00e2\u20ac\u02dc": "'",
    "\u00e2\u20ac\u2122": "'",
    "\u00e2\u20ac\u0153": '"',
    "\u00e2\u20ac\ufffd": '"',
    "\ufffd": "",
}


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_int_percentage(value: Any) -> int:
    try:
        return int(round(float(value or 0.0) * 100))
    except (TypeError, ValueError):
        return 0


def _safe_score(value: Any) -> int:
    try:
        return int(round(float(value or 0.0)))
    except (TypeError, ValueError):
        return 0


def _shorten(value: str, limit: int = 180) -> str:
    text = " ".join(clean_display_text(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def clean_display_text(value: Any) -> str:
    text = str(value or "")
    for source, replacement in ENCODING_REPLACEMENTS.items():
        text = text.replace(source, replacement)
    return text


def _project_inputs(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_title": item.get("title", ""),
        "project_desc": item.get("project_description", ""),
        "user_country": item.get("country", ""),
        "user_org_type": item.get("organisation_type", ""),
        "user_trl": item.get("trl"),
        "has_consortium": bool(item.get("has_consortium", False)),
    }


def status_at_least(status: str, minimum: str) -> bool:
    return STATUS_ORDER.get(status, -1) >= STATUS_ORDER.get(minimum, 0)


def load_watchlist_items(path: Path = DEFAULT_WATCHLIST_PATH) -> list[dict[str, Any]]:
    items = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError("Watchlist file must contain a list of project themes.")

    cleaned: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Watchlist item {index} is not an object.")
        missing = [field for field in ("id", "title", "project_description") if not str(item.get(field) or "").strip()]
        if missing:
            raise ValueError(f"Watchlist item {index} is missing required fields: {', '.join(missing)}")
        cleaned.append(item)
    return cleaned


def load_call_ids_from_csv(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            str(row.get("call_id") or "").strip()
            for row in csv.DictReader(handle, delimiter=";")
            if str(row.get("call_id") or "").strip()
        }


def _serialize_result(
    result: dict[str, Any],
    item: dict[str, Any],
    *,
    input_quality: dict[str, Any],
    retrieval_mode_used: str,
    previous_call_ids: set[str] | None,
) -> dict[str, Any]:
    project_inputs = _project_inputs(item)
    status = determine_client_review_status(
        result.get("similarity_score"),
        input_quality=input_quality,
        retrieval_mode=retrieval_mode_used,
        internal_confidence_label=result.get("match_confidence_label"),
        theme_coherence=result.get("theme_coherence"),
    )
    strategy = build_call_strategy(result, project_inputs)
    deadline = build_deadline_urgency(result.get("deadline_utc"))
    call_id = str(result.get("call_id") or "").strip()
    is_new_call = None if previous_call_ids is None else call_id not in previous_call_ids

    return {
        "call_id": call_id,
        "call_title": clean_display_text(result.get("call_title") or result.get("topic_title") or ""),
        "programme": clean_display_text(result.get("program") or ""),
        "cluster": clean_display_text(result.get("cluster") or ""),
        "source_url": result.get("source_url") or "",
        "deadline_utc": result.get("deadline_utc") or "",
        "deadline_label": clean_display_text(deadline["short_text"]),
        "deadline_urgency": deadline["urgency"],
        "overall_fit": _safe_score(result.get("strategic_success_index")),
        "relevance": _safe_int_percentage(result.get("similarity_score")),
        "review_status": status,
        "status_reason": clean_display_text(build_review_status_reason(result, status, input_quality=input_quality)),
        "why_matched": clean_display_text(result.get("match_explanation") or ""),
        "what_to_clarify": [clean_display_text(item) for item in strategy["clarifications"][:2]],
        "next_steps": [clean_display_text(item) for item in strategy["next_steps"][:3]],
        "shared_themes": (result.get("theme_coherence") or {}).get("shared_themes") or [],
        "guardrails": (result.get("theme_coherence") or {}).get("guardrails") or [],
        "is_new_call": is_new_call,
    }


def build_watchlist_report(
    items: list[dict[str, Any]],
    *,
    previous_call_ids: set[str] | None = None,
    top_k: int = 5,
    retrieval_mode: str = DEFAULT_END_USER_RETRIEVAL_MODE,
    sort_by: str = "strategic_success_index",
) -> dict[str, Any]:
    evaluations: list[dict[str, Any]] = []
    mode_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    new_top_result_count = 0 if previous_call_ids is not None else None
    watchlist_items_with_new_results = 0 if previous_call_ids is not None else None
    warning_count = 0

    for item in items:
        description = str(item.get("project_description") or "")
        input_quality = evaluate_project_description(description)
        execution = execute_retrieval(
            project_text=description,
            top_k=max(top_k, 8),
            user_country=str(item.get("country") or ""),
            user_org_type=str(item.get("organisation_type") or ""),
            user_trl=item.get("trl"),
            has_consortium=bool(item.get("has_consortium", False)),
            sort_by=sort_by,
            retrieval_mode=retrieval_mode,
            allow_semantic_fallback=True,
            include_expired=False,
        )
        mode_used = execution["retrieval_mode_used"]
        mode_counts[mode_used] += 1
        if execution.get("warning"):
            warning_count += 1

        ordered_results = prioritize_client_results(execution["results"], description)[:top_k]
        serialized_results = [
            _serialize_result(
                result,
                item,
                input_quality=input_quality,
                retrieval_mode_used=mode_used,
                previous_call_ids=previous_call_ids,
            )
            for result in ordered_results
        ]

        status_counts.update(result["review_status"] for result in serialized_results)
        item_new_results = [
            result
            for result in serialized_results
            if result["is_new_call"] is True and status_at_least(result["review_status"], "Worth reviewing")
        ]
        if previous_call_ids is not None:
            new_top_result_count = int(new_top_result_count or 0) + len(item_new_results)
            if item_new_results:
                watchlist_items_with_new_results = int(watchlist_items_with_new_results or 0) + 1

        evaluations.append(
            {
                "id": item["id"],
                "title": clean_display_text(item["title"]),
                "theme": clean_display_text(item.get("theme", "")),
                "notes": clean_display_text(item.get("notes", "")),
                "input_quality": input_quality,
                "retrieval_mode_requested": retrieval_mode,
                "retrieval_mode_used": mode_used,
                "warning": execution.get("warning"),
                "results": serialized_results,
                "new_reviewable_result_count": len(item_new_results),
            }
        )

    return {
        "generated_at_utc": _utc_now(),
        "watchlist_count": len(items),
        "top_k": top_k,
        "sort_by": sort_by,
        "previous_library_comparison": previous_call_ids is not None,
        "summary": {
            "retrieval_mode_counts": dict(mode_counts),
            "warning_count": warning_count,
            "status_counts": dict(status_counts),
            "new_reviewable_top_results": new_top_result_count,
            "watchlist_items_with_new_reviewable_results": watchlist_items_with_new_results,
        },
        "evaluations": evaluations,
    }


def render_watchlist_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Gillis Watchlist Match Report",
        "",
        f"Generated: {report['generated_at_utc']}",
        "",
        "## Summary",
        "",
        f"- Watchlist themes checked: {report['watchlist_count']}",
        f"- Retrieval modes used: {summary['retrieval_mode_counts']}",
        (
            f"- Results with reviewable status on newly added calls: {summary['new_reviewable_top_results']}"
            if report.get("previous_library_comparison")
            else "- New-call comparison: not run for this report"
        ),
        (
            f"- Watchlist themes with at least one new reviewable call: {summary['watchlist_items_with_new_reviewable_results']}"
            if report.get("previous_library_comparison")
            else "- Watchlist themes with new reviewable calls: not available without a previous snapshot"
        ),
        "",
        "This report is a review aid after a dataset refresh. It does not confirm eligibility, consortium rules, or funding probability.",
        "",
    ]

    if not report.get("previous_library_comparison"):
        lines.extend(
            [
                "> No previous call-library snapshot was supplied, so new-call flags are not shown.",
                "",
            ]
        )

    for evaluation in report["evaluations"]:
        lines.extend(
            [
                f"## {evaluation['title']}",
                "",
                f"Theme: {evaluation.get('theme') or 'Not specified'}",
                "",
            ]
        )
        if evaluation.get("warning"):
            lines.extend([f"Warning: {evaluation['warning']}", ""])
        if not evaluation["results"]:
            lines.extend(["No current active/upcoming matches were returned.", ""])
            continue

        lines.extend(
            [
                "| New | Status | Fit | Relevance | Deadline | Call | Next action |",
                "| --- | --- | ---: | ---: | --- | --- | --- |",
            ]
        )
        for result in evaluation["results"]:
            new_label = "Yes" if result["is_new_call"] is True else "No" if result["is_new_call"] is False else "-"
            source = result["source_url"]
            title = _shorten(str(result["call_title"]), 105)
            call_label = f"[{title}]({source})" if source else title
            next_action = _shorten(result["next_steps"][0] if result["next_steps"] else result["status_reason"], 140)
            lines.append(
                f"| {new_label} | {result['review_status']} | {result['overall_fit']} | {result['relevance']}% | "
                f"{result['deadline_label']} | {call_label} | {next_action} |"
            )
        lines.append("")

    return "\n".join(lines)


def flatten_watchlist_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for evaluation in report["evaluations"]:
        for rank, result in enumerate(evaluation["results"], start=1):
            rows.append(
                {
                    "watchlist_id": evaluation["id"],
                    "watchlist_title": evaluation["title"],
                    "rank": rank,
                    "is_new_call": result["is_new_call"],
                    "review_status": result["review_status"],
                    "overall_fit": result["overall_fit"],
                    "relevance": result["relevance"],
                    "deadline": result["deadline_label"],
                    "call_id": result["call_id"],
                    "call_title": result["call_title"],
                    "why_matched": result["why_matched"],
                    "status_reason": result["status_reason"],
                    "next_action": result["next_steps"][0] if result["next_steps"] else "",
                    "source_url": result["source_url"],
                }
            )
    return rows
