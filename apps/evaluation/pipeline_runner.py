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

from ai.annotations.adjudicator import adjudicate
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
            for block in extracted.blocks:
                question_number = block.question_number or carried_number
                if block.question_number:
                    carried_number = block.question_number
                key = _normalise_number(question_number)
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
