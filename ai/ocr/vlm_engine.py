"""
L4 — VLM transcription, the escalation path when Tesseract's own
confidence is too low to trust (ai.ocr.router,
ai.config.OCR_CONFIDENCE_ESCALATION_THRESHOLD).

The VLM has no notion of a 0-1 "confidence" the way Tesseract does — it
just answers. By convention (matching ai.annotations.adjudicator's same
choice) a VLM transcription is treated as confidence 1.0: it IS the final
word for that block, nothing downstream re-checks it.

apps.evaluation.pipeline_runner uses this result's `.text` DIRECTLY as
the block's reconstructed_text when this engine ran — not
ai.reconstruct's Tesseract-word-based assembly, which is exactly what
produced the unreadable text this escalation exists to replace. That's
why the struck-through exclusion below is this module's job now, not
ai.reconstruct's: there's no separate CV-driven strike-removal pass
downstream of a VLM transcription to rely on instead.
"""

import cv2
import numpy as np

from ai.providers.base import VLMProvider

from .tesseract_engine import OCRResult

VLM = "VLM"

TRANSCRIBE_PROMPT = (
    "This is a cropped region of a handwritten exam answer. Transcribe "
    "the handwritten text exactly as written, correcting nothing. If any "
    "word or phrase has been struck through, crossed out, or scribbled "
    "over, OMIT it entirely from your transcription — it was deleted by "
    "the student, not part of the final answer. Reply with the "
    "transcription only — no commentary, no markdown."
)


def transcribe(gray: np.ndarray, vlm: VLMProvider) -> OCRResult:
    ok, buf = cv2.imencode(".png", gray)
    image_bytes = buf.tobytes() if ok else b""
    text = vlm.describe_image(image_bytes, TRANSCRIBE_PROMPT).strip()
    return OCRResult(text=text, confidence=1.0, engine=VLM)
