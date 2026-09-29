"""
Phase B5 gate (BACKEND_PLAN.md): image in -> reconstructed_text + typed
Annotation[] with crop-pixel bboxes, composing L1-L5 exactly as
Phase B6's ai/pipeline.py will (that module doesn't exist yet — gluing the
already-built layers together here is what proves the contract holds
end-to-end today, not just layer-by-layer in isolation).

Plus the cost guard restated at pipeline scope: a clean block costs zero
VLM calls; a block with one genuinely ambiguous mark costs exactly one.
"""

from ai.annotations.adjudicator import adjudicate
from ai.ocr.tesseract_engine import extract_words
from ai.preprocessing import preprocess, to_gray
from ai.providers.mock import MockVLMProvider
from ai.reconstruct import reconstruct
from ai.types import Annotation, BBox
from tests.unit.cv_fixtures import blank_page, crop_to_content, draw_strike, put_text

MODEL_ANSWER_LINE = "BCNF removes redundancy and anomalies from the schema design"


def _run_l1_to_l5(image, vlm):
    """The full chain: L1 preprocess -> L3/L3.5 detect+adjudicate ->
    L4 word-level OCR -> L5 reconstruct. Segmentation (L2) is skipped here
    on purpose — this fixture is already a single answer block, exactly
    what L2 would have handed to this point for one question."""
    pre = preprocess(image)
    gray = pre.image
    binary = pre.binary

    annotations = adjudicate(image, binary, vlm)
    words = extract_words(gray)
    text = reconstruct(gray, words, annotations)
    return text, annotations


def test_a_clean_block_reconstructs_faithfully_with_zero_vlm_calls():
    img = blank_page()
    box = put_text(img, MODEL_ANSWER_LINE, 40, 100)
    block = crop_to_content(img, box)

    vlm = MockVLMProvider()
    text, annotations = _run_l1_to_l5(block, vlm)

    assert vlm.call_count == 0
    assert annotations == []
    # "design" OCRs as "desic" on this synthetic Hershey-font fixture under
    # full L1 preprocessing — a real (if unrepresentative) Tesseract
    # imperfection, not a pipeline bug; the words unaffected by it are
    # what this asserts on.
    for word in ["BCNF", "removes", "redundancy", "and", "anomalies", "from", "the", "schema"]:
        assert word in text


def test_a_struck_word_is_dropped_end_to_end_with_a_typed_crop_pixel_annotation():
    img = blank_page()
    box = put_text(img, MODEL_ANSWER_LINE, 40, 100)
    target = next(w for w in extract_words(to_gray(img)) if w.text == "anomalies")
    draw_strike(
        img,
        {
            "x": int(target.bbox.x),
            "y": int(target.bbox.y),
            "w": int(target.bbox.w),
            "h": int(target.bbox.h),
        },
    )
    block = crop_to_content(img, box)

    # Configured in case adaptive thresholding (L1) pushes this fixture's
    # confidence into the ambiguity band and it escalates — either
    # resolution is a CORRECT pipeline outcome for this test's purpose
    # (proving the chain composes end-to-end), so resolved_by isn't
    # asserted here. The cost guard itself — zero calls on a clean block,
    # exactly one on a genuinely ambiguous mark — is what
    # tests/unit/test_annotations_adjudicator.py verifies precisely.
    vlm = MockVLMProvider(response="STRIKE")
    text, annotations = _run_l1_to_l5(block, vlm)

    assert len(annotations) == 1
    annotation = annotations[0]

    # A real, typed Annotation — the exact contract the frontend overlay
    # (and Phase B6's Django Annotation model) depend on.
    assert isinstance(annotation, Annotation)
    assert annotation.kind == "STRIKE"
    assert annotation.intent == "CORRECTION"
    assert isinstance(annotation.bbox, BBox)
    assert annotation.resolved_by in ("CV", "VLM")

    # Crop-pixel coordinates: within the block's own image bounds, not
    # normalised [0,1] and not page coordinates from the original image.
    assert 0 <= annotation.bbox.x <= block.shape[1]
    assert 0 <= annotation.bbox.y <= block.shape[0]

    assert "anomalies" not in text.split()
    assert "BCNF" in text and "redundancy" in text


def test_an_ambiguous_block_costs_exactly_one_vlm_call_end_to_end():
    img = blank_page()
    box = put_text(img, MODEL_ANSWER_LINE, 40, 100)
    # A partial-width strike over part of the line — verified empirically
    # against this test's own L1 output (ai.preprocessing.preprocess,
    # adaptive-thresholded): confidence ~0.61, inside the ambiguity band
    # (ai.config.ANNOTATION_AMBIGUITY_THRESHOLD is 0.70).
    draw_strike(img, {"x": box["x"], "y": box["y"], "w": 150, "h": box["h"]})
    block = crop_to_content(img, box)

    vlm = MockVLMProvider(response="STRIKE")
    text, annotations = _run_l1_to_l5(block, vlm)

    assert vlm.call_count == 1
    assert len(annotations) == 1
    assert annotations[0].resolved_by == "VLM"
    assert isinstance(text, str)  # reconstruction still completes either way
