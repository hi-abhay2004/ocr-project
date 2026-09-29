"""
L8 — concept scoring.

Combines two independent signals into one COVERED/PARTIAL/MISSING verdict
and a mark factor: retrieval similarity (ai.rag.retriever, cosine against
the concept's own embedding) and the LLM's own coverage verdict
(ai.coverage, triple-pass voted). Full credit needs BOTH signals to agree
strongly; either signal alone is enough for partial credit — a single
provider's mistake (a hallucinating LLM, or a retrieval miss on
oddly-phrased but correct prose) never zeroes out a concept outright,
it just caps the credit at half.
"""

from decimal import ROUND_HALF_UP, Decimal

from ai.config import (
    SIMILARITY_FULL_CREDIT,
    SIMILARITY_PARTIAL_CREDIT,
    UNDERLINE_SIMILARITY_BOOST,
)

COVERED = "COVERED"
PARTIAL = "PARTIAL"
MISSING = "MISSING"

FULL_FACTOR = Decimal("1")
PARTIAL_FACTOR = Decimal("0.5")
MISSING_FACTOR = Decimal("0")


def apply_underline_boost(similarity: float, underlined: bool) -> float:
    """A student's own underline is a deliberate emphasis signal — worth
    trusting a little more. Capped at 1.0; a boost past that would claim
    more confidence in a cosine similarity than the number can honestly
    carry."""
    if not underlined:
        return similarity
    return round(min(similarity * UNDERLINE_SIMILARITY_BOOST, 1.0), 4)


def similarity_only_band(similarity: float) -> str:
    """Pure-retrieval banding, with no LLM opinion involved — used both as
    a fallback (no chunks to retrieve at all) and as the independent
    signal ai.confidence's retrieval-corroboration term compares the LLM's
    verdict against."""
    if similarity >= SIMILARITY_FULL_CREDIT:
        return COVERED
    if similarity >= SIMILARITY_PARTIAL_CREDIT:
        return PARTIAL
    return MISSING


def band_concept(similarity: float, llm_verdict: str) -> tuple[str, Decimal]:
    """`llm_verdict` is COVERED/PARTIAL/MISSING (ai.coverage.CoverageResult.verdict).

    - llm=COVERED: full credit only if similarity ALSO clears
      SIMILARITY_FULL_CREDIT; otherwise partial — this is what "downgrades"
      an LLM's covered verdict that similarity doesn't corroborate,
      whether the gap is small or the similarity is very low. Never
      zeroed to MISSING outright: the LLM read the actual answer text,
      which retrieval-alone banding didn't.
    - llm=PARTIAL: always partial credit, regardless of similarity.
    - llm=MISSING: similarity gets one more chance — a retrieval hit
      above SIMILARITY_PARTIAL_CREDIT overrides an LLM "missing" into
      partial credit; below it, missing stands.
    """
    if llm_verdict == COVERED:
        if similarity >= SIMILARITY_FULL_CREDIT:
            return COVERED, FULL_FACTOR
        return PARTIAL, PARTIAL_FACTOR
    if llm_verdict == PARTIAL:
        return PARTIAL, PARTIAL_FACTOR
    # MISSING
    if similarity >= SIMILARITY_PARTIAL_CREDIT:
        return PARTIAL, PARTIAL_FACTOR
    return MISSING, MISSING_FACTOR


def marks_for(weight: float, max_marks: Decimal, factor: Decimal) -> Decimal:
    concept_max = Decimal(str(weight)) * max_marks
    return (concept_max * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
