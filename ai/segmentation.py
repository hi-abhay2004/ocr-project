"""
L2 — page segmentation.

Splits a preprocessed page's binary image (ai/preprocessing.py's `binary`,
ink = 255) into per-question answer blocks. `find_peaks` (scipy.signal)
locates each text LINE's row-center on the horizontal ink-projection
profile, which gives a robust estimate of the page's typical line pitch;
a gap between consecutive ink runs is then treated as a block boundary
only once it's meaningfully wider than that pitch — adaptive to
handwriting/font scale rather than a fixed pixel constant, and it's what
keeps a single multi-line answer as ONE block instead of splitting on the
gap between its own lines.

Each block's own top-left strip is OCR'd (a single, narrowly-scoped
tesseract call — this only needs to read a short "1a)"-shaped label, not
transcribe the answer, so it is NOT the L4 adaptive routing this project's
answer-text OCR goes through) to recover its question number. A block
whose top strip doesn't match a recognisable pattern is flagged
`is_continuation` so the caller can stitch it onto the previous block —
the multi-page-answer case.
"""

import re
from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks
from skimage.filters import threshold_otsu

from ai.providers.base import VLMProvider
from ai.types import BBox

QUESTION_NUMBER_RE = re.compile(r"^\W*(?:Q\.?\s*)?(\d{1,2}\s*[a-eA-E]?)[.\):]", re.IGNORECASE)

# Tesseract's whitelist-restricted single-line read targets PRINTED-style
# labels and routinely fails outright on real handwriting — verified
# (2026-08-18) against real photographed answer sheets, not just synthetic
# fixtures: every block on a real handwritten page came back unmatched, and
# a fixed-height number-strip crop isn't even a safe fallback, since a
# printed header table (name/roll-no box) at the top of a real page varies
# in height photo to photo and can occupy the entire strip. When Tesseract
# fails AND a `vlm` is supplied, the block's FULL image (not a fixed strip)
# is escalated to the VLM instead — it reads handwriting far better and can
# visually tell a printed table from the handwritten label regardless of
# exactly where that label sits. This mirrors the same escalate-on-failure
# pattern ai/annotations/adjudicator.py already uses for L3.5.
_VLM_NUMBER_PROMPT = (
    "This is a crop of one answer block from a handwritten exam page. It "
    "may include printed page furniture (e.g. a boxed 'STUDENT'S NAME / "
    "CLASS / ROLL NO' table) as well as the handwritten answer — ignore any "
    "printed table text. Find the handwritten question-number label this "
    "block starts with (e.g. '3)', '2.', 'Q1a)'). Reply with ONLY the "
    "number and letter suffix if present (e.g. '3', '2', '1a') — no "
    "punctuation, no explanation. If this block genuinely has no visible "
    "question-number label of its own (it continues a previous answer), "
    "reply exactly: NONE"
)
# Deliberately more lenient than QUESTION_NUMBER_RE: that one requires a
# trailing '.', ')' or ':' because Tesseract is reading an exact character
# strip, but the VLM was explicitly told not to add punctuation, so its
# reply is just "3" or "1a" (or the literal word "NONE", which correctly
# fails to match).
_VLM_NUMBER_RE = re.compile(r"^\W*(?:Q\.?\s*)?(\d{1,2}\s*[a-eA-E]?)\W*$", re.IGNORECASE)

MIN_LINE_HEIGHT = 3  # px; drops single-row specks from noise, not real strokes
MIN_LINE_PITCH = 20  # px; find_peaks won't treat two peaks closer than this as separate lines
PROFILE_SMOOTHING = 15  # px; merges a single line's internal peaks (ascenders/x-height/etc)
BLOCK_GAP_FACTOR = 1.6  # a gap this many times the typical line pitch starts a new block
NUMBER_STRIP_HEIGHT = 40  # px, tall enough for one line's question-number label
NUMBER_STRIP_WIDTH = 220  # px, wide enough for "12b)" but not the rest of that line
# A single-line PSM-7 read of a 2-4 character label is sensitive to exactly
# where its crop starts — a thin leading digit ("1") can be clipped or
# smeared into a misread by a shift of just a few px either way (verified:
# adaptive-thresholded real page images, not just a clean synthetic Otsu
# binary). Trying a small spread of vertical offsets and taking the first
# one that parses is cheap (a handful of extra Tesseract calls on a tiny
# crop) and far more robust than betting everything on one exact offset.
NUMBER_STRIP_TOP_PADS = (0, 3, 6, 10, -3)


@dataclass
class Segment:
    bbox: BBox
    question_number: str | None
    is_continuation: bool


def projection_profile(binary: np.ndarray) -> np.ndarray:
    """Ink-pixel count per row (binary is 0/255, ink=255)."""
    return (binary > 0).sum(axis=1).astype(float)


def _line_pitch(profile: np.ndarray) -> float:
    """Median distance between consecutive text-line centers, found via
    find_peaks on the ink profile. The profile is smoothed first — a single
    line of text has several LOCAL maxima of its own (ascenders, x-height
    transitions, gaps between letters), and find_peaks on the raw profile
    would pick those up as separate "lines" a few pixels apart instead of
    one peak per real line. Falls back to a generous default if there are
    fewer than two lines to measure a pitch from."""
    smoothed = uniform_filter1d(profile, size=PROFILE_SMOOTHING)
    peak_height = smoothed.max() * 0.15 if smoothed.max() > 0 else 0
    peaks, _ = find_peaks(smoothed, height=peak_height, distance=MIN_LINE_PITCH)
    if len(peaks) < 2:
        return 40.0
    return float(np.median(np.diff(peaks)))


def segment_rows(binary: np.ndarray) -> list[tuple[int, int]]:
    """Row (top, bottom) ranges, one per answer block."""
    profile = projection_profile(binary)
    is_ink = profile > 0

    runs: list[tuple[int, int]] = []
    start = None
    for i, ink in enumerate(is_ink):
        if ink and start is None:
            start = i
        elif not ink and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(is_ink)))
    runs = [(t, b) for t, b in runs if b - t >= MIN_LINE_HEIGHT]

    if len(runs) <= 1:
        return runs

    gaps = np.array([runs[i + 1][0] - runs[i][1] for i in range(len(runs) - 1)])
    threshold = _block_gap_threshold(gaps, profile)

    merged = [runs[0]]
    for top, bottom in runs[1:]:
        gap = top - merged[-1][1]
        if gap <= threshold:
            merged[-1] = (merged[-1][0], bottom)
        else:
            merged.append((top, bottom))
    return merged


def _block_gap_threshold(gaps: np.ndarray, profile: np.ndarray) -> float:
    """The gap size (px) above which a run-to-run gap starts a new block.

    Otsu's method — normally used to threshold pixel intensities into two
    populations — works just as well on this 1D array of run-to-run gaps:
    within-block gaps (between a block's own lines) and between-block gaps
    are two populations with genuinely different typical sizes, and Otsu
    finds the split between them without hardcoding either value. This is
    more robust than a fixed multiple of `_line_pitch()` alone — a short
    line (e.g. a question-number label) has much less ink than a full
    sentence, so peak-detection-based pitch estimation can be thrown off by
    content density; the RAW gaps between ink runs aren't.

    Falls back to `_line_pitch() * BLOCK_GAP_FACTOR` when there's only one
    gap to look at (Otsu needs a distribution to split, not a single
    value). When every gap is roughly the same size — a single multi-line
    block with no real page break at all — there is only ONE population,
    not two; with too few samples (or none at all) to trust, Otsu still
    finds *some* split down the middle even though nothing should split,
    so that case returns a threshold above every observed gap instead of
    trusting Otsu's number."""
    if len(gaps) < 2:
        return _line_pitch(profile) * BLOCK_GAP_FACTOR

    span = float(gaps.max() - gaps.min())
    typical = max(float(np.median(gaps)), 1.0)
    if span < typical:
        return float(gaps.max()) + 1.0
    return float(threshold_otsu(gaps.astype(float)))


def _read_question_number(strip_binary: np.ndarray) -> tuple[str | None, bool]:
    if strip_binary.size == 0 or strip_binary.max() == 0:
        return None, False
    # Tesseract expects dark ink on a light background; our binary
    # convention (THRESH_BINARY_INV) is the opposite — ink=255, bg=0.
    ocr_input = 255 - strip_binary
    config = "--psm 7 -c tessedit_char_whitelist=0123456789abcdeQq.)"
    text = pytesseract.image_to_string(ocr_input, config=config).strip()
    match = QUESTION_NUMBER_RE.match(text)
    if not match:
        return None, False
    return match.group(1).replace(" ", "").lower(), True


def _vlm_read_question_number(
    block_image: np.ndarray, vlm: VLMProvider
) -> tuple[str | None, bool]:
    if block_image.size == 0:
        return None, False
    ok, buf = cv2.imencode(".png", block_image)
    if not ok:
        return None, False
    reply = vlm.describe_image(buf.tobytes(), _VLM_NUMBER_PROMPT).strip()
    match = _VLM_NUMBER_RE.match(reply)
    if not match:
        return None, False
    return match.group(1).replace(" ", "").lower(), True


def segment_page(
    binary: np.ndarray,
    previous_question_number: str | None = None,
    *,
    gray: np.ndarray | None = None,
    vlm: VLMProvider | None = None,
) -> list[Segment]:
    """Segments one page's binary image into blocks, in top-to-bottom
    order. `previous_question_number` carries the last question number
    seen on the PRIOR page, so a page that opens mid-answer (no visible
    number on its first block) still links to the right question — the
    multi-page answer case.

    `gray` and `vlm` are optional and both needed together: when the
    Tesseract strip-read above fails to match a number for a block, and
    both are supplied, that block's full image is escalated to the VLM
    (see `_vlm_read_question_number`) instead of silently leaving the
    block unattributed. Omit them and behavior is unchanged — exactly
    what every existing Tesseract-only test here exercises."""
    width = binary.shape[1]
    segments = []
    carried = previous_question_number

    for top, bottom in segment_rows(binary):
        number, matched = None, False
        for pad in NUMBER_STRIP_TOP_PADS:
            strip_top = max(0, top - pad)
            strip = binary[strip_top : strip_top + NUMBER_STRIP_HEIGHT, 0:NUMBER_STRIP_WIDTH]
            number, matched = _read_question_number(strip)
            if matched:
                break
        if not matched and vlm is not None:
            source = gray if gray is not None else binary
            number, matched = _vlm_read_question_number(source[top:bottom, :], vlm)
        if matched:
            carried = number
        segments.append(
            Segment(
                bbox=BBox(x=0, y=float(top), w=float(width), h=float(bottom - top)),
                question_number=number if matched else carried,
                is_continuation=not matched,
            )
        )
    return segments
