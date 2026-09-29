"""
ai/rag/retriever.py (L6) — top-k over already-embedded chunks. Thin over
ai.rag.store.top_k; this exercises it through the actual Chunk-shaped
interface ai.pipeline calls it with.
"""

from ai.config import RETRIEVAL_TOP_K
from ai.rag.chunker import Chunk
from ai.rag.retriever import retrieve


def test_retrieve_ranks_by_similarity_highest_first():
    query = [1.0, 0.0]
    chunks = [
        (Chunk("far", 0, 3), [0.0, 1.0]),
        (Chunk("near", 4, 8), [0.9, 0.1]),
        (Chunk("exact", 9, 14), [1.0, 0.0]),
    ]
    ranked = retrieve(query, chunks, k=2)
    assert [chunk.text for chunk, _sim in ranked] == ["exact", "near"]


def test_retrieve_defaults_to_the_configured_top_k():
    query = [1.0, 0.0]
    chunks = [(Chunk(str(i), i, i + 1), [1.0, 0.0]) for i in range(RETRIEVAL_TOP_K + 5)]
    assert len(retrieve(query, chunks)) == RETRIEVAL_TOP_K


def test_retrieve_on_no_chunks_returns_empty():
    assert retrieve([1.0, 0.0], []) == []
