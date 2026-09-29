"""
L1 — image preprocessing.

denoise -> CLAHE contrast normalisation -> deskew -> adaptive threshold,
plus a single composite `quality_score()` in [0, 1] that L4 (ai/ocr/router.py)
reads to decide how aggressively to intervene before OCR
(ai.config.OCR_QUALITY_ROUTING_THRESHOLD is what it's compared against).

Pure OpenCV/numpy — no Django, no provider calls; this layer never talks to
a model.
"""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class PreprocessResult:
    image: np.ndarray  # deskewed, denoised, CLAHE-normalised grayscale
    binary: np.ndarray  # adaptive-thresholded binary image (ink = 255)
    skew_angle: float
    quality_score: float


def to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


def _denoise(gray: np.ndarray) -> np.ndarray:
    return cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)


def _clahe(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


# estimate_skew used to take the angle straight from cv2.minAreaRect() over
# every ink pixel — cheap, but verified (2026-08-27) to badly misfire on a
# real photographed page: a phone photo's shadows, paper wrinkles and
# page-edge artifacts pull the minimum-area bounding rectangle's angle
# toward outliers that have nothing to do with the actual text's tilt.
# Confirmed concretely: a real upload whose text was genuinely upright
# (~2° off, confirmed by eye) got "corrected" to a wild ~30° rotation,
# WORSENING an already-fine photo and cascading into a segmentation/OCR
# failure downstream — a false-positive skew estimate is worse than none.
#
# This instead searches for the rotation that makes the image's own
# horizontal ink-row profile most sharply peaked — real text lines are
# genuinely horizontal at exactly one rotation, and every other rotation
# blurs row boundaries together, so that peak is a much more direct,
# outlier-resistant signal than one bounding box's angle. A coarse pass
# across the full range handles a phone photo taken at a real angle (not
# just a few degrees off a scanner bed); a fine pass around the coarse
# winner sharpens it. Standard technique (the "projection profile method"
# in OCR literature), reusing the same rotation primitive deskew() applies
# — so whatever this returns is guaranteed to be in deskew()'s own angle
# convention, not a separately-derived one that might disagree with it.
SKEW_SEARCH_RANGE_DEGREES = 45.0
SKEW_COARSE_STEP_DEGREES = 1.0
SKEW_FINE_WINDOW_DEGREES = 1.5
SKEW_FINE_STEP_DEGREES = 0.1


def _row_profile_peakiness(ink: np.ndarray, angle: float) -> float:
    h, w = ink.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(ink, matrix, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
    row_sums = rotated.sum(axis=1).astype(np.float64)
    return float(row_sums.var())


def estimate_skew(gray: np.ndarray) -> float:
    """Dominant skew angle in degrees — the rotation that makes the image's
    horizontal ink-row profile most sharply peaked (see the module comment
    above for why this replaced a minAreaRect-based estimate). Returns 0.0
    if there's too little ink to estimate reliably (a near-blank crop) — a
    bad angle from noise is worse than no correction at all.

    The search runs on a downscaled copy (max 400px on the long side) —
    projection profiles don't need full resolution, and downscaling cuts
    the per-warp cost dramatically (from ~1-3s for a full answer-sheet
    page to under 100ms)."""
    ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    if int((ink > 0).sum()) < 20:
        return 0.0

    # Downscale for speed: projection profiles are resolution-invariant.
    max_side = 400
    h, w = ink.shape[:2]
    if max(h, w) > max_side:
        scale = max_side / max(h, w)
        small_ink = cv2.resize(ink, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_NEAREST)
    else:
        small_ink = ink

    coarse_angles = np.arange(
        -SKEW_SEARCH_RANGE_DEGREES,
        SKEW_SEARCH_RANGE_DEGREES + SKEW_COARSE_STEP_DEGREES,
        SKEW_COARSE_STEP_DEGREES,
    )
    best_coarse = max(coarse_angles, key=lambda a: _row_profile_peakiness(small_ink, a))

    fine_angles = np.arange(
        best_coarse - SKEW_FINE_WINDOW_DEGREES,
        best_coarse + SKEW_FINE_WINDOW_DEGREES + SKEW_FINE_STEP_DEGREES,
        SKEW_FINE_STEP_DEGREES,
    )
    best = max(fine_angles, key=lambda a: _row_profile_peakiness(small_ink, a))
    return round(float(best), 2)


def deskew(gray: np.ndarray, angle: float) -> np.ndarray:
    if abs(angle) < 0.1:
        return gray
    h, w = gray.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, matrix, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)


def adaptive_threshold(gray: np.ndarray) -> np.ndarray:
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 10
    )


def quality_score(gray: np.ndarray) -> float:
    """Composite 0-1 score combining sharpness (Laplacian variance) and
    contrast (intensity std dev). Clamped against sane bounds for a 300dpi
    scan rather than calibrated against a labelled dataset — Phase B8's
    calibration targets are the scoring bands (ai.config.SIMILARITY_*),
    which have STS-B/graded-sheet ground truth to calibrate against; this
    metric doesn't, so a documented clamp is what's defensible here.

    A 3x3 median blur runs before the Laplacian on purpose: raw Gaussian
    sensor/compression noise is itself high-frequency, so scoring the
    UNfiltered image would rate a noisy scan as "sharp" — exactly backwards
    for a metric that exists to route noisy scans to more aggressive OCR
    preprocessing (ai.config.OCR_QUALITY_ROUTING_THRESHOLD). A 3px median
    survives real ink edges (several pixels wide after antialiasing) while
    suppressing per-pixel noise."""
    denoised = cv2.medianBlur(gray, 3)
    sharpness = cv2.Laplacian(denoised, cv2.CV_64F).var()
    contrast = float(denoised.std())

    sharpness_score = min(sharpness / 250.0, 1.0)
    contrast_score = min(contrast / 20.0, 1.0)
    return round(0.6 * sharpness_score + 0.4 * contrast_score, 4)


def preprocess(image: np.ndarray) -> PreprocessResult:
    gray = to_gray(image)
    denoised = _denoise(gray)
    normalised = _clahe(denoised)
    angle = estimate_skew(normalised)
    deskewed = deskew(normalised, angle)
    binary = adaptive_threshold(deskewed)
    return PreprocessResult(
        image=deskewed,
        binary=binary,
        skew_angle=angle,
        quality_score=quality_score(deskewed),
    )
