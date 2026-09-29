"""
One batched embed call, dimension-checked.

Every caller that needs vectors — concept indexing (apps/exams/tasks.py,
Phase B4) and answer-chunk indexing (Phase B6) — goes through this instead
of calling an EmbeddingProvider directly, so the "vectors must be exactly
ai.config.EMBEDDING_DIM long" contract (ai/providers/base.py) is checked in
one place rather than re-asserted at every call site.
"""

from ai.config import EMBEDDING_DIM
from ai.providers.base import EmbeddingProvider


def embed_texts(texts: list[str], provider: EmbeddingProvider) -> list[list[float]]:
    """Embeds `texts` in a single batched provider call. Returns vectors in
    the same order as `texts`. Raises `ValueError` if a provider implementation
    returns a vector of the wrong dimension — this catches a provider swap
    (e.g. NIM's real embedding dimension differing from EMBEDDING_DIM) at the
    call site instead of at the pgvector insert."""
    if not texts:
        return []

    vectors = provider.embed(texts)
    if len(vectors) != len(texts):
        raise ValueError(f"provider returned {len(vectors)} vectors for {len(texts)} texts")
    for v in vectors:
        if len(v) != EMBEDDING_DIM:
            raise ValueError(f"provider returned a {len(v)}-dim vector, expected {EMBEDDING_DIM}")
    return vectors
