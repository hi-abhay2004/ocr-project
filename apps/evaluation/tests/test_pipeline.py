import pytest

from apps.evaluation.models import AnswerSheet

from .conftest import make_uploaded_file

pytestmark = pytest.mark.django_db


def _upload(client, exam, student):
    return client.post(
        f"/api/exams/{exam.id}/sheets/",
        {"student": student.id, "pages": [make_uploaded_file()]},
        format="multipart",
    )


class TestStubEvaluator:
    """The ★ B3 gate's actual engine — BACKEND_PLAN.md §B3. Runs synchronously
    under CELERY_TASK_ALWAYS_EAGER, so by the time the upload response
    returns, all of this has already happened."""

    def test_produces_one_evaluation_per_question(
        self, auth_client, exam, question, enrolled_student
    ):
        response = _upload(auth_client, exam, enrolled_student)
        sheet = AnswerSheet.objects.get(id=response.data["id"])
        assert sheet.evaluations.count() == 1  # the `question` fixture creates exactly one

    def test_the_real_pipeline_finds_the_uploaded_pages_own_strike_mark(
        self, auth_client, exam, question, enrolled_student
    ):
        # make_uploaded_file() (conftest.py) renders a real page with a real
        # strike drawn over "redundancy" — this is apps.evaluation.pipeline_runner
        # actually segmenting, detecting and OCR-ing THAT image, not a
        # canned fixture standing in for it.
        response = _upload(auth_client, exam, enrolled_student)
        sheet = AnswerSheet.objects.get(id=response.data["id"])
        block = sheet.evaluations.first().blocks.first()

        assert block is not None  # segmentation found the uploaded content
        assert block.image_width > 0 and block.image_height > 0
        assert "redundancy" not in block.reconstructed_text  # dropped by L5 (ai.reconstruct)

        annotations = list(block.annotations.all())
        assert any(a.kind == "STRIKE" for a in annotations)
        for a in annotations:
            # Crop-pixel bbox, not page coordinates or normalised [0,1] —
            # within the block's own recorded dimensions.
            assert 0 <= a.bbox["x"] <= block.image_width
            assert 0 <= a.bbox["y"] <= block.image_height
            assert a.resolved_by in ("CV", "VLM")

    def test_a_blank_page_still_produces_an_evaluation_with_no_content(
        self, auth_client, exam, question, enrolled_student
    ):
        # Nothing written for a question is real input too — segmentation
        # finds no blocks, and ai.pipeline.evaluate_question correctly
        # bands every concept MISSING rather than crashing or skipping the
        # question's Evaluation row entirely.
        from .conftest import make_blank_uploaded_file

        response = auth_client.post(
            f"/api/exams/{exam.id}/sheets/",
            {"student": enrolled_student.id, "pages": [make_blank_uploaded_file()]},
            format="multipart",
        )
        sheet = AnswerSheet.objects.get(id=response.data["id"])
        evaluation = sheet.evaluations.first()
        assert evaluation.blocks.count() == 0
        assert evaluation.auto_marks == 0
        assert all(cs.status == "MISSING" for cs in evaluation.concept_scores.all())

    def test_unlabelled_content_still_scores_on_a_single_question_exam(
        self, auth_client, exam, question, enrolled_student
    ):
        # The `question` fixture creates exactly one question — a real
        # upload with an answer but no visible "1)"/"Q1" label anywhere
        # (verified 2026-08-27) previously left every concept MISSING even
        # though the student wrote a real, matching answer, because
        # nothing in the upload ever produced a question number to match
        # against. Unambiguous with only one question on the exam.
        from .conftest import make_unlabelled_uploaded_file

        response = auth_client.post(
            f"/api/exams/{exam.id}/sheets/",
            {"student": enrolled_student.id, "pages": [make_unlabelled_uploaded_file()]},
            format="multipart",
        )
        sheet = AnswerSheet.objects.get(id=response.data["id"])
        evaluation = sheet.evaluations.first()
        assert evaluation.blocks.count() == 1
        assert evaluation.blocks.first().reconstructed_text.strip() != ""
        assert not all(cs.status == "MISSING" for cs in evaluation.concept_scores.all())

    def test_mislabelled_content_still_scores_on_a_single_question_exam(
        self, auth_client, exam, question, enrolled_student
    ):
        # A confident but WRONG label (verified 2026-08-28 against a real
        # upload: a handwritten circled "1" misread as "1a") is a
        # different failure mode from no label at all — it doesn't fall
        # into the "" unmatched bucket, so a fix that only re-homes empty
        # matches doesn't catch it. With only one question on the exam,
        # there's no correct label to guess wrong: everything found on
        # the page is this question's content regardless.
        from .conftest import make_mislabelled_uploaded_file

        response = auth_client.post(
            f"/api/exams/{exam.id}/sheets/",
            {"student": enrolled_student.id, "pages": [make_mislabelled_uploaded_file()]},
            format="multipart",
        )
        sheet = AnswerSheet.objects.get(id=response.data["id"])
        evaluation = sheet.evaluations.first()
        assert evaluation.blocks.count() == 1
        assert evaluation.blocks.first().reconstructed_text.strip() != ""
        assert not all(cs.status == "MISSING" for cs in evaluation.concept_scores.all())

    def test_concept_scores_use_real_cosine_similarity_from_stored_embeddings(
        self, auth_client, exam, question, enrolled_student
    ):
        response = _upload(auth_client, exam, enrolled_student)
        sheet = AnswerSheet.objects.get(id=response.data["id"])
        evaluation = sheet.evaluations.first()
        scores = list(evaluation.concept_scores.all())

        from ai.config import SIMILARITY_FULL_CREDIT, SIMILARITY_PARTIAL_CREDIT

        assert len(scores) == question.concepts.count()
        for score in scores:
            assert 0.0 <= score.similarity <= 1.0
            # status must be consistent with the similarity that produced it
            # (ai.scoring.band_concept: COVERED needs similarity >=
            # SIMILARITY_FULL_CREDIT; MISSING needs similarity <
            # SIMILARITY_PARTIAL_CREDIT AND an llm verdict of MISSING).
            if score.status == "COVERED":
                assert score.similarity >= SIMILARITY_FULL_CREDIT
            elif score.status == "MISSING":
                assert score.similarity < SIMILARITY_PARTIAL_CREDIT

    def test_auto_marks_equals_the_sum_of_concept_marks(
        self, auth_client, exam, question, enrolled_student
    ):
        response = _upload(auth_client, exam, enrolled_student)
        sheet = AnswerSheet.objects.get(id=response.data["id"])
        evaluation = sheet.evaluations.first()
        expected = sum(cs.marks for cs in evaluation.concept_scores.all())
        assert evaluation.auto_marks == expected

    def test_sheet_confidence_and_band_are_set_on_completion(
        self, auth_client, exam, question, enrolled_student
    ):
        response = _upload(auth_client, exam, enrolled_student)
        sheet = AnswerSheet.objects.get(id=response.data["id"])
        assert sheet.status == "DONE"
        assert 0.0 < sheet.confidence <= 1.0
        assert sheet.band in ("GREEN", "ORANGE", "RED")

    def test_retry_clears_and_recreates_evaluations(
        self, auth_client, exam, question, enrolled_student
    ):
        response = _upload(auth_client, exam, enrolled_student)
        sheet_id = response.data["id"]
        first_eval_id = AnswerSheet.objects.get(id=sheet_id).evaluations.first().id

        retry = auth_client.post(f"/api/sheets/{sheet_id}/retry/")
        assert retry.status_code == 200

        sheet = AnswerSheet.objects.get(id=sheet_id)
        assert sheet.status == "DONE"
        new_eval = sheet.evaluations.first()
        assert new_eval.id != first_eval_id  # old row was deleted and recreated
        assert sheet.evaluations.count() == 1  # not doubled

    def test_a_failing_provider_marks_the_sheet_failed_not_running(
        self, exam, question, enrolled_student, monkeypatch
    ):
        # Calls evaluate_sheet() directly rather than through the upload API.
        # Going through the view would route the RuntimeError through DRF's
        # own dispatch()/EXCEPTION_HANDLER (apps.core.exceptions), which
        # converts ANY unhandled exception into a 500 Response — correct
        # production behaviour, but it means the exception never reaches a
        # test client as a raised Python exception. This test isolates what
        # it actually needs to check: evaluate_sheet()'s own try/except
        # contract, not DRF's separate exception-handling layer.
        from apps.evaluation.tasks import evaluate_sheet

        sheet = AnswerSheet.objects.create(exam=exam, student=enrolled_student, page_count=1)

        def boom(*args, **kwargs):
            raise RuntimeError("simulated provider outage")

        # get_llm_provider, not get_embedding_provider: with no SheetPage
        # uploaded, segmentation finds no blocks and the embedder is
        # correctly never called at all (empty text -> no chunks to embed)
        # — but ai.coverage.check_coverage's triple-pass vote runs
        # regardless, once per concept, so the LLM provider is always the
        # one guaranteed to fire.
        monkeypatch.setattr(
            "apps.evaluation.tasks.get_llm_provider", lambda: type("M", (), {"chat": boom})()
        )

        with pytest.raises(RuntimeError):
            evaluate_sheet(sheet.id)

        sheet.refresh_from_db()
        assert sheet.status == "FAILED"
        assert "simulated provider outage" in sheet.error_message

    def test_an_llm_that_never_returns_valid_json_marks_the_sheet_failed(
        self, exam, question, enrolled_student, monkeypatch
    ):
        # A real, not simulated, failure mode: ai.providers.retry.call_json
        # exhausts its retries and raises LLMJSONError from deep inside
        # ai.pipeline.evaluate_question (concept extraction already
        # succeeded in the `question` fixture — this is the coverage-check
        # LLM call failing during evaluation itself). evaluate_sheet's own
        # try/except is what has to catch this, same contract as any other
        # provider failure.
        from apps.evaluation.tasks import evaluate_sheet

        sheet = AnswerSheet.objects.create(exam=exam, student=enrolled_student, page_count=1)

        class _BrokenLLM:
            def chat(self, prompt, *, system=None, json_mode=True):
                return "this is not json"

        monkeypatch.setattr("apps.evaluation.tasks.get_llm_provider", lambda: _BrokenLLM())

        with pytest.raises(Exception, match="valid JSON"):
            evaluate_sheet(sheet.id)

        sheet.refresh_from_db()
        assert sheet.status == "FAILED"
        assert sheet.error_message  # a readable message, not silence

    def test_a_celery_soft_time_limit_marks_the_sheet_failed_not_running(
        self, exam, question, enrolled_student, monkeypatch
    ):
        # SoftTimeLimitExceeded (celery.exceptions, re-exported from
        # billiard) is a real Exception subclass, not BaseException — this
        # proves evaluate_sheet's bare `except Exception` actually catches
        # it rather than relying on an unverified assumption about Celery's
        # class hierarchy. A stuck LLM/VLM call hitting
        # CELERY_TASK_SOFT_TIME_LIMIT must not leave the sheet RUNNING
        # forever.
        from celery.exceptions import SoftTimeLimitExceeded

        from apps.evaluation.tasks import evaluate_sheet

        sheet = AnswerSheet.objects.create(exam=exam, student=enrolled_student, page_count=1)

        def timed_out(*args, **kwargs):
            raise SoftTimeLimitExceeded()

        monkeypatch.setattr(
            "apps.evaluation.tasks.get_llm_provider",
            lambda: type("M", (), {"chat": timed_out})(),
        )

        with pytest.raises(SoftTimeLimitExceeded):
            evaluate_sheet(sheet.id)

        sheet.refresh_from_db()
        assert sheet.status == "FAILED"
        assert sheet.error_message


class TestSheetStatusAndDetail:
    def test_status_endpoint_is_lightweight(self, auth_client, exam, question, enrolled_student):
        response = _upload(auth_client, exam, enrolled_student)
        sheet_id = response.data["id"]

        status_response = auth_client.get(f"/api/sheets/{sheet_id}/status/")
        assert status_response.status_code == 200
        assert set(status_response.data.keys()) == {
            "id",
            "status",
            "stage",
            "started_at",
            "error_message",
        }

    def test_detail_includes_full_nested_evaluation_tree(
        self, auth_client, exam, question, enrolled_student
    ):
        response = _upload(auth_client, exam, enrolled_student)
        sheet_id = response.data["id"]

        detail = auth_client.get(f"/api/sheets/{sheet_id}/")
        assert detail.status_code == 200
        ev = detail.data["evaluations"][0]
        assert "concept_scores" in ev and "blocks" in ev and "feedback" in ev
        assert set(ev["feedback"].keys()) == {"strengths", "gaps", "suggestions"}
        assert ev["blocks"][0]["annotations"]

    def test_max_marks_reflects_the_question_snapshot_not_a_live_read(
        self, auth_client, exam, question, enrolled_student
    ):
        response = _upload(auth_client, exam, enrolled_student)
        sheet_id = response.data["id"]

        # Editing the question's marks afterward must not reinterpret an
        # already-evaluated result.
        question.max_marks = 99
        question.save(update_fields=["max_marks"])

        detail = auth_client.get(f"/api/sheets/{sheet_id}/")
        assert detail.data["evaluations"][0]["max_marks"] == 10.0

    def test_another_teacher_cannot_read_status_or_detail(
        self, auth_client, other_auth_client, exam, question, enrolled_student
    ):
        response = _upload(auth_client, exam, enrolled_student)
        sheet_id = response.data["id"]

        assert other_auth_client.get(f"/api/sheets/{sheet_id}/status/").status_code == 404
        assert other_auth_client.get(f"/api/sheets/{sheet_id}/").status_code == 404

    def test_student_cannot_read_the_teacher_detail_endpoint(
        self, auth_client, student_client, exam, question, enrolled_student
    ):
        response = _upload(auth_client, exam, enrolled_student)
        sheet_id = response.data["id"]
        assert student_client.get(f"/api/sheets/{sheet_id}/").status_code == 403


def test_struck_regions_are_masked_out_before_either_ocr_engine_sees_them():
    # Belt-and-suspenders alongside ai.ocr.vlm_engine's prompt instruction
    # to omit struck text: verified (2026-08-27) against a real upload
    # that the VLM does not always comply with that instruction even when
    # explicitly asked, so removing the ink before any engine sees it is
    # the more reliable guarantee.
    import numpy as np

    from ai.types import Annotation, BBox
    from apps.evaluation.pipeline_runner import _mask_struck_regions

    gray = np.zeros((100, 200), dtype=np.uint8)  # all "ink" (0), nothing masked yet
    strike = Annotation(
        kind="STRIKE", intent="CORRECTION", bbox=BBox(x=50, y=40, w=60, h=4), confidence=1.0
    )
    masked = _mask_struck_regions(gray, [strike])

    # The struck region (plus its padding) is now background (255)...
    assert masked[40, 70] == 255
    # ...but ink well outside the struck region is untouched.
    assert masked[10, 10] == 0
    assert masked[90, 190] == 0


def test_a_vlm_transcription_is_used_directly_not_re_derived_from_tesseract(monkeypatch):
    # Verified (2026-08-27) against real uploads: when the OCR router
    # escalates to the VLM (ai.ocr.router, low Tesseract confidence),
    # falling back to ai.reconstruct's Tesseract-word-based assembly here
    # would silently throw away the VLM's good transcription and
    # re-derive text from the EXACT source that was unreliable enough to
    # escalate in the first place — which is what produced unreadable
    # "What the grader read" output on a real sheet despite the VLM
    # itself transcribing that same image almost perfectly.
    import apps.evaluation.pipeline_runner as pipeline_runner
    from ai.ocr.tesseract_engine import OCRResult
    from ai.ocr.vlm_engine import VLM
    from ai.preprocessing import to_gray
    from ai.providers.mock import MockVLMProvider
    from tests.unit.cv_fixtures import clean_answer_block, to_binary

    img, _ = clean_answer_block(["Some text Tesseract would actually read fine on its own."])
    gray = to_gray(img)
    binary = to_binary(img)

    monkeypatch.setattr(
        pipeline_runner,
        "run_ocr",
        lambda block_gray, vlm: OCRResult(
            text="The VLM's own clean transcription.", confidence=1.0, engine=VLM
        ),
    )

    result = pipeline_runner._process_block(gray, binary, MockVLMProvider())
    assert result["reconstructed_text"] == "The VLM's own clean transcription."


def test_a_tesseract_transcription_still_goes_through_reconstruct(monkeypatch):
    # The companion property to the test above: when Tesseract's OWN
    # result is confident enough to keep (no escalation), reconstruction
    # must still run its normal word-drop-and-stitch pass — this isn't a
    # blanket "always trust ocr_result.text" change.
    import apps.evaluation.pipeline_runner as pipeline_runner
    from ai.ocr.tesseract_engine import TESSERACT_6, OCRResult
    from ai.preprocessing import to_gray
    from ai.providers.mock import MockVLMProvider
    from tests.unit.cv_fixtures import clean_answer_block, to_binary

    img, _ = clean_answer_block(["Some text Tesseract would actually read fine on its own."])
    gray = to_gray(img)
    binary = to_binary(img)

    monkeypatch.setattr(
        pipeline_runner,
        "run_ocr",
        lambda block_gray, vlm: OCRResult(
            text="whatever ocr_result.text says", confidence=0.95, engine=TESSERACT_6
        ),
    )

    result = pipeline_runner._process_block(gray, binary, MockVLMProvider())
    # Real reconstruction of the ACTUAL image content, not the stubbed
    # ocr_result.text — proves this path didn't just switch to the same
    # ocr_result.text shortcut unconditionally.
    assert "Tesseract" in result["reconstructed_text"]
    assert result["reconstructed_text"] != "whatever ocr_result.text says"
