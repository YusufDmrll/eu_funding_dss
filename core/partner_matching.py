from typing import Any, Dict, List

from core.partner_directory import build_partner_directory_suggestions


def _combined_text(result: Dict[str, Any], project_inputs: Dict[str, Any] | None = None) -> str:
    project_inputs = project_inputs or {}
    fields = (
        result.get("call_title"),
        result.get("topic_title"),
        result.get("description"),
        result.get("objectives"),
        result.get("expected_impact"),
        result.get("keywords"),
        project_inputs.get("project_desc"),
        project_inputs.get("project_title"),
    )
    return " ".join(str(value or "").lower() for value in fields)


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _unique(items: List[str]) -> List[str]:
    selected: List[str] = []
    for item in items:
        if item not in selected:
            selected.append(item)
    return selected


def _role(label: str, reason: str, priority: str = "recommended") -> Dict[str, str]:
    return {"label": label, "reason": reason, "priority": priority}


def infer_partner_role_cards(
    result: Dict[str, Any],
    project_inputs: Dict[str, Any] | None = None,
) -> List[Dict[str, str]]:
    text = _combined_text(result, project_inputs)
    roles: List[Dict[str, str]] = []

    if _has_any(text, ("shore power", "berth", "harbour", "port", "ports", "terminal")):
        roles.extend(
            [
                _role(
                    "Port authority or terminal operator",
                    "Needed to confirm operational fit, site access, and port-side deployment conditions.",
                    "core",
                ),
                _role(
                    "Grid, energy, or shore-power infrastructure partner",
                    "Useful for checking power capacity, integration constraints, and investment readiness.",
                    "core",
                ),
            ]
        )
    if _has_any(text, ("maritime", "shipping", "vessel", "waterborne", "freight", "logistics")):
        roles.extend(
            [
                _role(
                    "Shipping, logistics, or port-community operator",
                    "Useful for validating real operational flows, data availability, and adoption barriers.",
                    "core",
                ),
                _role(
                    "Operational pilot site",
                    "Strengthens the case if the call expects demonstration in a realistic environment.",
                ),
            ]
        )
    if _has_any(text, ("hydrogen", "renewable", "clean energy", "energy efficiency", "grid", "storage", "decarbon")):
        roles.extend(
            [
                _role(
                    "Energy technology or infrastructure provider",
                    "Needed to ground the technical pathway, integration plan, and measurable energy performance.",
                    "core",
                ),
                _role(
                    "Industrial end user or demonstration site",
                    "Helps prove demand, operational relevance, and decarbonisation impact.",
                ),
            ]
        )
    if _has_any(text, ("critical raw material", "raw materials", "rare earth", "battery", "recycling", "circular")):
        roles.extend(
            [
                _role(
                    "Recycling or materials processor",
                    "Needed to validate feedstock, process feasibility, and recovery or upgrading performance.",
                    "core",
                ),
                _role(
                    "Battery, manufacturing, or industrial value-chain partner",
                    "Helps connect the project to European demand, supply-chain resilience, and uptake.",
                    "core",
                ),
            ]
        )
    if _has_any(text, ("security", "cybersecurity", "critical infrastructure", "threat", "risk assessment", "emergency")):
        roles.extend(
            [
                _role(
                    "Critical-infrastructure operator",
                    "Needed to define the protected asset, operational risk scenario, and validation environment.",
                    "core",
                ),
                _role(
                    "Security, cybersecurity, or resilience specialist",
                    "Supports threat modelling, risk assessment, and credible validation methodology.",
                    "core",
                ),
                _role(
                    "Public authority or emergency-response stakeholder",
                    "Useful when the call involves preparedness, response coordination, or public-sector uptake.",
                ),
            ]
        )
    if _has_any(text, ("artificial intelligence", " ai ", "automation", "data space", "digital twin", "cloud", "robotics")):
        roles.extend(
            [
                _role(
                    "Data, AI, or systems-integration partner",
                    "Useful for implementation credibility where the call depends on digital capability.",
                ),
                _role(
                    "Operational data owner",
                    "Needed to confirm access to realistic data and evaluation conditions.",
                ),
            ]
        )
    if _has_any(text, ("sme", "startup", "start-up", "scale-up", "market uptake", "commercialisation")):
        roles.extend(
            [
                _role(
                    "SME or scale-up participant",
                    "Helps position the project around market uptake and company-led innovation.",
                ),
                _role(
                    "Market validation or first-customer partner",
                    "Useful for proving demand, adoption route, and commercial relevance.",
                ),
            ]
        )
    if _has_any(text, ("research", "ria", "innovation action", "ia", "demonstrat", "pilot", "validation")):
        roles.append(
            _role(
                "Research, testing, or validation partner",
                "Useful for methodology, evaluation design, and independent technical evidence.",
            )
        )

    unique_by_label: Dict[str, Dict[str, str]] = {}
    for role in roles:
        existing = unique_by_label.get(role["label"])
        if existing is None or (existing.get("priority") != "core" and role.get("priority") == "core"):
            unique_by_label[role["label"]] = role
    unique_roles = list(unique_by_label.values())
    ordered = [
        role for role in unique_roles if role.get("priority") == "core"
    ] + [
        role for role in unique_roles if role.get("priority") != "core"
    ]
    return ordered[:6]


def infer_partner_types(
    result: Dict[str, Any],
    project_inputs: Dict[str, Any] | None = None,
) -> List[str]:
    return _unique([role["label"] for role in infer_partner_role_cards(result, project_inputs)])[:4]


def _outreach_focus(role_cards: List[Dict[str, str]]) -> str:
    core_roles = [role["label"] for role in role_cards if role.get("priority") == "core"]
    selected = core_roles or [role["label"] for role in role_cards[:2]]
    if not selected:
        return "Start by confirming whether the official call expects named partners or only a single applicant."
    return "Start outreach with " + " and ".join(selected[:2]) + "."


def _partner_validation_focus(text: str) -> str:
    if _has_any(text, ("shore power", "berth", "harbour", "port", "ports", "terminal")):
        return "site access, operational constraints, power capacity, and deployment readiness"
    if _has_any(text, ("critical raw material", "raw materials", "rare earth", "battery", "recycling", "circular")):
        return "feedstock access, process feasibility, material quality, and industrial uptake"
    if _has_any(text, ("security", "cybersecurity", "critical infrastructure", "threat", "risk assessment", "emergency")):
        return "protected assets, threat scenarios, validation users, and response procedures"
    if _has_any(text, ("maritime", "shipping", "vessel", "waterborne", "freight", "logistics")):
        return "operational flows, data availability, pilot setting, and adoption barriers"
    if _has_any(text, ("hydrogen", "renewable", "clean energy", "energy efficiency", "grid", "storage", "decarbon")):
        return "energy baseline, integration constraints, user demand, and measurable decarbonisation impact"
    if _has_any(text, ("sme", "startup", "start-up", "scale-up", "market uptake", "commercialisation")):
        return "customer demand, market access, scale-up route, and company-led innovation need"
    if _has_any(text, ("artificial intelligence", " ai ", "automation", "data space", "digital twin", "cloud", "robotics")):
        return "data access, systems integration, operational validation, and implementation feasibility"
    return "call-scope fit, validation needs, and practical implementation conditions"


def _outreach_rationale(role_cards: List[Dict[str, str]], validation_focus: str) -> str:
    if not role_cards:
        return "Use the official call text to decide whether external validation or implementation partners are needed."
    selected = [role["label"] for role in role_cards[:2]]
    return (
        "These roles should be checked first because they can confirm "
        + validation_focus
        + "."
        + (" Priority roles: " + " and ".join(selected) + "." if selected else "")
    )


def build_partner_guidance(
    result: Dict[str, Any],
    project_inputs: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    text = _combined_text(result, project_inputs)
    role_cards = infer_partner_role_cards(result, project_inputs)
    partner_types = _unique([role["label"] for role in role_cards])[:4]
    primary_roles = role_cards[:2]
    supporting_roles = role_cards[2:4]
    validation_focus = _partner_validation_focus(text)
    consortium_required = result.get("consortium_required") in [1, "1", True]
    consortium_unknown = result.get("consortium_required") in [None, ""]
    has_consortium = bool((project_inputs or {}).get("has_consortium"))

    if consortium_required and not has_consortium:
        summary = "A consortium appears important; identify the minimum required roles before proposal planning."
        priority = "high"
    elif consortium_required:
        summary = "Consortium participation appears relevant; confirm role coverage and minimum partner rules."
        priority = "medium"
    elif consortium_unknown and partner_types:
        summary = (
            "Partner requirements are not confirmed in the available call details; "
            "use the roles below to verify " + validation_focus + "."
        )
        priority = "review"
    elif partner_types:
        summary = "A focused partner setup could make the project easier to validate, position, and evidence."
        priority = "review"
    else:
        summary = "No specific partner pattern is visible from the available call text."
        priority = "low"
    directory_suggestions = build_partner_directory_suggestions(
        result=result,
        project_inputs=project_inputs,
        partner_roles=role_cards,
    )

    return {
        "summary": summary,
        "priority": priority,
        "partner_types": partner_types,
        "partner_roles": role_cards,
        "primary_roles": primary_roles,
        "supporting_roles": supporting_roles,
        "validation_focus": validation_focus,
        "outreach_focus": _outreach_focus(role_cards),
        "outreach_rationale": _outreach_rationale(primary_roles, validation_focus),
        "directory_suggestions": directory_suggestions,
        "evidence_to_confirm": [
            "Whether the call formally requires a consortium or only benefits from partner involvement.",
            "Which partner roles are necessary for " + validation_focus + ".",
            "Whether any partner must be from a specific country, sector, or organisation type.",
        ],
        "caution": "Confirm consortium and partner requirements in the official call documents before outreach.",
    }
