import html
import re
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List

from core.client_experience import build_call_strategy, build_review_status_reason, build_theme_aware_caution
from core.deadlines import (
    EXPIRED,
    INVALID_DEADLINE,
    OPEN_OR_UPCOMING,
    UNKNOWN_DEADLINE,
    classify_deadline,
)
from core.explanations import DEFAULT_MATCH_EXPLANATION
from core.input_quality import evaluate_project_description
from core.scoring import determine_client_review_status
from core.source_urls import canonical_official_topic_url, official_source_label

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
except Exception:
    colors = None
    A4 = None
    ParagraphStyle = None
    getSampleStyleSheet = None
    mm = None
    Paragraph = None
    KeepTogether = None
    SimpleDocTemplate = None
    Spacer = None
    Table = None
    TableStyle = None


REPORT_TITLE = "EU Funding Screening Summary"
DATASET_NOTE = (
    "Call details should be confirmed in the official EU documents before proposal decisions."
)
SCORE_NOTE = "The fit score supports early screening; it is not a funding probability."


def _format_value(value: Any) -> str:
    if value in [None, ""]:
        return "Not provided"
    return str(value)


def _format_org_type(value: Any) -> str:
    normalized = str(value or "").strip()
    mapping = {
        "sme": "SME",
        "smes": "SMEs",
        "company": "Company",
        "research institute": "Research organisation",
        "research organisation": "Research organisation",
        "university": "University",
        "public body": "Public body",
    }
    return mapping.get(normalized.lower(), normalized or "Not provided")


def _format_text_match(score: Any) -> str:
    return f"{float(score or 0.0) * 100:.0f} / 100"


def _format_generated_at() -> str:
    generated_at = datetime.now().astimezone()
    offset = generated_at.strftime("%z")
    timezone_label = f"UTC{offset[:3]}:{offset[3:]}" if offset else "local time"
    return f"{generated_at:%d %b %Y, %H:%M} {timezone_label}"


def _format_matching_method(project_inputs: Dict[str, Any]) -> str:
    if str(project_inputs.get("retrieval_mode") or "").strip().lower() == "semantic":
        return "Semantic matching"
    return "Baseline text matching"


def _format_programme_cluster(result: Dict[str, Any]) -> str:
    values = []
    for value in (result.get("program"), result.get("cluster")):
        normalized = str(value or "").strip()
        if normalized and normalized not in values:
            values.append(normalized)
    return " / ".join(values) or "Not listed"


def _format_deadline_status(result: Dict[str, Any]) -> str:
    deadline_value = result.get("deadline_utc")
    status = result.get("deadline_status") or classify_deadline(deadline_value)
    deadline = _parse_deadline(deadline_value)
    date_text = deadline.strftime("%d %b %Y") if deadline else ""

    if status == OPEN_OR_UPCOMING:
        return f"Open or upcoming - {date_text}" if date_text else "Open or upcoming"
    if status == EXPIRED:
        return f"Expired - {date_text}" if date_text else "Expired"
    if status == UNKNOWN_DEADLINE:
        return "Deadline not listed - check the official source"
    if status == INVALID_DEADLINE:
        return "Deadline needs confirmation on the official source"
    return "Deadline needs confirmation on the official source"


def _format_trl_alignment(result: Dict[str, Any]) -> str | None:
    trl_min = result.get("trl_min")
    trl_max = result.get("trl_max")
    alignment = (result.get("strategic_success_components") or {}).get("trl_alignment")

    if trl_min in [None, ""] and trl_max in [None, ""]:
        return None

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


def _active_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        result
        for result in results
        if (result.get("deadline_status") or classify_deadline(result.get("deadline_utc")))
        == OPEN_OR_UPCOMING
    ]


def _safe_markup(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _format_review_status(result: Dict[str, Any], project_inputs: Dict[str, Any]) -> str:
    input_quality = project_inputs.get("input_quality") or evaluate_project_description(
        str(project_inputs.get("project_desc") or "")
    )
    return determine_client_review_status(
        result.get("similarity_score"),
        input_quality=input_quality,
        retrieval_mode=project_inputs.get("retrieval_mode"),
        internal_confidence_label=result.get("match_confidence_label"),
        theme_coherence=result.get("theme_coherence"),
    )


def _format_eligibility_view(result: Dict[str, Any]) -> str:
    status = result.get("eligibility_status")
    if status == "Eligible":
        return "Broadly aligned with the available call details."
    if status == "Partially Eligible":
        return "Potentially aligned, but one or more eligibility points still need confirmation."
    return "The available call details suggest a likely mismatch."


def _parse_deadline(deadline_utc: Any) -> datetime | None:
    if deadline_utc in [None, ""]:
        return None
    try:
        return datetime.fromisoformat(str(deadline_utc).replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_primary_caution(result: Dict[str, Any]) -> str | None:
    reasons = result.get("eligibility_reasons") or []
    warnings = result.get("eligibility_warnings") or []
    data_quality_flags = result.get("data_quality_flags") or []
    trl_alignment = (result.get("strategic_success_components") or {}).get("trl_alignment", 100.0)
    result_text = _build_result_text(result)
    deadline = _parse_deadline(result.get("deadline_utc"))
    generic_eligibility_issue = any(
        term in " ".join([str(item).lower() for item in reasons + warnings + data_quality_flags])
        for term in ["country", "organisation", "eligible countries", "metadata"]
    )
    guardrails = set((result.get("theme_coherence") or {}).get("guardrails") or [])

    theme_caution = build_theme_aware_caution(result)
    if theme_caution:
        return theme_caution

    if _contains_any(result_text, ["direct recycling"]):
        return "Check whether the call expects direct-recycling performance and recovered material quality rather than broader circularity aims."

    if _contains_any(result_text, ["battery", "battery materials"]) and _contains_any(
        result_text, ["recycling", "direct recycling"]
    ):
        return "Check whether the call is focused on recovered battery-grade materials rather than broader battery value-chain activity."

    if _contains_any(result_text, ["battery", "battery materials", "raw materials"]) and _contains_any(
        result_text, ["refining", "processing"]
    ) and not _contains_any(result_text, ["secondary raw materials", "recycling"]):
        return "Check whether the call is centred on materials upgrading or refining rather than broader circularity aims."

    if _contains_any(result_text, ["substitution", "dependency", "dependencies"]):
        return "Check whether the call is framed around dependency reduction or substitution rather than recovery activity."

    if _contains_any(result_text, ["secondary raw materials", "recycling"]):
        return "Check whether the call expects recovery scale and processing depth rather than a broader circular-economy framing."

    if _contains_any(result_text, ["shore", "berth"]):
        return "Check whether the scope is berth-side electrification rather than wider port decarbonisation."

    if _contains_any(result_text, ["shipyard", "shipyards"]):
        return "Check whether the scope is shipyard and vessel-side transition rather than port-side infrastructure."

    if _contains_any(result_text, ["terminal", "infrastructure"]):
        return "Check whether the scope is infrastructure upgrade rather than operational optimisation alone."

    if _contains_any(result_text, ["shipping", "ships", "waterborne"]):
        return "Check whether the emphasis is on shipping operations rather than port-side infrastructure."

    if _contains_any(result_text, ["security", "critical infrastructure", "anomaly"]):
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


def _guidance_priority(item: str) -> int:
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


def _select_primary_next_step(result: Dict[str, Any]) -> str | None:
    guidance_items = result.get("next_step_guidance") or []
    if not guidance_items:
        return None
    return min(guidance_items, key=_guidance_priority)


def _build_result_text(result: Dict[str, Any]) -> str:
    parts = [
        result.get("call_title", ""),
        result.get("keywords", ""),
        result.get("description", ""),
        result.get("objectives", ""),
        result.get("expected_impact", ""),
    ]
    return " ".join(str(part or "").lower() for part in parts)


def _contains_any(text: str, terms: List[str]) -> bool:
    return any(term in text for term in terms)


def _contains_whole_term(text: str, terms: List[str]) -> bool:
    return any(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) for term in terms)


def _detect_result_theme(result: Dict[str, Any]) -> str:
    text = _build_result_text(result)

    if _contains_any(text, ["critical raw materials", "raw materials", "rare earth", "recycling"]):
        return "Critical raw materials and recycling"

    if _contains_whole_term(text, ["shore", "berth", "port", "ports", "harbour", "harbours"]) and _contains_any(
        text, ["energy", "electrification", "emissions", "electricity"]
    ):
        return "Port energy systems and maritime infrastructure"

    if _contains_any(
        text,
        [
            "wind",
            "wind energy",
            "solar",
            "photovoltaic",
            "renewable",
            "clean energy",
            "clean technologies",
            "energy efficiency",
            "energy transition",
            "industrial decarbon",
            "emissions reduction",
            "storage",
            "grid",
        ],
    ):
        return "Green energy and industrial decarbonisation"

    if _contains_any(
        text,
        [
            "security",
            "critical infrastructure",
            "cybersecurity",
            "physical protection",
            "threat",
            "risk assessment",
            "emergency preparedness",
            "anomaly detection",
        ],
    ):
        return "Infrastructure security and resilience"

    if _contains_any(text, ["shipping", "ship", "waterborne", "maritime"]):
        return "Maritime operations and shipping innovation"

    return "Thematically relevant funding calls"


def _build_shortlist_reason(results: List[Dict[str, Any]]) -> str:
    if not results:
        return "No current shortlist is available."

    top_theme = _detect_result_theme(results[0])

    if top_theme == "Critical raw materials and recycling":
        return "The clearest options focus on raw-material recovery, recycling, processing, or supply-chain resilience."

    if top_theme == "Port energy systems and maritime infrastructure":
        return "The clearest options connect port or maritime activity with energy use, electrification, or emissions reduction."

    if top_theme == "Green energy and industrial decarbonisation":
        return "The clearest options connect clean-energy innovation with emissions reduction, storage, grid readiness, or industrial decarbonisation."

    if top_theme == "Infrastructure security and resilience":
        return "The clearest options focus on infrastructure protection, monitoring, and operational resilience."

    return results[0].get("match_explanation") or "The shortlist is based on the closest current thematic overlap."


def _build_shortlist_caution(
    results: List[Dict[str, Any]],
    project_inputs: Dict[str, Any] | None = None,
) -> str:
    if not results:
        return "Manual review is still required."

    cautions = [
        build_theme_aware_caution(result, project_inputs) or _build_primary_caution(result)
        for result in results
    ]
    cautions = [caution for caution in cautions if caution]
    if not cautions:
        return "Manual review is still required before shortlisting any call."

    if any("Eligibility conditions should still be confirmed" in caution for caution in cautions):
        return "Eligibility conditions should still be confirmed on the official call pages."

    if any("consortium" in caution.lower() for caution in cautions):
        return "Consortium expectations may be more demanding than the current project setup."

    if any("reviewable" in caution.lower() for caution in cautions):
        return "The shortlist is useful, but it should still be treated as an early screening view."

    return cautions[0]


def _build_shortlist_count_text(
    results: List[Dict[str, Any]],
    project_inputs: Dict[str, Any] | None = None,
) -> str:
    count = len(results)
    if project_inputs is not None and results:
        statuses = [_format_review_status(result, project_inputs) for result in results]
        status_counts = {
            "Strong match": statuses.count("Strong match"),
            "Worth reviewing": statuses.count("Worth reviewing"),
            "Needs more detail": statuses.count("Needs more detail"),
        }
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
        if parts:
            return f"{count} current option{'s' if count != 1 else ''} found: {', '.join(parts)}."
    if count == 1:
        return "1 current option found."
    return f"{count} current options found."


def _build_summary_lead(results: List[Dict[str, Any]]) -> str:
    if not results:
        return "No shortlist is currently available."

    theme = _detect_result_theme(results[0])

    if theme == "Critical raw materials and recycling":
        return "The clearest current opportunity area is critical raw materials, recycling, and related processing."

    if theme == "Port energy systems and maritime infrastructure":
        return "The clearest current opportunity area is port energy, shore-side infrastructure, and related emissions reduction."

    if theme == "Green energy and industrial decarbonisation":
        return "The clearest current opportunity area is clean-energy innovation and industrial decarbonisation."

    if theme == "Infrastructure security and resilience":
        return "The clearest current opportunity area is infrastructure security, resilience, and operational monitoring."

    return "The shortlist reflects the closest thematic overlap in the current call set."


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_plain_text_pdf(project_inputs: Dict[str, Any], results: List[Dict[str, Any]]) -> bytes:
    active_results = _active_results(results)

    lines = [
        REPORT_TITLE,
        f"Generated: {_format_generated_at()}",
        "",
        "Project Summary",
        f"Applicant Country: {_format_value(project_inputs.get('user_country'))}",
        f"Organisation Type: {_format_org_type(project_inputs.get('user_org_type'))}",
        f"Project TRL: {_format_value(project_inputs.get('user_trl'))}",
        f"Project Description: {_format_value(project_inputs.get('project_desc'))}",
        f"Matching Method: {_format_matching_method(project_inputs)}",
        "",
        DATASET_NOTE,
        SCORE_NOTE,
        "",
        "Call Shortlist",
    ]
    if str(project_inputs.get("project_title") or "").strip():
        lines.insert(4, f"Project Title: {_format_value(project_inputs.get('project_title'))}")

    if not active_results:
        lines.append("No active recommended calls were available for this export.")

    for index, result in enumerate(active_results, start=1):
        review_status = _format_review_status(result, project_inputs)
        input_quality = project_inputs.get("input_quality") or evaluate_project_description(
            str(project_inputs.get("project_desc") or "")
        )
        status_reason = build_review_status_reason(
            result,
            review_status,
            input_quality=input_quality,
        )
        strategy = build_call_strategy(result, project_inputs)
        lines.extend(
            [
                "",
                f"{index}. {_format_value(result.get('call_title'))}",
                f"Call: {_format_value(result.get('call_id'))}",
                f"Programme / Cluster: {_format_programme_cluster(result)}",
                f"Overall Fit: {float(result.get('strategic_success_index', 0.0)):.0f} / 100",
                f"Relevance: {_format_text_match(result.get('similarity_score', 0.0))}",
                f"Review Status: {review_status}",
                f"Why This Status: {status_reason}",
                f"Deadline Status: {_format_deadline_status(result)}",
                f"Why This Matched: {_format_value(result.get('match_explanation') or DEFAULT_MATCH_EXPLANATION)}",
                f"Eligibility View: {_format_eligibility_view(result)}",
            ]
        )
        trl_alignment = _format_trl_alignment(result)
        if trl_alignment:
            lines.append(f"TRL Alignment: {trl_alignment}")
        primary_next_step = strategy["next_steps"][0] if strategy["next_steps"] else _select_primary_next_step(result)
        if primary_next_step:
            lines.append(f"Recommended Next Action: {_format_value(primary_next_step)}")
        primary_caution = build_theme_aware_caution(result, project_inputs) or _build_primary_caution(result)
        if primary_caution:
            lines.append(f"Main Caution: {_format_value(primary_caution)}")
        if strategy["clarifications"]:
            lines.append(f"What To Clarify: {'; '.join(strategy['clarifications'])}")
        for step_index, item in enumerate(strategy["next_steps"][:3], start=1):
            lines.append(f"Next Step {step_index}: {item}")
        if result.get("source_url"):
            official_url = canonical_official_topic_url(result.get("call_id"), result.get("source_url"))
            lines.append(f"Official Source: {official_url}")

    lines.extend(
        [
            "",
            "Next Step",
            "Use this shortlist to focus manual review on the most relevant current options and confirm details in the official call documents.",
        ]
    )

    page_lines: List[str] = []
    for line in lines:
        text = line or " "
        while len(text) > 95:
            page_lines.append(text[:95])
            text = text[95:]
        page_lines.append(text)

    content_parts = ["BT", "/F1 11 Tf", "50 790 Td", "14 TL"]
    for index, line in enumerate(page_lines):
        escaped_line = _escape_pdf_text(line)
        if index == 0:
            content_parts.append(f"({_escape_pdf_text(line)}) Tj")
        else:
            content_parts.append("T*")
            content_parts.append(f"({escaped_line}) Tj")
    content_parts.append("ET")
    content_stream = "\n".join(content_parts).encode("latin-1", errors="replace")

    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        (
            f"5 0 obj\n<< /Length {len(content_stream)} >>\nstream\n".encode("ascii")
            + content_stream
            + b"\nendstream\nendobj\n"
        ),
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode(
                "ascii"
            )
        )
    )
    return bytes(pdf)


def _build_project_summary_table(project_inputs: Dict[str, Any]) -> Table:
    rows = []
    if str(project_inputs.get("project_title") or "").strip():
        rows.append(["Project title", _format_value(project_inputs.get("project_title"))])
    rows.extend(
        [
            ["Applicant country", _format_value(project_inputs.get("user_country"))],
            ["Organisation type", _format_org_type(project_inputs.get("user_org_type"))],
            ["Project TRL", _format_value(project_inputs.get("user_trl"))],
            ["Consortium already identified", "Yes" if project_inputs.get("has_consortium") else "No"],
        ]
    )
    if project_inputs.get("has_consortium"):
        rows.append(["Current partner count", _format_value(project_inputs.get("partner_count"))])

    table = Table(rows, colWidths=[50 * mm, 120 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _build_report_styles(styles: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=23,
            textColor=colors.HexColor("#10233F"),
            spaceAfter=4,
        ),
        "generated": ParagraphStyle(
            "GeneratedAt",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#65758B"),
        ),
        "section": ParagraphStyle(
            "ReportSection",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#10233F"),
            spaceBefore=4,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "ReportBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#1F2937"),
        ),
        "small": ParagraphStyle(
            "ReportSmall",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#5B687A"),
        ),
        "call_title": ParagraphStyle(
            "CallTitle",
            parent=styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#10233F"),
            spaceAfter=0,
        ),
        "status": ParagraphStyle(
            "CallStatus",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            alignment=2,
            textColor=colors.HexColor("#315C45"),
        ),
        "metric": ParagraphStyle(
            "Metric",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#1F2937"),
            alignment=1,
        ),
        "detail_label": ParagraphStyle(
            "DetailLabel",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#5B687A"),
        ),
        "detail_value": ParagraphStyle(
            "DetailValue",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#1F2937"),
            wordWrap="CJK",
        ),
    }


def _build_note_table(text: str, report_styles: Dict[str, Any]) -> Table:
    table = Table(
        [[Paragraph(_safe_markup(text), report_styles["small"])]],
        colWidths=[170 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F5F7FA")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D7DEE8")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _build_call_section(
    result: Dict[str, Any],
    index: int,
    project_inputs: Dict[str, Any],
    report_styles: Dict[str, Any],
) -> List[Any]:
    title = _format_value(result.get("call_title"))
    review_status = _format_review_status(result, project_inputs)
    input_quality = project_inputs.get("input_quality") or evaluate_project_description(
        str(project_inputs.get("project_desc") or "")
    )
    status_reason = build_review_status_reason(
        result,
        review_status,
        input_quality=input_quality,
    )
    strategy = build_call_strategy(result, project_inputs)
    header = Table(
        [[
            Paragraph(f"{index}. {_safe_markup(title)}", report_styles["call_title"]),
            Paragraph(_safe_markup(review_status), report_styles["status"]),
        ]],
        colWidths=[137 * mm, 33 * mm],
    )
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F2F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#C9D4E2")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    call_id = _format_value(result.get("call_id"))
    programme_cluster = _format_programme_cluster(result)
    metadata = Paragraph(
        f"<b>Call:</b> {_safe_markup(call_id)} &nbsp;&nbsp; "
        f"<b>Programme / cluster:</b> {_safe_markup(programme_cluster)}",
        report_styles["small"],
    )

    metric_values = [
        ("Overall fit", f"{float(result.get('strategic_success_index', 0.0)):.0f} / 100"),
        ("Relevance", _format_text_match(result.get("similarity_score", 0.0))),
        ("Review status", review_status),
        ("Deadline", _format_deadline_status(result)),
    ]
    metric_cells = [
        Paragraph(
            f"<font color='#65758B'>{_safe_markup(label)}</font><br/>"
            f"<b>{_safe_markup(value)}</b>",
            report_styles["metric"],
        )
        for label, value in metric_values
    ]
    metrics = Table([metric_cells], colWidths=[42.5 * mm] * 4)
    metrics.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FBFCFE")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D7DEE8")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E3E8EF")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    detail_rows = [
        [
            Paragraph("Why this matched", report_styles["detail_label"]),
            Paragraph(
                _safe_markup(result.get("match_explanation") or DEFAULT_MATCH_EXPLANATION),
                report_styles["detail_value"],
            ),
        ],
        [
            Paragraph("Why this status", report_styles["detail_label"]),
            Paragraph(_safe_markup(status_reason), report_styles["detail_value"]),
        ],
        [
            Paragraph("Eligibility view", report_styles["detail_label"]),
            Paragraph(_safe_markup(_format_eligibility_view(result)), report_styles["detail_value"]),
        ],
    ]

    trl_alignment = _format_trl_alignment(result)
    if trl_alignment:
        detail_rows.append(
            [
                Paragraph("TRL alignment", report_styles["detail_label"]),
                Paragraph(_safe_markup(trl_alignment), report_styles["detail_value"]),
            ]
        )

    if strategy["clarifications"]:
        detail_rows.append(
            [
                Paragraph("What to clarify", report_styles["detail_label"]),
                Paragraph(
                    _safe_markup("; ".join(strategy["clarifications"])),
                    report_styles["detail_value"],
                ),
            ]
        )

    if strategy["next_steps"]:
        steps_text = "<br/>".join(
            f"{index}. {_safe_markup(item)}"
            for index, item in enumerate(strategy["next_steps"][:3], start=1)
        )
        detail_rows.append(
            [
                Paragraph("Next steps for this call", report_styles["detail_label"]),
                Paragraph(steps_text, report_styles["detail_value"]),
            ]
        )

    caution = build_theme_aware_caution(result, project_inputs) or _build_primary_caution(result)
    if caution:
        detail_rows.append(
            [
                Paragraph("Main caution", report_styles["detail_label"]),
                Paragraph(_safe_markup(caution), report_styles["detail_value"]),
            ]
        )

    source_url = str(result.get("source_url") or "").strip()
    if source_url:
        official_url = canonical_official_topic_url(result.get("call_id"), source_url)
        safe_url = _safe_markup(official_url)
        safe_label = _safe_markup(official_source_label(result.get("call_id")))
        detail_rows.append(
            [
                Paragraph("Official source", report_styles["detail_label"]),
                Paragraph(
                    f"<link href='{safe_url}' color='#1D4F7A'>{safe_label}</link>",
                    report_styles["detail_value"],
                ),
            ]
        )

    details = Table(detail_rows, colWidths=[38 * mm, 132 * mm])
    details.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.35, colors.HexColor("#E3E8EF")),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    return [
        KeepTogether([header, Spacer(1, 4), metadata, Spacer(1, 5), metrics]),
        Spacer(1, 4),
        details,
        Spacer(1, 12),
    ]


def _draw_page_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D7DEE8"))
    canvas.setLineWidth(0.4)
    canvas.line(18 * mm, 13 * mm, 192 * mm, 13 * mm)
    canvas.setFillColor(colors.HexColor("#65758B"))
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(18 * mm, 8 * mm, REPORT_TITLE)
    canvas.drawRightString(192 * mm, 8 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _build_results_table(
    results: List[Dict[str, Any]],
    styles: Dict[str, Any],
    project_inputs: Dict[str, Any],
) -> Table:
    body_style = ParagraphStyle(
        "PdfBodyCell",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=9,
        spaceAfter=0,
        wordWrap="CJK",
    )

    header_style = ParagraphStyle(
        "PdfHeaderCell",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=9,
        textColor=colors.white,
        alignment=1,
    )

    rows = [[
        Paragraph("Funding Call", header_style),
        Paragraph("Overall Fit", header_style),
        Paragraph("Relevance", header_style),
        Paragraph("Review Status", header_style),
    ]]

    for result in results:
        funding_call_text = (
            f"<b>{_format_value(result.get('call_id'))}</b><br/>"
            f"{_format_value(result.get('call_title'))}"
        )
        rows.append(
            [
                Paragraph(funding_call_text, body_style),
                Paragraph(f"{float(result.get('strategic_success_index', 0.0)):.2f}", body_style),
                Paragraph(_format_text_match(result.get('similarity_score', 0.0)), body_style),
                Paragraph(_format_review_status(result, project_inputs), body_style),
            ]
        )

    table = Table(
        rows,
        colWidths=[96 * mm, 24 * mm, 22 * mm, 26 * mm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _build_screening_notes(results: List[Dict[str, Any]], styles: Dict[str, Any]) -> List[Any]:
    story = [Paragraph("Why Each Call Is Worth Reviewing", styles["Heading2"]), Spacer(1, 6)]
    for result in results:
        explanation = result.get("match_explanation") or DEFAULT_MATCH_EXPLANATION
        story.append(
            Paragraph(
                f"<b>{_format_value(result.get('call_id'))}</b>: {_format_value(explanation)}",
                styles["BodyText"],
            )
        )
        story.append(
            Paragraph(
                f"Eligibility view: {_format_eligibility_view(result)}",
                styles["BodyText"],
            )
        )
        strategy = build_call_strategy(result, {})
        primary_next_step = strategy["next_steps"][0] if strategy["next_steps"] else _select_primary_next_step(result)
        if primary_next_step:
            story.append(
                Paragraph(
                    f"Most useful next step: {_format_value(primary_next_step)}",
                    styles["BodyText"],
                )
            )
        primary_caution = build_theme_aware_caution(result, {}) or _build_primary_caution(result)
        if primary_caution:
            story.append(
                Paragraph(
                    f"Main caution: {_format_value(primary_caution)}",
                    styles["BodyText"],
                )
            )
        story.append(Spacer(1, 4))
    return story


def _build_screening_readout(
    results: List[Dict[str, Any]],
    report_styles: Dict[str, Any],
    project_inputs: Dict[str, Any],
) -> List[Any]:
    if not results:
        return []

    return [
        Paragraph("Shortlist overview", report_styles["section"]),
        Spacer(1, 6),
        Paragraph(_safe_markup(_build_summary_lead(results)), report_styles["body"]),
        Spacer(1, 6),
        Paragraph(_safe_markup(_build_shortlist_count_text(results, project_inputs)), report_styles["body"]),
        Spacer(1, 4),
        Paragraph(
            f"<b>Main opportunity area:</b> {_safe_markup(_detect_result_theme(results[0]))}",
            report_styles["body"],
        ),
        Spacer(1, 4),
        Paragraph(
            f"<b>Why it stands out:</b> {_safe_markup(_build_shortlist_reason(results))}",
            report_styles["body"],
        ),
        Spacer(1, 4),
        Paragraph(
            f"<b>Main caution:</b> {_safe_markup(_build_shortlist_caution(results, project_inputs))}",
            report_styles["body"],
        ),
        Spacer(1, 12),
    ]


def build_decision_support_pdf(
    project_inputs: Dict[str, Any],
    results: List[Dict[str, Any]],
) -> bytes:
    active_results = _active_results(results)
    if SimpleDocTemplate is None:
        return _build_plain_text_pdf(project_inputs, active_results)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    report_styles = _build_report_styles(styles)
    story = []

    story.append(Paragraph(REPORT_TITLE, report_styles["title"]))
    story.append(
        Paragraph(
            f"Generated {_safe_markup(_format_generated_at())}",
            report_styles["generated"],
        )
    )
    story.append(Spacer(1, 12))

    story.append(Paragraph("Project summary", report_styles["section"]))
    story.append(_build_project_summary_table(project_inputs))
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            f"<b>Project description:</b> {_safe_markup(_format_value(project_inputs.get('project_desc')))}",
            report_styles["body"],
        )
    )
    story.append(Spacer(1, 8))

    method_summary = Table(
        [[
            Paragraph(
                f"<b>Matching method</b><br/>{_safe_markup(_format_matching_method(project_inputs))}",
                report_styles["body"],
            ),
            Paragraph(
                f"<b>Current options in this memo</b><br/>{len(active_results)}",
                report_styles["body"],
            ),
        ]],
        colWidths=[110 * mm, 60 * mm],
    )
    method_summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D7DEE8")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E3E8EF")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(method_summary)
    story.append(Spacer(1, 8))
    story.append(_build_note_table(DATASET_NOTE, report_styles))
    story.append(Spacer(1, 5))
    story.append(_build_note_table(SCORE_NOTE, report_styles))
    story.append(Spacer(1, 14))

    if active_results:
        story.extend(_build_screening_readout(active_results, report_styles, project_inputs))

    story.append(Paragraph("Call shortlist", report_styles["section"]))
    if not active_results:
        story.append(
            Paragraph(
                "No active recommended calls were available for this export.",
                report_styles["body"],
            )
        )
    else:
        for index, result in enumerate(active_results, start=1):
            story.extend(_build_call_section(result, index, project_inputs, report_styles))

    story.append(Paragraph("Suggested next step", report_styles["section"]))
    story.append(
        Paragraph(
            "Use this shortlist to focus manual review on the most relevant current options, then confirm scope, eligibility, deadline, and consortium requirements in the official call documents.",
            report_styles["body"],
        )
    )

    doc.build(story, onFirstPage=_draw_page_footer, onLaterPages=_draw_page_footer)
    return buffer.getvalue()
