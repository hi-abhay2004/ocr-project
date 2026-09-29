"""
ai/annotations/adjudicator.py (L3.5) — dedup across detectors, and the
VLM escalation cost guard: Phase B5's whole point is that a regression
which starts sending every block to the VLM shows up here as a failing
assertion, not as a NIM bill discovered later.
"""

from ai.annotations.adjudicator import adjudicate, detect_candidates
from ai.config import ANNOTATION_AMBIGUITY_THRESHOLD
from ai.providers.mock import MockVLMProvider
from tests.unit.cv_fixtures import blank_page, crop_to_content, draw_strike, put_text, to_binary

TEXT = "redundancy and update anomalies caused by transitive dependencies"


def _clean_strike_fixture():
    # Cropped to content, like a real L2 (ai.segmentation) block — NOT the
    # full ~1200px blank-page canvas, which would badly understate how
    # much of the "row" the strike actually spans.
    img = blank_page()
    box = put_text(img, TEXT, 40, 100)
    draw_strike(img, box)
    block = crop_to_content(img, box)
    return block, to_binary(block)


def _ambiguous_fixture():
    """A strike over only part of a line — passes the length prefilter but
    lands well inside the ambiguity band (verified: confidence ~0.49,
    ai.config.ANNOTATION_AMBIGUITY_THRESHOLD is 0.70)."""
    img = blank_page()
    box = put_text(img, TEXT, 40, 100)
    draw_strike(img, {"x": box["x"], "y": box["y"], "w": 280, "h": box["h"]})
    block = crop_to_content(img, box)
    return block, to_binary(block)


def test_detect_candidates_dedupes_overlapping_kinds():
    _, binary = _clean_strike_fixture()
    candidates = detect_candidates(binary)
    # strikethrough AND underline both fire on the same mark (see their own
    # tests) — dedup must leave exactly one candidate for it.
    assert len(candidates) == 1
    assert candidates[0].kind == "STRIKE"


def test_a_confident_mark_costs_zero_vlm_calls():
    image, binary = _clean_strike_fixture()
    [candidate] = detect_candidates(binary)
    assert candidate.confidence >= ANNOTATION_AMBIGUITY_THRESHOLD  # sanity: fixture is unambiguous

    vlm = MockVLMProvider()
    results = adjudicate(image, binary, vlm)
    assert vlm.call_count == 0
    assert results[0].resolved_by == "CV"


def test_an_ambiguous_mark_costs_exactly_one_vlm_call():
    image, binary = _ambiguous_fixture()
    [candidate] = detect_candidates(binary)
    assert candidate.confidence < ANNOTATION_AMBIGUITY_THRESHOLD  # sanity: fixture IS ambiguous

    vlm = MockVLMProvider(response="STRIKE")
    results = adjudicate(image, binary, vlm)
    assert vlm.call_count == 1
    assert results[0].resolved_by == "VLM"


def test_vlm_reply_overrides_the_cv_guess_when_it_disagrees():
    image, binary = _ambiguous_fixture()
    vlm = MockVLMProvider(response="The mark appears to be an UNDERLINE, for emphasis.")
    [result] = adjudicate(image, binary, vlm)
    assert result.kind == "UNDERLINE"
    assert result.intent == "EMPHASIS"
    assert result.resolved_by == "VLM"
    assert result.confidence == 1.0


def test_vlm_reply_of_none_drops_the_candidate_entirely():
    # The VLM's escape hatch for "this is printed ruled paper/a divider/a
    # border, not a mark the student drew" (see VLM_PROMPT) — a candidate
    # it rejects this way must not survive as a spurious annotation of any
    # kind, since forcing it into one of the four real kinds is exactly
    # the bug this option exists to avoid.
    image, binary = _ambiguous_fixture()
    vlm = MockVLMProvider(response="NONE")
    results = adjudicate(image, binary, vlm)
    assert vlm.call_count == 1
    assert results == []


def test_a_page_with_no_marks_at_all_costs_zero_vlm_calls():
    img = blank_page()
    put_text(img, TEXT, 40, 100)
    binary = to_binary(img)
    vlm = MockVLMProvider()
    results = adjudicate(img, binary, vlm)
    assert results == []
    assert vlm.call_count == 0
