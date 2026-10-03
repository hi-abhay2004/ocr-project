import uuid

from django.db import models

from apps.exams.models import Exam, Question
from apps.students.models import Student


def sheet_page_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"sheets/{instance.sheet.exam_id}/{instance.sheet_id}/{uuid.uuid4()}.{ext}"


def block_crop_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    return f"blocks/{instance.evaluation.sheet.exam_id}/{instance.evaluation.sheet_id}/{uuid.uuid4()}.{ext}"


class AnswerSheet(models.Model):
    """
    One uploaded answer script for one student. `stage`/`status` are the
    fields the frontend polls (`GET /sheets/{id}/status/` — every 2s); `band`
    and `confidence` are STORED, set once when evaluation finishes, not
    recomputed on read — a teacher's later mark override changes what was
    awarded, not how sure the AI was about its own reading. `total_marks` and
    `max_marks`, by contrast, ARE recomputed live (see EvaluationSerializer):
    they must reflect any override immediately.
    """

    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        RUNNING = "RUNNING", "Running"
        DONE = "DONE", "Done"
        FAILED = "FAILED", "Failed"
        APPROVED = "APPROVED", "Approved"

    class Stage(models.TextChoices):
        # Verbatim copy of STAGES in frontend/src/types/api.ts — the stepper
        # renders these strings directly. Changing one here without changing
        # it there breaks the progress UI silently.
        QUEUED = "queued", "Queued"
        PREPROCESSING = "preprocessing", "Preprocessing"
        SEGMENTATION = "segmentation", "Segmentation"
        ANNOTATIONS = "annotations", "Annotations"
        ADJUDICATION = "adjudication", "Adjudication"
        OCR = "ocr", "OCR"
        SPECIALIZED = "specialized", "Specialized"
        RECONSTRUCTION = "reconstruction", "Reconstruction"
        RETRIEVAL = "retrieval", "Retrieval"
        COVERAGE = "coverage", "Coverage"
        SCORING = "scoring", "Scoring"
        FEEDBACK = "feedback", "Feedback"
        DONE = "done", "Done"

    class Band(models.TextChoices):
        GREEN = "GREEN", "Green"
        ORANGE = "ORANGE", "Orange"
        RED = "RED", "Red"

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="sheets")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="sheets")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.QUEUED)
    page_count = models.PositiveSmallIntegerField(default=0)
    confidence = models.FloatField(default=0.0)
    band = models.CharField(max_length=10, choices=Band.choices, default=Band.RED)
    error_message = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(auto_now_add=True)
    # started_at is set once, at upload, and Django's auto_now_add means no
    # later .save() can move it — correct for "-started_at" ordering (sort
    # by upload time), wrong for anything that means "how long has the
    # CURRENT attempt been running." A sheet retried after sitting QUEUED
    # or FAILED for a day re-enters the pipeline with started_at still
    # pointing at the original upload, so a naive now-minus-started_at
    # elapsed-time display balloons to the sheet's total age instead of the
    # current run's actual duration (observed 2026-10-01: a stuck, retried
    # sheet showed "2316:37" of elapsed time). This is set fresh every time
    # _run() actually begins — including on retry — and is what the
    # frontend's elapsed-time clock should read instead.
    last_run_started_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["exam", "band", "status"])]

    def __str__(self):
        return f"{self.student.usn} — {self.exam.name} ({self.status})"


class SheetPage(models.Model):
    """One uploaded page image. Upload accepts multiple `pages` files
    (§2.1) — a single `image` field on AnswerSheet can't represent that."""

    sheet = models.ForeignKey(AnswerSheet, on_delete=models.CASCADE, related_name="pages")
    index = models.PositiveSmallIntegerField()
    # FileField, not ImageField: an uploaded page is legitimately either an
    # image OR a PDF (settings.ALLOWED_UPLOAD_CONTENT_TYPES). ImageField would
    # try to Pillow-validate a PDF as an image and fail. PDF-to-image
    # conversion is a Phase B5 preprocessing (L1) concern, not an upload-time
    # one — this field just needs to store what was actually sent.
    image = models.FileField(upload_to=sheet_page_path)

    class Meta:
        ordering = ["index"]
        constraints = [
            models.UniqueConstraint(fields=["sheet", "index"], name="unique_sheet_page_index")
        ]

    def __str__(self):
        return f"Page {self.index} of sheet {self.sheet_id}"


class Evaluation(models.Model):
    """
    One question's result on one sheet. Field names match the API directly
    (`auto_marks`, `override_marks`, `override_comment`, `feedback_*`) rather
    than the original §7 names (`marks_awarded`, `teacher_override_marks`,
    `teacher_comment`) — the frontend is the fixed contract now, so naming the
    DB columns to match it removes a translation layer that would otherwise
    exist forever in every serializer.

    `max_marks` is a SNAPSHOT of question.max_marks at evaluation time, not a
    live read — a teacher editing a question's marks later must not silently
    reinterpret an already-graded, possibly-approved and student-visible
    result.
    """

    class Band(models.TextChoices):
        GREEN = "GREEN", "Green"
        ORANGE = "ORANGE", "Orange"
        RED = "RED", "Red"

    sheet = models.ForeignKey(AnswerSheet, on_delete=models.CASCADE, related_name="evaluations")
    question = models.ForeignKey(Question, on_delete=models.SET_NULL, null=True, related_name="+")
    # Snapshotted so a QuestionEvaluation still makes sense even if `question`
    # is later edited or deleted.
    question_number = models.CharField(max_length=10)
    question_text = models.TextField()
    max_marks = models.DecimalField(max_digits=6, decimal_places=2)

    auto_marks = models.DecimalField(max_digits=6, decimal_places=2)
    override_marks = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    override_comment = models.TextField(blank=True, default="")

    confidence = models.FloatField(default=0.0)
    band = models.CharField(max_length=10, choices=Band.choices, default=Band.RED)

    feedback_strengths = models.TextField(blank=True, default="")
    feedback_gaps = models.TextField(blank=True, default="")
    feedback_suggestions = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["question_number"]
        constraints = [
            models.UniqueConstraint(fields=["sheet", "question"], name="unique_sheet_question")
        ]

    def __str__(self):
        return f"Q{self.question_number} on sheet {self.sheet_id}"

    @property
    def effective_marks(self):
        return self.override_marks if self.override_marks is not None else self.auto_marks


class AnswerBlock(models.Model):
    class ContentType(models.TextChoices):
        TEXT = "TEXT", "Text"
        DIAGRAM = "DIAGRAM", "Diagram"
        TABLE = "TABLE", "Table"
        EQUATION = "EQUATION", "Equation"

    class OcrEngine(models.TextChoices):
        TESSERACT_6 = "TESSERACT_6", "Tesseract PSM 6"
        TESSERACT_11 = "TESSERACT_11", "Tesseract PSM 11"
        VLM = "VLM", "Vision model"
        VLM_SPECIALIZED = "VLM_SPECIALIZED", "Vision model (specialized content)"

    evaluation = models.ForeignKey(Evaluation, on_delete=models.CASCADE, related_name="blocks")
    crop_image = models.ImageField(upload_to=block_crop_path)
    image_width = models.PositiveIntegerField()
    image_height = models.PositiveIntegerField()
    quality_score = models.FloatField()
    content_type = models.CharField(
        max_length=10, choices=ContentType.choices, default=ContentType.TEXT
    )
    ocr_engine = models.CharField(
        max_length=20, choices=OcrEngine.choices, default=OcrEngine.TESSERACT_6
    )
    raw_text = models.TextField(blank=True, default="")
    reconstructed_text = models.TextField(blank=True, default="")

    def __str__(self):
        return f"Block {self.id} for evaluation {self.evaluation_id}"


class Annotation(models.Model):
    class Kind(models.TextChoices):
        STRIKE = "STRIKE", "Strike"
        UNDERLINE = "UNDERLINE", "Underline"
        ARROW = "ARROW", "Arrow"
        MARGIN = "MARGIN", "Margin"

    class Intent(models.TextChoices):
        CORRECTION = "CORRECTION", "Correction"
        EMPHASIS = "EMPHASIS", "Emphasis"
        INSERTION = "INSERTION", "Insertion"

    class ResolvedBy(models.TextChoices):
        CV = "CV", "Computer vision"
        VLM = "VLM", "Vision model"

    block = models.ForeignKey(AnswerBlock, on_delete=models.CASCADE, related_name="annotations")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    intent = models.CharField(max_length=10, choices=Intent.choices)
    # {x, y, w, h} in the CROP's own pixel coordinates — never page
    # coordinates, never normalised. See frontend/src/types/api.ts BBox.
    bbox = models.JSONField()
    confidence = models.FloatField()
    resolved_by = models.CharField(max_length=3, choices=ResolvedBy.choices, default=ResolvedBy.CV)

    def __str__(self):
        return f"{self.kind} on block {self.block_id}"


class ConceptScore(models.Model):
    class Status(models.TextChoices):
        COVERED = "COVERED", "Covered"
        PARTIAL = "PARTIAL", "Partial"
        MISSING = "MISSING", "Missing"

    evaluation = models.ForeignKey(
        Evaluation, on_delete=models.CASCADE, related_name="concept_scores"
    )
    # Nullable + snapshotted text: the source Concept can be deleted or
    # re-extracted later (Phase B2's model-answer re-index), but a
    # student-visible, possibly-approved result must keep meaning.
    concept = models.ForeignKey(
        "exams.Concept", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    concept_text = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices)
    similarity = models.FloatField()
    marks = models.DecimalField(max_digits=6, decimal_places=2)
    max_marks = models.DecimalField(max_digits=6, decimal_places=2)
    # Teacher-only (§8 screen 12 strips this for students).
    evidence = models.TextField(blank=True, default="")
    # True when the (future, Phase B6) triple-pass vote didn't agree. Stored
    # rather than computed from EvaluationRun so the stub evaluator (B3) can
    # exercise the ⚠ UI before real triple-pass voting exists.
    disagreed = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.concept_text[:40]} ({self.status})"


class EvaluationRun(models.Model):
    """Audit trail: one row per LLM coverage-check pass
    (ai.coverage.check_coverage, Phase B6) — three per concept, not three
    per evaluation, since triple-pass voting happens independently for
    each concept a question has."""

    evaluation = models.ForeignKey(Evaluation, on_delete=models.CASCADE, related_name="runs")
    # Nullable + SET_NULL like ConceptScore.concept: a source Concept can be
    # deleted or re-extracted later without invalidating an already-graded,
    # possibly-approved result's audit trail.
    concept = models.ForeignKey(
        "exams.Concept", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    pass_no = models.PositiveSmallIntegerField()
    raw_response = models.JSONField(default=dict, blank=True)
    latency_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["concept_id", "pass_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation", "concept", "pass_no"], name="unique_evaluation_concept_pass"
            )
        ]

    def __str__(self):
        return f"Pass {self.pass_no} of evaluation {self.evaluation_id}"
