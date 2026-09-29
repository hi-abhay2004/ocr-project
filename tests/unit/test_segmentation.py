"""
ai/segmentation.py (L2) — synthetic multi-block pages with a known number
of blocks, known question-number labels, and known multi-line answers, so
"did it find 3 blocks, not 7" is checked against ground truth rather than
eyeballed.
"""

import cv2

from ai.providers.mock import MockVLMProvider
from ai.segmentation import segment_page, segment_rows
from tests.unit.cv_fixtures import numbered_answer_page


def _binary(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]


def _gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def test_segment_rows_keeps_a_multiline_block_as_one_segment():
    img, layout = numbered_answer_page(
        [("1a)", ["BCNF is a normal form for relational schemas.", "It is stricter than 3NF."])]
    )
    rows = segment_rows(_binary(img))
    assert len(rows) == 1


def test_segment_rows_splits_on_a_wide_block_gap():
    img, layout = numbered_answer_page(
        [
            ("1a)", ["First answer, one line."]),
            ("1b)", ["Second answer, one line."]),
            ("2)", ["Third answer, one line."]),
        ]
    )
    rows = segment_rows(_binary(img))
    assert len(rows) == 3


def test_segment_page_reads_the_question_number_for_each_block():
    img, layout = numbered_answer_page(
        [
            ("1a)", ["BCNF is a normal form for relational schemas."]),
            ("1b)", ["A relation is in BCNF if every determinant is a superkey."]),
        ]
    )
    segments = segment_page(_binary(img))
    assert len(segments) == 2
    assert [s.question_number for s in segments] == ["1a", "1b"]
    assert all(not s.is_continuation for s in segments)


def test_segment_page_flags_an_unlabelled_block_as_a_continuation():
    img, layout = numbered_answer_page(
        [
            ("1a)", ["First page ends mid-sentence and the answer"]),
        ]
    )
    # No question number on this block at all — simulates a page that opens
    # mid-answer (the continuation of question 1a from a previous page).
    blank_top_img, _ = numbered_answer_page([("", ["continues here on the next page."])])
    segments = segment_page(_binary(blank_top_img), previous_question_number="1a")
    assert len(segments) == 1
    assert segments[0].is_continuation is True
    assert segments[0].question_number == "1a"  # carried from the previous page


def test_segment_page_bboxes_span_the_full_page_width():
    img, layout = numbered_answer_page([("1a)", ["One line answer."])])
    binary = _binary(img)
    segments = segment_page(binary)
    assert segments[0].bbox.w == binary.shape[1]
    assert segments[0].bbox.x == 0


# --- VLM escalation for real handwriting Tesseract can't read (2026-08-18) ---
# Real photographed pages routinely defeat the Tesseract-only strip read
# entirely (verified against real uploads, not just these synthetic
# fixtures) — these use the SAME "no printed number" fixture as the
# continuation test above (Tesseract genuinely finds nothing there) to
# drive the VLM escalation path deterministically.


def test_segment_page_escalates_to_the_vlm_when_tesseract_finds_no_number():
    blank_top_img, _ = numbered_answer_page([("", ["Some handwritten-style answer text."])])
    vlm = MockVLMProvider(response="2")
    segments = segment_page(_binary(blank_top_img), gray=_gray(blank_top_img), vlm=vlm)
    assert len(segments) == 1
    assert segments[0].question_number == "2"
    assert segments[0].is_continuation is False
    assert vlm.call_count == 1


def test_segment_page_does_not_call_the_vlm_when_tesseract_already_matched():
    img, _ = numbered_answer_page([("1a)", ["A clean label Tesseract reads fine on its own."])])
    vlm = MockVLMProvider(response="9")  # would be wrong if it were ever consulted
    segments = segment_page(_binary(img), gray=_gray(img), vlm=vlm)
    assert segments[0].question_number == "1a"
    assert vlm.call_count == 0


def test_segment_page_falls_back_to_carried_number_when_the_vlm_also_finds_nothing():
    blank_top_img, _ = numbered_answer_page([("", ["Continues an answer, no new label here."])])
    vlm = MockVLMProvider(response="NONE")
    segments = segment_page(
        _binary(blank_top_img),
        previous_question_number="3",
        gray=_gray(blank_top_img),
        vlm=vlm,
    )
    assert segments[0].question_number == "3"
    assert segments[0].is_continuation is True
    assert vlm.call_count == 1
