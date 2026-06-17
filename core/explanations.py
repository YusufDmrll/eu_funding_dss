import re
import unicodedata
from typing import Any, Dict, List, Tuple

from core.input_quality import evaluate_project_intent
from core.theme_coherence import assess_theme_coherence, build_coherence_explanation

DEFAULT_MATCH_EXPLANATION = (
    "This result was matched based on limited textual overlap and should be reviewed manually."
)

FIELD_LABELS = [
    ("keywords", "keywords"),
    ("call_title", "call title"),
    ("objectives", "objectives"),
    ("expected_impact", "expected impact"),
    ("description", "description"),
]

COMMON_STOPWORDS = {
    "and",
    "the",
    "for",
    "with",
    "from",
    "that",
    "this",
    "into",
    "their",
    "about",
    "project",
    "system",
    "support",
    "application",
    "de",
    "het",
    "een",
    "van",
    "voor",
    "met",
    "door",
    "bir",
    "ve",
    "ile",
    "icin",
    "için",
    "olan",
}

WEAK_GENERIC_TERMS = {
    "about",
    "across",
    "aim",
    "aims",
    "analytics",
    "approach",
    "based",
    "better",
    "build",
    "building",
    "combine",
    "combining",
    "current",
    "decision",
    "develop",
    "developing",
    "development",
    "digital",
    "driven",
    "effective",
    "help",
    "helps",
    "improve",
    "improving",
    "includes",
    "including",
    "intended",
    "lower",
    "method",
    "multi",
    "multiple",
    "operations",
    "operational",
    "planning",
    "platform",
    "process",
    "processes",
    "reduce",
    "reducing",
    "related",
    "relevant",
    "results",
    "scalable",
    "screening",
    "service",
    "solution",
    "solutions",
    "strategic",
    "stronger",
    "supports",
    "through",
    "using",
    "while",
    "within",
    "work",
    "works",
    "would",
    "are",
}

WEAK_GENERIC_TERMS.update(
    {
        "additional",
        "changed",
        "evidence",
        "files",
        "hash",
        "metadata",
        "official",
        "output",
        "processed",
        "records",
        "source",
        "sqlite",
        "tests",
        "validation",
        "activities",
        "create",
        "europe",
        "focus",
        "innovative",
        "level",
        "people",
        "potential",
        "public",
        "should",
        "smart",
        "technology",
        "will",
        "data",
        "environmental",
        "funding",
        "impact",
        "import",
        "imported",
        "imports",
        "include",
        "projects",
        "regional",
        "sector",
        "services",
        "technologies",
    }
)

TERM_WHITELIST = {"ai", "raw", "sme", "smes", "trl", "port", "ports", "grid"}


def _looks_like_latin_word(token: str) -> bool:
    letters = [char for char in token if char.isalpha()]
    if len(letters) < 3:
        return False

    latin_letters = 0
    for char in letters:
        if "LATIN" in unicodedata.name(char, ""):
            latin_letters += 1

    return bool(letters) and (latin_letters / len(letters)) >= 0.8


def _tokenize(text: Any) -> List[str]:
    raw_tokens = re.findall(r"[^\W\d_]+", str(text or "").lower(), flags=re.UNICODE)
    filtered_tokens = []
    for token in raw_tokens:
        if not _looks_like_latin_word(token):
            continue
        if token in COMMON_STOPWORDS or token in WEAK_GENERIC_TERMS:
            continue
        if len(token) < 4 and token not in TERM_WHITELIST:
            continue
        filtered_tokens.append(token)
    return filtered_tokens


def _ordered_unique(tokens: List[str]) -> List[str]:
    seen = set()
    ordered = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def _join_labels(labels: List[str]) -> str:
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return f"{', '.join(labels[:-1])}, and {labels[-1]}"


def _remove_redundant_signals(signals: List[str]) -> List[str]:
    cleaned: List[str] = []
    for signal in signals:
        lower_signal = signal.lower()
        if any(
            lower_signal != existing.lower()
            and lower_signal in existing.lower()
            for existing in cleaned
        ):
            continue
        cleaned = [
            existing
            for existing in cleaned
            if not (
                existing.lower() != lower_signal
                and existing.lower() in lower_signal
            )
        ]
        cleaned.append(signal)
    return cleaned


def _contains_any(signals: List[str], terms: List[str]) -> bool:
    lowered = [signal.lower() for signal in signals]
    return any(term in signal for signal in lowered for term in terms)


def _build_call_text(call_record: Dict[str, Any]) -> str:
    parts = [
        call_record.get("call_title", ""),
        call_record.get("keywords", ""),
        call_record.get("description", ""),
        call_record.get("objectives", ""),
        call_record.get("expected_impact", ""),
    ]
    return " ".join(str(part or "").lower() for part in parts)


def _build_phrase_candidates(field_name: str, value: Any, project_term_set: set[str]) -> List[str]:
    text = str(value or "").strip()
    if not text:
        return []

    candidates: List[str] = []

    if field_name == "keywords":
        raw_phrases = re.split(r"[,;|]", text)
        for raw_phrase in raw_phrases:
            phrase_tokens = _ordered_unique(_tokenize(raw_phrase))
            if phrase_tokens and all(token in project_term_set for token in phrase_tokens):
                candidates.append(" ".join(phrase_tokens[:3]))
    else:
        tokens = _ordered_unique(_tokenize(text))
        for window_size in (3, 2):
            for index in range(len(tokens) - window_size + 1):
                phrase_tokens = tokens[index:index + window_size]
                if all(token in project_term_set for token in phrase_tokens):
                    candidates.append(" ".join(phrase_tokens))

    unique_candidates = []
    for candidate in candidates:
        if candidate not in unique_candidates:
            unique_candidates.append(candidate)
    return unique_candidates[:3]


def generate_match_explanation(
    project_text: str,
    call_record: Dict[str, Any],
    *,
    theme_coherence: Dict[str, Any] | None = None,
) -> str:
    call_text = _build_call_text(call_record)
    if not call_text.strip():
        return DEFAULT_MATCH_EXPLANATION

    if evaluate_project_intent(project_text).get("is_likely_non_project"):
        return (
            "This match is driven mainly by broad EU funding terminology in the input, "
            "so it should be treated carefully rather than as a project-specific fit."
        )

    coherence = theme_coherence or assess_theme_coherence(project_text, call_record)
    coherence_explanation = build_coherence_explanation(coherence)
    if coherence_explanation:
        return coherence_explanation

    project_terms = _ordered_unique(_tokenize(project_text))
    project_term_set = set(project_terms)

    field_matches: List[Tuple[str, List[str], List[str]]] = []
    for field_name, label in FIELD_LABELS:
        field_terms = _ordered_unique(_tokenize(call_record.get(field_name, "")))
        overlap_terms = [term for term in field_terms if term in project_term_set]
        overlap_phrases = _build_phrase_candidates(field_name, call_record.get(field_name, ""), project_term_set)
        if overlap_terms:
            field_matches.append((label, overlap_terms, overlap_phrases))

    if not field_matches:
        return DEFAULT_MATCH_EXPLANATION

    top_fields = sorted(
        field_matches,
        key=lambda item: ((len(item[2]) * 3) + len(item[1])),
        reverse=True,
    )
    primary_labels = [label for label, _terms, _phrases in top_fields[:2]]

    shared_signals: List[str] = []
    for _label, terms, phrases in top_fields:
        for item in phrases + terms:
            if item not in shared_signals:
                shared_signals.append(item)
            if len(shared_signals) == 3:
                break
        if len(shared_signals) == 3:
            break

    if not shared_signals:
        return DEFAULT_MATCH_EXPLANATION

    shared_signals = _remove_redundant_signals(shared_signals)

    if _contains_any(shared_signals, ["rare earth", "raw materials", "critical raw materials", "recycling"]) or (
        _contains_any(shared_signals, ["battery", "batteries"])
        and any(term in call_text for term in ("battery-grade", "electrode", "raw materials", "recycling"))
    ):
        if "direct recycling" in call_text:
            return "Relevant because it focuses on direct recycling routes for recovered materials."
        if ("battery" in call_text or "battery materials" in call_text) and "recycling" in call_text:
            return "Relevant because it links battery-material recovery with recycling and upgrading activity."
        if "battery-grade" in call_text or "electrode" in call_text:
            return "Relevant because it targets battery-grade materials, electrodes, and related raw-material processing."
        if "battery" in call_text or "battery materials" in call_text:
            return "Relevant because it connects with battery-material value chains and materials upgrading."
        if "substitution" in call_text or "dependencies" in call_text:
            return "Relevant because it addresses reduced dependence on critical raw materials."
        if ("processing" in call_text or "refining" in call_text) and not (
            "recycling" in call_text or "secondary raw materials" in call_text or "direct recycling" in call_text
        ):
            return "Relevant because it addresses raw-material processing, refining, and deployment capacity."
        if "value chain" in call_text or "supply chain" in call_text or "capacity" in call_text:
            return "Relevant because it supports critical raw-material value-chain capacity and supply resilience."
        if "secondary raw materials" in call_text or "recycling" in call_text:
            return "Relevant because it targets recycling and secondary raw-material recovery."
        if "extraction" in call_text:
            return "Relevant because it addresses upstream raw-material extraction and processing."
        return "Relevant because it addresses critical raw materials recovery or processing."

    if coherence.get("call_has_port_context") and _contains_any(
        shared_signals, ["shore", "berth", "port", "ports"]
    ) and _contains_any(
        shared_signals, ["energy", "electricity", "emissions"]
    ):
        if "shore" in call_text or "berth" in call_text:
            return "Relevant because it focuses on shore-side port energy use and berth-related emissions."
        if "terminal" in call_text:
            return "Relevant because it focuses on terminal-level port infrastructure linked to energy use and emissions."
        if "shipyard" in call_text or "shipyards" in call_text:
            return "Relevant because it connects port energy themes with shipyard and vessel-side transition activity."
        if "infrastructure" in call_text or "terminal" in call_text:
            return "Relevant because it focuses on port infrastructure upgrades linked to energy use and emissions."
        if "grid" in call_text or "electricity" in call_text or "energy planning" in call_text:
            return "Relevant because it focuses on port electricity use, energy planning, and related emissions."
        if "shipping" in call_text or "ships" in call_text:
            return "Relevant because it connects port operations with shipping-related energy efficiency."
        return "Relevant because it links port operations with energy use and emissions reduction."

    has_security_signal = _contains_any(shared_signals, ["security", "critical infrastructure", "anomaly"])
    has_security_context = any(
        term in call_text
        for term in ("security", "protection", "critical infrastructure", "anomaly detection")
    )
    if has_security_signal or (_contains_any(shared_signals, ["resilience"]) and has_security_context):
        if "anomaly" in call_text or "monitoring" in call_text:
            return "Relevant because it focuses on infrastructure monitoring, anomaly detection, and resilience."
        if "critical infrastructure" in call_text or "protection" in call_text:
            return "Relevant because it addresses protection of critical infrastructure and operational resilience."
        return "Relevant because it focuses on infrastructure security and operational resilience."

    if len(shared_signals) == 1:
        return f"Relevant because it directly connects with {shared_signals[0]}."

    if len(shared_signals) == 2:
        signal_text = f"{shared_signals[0]} and {shared_signals[1]}"
    else:
        signal_text = f"{shared_signals[0]}, {shared_signals[1]}, and {shared_signals[2]}"

    return f"Relevant because it connects strongly with {signal_text}."


def build_safe_match_explanation(
    project_text: str,
    call_record: Dict[str, Any],
    *,
    theme_coherence: Dict[str, Any] | None = None,
) -> str:
    try:
        explanation = generate_match_explanation(
            project_text,
            call_record,
            theme_coherence=theme_coherence,
        )
    except Exception:
        explanation = DEFAULT_MATCH_EXPLANATION

    cleaned = str(explanation or "").strip()
    return cleaned if cleaned else DEFAULT_MATCH_EXPLANATION
