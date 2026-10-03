"""
L8 — concept scoring.

Combines two signals into one COVERED/PARTIAL/MISSING verdict and a mark
factor: retrieval similarity (ai.rag.retriever, cosine against the
concept's own embedding) and the LLM's own coverage verdict (ai.coverage,
triple-pass voted). They are NOT symmetric: an LLM "covered" that
similarity doesn't corroborate is downgraded, never zeroed — the LLM read
the actual answer text, which retrieval-alone banding didn't. An LLM
"missing" is trusted outright, with no similarity override in the other
direction (see band_concept's docstring for why: live data ruled it out,
this isn't a style choice).
"""

from decimal import ROUND_HALF_UP, Decimal

from ai.config import SIMILARITY_FULL_CREDIT, SIMILARITY_PARTIAL_CREDIT, UNDERLINE_SIMILARITY_BOOST

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
    - llm=MISSING: stands, full stop — no similarity override. There used
      to be one ("a retrieval hit above some threshold overrides an LLM
      'missing' into partial credit"), on the theory that a high cosine
      similarity could catch a retrieval miss on correct-but-oddly-phrased
      prose. Live data killed that theory (2026-10-01): a genuinely
      irrelevant answer (the wrong booklet entirely) landed at 0.78-0.80
      similarity against every concept — and real, legitimately
      PARTIAL-credit answers in this same system land at 0.776-0.89. The
      two distributions overlap; there is no threshold that lets one
      through without also letting the other through. Below
      SIMILARITY_FULL_CREDIT, similarity cannot be trusted to overrule an
      LLM that actually read the text and judged it doesn't address the
      concept — so it doesn't get the chance to.
    """
    if llm_verdict == COVERED:
        if similarity >= SIMILARITY_FULL_CREDIT:
            return COVERED, FULL_FACTOR
        return PARTIAL, PARTIAL_FACTOR
    if llm_verdict == PARTIAL:
        return PARTIAL, PARTIAL_FACTOR
    return MISSING, MISSING_FACTOR


def marks_for(weight: float, max_marks: Decimal, factor: Decimal) -> Decimal:
    concept_max = Decimal(str(weight)) * max_marks
    return (concept_max * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
