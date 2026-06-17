from collections import Counter
import logging
from math import sqrt
from pathlib import Path
import re
import sqlite3
from typing import List, Dict, Any

from core.text_utils import build_call_text
from core.deadlines import classify_deadline, should_include_call
from core.explanations import build_safe_match_explanation
from core.guidance import build_next_step_guidance
from core.eligibility import evaluate_eligibility
from core.scoring import calculate_strategic_success_index
from core.theme_coherence import assess_theme_coherence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "eu_funding.sqlite"
DEFAULT_END_USER_RETRIEVAL_MODE = "semantic"
INTERNAL_BASELINE_RETRIEVAL_MODE = "lexical"
END_USER_RETRIEVAL_FALLBACK_NOTE = (
    "Using baseline text matching for this run. Review the shortlist carefully."
)
RETRIEVAL_MODE_LABELS = {
    "lexical": "Lexical (TF-IDF)",
    "semantic": "Semantic (Embeddings)",
}
LOGGER = logging.getLogger(__name__)


def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def fetch_call_records() -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            call_id,
            program,
            pillar,
            cluster,
            call_title,
            topic_title,
            description,
            objectives,
            expected_impact,
            action_type,
            deadline_utc,
            budget_min_eur,
            budget_max_eur,
            trl_min,
            trl_max,
            eligible_countries,
            eligible_org_types,
            consortium_required,
            min_partners,
            keywords,
            source_url,
            source_last_checked_utc,
            verified_status
        FROM funding_calls
    """)

    rows = cur.fetchall()
    conn.close()

    columns = [
        "call_id",
        "program",
        "pillar",
        "cluster",
        "call_title",
        "topic_title",
        "description",
        "objectives",
        "expected_impact",
        "action_type",
        "deadline_utc",
        "budget_min_eur",
        "budget_max_eur",
        "trl_min",
        "trl_max",
        "eligible_countries",
        "eligible_org_types",
        "consortium_required",
        "min_partners",
        "keywords",
        "source_url",
        "source_last_checked_utc",
        "verified_status",
    ]

    records = [dict(zip(columns, row)) for row in rows]
    return records


def _normalize_sort_field(sort_by: str) -> str:
    if sort_by in {"similarity_score", "strategic_success_index"}:
        return sort_by
    return "strategic_success_index"


def _normalize_retrieval_mode(retrieval_mode: str) -> str:
    if retrieval_mode in RETRIEVAL_MODE_LABELS:
        return retrieval_mode
    return "lexical"


def _tokenize_fallback_text(value: str) -> List[str]:
    return re.findall(r"[a-z0-9]{2,}", (value or "").lower())


def _cosine_similarity_from_counters(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0

    shared_terms = set(left).intersection(right)
    dot_product = sum(left[term] * right[term] for term in shared_terms)
    left_norm = sqrt(sum(value * value for value in left.values()))
    right_norm = sqrt(sum(value * value for value in right.values()))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def _compute_fallback_lexical_similarities(project_text: str, call_texts: List[str]) -> List[float]:
    project_counter = Counter(_tokenize_fallback_text(project_text))
    return [
        _cosine_similarity_from_counters(project_counter, Counter(_tokenize_fallback_text(call_text)))
        for call_text in call_texts
    ]


def _compute_lexical_similarities(project_text: str, call_texts: List[str]) -> List[float]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except Exception:
        return _compute_fallback_lexical_similarities(project_text, call_texts)

    vectorizer = TfidfVectorizer(stop_words="english")
    tfidf_matrix = vectorizer.fit_transform(call_texts + [project_text])

    call_vectors = tfidf_matrix[:-1]
    project_vector = tfidf_matrix[-1]

    similarities = cosine_similarity(project_vector, call_vectors).flatten()
    return similarities.tolist()


def _compute_semantic_similarities(project_text: str, call_texts: List[str]) -> List[float]:
    from core.semantic_retrieval import compute_semantic_similarities

    return compute_semantic_similarities(project_text=project_text, call_texts=call_texts)


def _filter_records_by_deadline(
    records: List[Dict[str, Any]],
    *,
    include_expired: bool,
) -> List[Dict[str, Any]]:
    filtered_records = []
    for record in records:
        deadline_status = classify_deadline(record.get("deadline_utc"))
        if not should_include_call(
            record.get("deadline_utc"),
            include_expired=include_expired,
        ):
            continue

        enriched_record = record.copy()
        enriched_record["deadline_status"] = deadline_status
        filtered_records.append(enriched_record)
    return filtered_records


def _build_ranked_results(
    records: List[Dict[str, Any]],
    similarities: List[float],
    project_text: str,
    user_country: str,
    user_org_type: str,
    user_trl: int | None,
    has_consortium: bool,
    partner_count: int | None,
    sort_by: str,
) -> List[Dict[str, Any]]:
    ranked = []
    for record, score in zip(records, similarities):
        enriched = record.copy()
        enriched["similarity_score"] = float(score)

        eligibility_result = evaluate_eligibility(
            call_record=record,
            user_country=user_country,
            user_org_type=user_org_type,
            user_trl=user_trl,
            has_consortium=has_consortium,
            partner_count=partner_count,
        )

        enriched.update(eligibility_result)
        enriched["theme_coherence"] = assess_theme_coherence(project_text, record)
        enriched["match_explanation"] = build_safe_match_explanation(
            project_text,
            record,
            theme_coherence=enriched["theme_coherence"],
        )
        enriched.update(
            calculate_strategic_success_index(
                similarity_score=float(score),
                eligibility_status=eligibility_result["eligibility_status"],
                user_trl=user_trl,
                trl_min=record.get("trl_min"),
                trl_max=record.get("trl_max"),
            )
        )
        enriched["next_step_guidance"] = build_next_step_guidance(
            enriched,
            user_trl=user_trl,
            has_consortium=has_consortium,
            partner_count=partner_count,
        )
        ranked.append(enriched)

    sort_field = _normalize_sort_field(sort_by)
    ranked.sort(key=lambda x: x[sort_field], reverse=True)
    return ranked


def execute_retrieval(
    project_text: str,
    top_k: int = 5,
    user_country: str = "",
    user_org_type: str = "",
    user_trl: int | None = None,
    has_consortium: bool = False,
    partner_count: int | None = None,
    sort_by: str = "strategic_success_index",
    retrieval_mode: str = "lexical",
    allow_semantic_fallback: bool = True,
    include_expired: bool = False,
) -> Dict[str, Any]:
    records = _filter_records_by_deadline(
        fetch_call_records(),
        include_expired=include_expired,
    )

    if not project_text or not project_text.strip():
        return {
            "results": [],
            "retrieval_mode_requested": _normalize_retrieval_mode(retrieval_mode),
            "retrieval_mode_used": _normalize_retrieval_mode(retrieval_mode),
            "warning": None,
        }

    if not records:
        return {
            "results": [],
            "retrieval_mode_requested": _normalize_retrieval_mode(retrieval_mode),
            "retrieval_mode_used": _normalize_retrieval_mode(retrieval_mode),
            "warning": None,
        }

    call_texts = [build_call_text(record) for record in records]
    requested_mode = _normalize_retrieval_mode(retrieval_mode)
    effective_mode = requested_mode
    warning = None

    if requested_mode == "semantic":
        try:
            similarities = _compute_semantic_similarities(project_text, call_texts)
        except Exception as exc:
            # The fallback is intentionally broad so lexical retrieval remains usable
            # if the local semantic stack is unavailable or fails unexpectedly.
            LOGGER.warning("Semantic retrieval unavailable; using lexical fallback: %s", exc)
            if not allow_semantic_fallback:
                raise
            similarities = _compute_lexical_similarities(project_text, call_texts)
            effective_mode = "lexical"
            warning = END_USER_RETRIEVAL_FALLBACK_NOTE
    else:
        similarities = _compute_lexical_similarities(project_text, call_texts)

    ranked = _build_ranked_results(
        records=records,
        similarities=similarities,
        project_text=project_text,
        user_country=user_country,
        user_org_type=user_org_type,
        user_trl=user_trl,
        has_consortium=has_consortium,
        partner_count=partner_count,
        sort_by=sort_by,
    )

    return {
        "results": ranked[:top_k],
        "retrieval_mode_requested": requested_mode,
        "retrieval_mode_used": effective_mode,
        "warning": warning,
    }


def retrieve_matching_calls(
    project_text: str,
    top_k: int = 5,
    user_country: str = "",
    user_org_type: str = "",
    user_trl: int | None = None,
    has_consortium: bool = False,
    partner_count: int | None = None,
    sort_by: str = "strategic_success_index",
    retrieval_mode: str = "lexical",
    include_expired: bool = False,
) -> List[Dict[str, Any]]:
    execution = execute_retrieval(
        project_text=project_text,
        top_k=top_k,
        user_country=user_country,
        user_org_type=user_org_type,
        user_trl=user_trl,
        has_consortium=has_consortium,
        partner_count=partner_count,
        sort_by=sort_by,
        retrieval_mode=retrieval_mode,
        allow_semantic_fallback=False,
        include_expired=include_expired,
    )
    return execution["results"]
