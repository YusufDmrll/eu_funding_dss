import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.semantic_retrieval import SEMANTIC_MODEL_NAME, load_semantic_runtime


def main() -> int:
    try:
        torch, sentence_transformers = load_semantic_runtime()

        # Import explicitly after the deterministic runtime bootstrap so this
        # script verifies the same modules a normal local session will use.
        import numpy as np
        import sentence_transformers as sentence_transformers_import
        import torch as torch_import

        print(f"Python: {sys.version.split()[0]}")
        print(f"PyTorch: {torch_import.__version__}")
        print(f"sentence-transformers: {sentence_transformers_import.__version__}")
        print(f"Model: {SEMANTIC_MODEL_NAME}")

        model = sentence_transformers.SentenceTransformer(SEMANTIC_MODEL_NAME)
        embeddings = model.encode(
            [
                "A project for recycling critical raw materials from industrial waste.",
                "An industrial process for recovering strategic materials through recycling.",
            ],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        similarity = float(np.dot(embeddings[0], embeddings[1]))

        if not np.isfinite(similarity):
            raise RuntimeError("The model returned a non-finite similarity value.")

        print(f"Example cosine similarity: {similarity:.4f}")
        print("Semantic stack check: OK")
        return 0
    except Exception as exc:
        root_cause = exc.__cause__ or exc
        print("Semantic stack check: FAILED", file=sys.stderr)
        print(f"Reason: {root_cause}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
