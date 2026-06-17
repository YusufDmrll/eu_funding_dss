from datetime import datetime, UTC
from typing import Any, Dict, List


MAX_GUIDANCE_ITEMS = 2
DEADLINE_REVIEW_WINDOW_DAYS = 150


def _parse_deadline(deadline_utc: Any) -> datetime | None:
    if deadline_utc in [None, ""]:
        return None
    try:
        parsed = datetime.fromisoformat(str(deadline_utc).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    except ValueError:
        return None


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


def _build_theme_specific_guidance(result: Dict[str, Any]) -> str | None:
    text = _build_result_text(result)

    if _contains_any(text, ["direct recycling"]):
        return (
            "Check whether the call expects direct recycling routes, recovered material quality, or wider circular-processing capacity."
        )

    if _contains_any(text, ["rare earth", "extraction"]):
        return (
            "Confirm whether the call expects extraction, recovery, or upstream processing before positioning the project."
        )

    if _contains_any(text, ["processing", "refining"]) and _contains_any(
        text, ["critical raw materials", "raw materials", "rare earth"]
    ) and not _contains_any(text, ["recycling", "secondary raw materials"]):
        return (
            "Check whether the call is aimed at processing and refining capability rather than recycling-led recovery."
        )

    if _contains_any(text, ["battery", "battery materials"]) and _contains_any(
        text, ["recycling", "direct recycling"]
    ):
        return (
            "Check whether the call prioritises recovered battery-grade materials, recycling performance, or wider battery value-chain capacity."
        )

    if _contains_any(text, ["battery", "battery materials"]) and _contains_any(
        text, ["raw materials", "critical raw materials", "rare earth"]
    ):
        return (
            "Check whether the call is positioned around battery materials, materials upgrading, or broader raw-material supply capacity."
        )

    if _contains_any(text, ["value chain", "supply chain", "capacity"]) and _contains_any(
        text, ["critical raw materials", "raw materials", "rare earth"]
    ):
        return (
            "Check whether the call is aimed at value-chain capacity, strategic resilience, or process deployment before shortlisting."
        )

    if _contains_any(text, ["critical raw materials", "raw materials", "recycling"]):
        return (
            "Confirm whether the call is centred on recycling, recovery, or substitution so the project is positioned on the right value-chain step."
        )

    if _contains_any(text, ["shore", "berth"]) and _contains_any(
        text, ["energy", "electrification", "emissions", "electricity"]
    ):
        return (
            "Confirm whether the call is specifically aimed at shore-power deployment, berth operations, or port-side electricity management."
        )

    if _contains_any(text, ["shipyard", "shipyards"]) and _contains_any(
        text, ["port", "ports", "energy", "electrification", "electricity", "emissions"]
    ):
        return (
            "Check whether the call is centred on shipyard and vessel-side transition activity rather than port-side infrastructure."
        )

    if _contains_any(text, ["terminal"]) and _contains_any(
        text, ["port", "ports", "energy", "electrification", "electricity"]
    ):
        return (
            "Check whether the call is centred on terminal systems and infrastructure upgrades or a wider port planning scope."
        )

    if _contains_any(text, ["infrastructure", "terminal"]) and _contains_any(
        text, ["port", "ports", "energy", "electrification", "electricity"]
    ):
        return (
            "Check whether the call is primarily about port infrastructure upgrades, terminal systems, or wider network coordination."
        )

    if _contains_any(text, ["port", "ports"]) and _contains_any(
        text, ["energy", "electrification", "emissions", "electricity"]
    ):
        return (
            "Confirm whether the call prioritises port infrastructure and energy planning or a wider transport decarbonisation scope."
        )

    if _contains_any(text, ["security", "critical infrastructure", "resilience", "anomaly"]):
        return (
            "Confirm whether the call is centred on monitoring and anomaly detection, protection of critical assets, or broader resilience measures."
        )

    return None


def build_next_step_guidance(
    result: Dict[str, Any],
    *,
    user_trl: int | None,
    has_consortium: bool,
    partner_count: int | None,
) -> List[str]:
    guidance: List[str] = []
    eligibility_follow_up: str | None = None

    eligibility_status = result.get("eligibility_status")
    eligibility_warnings = result.get("eligibility_warnings") or []
    eligibility_reasons = result.get("eligibility_reasons") or []
    data_quality_flags = result.get("data_quality_flags") or []
    confidence = result.get("match_confidence_label")

    consortium_required = result.get("consortium_required") in [1, "1", True]
    min_partners = result.get("min_partners")
    trl_alignment = (result.get("strategic_success_components") or {}).get("trl_alignment", 100.0)
    deadline = _parse_deadline(result.get("deadline_utc"))
    now = datetime.now(UTC)

    # Priority 1: eligibility / data validation
    if eligibility_status == "Not Eligible" or eligibility_reasons:
        guidance.append(
            "Review eligibility conditions carefully before treating this as a viable target call."
        )
    elif data_quality_flags:
        eligibility_follow_up = (
            "Validate the key eligibility details against the official call text."
        )
    elif eligibility_warnings:
        eligibility_follow_up = (
            "Confirm the main eligibility conditions manually before shortlisting this result."
        )
    elif confidence == "Needs Review":
        eligibility_follow_up = (
            "Treat this as a reviewable match and confirm the thematic fit against the official call text."
        )

    # Priority 2: theme-fit positioning
    theme_specific_guidance = _build_theme_specific_guidance(result)
    if theme_specific_guidance:
        guidance.append(theme_specific_guidance)

    # Priority 3: consortium / TRL
    if consortium_required and (not has_consortium or (partner_count is not None and min_partners not in [None, ""] and int(partner_count) < int(min_partners))):
        guidance.append(
            "Review consortium expectations and current partner readiness before moving forward."
        )
    elif consortium_required:
        guidance.append(
            "Confirm consortium structure and partner roles against the official call requirements."
        )
    elif user_trl is not None and trl_alignment < 100:
        guidance.append(
            "Confirm TRL positioning against the expected maturity range in the official call text."
        )

    # Priority 4: deadline / work programme
    if deadline is not None and (deadline - now).days <= DEADLINE_REVIEW_WINDOW_DAYS:
        guidance.append(
            "Review the official work programme and the current listed deadline before deciding whether to shortlist this call."
        )
    elif not guidance and confidence in {"Reliable", "Needs Review"}:
        guidance.append(
            "Review the official call page, expected impact, and current listed deadline before shortlisting."
        )

    if eligibility_follow_up and len(guidance) < MAX_GUIDANCE_ITEMS:
        guidance.append(eligibility_follow_up)

    # De-duplicate while preserving priority order.
    unique_guidance: List[str] = []
    for item in guidance:
        if item not in unique_guidance:
            unique_guidance.append(item)

    return unique_guidance[:MAX_GUIDANCE_ITEMS]
