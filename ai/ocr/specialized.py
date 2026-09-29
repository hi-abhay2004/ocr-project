"""
L4.5 — specialized (non-text) content description.

Once ai.ocr.content_type.classify() has decided a block is a
DIAGRAM/TABLE/EQUATION rather than prose, no OCR engine touches it at all
— this asks the VLM to describe it instead, with a prompt suited to what
kind of content it is. That description becomes the block's
`reconstructed_text`, feeding into ai.reconstruct (L5) exactly like a
transcribed answer would.
"""

import cv2
import numpy as np

from ai.providers.base import VLMProvider

from .content_type import DIAGRAM, EQUATION, TABLE
from .tesseract_engine import OCRResult

VLM_SPECIALIZED = "VLM_SPECIALIZED"

_PROMPTS = {
    # An automated classifier (ai.ocr.content_type) decided this crop
    # isn't ordinary prose and routed it here instead of through normal
    # OCR — but that classifier can be wrong (verified 2026-08-26: a
    # page's own printed ruling/divider/border diluted its text-density
    # measurement enough to misroute an otherwise ordinary paragraph of
    # handwriting). Asked to blindly "describe the diagram," a vision
    # model will confabulate a plausible-sounding one rather than say
    # there isn't one — so this explicitly gives it the escape hatch of
    # transcribing real text instead, which is the actual defense against
    # that failure mode, not just a description-quality tweak.
    DIAGRAM: (
        "An automated classifier flagged this exam-answer crop as a "
        "hand-drawn diagram rather than ordinary handwritten text — but "
        "that classifier can be wrong. First check: does this crop mainly "
        "show a genuine diagram (shapes/boxes connected by lines, with "
        "labels), or is it actually just handwritten or printed prose "
        "text? If it's real prose, transcribe that text plainly instead — "
        "do not invent or guess at a diagram that isn't there. Only if it "
        "truly is a diagram, describe its structure and labels precisely "
        "enough for a grader to judge whether it matches a model answer's "
        "diagram — the shapes, their labels, and how they connect. Reply "
        "with the transcription or description only, no preamble."
    ),
    TABLE: (
        "This is a hand-drawn table from an exam answer. Transcribe its "
        "rows and columns as plain text, preserving the structure. Reply "
        "with the transcription only."
    ),
    EQUATION: (
        "This is a handwritten mathematical equation or expression from "
        "an exam answer. Transcribe it precisely using plain-text math "
        "notation. Reply with the transcription only."
    ),
}


def describe(gray: np.ndarray, content_type: str, vlm: VLMProvider) -> OCRResult:
    prompt = _PROMPTS.get(content_type, _PROMPTS[DIAGRAM])
    ok, buf = cv2.imencode(".png", gray)
    image_bytes = buf.tobytes() if ok else b""
    text = vlm.describe_image(image_bytes, prompt).strip()
    return OCRResult(text=text, confidence=1.0, engine=VLM_SPECIALIZED)
