import re
import unicodedata
from typing import Any, Dict, List


MIN_DESCRIPTION_CHARS = 40
MIN_MEANINGFUL_WORDS = 6
MIN_UNIQUE_MEANINGFUL_WORDS = 4
MIN_ALPHA_RATIO = 0.65
MIN_SCREENABLE_CHARS = 24
MIN_SCREENABLE_MEANINGFUL_WORDS = 4
MIN_SCREENABLE_UNIQUE_WORDS = 3
MIN_SCREENABLE_ALPHA_RATIO = 0.60
MIN_DETAILED_DESCRIPTION_CHARS = 160
MIN_DETAILED_MEANINGFUL_WORDS = 22
MIN_DETAILED_UNIQUE_WORDS = 15

WEAK_INPUT_GUIDANCE = (
    "Add a little more detail about the problem, technology, target users, "
    "and expected impact to get stronger matches."
)

NON_PROJECT_INPUT_WARNING = (
    "This looks like a technical log or system output rather than a project idea. "
    "For stronger matches, describe the actual project challenge, solution, target users, "
    "and expected impact."
)

NON_PROJECT_PATTERNS = (
    ("codex output", r"\bcodex\b"),
    ("files changed", r"\bfiles? changed\b"),
    ("test results", r"\b(?:tests? passed|test results?|full test suite)\b"),
    ("validation report", r"\bvalidation(?: results?| summary| report)?\b"),
    ("processed records", r"\b(?:processed|enriched|reviewed)\s+\d+\s+(?:records?|candidates?|rows?)\b"),
    ("hash status", r"\b(?:hash|sha-?256)\b.{0,35}\b(?:unchanged|verified|match(?:es|ed)?)\b"),
    ("database status", r"\bsqlite\b.{0,35}\b(?:unchanged|updated|records?|database)\b"),
    ("dependency report", r"\b(?:dependency|package|version)\s+(?:check|report|status|summary)\b"),
    ("terminal command", r"\bpython\s+-m\s+(?:unittest|py_compile|streamlit)\b"),
    ("terminal result", r"\b(?:exit code|traceback|script completed|script failed)\b"),
    ("generated output", r"\b(?:output file|wrote|generated at|verification status distribution)\b"),
    ("technical file path", r"(?:[a-zA-Z]:\\[^\n]+|\b(?:data|core|scripts|tests|app)/[^\s]+\.(?:py|csv|json|sqlite|pdf))"),
)

PROJECT_INTENT_PATTERNS = (
    r"\b(?:we|our team|the consortium)\s+(?:are|is|will be)?\s*(?:developing|building|piloting|designing|creating)\b",
    r"\bour project\b",
    r"\b(?:target users?|beneficiaries|customers?|operators?|authorities)\b",
    r"\b(?:expected impact|aims? to|will enable|will reduce|will improve)\b",
    r"\b(?:technology|solution|platform|process|system)\b.{0,80}\b(?:pilot|demonstrat|deploy|validate|develop)\w*\b",
)


def _looks_like_latin_word(token: str) -> bool:
    letters = [char for char in token if char.isalpha()]
    if len(letters) < 3:
        return False

    latin_letters = 0
    for char in letters:
        if "LATIN" in unicodedata.name(char, ""):
            latin_letters += 1

    return bool(letters) and (latin_letters / len(letters)) >= 0.8


def _extract_meaningful_words(text: str) -> List[str]:
    # This validation is intentionally heuristic: it is optimized for short
    # project descriptions written in Latin-alphabet European languages.
    raw_tokens = re.findall(r"[^\W\d_]+", text.lower(), flags=re.UNICODE)
    return [token for token in raw_tokens if _looks_like_latin_word(token)]


def evaluate_project_intent(text: str) -> Dict[str, Any]:
    cleaned_text = (text or "").strip()
    matched_patterns = [
        label
        for label, pattern in NON_PROJECT_PATTERNS
        if re.search(pattern, cleaned_text, flags=re.IGNORECASE | re.DOTALL)
    ]
    project_signals = sum(
        1
        for pattern in PROJECT_INTENT_PATTERNS
        if re.search(pattern, cleaned_text, flags=re.IGNORECASE | re.DOTALL)
    )

    # Require several independent operational/reporting signals so an actual
    # project mentioning validation or metadata is not incorrectly flagged.
    non_project_score = len(matched_patterns)
    is_likely_non_project = non_project_score >= 3 and non_project_score >= project_signals + 2
    may_be_non_project = not is_likely_non_project and non_project_score >= 2 and project_signals == 0

    if is_likely_non_project:
        intent_level = "non_project"
    elif may_be_non_project:
        intent_level = "uncertain"
    else:
        intent_level = "project_like"

    return {
        "is_project_like": not is_likely_non_project,
        "is_likely_non_project": is_likely_non_project,
        "project_intent_level": intent_level,
        "non_project_signal_count": non_project_score,
        "project_signal_count": project_signals,
        "matched_non_project_patterns": matched_patterns,
        "project_intent_warning": NON_PROJECT_INPUT_WARNING if is_likely_non_project else "",
    }


def evaluate_project_description(text: str) -> Dict[str, Any]:
    cleaned_text = (text or "").strip()
    meaningful_words = _extract_meaningful_words(cleaned_text)
    unique_meaningful_words = set(meaningful_words)

    alpha_chars = sum(1 for char in cleaned_text if char.isalpha())
    total_chars = len(cleaned_text)
    alpha_ratio = (alpha_chars / total_chars) if total_chars else 0.0

    checks = {
        "char_count": total_chars,
        "meaningful_word_count": len(meaningful_words),
        "unique_meaningful_word_count": len(unique_meaningful_words),
        "alpha_ratio": round(alpha_ratio, 2),
    }

    is_valid = (
        total_chars >= MIN_DESCRIPTION_CHARS
        and len(meaningful_words) >= MIN_MEANINGFUL_WORDS
        and len(unique_meaningful_words) >= MIN_UNIQUE_MEANINGFUL_WORDS
        and alpha_ratio >= MIN_ALPHA_RATIO
    )

    # Meaningful short inputs may still be screened, while random or nearly
    # empty text remains blocked from retrieval.
    can_screen = (
        total_chars >= MIN_SCREENABLE_CHARS
        and len(meaningful_words) >= MIN_SCREENABLE_MEANINGFUL_WORDS
        and len(unique_meaningful_words) >= MIN_SCREENABLE_UNIQUE_WORDS
        and alpha_ratio >= MIN_SCREENABLE_ALPHA_RATIO
    )

    is_detailed = (
        is_valid
        and total_chars >= MIN_DETAILED_DESCRIPTION_CHARS
        and len(meaningful_words) >= MIN_DETAILED_MEANINGFUL_WORDS
        and len(unique_meaningful_words) >= MIN_DETAILED_UNIQUE_WORDS
    )

    if not is_valid:
        quality_level = "insufficient"
    elif is_detailed:
        quality_level = "detailed"
    else:
        quality_level = "broad"

    intent_result = evaluate_project_intent(cleaned_text)

    return {
        "is_valid": is_valid,
        "can_screen": can_screen,
        "is_broad": quality_level == "broad",
        "needs_more_detail": quality_level != "detailed",
        "quality_level": quality_level,
        "guidance_message": WEAK_INPUT_GUIDANCE if quality_level != "detailed" else "",
        "checks": checks,
        **intent_result,
    }
