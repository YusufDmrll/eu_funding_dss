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

CRITICAL_CIRCULARITY_TERMS = (
    "critical raw material",
    "critical raw materials",
    "strategic raw material",
    "raw materials",
    "rare earth",
    "battery materials",
    "battery-grade",
    "battery grade",
    "recycling",
    "direct recycling",
    "secondary raw material",
    "secondary raw materials",
    "circularity",
    "circular economy",
    "materials recovery",
    "material recovery",
    "recovery",
    "refining",
    "processing",
    "substitution",
    "dependency",
    "dependencies",
)

GREEN_ENERGY_TERMS = (
    "renewable",
    "renewable energy",
    "clean energy",
    "energy efficiency",
    "energy management",
    "energy transition",
    "clean industrial",
    "industrial decarbon",
    "decarbonisation",
    "decarbonization",
    "emissions reduction",
    "electricity",
    "electrification",
    "storage",
    "grid",
    "sustainability",
    "climate action",
)

SECURITY_TERMS = (
    "security",
    "cybersecurity",
    "critical infrastructure",
    "critical infrastructures",
    "physical protection",
    "infrastructure protection",
    "threat",
    "threats",
    "risk assessment",
    "risk detection",
    "emergency preparedness",
    "crisis response",
    "resilience",
    "stress tests",
    "stress test",
    "hybrid scenarios",
    "critical entities",
)

MARITIME_TERMS = (
    "maritime",
    "shipping",
    "ship",
    "ships",
    "vessel",
    "vessels",
    "waterborne",
    "port",
    "ports",
    "harbour",
    "harbours",
    "terminal",
    "terminals",
    "freight",
    "logistics",
    "short sea",
    "inland waterways",
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


def _project_scope_text(project_inputs: Dict[str, Any] | None) -> str:
    if not project_inputs:
        return ""
    return " ".join(
        str(project_inputs.get(field) or "")
        for field in ("project_desc", "project_title", "user_country", "user_org_type")
    )


def _supports_terms(text: str, terms: Iterable[str]) -> bool:
    return _contains_any(text, terms)


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


def _supported_project_call_theme(
    result: Dict[str, Any],
    project_inputs: Dict[str, Any] | None,
) -> str | None:
    """Choose a wording theme only when the call and project both support it."""
    call_text = _call_scope_text(result)
    project_text = _project_scope_text(project_inputs)
    shared_themes = set((result.get("theme_coherence") or {}).get("shared_themes") or [])

    project_has_green = _supports_terms(project_text, GREEN_ENERGY_TERMS)
    call_has_green = _supports_terms(call_text, GREEN_ENERGY_TERMS)
    project_has_security = _supports_terms(project_text, SECURITY_TERMS)
    call_has_security = _supports_terms(call_text, SECURITY_TERMS)
    project_has_maritime = _supports_terms(project_text, MARITIME_TERMS)
    call_has_maritime = _supports_terms(call_text, MARITIME_TERMS)
    project_has_critical = _supports_terms(project_text, CRITICAL_CIRCULARITY_TERMS)
    call_has_critical = _supports_terms(call_text, CRITICAL_CIRCULARITY_TERMS)

    if (project_has_security and call_has_security) or "security_resilience_infrastructure" in shared_themes:
        return "security"
    if (
        project_has_maritime
        and call_has_maritime
        and (
            is_port_side_project(project_text)
            or port_side_call_classification(result) == "direct_port_side"
        )
    ):
        return "maritime"
    if (project_has_green and call_has_green) or "port_energy_hydrogen" in shared_themes:
        return "green_energy"
    if (project_has_maritime and call_has_maritime) or "maritime_ports_logistics" in shared_themes:
        return "maritime"
    if (project_has_critical and call_has_critical) or "critical_materials_circularity" in shared_themes:
        return "critical_materials"
    return None


def build_theme_aware_next_action(
    result: Dict[str, Any],
    project_inputs: Dict[str, Any] | None,
) -> str | None:
    guardrails = set((result.get("theme_coherence") or {}).get("guardrails") or [])
    call_text = _call_scope_text(result)
    theme = _supported_project_call_theme(result, project_inputs)

    if "port_side_scope_mismatch" in guardrails:
        return "Confirm whether ship-side technology is genuinely part of the port project scope before shortlisting."
    if "passenger_transport_drift" in guardrails:
        return "Validate whether the call addresses freight, logistics, or port operations rather than passenger transport."
    if "hydrogen_scope_drift" in guardrails:
        return "Confirm that hydrogen infrastructure is explicit in the official call text before treating this as a direct energy match."
    if "no_meaningful_theme_overlap" in guardrails or "partial_theme_overlap" in guardrails:
        return "Validate the project-call scope against the official text before treating this as more than a reviewable lead."

    if theme == "security":
        return "Check whether the call focuses on infrastructure protection, cyber-physical security, emergency preparedness, or operational resilience."
    if theme == "green_energy":
        return "Check whether the call expects energy-efficiency gains, renewable integration, storage/grid readiness, or industrial decarbonisation outcomes."
    if theme == "maritime":
        if _supports_terms(call_text, PORT_SIDE_CALL_TERMS):
            return "Check whether the call is centred on port operations, harbour infrastructure, or wider maritime network coordination."
        return "Check whether the call addresses maritime logistics, green shipping, operational efficiency, or consortium needs."
    if theme == "critical_materials":
        if _supports_terms(call_text, ("battery", "battery materials", "battery-grade", "battery grade")):
            return "Check whether the call prioritises recovered battery-grade materials, recycling performance, or wider battery value-chain capacity."
        return "Confirm whether the call is centred on recycling, recovery, substitution, processing, or raw-material value-chain capacity."

    return None


def build_theme_aware_caution(
    result: Dict[str, Any],
    project_inputs: Dict[str, Any] | None = None,
) -> str | None:
    guardrails = set((result.get("theme_coherence") or {}).get("guardrails") or [])
    call_text = _call_scope_text(result)
    theme = _supported_project_call_theme(result, project_inputs)

    if "port_side_scope_mismatch" in guardrails:
        return "Check whether the ship-side scope is relevant enough for this port-side project."
    if "passenger_transport_drift" in guardrails:
        return "Check whether the call is passenger-transport focused rather than freight, logistics, or port operations."
    if "hydrogen_scope_drift" in guardrails:
        return "Check whether the clean-energy scope is truly hydrogen-related rather than an adjacent CCUS, nuclear, or shipping topic."
    if "no_meaningful_theme_overlap" in guardrails:
        return "Only adjacent overlap is visible, so validate scope carefully before shortlisting."

    if theme == "security":
        return "Check whether the call matches the specific assets, threat model, and public-private response context of the project."
    if theme == "green_energy":
        return "Check whether the call expects measurable energy, emissions, storage, or industrial-decarbonisation outcomes."
    if theme == "maritime":
        if _supports_terms(call_text, SHIP_SIDE_CALL_TERMS) and _supports_terms(_project_scope_text(project_inputs), PORT_SIDE_PROJECT_TERMS):
            return "Check whether the ship-side scope is relevant enough for this port-side project."
        if port_side_call_classification(result) == "direct_port_side":
            return "Check whether the call is focused on harbour infrastructure, terminal systems, or wider port-network coordination."
        return "Check whether the call is focused on maritime operations, harbour infrastructure, or logistics rather than an adjacent transport topic."
    if theme == "critical_materials":
        if _supports_terms(call_text, ("direct recycling",)):
            return "Check whether the call expects direct-recycling performance and recovered material quality rather than broader circularity aims."
        if _supports_terms(call_text, ("battery", "battery materials", "battery-grade", "battery grade")) and _supports_terms(
            call_text, ("recycling", "direct recycling", "recovery")
        ):
            return "Check whether the call is focused on recovered battery-grade materials rather than broader battery value-chain activity."
        if _supports_terms(call_text, ("substitution", "dependency", "dependencies")):
            return "Check whether the call is framed around dependency reduction or substitution rather than recovery activity."
        if _supports_terms(call_text, ("secondary raw materials", "recycling", "recovery")):
            return "Check whether the call expects recovery scale and processing depth rather than a broader circular-economy framing."
        return "Check whether the call is aimed at materials processing, recovery, substitution, or value-chain capacity."

    return None


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

    theme_next_action = build_theme_aware_next_action(result, project_inputs)
    if theme_next_action:
        next_steps.append(theme_next_action)
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
