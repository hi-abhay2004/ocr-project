import json

import numpy as np

from ai.ocr.vlm_extractor import extract_page
from ai.providers.mock import MockVLMProvider


def test_vlm_extractor_validates_structured_page_response():
    response = {
        "blocks": [
            {
                "question_number": "1a",
                "bbox": {"x": 100, "y": 50, "w": 300, "h": 200},
                "content_type": "TEXT",
                "raw_text": "old crossed text and final answer",
                "reconstructed_text": "final answer",
                "confidence": 0.84,
                "annotations": [
                    {
                        "kind": "STRIKE",
                        "intent": "CORRECTION",
                        "bbox": {"x": 120, "y": 80, "w": 80, "h": 20},
                        "confidence": 0.91,
                    }
                ],
            }
        ]
    }
    image = np.full((400, 600, 3), 255, dtype=np.uint8)
    provider = MockVLMProvider(response=json.dumps(response))

    result = extract_page(image, provider)

    assert provider.call_count == 1
    assert result.confidence == 0.84
    assert result.blocks[0].question_number == "1a"
    assert result.blocks[0].reconstructed_text == "final answer"
    assert result.blocks[0].annotations[0].kind == "STRIKE"


def test_vlm_extractor_clamps_out_of_bounds_coordinates():
    # A real Gemini response on a real photographed answer sheet (2026-09-29
    # live test) reported a bbox a few px past the page edge on one page and
    # a height well past it on another — both real, correct answers, just an
    # imprecise box. Clamping (not rejecting) is what let both actually
    # grade instead of failing the whole sheet after 3 wasted retries.
    response = {
        "blocks": [
            {
                "question_number": "1",
                "bbox": {"x": 0, "y": 0, "w": 601, "h": 100},
                "content_type": "TEXT",
                "raw_text": "",
                "reconstructed_text": "",
                "confidence": 0.5,
                "annotations": [],
            }
        ]
    }
    image = np.full((400, 600, 3), 255, dtype=np.uint8)

    result = extract_page(image, MockVLMProvider(response=json.dumps(response)))

    assert result.blocks[0].bbox == {"x": 0.0, "y": 0.0, "w": 600.0, "h": 100.0}


def test_vlm_extractor_widens_a_text_block_to_the_full_page_width():
    # Live finding (2026-10-01): the VLM transcribed an answer completely
    # and correctly (reconstructed_text had everything), but drew its own
    # display bbox narrower than the handwriting actually ran — cropping
    # the review screen's image to ~58% of the page width and cutting off
    # the right side of every line. Grading reads reconstructed_text, not
    # the crop, so marks were unaffected — but the crop exists so a
    # teacher can check the transcription against the real scan, and a
    # truncated one defeats that.
    response = {
        "blocks": [
            {
                "question_number": "1",
                "bbox": {"x": 50, "y": 20, "w": 350, "h": 150},
                "content_type": "TEXT",
                "raw_text": "the whole answer, including the part past x=400",
                "reconstructed_text": "the whole answer, including the part past x=400",
                "confidence": 0.9,
                "annotations": [],
            }
        ]
    }
    image = np.full((400, 600, 3), 255, dtype=np.uint8)

    result = extract_page(image, MockVLMProvider(response=json.dumps(response)))

    block = result.blocks[0]
    assert block.bbox == {"x": 0.0, "y": 20.0, "w": 600.0, "h": 150.0}


def test_vlm_extractor_widens_a_table_block_too():
    # Live finding (2026-10-01): a hand-drawn comparison table got the same
    # too-narrow treatment as prose — tables a student actually draws also
    # tend to run edge margin to edge margin.
    response = {
        "blocks": [
            {
                "question_number": "1",
                "bbox": {"x": 50, "y": 20, "w": 350, "h": 150},
                "content_type": "TABLE",
                "raw_text": "",
                "reconstructed_text": "a two-column comparison table",
                "confidence": 0.9,
                "annotations": [],
            }
        ]
    }
    image = np.full((400, 600, 3), 255, dtype=np.uint8)

    result = extract_page(image, MockVLMProvider(response=json.dumps(response)))

    assert result.blocks[0].bbox == {"x": 0.0, "y": 20.0, "w": 600.0, "h": 150.0}


def test_vlm_extractor_drops_a_malformed_annotation_but_keeps_the_block():
    # Live finding (2026-10-02): a single degenerate annotation bbox
    # (clamped to zero area — the same imprecision block bboxes have, on
    # a box that starts out much smaller) failed extraction for the WHOLE
    # page, losing every block's real, correctly-transcribed text over one
    # overlay rectangle the grading path never reads.
    response = {
        "blocks": [
            {
                "question_number": "1",
                "bbox": {"x": 0, "y": 0, "w": 600, "h": 400},
                "content_type": "TEXT",
                "raw_text": "the answer",
                "reconstructed_text": "the answer",
                "confidence": 0.9,
                "annotations": [
                    {
                        "kind": "STRIKE",
                        "intent": "CORRECTION",
                        "bbox": {"x": 600, "y": 0, "w": 0, "h": 10},  # degenerate: x at the edge, zero width
                        "confidence": 0.9,
                    }
                ],
            }
        ]
    }
    image = np.full((400, 600, 3), 255, dtype=np.uint8)

    result = extract_page(image, MockVLMProvider(response=json.dumps(response)))

    assert len(result.blocks) == 1
    assert result.blocks[0].reconstructed_text == "the answer"
    assert result.blocks[0].annotations == []


def test_vlm_extractor_accepts_width_height_as_bbox_key_aliases():
    # Live finding (2026-10-02): Gemini sent {"width": 687, "height": 822}
    # instead of the documented {"w": ..., "h": ...} for an otherwise
    # perfectly good, correctly-transcribed block — dropping it over a key
    # name would have thrown away real answer content for no real reason.
    response = {
        "blocks": [
            {
                "question_number": "3",
                "bbox": {"x": 10, "y": 20, "width": 300, "height": 150},
                "content_type": "DIAGRAM",  # not TEXT/TABLE, so width-widening doesn't confound this
                "raw_text": "real answer",
                "reconstructed_text": "real answer",
                "confidence": 0.95,
                "annotations": [],
            }
        ]
    }
    image = np.full((400, 600, 3), 255, dtype=np.uint8)

    result = extract_page(image, MockVLMProvider(response=json.dumps(response)))

    assert len(result.blocks) == 1
    assert result.blocks[0].reconstructed_text == "real answer"
    assert result.blocks[0].bbox["w"] == 300.0
    assert result.blocks[0].bbox["h"] == 150.0


def test_vlm_extractor_drops_a_malformed_block_but_keeps_the_others():
    response = {
        "blocks": [
            {
                "question_number": "1",
                "bbox": {"x": 0, "y": 0, "w": 600, "h": 100},
                "content_type": "NOT_A_REAL_TYPE",  # malformed
                "raw_text": "",
                "reconstructed_text": "bad block",
                "confidence": 0.9,
                "annotations": [],
            },
            {
                "question_number": "2",
                "bbox": {"x": 0, "y": 100, "w": 600, "h": 100},
                "content_type": "TEXT",
                "raw_text": "good answer",
                "reconstructed_text": "good answer",
                "confidence": 0.9,
                "annotations": [],
            },
        ]
    }
    image = np.full((400, 600, 3), 255, dtype=np.uint8)

    result = extract_page(image, MockVLMProvider(response=json.dumps(response)))

    assert len(result.blocks) == 1
    assert result.blocks[0].reconstructed_text == "good answer"


def test_vlm_extractor_does_not_widen_a_diagram_or_equation_block():
    for content_type in ("DIAGRAM", "EQUATION"):
        response = {
            "blocks": [
                {
                    "question_number": "1",
                    "bbox": {"x": 50, "y": 20, "w": 350, "h": 150},
                    "content_type": content_type,
                    "raw_text": "",
                    "reconstructed_text": "described content",
                    "confidence": 0.9,
                    "annotations": [],
                }
            ]
        }
        image = np.full((400, 600, 3), 255, dtype=np.uint8)

        result = extract_page(image, MockVLMProvider(response=json.dumps(response)))

        assert result.blocks[0].bbox == {"x": 50.0, "y": 20.0, "w": 350.0, "h": 150.0}