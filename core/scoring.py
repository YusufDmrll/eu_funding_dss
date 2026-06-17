from typing import Any, Dict

from core.theme_coherence import cap_status


ELIGIBILITY_SCORE_MAP = {
    "Eligible": 100.0,
    "Partially Eligible": 70.0,
    "Not Eligible": 30.0,
}

MIN_DISPLAY_SIMILARITY_SCORE = 0.08
MIN_RELIABLE_SIMILARITY_SCORE = 0.14

CLIENT_CONFIDENCE_LABELS = {
    "Reliable": "Strong match",
    "Needs Review": "Worth reviewing",
    "Weak Match": "Needs more detail",
}

SEMANTIC_STRONG_MATCH_THRESHOLD = 0.55
LEXICAL_STRONG_MATCH_THRESHOLD = 0.22


def clamp_score(score: float) -> float:
    return max(0.0, min(100.0, float(score)))


def similarity_to_score(similarity_score: float | None) -> float:
    if similarity_score in [None, ""]:
        return 0.0
    return clamp_score(float(similarity_score) * 100.0)


def eligibility_status_to_score(eligibility_status: str) -> float:
    return ELIGIBILITY_SCORE_MAP.get(str(eligibility_status).strip(), 40.0)


def determine_match_confidence_label(similarity_score: float | None) -> str:
    normalized_score = 0.0 if similarity_score in [None, ""] else float(similarity_score)

    if normalized_score >= MIN_RELIABLE_SIMILARITY_SCORE:
        return "Reliable"
    if normalized_score >= MIN_DISPLAY_SIMILARITY_SCORE:
        return "Needs Review"
    return "Weak Match"


def format_client_confidence_label(label: str | None) -> str:
    normalized_label = str(label or "").strip()
    return CLIENT_CONFIDENCE_LABELS.get(normalized_label, normalized_label or "Needs more detail")


def determine_client_review_status(
    similarity_score: float | None,
    *,
    input_quality: Dict[str, Any] | None = None,
    retrieval_mode: str | None = None,
    internal_confidence_label: str | None = None,
    theme_coherence: Dict[str, Any] | None = None,
) -> str:
    """Return a cautious user-facing status without altering the underlying score."""
    normalized_score = 0.0 if similarity_score in [None, ""] else float(similarity_score)
    internal_label = internal_confidence_label or determine_match_confidence_label(normalized_score)
    quality_level = str((input_quality or {}).get("quality_level") or "detailed")
    intent_level = str((input_quality or {}).get("project_intent_level") or "project_like")

    if intent_level == "non_project" or bool((input_quality or {}).get("is_likely_non_project")):
        base_status = "Needs more detail"
        return cap_status(base_status, (theme_coherence or {}).get("max_client_status"))

    if quality_level == "insufficient" or normalized_score < MIN_DISPLAY_SIMILARITY_SCORE:
        base_status = "Needs more detail"
        return cap_status(base_status, (theme_coherence or {}).get("max_client_status"))

    if internal_label == "Weak Match":
        base_status = "Needs more detail"
        return cap_status(base_status, (theme_coherence or {}).get("max_client_status"))

    if quality_level == "broad":
        base_status = "Worth reviewing"
        return cap_status(base_status, (theme_coherence or {}).get("max_client_status"))

    strong_threshold = (
        SEMANTIC_STRONG_MATCH_THRESHOLD
        if str(retrieval_mode or "").strip().lower() == "semantic"
        else LEXICAL_STRONG_MATCH_THRESHOLD
    )
    if internal_label == "Reliable" and normalized_score >= strong_threshold:
        if theme_coherence:
            coherence_level = str(theme_coherence.get("coherence_level") or "")
            shared_themes = theme_coherence.get("shared_themes") or []
            guardrails = theme_coherence.get("guardrails") or []
            if coherence_level != "strong" or not shared_themes or guardrails:
                return cap_status("Worth reviewing", theme_coherence.get("max_client_status"))
        base_status = "Strong match"
        return cap_status(base_status, (theme_coherence or {}).get("max_client_status"))

    base_status = "Worth reviewing"
    return cap_status(base_status, (theme_coherence or {}).get("max_client_status"))


def _parse_optional_int(value: Any) -> int | None:
    if value in [None, ""]:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def trl_alignment_score(
    user_trl: int | None,
    trl_min: Any,
    trl_max: Any,
) -> float:
    min_value = _parse_optional_int(trl_min)
    max_value = _parse_optional_int(trl_max)

    if user_trl is None:
        return 50.0

    if min_value is None and max_value is None:
        return 50.0

    if min_value is not None and user_trl < min_value:
        distance = min_value - user_trl
        return clamp_score(100.0 - (25.0 * distance))

    if max_value is not None and user_trl > max_value:
        distance = user_trl - max_value
        return clamp_score(100.0 - (25.0 * distance))

    return 100.0


def calculate_strategic_success_index(
    similarity_score: float | None,
    eligibility_status: str,
    user_trl: int | None,
    trl_min: Any,
    trl_max: Any,
) -> Dict[str, Any]:
    similarity_component = similarity_to_score(similarity_score)
    eligibility_component = eligibility_status_to_score(eligibility_status)
    trl_component = trl_alignment_score(user_trl, trl_min, trl_max)

    final_score = round(
        (0.50 * similarity_component)
        + (0.30 * eligibility_component)
        + (0.20 * trl_component),
        2,
    )

    return {
        "strategic_success_index": final_score,
        "match_confidence_label": determine_match_confidence_label(similarity_score),
        "strategic_success_components": {
            "similarity": round(similarity_component, 2),
            "eligibility": round(eligibility_component, 2),
            "trl_alignment": round(trl_component, 2),
        },
        "strategic_success_explanation": (
            "A simple 0-100 fit score that combines topic similarity, "
            "current eligibility outcome, and TRL alignment."
        ),
    }
