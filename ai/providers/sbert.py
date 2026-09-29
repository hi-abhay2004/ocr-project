"""
SBERT embedding fallback — local, no API key, no network. Only reached if
LLM_PROVIDER=sbert is explicitly selected; nothing else in the app requires
it.

Deliberately NOT a dependency of the base install (see pyproject.toml and
BACKEND_PLAN.md §3: the default PyPI `torch` wheel drags in ~2.5GB of CUDA
libraries on a machine with no GPU). If `sentence-transformers` isn't
installed, this raises a clear, actionable error instead of the raw
ModuleNotFoundError a bare `import` would.

STS-B calibration (Phase B8) is a comparison target for the real (NIM)
embedding model, not a code dependency of it, so this class only needs to
produce reasonable, real embeddings — the dimension is whatever the chosen
SBERT checkpoint returns, which will generally NOT equal ai.config.EMBEDDING_DIM.
Do not select this provider in the same environment as data indexed by
another provider — pgvector's fixed-width VectorField would reject the
mismatch at insert time.
"""

import os

from .base import EmbeddingProvider

DEFAULT_MODEL = "all-MiniLM-L6-v2"


def _install_hint() -> str:
    return (
        "sentence-transformers is not installed. Install the CPU-only "
        "torch wheel first (the default PyPI wheel bundles ~2.5GB of CUDA "
        "libraries this project doesn't need):\n"
        "  pip install torch --index-url https://download.pytorch.org/whl/cpu\n"
        "  pip install sentence-transformers"
    )


class SBERTEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or os.environ.get("SBERT_MODEL", DEFAULT_MODEL)
        self.call_count = 0
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise ImportError(_install_hint()) from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        vectors = self._load().encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vectors]
