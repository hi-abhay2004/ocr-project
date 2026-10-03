"""
Runs the REAL L1-L5 pipeline (ai.preprocessing / ai.segmentation /
ai.annotations / ai.ocr / ai.reconstruct) against a sheet's actually
uploaded page images, then hands each question's real reconstructed text
to the REAL L6-L8 pipeline (ai.pipeline.evaluate_question). Replaces the
canned-fixture block/text apps/evaluation/tasks.py used through Phase B6.

One page image can legitimately contain several questions' answers (or
none — a blank/mostly-blank page); one question's answer can legitimately
span several pages. This is what ties those two facts together:

  1. decode every uploaded page (image formats directly; PDF pages via
     PyMuPDF, one page image per PDF page)
  2. preprocess + segment EACH page image independently (ai.preprocessing,
     ai.segmentation) — segmentation carries the last-seen question number
     across pages, so a page that opens mid-answer still links correctly
  3. group the resulting blocks by question number, matched (loosely
     normalised) against the exam's real Question rows
  4. for each matched question: run L3-L5 per block, concatenate the
     reconstructed text across all of that question's blocks, and score it
     for real via ai.pipeline.evaluate_question
  5. a question with NO matching block at all (nothing recognisably
     written for it anywhere in the upload) still gets a real Evaluation —
     empty reconstructed text, which ai.pipeline already handles correctly
     (every concept MISSING, zero marks) — not a crash, not a silent skip
"""

import re

import cv2
import numpy as np
import pymupdf
from django.conf import settings
from django.core.files.base import ContentFile

from ai.annotations import strikethrough, underline
from ai.annotations.adjudicator import _DEFAULT_INTENT, _iou, adjudicate
from ai.config import ANNOTATION_AMBIGUITY_THRESHOLD
from ai.ocr import content_type as content_type_module
from ai.ocr import vlm_engine
from ai.ocr.router import run as run_ocr
from ai.ocr.specialized import describe as describe_specialized
from ai.ocr.tesseract_engine import extract_words
from ai.ocr.vlm_extractor import ExtractedBlock, extract_page
from ai.pipeline import evaluate_question
from ai.preprocessing import preprocess, quality_score
from ai.reconstruct import reconstruct
from ai.segmentation import segment_page
from ai.types import BBox

from .models import Annotation, AnswerBlock, ConceptScore, Evaluation, EvaluationRun

_NORMALISE_RE = re.compile(r"[^0-9a-z]")


def _normalise_number(value: str) -> str:
    return _NORMALISE_RE.sub("", (value or "").lower())


def _decode_pages(sheet_page) -> list[np.ndarray]:
    """Returns one BGR image per page. Usually a list of one — more only
    for a multi-page PDF uploaded as a single SheetPage row."""
    with sheet_page.image.open("rb") as fh:
        raw = fh.read()

    if sheet_page.image.name.lower().endswith(".pdf"):
        images = []
        doc = pymupdf.open(stream=raw, filetype="pdf")
        try:
            # The upload boundary (SheetUploadSerializer) only sees the raw
            # PDF bytes and can't know its page count without parsing it —
            # so a PDF with hundreds of pages passed that check fine. This
            # is the first place the real page count is known, and it must
            # be checked before the render loop below, not after: each
            # iteration is a real 200 DPI rasterisation, the actual
            # expensive part a malicious or oversized PDF would exploit.
            if doc.page_count > settings.MAX_UPLOAD_PAGE_COUNT:
                raise ValueError(
                    f"PDF has {doc.page_count} pages — "
                    f"the limit is {settings.MAX_UPLOAD_PAGE_COUNT}."
                )
            for page in doc:
                pix = page.get_pixmap(dpi=200)
                arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height, pix.width, pix.n
                )
                if pix.n == 4:
                    arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
                elif pix.n == 1:
                    arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
                images.append(np.ascontiguousarray(arr))
        finally:
            doc.close()
        return images

    arr = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise ValueError(f"Could not decode uploaded page image: {sheet_page.image.name}")
    return [arr]


def _segment_sheet(sheet, vlm) -> dict:
    """Returns {normalised_question_number: [(gray_page, binary_page, Segment), ...]},
    in reading order (page index, then top-to-bottom within a page).

    `vlm` is passed straight through to ai.segmentation.segment_page — real
    handwritten pages routinely defeat the Tesseract-only number read (see
    that module's docstring), and without a VLM fallback here, every block
    on such a page comes back with question_number=None and never matches
    any real question, silently scoring a genuinely-written answer as
    blank."""
    grouped: dict[str, list] = {}
    carried_number = None

    for sheet_page in sheet.pages.order_by("index"):
        for page_image in _decode_pages(sheet_page):
            pre = preprocess(page_image)
            segments = segment_page(
                pre.binary, previous_question_number=carried_number, gray=pre.image, vlm=vlm
            )
            for segment in segments:
                carried_number = segment.question_number
                key = _normalise_number(segment.question_number)
                grouped.setdefault(key, []).append((pre.image, pre.binary, segment))

    return grouped


def _crop(image: np.ndarray, bbox) -> np.ndarray:
    x0, y0 = max(0, int(bbox.x)), max(0, int(bbox.y))
    x1 = min(image.shape[1], int(bbox.x + bbox.w))
    y1 = min(image.shape[0], int(bbox.y + bbox.h))
    return image[y0:y1, x0:x1]


STRIKE_MASK_X_PAD = 4
# Covers the struck word's own ascenders/descenders, not just the thin
# geometric strike line itself (ai.annotations.strikethrough draws that
# line ~4px tall at the mark's own midpoint) — an unpadded mask would hide
# the drawn line but leave the actual struck letters fully visible above
# and below it.
STRIKE_MASK_Y_PAD = 20


def _mask_struck_regions(gray: np.ndarray, annotations: list[Annotation]) -> np.ndarray:
    """Paints over STRIKE-annotated regions with background fill before
    OCR, so struck-out text can never be read by ANY OCR engine.
    Deliberately not left to the VLM's own prompt instruction alone
    (ai.ocr.vlm_engine.TRANSCRIBE_PROMPT already asks it to omit struck
    text) — verified 2026-08-27 against a real upload that the VLM does
    not always comply even when explicitly told to, so removing the ink
    before it's ever seen is the more reliable guarantee."""
    strikes = [a for a in annotations if a.kind == "STRIKE"]
    if not strikes:
        return gray
    masked = gray.copy()
    height, width = masked.shape[:2]
    for a in strikes:
        x0 = max(0, int(a.bbox.x) - STRIKE_MASK_X_PAD)
        y0 = max(0, int(a.bbox.y) - STRIKE_MASK_Y_PAD)
        x1 = min(width, int(a.bbox.x + a.bbox.w) + STRIKE_MASK_X_PAD)
        y1 = min(height, int(a.bbox.y + a.bbox.h) + STRIKE_MASK_Y_PAD)
        masked[y0:y1, x0:x1] = 255
    return masked


def _process_block(block_gray: np.ndarray, block_binary: np.ndarray, vlm) -> dict:
    annotations = adjudicate(block_gray, block_binary, vlm)
    kind = content_type_module.classify(block_binary)
    quality = quality_score(block_gray)

    if kind == content_type_module.TEXT:
        ocr_input = _mask_struck_regions(block_gray, annotations)
        ocr_result = run_ocr(ocr_input, vlm)
        if ocr_result.engine == vlm_engine.VLM:
            # ai.reconstruct's word-drop-and-stitch logic depends on
            # Tesseract's own per-word bboxes (ai.ocr.tesseract_engine.
            # extract_words) — exactly the source that just produced text
            # unreliable enough to escalate in the first place. Falling
            # back to it here would silently throw away the VLM's good
            # transcription and re-derive the same bad Tesseract read.
            # Struck text is already masked out of ocr_input above, so
            # the VLM's answer IS the reconstructed text directly.
            reconstructed_text = ocr_result.text
        else:
            words = extract_words(ocr_input)
            # block_gray, not ocr_input: reconstruct()'s `image` param is
            # only used to separately OCR each MARGIN note's own crop,
            # which strike-masking never touches — no reason to hand it
            # the masked version.
            reconstructed_text = reconstruct(block_gray, words, annotations)
        raw_text = ocr_result.text
        engine = ocr_result.engine
    else:
        ocr_result = describe_specialized(block_gray, kind, vlm)
        reconstructed_text = ocr_result.text
        raw_text = ""
        engine = ocr_result.engine

    return {
        "annotations": annotations,
        "content_type": kind,
        "ocr_engine": engine,
        "raw_text": raw_text,
        "reconstructed_text": reconstructed_text,
        "quality_score": quality,
        "image": block_gray,
    }


def _normalise_word(text: str) -> str:
    return _NORMALISE_RE.sub("", text.lower())


# A fraction bar is geometrically IDENTICAL to a real underline (ink
# above, blank below) to underline.py's own detector, by construction —
# not a threshold-tuning problem. Live-verified (2026-10-06): Gemini
# transcribes a handwritten fraction as literal LaTeX (e.g.
# "\frac{TP}{(TP + FP)}"), which is a clean, deterministic signal that
# this block's own fraction bars would otherwise score as confident
# (0.7-0.9) false-positive underlines. "x / (y + z)"-shaped plain-text
# fractions are covered too, in case a future prompt change stops asking
# for LaTeX.
_MATH_NOTATION_RE = re.compile(r"\\frac|\\sum|\\int|[A-Za-z0-9]\s*/\s*\(")


def _looks_like_math_notation(raw_text: str) -> bool:
    return bool(_MATH_NOTATION_RE.search(raw_text))


def _word_text_above(words: list, line_bbox) -> str:
    """The text of whichever OCR'd word(s) sit just above this candidate
    underline and overlap it horizontally — this candidate's best guess at
    which word it's under. `words` are Tesseract's own word-level bboxes
    (ai.ocr.tesseract_engine.extract_words), crop-local, same coordinate
    space as `line_bbox` (both measured against the same preprocessed
    crop)."""
    line_x0, line_x1 = line_bbox.x, line_bbox.x + line_bbox.w
    above = []
    for w in words:
        word_bottom = w.bbox.y + w.bbox.h
        gap = line_bbox.y - word_bottom
        if not (0 <= gap <= WORD_ABOVE_LINE_MAX_GAP):
            continue
        word_x0, word_x1 = w.bbox.x, w.bbox.x + w.bbox.w
        overlap = min(line_x1, word_x1) - max(line_x0, word_x0)
        shorter_span = min(line_x1 - line_x0, word_x1 - word_x0)
        if shorter_span > 0 and overlap / shorter_span >= WORD_X_OVERLAP_MIN_FRACTION:
            above.append(w)
    above.sort(key=lambda w: w.bbox.x)
    return " ".join(w.text for w in above)


def _matches_any_underlined_word(word_text: str, underlined_words: list[str]) -> bool:
    normalised = _normalise_word(word_text)
    if not normalised:
        return False
    return any(
        (target := _normalise_word(w)) and (target in normalised or normalised in target)
        for w in underlined_words
    )


WORD_ABOVE_LINE_MAX_GAP = 20  # px
WORD_X_OVERLAP_MIN_FRACTION = 0.4


def _cv_assist_annotations(
    crop: np.ndarray, existing: list, underlined_words: list[str], raw_text: str
) -> list:
    """Fills the gap between what Gemini's single extraction call actually
    populates and what it's supposed to: live testing (2026-10-03) showed
    it reliably edits reconstructed_text correctly (excluding struck words,
    stitching in margin insertions) while leaving `annotations` empty even
    when the prompt says to report one for every such edit — the model
    does the judgment call but skips the separate structured bookkeeping.
    The result: a correctly-graded answer with nothing drawn on the image.

    This runs ai.annotations.underline.detect directly against this
    block's own crop, geometry only, no VLM call: Gemini already got the
    TEXT right, so there's nothing here that risks a wrong grade — only
    whether a box gets drawn.

    Kept to UNDERLINE only (live-verified 2026-10-04): underline is clean
    here (ink-above/blank-below is an unambiguous shape), and it's also
    the one kind VLM-first structurally can't recover on its own — a real
    underline's near-zero-height bbox is exactly what the model tends to
    report badly. STRIKE/ARROW/MARGIN stayed noisy enough in the same test
    (ruled lines mid-paragraph still read as strikes; arrows.py's
    ink-asymmetry check still fires on ordinary cursive joins) that a
    wrong box would mislead a teacher more than a missing one would — so
    those stay VLM-reported only until that noise is addressed separately.

    Two confidence tiers (live-verified 2026-10-05: CV's own recall on a
    full block missed most of several real underlines a block genuinely
    had — only the clearest one cleared ANNOTATION_AMBIGUITY_THRESHOLD on
    its own):
    - At or above ANNOTATION_AMBIGUITY_THRESHOLD: accepted outright, same
      as before.
    - Below that, down to underline.py's own noise floor: accepted ONLY
      if `underlined_words` (EXTRACTION_PROMPT's new field — Gemini's own
      plain-text read of which words are underlined, not a pixel guess)
      names the word sitting just above that candidate line. Gemini is
      asked to read text here, which it's reliably good at, rather than
      estimate a coordinate, which it isn't — this corroboration lets a
      marginal CV candidate through specifically when an independent,
      different-modality signal agrees a mark belongs roughly there,
      without just lowering the confidence bar for everyone and
      reinstating false positives on ordinary ruled paper.

    Returns the FULL replacement annotations list for this block, not just
    additions — when Gemini DOES report its own underline bbox directly
    (it sometimes does, separately from underlined_words), its pixel
    coordinates are frequently visibly offset from the real word even
    though the model correctly identified that one exists. CV's own
    geometry comes from Hough line detection directly against the ink, so
    it doesn't have that imprecision. When both agree a mark is roughly in
    the same place, CV's box REPLACES Gemini's rather than being dropped
    by it — the one case where CV is trusted over Gemini's own report,
    because here CV is demonstrably the more accurate source of geometry,
    not just a fallback for when Gemini stays silent.

    Before any of that: corrects Gemini's own STRIKE/UNDERLINE kind label
    when CV's geometry confidently disagrees (live-verified 2026-10-06:
    one real page came back with 5 genuine underlines, all correctly
    detected as marks, but mislabeled STRIKE instead of UNDERLINE in
    Gemini's own JSON — a semantic mix-up, not a geometry one, since the
    bbox position was fine). underline.py and strikethrough.py are the
    same measurement pointed at opposite shapes (ink-above-only vs
    ink-both-sides) — for a position Gemini ALREADY flagged as one of
    these two kinds, running both against it and trusting whichever
    measures higher doesn't require reading any text (unlike the
    underlined_words corroboration above, which needs Tesseract word
    positions and doesn't work reliably on real handwriting — see that
    tier's own history). This only ever RELABELS a mark Gemini already
    reported; it never adds a new STRIKE from nothing, so it doesn't
    reopen strikethrough.py's own false-positive risk on ordinary ruled
    paper (why STRIKE was kept out of the rescue tier above).

    Skipped entirely — returns `existing` untouched — when this block's
    own transcription looks like it contains a fraction/formula (see
    _looks_like_math_notation): a handwritten fraction bar is ink-above,
    blank-below over its numerator exactly like a real underline is, so
    underline.py scores one with genuine, non-marginal confidence
    (observed live, 2026-10-06: 0.84 and 0.88 on two fraction bars in a
    precision/recall formula block) — not a case the confidence tiers
    above can tell apart from a real mark, since geometrically there is
    no difference to measure.
    """
    if _looks_like_math_notation(raw_text):
        return existing
    pre = preprocess(crop)
    underline_candidates = underline.detect(pre.binary)
    strike_candidates = strikethrough.detect(pre.binary)

    def _best_match(bbox, candidates):
        matches = [c.confidence for c in candidates if _iou(bbox, c.bbox) >= 0.3]
        return max(matches, default=0.0)

    corrected_existing = []
    for e in existing:
        if e.kind not in ("STRIKE", "UNDERLINE"):
            corrected_existing.append(e)
            continue
        same_candidates = strike_candidates if e.kind == "STRIKE" else underline_candidates
        other_kind = "UNDERLINE" if e.kind == "STRIKE" else "STRIKE"
        other_candidates = underline_candidates if e.kind == "STRIKE" else strike_candidates
        same_conf = _best_match(e.bbox, same_candidates)
        other_conf = _best_match(e.bbox, other_candidates)
        if other_conf > same_conf and other_conf >= ANNOTATION_AMBIGUITY_THRESHOLD:
            # Mutated in place rather than via dataclasses.replace(): `e`
            # here is the Django model Annotation (apps/evaluation/models.py),
            # not ai.types.Annotation — a transient carrier never saved
            # until _save_block persists it, so direct mutation is safe.
            e.kind = other_kind
            e.intent = _DEFAULT_INTENT[other_kind]
            e.resolved_by = "CV"
        corrected_existing.append(e)

    accepted = [a for a in underline_candidates if a.confidence >= ANNOTATION_AMBIGUITY_THRESHOLD]
    if underlined_words:
        marginal = [a for a in underline_candidates if a.confidence < ANNOTATION_AMBIGUITY_THRESHOLD]
        if marginal:
            words = extract_words(pre.image)
            for candidate in marginal:
                word_text = _word_text_above(words, candidate.bbox)
                if _matches_any_underlined_word(word_text, underlined_words):
                    accepted.append(candidate)
    kept_existing = [
        e
        for e in corrected_existing
        if not (e.kind == "UNDERLINE" and any(_iou(e.bbox, c.bbox) >= 0.3 for c in accepted))
    ]
    return kept_existing + accepted


def _crop_page_block(image: np.ndarray, block: ExtractedBlock) -> dict:
    """Convert one VLM page-coordinate block into the persistence shape.

    The VLM describes annotations in page coordinates. The review overlay
    contract requires crop-local coordinates, so this is the only coordinate
    conversion in the VLM-first path.
    """
    x0 = max(0, int(block.bbox["x"]))
    y0 = max(0, int(block.bbox["y"]))
    x1 = min(image.shape[1], int(block.bbox["x"] + block.bbox["w"]))
    y1 = min(image.shape[0], int(block.bbox["y"] + block.bbox["h"]))
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        raise ValueError("VLM returned an empty answer block crop")

    annotations = []
    for annotation in block.annotations:
        bbox = annotation.bbox
        annotations.append(
            Annotation(
                kind=annotation.kind,
                intent=annotation.intent,
                bbox=BBox(
                    x=bbox["x"] - x0,
                    y=bbox["y"] - y0,
                    w=bbox["w"],
                    h=bbox["h"],
                ),
                confidence=annotation.confidence,
                resolved_by="VLM",
            )
        )

    if block.content_type == "TEXT":
        annotations = _cv_assist_annotations(
            crop, annotations, block.underlined_words, block.raw_text
        )

    return {
        "annotations": annotations,
        "content_type": block.content_type,
        "ocr_engine": "VLM" if block.content_type == "TEXT" else "VLM_SPECIALIZED",
        "raw_text": block.raw_text,
        "reconstructed_text": block.reconstructed_text,
        "quality_score": block.confidence,
        "image": crop,
    }


def _full_page_blocks(image: np.ndarray, blocks: list[ExtractedBlock]) -> dict:
    """Keep the original page when VLM block geometry is clearly unreliable.

    Some vision responses identify the answer text correctly but return tiny,
    repeated placeholder boxes. Cropping those boxes makes the review UI show
    magnified fragments instead of the uploaded paper. A full-page fallback
    preserves the source image and keeps annotations in the page/crop space
    required by the overlay.
    """
    annotations = []
    for block in blocks:
        for annotation in block.annotations:
            bbox = annotation.bbox
            annotations.append(
                Annotation(
                    kind=annotation.kind,
                    intent=annotation.intent,
                    bbox=BBox(
                        x=bbox["x"],
                        y=bbox["y"],
                        w=bbox["w"],
                        h=bbox["h"],
                    ),
                    confidence=annotation.confidence,
                    resolved_by="VLM",
                )
            )
    text = " ".join(block.reconstructed_text for block in blocks).strip()
    raw_text = " ".join(block.raw_text for block in blocks).strip()
    confidence = (
        sum(block.confidence for block in blocks) / len(blocks) if blocks else 0.0
    )
    return {
        "annotations": annotations,
        "content_type": "TEXT" if all(block.content_type == "TEXT" for block in blocks) else "DIAGRAM",
        "ocr_engine": "VLM",
        "raw_text": raw_text,
        "reconstructed_text": text,
        "quality_score": confidence,
        "image": image,
    }


def _merge_text_blocks(blocks: list[ExtractedBlock], max_bottom: float) -> ExtractedBlock:
    """Collapses several same-question TEXT blocks from one page into one.

    Gemini's "one block per answer/question region" instruction
    (EXTRACTION_PROMPT) isn't always followed — observed live (2026-10-04):
    one short, continuous handwritten paragraph came back as 6 separate
    blocks, each only a couple of lines tall, with the same question
    number. Left as 6 blocks, the review screen renders 6 separate thin
    image strips stacked on top of each other instead of one answer — "why
    is my image shredded" is the direct, correct reading of that.

    The crop's LEFT/TOP/RIGHT edges come from the union of these blocks'
    own bboxes (trustworthy — a block's own top-left corner is where
    Gemini actually drew it). The BOTTOM edge deliberately does NOT: it
    uses `max_bottom` (the caller's choice — see _vlm_page_blocks, which
    passes the next question's own top on this page, or the page's bottom
    edge if there is none) instead of these blocks' own union height.
    Live-verified (2026-10-04) that this matters even with NO overlap
    between blocks: Gemini transcribed a 6-line answer's text completely
    correctly, but the trailing block's own reported height undershot how
    much of the page it actually covered — a plain union still came out
    too short and the saved crop silently stopped partway through the
    real answer. A second identical extraction call on the same image
    moments later produced different, correct bboxes for the same text —
    confirming this is Gemini's own per-call non-determinism, not a
    one-off, so nothing about an individual block's own claimed height can
    safely be trusted as this crop's lower bound. Extending to the next
    independently-known boundary instead costs a slightly taller crop
    (some blank trailing space is normal) in exchange for never truncating
    real content — the safer trade given the alternative is silently
    grading text the teacher can't actually see or verify.

    Annotation bboxes need no adjustment here — they're still in page
    coordinates at this point (_crop_page_block does the only
    page->crop conversion, after this).
    """
    ordered = sorted(blocks, key=lambda b: b.bbox["y"])
    x0 = min(b.bbox["x"] for b in ordered)
    y0 = min(b.bbox["y"] for b in ordered)
    x1 = max(b.bbox["x"] + b.bbox["w"] for b in ordered)
    return ExtractedBlock(
        question_number=ordered[0].question_number,
        bbox={"x": x0, "y": y0, "w": x1 - x0, "h": max_bottom - y0},
        content_type="TEXT",
        raw_text=" ".join(b.raw_text for b in ordered if b.raw_text).strip(),
        reconstructed_text=" ".join(b.reconstructed_text for b in ordered if b.reconstructed_text).strip(),
        confidence=sum(b.confidence for b in ordered) / len(ordered),
        annotations=[a for b in ordered for a in b.annotations],
        underlined_words=[w for b in ordered for w in b.underlined_words],
    )


def _vlm_geometry_is_suspicious(image: np.ndarray, blocks: list[ExtractedBlock]) -> bool:
    if not blocks:
        return False
    page_area = image.shape[0] * image.shape[1]
    return all(
        block.bbox["w"] * block.bbox["h"] < page_area * 0.02
        for block in blocks
    )


def _vlm_page_blocks(sheet, questions: list, vlm) -> dict:
    """Extract all pages directly through the VLM and group blocks by question."""
    grouped: dict[str, list] = {}
    carried_number = None
    for sheet_page in sheet.pages.order_by("index"):
        for page_image in _decode_pages(sheet_page):
            extracted = extract_page(page_image, vlm)
            if _vlm_geometry_is_suspicious(page_image, extracted.blocks):
                by_question: dict[str, list[ExtractedBlock]] = {}
                if len(questions) == 1:
                    by_question[_normalise_number(questions[0].number)] = extracted.blocks
                else:
                    for block in extracted.blocks:
                        question_number = block.question_number or carried_number
                        if block.question_number:
                            carried_number = block.question_number
                        key = _normalise_number(question_number)
                        by_question.setdefault(key, []).append(block)
                if not by_question and questions:
                    by_question[_normalise_number(questions[0].number)] = []
                for key, blocks in by_question.items():
                    grouped.setdefault(key, []).append(_full_page_blocks(page_image, blocks))
                continue
            # Resolve each block's question key first, in page order, THEN
            # merge same-question TEXT blocks on this page into one (see
            # _merge_text_blocks) — merging needs the resolved key to know
            # which blocks actually belong together, so it can't happen
            # before carried_number resolution above.
            page_groups: dict[str, list[ExtractedBlock]] = {}
            page_order: list[str] = []
            for block in extracted.blocks:
                question_number = block.question_number or carried_number
                if block.question_number:
                    carried_number = block.question_number
                key = _normalise_number(question_number)
                page_groups.setdefault(key, []).append(block)
                if key not in page_order:
                    page_order.append(key)

            page_height = page_image.shape[0]
            for key in page_order:
                blocks_for_key = page_groups[key]
                text_blocks = [b for b in blocks_for_key if b.content_type == "TEXT"]
                to_crop = [b for b in blocks_for_key if b.content_type != "TEXT"]
                if len(text_blocks) > 1:
                    # Cap how far down the merged crop can extend at
                    # wherever the NEXT question's own content starts on
                    # this page (or the page bottom, if this is the last
                    # one) — not at the union of these blocks' own
                    # reported heights. See _merge_text_blocks's docstring
                    # for why an individual block's own height can't be
                    # trusted as this crop's lower bound.
                    own_top = min(b.bbox["y"] for b in text_blocks)
                    other_tops = [
                        min(b.bbox["y"] for b in other_blocks)
                        for other_key, other_blocks in page_groups.items()
                        if other_key != key
                    ]
                    later_tops = [top for top in other_tops if top > own_top]
                    max_bottom = min(page_height, *later_tops) if later_tops else page_height
                    to_crop.append(_merge_text_blocks(text_blocks, max_bottom))
                else:
                    to_crop.extend(text_blocks)
                to_crop.sort(key=lambda b: b.bbox["y"])  # original reading order
                for block in to_crop:
                    grouped.setdefault(key, []).append(_crop_page_block(page_image, block))
    return grouped


def _save_block(evaluation: Evaluation, processed: dict) -> None:
    block = AnswerBlock(
        evaluation=evaluation,
        image_width=processed["image"].shape[1],
        image_height=processed["image"].shape[0],
        quality_score=processed["quality_score"],
        content_type=processed["content_type"],
        ocr_engine=processed["ocr_engine"],
        raw_text=processed["raw_text"],
        reconstructed_text=processed["reconstructed_text"],
    )
    ok, buf = cv2.imencode(".png", processed["image"])
    block.crop_image.save("block.png", ContentFile(buf.tobytes() if ok else b""), save=False)
    block.save()

    Annotation.objects.bulk_create(
        Annotation(
            block=block,
            kind=a.kind,
            intent=a.intent,
            bbox={"x": a.bbox.x, "y": a.bbox.y, "w": a.bbox.w, "h": a.bbox.h},
            confidence=a.confidence,
            resolved_by=a.resolved_by,
        )
        for a in processed["annotations"]
    )


def create_real_evaluations(sheet, questions: list, embedder, llm, vlm) -> None:
    """The real replacement for the old fixture-based `_create_evaluations`.
    Same call-site contract: idempotent on retry (clears prior evaluations
    for this sheet first), creates exactly one Evaluation per question."""
    sheet.evaluations.all().delete()

    grouped = (
        _vlm_page_blocks(sheet, questions, vlm)
        if settings.VLM_FIRST_EXTRACTION
        else _segment_sheet(sheet, vlm)
    )

    # A single-question exam has no real ambiguity about which question
    # ANY segmented content belongs to — regardless of what (if anything)
    # the number-reader in ai.segmentation produced for it. Originally
    # this only re-homed content that matched nothing at all (a student
    # who just writes the answer with no "1)"/"Q1" label, common when
    # there's only one question to answer). That's not the only failure
    # mode, though: verified (2026-08-28) against a real upload where a
    # handwritten CIRCLED "1" was misread by the VLM fallback as "1a" — a
    # confident, WRONG, non-empty guess, which the narrower "" -> only_key
    # fix doesn't catch, since it only ever moves the empty-string bucket.
    # With only one question on the exam, there is no wrong guess to
    # protect against: every segment found on the page is unambiguously
    # this question's content, whatever label (right, wrong, or none) got
    # attached to it. With more than one question, this does NOT apply —
    # guessing which question unlabelled/mislabelled content belongs to
    # among several would be a real, unsafe guess.
    if len(questions) == 1:
        only_key = _normalise_number(questions[0].number)
        all_blocks = [block for blocks in grouped.values() for block in blocks]
        grouped = {only_key: all_blocks}

    for question in questions:
        key = _normalise_number(question.number)
        blocks_for_question = grouped.get(key, [])

        if settings.VLM_FIRST_EXTRACTION:
            processed_blocks = blocks_for_question
        else:
            processed_blocks = [
                _process_block(_crop(gray, seg.bbox), _crop(binary, seg.bbox), vlm)
                for gray, binary, seg in blocks_for_question
            ]
        combined_text = " ".join(p["reconstructed_text"] for p in processed_blocks).strip()
        avg_quality = (
            sum(p["quality_score"] for p in processed_blocks) / len(processed_blocks)
            if processed_blocks
            else 0.0
        )

        concepts = list(question.concepts.all())
        result = evaluate_question(
            reconstructed_text=combined_text,
            concepts=concepts,
            max_marks=question.max_marks,
            ocr_quality=avg_quality,
            llm=llm,
            embedder=embedder,
        )

        evaluation = Evaluation.objects.create(
            sheet=sheet,
            question=question,
            question_number=question.number,
            question_text=question.text,
            max_marks=question.max_marks,
            auto_marks=result.auto_marks,
            confidence=result.confidence,
            band=result.band,
            feedback_strengths=result.feedback["strengths"],
            feedback_gaps=result.feedback["gaps"],
            feedback_suggestions=result.feedback["suggestions"],
        )

        for concept_result in result.concept_results:
            ConceptScore.objects.create(
                evaluation=evaluation,
                concept_id=concept_result.concept_id,
                concept_text=concept_result.text,
                status=concept_result.status,
                similarity=concept_result.similarity,
                marks=concept_result.marks,
                max_marks=concept_result.max_marks,
                evidence=(
                    concept_result.evidence
                    if concept_result.status != ConceptScore.Status.MISSING
                    else ""
                ),
                disagreed=concept_result.disagreed,
            )
            EvaluationRun.objects.bulk_create(
                EvaluationRun(
                    evaluation=evaluation,
                    concept_id=concept_result.concept_id,
                    pass_no=pass_no,
                    raw_response=vote.raw_response,
                )
                for pass_no, vote in enumerate(concept_result.coverage.votes, start=1)
            )

        for processed in processed_blocks:
            _save_block(evaluation, processed)
