"""
L6 — retrieval.

The real, persisted index is pgvector's `<=>` operator once chunks are
written to the DB (Phase B6's apps/evaluation glue — `ai/` has no Django
imports, so that half of this boundary lives there, not here). This
module is the pure-Python side: given one concept's embedding and a
batch of already-embedded chunk candidates, return the top-k most
similar — ai.config.RETRIEVAL_TOP_K of them, highest similarity first.
"""

from ai.config import RETRIEVAL_TOP_K
from ai.rag.chunker import Chunk
from ai.rag.store import top_k


def retrieve(
    concept_embedding: list[float],
    chunk_vectors: list[tuple[Chunk, list[float]]],
    k: int = RETRIEVAL_TOP_K,
) -> list[tuple[Chunk, float]]:
    """`chunk_vectors` is `[(Chunk, embedding), ...]` — every chunk of the
    answer, already embedded once (Phase B4's ai.rag.embedder pattern,
    reused here rather than re-embedding per concept). Returns the top-k
    `(Chunk, similarity)` pairs."""
    return top_k(concept_embedding, chunk_vectors, k)
