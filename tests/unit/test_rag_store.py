"""
ai/rag/store.py — pure vector math shared by the B3 stub evaluator's
concept-similarity scoring and Phase B6's top-k chunk retrieval.
"""

import pytest

from ai.rag.embedder import embed_texts
from ai.rag.store import cosine_similarity, top_k


def test_identical_vectors_are_similarity_one():
    v = [1.0, 2.0, 3.0]
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_orthogonal_vectors_are_similarity_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_opposite_vectors_are_similarity_negative_one():
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_a_zero_vector_is_similarity_zero_not_a_division_error():
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_top_k_ranks_by_similarity_highest_first():
    query = [1.0, 0.0]
    candidates = [
        ("far", [0.0, 1.0]),
        ("near", [0.9, 0.1]),
        ("exact", [1.0, 0.0]),
    ]
    ranked = top_k(query, candidates, k=2)
    assert [key for key, _ in ranked] == ["exact", "near"]


def test_top_k_respects_k():
    query = [1.0, 0.0]
    candidates = [("a", [1.0, 0.0]), ("b", [0.9, 0.1]), ("c", [0.1, 0.9])]
    assert len(top_k(query, candidates, k=1)) == 1


class _StubEmbedder:
    def __init__(self, dim: int):
        self.dim = dim

    def embed(self, texts):
        return [[0.0] * self.dim for _ in texts]


def test_embed_texts_returns_empty_for_empty_input():
    assert embed_texts([], _StubEmbedder(dim=1024)) == []


def test_embed_texts_rejects_a_wrong_dimension_vector():
    with pytest.raises(ValueError, match="dim"):
        embed_texts(["hello"], _StubEmbedder(dim=16))


def test_embed_texts_passes_through_a_correct_dimension():
    from ai.config import EMBEDDING_DIM

    vectors = embed_texts(["a", "b"], _StubEmbedder(dim=EMBEDDING_DIM))
    assert len(vectors) == 2
    assert len(vectors[0]) == EMBEDDING_DIM
