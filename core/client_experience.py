import os
import re
from typing import Any, Dict, Iterable, List


INTERNAL_MODE_ENV = "EU_FUNDING_INTERNAL_MODE"

PORT_SIDE_PROJECT_TERMS = (
    "shore power",
    "berth",
    "harbour energy",
    "port energy",
    "port authority",
    "port authorities",
    "terminal operator",
    "terminal operators",
    "port infrastructure",
    "port-side",
    "port side",
)

PORT_SIDE_CALL_TERMS = (
    "shore power",
    "berth",
    "harbour",
    "harbours",
    "port authority",
    "port authorities",
    "port infrastructure",
    "port area",
    "port areas",
    "port operation",
    "port operations",
    "ports",
    "terminal operator",
    "terminal operators",
    "terminal infrastructure",
)

SHIP_SIDE_CALL_TERMS = (
    "onboard",
    "ship propulsion",
    "propulsion system",
    "vessel propulsion",
    "ship energy efficiency",
    "fuel consumption of ships",
    "battery-electric operation of ferries",
)

THEME_LABELS = {
    "critical_materials_circularity": "critical materials and circularity",
    "port_energy_hydrogen": "port energy and clean-energy transition",
    "maritime_ports_logistics": "maritime, port, and logistics",
    "security_resilience_infrastructure": "security and critical-infrastructure resilience",
    "sme_startup_ecosystem": "SME and innovation-ecosystem support",
    "digital_ai_automation": "digital and automation",
    "transport_mobility_supply_chain": "transport and supply-chain",
}

THEME_COPY_PRIORITY = (
    "port_energy_hydrogen",
    "critical_materials_circularity",
    "security_resilience_infrastructure",
    "maritime_ports_logistics",
    "transport_mobility_supply_chain",
    "sme_startup_ecosystem",
    "digital_ai_automation",
)


def _normalize(value: Any) -> str:
    text = str(value or "").lower().replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    normalized = f" {_normalize(text)} "
    return any(f" {_normalize(term)} " in normalized for term in terms)


def is_internal_mode(environ: Dict[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return str(env.get(INTERNAL_MODE_ENV, "")).strip().lower() in {"1", "true", "yes", "on"}


def _call_scope_text(result: Dict[str, Any]) -> str:
    return " ".join(
        str(result.get(field) or "")
        for field in ("call_title", "topic_title", "description", "objectives", "expected_impact")
    )


def is_port_side_project(project_text: str) -> bool:
    return _contains_any(project_text, PORT_SIDE_PROJECT_TERMS)


def port_side_call_classification(result: Dict[str, Any]) -> str:
    scope_text = _call_scope_text(result)
    has_port_side_scope = _contains_any(scope_text, PORT_SIDE_CALL_TERMS)
    has_ship_side_scope = _contains_any(scope_text, SHIP_SIDE_CALL_TERMS)
    if has_port_side_scope:
        return "direct_port_side"
    if has_ship_side_scope:
        return "ship_side_adjacent"
    return "other"


def _primary_theme_for_copy(shared_themes: Iterable[str]) -> str | None:
    shared_set = set(shared_themes)
    for theme in THEME_COPY_PRIORITY:
        if theme in shared_set:
            return theme
    return next(iter(shared_set), None)


def prioritize_client_results(
    results: List[Dict[str, Any]],
    project_text: str,
) -> List[Dict[str, Any]]:
    """Apply a narrow client-display priority without changing retrieval scores."""
    ordered = list(results)
    if not ordered or not is_port_side_project(project_text):
        return ordered

    # Promote explicit port-side evidence, but preserve the raw order of every
    # remaining result so adjacent calls do not fall behind weaker noise.
    priority = {
        "direct_port_side": 0,
        "other": 1,
        "ship_side_adjacent": 1,
    }
    original_positions = {id(result): index for index, result in enumerate(ordered)}
    return sorted(
        ordered,
        key=lambda result: (
            priority[port_side_call_classification(result)],
            original_positions[id(result)],
        ),
    )


def build_review_status_reason(
    result: Dict[str, Any],
    status: str,
    *,
    input_quality: Dict[str, Any] | None = None,
) -> str:
    coherence = result.get("theme_coherence") or {}
    guardrails = set(coherence.get("guardrails") or [])
    shared_themes = coherence.get("shared_themes") or []
    quality_level = str((input_quality or {}).get("quality_level") or "detailed")
    similarity = float(result.get("similarity_score") or 0.0)

    if "port_side_scope_mismatch" in guardrails:
        return "Useful maritime overlap is visible, but the call is ship-side rather than directly port-side."
    if "sme_support_scope_mismatch" in guardrails:
        return "The sector is relevant, but the call does not clearly provide SME or scale-up support."
    if "hydrogen_scope_drift" in guardrails:
        return "The clean-energy link is adjacent because hydrogen is not explicit in the call scope."
    if "passenger_transport_drift" in guardrails:
        return "The call focuses on passenger transport rather than freight logistics."
    if "no_meaningful_theme_overlap" in guardrails:
        return "Only broad or adjacent overlap is visible, so the result needs careful review."
    if "partial_theme_overlap" in guardrails:
        return "The call covers part of the project theme, but not the full project scope."
    if quality_level != "detailed":
        return "The project description needs more detail before the fit can be judged strongly."
    if status == "Strong match":
        if shared_themes:
            primary_theme = _primary_theme_for_copy(shared_themes)
            readable = THEME_LABELS.get(primary_theme, str(primary_theme or shared_themes[0]).replace("_", " "))
            return f"The call has a direct {readable} fit with enough detail to review first."
        return "The call is closely aligned with the project description and is worth reviewing first."
    if status == "Worth reviewing":
        if similarity >= 0.55:
            return "The fit score is useful, but one scope detail still needs confirmation before treating it as a strong match."
        if "partial_theme_overlap" in guardrails:
            primary_theme = _primary_theme_for_copy(shared_themes)
            if primary_theme == "security_resilience_infrastructure":
                return "The security theme is relevant, but the exact asset and threat scope needs confirmation."
            if primary_theme in {"maritime_ports_logistics", "transport_mobility_supply_chain"}:
                return "The transport theme is relevant, but the maritime logistics fit needs closer review."
            if primary_theme == "sme_startup_ecosystem":
                return "The innovation-support angle is relevant, but the SME pathway is not yet specific enough."
        return "The thematic connection is useful, but scope or screening details still need confirmation."
    return "The current evidence is not specific enough for a confident shortlist decision."


def _project_input_gaps(project_text: str, user_trl: int | None) -> List[str]:
    text = _normalize(project_text)
    checks = (
        (("problem", "challenge", "need", "bottleneck"), "Clarify the operational problem or unmet need."),
        (("solution", "platform", "process", "system", "technology", "tool"), "Describe the proposed solution more concretely."),
        (("user", "operator", "authority", "manufacturer", "company", "sme", "beneficiar"), "Name the main users or beneficiaries."),
        (("impact", "reduce", "increase", "improve", "resilience", "emission"), "State the expected operational or European impact."),
        (("europe", "european", " eu ", "cross border"), "Explain why the project matters at European level."),
    )
    gaps = [message for terms, message in checks if not _contains_any(text, terms)]
    if user_trl is None and not _contains_any(text, ("trl", "pilot", "demonstrat", "validat")):
        gaps.append("Add an estimated maturity or pilot stage if known.")
    return gaps


def build_call_strategy(
    result: Dict[str, Any],
    project_inputs: Dict[str, Any],
) -> Dict[str, List[str]]:
    coherence = result.get("theme_coherence") or {}
    shared_themes = coherence.get("shared_themes") or []
    strengths: List[str] = []
    clarifications: List[str] = []
    next_steps: List[str] = []

    primary_shared_theme = _primary_theme_for_copy(shared_themes)
    if primary_shared_theme:
        readable_theme = THEME_LABELS.get(primary_shared_theme, primary_shared_theme.replace("_", " "))
        strengths.append(f"Project and call share {readable_theme} signals.")

    alignment = (result.get("strategic_success_components") or {}).get("trl_alignment")
    if project_inputs.get("user_trl") is not None and alignment is not None and float(alignment) >= 100.0:
        strengths.append("The stated project maturity sits within the recorded call range.")

    explanation = str(result.get("match_explanation") or "").strip()
    if not strengths and explanation:
        strengths.append(explanation)

    guardrails = set(coherence.get("guardrails") or [])
    if "port_side_scope_mismatch" in guardrails:
        clarifications.append("Confirm whether ship-side technology is genuinely part of the port project scope.")
    elif "partial_theme_overlap" in guardrails:
        clarifications.append("Clarify which part of the call scope the project will address directly.")
    elif coherence.get("coherence_level") == "weak":
        clarifications.append("The call is adjacent rather than directly aligned; confirm the scope before shortlisting.")

    if not clarifications:
        if "critical_materials_circularity" in shared_themes:
            clarifications.append(
                "Clarify whether the project is mainly recovery, processing, substitution, or value-chain capacity."
            )
        elif "port_energy_hydrogen" in shared_themes or "maritime_ports_logistics" in shared_themes:
            clarifications.append(
                "Clarify whether the work is port-side infrastructure, ship-side technology, or operational planning."
            )
        elif "security_resilience_infrastructure" in shared_themes:
            clarifications.append(
                "Clarify which assets, threats, and operational users the security work will address."
            )
        elif "sme_startup_ecosystem" in shared_themes:
            clarifications.append(
                "Clarify whether the need is funding support, market access, piloting, or technical development."
            )

    data_flags = " ".join(str(item).lower() for item in result.get("data_quality_flags") or [])
    if len(clarifications) < 2 and ("country" in data_flags or "organisation" in data_flags):
        clarifications.append("Confirm applicant country and organisation type in the official eligibility conditions.")

    if len(clarifications) < 2 and result.get("consortium_required") in [None, ""]:
        clarifications.append("Consortium requirements are not confirmed in the available call details.")
    elif (
        len(clarifications) < 2
        and result.get("consortium_required") in [1, "1", True]
        and not project_inputs.get("has_consortium")
    ):
        clarifications.append("A consortium appears relevant, but the current project setup does not yet include one.")

    if len(clarifications) < 2:
        for gap in _project_input_gaps(
            str(project_inputs.get("project_desc") or ""),
            project_inputs.get("user_trl"),
        ):
            if gap not in clarifications:
                clarifications.append(gap)
            if len(clarifications) >= 2:
                break

    if "port_side_scope_mismatch" in guardrails:
        next_steps.append("Confirm whether ship-side technology is genuinely part of the port project scope.")
    next_steps.append("Check applicant eligibility and participation conditions in the official call documents.")
    next_steps.append("Map the project objectives and impact to the call's expected outcomes.")

    if result.get("consortium_required") in [1, "1", True]:
        next_steps.append("Confirm the required consortium structure and identify missing partner roles.")
    elif result.get("consortium_required") in [None, ""]:
        next_steps.append("Confirm whether a consortium is required before planning partner outreach.")

    next_steps.append("Prepare a one-page project summary for an internal go/no-go review.")
    next_steps.append("Review the listed deadline, budget, and funding conditions on the official source.")

    return {
        "strengths": strengths[:2],
        "clarifications": clarifications[:2],
        "next_steps": next_steps[:4],
    }
