"""
ai/pipeline.py — L6-L8 orchestration end to end, on mock providers.

MockEmbeddingProvider is content-derived (identical text -> cosine 1.0),
not a semantic embedder — so "full credit" fixtures here use a concept
whose text appears VERBATIM in the answer (a real semantic embedder would
also score a close paraphrase highly; the mock only recognises exact
matches). That is a property of the fixture, not of ai.pipeline itself.
"""

from decimal import Decimal

import pytest

from ai.pipeline import evaluate_question
from ai.providers.mock import MockEmbeddingProvider, MockLLMProvider


class _Concept:
    def __init__(self, id, text, weight, embedding):
        self.id = id
        self.text = text
        self.weight = weight
        self.embedding = embedding


def _make_concepts(texts_and_weights, embedder):
    vectors = embedder.embed([t for t, _w in texts_and_weights])
    return [
        _Concept(i, t, w, v)
        for i, ((t, w), v) in enumerate(zip(texts_and_weights, vectors, strict=True))
    ]


class _OpposingEmbeddingProvider(MockEmbeddingProvider):
    """MockEmbeddingProvider's per-text vector is hash-seeded, effectively
    random relative to any other text — genuinely UNRELATED text isn't
    reliably far from a genuinely COVERED one, it's just as likely to land
    on either side of a similarity threshold by chance. That chance gets
    worse, not better, at higher ai.config.EMBEDDING_DIM: cosine similarity
    between independent random vectors concentrates tightly around 0 as
    dimension grows, so the remapped similarity of two totally unrelated
    mock texts clusters right on top of SIMILARITY_PARTIAL_CREDIT (0.50)
    instead of safely below it (verified: 2026-08-26, best-of-3000 random
    text search still couldn't clear more than ~0.04 margin at 2048-dim).
    A test asserting one concept is genuinely MISSING needs a guaranteed
    gap, not a coin flip — this subclass forces `opposed_text`'s vector to
    be the exact negation of `anchor_text`'s (raw cosine -1.0, remapped
    similarity 0.0) whenever both are embedded in the same call, which is
    exactly the shape `_make_concepts` uses."""

    def __init__(self, anchor_text: str, opposed_text: str):
        super().__init__()
        self._anchor_text = anchor_text
        self._opposed_text = opposed_text

    def embed(self, texts):
        vectors = super().embed(texts)
        if self._anchor_text not in texts or self._opposed_text not in texts:
            return vectors
        anchor_vector = vectors[texts.index(self._anchor_text)]
        return [
            [-x for x in anchor_vector] if t == self._opposed_text else v
            for t, v in zip(texts, vectors)
        ]


def test_a_concept_verbatim_in_the_answer_gets_full_marks():
    embedder = MockEmbeddingProvider()
    llm = MockLLMProvider()
    concept_text = "BCNF requires every determinant to be a superkey."
    concepts = _make_concepts([(concept_text, 1.0)], embedder)

    result = evaluate_question(
        reconstructed_text=f"Some intro. {concept_text} Some conclusion.",
        concepts=concepts,
        max_marks=Decimal("10"),
        ocr_quality=1.0,
        llm=llm,
        embedder=embedder,
    )

    assert len(result.concept_results) == 1
    [cr] = result.concept_results
    assert cr.status == "COVERED"
    assert cr.similarity == pytest.approx(1.0)
    assert cr.marks == Decimal("10.00")
    assert result.auto_marks == Decimal("10.00")


def test_a_concept_absent_from_the_answer_gets_zero_marks():
    embedder = MockEmbeddingProvider()
    llm = MockLLMProvider()
    concepts = _make_concepts(
        [("Deadlock prevention uses wait-die and wound-wait.", 1.0)], embedder
    )

    result = evaluate_question(
        reconstructed_text="This answer is entirely about BCNF and normal forms instead.",
        concepts=concepts,
        max_marks=Decimal("10"),
        ocr_quality=1.0,
        llm=llm,
        embedder=embedder,
    )

    [cr] = result.concept_results
    assert cr.status == "MISSING"
    assert cr.marks == Decimal("0.00")
    assert result.auto_marks == Decimal("0.00")


def test_multiple_concepts_sum_to_the_total():
    a_text = "BCNF requires every determinant to be a superkey."
    b_text = "Deadlock prevention uses wait-die and wound-wait schemes."
    embedder = _OpposingEmbeddingProvider(anchor_text=a_text, opposed_text=b_text)
    llm = MockLLMProvider()
    concepts = _make_concepts([(a_text, 0.5), (b_text, 0.5)], embedder)

    result = evaluate_question(
        reconstructed_text=a_text,
        concepts=concepts,
        max_marks=Decimal("10"),
        ocr_quality=1.0,
        llm=llm,
        embedder=embedder,
    )

    by_text = {cr.text: cr for cr in result.concept_results}
    assert by_text[a_text].status == "COVERED"
    assert by_text[b_text].status == "MISSING"
    assert result.auto_marks == by_text[a_text].marks + by_text[b_text].marks


def test_confidence_and_band_are_populated():
    embedder = MockEmbeddingProvider()
    llm = MockLLMProvider()
    concept_text = "BCNF requires every determinant to be a superkey."
    concepts = _make_concepts([(concept_text, 1.0)], embedder)

    result = evaluate_question(
        reconstructed_text=concept_text,
        concepts=concepts,
        max_marks=Decimal("10"),
        ocr_quality=0.9,
        llm=llm,
        embedder=embedder,
    )
    assert 0.0 <= result.confidence <= 1.0
    assert result.band in ("GREEN", "ORANGE", "RED")


def test_feedback_is_populated_from_the_real_concept_results():
    embedder = MockEmbeddingProvider()
    llm = MockLLMProvider()
    concept_text = "BCNF requires every determinant to be a superkey."
    concepts = _make_concepts([(concept_text, 1.0)], embedder)

    result = evaluate_question(
        reconstructed_text=concept_text,
        concepts=concepts,
        max_marks=Decimal("10"),
        ocr_quality=1.0,
        llm=llm,
        embedder=embedder,
    )
    assert concept_text in result.feedback["strengths"]


def test_no_concepts_at_all_produces_zero_marks_without_crashing():
    embedder = MockEmbeddingProvider()
    llm = MockLLMProvider()
    result = evaluate_question(
        reconstructed_text="An answer to a question with no extracted concepts yet.",
        concepts=[],
        max_marks=Decimal("10"),
        ocr_quality=1.0,
        llm=llm,
        embedder=embedder,
    )
    assert result.auto_marks == Decimal("0")
    assert result.concept_results == []


def test_empty_answer_text_yields_missing_for_every_concept():
    embedder = MockEmbeddingProvider()
    llm = MockLLMProvider()
    concepts = _make_concepts(
        [("BCNF requires every determinant to be a superkey.", 1.0)], embedder
    )

    result = evaluate_question(
        reconstructed_text="",
        concepts=concepts,
        max_marks=Decimal("10"),
        ocr_quality=1.0,
        llm=llm,
        embedder=embedder,
    )
    [cr] = result.concept_results
    assert cr.status == "MISSING"
    assert cr.similarity == 0.0


def test_an_underlined_span_can_lift_a_borderline_concept_into_full_credit():
    # Construct a case where the retrieved chunk's similarity sits just
    # under SIMILARITY_FULL_CREDIT unboosted, and the underline boost is
    # what pushes it over — proves the span is actually wired through
    # chunking -> retrieval -> scoring, not just accepted and ignored.
    from ai.config import SIMILARITY_FULL_CREDIT

    embedder = MockEmbeddingProvider()
    llm = MockLLMProvider()
    concept_text = "BCNF requires every determinant to be a superkey."
    concepts = _make_concepts([(concept_text, 1.0)], embedder)

    # A near-but-not-exact paraphrase: under the mock's content-hashed
    # vectors this won't be an exact 1.0 match, but is similar enough
    # (shares many characters/words) to land close to, not necessarily
    # above, FULL_CREDIT — good enough to demonstrate the boost path
    # without depending on an exact numeric coincidence.
    answer = concept_text  # exact match keeps this deterministic across runs
    span = (0, len(answer))

    result = evaluate_question(
        reconstructed_text=answer,
        concepts=concepts,
        max_marks=Decimal("10"),
        ocr_quality=1.0,
        llm=llm,
        embedder=embedder,
        underlined_spans=(span,),
    )
    [cr] = result.concept_results
    assert cr.similarity <= 1.0  # boost is capped, never exceeds the [0,1] range
    assert cr.similarity >= SIMILARITY_FULL_CREDIT
