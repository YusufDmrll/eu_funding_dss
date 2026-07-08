import csv
import re
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIRECTORY_PATH = PROJECT_ROOT / "data" / "imports" / "partner_directory.csv"

PARTNER_DIRECTORY_COLUMNS = [
    "organization_name",
    "country",
    "organization_type",
    "sector",
    "roles",
    "themes",
    "website",
    "notes",
    "verified_status",
    "last_checked_utc",
]

THEME_KEYWORDS = {
    "critical materials / circularity": (
        "critical raw material",
        "raw material",
        "rare earth",
        "battery",
        "recycling",
        "circular",
        "materials",
    ),
    "port energy / green harbour": (
        "port",
        "harbour",
        "shore power",
        "berth",
        "terminal",
        "green harbour",
    ),
    "maritime / logistics": (
        "maritime",
        "shipping",
        "vessel",
        "waterborne",
        "logistics",
        "freight",
        "supply chain",
    ),
    "green energy / hydrogen": (
        "hydrogen",
        "renewable",
        "clean energy",
        "energy efficiency",
        "storage",
        "grid",
        "decarbon",
    ),
    "security / resilience": (
        "security",
        "cybersecurity",
        "critical infrastructure",
        "resilience",
        "emergency",
        "risk assessment",
    ),
    "sme / scale-up innovation": (
        "sme",
        "startup",
        "start-up",
        "scale-up",
        "market uptake",
        "commercialisation",
    ),
    "digital / automation": (
        "artificial intelligence",
        " ai ",
        "automation",
        "data",
        "digital twin",
        "robotics",
        "cloud",
    ),
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalise(value: Any) -> str:
    return _clean(value).lower().replace("-", " ")


def _split_values(value: Any) -> list[str]:
    raw = _clean(value)
    if not raw:
        return []
    return [_clean(item) for item in re.split(r"[;,|]", raw) if _clean(item)]


def _token_set(value: Any) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _normalise(value))
        if len(token) > 2 and token not in {"and", "the", "for", "with", "from"}
    }


def detect_partner_themes(*texts: Any) -> list[str]:
    combined = " ".join(_normalise(text) for text in texts)
    themes = [
        theme
        for theme, terms in THEME_KEYWORDS.items()
        if any(term in combined for term in terms)
    ]
    return themes


def load_partner_directory(path: Path = DEFAULT_DIRECTORY_PATH) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        return [
            {column: _clean(row.get(column)) for column in PARTNER_DIRECTORY_COLUMNS}
            for row in reader
            if _clean(row.get("organization_name"))
        ]


def _role_match_score(requested_roles: Iterable[str], partner_roles: Iterable[str]) -> tuple[int, list[str]]:
    requested = list(requested_roles)
    partner = list(partner_roles)
    reasons: list[str] = []
    score = 0
    for requested_role in requested:
        requested_tokens = _token_set(requested_role)
        for partner_role in partner:
            partner_tokens = _token_set(partner_role)
            if not requested_tokens or not partner_tokens:
                continue
            overlap = requested_tokens & partner_tokens
            if overlap:
                score += min(10, 4 + len(overlap) * 2)
                reasons.append(f"role overlap with {requested_role}")
                break
    return min(score, 24), reasons[:3]


def _theme_match_score(requested_themes: Iterable[str], partner_themes: Iterable[str]) -> tuple[int, list[str]]:
    requested = {_normalise(theme) for theme in requested_themes}
    partner = {_normalise(theme) for theme in partner_themes}
    exact = requested & partner
    if exact:
        return min(18, 6 * len(exact)), [f"theme overlap: {theme}" for theme in sorted(exact)[:3]]

    score = 0
    reasons: list[str] = []
    for requested_theme in requested:
        requested_tokens = _token_set(requested_theme)
        for partner_theme in partner:
            overlap = requested_tokens & _token_set(partner_theme)
            if overlap:
                score += min(6, 2 + len(overlap))
                reasons.append(f"related theme: {partner_theme}")
                break
    return min(score, 12), reasons[:3]


def score_partner_record(
    partner: Mapping[str, Any],
    *,
    requested_roles: Iterable[str],
    requested_themes: Iterable[str],
    user_country: str = "",
) -> dict[str, Any]:
    role_score, role_reasons = _role_match_score(requested_roles, _split_values(partner.get("roles")))
    theme_score, theme_reasons = _theme_match_score(requested_themes, _split_values(partner.get("themes")))
    country_score = 0
    country = _normalise(partner.get("country"))
    requested_country = _normalise(user_country)
    if requested_country and country == requested_country:
        country_score = 6
    elif country in {"eu", "europe", "european union", "cross-border"}:
        country_score = 2

    verified = _normalise(partner.get("verified_status"))
    verification_score = 3 if verified in {"verified", "confirmed", "active"} else 1 if verified else 0
    total = role_score + theme_score + country_score + verification_score
    reasons = role_reasons + theme_reasons
    if country_score:
        reasons.append("country or EU coverage is relevant")
    if verification_score >= 3:
        reasons.append("partner record is marked verified")

    return {
        "organization_name": _clean(partner.get("organization_name")),
        "country": _clean(partner.get("country")),
        "organization_type": _clean(partner.get("organization_type")),
        "sector": _clean(partner.get("sector")),
        "roles": _split_values(partner.get("roles")),
        "themes": _split_values(partner.get("themes")),
        "website": _clean(partner.get("website")),
        "notes": _clean(partner.get("notes")),
        "verified_status": _clean(partner.get("verified_status")),
        "score": total,
        "reasons": reasons[:4],
    }


def build_partner_directory_suggestions(
    *,
    result: Mapping[str, Any],
    project_inputs: Mapping[str, Any] | None,
    partner_roles: Iterable[Mapping[str, Any]],
    directory_path: Path = DEFAULT_DIRECTORY_PATH,
    limit: int = 3,
) -> dict[str, Any]:
    role_labels = [_clean(role.get("label")) for role in partner_roles if _clean(role.get("label"))]
    requested_themes = detect_partner_themes(
        result.get("call_title"),
        result.get("topic_title"),
        result.get("description"),
        result.get("objectives"),
        result.get("expected_impact"),
        result.get("keywords"),
        (project_inputs or {}).get("project_desc"),
        (project_inputs or {}).get("project_title"),
    )
    search_profile = {
        "roles": role_labels[:6],
        "themes": requested_themes,
        "country": _clean((project_inputs or {}).get("user_country")),
    }
    if not directory_path.exists():
        return {
            "status": "not_configured",
            "matches": [],
            "search_profile": search_profile,
            "note": "No curated partner directory is configured yet; use this as a search profile.",
        }

    records = load_partner_directory(directory_path)
    scored = [
        score_partner_record(
            partner,
            requested_roles=role_labels,
            requested_themes=requested_themes,
            user_country=search_profile["country"],
        )
        for partner in records
    ]
    matches = [
        item
        for item in sorted(scored, key=lambda entry: (-entry["score"], entry["organization_name"]))
        if item["score"] >= 8
    ][:limit]
    return {
        "status": "matched" if matches else "no_matches",
        "matches": matches,
        "search_profile": search_profile,
        "note": (
            "Curated partner matches are suggestions for outreach planning, not consortium confirmation."
            if matches
            else "No strong curated partner-directory match was found; use the role profile for manual outreach."
        ),
    }
