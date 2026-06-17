import csv
import json
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.retrieval import RETRIEVAL_MODE_LABELS, execute_retrieval

DATASET_PATH = PROJECT_ROOT / "data" / "retrieval_evaluation_cases.json"
OUTPUT_DIR = PROJECT_ROOT / "data" / "evaluation_outputs"
TOP_K = 3
DEFAULT_SORT_BY = "strategic_success_index"
MANUAL_REVIEW_FIELDS = [
    "better_mode",
    "lexical_overall_review",
    "semantic_overall_review",
    "reviewer_notes",
]


def load_evaluation_cases(path: Path = DATASET_PATH) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _serialize_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "call_id": result.get("call_id"),
        "call_title": result.get("call_title"),
        "program": result.get("program"),
        "cluster": result.get("cluster"),
        "deadline_utc": result.get("deadline_utc"),
        "similarity_score": round(float(result.get("similarity_score", 0.0)), 4),
        "strategic_fit_score": round(float(result.get("strategic_success_index", 0.0)), 2),
        "confidence": result.get("match_confidence_label"),
        "eligibility": result.get("eligibility_status"),
        "why_this_matched": result.get("match_explanation"),
    }


def _build_mode_output(case: dict[str, Any], retrieval_mode: str) -> dict[str, Any]:
    execution = execute_retrieval(
        project_text=case["project_description"],
        top_k=TOP_K,
        sort_by=DEFAULT_SORT_BY,
        retrieval_mode=retrieval_mode,
        allow_semantic_fallback=True,
    )

    return {
        "mode_requested": retrieval_mode,
        "mode_used": execution["retrieval_mode_used"],
        "mode_label_used": RETRIEVAL_MODE_LABELS.get(execution["retrieval_mode_used"], execution["retrieval_mode_used"]),
        "warning": execution["warning"],
        "results": [_serialize_result(result) for result in execution["results"]],
    }


def build_evaluation_report(cases: list[dict[str, Any]]) -> dict[str, Any]:
    generated_at = datetime.now(UTC).isoformat()
    evaluations = []

    for case in cases:
        evaluations.append(
            {
                "eval_id": case["eval_id"],
                "theme": case["theme"],
                "project_title": case["project_title"],
                "project_description": case["project_description"],
                "expected_fit_notes": case["expected_fit_notes"],
                "must_have_signals": case["must_have_signals"],
                "likely_false_positive_patterns": case["likely_false_positive_patterns"],
                "ranking_basis": DEFAULT_SORT_BY,
                "lexical": _build_mode_output(case, "lexical"),
                "semantic": _build_mode_output(case, "semantic"),
                "manual_review": {
                    "better_mode": "",
                    "lexical_overall_review": "",
                    "semantic_overall_review": "",
                    "reviewer_notes": "",
                },
            }
        )

    return {
        "generated_at_utc": generated_at,
        "dataset_path": str(DATASET_PATH),
        "top_k": TOP_K,
        "ranking_basis": DEFAULT_SORT_BY,
        "evaluations": evaluations,
    }


def _build_csv_row(evaluation: dict[str, Any]) -> dict[str, Any]:
    row = {
        "eval_id": evaluation["eval_id"],
        "theme": evaluation["theme"],
        "project_title": evaluation["project_title"],
        "expected_fit_notes": evaluation["expected_fit_notes"],
        "must_have_signals": " | ".join(evaluation["must_have_signals"]),
        "likely_false_positive_patterns": " | ".join(evaluation["likely_false_positive_patterns"]),
        "ranking_basis": evaluation["ranking_basis"],
    }

    for mode_name in ("lexical", "semantic"):
        mode_output = evaluation[mode_name]
        row[f"{mode_name}_mode_requested"] = mode_output["mode_requested"]
        row[f"{mode_name}_mode_used"] = mode_output["mode_used"]
        row[f"{mode_name}_warning"] = mode_output["warning"] or ""

        for index in range(TOP_K):
            prefix = f"{mode_name}_top_{index + 1}"
            if index < len(mode_output["results"]):
                result = mode_output["results"][index]
                row[f"{prefix}_call_id"] = result["call_id"]
                row[f"{prefix}_title"] = result["call_title"]
                row[f"{prefix}_similarity"] = result["similarity_score"]
                row[f"{prefix}_strategic_fit"] = result["strategic_fit_score"]
                row[f"{prefix}_confidence"] = result["confidence"]
                row[f"{prefix}_eligibility"] = result["eligibility"]
                row[f"{prefix}_why_this_matched"] = result["why_this_matched"]
            else:
                row[f"{prefix}_call_id"] = ""
                row[f"{prefix}_title"] = ""
                row[f"{prefix}_similarity"] = ""
                row[f"{prefix}_strategic_fit"] = ""
                row[f"{prefix}_confidence"] = ""
                row[f"{prefix}_eligibility"] = ""
                row[f"{prefix}_why_this_matched"] = ""

    for field in MANUAL_REVIEW_FIELDS:
        row[field] = evaluation["manual_review"][field]

    return row


def write_outputs(report: dict[str, Any], output_dir: Path = OUTPUT_DIR) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"retrieval_evaluation_{timestamp}.json"
    csv_path = output_dir / f"retrieval_evaluation_{timestamp}.csv"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)

    rows = [_build_csv_row(evaluation) for evaluation in report["evaluations"]]
    fieldnames = list(rows[0].keys()) if rows else []
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return json_path, csv_path


def main() -> None:
    cases = load_evaluation_cases()
    report = build_evaluation_report(cases)
    json_path, csv_path = write_outputs(report)

    print(f"Saved JSON evaluation output to: {json_path}")
    print(f"Saved CSV evaluation output to: {csv_path}")
    print(f"Evaluated {len(report['evaluations'])} cases with lexical and semantic retrieval.")


if __name__ == "__main__":
    main()
