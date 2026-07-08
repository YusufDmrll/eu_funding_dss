from typing import Any, Dict, List

from core.partner_matching import build_partner_guidance


def _project_text(project_inputs: Dict[str, Any] | None) -> str:
    if not project_inputs:
        return ""
    return " ".join(
        str(project_inputs.get(field) or "")
        for field in ("project_title", "project_desc")
    ).strip()


def _call_title(result: Dict[str, Any]) -> str:
    return str(result.get("topic_title") or result.get("call_title") or result.get("title") or "this call").strip()


def _missing_project_inputs(project_inputs: Dict[str, Any] | None) -> List[str]:
    text = _project_text(project_inputs).lower()
    missing: List[str] = []
    if not any(term in text for term in ("problem", "challenge", "barrier", "need", "risk")):
        missing.append("problem or operational challenge")
    if not any(term in text for term in ("solution", "develop", "deploy", "demonstrate", "platform", "process", "tool")):
        missing.append("proposed solution or technology")
    if not any(term in text for term in ("user", "customer", "operator", "authority", "manufacturer", "sme", "industry")):
        missing.append("target users or beneficiaries")
    if not any(term in text for term in ("impact", "reduce", "increase", "improve", "emissions", "resilience", "dependency")):
        missing.append("expected impact")
    if not any(term in text for term in ("trl", "pilot", "prototype", "validation", "demonstration", "ready")):
        missing.append("current maturity or validation stage")
    return missing[:4]


def _theme_angle(result: Dict[str, Any]) -> str:
    text = " ".join(
        str(result.get(field) or "").lower()
        for field in ("call_title", "topic_title", "description", "objectives", "expected_impact", "keywords")
    )
    if any(term in text for term in ("critical raw material", "raw materials", "battery", "recycling", "circular")):
        return "Frame the concept around materials resilience, circular value chains, and measurable recovery or processing outcomes."
    if any(term in text for term in ("shore power", "port", "harbour", "maritime", "shipping", "logistics")):
        return "Frame the concept around operational deployment, emissions reduction, and clear roles for port or maritime actors."
    if any(term in text for term in ("hydrogen", "renewable", "clean energy", "energy efficiency", "storage", "grid", "decarbon")):
        return "Frame the concept around clean-energy performance, emissions reduction, and practical integration in industrial or infrastructure settings."
    if any(term in text for term in ("security", "critical infrastructure", "cybersecurity", "threat", "emergency")):
        return "Frame the concept around protected assets, threat scenarios, operational users, and resilience outcomes."
    return "Frame the concept around the call's expected outcomes and make the project contribution specific."


def _theme_profile(result: Dict[str, Any]) -> str:
    text = " ".join(
        str(result.get(field) or "").lower()
        for field in ("call_title", "topic_title", "description", "objectives", "expected_impact", "keywords")
    )
    if any(term in text for term in ("critical raw material", "raw materials", "rare earth", "battery", "recycling", "circular")):
        return "critical_materials"
    if any(term in text for term in ("shore power", "port", "harbour")):
        return "port_energy"
    if any(term in text for term in ("maritime", "shipping", "waterborne", "logistics", "freight")):
        return "maritime_logistics"
    if any(term in text for term in ("hydrogen", "renewable", "clean energy", "energy efficiency", "storage", "grid", "decarbon")):
        return "green_energy"
    if any(term in text for term in ("security", "critical infrastructure", "cybersecurity", "threat", "emergency")):
        return "security"
    if any(term in text for term in ("sme", "startup", "start-up", "scale-up", "market uptake", "commercialisation")):
        return "sme_innovation"
    return "general"


def _theme_evidence_items(profile: str) -> List[str]:
    evidence = {
        "critical_materials": [
            "Feedstock source, material stream, and current dependency or supply-chain problem",
            "Expected recovery, recycling, substitution, or processing performance",
            "Industrial user or value-chain partner that can validate uptake",
        ],
        "port_energy": [
            "Port-side user need, berth/vessel demand, and infrastructure baseline",
            "Energy integration plan covering shore power, grid capacity, renewables, or storage",
            "Expected emissions, congestion, cost, or resilience improvement at port level",
        ],
        "maritime_logistics": [
            "Operational logistics problem, data availability, and actors affected",
            "Pilot route, terminal, shipping, or freight environment for validation",
            "Expected improvement in waiting time, fuel use, reliability, or multimodal coordination",
        ],
        "green_energy": [
            "Energy baseline and measurable decarbonisation or efficiency target",
            "Technology integration plan for renewables, storage, grid, hydrogen, or industrial use",
            "Demonstration site and user demand evidence",
        ],
        "security": [
            "Protected asset, threat scenario, and operational risk being addressed",
            "Validation plan with infrastructure, emergency, cybersecurity, or public-sector users",
            "Expected resilience, preparedness, detection, response, or continuity improvement",
        ],
        "sme_innovation": [
            "Company role, market need, and route to adoption",
            "Evidence of customer demand, market validation, or scale-up potential",
            "Why EU funding is needed for the next innovation step",
        ],
        "general": [
            "Specific problem, user group, and expected project outcome",
            "Evidence that the project fits the official topic scope",
            "Practical validation plan and measurable impact",
        ],
    }
    return evidence.get(profile, evidence["general"])


def _proposal_outline(profile: str, partner_guidance: Dict[str, Any]) -> List[str]:
    shared = [
        "Problem and EU relevance: define the operational challenge and why it matters at European level.",
        "Solution and innovation: describe what is new, what will be built, and how it fits the call scope.",
        "Validation plan: explain where, with whom, and how the project will prove the result.",
        "Impact and adoption: state the measurable benefit and the route toward use after the project.",
    ]
    profile_sections = {
        "critical_materials": "Value-chain case: show feedstock, processing step, material output, and dependency-reduction logic.",
        "port_energy": "Deployment setting: show the port-side infrastructure, operational users, and energy-system integration.",
        "maritime_logistics": "Operational workflow: show the logistics process, data flows, and measurable transport improvement.",
        "green_energy": "Energy case: show the baseline, decarbonisation pathway, integration constraints, and demonstration site.",
        "security": "Risk scenario: show the protected asset, threat model, user roles, and resilience validation method.",
        "sme_innovation": "Market case: show customer need, company capability, uptake route, and scale-up milestone.",
    }
    outline = [profile_sections.get(profile, "Call-scope fit: show how the concept maps to the official expected outcomes.")] + shared
    if partner_guidance.get("partner_types"):
        outline.append("Consortium logic: connect each key partner role to a work package or validation need.")
    return outline[:5]


def _preparation_focus_items(profile: str, partner_guidance: Dict[str, Any]) -> List[str]:
    focus = {
        "critical_materials": [
            "Map the value chain: feedstock source, processing step, output material, and end user.",
            "Quantify the recovery, recycling, substitution, or dependency-reduction claim.",
            "Check which industrial partner can validate material quality and uptake.",
        ],
        "port_energy": [
            "Define the port-side use case: berth, terminal, vessel demand, and energy baseline.",
            "Show the integration route for shore power, grid capacity, storage, hydrogen, or renewables.",
            "Identify the operator or infrastructure owner needed for a credible pilot.",
        ],
        "maritime_logistics": [
            "Define the operational workflow: route, cargo flow, terminal process, or logistics bottleneck.",
            "Confirm what operational data is available and who controls it.",
            "Show the measurable gain: waiting time, emissions, reliability, fuel use, or coordination.",
        ],
        "green_energy": [
            "Set the energy baseline and the measurable decarbonisation or efficiency target.",
            "Explain the technology integration path for renewables, storage, grid, hydrogen, or industrial use.",
            "Identify a demonstration site and user demand evidence.",
        ],
        "security": [
            "Define the protected asset, threat scenario, and operational risk.",
            "Show how the solution will be validated with infrastructure, cybersecurity, emergency, or public-sector users.",
            "State the expected resilience, preparedness, detection, response, or continuity improvement.",
        ],
        "sme_innovation": [
            "Clarify the company role, customer need, and route to adoption.",
            "Show market validation, first-customer evidence, or scale-up potential.",
            "Explain why EU funding is needed for the next innovation step.",
        ],
        "general": [
            "Map the project directly to the official expected outcomes.",
            "Clarify the validation setting, target users, and measurable impact.",
            "Check whether the call expects partners, demonstration, or specific maturity evidence.",
        ],
    }
    selected = list(focus.get(profile, focus["general"]))
    if partner_guidance.get("primary_roles"):
        selected.append("Connect each priority partner role to a validation need or work package.")
    return selected[:4]


def _first_preparation_actions(profile: str, partner_guidance: Dict[str, Any]) -> List[str]:
    actions = {
        "critical_materials": [
            "Create a one-page value-chain map covering feedstock, process, output material, and target user.",
            "Collect evidence for recovery performance, material quality, and dependency-reduction impact.",
        ],
        "port_energy": [
            "Create a one-page port deployment case covering site, energy baseline, users, and integration constraints.",
            "Check whether the official call expects port-side infrastructure, vessel technology, or both.",
        ],
        "maritime_logistics": [
            "Create a one-page logistics use-case map covering actors, data, bottleneck, and measurable operational gain.",
            "Confirm whether the call focuses on maritime operations, broader transport, or passenger mobility.",
        ],
        "green_energy": [
            "Create a one-page energy case covering baseline, technology route, expected savings, and demonstration site.",
            "Check whether the call expects renewables, hydrogen, grid integration, efficiency, or industrial decarbonisation.",
        ],
        "security": [
            "Create a one-page risk scenario covering protected asset, threat, users, and validation method.",
            "Check whether the call expects cybersecurity, physical security, resilience, preparedness, or public coordination.",
        ],
        "sme_innovation": [
            "Create a one-page market-readiness case covering customer need, company role, adoption route, and scale-up step.",
            "Check whether the call is for SME support, piloting, market uptake, or technology development.",
        ],
        "general": [
            "Create a one-page concept note mapped directly to the call scope.",
            "Check which official expected outcomes the project can credibly address.",
        ],
    }
    selected = list(actions.get(profile, actions["general"]))
    if partner_guidance.get("outreach_focus"):
        selected.append(partner_guidance["outreach_focus"])
    selected.append("Check official eligibility, deadline, budget, TRL, and consortium conditions.")
    selected.append("Prepare evidence for expected impact and validation plan.")
    return selected[:4]


def _call_metadata_gaps(result: Dict[str, Any]) -> List[str]:
    gaps: List[str] = []
    if not str(result.get("eligible_countries") or "").strip():
        gaps.append("country eligibility")
    if not str(result.get("eligible_org_types") or "").strip():
        gaps.append("organisation eligibility")
    if not str(result.get("trl_min") or "").strip() or not str(result.get("trl_max") or "").strip():
        gaps.append("TRL range")
    if result.get("consortium_required") in [None, ""]:
        gaps.append("consortium requirement")
    if not str(result.get("expected_impact") or "").strip():
        gaps.append("expected impact text")
    if not str(result.get("budget_min_eur") or result.get("budget_max_eur") or "").strip():
        gaps.append("budget conditions")
    return gaps[:5]


def _proposal_strengths(
    result: Dict[str, Any],
    project_inputs: Dict[str, Any] | None,
    partner_guidance: Dict[str, Any],
) -> List[str]:
    strengths: List[str] = []
    project_text = _project_text(project_inputs)

    if len(project_text) >= 180:
        strengths.append("The project description is detailed enough for a first call-scope review.")
    if str(result.get("objectives") or "").strip():
        strengths.append("The official topic has objectives that can be mapped against the project concept.")
    if str(result.get("expected_impact") or "").strip():
        strengths.append("Expected outcomes or impact text is available for proposal alignment.")
    if result.get("source_url"):
        strengths.append("An official topic source is available for verification.")
    if partner_guidance.get("partner_types"):
        strengths.append("Relevant partner roles can already be identified for consortium planning.")
    if str(result.get("trl_min") or "").strip() and str(result.get("trl_max") or "").strip():
        strengths.append("The call includes a TRL range that can support maturity alignment.")
    return strengths[:4]


def _readiness_level(
    result: Dict[str, Any],
    project_missing: List[str],
    metadata_gaps: List[str],
    strengths: List[str],
) -> str:
    fit = float(result.get("strategic_success_index") or 0.0)
    similarity = float(result.get("similarity_score") or 0.0)
    if fit >= 65 and similarity >= 0.20 and len(project_missing) <= 1 and len(strengths) >= 3:
        return "Ready for structured review"
    if fit >= 40 or similarity >= 0.12 or len(strengths) >= 2:
        return "Needs targeted clarification"
    return "Early concept - add detail before proposal work"


def _readiness_summary(level: str, metadata_gaps: List[str]) -> str:
    if level == "Ready for structured review":
        return "This looks suitable for a focused call-scope review, provided the official conditions are checked before proposal work."
    if level == "Needs targeted clarification":
        if metadata_gaps:
            return "The match is useful for screening, but proposal preparation should wait until the main gaps are clarified."
        return "The concept has enough signal for review, but the project framing should be sharpened before drafting."
    return "The input needs more project detail before this call can be treated as a practical proposal candidate."


def build_proposal_readiness_memo(
    result: Dict[str, Any],
    project_inputs: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    partner_guidance = build_partner_guidance(result, project_inputs)
    profile = _theme_profile(result)
    project_missing = _missing_project_inputs(project_inputs)
    metadata_gaps = _call_metadata_gaps(result)
    strengths = _proposal_strengths(result, project_inputs, partner_guidance)
    level = _readiness_level(result, project_missing, metadata_gaps, strengths)

    gaps = []
    for item in project_missing:
        gaps.append("Clarify the " + item + ".")
    if metadata_gaps:
        gaps.append("Verify official " + ", ".join(metadata_gaps[:3]) + " before proposal planning.")
    if not partner_guidance.get("partner_types"):
        gaps.append("Clarify whether the project needs external validation or implementation partners.")

    actions = _first_preparation_actions(profile, partner_guidance)

    return {
        "readiness_level": level,
        "summary": _readiness_summary(level, metadata_gaps),
        "strongest_starting_points": strengths,
        "main_gaps": gaps[:4],
        "first_actions": actions[:4],
        "preparation_focus": _preparation_focus_items(profile, partner_guidance),
        "proposal_sections": _proposal_outline(profile, partner_guidance),
        "source_caution": "This memo supports preparation only; official call documents remain authoritative.",
    }


def build_concept_note_starter(
    result: Dict[str, Any],
    project_inputs: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    partner_guidance = build_partner_guidance(result, project_inputs)
    missing = _missing_project_inputs(project_inputs)
    project_summary = _project_text(project_inputs)
    title = _call_title(result)

    if len(project_summary) > 260:
        project_summary = project_summary[:257].rstrip() + "..."
    if not project_summary:
        project_summary = "Describe the project challenge, solution, users, EU relevance, maturity, and expected impact."

    evidence_items = [
        "Relevant official call objectives and expected outcomes",
        "Eligibility, consortium, and deadline conditions from the official source",
    ]
    profile = _theme_profile(result)
    evidence_items.extend(_theme_evidence_items(profile))
    evidence_items.append("Maturity level, pilot plan, and measurable expected impact")
    if partner_guidance["partner_types"]:
        evidence_items.append("Named partner roles for " + ", ".join(partner_guidance["partner_types"][:2]))

    return {
        "working_title": str((project_inputs or {}).get("project_title") or "").strip() or "Working project concept",
        "target_call": title,
        "project_summary": project_summary,
        "call_fit_angle": _theme_angle(result),
        "partner_positioning": partner_guidance["summary"],
        "missing_information": missing,
        "evidence_to_collect": evidence_items[:6],
        "proposal_outline": _proposal_outline(profile, partner_guidance),
        "outreach_focus": partner_guidance.get("outreach_focus", ""),
        "caution": "Use this as a drafting starter only; verify all eligibility and proposal requirements in the official documents.",
    }


def llm_assistant_policy() -> Dict[str, str]:
    return {
        "status": "not_enabled",
        "reason": "LLM drafting should only be enabled after API-key handling, privacy expectations, and source-grounding rules are agreed.",
        "safe_next_step": "Use the template-based concept note assistant until the security and data-handling model is approved.",
    }
