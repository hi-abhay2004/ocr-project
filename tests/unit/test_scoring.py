"""
ai/scoring.py (L8) — table-driven over every band boundary. Pure
functions, zero mocks — per BACKEND_PLAN.md's B6 section, this is meant to
be the highest-ROI file in the suite: every one of these assertions is a
direct, unmediated check of the grading rule itself.
"""

from decimal import Decimal

import pytest

from ai.config import SIMILARITY_FULL_CREDIT, SIMILARITY_PARTIAL_CREDIT, UNDERLINE_SIMILARITY_BOOST
from ai.scoring import (
    COVERED,
    MISSING,
    PARTIAL,
    apply_underline_boost,
    band_concept,
    marks_for,
    similarity_only_band,
)

# SIMILARITY_FULL_CREDIT = 0.72, SIMILARITY_PARTIAL_CREDIT = 0.50


@pytest.mark.parametrize(
    "similarity,llm_verdict,expected_status,expected_factor",
    [
        # llm=COVERED: full credit only with similarity >= FULL_CREDIT.
        (0.90, "COVERED", COVERED, Decimal("1")),
        (SIMILARITY_FULL_CREDIT, "COVERED", COVERED, Decimal("1")),  # boundary: inclusive
        (SIMILARITY_FULL_CREDIT - 0.01, "COVERED", PARTIAL, Decimal("0.5")),  # just under
        (0.50, "COVERED", PARTIAL, Decimal("0.5")),
        (0.10, "COVERED", PARTIAL, Decimal("0.5")),  # low similarity never zeroes a COVERED verdict
        (0.0, "COVERED", PARTIAL, Decimal("0.5")),
        # llm=PARTIAL: always partial, regardless of similarity.
        (0.95, "PARTIAL", PARTIAL, Decimal("0.5")),
        (0.0, "PARTIAL", PARTIAL, Decimal("0.5")),
        # llm=MISSING: stands regardless of similarity — no override. A
        # genuinely irrelevant answer and a real PARTIAL-credit answer
        # overlap in similarity (0.78-0.89, live 2026-10-01 finding), so
        # even a near-1.0 similarity must not rescue an explicit "missing".
        (0.90, "MISSING", MISSING, Decimal("0")),
        (SIMILARITY_FULL_CREDIT, "MISSING", MISSING, Decimal("0")),
        (SIMILARITY_PARTIAL_CREDIT, "MISSING", MISSING, Decimal("0")),
        (0.99, "MISSING", MISSING, Decimal("0")),
        (0.0, "MISSING", MISSING, Decimal("0")),
    ],
)
def test_band_concept(similarity, llm_verdict, expected_status, expected_factor):
    status, factor = band_concept(similarity, llm_verdict)
    assert status == expected_status
    assert factor == expected_factor


@pytest.mark.parametrize(
    "similarity,expected",
    [
        (1.0, COVERED),
        (SIMILARITY_FULL_CREDIT, COVERED),
        (SIMILARITY_FULL_CREDIT - 0.0001, PARTIAL),
        (SIMILARITY_PARTIAL_CREDIT, PARTIAL),
        (SIMILARITY_PARTIAL_CREDIT - 0.0001, MISSING),
        (0.0, MISSING),
    ],
)
def test_similarity_only_band(similarity, expected):
    assert similarity_only_band(similarity) == expected


def test_underline_boost_multiplies_similarity():
    boosted = apply_underline_boost(0.6, underlined=True)
    assert boosted == pytest.approx(0.6 * UNDERLINE_SIMILARITY_BOOST, abs=1e-4)


def test_underline_boost_is_capped_at_one():
    assert apply_underline_boost(0.99, underlined=True) == 1.0


def test_underline_boost_is_a_noop_when_not_underlined():
    assert apply_underline_boost(0.6, underlined=False) == 0.6


def test_underline_boost_can_flip_the_band():
    # 0.66 alone is PARTIAL (< 0.72); boosted by 1.10x it clears FULL_CREDIT.
    boosted = apply_underline_boost(0.66, underlined=True)
    assert similarity_only_band(0.66) == PARTIAL
    assert similarity_only_band(boosted) == COVERED


@pytest.mark.parametrize(
    "weight,max_marks,factor,expected",
    [
        (0.5, Decimal("10"), Decimal("1"), Decimal("5.00")),
        (0.5, Decimal("10"), Decimal("0.5"), Decimal("2.50")),
        (0.5, Decimal("10"), Decimal("0"), Decimal("0.00")),
        (1 / 3, Decimal("10"), Decimal("1"), Decimal("3.33")),  # rounds half up to 2dp
    ],
)
def test_marks_for(weight, max_marks, factor, expected):
    assert marks_for(weight, max_marks, factor) == expected
