"""
L6-L8 orchestrator.

Given one question's reconstructed answer text (ai.reconstruct, L5) and
its Concept rows (real embeddings, Phase B2/B4), runs chunking ->
retrieval -> triple-pass coverage -> scoring -> feedback -> confidence and
returns one typed result. This is what
apps.evaluation.tasks.evaluate_sheet calls per question, in place of
Phase B3's stub scoring.

`concepts` is duck-typed (needs `.id`, `.text`, `.weight`, `.embedding`)
rather than importing apps.exams.models.Concept directly — `ai/` has no
Django imports anywhere, including here.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from decimal import Decimal

from ai.confidence import band_for, composite_confidence, retrieval_agreement
from ai.config import RETRIEVAL_TOP_K, UNDERLINE_SIMILARITY_BOOST
from ai.coverage import CoverageResult, check_coverage
from ai.feedback import generate_feedback
from ai.providers.base import EmbeddingProvider, LLMProvider
from ai.rag.chunker import chunk_text
from ai.rag.retriever import retrieve
from ai.scoring import band_concept, marks_for, similarity_only_band


@dataclass
class ConceptResult:
    concept_id: int | None
    text: str
    status: str
    similarity: float
    marks: Decimal
    max_marks: Decimal
    evidence: str
    disagreed: bool
    coverage: CoverageResult = field(repr=False)


@dataclass
class QuestionResult:
    auto_marks: Decimal
    confidence: float
    band: str
    concept_results: list[ConceptResult]
    feedback: dict


# Concepts are checked concurrently, not one after another — each one is a
# real network round-trip (ai.coverage.check_coverage's own triple-pass
# vote), and there's no reason those round-trips should be serialized just
# because the for-loop that reads their results is written sequentially.
# Capped, not unbounded: check_coverage() ALREADY opens its own 3-worker
# pool per concept, so N concurrent concepts means up to 3N simultaneous
# HTTP requests — capping the outer level keeps that from overwhelming the
# provider's own rate limits and turning "faster" into "more 429s."
#
# 2, not 4: measured (2026-08-18) a real sheet hitting `openai.RateLimitError:
# 429` at the default of 4 (= 12 simultaneous requests per question at the
# instant coverage-checking starts) against a real NIM API key. Halving the
# burst to 6 simultaneous requests, combined with the provider's own retry
# budget (ai/providers/nim.py's RATE_LIMIT_MAX_RETRIES), stays well under
# NIM's per-minute limit while still parallelizing meaningfully over a fully
# sequential loop.
# With COVERAGE_PASS_COUNT=1 each concept costs exactly 1 LLM call, so
# 4 concurrent concepts = 4 simultaneous requests, well within NIM's
# 36/min rate limit. Raised from 2 (the old 3-pass multiplier is gone).
# Back to 2: free-tier NIM quota (40 req/min) gets exhausted when 4
# concepts fire simultaneously alongside VLM + embedding calls.
# 2 concurrent concepts = controlled burst, no 429s.
MAX_CONCURRENT_CONCEPTS = 2


def _prepare_concept(concept, chunk_vectors: list) -> tuple:
    """The fast, local half of scoring one concept — retrieval and
    similarity math, no network call. Split out so it can run before the
    (slow, real) coverage check without blocking on other concepts."""
    ranked = retrieve(concept.embedding, chunk_vectors, k=RETRIEVAL_TOP_K) if chunk_vectors else []
    top_chunk, raw_similarity = ranked[0] if ranked else (None, None)
    if raw_similarity is None:
        # No chunks at all to retrieve against (empty answer text) — an
        # explicit 0.0 floor, not a remapped "orthogonal" cosine value.
        # ai.rag.store.cosine_similarity's raw [-1, 1] output IS remapped
        # to [0, 1] below when there's an actual measurement, since
        # ai.scoring's thresholds (SIMILARITY_FULL_CREDIT etc) and
        # ConceptScore.similarity (a 0-100% bar in the frontend) are both
        # written for that scale — but "nothing was retrieved" isn't a
        # measurement to remap, it's the absence of one.
        similarity = 0.0
    else:
        similarity = round((raw_similarity + 1) / 2, 4)
    if top_chunk is not None and top_chunk.underlined:
        similarity = round(min(similarity * UNDERLINE_SIMILARITY_BOOST, 1.0), 4)

    retrieved_text = " ".join(chunk.text for chunk, _sim in ranked)
    return concept, similarity, retrieved_text


def evaluate_question(
    *,
    reconstructed_text: str,
    concepts: list,
    max_marks: Decimal,
    ocr_quality: float,
    llm: LLMProvider,
    embedder: EmbeddingProvider,
    underlined_spans: tuple = (),
) -> QuestionResult:
    # Deep fix: If the VLM found no blocks for this question, don't waste LLM/Embedder
    # calls checking concepts against an empty string. Short-circuit to 0 marks.
    if not reconstructed_text.strip():
        return QuestionResult(
            auto_marks=Decimal("0.0"),
            band="RED",
            confidence=1.0,  # 100% confident it's empty
            feedback={
                "strengths": "",
                "gaps": "No answer provided for this question.",
                "suggestions": "Review the relevant concepts."
            },
            concept_results=[
                ConceptResult(
                    concept_id=c["id"] if isinstance(c, dict) else c.id,
                    text=c["text"] if isinstance(c, dict) else c.text,
                    status="MISSING",
                    similarity=0.0,
                    marks=Decimal("0.0"),
                    max_marks=Decimal(
                        str(
                            round(
                                float(c["weight"] if isinstance(c, dict) else c.weight)
                                * float(max_marks),
                                2,
                            )
                        )
                    ),
                    evidence="Empty answer block.",
                    disagreed=False,
                    coverage=CoverageResult(verdict="MISSING", votes=[], agreement=1.0),
                )
                for c in concepts
            ]
        )

    chunks = chunk_text(reconstructed_text, underlined_spans)
    chunk_vectors = (
        list(zip(chunks, embedder.embed([c.text for c in chunks]), strict=True)) if chunks else []
    )

    prepared = [_prepare_concept(concept, chunk_vectors) for concept in concepts]

    if prepared:
        with ThreadPoolExecutor(max_workers=min(len(prepared), MAX_CONCURRENT_CONCEPTS)) as pool:
            coverages = list(
                pool.map(
                    lambda p: check_coverage(p[0].text, p[2], llm),
                    prepared,
                )
            )
    else:
        coverages = []

    concept_results = []
    llm_verdicts: list[str] = []
    similarity_verdicts: list[str] = []
    pass_agreements: list[float] = []

    for (concept, similarity, retrieved_text), coverage in zip(prepared, coverages, strict=True):
        status, factor = band_concept(similarity, coverage.verdict)
        marks = marks_for(concept.weight, max_marks, factor)
        concept_max = marks_for(concept.weight, max_marks, Decimal("1"))

        llm_verdicts.append(coverage.verdict)
        similarity_verdicts.append(similarity_only_band(similarity))
        pass_agreements.append(coverage.agreement)

        concept_results.append(
            ConceptResult(
                concept_id=getattr(concept, "id", None),
                text=concept.text,
                status=status,
                similarity=similarity,
                marks=marks,
                max_marks=concept_max,
                evidence=retrieved_text,
                disagreed=coverage.agreement < 1.0,
                coverage=coverage,
            )
        )

    auto_marks = sum((c.marks for c in concept_results), Decimal("0"))

    pass_agreement = (
        round(sum(pass_agreements) / len(pass_agreements), 4) if pass_agreements else 1.0
    )
    retrieval_verify = retrieval_agreement(llm_verdicts, similarity_verdicts)
    confidence = composite_confidence(ocr_quality, pass_agreement, retrieval_verify)

    feedback = generate_feedback(
        [{"text": c.text, "status": c.status} for c in concept_results], llm
    )

    return QuestionResult(
        auto_marks=auto_marks,
        confidence=confidence,
        band=band_for(confidence),
        concept_results=concept_results,
        feedback=feedback,
    )
