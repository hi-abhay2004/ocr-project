"""
Real evaluator: walks the 13-stage enum with short sleeps (so a human
watching the stepper can see it move), then runs the REAL pipeline
end to end — L1-L5 (ai.preprocessing/segmentation/annotations/ocr/
reconstruct, Phase B5) against the sheet's ACTUALLY uploaded page images,
feeding each question's real reconstructed text into the REAL L6-L8
scoring pipeline (ai.pipeline.evaluate_question, Phase B6). See
apps/evaluation/pipeline_runner.py for the segmentation-to-scoring glue.

This task must still get one thing right, unchanged since Phase B3: it
must end in DONE or FAILED, never left RUNNING. A worker crash mid-task is
the one case this does NOT protect against (that needs acks_late + a
periodic sweep); an exception raised BY this function's own logic —
including a page image that fails to decode — is caught here and always
resolves the sheet.
"""

import time

from celery import shared_task
from django.conf import settings
from django.db import transaction

from ai.config import CONFIDENCE_BAND_GREEN, CONFIDENCE_BAND_ORANGE
from ai.providers import get_embedding_provider, get_llm_provider, get_vlm_provider

from .models import AnswerSheet
from .pipeline_runner import create_real_evaluations

STAGE_ORDER = [s for s in AnswerSheet.Stage.values if s != AnswerSheet.Stage.QUEUED]


def _sheet_band_for(confidence: float) -> str:
    if confidence >= CONFIDENCE_BAND_GREEN:
        return AnswerSheet.Band.GREEN
    if confidence >= CONFIDENCE_BAND_ORANGE:
        return AnswerSheet.Band.ORANGE
    return AnswerSheet.Band.RED


@shared_task
def evaluate_sheet(sheet_id: int):
    try:
        _run(sheet_id)
    except Exception as exc:  # noqa: BLE001 — this boundary must never re-raise
        msg = f"Evaluation failed: {exc}"
        exc_type = str(type(exc)).lower()
        if "openai" in exc_type and any(x in exc_type for x in ["servererror", "ratelimit", "timeout", "connection"]):
            msg = "Currently NVIDIA servers are experiencing huge load, try after some time."
            
        AnswerSheet.objects.filter(id=sheet_id).update(
            status=AnswerSheet.Status.FAILED,
            error_message=msg,
        )
        raise


def _run(sheet_id: int):
    sheet = AnswerSheet.objects.select_related("exam").get(id=sheet_id)
    sheet.status = AnswerSheet.Status.RUNNING
    sheet.stage = AnswerSheet.Stage.QUEUED
    sheet.save(update_fields=["status", "stage"])

    embedder = get_embedding_provider()
    llm = get_llm_provider()
    vlm = get_vlm_provider()
    questions = list(sheet.exam.questions.prefetch_related("concepts").order_by("number"))

    for stage in STAGE_ORDER:
        # Real work per stage is milliseconds to low seconds; this sleep
        # exists so a human watching the 13-stage stepper in the browser
        # can actually see it move (matches the frontend's
        # simulatePipeline() timing in the MSW mock this replaces). A
        # Django setting, not a module constant, so
        # config/settings/test.py can set it to ~0 — under
        # CELERY_TASK_ALWAYS_EAGER, `.delay()` runs this function
        # synchronously in the test request itself, so a human-paced delay
        # here would make every upload-touching test take 4+ seconds for no
        # functional reason.
        time.sleep(settings.PIPELINE_STAGE_DELAY_SECONDS)
        sheet.stage = stage
        sheet.save(update_fields=["stage"])

        if stage == AnswerSheet.Stage.SCORING:
            create_real_evaluations(sheet, questions, embedder, llm, vlm)

    with transaction.atomic():
        evaluations = list(sheet.evaluations.all())
        avg_confidence = (
            sum(e.confidence for e in evaluations) / len(evaluations) if evaluations else 0.0
        )
        sheet.status = AnswerSheet.Status.DONE
        sheet.confidence = avg_confidence
        sheet.band = _sheet_band_for(avg_confidence)
        sheet.error_message = ""
        sheet.save(update_fields=["status", "confidence", "band", "error_message"])
