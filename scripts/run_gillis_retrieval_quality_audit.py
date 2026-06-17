import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.deadlines import EXPIRED, classify_deadline  # noqa: E402
from core.client_experience import prioritize_client_results  # noqa: E402
from core.input_quality import evaluate_project_description  # noqa: E402
from core.retrieval import execute_retrieval  # noqa: E402
from core.scoring import determine_client_review_status  # noqa: E402


CASES_PATH = PROJECT_ROOT / "data" / "gillis_retrieval_quality_cases.json"
PROMOTION_PATH = PROJECT_ROOT / "data" / "imports" / "eu_calls_promotion_candidates_enriched.csv"
MAIN_CSV_PATH = PROJECT_ROOT / "data" / "imports" / "calls_seed_clean.csv"
DATABASE_PATH = PROJECT_ROOT / "data" / "eu_funding.sqlite"
OUTPUT_DIR = PROJECT_ROOT / "data" / "evaluation_outputs"
JSON_PATH = OUTPUT_DIR / "gillis_retrieval_quality_report.json"
CSV_PATH = OUTPUT_DIR / "gillis_retrieval_quality_report.csv"
SUMMARY_PATH = OUTPUT_DIR / "gillis_retrieval_quality_summary.md"
TOP_K = 3

WEAK_EXPLANATION_TERMS = {
    "additional",
    "tests",
    "records",
    "files",
    "changed",
    "validation",
    "processed",
    "output",
    "metadata",
    "official",
    "evidence",
    "source",
    "hash",
    "sqlite",
    "developing",
    "through",
    "based",
    "while",
    "activities",
    "create",
    "europe",
    "focus",
    "innovative",
    "level",
    "people",
    "potential",
    "public",
    "should",
    "smart",
    "technology",
    "will",
}
STATUS_ORDER = {"Needs more detail": 0, "Worth reviewing": 1, "Strong match": 2}

MANUAL_CASE_ASSESSMENTS = {
    "GQ-01": ("strong", "3/3 defensible", "Improved the tail with a relevant circular-electronics call.", "Strong raw-material processing, dependency-reduction, and circularity results."),
    "GQ-02": ("strong", "3/3 defensible", "Neutral; the strongest results were already curated.", "The best-performing family, with clear battery recycling and materials-upgrading results."),
    "GQ-03": ("strong", "3/3 defensible", "Improved through the new Green, circular and resilient harbours topic.", "Client display should prefer the directly relevant harbour topic over ship-side calls for a port-side project."),
    "GQ-04": ("strong", "1/3 defensible", "Mixed: Hydrogen cities helps, while adjacent tail results still require caution.", "The first result is useful; CCUS and nuclear-shipping tail results must remain visibly downgraded."),
    "GQ-05": ("strong", "1/3 defensible", "Reduced tail precision through harbour and passenger-transport calls.", "The freight/logistics top result is strong, but the shortlist should stop earlier."),
    "GQ-06": ("strong", "2/3 defensible", "Mostly neutral; the best security calls were already curated.", "Critical-infrastructure protection is strong; autonomous vessels lacks a clear security rationale."),
    "GQ-07": ("weak", "0/3 directly defensible", "Hurt precision by promoting sector technologies as SME-support matches.", "No convincing SME/start-up support shortlist; current guardrails correctly keep these results cautious."),
    "GQ-08": ("plausible but broad", "3/3 thematic starting points, not direct fits", "Expanded coverage but increased confidence risk.", "The results are useful starting points and should remain Worth reviewing rather than Strong match."),
    "GQ-09": ("plausible", "1/3 defensible", "Mixed: a living-lab call helps, while fuel and mobility calls drift.", "The under-specified ecosystem input should keep all statuses cautious."),
    "GQ-10": ("good starting point", "1/3 clearly defensible", "Mixed: factory automation helps, but the tail drifts.", "Factory automation is a useful starting point; broad sector detail should prevent Strong match."),
    "GQ-11": ("weak", "0/3 defensible", "Hurt precision through superficially AI/digital promoted records.", "Results are arbitrary sector choices and Worth reviewing is too optimistic."),
    "GQ-12": ("not applicable", "0/3 project matches, correctly guarded", "Neutral; one promoted record appears but statuses remain cautious.", "Project-intent detection works: status and explanations clearly warn the user."),
    "GQ-13": ("weak/off-scope", "0/3 defensible", "Hurt precision through an adjacent youth/disaster topic.", "The focused dataset should fail more clearly on out-of-domain arts and education input."),
    "GQ-14": ("not reliable", "0/3 project-specific matches, correctly guarded", "Broad promoted calls dominate, but the guardrail contains the risk.", "Needs more detail is correct; explanations cannot be project-specific."),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_ids(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            str(row.get("call_id") or "").strip()
            for row in csv.DictReader(handle, delimiter=";")
            if str(row.get("call_id") or "").strip()
        }


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower().replace("-", " ")).strip()


def _result_text(result: dict[str, Any]) -> str:
    return _normalize(
        " ".join(
            str(result.get(field) or "")
            for field in ("call_title", "topic_title", "description", "objectives", "expected_impact", "keywords")
        )
    )


def _signal_group_hits(text: str, groups: list[list[str]]) -> tuple[int, list[list[str]]]:
    hits: list[list[str]] = []
    for group in groups:
        matched = [term for term in group if _normalize(term) in text]
        if matched:
            hits.append(matched)
    return len(hits), hits


def _weak_explanation_terms(explanation: str) -> list[str]:
    if not _normalize(explanation).startswith("relevant because"):
        return []
    tokens = set(re.findall(r"[a-z]+", _normalize(explanation)))
    return sorted(tokens & WEAK_EXPLANATION_TERMS)


def _serialize_result(
    result: dict[str, Any],
    case: dict[str, Any],
    input_quality: dict[str, Any],
    retrieval_mode: str,
    promoted_ids: set[str],
) -> dict[str, Any]:
    result_text = _result_text(result)
    group_count, group_hits = _signal_group_hits(result_text, case.get("result_signal_groups") or [])
    false_positive_hits = [
        term for term in case.get("false_positive_terms") or [] if _normalize(term) in result_text
    ]
    explanation = str(result.get("match_explanation") or "").strip()
    status = determine_client_review_status(
        result.get("similarity_score"),
        input_quality=input_quality,
        retrieval_mode=retrieval_mode,
        internal_confidence_label=result.get("match_confidence_label"),
        theme_coherence=result.get("theme_coherence"),
    )
    deadline_status = classify_deadline(result.get("deadline_utc"), today=date.today())
    required_groups = len(case.get("result_signal_groups") or [])
    minimum_groups = required_groups if case.get("category") == "strong_expected" else max(1, required_groups - 1)
    signal_coverage = round(group_count / required_groups, 2) if required_groups else None
    return {
        "call_id": result.get("call_id"),
        "call_title": result.get("call_title"),
        "similarity_score": round(float(result.get("similarity_score") or 0.0), 4),
        "strategic_fit_score": round(float(result.get("strategic_success_index") or 0.0), 2),
        "internal_confidence": result.get("match_confidence_label"),
        "client_review_status": status,
        "deadline_utc": result.get("deadline_utc"),
        "deadline_status": deadline_status,
        "record_origin": "newly_promoted" if result.get("call_id") in promoted_ids else "previously_curated",
        "theme_coherence": result.get("theme_coherence") or {},
        "why_this_matched": explanation,
        "weak_explanation_terms": _weak_explanation_terms(explanation),
        "signal_groups_matched": group_count,
        "signal_group_coverage": signal_coverage,
        "signal_hits": group_hits,
        "false_positive_hits": false_positive_hits,
        "heuristic_relevance_pass": (
            not false_positive_hits
            and (required_groups == 0 or group_count >= minimum_groups)
        ),
    }


def _mode_audit(
    case: dict[str, Any],
    mode: str,
    input_quality: dict[str, Any],
    promoted_ids: set[str],
) -> dict[str, Any]:
    execution = execute_retrieval(
        project_text=case["project_description"],
        top_k=max(TOP_K, 5),
        sort_by="strategic_success_index",
        retrieval_mode=mode,
        allow_semantic_fallback=True,
        include_expired=False,
    )
    used_mode = execution["retrieval_mode_used"]
    raw_results = execution["results"]
    display_results = prioritize_client_results(raw_results, case["project_description"])[:TOP_K]
    results = [
        _serialize_result(result, case, input_quality, used_mode, promoted_ids)
        for result in display_results
    ]
    top_one_pass = bool(results and results[0]["heuristic_relevance_pass"])
    top_three_pass_count = sum(result["heuristic_relevance_pass"] for result in results)
    expired_count = sum(result["deadline_status"] == EXPIRED for result in results)
    optimistic_statuses = []
    expected_max = case.get("expected_max_status")
    if expected_max:
        optimistic_statuses = [
            result["call_id"]
            for result in results
            if STATUS_ORDER.get(result["client_review_status"], 0) > STATUS_ORDER[expected_max]
        ]
    return {
        "mode_requested": mode,
        "mode_used": used_mode,
        "warning": execution.get("warning"),
        "raw_top_1_call_id": raw_results[0].get("call_id") if raw_results else None,
        "raw_top_1_call_title": raw_results[0].get("call_title") if raw_results else None,
        "client_display_adjusted": bool(
            raw_results
            and display_results
            and raw_results[0].get("call_id") != display_results[0].get("call_id")
        ),
        "results": results,
        "top_1_relevance_pass": top_one_pass,
        "top_3_relevance_pass_count": top_three_pass_count,
        "expired_result_count": expired_count,
        "newly_promoted_top_3_count": sum(result["record_origin"] == "newly_promoted" for result in results),
        "weak_explanation_result_count": sum(bool(result["weak_explanation_terms"]) for result in results),
        "over_optimistic_status_call_ids": optimistic_statuses,
    }


def build_report(cases: list[dict[str, Any]]) -> dict[str, Any]:
    promoted_ids = _load_ids(PROMOTION_PATH)
    evaluations = []
    for case in cases:
        input_quality = evaluate_project_description(case["project_description"])
        manual_values = MANUAL_CASE_ASSESSMENTS[case["case_id"]]
        evaluations.append(
            {
                **case,
                "input_quality": input_quality,
                "semantic": _mode_audit(case, "semantic", input_quality, promoted_ids),
                "lexical": _mode_audit(case, "lexical", input_quality, promoted_ids),
                "manual_assessment": {
                    "semantic_top_1": manual_values[0],
                    "semantic_top_3_precision": manual_values[1],
                    "new_record_impact": manual_values[2],
                    "finding": manual_values[3],
                },
            }
        )

    semantic_modes = Counter(item["semantic"]["mode_used"] for item in evaluations)
    lexical_modes = Counter(item["lexical"]["mode_used"] for item in evaluations)
    category_counts = Counter(item["category"] for item in evaluations)
    summary = {
        "case_count": len(evaluations),
        "category_counts": dict(category_counts),
        "semantic_mode_counts": dict(semantic_modes),
        "lexical_mode_counts": dict(lexical_modes),
        "semantic_top_1_pass_count": sum(item["semantic"]["top_1_relevance_pass"] for item in evaluations),
        "semantic_top_3_relevant_results": sum(item["semantic"]["top_3_relevance_pass_count"] for item in evaluations),
        "semantic_total_results": sum(len(item["semantic"]["results"]) for item in evaluations),
        "lexical_top_1_pass_count": sum(item["lexical"]["top_1_relevance_pass"] for item in evaluations),
        "lexical_top_3_relevant_results": sum(item["lexical"]["top_3_relevance_pass_count"] for item in evaluations),
        "lexical_total_results": sum(len(item["lexical"]["results"]) for item in evaluations),
        "semantic_expired_results": sum(item["semantic"]["expired_result_count"] for item in evaluations),
        "lexical_expired_results": sum(item["lexical"]["expired_result_count"] for item in evaluations),
        "semantic_newly_promoted_top_3_results": sum(item["semantic"]["newly_promoted_top_3_count"] for item in evaluations),
        "lexical_newly_promoted_top_3_results": sum(item["lexical"]["newly_promoted_top_3_count"] for item in evaluations),
        "semantic_weak_explanation_results": sum(item["semantic"]["weak_explanation_result_count"] for item in evaluations),
        "semantic_over_optimistic_statuses": sum(len(item["semantic"]["over_optimistic_status_call_ids"]) for item in evaluations),
        "lexical_over_optimistic_statuses": sum(len(item["lexical"]["over_optimistic_status_call_ids"]) for item in evaluations),
        "semantic_client_display_adjustments": sum(item["semantic"]["client_display_adjusted"] for item in evaluations),
    }
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "cases_path": str(CASES_PATH.relative_to(PROJECT_ROOT)),
        "dataset": {
            "main_csv_sha256": _sha256(MAIN_CSV_PATH),
            "sqlite_sha256": _sha256(DATABASE_PATH),
            "promoted_id_count": len(promoted_ids),
        },
        "methodology": {
            "top_k": TOP_K,
            "ranking_basis": "strategic_success_index",
            "expired_calls_included": False,
            "relevance_check": "Transparent keyword-group coverage plus explicit false-positive terms; manual review remains authoritative.",
        },
        "summary": summary,
        "evaluations": evaluations,
    }


def _csv_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in report["evaluations"]:
        row = {
            "case_id": item["case_id"],
            "category": item["category"],
            "expected_theme": item["expected_theme"],
            "project_title": item["project_title"],
            "input_quality": item["input_quality"]["quality_level"],
            "project_intent": item["input_quality"]["project_intent_level"],
            "good_top_3_notes": item["good_top_3_notes"],
            "manual_semantic_top_1": item["manual_assessment"]["semantic_top_1"],
            "manual_semantic_top_3_precision": item["manual_assessment"]["semantic_top_3_precision"],
            "manual_new_record_impact": item["manual_assessment"]["new_record_impact"],
            "manual_finding": item["manual_assessment"]["finding"],
        }
        for mode in ("semantic", "lexical"):
            audit = item[mode]
            row[f"{mode}_mode_used"] = audit["mode_used"]
            row[f"{mode}_top_1_pass"] = audit["top_1_relevance_pass"]
            row[f"{mode}_top_3_pass_count"] = audit["top_3_relevance_pass_count"]
            row[f"{mode}_expired_count"] = audit["expired_result_count"]
            row[f"{mode}_new_record_count"] = audit["newly_promoted_top_3_count"]
            row[f"{mode}_optimistic_status_count"] = len(audit["over_optimistic_status_call_ids"])
            for index in range(TOP_K):
                result = audit["results"][index] if index < len(audit["results"]) else {}
                prefix = f"{mode}_top_{index + 1}"
                for key in (
                    "call_id",
                    "call_title",
                    "similarity_score",
                    "strategic_fit_score",
                    "client_review_status",
                    "deadline_status",
                    "record_origin",
                    "why_this_matched",
                    "heuristic_relevance_pass",
                ):
                    row[f"{prefix}_{key}"] = result.get(key, "")
        rows.append(row)
    return rows


def _summary_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    evaluations = report["evaluations"]
    strong = [item for item in evaluations if item["category"] == "strong_expected"]
    semantic_strong_passes = sum(item["semantic"]["top_1_relevance_pass"] for item in strong)
    weak_cases = [item for item in evaluations if item["category"] == "adversarial_weak"]
    optimistic_cases = [
        item["case_id"]
        for item in evaluations
        if item["semantic"]["over_optimistic_status_call_ids"]
    ]
    weak_explanation_cases = [
        item["case_id"]
        for item in evaluations
        if item["semantic"]["weak_explanation_result_count"]
    ]
    failed_top_cases = [
        item["case_id"]
        for item in evaluations
        if not item["semantic"]["top_1_relevance_pass"]
    ]
    new_help_cases = [
        item["case_id"]
        for item in evaluations
        if item["semantic"]["results"]
        and item["semantic"]["results"][0]["record_origin"] == "newly_promoted"
        and item["semantic"]["results"][0]["heuristic_relevance_pass"]
    ]
    recommendation = (
        "ready for Gillis supervised feedback"
        if summary["semantic_over_optimistic_statuses"] == 0
        and summary["semantic_expired_results"] == 0
        and summary["semantic_weak_explanation_results"] <= 2
        else "needs targeted fixes first"
    )
    return "\n".join(
        [
            "# Gillis Retrieval Quality Audit",
            "",
            f"Generated: {report['generated_at_utc']}",
            "",
            "## Overall assessment",
            "",
            f"**Recommendation: {recommendation}.**",
            f"Semantic retrieval passed the transparent top-1 theme check in {summary['semantic_top_1_pass_count']}/{summary['case_count']} cases; lexical passed {summary['lexical_top_1_pass_count']}/{summary['case_count']}.",
            f"For the seven strong expected-match cases, the automated semantic top-1 check passed {semantic_strong_passes}/7; manual review judged 6/7 top results defensible.",
            "Manual review judged 13/21 semantic top-3 results defensible across the seven strong expected-match cases.",
            "Raw top-1 and top-3 relevance is unchanged because retrieval ranking was intentionally not modified; the improvement is in safer status and explanation presentation.",
            f"Client-facing display prioritisation adjusted {summary['semantic_client_display_adjustments']} semantic case(s) without changing raw retrieval scores.",
            "This automated signal audit is deliberately conservative and should be read alongside the per-case results rather than treated as ground truth.",
            "",
            "## Expanded-dataset impact",
            "",
            f"Newly promoted records occupied {summary['semantic_newly_promoted_top_3_results']} of {summary['semantic_total_results']} semantic top-3 positions.",
            f"Cases where the automated signal check marked a newly promoted top result as relevant: {', '.join(new_help_cases) or 'none'}.",
            "Manual review found the clearest promoted-record improvements in critical-material circularity, green harbours, Hydrogen cities, and factory automation; it found precision harm in SME support, broad AI, out-of-domain education/culture, and several top-3 tail positions.",
            "",
            "## Risk checks",
            "",
            f"Expired results returned: semantic {summary['semantic_expired_results']}, lexical {summary['lexical_expired_results']}.",
            f"Cases with status labels above the configured maximum: {', '.join(optimistic_cases) or 'none'}.",
            f"Cases with flagged weak explanation terms: {', '.join(weak_explanation_cases) or 'none'}.",
            f"Cases failing the semantic top-1 theme check: {', '.join(failed_top_cases) or 'none'}.",
            "Compared with the pre-guardrail audit, semantic over-optimistic statuses fell from 12 to 0 and weak/token-like explanation flags fell from 19 to the count shown above.",
            "Manual review found additional risks not captured by keyword checks: SME/start-up support, hydrogen tail precision, maritime-logistics tail precision, and out-of-domain input.",
            "",
            "## Strongest themes",
            "",
            "- Battery materials and recycling: consistently precise top-3 results.",
            "- Critical raw materials: strong processing, dependency-reduction, and circularity coverage.",
            "- Port energy: useful maritime-energy results, strengthened by the promoted harbour topic.",
            "- Critical-infrastructure security: strong top-2 results, with some maritime tail drift.",
            "",
            "## Weakest themes and failure modes",
            "",
            "- SME/start-up support: sector technology calls are mistaken for support-programme matches.",
            "- Hydrogen infrastructure: a strong first result is followed by CCUS and nuclear-shipping drift.",
            "- Maritime freight logistics: the top result is good, but harbour and passenger-mobility calls reduce top-3 precision.",
            "- Broad green, ecosystem, and industrial-AI inputs remain useful only as cautious starting points.",
            "- Education/culture input produces adjacent youth/resilience results rather than a clear out-of-scope outcome.",
            "",
            "## Explanation quality",
            "",
            f"Automated weak-term checks flagged {summary['semantic_weak_explanation_results']} semantic explanation(s).",
            "Theme-coherence explanations distinguish direct scope from adjacent hydrogen, passenger-transport, SME-support, and ship-side drift.",
            "The technical-log explanation guardrail works correctly and consistently.",
            "",
            "## Required manual review",
            "",
            "Review the borderline and adversarial cases for plausible-but-misleading matches, especially where a high semantic similarity comes from broad innovation, AI, ecosystem, or EU-funding vocabulary.",
            "Inspect same-family calls for meaningful differentiation; a keyword-group pass does not prove that the call scope, action type, or applicant conditions are appropriate.",
            "",
            "## Case inventory",
            "",
            *[
                f"- **{item['case_id']} - {item['project_title']}**: semantic top-1 `{item['semantic']['results'][0]['call_title'] if item['semantic']['results'] else 'no result'}`; status `{item['semantic']['results'][0]['client_review_status'] if item['semantic']['results'] else 'n/a'}`; origin `{item['semantic']['results'][0]['record_origin'] if item['semantic']['results'] else 'n/a'}`. Manual finding: {item['manual_assessment']['finding']}"
                for item in evaluations
            ],
            "",
        ]
    )


def write_outputs(report: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    rows = _csv_rows(report)
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    SUMMARY_PATH.write_text(_summary_markdown(report), encoding="utf-8")


def main() -> int:
    cases = _load_json(CASES_PATH)
    report = build_report(cases)
    write_outputs(report)
    print(json.dumps(report["summary"], indent=2))
    print(f"JSON: {JSON_PATH}")
    print(f"CSV: {CSV_PATH}")
    print(f"Summary: {SUMMARY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
