import re
from typing import Any, Dict, Iterable


THEME_TERMS = {
    "critical_materials_circularity": (
        "critical raw material",
        "strategic raw material",
        "rare earth",
        "battery material",
        "battery materials",
        "batteries",
        "battery recycling",
        "recycling",
        "secondary raw material",
        "circularity",
        "circular economy",
        "materials recovery",
        "material recovery",
        "refining",
    ),
    "port_energy_hydrogen": (
        "shore power",
        "port energy",
        "harbour energy",
        "green hydrogen",
        "hydrogen",
        "renewable fuel",
        "renewable energy",
        "energy transition",
        "electrification",
        "battery storage",
    ),
    "maritime_ports_logistics": (
        "maritime",
        "port",
        "ports",
        "harbour",
        "shipping",
        "ship",
        "ships",
        "vessel",
        "waterborne",
        "cargo",
        "freight terminal",
        "maritime logistics",
    ),
    "security_resilience_infrastructure": (
        "security",
        "cybersecurity",
        "critical infrastructure",
        "infrastructure protection",
        "threat detection",
        "anomaly detection",
        "disaster resilience",
        "crisis response",
        "operational resilience",
    ),
    "sme_startup_ecosystem": (
        "sme",
        "smes",
        "startup",
        "start-up",
        "scale-up",
        "scaleup",
        "innovation ecosystem",
        "investment readiness",
        "market entry",
        "pilot customer",
        "commercial deployment",
    ),
    "digital_ai_automation": (
        "artificial intelligence",
        "machine learning",
        "digital infrastructure",
        "data infrastructure",
        "data space",
        "digital twin",
        "automation",
        "robotics",
        "predictive analytics",
        " ai ",
    ),
    "transport_mobility_supply_chain": (
        "transport",
        "mobility",
        "supply chain",
        "logistics",
        "freight",
        "multimodal",
        "cargo flow",
        "passenger transport",
        "urban mobility",
    ),
}

UNDER_SPECIFIED_PATTERNS = (
    r"\bnot yet defined\b",
    r"\bremain(?:s)? open\b",
    r"\bstill need(?:s)? to be defined\b",
    r"\bconcept (?:is|remains) broad\b",
    r"\bmay include\b",
    r"\bsector focus.{0,30}(?:open|undefined|not defined)\b",
    r"\bpilot sector.{0,30}(?:open|undefined|not defined)\b",
)

SME_SUPPORT_TERMS = (
    "support programme",
    "support program",
    "investment readiness",
    "market entry",
    "pilot customer",
    "accelerator",
    "business support",
    "innovation ecosystem",
    "commercialisation support",
    "commercialization support",
)

FREIGHT_PROJECT_TERMS = ("freight", "cargo", "logistics", "supply chain", "terminal")
PASSENGER_ONLY_TERMS = ("passenger transport", "passenger mobility", "passenger hub", "public transport")
HYDROGEN_DRIFT_TERMS = ("ccus", "carbon capture", "nuclear power", "nuclear shipping")
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
    "port operation",
    "ports",
    "terminal operator",
    "terminal infrastructure",
)
SHIP_SIDE_CALL_TERMS = (
    "onboard",
    "ship propulsion",
    "propulsion system",
    "vessel propulsion",
    "fuel consumption of ships",
    "battery-electric operation of ferries",
)
DOMAIN_CONTEXT_TERMS = (
    "industrial",
    "manufacturing",
    "factory",
    "port",
    "maritime",
    "logistics",
    "transport",
    "energy",
    "security",
    "materials",
    "recycling",
    "hydrogen",
)

STATUS_ORDER = {"Needs more detail": 0, "Worth reviewing": 1, "Strong match": 2}


def _normalize(value: Any) -> str:
    text = str(value or "").lower().replace("-", " ")
    cleaned = re.sub(r"\s+", " ", text).strip()
    return f" {cleaned} "


def _contains(text: str, term: str) -> bool:
    normalized_term = _normalize(term).strip()
    if not normalized_term:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", text) is not None


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(_contains(text, term) for term in terms)


def build_call_theme_text(call_record: Dict[str, Any], *, primary_only: bool = False) -> str:
    fields = ("call_title", "topic_title", "keywords", "objectives") if primary_only else (
        "call_title",
        "topic_title",
        "keywords",
        "objectives",
        "description",
        "expected_impact",
    )
    return _normalize(" ".join(str(call_record.get(field) or "") for field in fields))


def build_call_identity_text(call_record: Dict[str, Any]) -> str:
    return _normalize(
        " ".join(
            str(call_record.get(field) or "")
            for field in ("call_title", "topic_title", "keywords")
        )
    )


def build_call_scope_text(call_record: Dict[str, Any]) -> str:
    return _normalize(
        " ".join(
            str(call_record.get(field) or "")
            for field in ("call_title", "topic_title", "description", "objectives", "expected_impact")
        )
    )


def detect_theme_signals(text: Any) -> Dict[str, list[str]]:
    normalized = _normalize(text)
    signals: Dict[str, list[str]] = {}
    for theme, terms in THEME_TERMS.items():
        matches = [term.strip() for term in terms if _contains(normalized, term)]
        if matches:
            signals[theme] = matches
    return signals


def cap_status(status: str, maximum_status: str | None) -> str:
    if not maximum_status:
        return status
    if STATUS_ORDER.get(status, 0) > STATUS_ORDER.get(maximum_status, 0):
        return maximum_status
    return status


def assess_theme_coherence(project_text: str, call_record: Dict[str, Any]) -> Dict[str, Any]:
    project_normalized = _normalize(project_text)
    call_text = build_call_theme_text(call_record)
    call_primary_text = build_call_theme_text(call_record, primary_only=True)
    call_identity_text = build_call_identity_text(call_record)
    call_scope_text = build_call_scope_text(call_record)
    project_signals = detect_theme_signals(project_text)
    call_signals = detect_theme_signals(call_text)
    project_themes = set(project_signals)
    call_themes = set(call_signals)
    shared_themes = sorted(project_themes & call_themes)
    guardrails: list[str] = []
    max_status: str | None = None

    under_specified = any(re.search(pattern, project_normalized) for pattern in UNDER_SPECIFIED_PATTERNS)
    if under_specified:
        guardrails.append("under_specified_input")
        max_status = "Worth reviewing"

    if not project_themes:
        guardrails.append("no_clear_project_theme")
        max_status = "Needs more detail"
    elif not shared_themes:
        guardrails.append("no_meaningful_theme_overlap")
        max_status = "Needs more detail"

    if project_themes == {"digital_ai_automation"}:
        guardrails.append("generic_digital_only")
        digital_cap = "Worth reviewing" if _contains_any(project_normalized, DOMAIN_CONTEXT_TERMS) else "Needs more detail"
        max_status = cap_status(max_status or "Strong match", digital_cap)

    is_sme_support_project = _contains_any(project_normalized, SME_SUPPORT_TERMS)
    call_has_sme_support_scope = _contains_any(call_primary_text, SME_SUPPORT_TERMS)
    if is_sme_support_project and not call_has_sme_support_scope:
        guardrails.append("sme_support_scope_mismatch")
        max_status = "Needs more detail"

    is_freight_project = _contains_any(project_normalized, FREIGHT_PROJECT_TERMS)
    passenger_only_call = _contains_any(call_primary_text, PASSENGER_ONLY_TERMS) and not _contains_any(
        call_primary_text,
        ("freight", "cargo", "maritime", "port", "shipping", "supply chain"),
    )
    if is_freight_project and passenger_only_call:
        guardrails.append("passenger_transport_drift")
        max_status = "Needs more detail"

    is_hydrogen_project = _contains(project_normalized, "hydrogen")
    call_has_explicit_hydrogen = _contains(call_identity_text, "hydrogen")
    hydrogen_drift = _contains_any(call_primary_text, HYDROGEN_DRIFT_TERMS)
    if is_hydrogen_project and hydrogen_drift and not call_has_explicit_hydrogen:
        guardrails.append("hydrogen_scope_drift")
        max_status = "Needs more detail"

    is_port_side_project = _contains_any(project_normalized, PORT_SIDE_PROJECT_TERMS)
    call_has_direct_port_scope = _contains_any(call_scope_text, PORT_SIDE_CALL_TERMS)
    call_has_ship_side_scope = _contains_any(call_scope_text, SHIP_SIDE_CALL_TERMS)
    if is_port_side_project and call_has_ship_side_scope and not call_has_direct_port_scope:
        guardrails.append("port_side_scope_mismatch")
        max_status = cap_status(max_status or "Strong match", "Worth reviewing")

    if shared_themes and len(project_themes) > 1 and len(shared_themes) == 1:
        guardrails.append("partial_theme_overlap")
        max_status = cap_status(max_status or "Strong match", "Worth reviewing")

    if "no_meaningful_theme_overlap" in guardrails or "no_clear_project_theme" in guardrails:
        coherence_level = "weak"
    elif any(
        item in guardrails
        for item in (
            "sme_support_scope_mismatch",
            "passenger_transport_drift",
            "hydrogen_scope_drift",
            "port_side_scope_mismatch",
        )
    ):
        coherence_level = "weak"
    elif guardrails:
        coherence_level = "partial"
    else:
        coherence_level = "strong"

    return {
        "project_themes": sorted(project_themes),
        "call_themes": sorted(call_themes),
        "shared_themes": shared_themes,
        "project_theme_signals": project_signals,
        "call_theme_signals": call_signals,
        "coherence_level": coherence_level,
        "guardrails": guardrails,
        "max_client_status": max_status,
        "call_has_port_context": _contains_any(call_text, ("port", "ports", "harbour", "shore power", "berth", "terminal")),
        "call_has_direct_port_scope": call_has_direct_port_scope,
        "call_has_ship_side_scope": call_has_ship_side_scope,
        "call_has_hydrogen_context": call_has_explicit_hydrogen,
    }


def build_coherence_explanation(theme_coherence: Dict[str, Any] | None) -> str | None:
    coherence = theme_coherence or {}
    guardrails = set(coherence.get("guardrails") or [])
    if "sme_support_scope_mismatch" in guardrails:
        return "This call is adjacent to the project sector, but it does not clearly provide the SME or scale-up support described in the project idea."
    if "passenger_transport_drift" in guardrails:
        return "This call is transport-related, but its passenger focus does not clearly match the project's freight and maritime logistics scope."
    if "hydrogen_scope_drift" in guardrails:
        return "This call is adjacent to the clean-energy theme, but explicit hydrogen relevance is not clear and should be reviewed carefully."
    if "port_side_scope_mismatch" in guardrails:
        return "This call is relevant to maritime decarbonisation, but its scope is ship-side rather than directly focused on port or harbour infrastructure."
    if "no_meaningful_theme_overlap" in guardrails:
        return "The call has only broad or adjacent overlap with the project and should be reviewed carefully before shortlisting."
    if "no_clear_project_theme" in guardrails:
        return "The project description does not yet provide enough domain detail for a project-specific match explanation."
    if "generic_digital_only" in guardrails:
        return "The call has broad digital or AI overlap, but the project needs clearer sector, user, and impact detail before this can be treated as a specific fit."
    if "under_specified_input" in guardrails:
        return "The call is a plausible thematic starting point, but the project scope needs more detail before the fit can be assessed confidently."
    if "partial_theme_overlap" in guardrails:
        shared_themes = set(coherence.get("shared_themes") or [])
        if "security_resilience_infrastructure" in shared_themes:
            return "This call is security-related, but confirm whether it covers the specific infrastructure assets, threats, and users in the project."
        if "maritime_ports_logistics" in shared_themes or "transport_mobility_supply_chain" in shared_themes:
            return "This call is transport-related, but confirm whether it covers the project's maritime logistics workflow directly."
        if "sme_startup_ecosystem" in shared_themes:
            return "This call touches innovation support, but confirm whether it provides the SME or scale-up pathway described in the project."
        if "critical_materials_circularity" in shared_themes:
            return "This call is circularity-related, but confirm whether it covers the project's specific material stream and value-chain step."
        return "The call aligns with part of the project theme, but the full scope is not clearly covered and needs closer review."
    return None
