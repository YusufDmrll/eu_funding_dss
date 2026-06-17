from typing import Dict, Any, List


COUNTRY_ALIASES = {
    "turkey": ["turkey", "türkiye", "turkiye"],
    "germany": ["germany", "deutschland"],
    "netherlands": ["netherlands", "the netherlands", "holland"],
}

ORG_TYPE_ALIASES = {
    "sme": ["sme", "small and medium-sized enterprise", "small and medium-sized enterprises"],
    "university": ["university", "higher education", "higher education institution", "hei"],
    "research institute": ["research institute", "research organisation", "research organization", "rto"],
    "public body": ["public body", "public authority", "municipality", "government"],
    "company": ["company", "enterprise", "industry", "business", "private entity"],
}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def expand_country_aliases(country: str) -> List[str]:
    country_norm = normalize_text(country)
    return COUNTRY_ALIASES.get(country_norm, [country_norm])


def expand_org_aliases(org_type: str) -> List[str]:
    org_norm = normalize_text(org_type)
    return ORG_TYPE_ALIASES.get(org_norm, [org_norm])


def country_seems_eligible(user_country: str, eligible_countries_text: Any) -> str:
    text = normalize_text(eligible_countries_text)
    if not text:
        return "unknown"

    aliases = expand_country_aliases(user_country)

    if any(alias in text for alias in aliases):
        return "yes"

    broad_patterns = [
        "associated countries",
        "eu member states and associated countries",
        "eligible countries",
        "all member states",
        "all eu member states",
    ]

    if any(pattern in text for pattern in broad_patterns):
        if normalize_text(user_country) in ["turkey", "türkiye", "turkiye"]:
            return "probable"
        return "probable"

    return "no"


def org_type_seems_eligible(user_org_type: str, eligible_org_types_text: Any) -> str:
    text = normalize_text(eligible_org_types_text)
    if not text:
        return "unknown"

    aliases = expand_org_aliases(user_org_type)

    if any(alias in text for alias in aliases):
        return "yes"

    broad_patterns = [
        "all legal entities",
        "legal entities",
        "companies",
        "enterprises",
        "research organisations",
        "research organizations",
        "universities",
        "public bodies",
    ]

    if any(pattern in text for pattern in broad_patterns):
        return "probable"

    return "no"


def evaluate_eligibility(
    call_record: Dict[str, Any],
    user_country: str,
    user_org_type: str,
    user_trl: int | None,
    has_consortium: bool,
    partner_count: int | None,
) -> Dict[str, Any]:
    reasons = []
    warnings = []
    data_quality_flags = []
    hard_fail = False

    eligible_countries_raw = call_record.get("eligible_countries")
    eligible_org_types_raw = call_record.get("eligible_org_types")

    record_trl_min = call_record.get("trl_min")
    record_trl_max = call_record.get("trl_max")
    consortium_required = call_record.get("consortium_required")
    min_partners = call_record.get("min_partners")

    country_status = country_seems_eligible(user_country, eligible_countries_raw)
    if country_status == "no":
        warnings.append("Applicant country does not appear clearly eligible based on the available call details.")
    elif country_status == "unknown":
        warnings.append("Eligible countries field is missing or unclear.")
        data_quality_flags.append("Country eligibility details are missing or incomplete.")
    elif country_status == "probable":
        warnings.append("Applicant country appears probably eligible, but the available call details are too general for full certainty.")
        data_quality_flags.append("Country eligibility requires manual validation.")

    org_status = org_type_seems_eligible(user_org_type, eligible_org_types_raw)
    if org_status == "no":
        warnings.append("Organisation type does not appear clearly eligible based on the available call details.")
    elif org_status == "unknown":
        warnings.append("Eligible organisation types field is missing or unclear.")
        data_quality_flags.append("Organisation type details are missing or incomplete.")
    elif org_status == "probable":
        warnings.append("Organisation type appears probably eligible, but the available call details are too general for full certainty.")
        data_quality_flags.append("Organisation eligibility requires manual validation.")

    if user_trl is not None:
        if record_trl_min not in [None, ""]:
            if user_trl < int(record_trl_min):
                reasons.append("Project TRL is below the minimum required level.")
                hard_fail = True

        if record_trl_max not in [None, ""]:
            if user_trl > int(record_trl_max):
                reasons.append("Project TRL is above the maximum expected level.")
                hard_fail = True
    else:
        warnings.append("Project TRL not provided.")

    if consortium_required in [1, "1", True]:
        if not has_consortium:
            warnings.append("This call appears to require a consortium.")

        if min_partners not in [None, ""]:
            if partner_count is None:
                warnings.append("Minimum partner requirement exists but partner count was not provided.")
            elif int(partner_count) < int(min_partners):
                warnings.append("Number of partners is below the minimum required.")

    if hard_fail:
        status = "Not Eligible"
    elif warnings:
        status = "Partially Eligible"
    else:
        status = "Eligible"

    return {
        "eligibility_status": status,
        "eligibility_reasons": reasons,
        "eligibility_warnings": warnings,
        "data_quality_flags": data_quality_flags,
    }
