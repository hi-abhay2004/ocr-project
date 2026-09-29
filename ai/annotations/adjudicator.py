"""
L3.5 — annotation adjudication (VLM escalation).

Runs every L3 detector over a block, resolves overlapping candidates (the
same mark detected as more than one kind — e.g. a strike sitting close to
a word's ink center legitimately scores moderately as an underline too,
see strikethrough.py/underline.py's shared occupancy math) down to one
candidate per mark, and escalates anything still below
ai.config.ANNOTATION_AMBIGUITY_THRESHOLD to the VLM for a final call. Most
blocks never reach the VLM at all — that's deliberate (see the cost-guard
tests in tests/unit/test_annotations_adjudicator.py, which is what would
catch a regression that sent every block to the VLM).
"""

import re
from dataclasses import replace

import cv2
import numpy as np

from ai.annotations import arrows, margins, strikethrough, underline
from ai.config import ANNOTATION_AMBIGUITY_THRESHOLD
from ai.providers.base import VLMProvider
from ai.types import Annotation, BBox

VLM_PROMPT = (
    "This is a cropped region of a handwritten exam answer page. A simple "
    "line-detection algorithm flagged one candidate mark here, but it "
    "cannot tell a genuine hand-drawn mark apart from the page's own "
    "printed ruled-paper lines, a divider, or a table/box border — those "
    "produce a straight line too, just not one the student drew. Look at "
    "the actual ink: a real mark is a single deliberate pen stroke close "
    "to specific handwritten words; printed ruling is uniform, often "
    "repeats at a regular spacing down the page, and runs independently "
    "of exactly where the words sit.\n\n"
    "Reply with exactly one word:\n"
    "STRIKE - text is crossed/scratched out\n"
    "UNDERLINE - text is underlined by hand for emphasis\n"
    "ARROW - a line with an arrowhead\n"
    "MARGIN - a note written outside the main answer text\n"
    "NONE - this is printed ruled paper, a divider, a border, or "
    "otherwise not a mark the student drew"
)

_KIND_RE = re.compile(r"\b(STRIKE|UNDERLINE|ARROW|MARGIN|NONE)\b", re.IGNORECASE)

_DEFAULT_INTENT = {
    "STRIKE": "CORRECTION",
    "UNDERLINE": "EMPHASIS",
    "ARROW": "INSERTION",
    "MARGIN": "INSERTION",
}

CROP_PADDING = 10


def _iou(a: BBox, b: BBox) -> float:
    ax1, ay1, ax2, ay2 = a.x, a.y, a.x + a.w, a.y + a.h
    bx1, by1, bx2, by2 = b.x, b.y, b.x + b.w, b.y + b.h
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    intersection = iw * ih
    if intersection <= 0:
        return 0.0
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - intersection
    return intersection / union if union > 0 else 0.0


def _dedupe(candidates: list[Annotation], iou_threshold: float = 0.3) -> list[Annotation]:
    """When two detectors both fire on the same mark (their bboxes
    substantially overlap), only the higher-confidence interpretation
    survives — this is what stops a single ambiguous strike-or-underline
    from being reported as two separate annotations."""
    kept: list[Annotation] = []
    for candidate in sorted(candidates, key=lambda a: a.confidence, reverse=True):
        if any(_iou(candidate.bbox, k.bbox) >= iou_threshold for k in kept):
            continue
        kept.append(candidate)
    return kept


def detect_candidates(binary: np.ndarray) -> list[Annotation]:
    """Every L3 detector's raw output, deduplicated. `binary` is one
    block's ink=255 image."""
    all_candidates = (
        strikethrough.detect(binary)
        + underline.detect(binary)
        + arrows.detect(binary)
        + margins.detect(binary)
    )
    return _dedupe(all_candidates)


def _crop(image: np.ndarray, bbox: BBox, pad: int = CROP_PADDING) -> np.ndarray:
    x0 = max(0, int(bbox.x) - pad)
    y0 = max(0, int(bbox.y) - pad)
    x1 = min(image.shape[1], int(bbox.x + bbox.w) + pad)
    y1 = min(image.shape[0], int(bbox.y + bbox.h) + pad)
    return image[y0:y1, x0:x1]


def _ask_vlm(candidate: Annotation, image: np.ndarray, vlm: VLMProvider) -> Annotation | None:
    """Returns `None` when the VLM says this isn't a real mark at all
    (printed ruled paper, a divider, a border) — the caller drops it
    rather than forcing it into one of the four annotation kinds."""
    crop = _crop(image, candidate.bbox)
    ok, buf = cv2.imencode(".png", crop)
    image_bytes = buf.tobytes() if ok else b""

    reply = vlm.describe_image(image_bytes, VLM_PROMPT)
    match = _KIND_RE.search(reply)
    kind = match.group(1).upper() if match else candidate.kind

    if kind == "NONE":
        return None

    return replace(
        candidate,
        kind=kind,
        intent=_DEFAULT_INTENT.get(kind, candidate.intent),
        confidence=1.0,  # the VLM call IS the final word — nothing downstream re-adjudicates it
        resolved_by="VLM",
    )


def adjudicate(image: np.ndarray, binary: np.ndarray, vlm: VLMProvider) -> list[Annotation]:
    """`image` is the block's original (non-binary) crop — used only for
    the VLM call, since a binary mask throws away information a vision
    model could use that pure CV can't. Every candidate at or above
    ai.config.ANNOTATION_AMBIGUITY_THRESHOLD is returned exactly as CV
    found it (`resolved_by="CV"`, the Annotation default); anything below
    gets one VLM call and comes back `resolved_by="VLM"` — or is dropped
    entirely if the VLM decides it isn't a real mark (see `_ask_vlm`)."""
    resolved = []
    for candidate in detect_candidates(binary):
        if candidate.confidence >= ANNOTATION_AMBIGUITY_THRESHOLD:
            resolved.append(candidate)
        else:
            vlm_result = _ask_vlm(candidate, image, vlm)
            if vlm_result is not None:
                resolved.append(vlm_result)
    return resolved
