"""VLM-first answer-page extraction.

The VLM receives one complete answer-sheet page and returns the structured
blocks needed by the evaluator. This module intentionally does not run OCR,
projection-profile segmentation, or annotation detectors. It validates the
model response and keeps all coordinates in page pixels until the caller crops
individual blocks for persistence.
"""

import json
import re
from dataclasses import dataclass, field

import cv2
import numpy as np

from ai.providers.base import VLMProvider

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
      ]
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


def _bbox(value, *, name: str, width: int, height: int) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError(f"VLM {name} must be an object")
    x = _number(value.get("x"), name=f"{name}.x", minimum=0, maximum=width)
    y = _number(value.get("y"), name=f"{name}.y", minimum=0, maximum=height)
    w = _number(value.get("w"), name=f"{name}.w", minimum=0, maximum=width)
    h = _number(value.get("h"), name=f"{name}.h", minimum=0, maximum=height)
    if w <= 0 or h <= 0:
        raise ValueError(f"VLM {name} must have positive width and height")
    if x + w > width or y + h > height:
        raise ValueError(f"VLM {name} extends outside the page")
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
        bbox=_bbox(value.get("bbox"), name="annotation.bbox", width=width, height=height),
        confidence=_number(value.get("confidence"), name="annotation.confidence", minimum=0, maximum=1),
    )


def _block(value, *, width: int, height: int) -> ExtractedBlock:
    if not isinstance(value, dict):
        raise ValueError("VLM block must be an object")
    content_type = str(value.get("content_type", "")).upper()
    if content_type not in _CONTENT_TYPES:
        raise ValueError(f"Unknown VLM content type: {content_type!r}")
    annotations = [
        _annotation(item, width=width, height=height)
        for item in value.get("annotations", [])
    ]
    if not isinstance(value.get("annotations", []), list):
        raise ValueError("VLM annotations must be a list")
    return ExtractedBlock(
        question_number=(str(value["question_number"]).strip() if value.get("question_number") is not None else None),
        bbox=_bbox(value.get("bbox"), name="block.bbox", width=width, height=height),
        content_type=content_type,
        raw_text=str(value.get("raw_text", "")),
        reconstructed_text=str(value.get("reconstructed_text", "")),
        confidence=_number(value.get("confidence"), name="block.confidence", minimum=0, maximum=1),
        annotations=annotations,
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
            blocks = [_block(value, width=width, height=height) for value in values]
            confidence = round(sum((block.confidence for block in blocks), 0.0) / len(blocks), 4) if blocks else 0.0
            return ExtractedPage(blocks=blocks, confidence=confidence)
        except ValueError as exc:
            last_error = exc
            prompt = EXTRACTION_PROMPT + f"\n\nCRITICAL: Your previous response failed to parse as valid JSON. Error: {exc}\nYou MUST return ONLY valid JSON with correctly matched braces, commas, and quotes."
            
    raise ValueError(f"VLM extraction failed after 3 attempts: {last_error}")
