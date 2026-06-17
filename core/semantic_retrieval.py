from functools import lru_cache
from importlib import import_module
from typing import Any, Sequence


SEMANTIC_MODEL_NAME = "all-MiniLM-L6-v2"


class SemanticRetrievalError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def load_semantic_runtime() -> tuple[Any, Any]:
    """Load the local semantic stack in a deterministic Windows-safe order."""
    try:
        # In the supported Windows CPU environment, initializing scikit-learn's
        # compiled runtime before PyTorch prevents intermittent c10.dll failures.
        import_module("sklearn")
        torch_module = import_module("torch")
        sentence_transformers_module = import_module("sentence_transformers")
    except Exception as exc:
        raise SemanticRetrievalError(
            "The local semantic matching runtime could not be initialized."
        ) from exc

    return torch_module, sentence_transformers_module


@lru_cache(maxsize=1)
def _load_numpy_module() -> Any:
    try:
        return import_module("numpy")
    except Exception as exc:
        raise SemanticRetrievalError(
            "Numerical dependencies for semantic retrieval are not available in the current environment."
        ) from exc


@lru_cache(maxsize=1)
def _load_sentence_transformer_class():
    _, sentence_transformers_module = load_semantic_runtime()
    return sentence_transformers_module.SentenceTransformer


@lru_cache(maxsize=1)
def _load_model():
    SentenceTransformer = _load_sentence_transformer_class()
    try:
        return SentenceTransformer(SEMANTIC_MODEL_NAME)
    except Exception as exc:
        raise SemanticRetrievalError(
            "The semantic retrieval model could not be loaded."
        ) from exc


@lru_cache(maxsize=4)
def _encode_call_texts(call_texts: tuple[str, ...]) -> Any:
    # Cache embeddings against the exact call text tuple. This is a simple,
    # low-risk cache that automatically refreshes when imported call text changes.
    model = _load_model()
    return model.encode(
        list(call_texts),
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )


def compute_semantic_similarities(
    project_text: str,
    call_texts: Sequence[str],
) -> list[float]:
    if not project_text or not project_text.strip():
        return []

    np = _load_numpy_module()
    model = _load_model()
    call_embeddings = _encode_call_texts(tuple(call_texts))
    project_embedding = model.encode(
        [project_text],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )[0]

    similarities = np.matmul(call_embeddings, project_embedding)
    return similarities.tolist()
