import html
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from core.client_experience import (
    build_call_strategy,
    build_review_status_reason,
    build_theme_aware_caution,
    is_internal_mode,
    prioritize_client_results,
)
from core.db import count_calls, fetch_calls, run_seed_import
from core.dataset_status import get_dataset_status
from core.deadlines import (
    EXPIRED,
    INVALID_DEADLINE,
    OPEN_OR_UPCOMING,
    UNKNOWN_DEADLINE,
    classify_deadline,
)
from core.input_quality import (
    NON_PROJECT_INPUT_WARNING,
    WEAK_INPUT_GUIDANCE,
    evaluate_project_description,
)
from core.reporting import build_decision_support_pdf
from core.retrieval import DEFAULT_END_USER_RETRIEVAL_MODE, execute_retrieval
from core.scoring import (
    MIN_DISPLAY_SIMILARITY_SCORE,
    MIN_RELIABLE_SIMILARITY_SCORE,
    determine_client_review_status,
    format_client_confidence_label,
)
from core.source_urls import canonical_official_topic_url, official_source_label

MAX_DISPLAY_RESULTS = 3
INTERNAL_MODE = is_internal_mode()
DEFAULT_COUNTRY = "Netherlands"
ORG_TYPE_OPTIONS = {
    "SME": "sme",
    "Company": "company",
    "University": "university",
    "Research organisation": "research institute",
    "Public body": "public body",
}
TRL_OPTIONS = ["Not sure"] + [str(value) for value in range(1, 10)]
RETRIEVAL_SPINNER_TEXT = (
    "Reviewing active calls... the first search on the hosted app may take a little longer while matching starts."
)


def select_display_results(results):
    if not results:
        return []

    top_similarity = float(results[0]["similarity_score"])
    top_fit = float(results[0]["strategic_success_index"])
    similarity_cutoff = max(MIN_DISPLAY_SIMILARITY_SCORE, top_similarity * 0.78)
    fit_cutoff = max(0.0, top_fit - 12.0)

    selected = [
        result
        for result in results
        if float(result["similarity_score"]) >= similarity_cutoff
        and float(result["strategic_success_index"]) >= fit_cutoff
    ]

    if not selected:
        selected = [results[0]]

    return selected[:MAX_DISPLAY_RESULTS]


def format_text_match(score: float) -> str:
    return f"{score * 100:.0f} / 100"


def display_percentage(value_0_to_1: float) -> str:
    try:
        return f"{int(round(float(value_0_to_1) * 100))}%"
    except Exception:
        return "—"


def client_confidence_class(label: str | None) -> str:
    client_label = format_client_confidence_label(label)
    if client_label == "Strong match":
        return "ui-badge-promising"
    if client_label == "Worth reviewing":
        return "ui-badge-review"
    return "ui-badge-caution"


def client_review_status_class(status: str) -> str:
    if status == "Strong match":
        return "ui-badge-promising"
    if status == "Worth reviewing":
        return "ui-badge-review"
    return "ui-badge-caution"


def format_deadline(deadline_utc: str | None) -> str:
    if deadline_utc in [None, ""]:
        return "Not listed"
    try:
        parsed = datetime.fromisoformat(str(deadline_utc).replace("Z", "+00:00"))
        return parsed.strftime("%d %b %Y")
    except ValueError:
        return str(deadline_utc)


def format_eligibility_view(result: dict) -> str:
    status = result.get("eligibility_status")
    if status == "Eligible":
        return "Broadly aligned with the available call details."
    if status == "Partially Eligible":
        return "Potentially aligned, but one or more eligibility points still need confirmation."
    return "The available call details suggest a likely mismatch."


def format_programme_cluster(result: dict) -> str:
    parts = []
    for value in (result.get("program"), result.get("cluster")):
        normalized = str(value or "").strip()
        if normalized and normalized not in parts:
            parts.append(normalized)
    return " / ".join(parts) or "Not listed"


def format_eligibility_summary(result: dict) -> str:
    status = result.get("eligibility_status")
    if status == "Eligible":
        return "Broadly aligned"
    if status == "Partially Eligible":
        return "Needs confirmation"
    return "Potential mismatch"


def format_trl_alignment(result: dict) -> str:
    trl_min = result.get("trl_min")
    trl_max = result.get("trl_max")
    alignment = (result.get("strategic_success_components") or {}).get("trl_alignment")

    if trl_min in [None, ""] and trl_max in [None, ""]:
        return "Range not specified"

    if trl_min not in [None, ""] and trl_max not in [None, ""]:
        range_text = f"TRL {trl_min}-{trl_max}"
    elif trl_min not in [None, ""]:
        range_text = f"TRL {trl_min}+"
    else:
        range_text = f"Up to TRL {trl_max}"

    if alignment is None or float(alignment) == 50.0:
        return f"Needs confirmation ({range_text})"
    if float(alignment) >= 100.0:
        return f"Aligned ({range_text})"
    if float(alignment) >= 75.0:
        return f"Close to range ({range_text})"
    return f"Maturity gap ({range_text})"


def format_deadline_status(result: dict) -> tuple[str, str, bool]:
    raw_deadline = result.get("deadline_utc")
    status = result.get("deadline_status") or classify_deadline(raw_deadline)
    formatted_deadline = format_deadline(raw_deadline)

    if status == OPEN_OR_UPCOMING:
        return "Open or upcoming", formatted_deadline, False
    if status == EXPIRED:
        return "Archived", formatted_deadline, True
    if status == UNKNOWN_DEADLINE:
        return "Deadline not listed", "Confirm on the official source", True
    if status == INVALID_DEADLINE:
        return "Deadline needs confirmation", "Confirm on the official source", True
    return "Deadline needs confirmation", "Confirm on the official source", True


def parse_deadline(deadline_utc: str | None) -> datetime | None:
    if deadline_utc in [None, ""]:
        return None
    try:
        return datetime.fromisoformat(str(deadline_utc).replace("Z", "+00:00"))
    except ValueError:
        return None


def _escape_text(value: str) -> str:
    return html.escape(str(value or ""))


def build_result_text(result: dict) -> str:
    parts = [
        result.get("call_title", ""),
        result.get("keywords", ""),
        result.get("description", ""),
        result.get("objectives", ""),
        result.get("expected_impact", ""),
    ]
    return " ".join(str(part or "").lower() for part in parts)


def contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def detect_result_theme(result: dict) -> str:
    text = build_result_text(result)

    if contains_any(text, ["critical raw materials", "raw materials", "rare earth", "recycling"]):
        return "Critical materials and recycling"

    if contains_any(text, ["shore", "berth", "port", "ports"]) and contains_any(
        text, ["energy", "electrification", "emissions", "electricity"]
    ):
        return "Port energy and maritime infrastructure"

    if contains_any(text, ["security", "critical infrastructure", "resilience", "anomaly"]):
        return "Infrastructure security and resilience"

    if contains_any(text, ["shipping", "ship", "waterborne", "maritime"]):
        return "Maritime operations and shipping innovation"

    return "Relevant funding calls"


def build_theme_tag(result: dict) -> str:
    theme = detect_result_theme(result)
    if theme == "Critical materials and recycling":
        return "Critical materials"
    if theme == "Port energy and maritime infrastructure":
        return "Port energy"
    if theme == "Infrastructure security and resilience":
        return "Infrastructure security"
    if theme == "Maritime operations and shipping innovation":
        return "Maritime innovation"
    return "Relevant theme"


def build_focus_label(result: dict) -> str:
    text = build_result_text(result)

    if contains_any(text, ["direct recycling"]):
        return "Direct recycling"
    if contains_any(text, ["battery", "battery materials"]) and contains_any(text, ["recycling", "recovered"]):
        return "Battery-material recovery"
    if contains_any(text, ["battery", "batteries"]) and contains_any(
        text, ["operation", "durability", "waterborne", "vessel", "ship", "ferries", "electric"]
    ) and not contains_any(text, ["raw materials", "battery-grade", "electrodes", "refining", "recycling"]):
        return "Electric vessel batteries"
    if contains_any(text, ["battery", "battery materials"]):
        return "Battery materials"
    if contains_any(text, ["substitution", "dependency", "dependencies"]):
        return "Dependency reduction"
    if contains_any(text, ["processing", "refining"]) and contains_any(
        text, ["critical raw materials", "raw materials", "rare earth"]
    ):
        return "Processing and refining"
    if contains_any(text, ["secondary raw materials", "recycling"]):
        return "Recovery and recycling"
    if contains_any(text, ["shore", "berth"]):
        return "Shore power and berth operations"
    if contains_any(text, ["terminal", "infrastructure"]):
        return "Port infrastructure"
    if contains_any(text, ["shipyard", "shipyards"]):
        return "Shipyard transition"
    if contains_any(text, ["shipping", "ships", "waterborne"]):
        return "Shipping operations"
    if contains_any(text, ["anomaly", "monitoring"]):
        return "Monitoring and anomaly detection"
    if contains_any(text, ["critical infrastructure", "protection"]):
        return "Asset protection"
    return "Screening focus"


def theme_class(result: dict) -> str:
    theme = detect_result_theme(result)
    if theme == "Critical materials and recycling":
        return "materials"
    if theme == "Port energy and maritime infrastructure":
        return "ports"
    if theme == "Infrastructure security and resilience":
        return "security"
    if theme == "Maritime operations and shipping innovation":
        return "maritime"
    return "general"


def build_primary_caution(result: dict) -> str | None:
    reasons = result.get("eligibility_reasons") or []
    warnings = result.get("eligibility_warnings") or []
    data_quality_flags = result.get("data_quality_flags") or []
    trl_alignment = (result.get("strategic_success_components") or {}).get("trl_alignment", 100.0)
    result_text = build_result_text(result)
    deadline = parse_deadline(result.get("deadline_utc"))
    generic_eligibility_issue = any(
        term in " ".join([str(item).lower() for item in reasons + warnings + data_quality_flags])
        for term in ["country", "organisation", "eligible countries", "metadata"]
    )
    guardrails = set((result.get("theme_coherence") or {}).get("guardrails") or [])

    theme_caution = build_theme_aware_caution(result)
    if theme_caution:
        return theme_caution

    if contains_any(result_text, ["direct recycling"]):
        return "Check whether the call expects direct-recycling performance and recovered material quality rather than broader circularity aims."

    if contains_any(result_text, ["battery", "battery materials"]) and contains_any(
        result_text, ["recycling", "direct recycling"]
    ):
        return "Check whether the call is focused on recovered battery-grade materials rather than broader battery value-chain activity."

    if contains_any(result_text, ["battery", "battery materials", "raw materials"]) and contains_any(
        result_text, ["refining", "processing"]
    ) and not contains_any(result_text, ["secondary raw materials", "recycling"]):
        return "Check whether the call is centred on materials upgrading or refining rather than broader circularity aims."

    if contains_any(result_text, ["substitution", "dependency", "dependencies"]):
        return "Check whether the call is framed around dependency reduction or substitution rather than recovery activity."

    if contains_any(result_text, ["secondary raw materials", "recycling"]):
        return "Check whether the call expects recovery scale and processing depth rather than a broader circular-economy framing."

    if contains_any(result_text, ["shore", "berth"]):
        return "Check whether the scope is berth-side electrification rather than wider port decarbonisation."

    if contains_any(result_text, ["shipyard", "shipyards"]):
        return "Check whether the scope is shipyard and vessel-side transition rather than port-side infrastructure."

    if contains_any(result_text, ["terminal", "infrastructure"]):
        return "Check whether the scope is infrastructure upgrade rather than operational optimisation alone."

    if contains_any(result_text, ["shipping", "ships", "waterborne"]):
        return "Check whether the emphasis is on shipping operations rather than port-side infrastructure."

    if contains_any(result_text, ["security", "critical infrastructure", "anomaly"]):
        return "Check whether the call is centred on monitoring, asset protection, or a broader resilience scope."

    if result.get("consortium_required") in [1, "1", True]:
        min_partners = result.get("min_partners")
        if min_partners not in [None, "", 1, "1"]:
            return "This call may depend on a broader partner setup than a single-organisation project."

    if reasons:
        first_reason = str(reasons[0])
        lower_reason = first_reason.lower()
        if "country" in lower_reason or "organisation" in lower_reason:
            if not generic_eligibility_issue:
                return "Eligibility conditions should still be confirmed on the official call page."
        if "consortium" in lower_reason or "partner" in lower_reason:
            return "The call may expect a broader consortium setup than the current project plan."
        if "trl" in lower_reason or "maturity" in lower_reason:
            return "The thematic fit looks stronger than the current maturity alignment."
        return first_reason

    for warning in warnings:
        lower_warning = warning.lower()
        if "consortium" in lower_warning or "partner" in lower_warning:
            return "The call may require a broader consortium setup than is currently in place."
        if "country" in lower_warning or "organisation" in lower_warning:
            if not generic_eligibility_issue:
                return "Eligibility conditions should still be confirmed on the official call page."
        if "trl" in lower_warning:
            return "The project idea appears thematically relevant, but the maturity level may need closer checking."

    if data_quality_flags:
        if not generic_eligibility_issue:
            return "Some call details still need confirmation on the official call page."

    if result.get("match_confidence_label") == "Needs Review":
        return "The thematic link is useful, but this is still an early screening result rather than a firm shortlist."

    if trl_alignment < 100:
        return "The thematic fit looks stronger than the current TRL alignment."

    if deadline is not None:
        now = datetime.now(deadline.tzinfo)
        if 0 <= (deadline - now).days <= 120:
            return "This call may need near-term shortlisting if you decide to pursue it."

    if generic_eligibility_issue:
        return "Eligibility conditions should still be confirmed on the official call page."

    return None


def collect_points_to_verify(result: dict) -> list[str]:
    items = []
    for source in (
        result.get("eligibility_reasons") or [],
        result.get("eligibility_warnings") or [],
        result.get("data_quality_flags") or [],
    ):
        for item in source:
            if item not in items:
                items.append(item)
    return items[:2]


def build_meta_items(result: dict) -> list[str]:
    items = []
    if result.get("call_id"):
        items.append(f"Call {str(result['call_id']).strip()}")
    if result.get("deadline_utc"):
        items.append(f"Deadline {format_deadline(result['deadline_utc'])}")
    return items


def build_shortlist_reason(results: list[dict]) -> str:
    if not results:
        return "No current shortlist is available."

    top_theme = detect_result_theme(results[0])

    if top_theme == "Critical materials and recycling":
        return "The clearest options focus on raw-material recovery, recycling, processing, or supply-chain resilience."

    if top_theme == "Port energy and maritime infrastructure":
        return "The clearest options connect port or maritime activity with energy use, electrification, or emissions reduction."

    if top_theme == "Infrastructure security and resilience":
        return "The clearest options focus on infrastructure protection, monitoring, and operational resilience."

    return results[0].get("match_explanation") or "The shortlist is based on the closest current thematic overlap."


def build_shortlist_caution(results: list[dict]) -> str:
    if not results:
        return "Manual review is still required."

    cautions = [build_primary_caution(result) for result in results]
    cautions = [caution for caution in cautions if caution]
    if not cautions:
        return "Manual review is still required before shortlisting any call."

    if any("Eligibility conditions should still be confirmed" in caution for caution in cautions):
        return "Eligibility conditions should still be confirmed on the official call pages."

    if any("consortium" in caution.lower() for caution in cautions):
        return "Consortium expectations may be more demanding than the current project setup."

    if any("reviewable" in caution.lower() for caution in cautions):
        return "The shortlist is useful, but the adjacent results should be checked before shortlisting."

    return cautions[0]


def build_shortlist_count_text(results: list[dict]) -> str:
    count = len(results)
    status_counts = {
        "Strong match": sum(1 for result in results if result.get("client_review_status") == "Strong match"),
        "Worth reviewing": sum(1 for result in results if result.get("client_review_status") == "Worth reviewing"),
        "Needs more detail": sum(1 for result in results if result.get("client_review_status") == "Needs more detail"),
    }
    if any(status_counts.values()):
        parts = []
        if status_counts["Strong match"]:
            parts.append(
                f"{status_counts['Strong match']} Strong match candidate"
                f"{'s' if status_counts['Strong match'] != 1 else ''}"
            )
        if status_counts["Worth reviewing"]:
            parts.append(
                f"{status_counts['Worth reviewing']} reviewable option"
                f"{'s' if status_counts['Worth reviewing'] != 1 else ''}"
            )
        if status_counts["Needs more detail"]:
            parts.append(
                f"{status_counts['Needs more detail']} option"
                f"{'s' if status_counts['Needs more detail'] != 1 else ''} needing more detail"
            )
        return f"{count} current option{'s' if count != 1 else ''} found: {', '.join(parts)}."
    if count == 1:
        return "1 current option found."
    return f"{count} current options found."


def build_summary_lead(results: list[dict]) -> str:
    if not results:
        return "No shortlist is currently available."

    theme = detect_result_theme(results[0])

    if theme == "Critical materials and recycling":
        return "The main opportunity area is critical materials, recycling, and related processing."

    if theme == "Port energy and maritime infrastructure":
        return "The main opportunity area is port energy, shore-side infrastructure, and related emissions reduction."

    if theme == "Infrastructure security and resilience":
        return "The main opportunity area is infrastructure security, resilience, and operational monitoring."

    return "The shortlist reflects the closest thematic overlap in the current call set."


def with_client_review_statuses(
    results: list[dict],
    *,
    input_quality: dict,
    retrieval_mode: str,
) -> list[dict]:
    enriched_results = []
    for result in results:
        enriched = dict(result)
        enriched["client_review_status"] = determine_client_review_status(
            result.get("similarity_score"),
            input_quality=input_quality,
            retrieval_mode=retrieval_mode,
            internal_confidence_label=result.get("match_confidence_label"),
            theme_coherence=result.get("theme_coherence"),
        )
        enriched_results.append(enriched)
    return enriched_results


def guidance_priority(item: str) -> int:
    text = item.lower()
    if any(
        term in text
        for term in [
            "raw-material",
            "recycling",
            "substitution",
            "port infrastructure",
            "shore-side",
            "shipping operations",
            "critical-infrastructure",
            "security monitoring",
            "resilience measures",
        ]
    ):
        return 0
    if "consortium" in text or "partner" in text:
        return 1
    if "trl" in text:
        return 2
    if "deadline" in text or "work programme" in text or "call page" in text:
        return 3
    return 4


def select_primary_next_step(guidance_items: list[str]) -> str | None:
    if not guidance_items:
        return None
    return min(guidance_items, key=guidance_priority)


def confidence_class(label: str) -> str:
    if label == "Reliable":
        return "strong"
    if label == "Needs Review":
        return "review"
    return "weak"


def build_score_cluster_markup(result: dict, rank: int | None = None) -> str:
    fit_value = f"{float(result['strategic_success_index']):.0f}"
    text_match_value = display_percentage(float(result["similarity_score"]))
    confidence_label = result.get("match_confidence_label")
    priority_value = format_client_confidence_label(confidence_label)
    priority_class = client_confidence_class(confidence_label)
    return (
        "<div class='ui-score-panel'>"
        "<div class='ui-rank'>"
        f"{int(rank or 0):02d}"
        "</div>"
        "<div class='ui-score-primary-label'>Overall fit</div>"
        f"<div class='ui-score-primary'>{_escape_text(fit_value)}</div>"
        "<div class='ui-score-sub'>out of 100</div>"
        "<div class='ui-score-row'>"
        "<div class='ui-score-name'>Relevance</div>"
        f"<div class='ui-score-value'>{_escape_text(text_match_value)}</div>"
        "</div>"
        "<div class='ui-score-row'>"
        "<div class='ui-score-name'>Review status</div>"
        f"<div class='ui-badge {_escape_text(priority_class)}'>{_escape_text(priority_value)}</div>"
        "</div>"
        "<div class='ui-score-note'>Fit score supports early screening; it is not a funding probability.</div>"
        "</div>"
    )


def render_notice(message: str, *, tone: str = "neutral") -> None:
    class_name = "notice review" if tone == "review" else "notice"
    st.markdown(
        f"<div class='{class_name}'>{_escape_text(message)}</div>",
        unsafe_allow_html=True,
    )


def render_score_cluster(result: dict) -> None:
    st.markdown(build_score_cluster_markup(result), unsafe_allow_html=True)


def render_shortlist_summary(results: list[dict]) -> None:
    opportunity_area = detect_result_theme(results[0])
    count_text = build_shortlist_count_text(results)
    summary_markup = f"""
    <div class='ui-summary'>
        <div class='ui-label'>Shortlist overview</div>
        <div class='ui-overview-title'>{_escape_text(count_text)}</div>
        <div class='ui-small'>{_escape_text(build_summary_lead(results))}</div>
        <div class='ui-summary-grid'>
            <div class='ui-summary-cell'>
                <div class='ui-label'>Opportunity area</div>
                <div class='ui-summary-main-value'>{_escape_text(opportunity_area)}</div>
            </div>
            <div class='ui-summary-cell'>
                <div class='ui-label'>Why this stands out</div>
                <div class='ui-summary-body'>{_escape_text(build_shortlist_reason(results))}</div>
            </div>
            <div class='ui-summary-cell'>
                <div class='ui-label'>Main caution</div>
                <div class='ui-summary-body'>{_escape_text(build_shortlist_caution(results))}</div>
            </div>
        </div>
    </div>
    """
    st.markdown(summary_markup, unsafe_allow_html=True)


def render_result_card(
    result: dict,
    rank: int,
    *,
    input_quality: dict,
    retrieval_mode: str,
    project_inputs: dict,
) -> None:
    explanation = result.get("match_explanation") or (
        "This result was matched based on limited textual overlap and should be reviewed manually."
    )
    guidance_items = result.get("next_step_guidance") or []
    source_url = result.get("source_url")
    confidence_label = result.get("match_confidence_label")
    status_label = result.get("client_review_status") or determine_client_review_status(
        result.get("similarity_score"),
        input_quality=input_quality,
        retrieval_mode=retrieval_mode,
        internal_confidence_label=confidence_label,
        theme_coherence=result.get("theme_coherence"),
    )
    status_class = client_review_status_class(status_label)
    status_reason = build_review_status_reason(
        result,
        status_label,
        input_quality=input_quality,
    )
    strategy = build_call_strategy(result, project_inputs)
    primary_next_step = strategy["next_steps"][0] if strategy["next_steps"] else select_primary_next_step(guidance_items)
    primary_caution = build_theme_aware_caution(result, project_inputs) or build_primary_caution(result)
    call_reference_text = f"Call {str(result.get('call_id') or '').strip()}"
    deadline_status_label, deadline_status_detail, deadline_needs_attention = format_deadline_status(result)
    if deadline_needs_attention:
        deadline_text = deadline_status_label
    else:
        deadline_text = f"Deadline {deadline_status_detail}"
    deadline_value_class = "ui-fact-value ui-fact-warning" if deadline_needs_attention else "ui-fact-value"
    programme_cluster = format_programme_cluster(result)
    eligibility_summary = format_eligibility_summary(result)
    trl_alignment = format_trl_alignment(result)
    source_link_markup = ""
    if source_url:
        official_url = canonical_official_topic_url(result.get("call_id"), source_url)
        official_label = official_source_label(result.get("call_id"))
        source_link_markup = (
            "<div class='ui-card-footer'>"
            f"<a class='ui-source-link' href='{_escape_text(official_url)}' target='_blank' rel='noopener noreferrer'>"
            f"{_escape_text(official_label)}"
            "</a>"
            "</div>"
        )
    with st.container():
        card_markup = f"""
        <div class='ui-card'>
            <div class='ui-card-top'>
                <div>
                    <div class='ui-card-meta' style='margin-bottom:0.58rem;'>
                        <span class='ui-chip ui-chip-theme'>{_escape_text(build_theme_tag(result))}</span>
                        <span class='ui-chip ui-chip-subtheme'>{_escape_text(build_focus_label(result))}</span>
                    </div>
                    <div class='ui-card-title'>{_escape_text(result['call_title'])}</div>
                    <div class='ui-card-meta'>
                        <span class='ui-chip'>{_escape_text(call_reference_text)}</span>
                        <span class='ui-chip'>{_escape_text(deadline_text)}</span>
                    </div>
                </div>
                <div class='ui-score-wrap'>
                    <div class='ui-rank'>{rank:02d}</div>
                    <div class='ui-score-panel'>
                        <div class='ui-score-primary-label'>Overall fit</div>
                        <div class='ui-score-primary'>{int(round(float(result.get('strategic_success_index') or 0.0)))}</div>
                        <div class='ui-score-sub'>out of 100</div>
                        <div class='ui-score-row'>
                            <div class='ui-score-name'>Relevance</div>
                            <div class='ui-score-value'>{_escape_text(display_percentage(float(result.get('similarity_score') or 0.0)))}</div>
                        </div>
                        <div class='ui-score-row'>
                            <div class='ui-score-name'>Review status</div>
                            <div class='{_escape_text(status_class)} ui-badge'>{_escape_text(status_label)}</div>
                        </div>
                        <div class='ui-score-note'>Fit score supports early screening; it is not a funding probability.</div>
                        <div class='ui-status-reason'>{_escape_text(status_reason)}</div>
                    </div>
                </div>
            </div>
            <div class='ui-card-divider'></div>
            <div class='ui-facts'>
                <div class='ui-fact'>
                    <div class='ui-fact-label'>Programme / cluster</div>
                    <div class='ui-fact-value'>{_escape_text(programme_cluster)}</div>
                </div>
                <div class='ui-fact'>
                    <div class='ui-fact-label'>Deadline status</div>
                    <div class='{deadline_value_class}'>{_escape_text(deadline_status_label)}</div>
                    <div class='ui-fact-detail'>{_escape_text(deadline_status_detail)}</div>
                </div>
                <div class='ui-fact'>
                    <div class='ui-fact-label'>Eligibility view</div>
                    <div class='ui-fact-value'>{_escape_text(eligibility_summary)}</div>
                </div>
                <div class='ui-fact'>
                    <div class='ui-fact-label'>TRL alignment</div>
                    <div class='ui-fact-value'>{_escape_text(trl_alignment)}</div>
                </div>
            </div>
            <div class='ui-insights'>
                <div class='ui-insight ui-insight-wide'>
                    <div class='ui-insight-title'>Why this matched</div>
                    <p class='ui-insight-text'>{_escape_text(explanation)}</p>
                </div>
                <div class='ui-insight'>
                    <div class='ui-insight-title'>Next best action</div>
                    <p class='ui-insight-text'>{_escape_text(primary_next_step or 'Review the official call text before deciding whether to shortlist it.')}</p>
                </div>
                <div class='ui-insight'>
                    <div class='ui-insight-title'>Main caution</div>
                    <p class='ui-insight-text'>{_escape_text(primary_caution or 'Manual review is still needed before treating this as a firm shortlist candidate.')}</p>
                </div>
            </div>
            {source_link_markup}
        </div>
        """
        st.markdown(card_markup, unsafe_allow_html=True)

        with st.expander("Supporting screening details"):
            st.markdown(f"**Eligibility view**  \n{format_eligibility_view(result)}")
            st.markdown(f"**TRL alignment**  \n{trl_alignment}")

            if strategy["strengths"]:
                st.markdown("**What supports the fit**")
                for item in strategy["strengths"]:
                    st.markdown(f"- {_escape_text(item)}")

            if strategy["clarifications"]:
                st.markdown("**What to clarify**")
                for item in strategy["clarifications"]:
                    st.markdown(f"- {_escape_text(item)}")

            st.markdown("**Next steps for this call**")
            for item in strategy["next_steps"]:
                st.markdown(f"- {_escape_text(item)}")

            st.markdown(
                f"**Deadline status**  \n{deadline_status_label}: {deadline_status_detail}"
            )


st.set_page_config(page_title="EU Funding Match", layout="wide", initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
        :root {
            --bg: #f5f7fb;
            --surface: #ffffff;
            --surface-soft: #f8fafc;
            --border: #d8e1ec;
            --text: #0f172a;
            --muted: #5b6b82;
            --muted-2: #7b8aa0;
            --accent: #0f2747;
            --success-bg: #e7f4ea;
            --success-text: #1f6b3b;
            --warning-bg: #fff3dd;
            --warning-text: #8a5a00;
            --danger-bg: #fdeaea;
            --danger-text: #9c2f2f;
            --shadow: 0 10px 30px rgba(15, 23, 42, 0.05);
            --radius-lg: 20px;
            --radius-md: 14px;
        }
        .stApp, [data-testid="stAppViewContainer"] {
            background: var(--bg);
            color: var(--text);
        }
        [data-testid="stHeader"] {
            background: rgba(245, 247, 251, 0.9);
        }
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        #MainMenu,
        footer {
            display: none !important;
            visibility: hidden !important;
        }
        .block-container {
            max-width: 1380px;
            padding-top: 2.1rem;
            padding-bottom: 2rem;
            padding-left: 1.5rem;
            padding-right: 1.5rem;
        }
        h1, h2, h3, h4 {
            color: var(--text);
            letter-spacing: -0.03em;
        }
        p, li {
            color: var(--text);
            font-size: 0.98rem;
            line-height: 1.55;
        }
        div[data-testid="stMarkdownContainer"] p {
            font-size: 0.98rem;
            line-height: 1.55;
        }
        div[data-testid="stCaptionContainer"] p {
            color: var(--muted) !important;
            font-size: 0.92rem !important;
            line-height: 1.45 !important;
        }
        label, .stCheckbox label, .stRadio label {
            color: var(--text) !important;
            font-size: 0.95rem !important;
            font-weight: 600 !important;
        }
        .ui-hero-title {
            font-size: 3.2rem;
            line-height: 1.02;
            font-weight: 800;
            letter-spacing: -0.03em;
            color: var(--text);
            margin: 0 0 0.45rem 0;
        }
        .ui-hero-subtitle {
            font-size: 1.05rem;
            line-height: 1.55;
            color: var(--muted);
            margin: 0 0 0.85rem 0;
            max-width: 880px;
        }
        .ui-hero-focus {
            max-width: 1120px;
            margin: 0 0 1.35rem 0;
            padding: 0.85rem 1rem;
            border-left: 4px solid #0f2747;
            border-radius: 0 14px 14px 0;
            background: rgba(255, 255, 255, 0.72);
            color: var(--text);
            font-size: 0.98rem;
            line-height: 1.52;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.035);
        }
        .ui-scope-strip {
            display: grid;
            grid-template-columns: 1.1fr 1fr 1fr;
            gap: 1rem;
            margin: 0.2rem 0 1.35rem 0;
            padding: 0.85rem 1rem;
            border-top: 1px solid var(--border);
            border-bottom: 1px solid var(--border);
        }
        .ui-scope-item {
            color: var(--muted);
            font-size: 0.9rem;
            line-height: 1.42;
        }
        .ui-scope-item strong {
            display: block;
            margin-bottom: 0.12rem;
            color: var(--text);
            font-size: 0.92rem;
        }
        .ui-section-title {
            font-size: 1.8rem;
            line-height: 1.1;
            font-weight: 800;
            letter-spacing: -0.02em;
            color: var(--text);
            margin: 0 0 0.8rem 0;
        }
        .ui-overview-title {
            font-size: 2.1rem;
            line-height: 1.06;
            font-weight: 800;
            letter-spacing: -0.03em;
            color: var(--text);
            margin: 0.15rem 0 0.45rem 0;
        }
        .ui-label {
            font-size: 0.74rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.11em;
            color: var(--muted-2);
            margin-bottom: 0.32rem;
        }
        .ui-small {
            font-size: 0.92rem;
            color: var(--muted);
            line-height: 1.45;
        }
        [data-testid="stForm"] {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow);
            padding: 1.2rem 1.3rem 1.15rem 1.3rem;
            margin-bottom: 1.2rem;
        }
        [data-testid="stForm"] > div {
            gap: 1rem;
        }
        .stTextInput input,
        .stTextArea textarea,
        .stSelectbox div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div {
            border-radius: 14px !important;
            border-color: var(--border) !important;
            background: var(--surface) !important;
        }
        .stTextArea textarea {
            font-size: 1.02rem !important;
            line-height: 1.55 !important;
            min-height: 280px;
        }
        div[data-baseweb="input"] input,
        div[data-baseweb="select"] * {
            color: var(--text) !important;
            font-size: 0.95rem !important;
        }
        div[data-testid="stExpander"] {
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            background: var(--surface);
        }
        div[data-testid="stExpander"] summary {
            font-size: 0.96rem;
            font-weight: 700;
            color: var(--text);
        }
        div[data-testid="stFormSubmitButton"] button,
        div[data-testid="stButton"] button {
            min-height: 52px;
            border-radius: 15px !important;
            font-weight: 700 !important;
            font-size: 1rem !important;
            padding: 0.7rem 1.15rem !important;
            border: 1px solid #0f2747 !important;
            background: #0f2747 !important;
            color: white !important;
            box-shadow: 0 8px 22px rgba(15, 39, 71, 0.18);
        }
        div[data-testid="stFormSubmitButton"] button *,
        div[data-testid="stButton"] button * {
            color: white !important;
            fill: white !important;
        }
        div[data-testid="stFormSubmitButton"] button:hover,
        div[data-testid="stButton"] button:hover {
            background: #16355f !important;
            border-color: #16355f !important;
            color: white !important;
        }
        div[data-testid="stDownloadButton"] button {
            min-height: 48px !important;
            width: 100%;
            border-radius: 14px !important;
            font-weight: 700 !important;
            font-size: 0.98rem !important;
            padding: 0.62rem 1rem !important;
            border: 1px solid var(--border) !important;
            background: var(--surface) !important;
            color: var(--text) !important;
            box-shadow: none !important;
        }
        div[data-testid="stDownloadButton"] button *,
        div[data-testid="stDownloadButton"] button:hover * {
            color: var(--text) !important;
            fill: var(--text) !important;
        }
        div[data-testid="stDownloadButton"] button:hover {
            border-color: #b8c7d9 !important;
            background: #fbfcfe !important;
            color: var(--text) !important;
        }
        .ui-summary {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow);
            padding: 1.1rem 1.25rem 1rem 1.25rem;
            margin-bottom: 1.25rem;
        }
        .ui-summary-grid {
            display: grid;
            grid-template-columns: 1.2fr 1fr 1fr;
            gap: 0.9rem;
            margin-top: 0.9rem;
        }
        .ui-summary-cell {
            background: #fbfcfe;
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 0.85rem 0.95rem;
        }
        .ui-summary-main-value {
            font-size: 1.05rem;
            font-weight: 700;
            color: var(--text);
        }
        .ui-summary-body {
            font-size: 0.98rem;
            line-height: 1.5;
            color: var(--text);
        }
        .notice {
            border-radius: 14px;
            padding: 0.74rem 0.82rem;
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text);
            font-size: 0.92rem;
            line-height: 1.48;
            margin: 0.08rem 0;
        }
        .notice.review {
            background: #fbfcfe;
        }
        .matching-method {
            display: inline-flex;
            align-items: center;
            margin: 0.15rem 0 0.7rem 0;
            padding: 0.3rem 0.62rem;
            border-radius: 999px;
            font-size: 0.8rem;
            font-weight: 700;
        }
        .matching-method.semantic {
            background: var(--success-bg);
            color: var(--success-text);
        }
        .ui-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 22px;
            box-shadow: var(--shadow);
            padding: 1rem 1.1rem 0.95rem 1.1rem;
            margin-bottom: 0.55rem;
        }
        .ui-card-top {
            display: grid;
            grid-template-columns: minmax(0, 1fr) 250px;
            gap: 0.9rem;
            align-items: start;
        }
        .ui-score-wrap {
            display: flex;
            flex-direction: column;
            align-items: stretch;
            gap: 0.35rem;
        }
        .ui-card-title {
            font-size: 1.45rem;
            line-height: 1.12;
            font-weight: 800;
            letter-spacing: -0.025em;
            color: var(--text);
            margin: 0.12rem 0 0.45rem 0;
        }
        .ui-card-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.42rem;
            margin-top: 0.08rem;
        }
        .ui-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            background: #fcfdff;
            border: 1px solid var(--border);
            border-radius: 999px;
            padding: 0.33rem 0.72rem;
            font-size: 0.86rem;
            color: var(--muted);
            white-space: nowrap;
        }
        .ui-chip-theme {
            background: #efe5cf;
            border-color: #e4d2ad;
            color: #7a5a14;
            font-weight: 700;
        }
        .ui-chip-subtheme {
            background: #fbfcfe;
            color: #50627c;
        }
        .ui-rank {
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.12em;
            color: var(--muted-2);
            text-transform: uppercase;
            text-align: right;
            margin-bottom: 0.15rem;
        }
        .ui-card-divider {
            height: 1px;
            background: #e8eef5;
            margin: 0.85rem 0 0.7rem 0;
        }
        .ui-facts {
            display: grid;
            grid-template-columns: 1.2fr 1fr 0.9fr 1.1fr;
            gap: 0;
            padding: 0.15rem 0 0.72rem 0;
            border-bottom: 1px solid #e8eef5;
        }
        .ui-fact {
            min-width: 0;
            padding: 0.1rem 0.9rem 0.1rem 0;
        }
        .ui-fact + .ui-fact {
            padding-left: 0.9rem;
            border-left: 1px solid #e8eef5;
        }
        .ui-fact-label {
            margin-bottom: 0.22rem;
            color: var(--muted-2);
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }
        .ui-fact-value {
            color: var(--text);
            font-size: 0.92rem;
            font-weight: 700;
            line-height: 1.35;
        }
        .ui-fact-warning {
            color: var(--warning-text);
        }
        .ui-fact-detail {
            margin-top: 0.1rem;
            color: var(--muted);
            font-size: 0.8rem;
            line-height: 1.35;
        }
        .ui-score-panel {
            background: #fbfcfe;
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 0.8rem 0.9rem;
        }
        .ui-score-primary-label {
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            color: var(--muted-2);
            margin-bottom: 0.3rem;
        }
        .ui-score-primary {
            font-size: 2.5rem;
            line-height: 0.95;
            font-weight: 800;
            letter-spacing: -0.035em;
            color: var(--text);
            margin: 0;
        }
        .ui-score-sub {
            font-size: 0.88rem;
            color: var(--muted);
            margin-top: 0.12rem;
            margin-bottom: 0.65rem;
        }
        .ui-score-row {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            gap: 0.65rem;
            padding: 0.42rem 0 0.34rem 0;
            border-top: 1px solid #e8eef5;
        }
        .ui-score-row:first-of-type {
            border-top: none;
            padding-top: 0;
        }
        .ui-score-name {
            font-size: 0.9rem;
            color: var(--muted);
        }
        .ui-score-value {
            font-size: 1.05rem;
            font-weight: 800;
            color: var(--text);
        }
        .ui-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            padding: 0.27rem 0.62rem;
            font-size: 0.83rem;
            font-weight: 700;
        }
        .ui-badge-promising {
            background: var(--success-bg);
            color: var(--success-text);
        }
        .ui-badge-review {
            background: var(--warning-bg);
            color: var(--warning-text);
        }
        .ui-badge-caution {
            background: var(--danger-bg);
            color: var(--danger-text);
        }
        .ui-score-note {
            margin-top: 0.55rem;
            padding-top: 0.5rem;
            border-top: 1px solid #e8eef5;
            color: var(--muted);
            font-size: 0.76rem;
            line-height: 1.35;
        }
        .ui-status-reason {
            margin-top: 0.45rem;
            color: var(--text);
            font-size: 0.78rem;
            line-height: 1.38;
        }
        .ui-insights {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.8rem 1rem;
            margin-top: 0.72rem;
            align-items: start;
        }
        .ui-insight {
            padding-top: 0.02rem;
        }
        .ui-insight-wide {
            grid-column: 1 / -1;
            padding-bottom: 0.45rem;
        }
        .ui-insight-title {
            font-size: 0.74rem;
            font-weight: 800;
            letter-spacing: 0.11em;
            text-transform: uppercase;
            color: var(--muted-2);
            margin-bottom: 0.28rem;
        }
        .ui-insight-text {
            font-size: 1rem;
            line-height: 1.5;
            color: var(--text);
            margin: 0;
        }
        .ui-card-footer {
            display: flex;
            justify-content: flex-end;
            margin-top: 0.72rem;
            padding-top: 0.65rem;
            border-top: 1px solid #e8eef5;
        }
        .ui-source-link {
            color: var(--accent) !important;
            font-size: 0.9rem;
            font-weight: 700;
            text-decoration: none;
        }
        .ui-source-link:hover {
            text-decoration: underline;
        }
        @media (max-width: 1200px) {
            .ui-card-top {
                grid-template-columns: 1fr;
            }
            .ui-summary-grid {
                grid-template-columns: 1fr;
            }
            .ui-scope-strip {
                grid-template-columns: 1fr;
                gap: 0.55rem;
            }
            .ui-insights {
                grid-template-columns: 1fr;
            }
            .ui-insight-wide {
                grid-column: auto;
            }
            .ui-facts {
                grid-template-columns: 1fr 1fr;
                row-gap: 0.75rem;
            }
            .ui-fact:nth-child(3) {
                padding-left: 0;
                border-left: none;
            }
            .ui-rank {
                text-align: left;
            }
        }
        @media (max-width: 760px) {
            .block-container {
                padding-left: 1rem;
                padding-right: 1rem;
            }
            .ui-hero-title {
                font-size: 2.5rem;
            }
            .ui-card-title {
                font-size: 1.55rem;
            }
            .ui-facts {
                grid-template-columns: 1fr;
            }
            .ui-fact,
            .ui-fact + .ui-fact {
                padding: 0.42rem 0;
                border-left: none;
            }
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div>
        <div class="ui-hero-title">EU Funding Match</div>
        <div class="ui-hero-subtitle">Screen innovation project ideas against active Horizon Europe calls and turn the best matches into a practical review shortlist.</div>
        <div class="ui-hero-focus">
            Built for early funding discovery across critical materials, green energy, ports and maritime, security, and SME/start-up innovation. The tool highlights promising calls, key cautions, next steps, and official source links; final eligibility and proposal decisions still belong in the official call documents.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    total_calls = count_calls()
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

st.markdown("<div class='ui-section-title'>Project description</div>", unsafe_allow_html=True)

with st.form("project_screening_form"):
    trl_choice = "Not sure"
    has_consortium = False
    partner_count = None

    form_cols = st.columns([1.75, 0.95], gap="large")

    with form_cols[0]:
        project_title = st.text_input("Project name (optional)", value="")
        project_desc = st.text_area(
            "Project description",
            height=280,
            placeholder=(
                "Example: We are developing a decision-support solution that helps ports reduce berth-side "
                "emissions by optimising shore power use, electricity demand balancing, and operational planning."
            ),
        )
        st.caption(
            "For stronger matches, include the challenge, sector, proposed solution, target users, "
            "EU relevance, maturity if known, and expected impact."
        )

        with st.expander("Build a stronger project description", expanded=False):
            st.markdown(
                """
                A useful description answers five questions:

                - **Problem:** What operational or market challenge needs to be solved?
                - **Solution:** What will the project develop, demonstrate, or deploy?
                - **Users:** Who will use or benefit from the result?
                - **European value:** Why does this matter across Europe or EU value chains?
                - **Readiness and impact:** What is the current maturity and expected outcome?

                **Critical raw materials and circularity**  
                We are developing a pilot process to recover rare earth elements from industrial and electronic waste.
                The solution combines selective separation, material traceability, and quality validation with European
                manufacturers. It targets recycling operators and industrial supply chains, with the aim of reducing
                reliance on imported critical materials and increasing the use of high-quality secondary raw materials.

                **Port energy and green transition**  
                We are developing an energy-management solution for European ports that coordinates shore power,
                renewable generation, battery storage, and berth demand. Port authorities and terminal operators will
                use the system to reduce vessel emissions at berth, manage electricity peaks, and plan cost-effective
                infrastructure upgrades. The concept is ready for pilot validation in an operational port environment.

                **Maritime and logistics innovation**  
                We are developing a digital planning platform for ports, shipping operators, and logistics providers.
                It combines arrival data, cargo flows, and terminal capacity to reduce waiting time, improve multimodal
                coordination, and lower fuel use. The project will validate interoperable services across European
                transport partners and support more resilient, lower-emission maritime logistics.
                """
            )

    with form_cols[1]:
        st.markdown("**Location and organisation**")
        user_country = st.text_input("Based in", value=DEFAULT_COUNTRY)
        org_label = st.selectbox(
            "Organisation type",
            options=list(ORG_TYPE_OPTIONS.keys()),
            index=0,
        )

        with st.expander("More context", expanded=False):
            trl_choice = st.selectbox(
                "Solution maturity",
                options=TRL_OPTIONS,
                index=0,
                help="Leave this as Not sure if the maturity level is still unclear.",
            )
            has_consortium = st.checkbox("Likely to involve partners", value=False)

            if has_consortium:
                partner_count = st.number_input(
                    "How many organisations are currently involved?",
                    min_value=2,
                    max_value=20,
                    value=2,
                    step=1,
                )
            else:
                partner_count = None

    run_btn = st.form_submit_button("Find relevant funding calls")

if run_btn:
    st.session_state.pop("last_retrieval_inputs", None)
    st.session_state.pop("last_project_inputs", None)
    st.session_state.pop("last_retrieval_mode_used", None)
    st.session_state.pop("last_retrieval_warning", None)
    st.session_state.pop("last_input_quality", None)
    st.session_state.pop("last_results_execution", None)

    if not project_desc.strip():
        render_notice(WEAK_INPUT_GUIDANCE, tone="review")
    else:
        quality_result = evaluate_project_description(project_desc)
        if not quality_result["can_screen"]:
            render_notice(
                NON_PROJECT_INPUT_WARNING
                if quality_result.get("is_likely_non_project")
                else WEAK_INPUT_GUIDANCE,
                tone="review",
            )
        else:
            user_trl = None if trl_choice == "Not sure" else int(trl_choice)
            retrieval_inputs = {
                "project_text": project_desc,
                "top_k": 5,
                "user_country": user_country,
                "user_org_type": ORG_TYPE_OPTIONS[org_label],
                "user_trl": user_trl,
                "has_consortium": has_consortium,
                "partner_count": int(partner_count) if partner_count is not None else None,
            }
            with st.spinner(RETRIEVAL_SPINNER_TEXT):
                candidate_execution = execute_retrieval(
                    **retrieval_inputs,
                    sort_by="strategic_success_index",
                    retrieval_mode=DEFAULT_END_USER_RETRIEVAL_MODE,
                    allow_semantic_fallback=True,
                )
                top_similarity_execution = execute_retrieval(
                    project_text=project_desc,
                    top_k=1,
                    user_country=user_country,
                    user_org_type=ORG_TYPE_OPTIONS[org_label],
                    user_trl=user_trl,
                    has_consortium=has_consortium,
                    partner_count=int(partner_count) if partner_count is not None else None,
                    sort_by="similarity_score",
                    retrieval_mode=candidate_execution["retrieval_mode_used"],
                    allow_semantic_fallback=True,
                )
            candidate_results = candidate_execution["results"]
            top_similarity_result = top_similarity_execution["results"]

            if (
                not candidate_results
                or not top_similarity_result
                or top_similarity_result[0]["similarity_score"] < MIN_DISPLAY_SIMILARITY_SCORE
            ):
                if quality_result.get("is_likely_non_project"):
                    render_notice(NON_PROJECT_INPUT_WARNING, tone="review")
                render_notice(
                    "No reliable funding match was found for the current input. Please revise the project description."
                )
            else:
                st.session_state["last_retrieval_inputs"] = retrieval_inputs
                st.session_state["last_project_inputs"] = {
                    "project_title": project_title,
                    "project_desc": project_desc,
                    "user_country": user_country,
                    "user_org_type": ORG_TYPE_OPTIONS[org_label],
                    "user_trl": user_trl,
                    "has_consortium": has_consortium,
                    "partner_count": int(partner_count) if partner_count is not None else None,
                }
                st.session_state["last_retrieval_mode_used"] = candidate_execution["retrieval_mode_used"]
                st.session_state["last_retrieval_warning"] = candidate_execution["warning"]
                st.session_state["last_input_quality"] = quality_result
                st.session_state["last_results_execution"] = candidate_execution

if "last_retrieval_inputs" in st.session_state:
    st.markdown("<div class='ui-section-title'>Best current matches</div>", unsafe_allow_html=True)
    st.caption("Archived deadlines are excluded from this view.")

    results_execution = st.session_state.get("last_results_execution")
    if results_execution is None:
        with st.spinner(RETRIEVAL_SPINNER_TEXT):
            results_execution = execute_retrieval(
                **st.session_state["last_retrieval_inputs"],
                sort_by="strategic_success_index",
                retrieval_mode=st.session_state.get("last_retrieval_mode_used", "lexical"),
                allow_semantic_fallback=True,
            )
        st.session_state["last_results_execution"] = results_execution
    results = results_execution["results"]
    retrieval_mode_used = results_execution["retrieval_mode_used"]
    retrieval_warning = results_execution["warning"] or st.session_state.get("last_retrieval_warning")
    input_quality = st.session_state.get("last_input_quality") or evaluate_project_description(
        st.session_state["last_project_inputs"].get("project_desc", "")
    )
    st.session_state["last_retrieval_mode_used"] = retrieval_mode_used
    st.session_state["last_retrieval_warning"] = retrieval_warning

    if retrieval_mode_used == "semantic":
        if INTERNAL_MODE:
            st.markdown(
                "<div class='matching-method semantic'>Semantic matching active</div>",
                unsafe_allow_html=True,
            )
    else:
        render_notice(
            retrieval_warning or "Using baseline text matching for this run. Review the shortlist carefully.",
            tone="review",
        )

    if input_quality.get("is_likely_non_project"):
        render_notice(NON_PROJECT_INPUT_WARNING, tone="review")
    elif input_quality.get("needs_more_detail"):
        render_notice(
            f"{WEAK_INPUT_GUIDANCE} Treat these matches as a starting point and review them carefully.",
            tone="review",
        )

    filtered_results = [r for r in results if r["similarity_score"] >= MIN_DISPLAY_SIMILARITY_SCORE]
    project_inputs = st.session_state["last_project_inputs"]
    project_inputs["input_quality"] = input_quality
    project_inputs["retrieval_mode"] = retrieval_mode_used
    display_results = prioritize_client_results(
        select_display_results(filtered_results),
        project_inputs.get("project_desc", ""),
    )
    display_results = with_client_review_statuses(
        display_results,
        input_quality=input_quality,
        retrieval_mode=retrieval_mode_used,
    )
    top_similarity_score = max((r["similarity_score"] for r in results), default=0.0)

    if not display_results:
        render_notice(
            "No sufficiently reliable funding matches are available for summary output. Please refine the project description and review manually."
        )
    else:
        render_shortlist_summary(display_results)

        action_cols = st.columns([1.0, 2.2], gap="medium")
        with action_cols[0]:
            st.download_button(
                label="Download PDF summary",
                data=build_decision_support_pdf(
                    project_inputs=project_inputs,
                    results=display_results,
                ),
                file_name="eu_funding_screening_summary.pdf",
                mime="application/pdf",
            )
        with action_cols[1]:
            if top_similarity_score < MIN_RELIABLE_SIMILARITY_SCORE:
                render_notice(
                    "These are reviewable options rather than firm shortlist candidates. Manual review is recommended before moving forward.",
                    tone="review",
                )
            elif len(display_results) < len(filtered_results):
                render_notice("Only the most relevant current options are shown here.")

        for idx, result in enumerate(display_results, start=1):
            render_result_card(
                result,
                idx,
                input_quality=input_quality,
                retrieval_mode=retrieval_mode_used,
                project_inputs=project_inputs,
            )

with st.sidebar:
    with st.expander("Call library", expanded=False):
        try:
            dataset_status = get_dataset_status()
            st.markdown(
                f"**{dataset_status['open_or_upcoming_records']} active or upcoming calls**"
            )
            st.caption(
                f"{dataset_status['total_records']} records in the working library; "
                f"{dataset_status['expired_records']} archived calls are hidden from default results."
            )

            deadline_issues = (
                dataset_status["unknown_deadline_records"]
                + dataset_status["invalid_deadline_records"]
            )
            if deadline_issues:
                st.caption(f"{deadline_issues} records need deadline confirmation.")

            st.caption(
                "Eligibility coverage is incomplete for "
                f"{dataset_status['missing_eligible_countries']} country fields and "
                f"{dataset_status['missing_eligible_org_types']} organisation fields."
            )
            st.caption(
                "TRL coverage is incomplete for "
                f"{dataset_status['missing_trl_min']} minimum fields and "
                f"{dataset_status['missing_trl_max']} maximum fields."
            )
            st.caption(
                "Use official EU call documents to confirm details before proposal decisions."
            )
        except Exception:
            st.caption("Call library status is temporarily unavailable.")

    if INTERNAL_MODE:
        with st.expander("Internal data and maintenance", expanded=False):
            import pandas as pd

            st.caption("Internal mode is enabled for dataset review and maintenance.")
            st.caption(f"Current screened dataset: {total_calls} calls.")
            if st.button("Reload dataset from clean CSV"):
                try:
                    imported_count = run_seed_import()
                    st.success(f"Reloaded {imported_count} calls from clean CSV.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Import failed: {e}")

            rows = fetch_calls(limit=500)
            df = pd.DataFrame(
                rows,
                columns=[
                    "call_id",
                    "program",
                    "pillar",
                    "cluster",
                    "call_title",
                    "deadline_utc",
                    "trl_min",
                    "trl_max",
                    "source_url",
                    "verified_status",
                ],
            )

            st.dataframe(df, width="stretch", hide_index=True)
