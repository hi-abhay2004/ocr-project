"""
Pure vector-similarity math — no Django, no pgvector import.

The actual index lives in Postgres (Concept.embedding / AnswerChunk.embedding,
both pgvector VectorFields with an ivfflat cosine index) and the retrieval
query itself runs there via `<=>` once Phase B6's retriever exists. What
belongs here is the math every caller needs on the *Python* side of that
boundary: the B3 stub evaluator's concept-similarity scoring and Phase B6's
top-k chunk retrieval both reduce to "cosine between two vectors" and "rank
candidates by it" — one implementation of each, not two that quietly drift.
"""


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors, in [-1, 1]. If both are unit
    vectors (every embedding this project produces is — see
    ai/providers/mock.py and the real providers alike) this is just their
    dot product; norms are still divided out so a non-unit vector never
    silently produces a bogus similarity."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def top_k(query: list[float], candidates: list[tuple], k: int) -> list[tuple]:
    """`candidates` is a list of `(key, vector)` pairs. Returns the top `k`
    as `(key, similarity)`, highest similarity first."""
    scored = [(key, cosine_similarity(query, vector)) for key, vector in candidates]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:k]
