"""VLM-first answer-page extraction.

The VLM receives one complete answer-sheet page and returns the structured
blocks needed by the evaluator. This module intentionally does not run OCR,
projection-profile segmentation, or annotation detectors. It validates the
model response and keeps all coordinates in page pixels until the caller crops
individual blocks for persistence.
"""

import json
import logging
import re
from dataclasses import dataclass, field

import cv2
import numpy as np

from ai.providers.base import VLMProvider

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """
You are extracting a handwritten student answer sheet for automated grading.
Inspect the entire page and return ONLY valid JSON. Do not use markdown fences
or explanatory prose.

Return exactly this shape:
{
  "blocks": [
    {
      "question_number": "1a",
      "bbox": {"x": 0, "y": 0, "w": 100, "h": 100},
      "content_type": "TEXT",
      "raw_text": "text as visible, including struck text when readable",
      "reconstructed_text": "final answer text, excluding crossed-out text",
      "confidence": 0.0,
      "annotations": [
        {
          "kind": "STRIKE",
          "intent": "CORRECTION",
          "bbox": {"x": 0, "y": 0, "w": 10, "h": 10},
          "confidence": 0.0
        }
      ],
      "underlined_words": ["exact word or short phrase", "another one"]
    }
  ]
}

Rules:
- Return one block per answer/question region, in reading order.
- Coordinates are page-pixel coordinates with origin at the top-left.
- question_number may be null for an unlabeled continuation block.
- content_type must be TEXT, DIAGRAM, TABLE, or EQUATION.
- annotation kind must be STRIKE, UNDERLINE, ARROW, or MARGIN.
- annotation intent must be CORRECTION, EMPHASIS, or INSERTION.
- Use reconstructed_text for what should be graded. Omit text that is clearly
  crossed out. Preserve meaningful margin insertions in the answer.
- MANDATORY: every mark you can see on the page must appear in annotations,
  with a real bbox drawn tightly around that exact mark on the page — not
  just reflected as a change between raw_text and reconstructed_text. If you
  excluded any words from reconstructed_text because they were struck out,
  you must add a matching STRIKE annotation for each one. If you pulled any
  text in from the margin, add a matching MARGIN annotation (and an ARROW
  annotation too if a drawn arrow pointed to it). If any word anywhere on the
  page is underlined, add an UNDERLINE annotation for it even though the
  text itself doesn't change — underlines carry no text edit, so they are
  the easiest mark to silently skip; do not skip them.
- An underline or strike is a thin LINE, not a filled box — give it a small
  bbox height (a few pixels), not the height of the whole word or line it
  sits under/through. Report its real thinness; do not pad it out.
- underlined_words: list the exact word or short phrase text for every
  underline on this block, in reading order — this is in ADDITION to the
  UNDERLINE entries in annotations above, not instead of them. You are
  reading text here, not estimating a pixel position, so get this list
  right even on a block where the UNDERLINE bbox above might be rough.
  Empty list if nothing on this block is underlined.
- If the page is blank or unreadable, return {"blocks": []}.
- Confidence values must be between 0.0 and 1.0.
""".strip()


@dataclass
class ExtractedAnnotation:
    kind: str
    intent: str
    bbox: dict[str, float]
    confidence: float


@dataclass
class ExtractedBlock:
    question_number: str | None
    bbox: dict[str, float]
    content_type: str
    raw_text: str
    reconstructed_text: str
    confidence: float
    annotations: list[ExtractedAnnotation] = field(default_factory=list)
    underlined_words: list[str] = field(default_factory=list)


@dataclass
class ExtractedPage:
    blocks: list[ExtractedBlock]
    confidence: float


_CONTENT_TYPES = {"TEXT", "DIAGRAM", "TABLE", "EQUATION"}
_ANNOTATION_KINDS = {"STRIKE", "UNDERLINE", "ARROW", "MARGIN"}
_ANNOTATION_INTENTS = {"CORRECTION", "EMPHASIS", "INSERTION"}


def _parse_json(raw: str) -> dict:
    import ast
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        
    # Attempt 1: Standard json.loads
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
        
    # Attempt 2: Extract between braces and json.loads
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            value = json.loads(text[start : end + 1])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass

    # Attempt 3: ast.literal_eval for single-quoted dicts
    try:
        value = ast.literal_eval(text)
        if isinstance(value, dict):
            return value
    except (ValueError, SyntaxError):
        pass
        
    # Attempt 4: Extract between braces and ast.literal_eval
    if start >= 0 and end > start:
        try:
            value = ast.literal_eval(text[start : end + 1])
            if isinstance(value, dict):
                return value
        except (ValueError, SyntaxError):
            pass
            
    raise ValueError("VLM extraction response was not valid JSON or a Python dict")


def _number(value, *, name: str, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"VLM {name} must be numeric") from exc
    if not minimum <= number <= maximum:
        raise ValueError(f"VLM {name} must be between {minimum} and {maximum}")
    return number


def _clamped_coord(value, *, name: str, maximum: float) -> float:
    """Like `_number`, but clamps into [0, maximum] instead of rejecting —
    a VLM's own pixel estimate for a box it can plainly see is routinely
    off by a few px (a table border a hair past the margin) or occasionally
    wildly off on a diagram-heavy page (real observed case: a height
    reported well past the page's actual height). Either way, it's a
    precision error in a real answer, not a wrong answer, and rejecting the
    whole page over it wastes 3 retries for nothing. Only a genuinely
    non-numeric value (the model returning a string, null, etc.) still
    raises — that's not a precision problem, it's a shape problem the
    retry's clarified prompt can actually fix."""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"VLM {name} must be numeric") from exc
    return max(0.0, min(number, maximum))


def _bbox(
    value, *, name: str, width: int, height: int, min_size: float = 0.0
) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError(f"VLM {name} must be an object")
    # The prompt is explicit that bbox keys are "w"/"h" (EXTRACTION_PROMPT
    # spells out the exact shape), but Gemini occasionally sends
    # "width"/"height" instead — observed live (2026-10-02), and not on a
    # garbled block either: real, correctly-transcribed answer text was
    # being thrown away over this key-naming alone, which the per-block
    # drop-and-continue fix would otherwise have silently hidden as "one
    # less block" with no sign the content itself was ever fine. Falling
    # back to the longer key name costs nothing when "w"/"h" are present
    # (which stay the primary, documented key) and recovers the block
    # when they're not.
    x = _clamped_coord(value.get("x"), name=f"{name}.x", maximum=width)
    y = _clamped_coord(value.get("y"), name=f"{name}.y", maximum=height)
    w = _clamped_coord(value.get("w", value.get("width")), name=f"{name}.w", maximum=width)
    h = _clamped_coord(value.get("h", value.get("height")), name=f"{name}.h", maximum=height)
    # x/y are already clamped into [0, width]/[0, height] above, so
    # tightening w/h to fit what's left is always geometrically valid.
    w = min(w, width - x)
    h = min(h, height - y)
    # A genuine underline or strike IS a thin line, not a filled box — the
    # VLM's own pixel estimate for one routinely rounds to w/h of 0 or 1
    # (observed live, 2026-10-03: real, correctly-identified underlines
    # dropped here every time, never reaching the DB). min_size floors w/h
    # back up to a visible mark instead of rejecting a detection the model
    # already got right, the same way underline.py's own CV detector always
    # emits a fixed h=4.0 for exactly this reason. Only applied where the
    # caller says a thin mark is plausible (annotations) — a block's own
    # bbox staying genuinely zero-sized is still a real error, not this.
    if min_size > 0:
        w = max(w, min(min_size, width - x))
        h = max(h, min(min_size, height - y))
    if w <= 0 or h <= 0:
        raise ValueError(f"VLM {name} must have positive width and height")
    return {"x": x, "y": y, "w": w, "h": h}


def _annotation(value, *, width: int, height: int) -> ExtractedAnnotation:
    if not isinstance(value, dict):
        raise ValueError("VLM annotation must be an object")
    kind = str(value.get("kind", "")).upper()
    intent = str(value.get("intent", "")).upper()
    if kind not in _ANNOTATION_KINDS:
        raise ValueError(f"Unknown VLM annotation kind: {kind!r}")
    if intent not in _ANNOTATION_INTENTS:
        raise ValueError(f"Unknown VLM annotation intent: {intent!r}")
    return ExtractedAnnotation(
        kind=kind,
        intent=intent,
        bbox=_bbox(
            value.get("bbox"), name="annotation.bbox", width=width, height=height, min_size=4.0
        ),
        confidence=_number(value.get("confidence"), name="annotation.confidence", minimum=0, maximum=1),
    )


def _block(value, *, width: int, height: int) -> ExtractedBlock:
    if not isinstance(value, dict):
        raise ValueError("VLM block must be an object")
    content_type = str(value.get("content_type", "")).upper()
    if content_type not in _CONTENT_TYPES:
        raise ValueError(f"Unknown VLM content type: {content_type!r}")
    raw_annotations = value.get("annotations", [])
    if not isinstance(raw_annotations, list):
        raise ValueError("VLM annotations must be a list")
    # A malformed annotation (observed live, 2026-10-02: a degenerate
    # zero-area bbox — the same imprecision block bboxes have, except an
    # annotation's own box is small to begin with, so the SAME few-px
    # error is proportionally far more likely to clamp it to nothing) used
    # to fail the entire page — not just that one mark, every block's real
    # text and every question's real score, over one bad rectangle the
    # grading never even reads (reconstructed_text already has struck text
    # excluded by the VLM's own transcription, independent of whether the
    # annotation box describing it parsed). Drop the one bad annotation
    # instead; the overlay just shows one fewer box.
    annotations = []
    for item in raw_annotations:
        try:
            annotations.append(_annotation(item, width=width, height=height))
        except ValueError as exc:
            logger.warning("Dropping malformed VLM annotation %r: %s", item, exc)
    bbox = _bbox(value.get("bbox"), name="block.bbox", width=width, height=height)
    if content_type in ("TEXT", "TABLE"):
        # The VLM's own bbox is a visual pixel estimate, and on a real
        # photographed page it sometimes draws the box narrower than the
        # content actually extends — confirmed live (2026-10-01) for both:
        # a prose answer cropped to 58% of the page width, and a hand-drawn
        # comparison table cropped the same way, both cutting off the right
        # side of every line in the review screen. Grading was unaffected
        # either time (it reads reconstructed_text, not the crop), but the
        # crop exists so a teacher can check the transcription against the
        # actual scan, and one missing real content defeats that. Prose and
        # a table a student actually draws both tend to run edge margin to
        # edge margin; a diagram or equation more plausibly sits in just
        # part of the page, so those two are left at the VLM's own
        # estimate. The VLM's own y/h (which answer block this is,
        # vertically) stays as estimated in all cases.
        bbox = {**bbox, "x": 0.0, "w": float(width)}
    raw_underlined_words = value.get("underlined_words", [])
    if not isinstance(raw_underlined_words, list):
        raw_underlined_words = []
    underlined_words = [str(w).strip() for w in raw_underlined_words if str(w).strip()]
    return ExtractedBlock(
        question_number=(str(value["question_number"]).strip() if value.get("question_number") is not None else None),
        bbox=bbox,
        content_type=content_type,
        raw_text=str(value.get("raw_text", "")),
        reconstructed_text=str(value.get("reconstructed_text", "")),
        confidence=_number(value.get("confidence"), name="block.confidence", minimum=0, maximum=1),
        annotations=annotations,
        underlined_words=underlined_words,
    )


def extract_page(image: np.ndarray, vlm: VLMProvider) -> ExtractedPage:
    """Send one complete page to the VLM and validate its structured reply."""
    height, width = image.shape[:2]
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("Could not encode page for VLM extraction")
        
    prompt = EXTRACTION_PROMPT
    last_error = None
    
    for attempt in range(3):
        try:
            raw = vlm.describe_image(buffer.tobytes(), prompt)
            data = _parse_json(raw)
            values = data.get("blocks", [])
            if not isinstance(values, list):
                raise ValueError("VLM blocks must be a list")
            # Same reasoning as the per-annotation drop above, one level
            # up: one malformed block (a bad bbox, an unrecognised
            # content_type) used to fail every OTHER block on the page
            # too — a student's fully correct answer to question 2 lost
            # to a parsing error on question 1's block. Only re-prompt and
            # retry the whole page when NOTHING on it parsed at all; a
            # partially-bad response still keeps whatever did.
            blocks = []
            block_errors = []
            for value in values:
                try:
                    blocks.append(_block(value, width=width, height=height))
                except ValueError as exc:
                    logger.warning("Dropping malformed VLM block %r: %s", value, exc)
                    block_errors.append(str(exc))
            if not blocks and values:
                raise ValueError(f"every block on the page was malformed: {block_errors}")
            confidence = round(sum((block.confidence for block in blocks), 0.0) / len(blocks), 4) if blocks else 0.0
            return ExtractedPage(blocks=blocks, confidence=confidence)
        except ValueError as exc:
            last_error = exc
            prompt = EXTRACTION_PROMPT + f"\n\nCRITICAL: Your previous response failed to parse as valid JSON. Error: {exc}\nYou MUST return ONLY valid JSON with correctly matched braces, commas, and quotes."
            
    raise ValueError(f"VLM extraction failed after 3 attempts: {last_error}")
