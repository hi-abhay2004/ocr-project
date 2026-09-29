from decimal import Decimal

from rest_framework import serializers

from apps.students.serializers import StudentSerializer

from .models import Annotation, AnswerBlock, AnswerSheet, ConceptScore, Evaluation


class MarksMixin:
    """Shared by SheetSerializer and SheetListItemSerializer. Computed LIVE
    from the sheet's evaluations rather than stored — an override must be
    reflected immediately, and this is always correct with zero extra
    bookkeeping (see AnswerSheet's docstring)."""

    def get_total_marks(self, obj) -> float:
        total = sum((e.effective_marks for e in obj.evaluations.all()), Decimal("0"))
        return float(total)

    def get_max_marks(self, obj) -> float:
        total = sum((e.max_marks for e in obj.evaluations.all()), Decimal("0"))
        return float(total)


class AnnotationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Annotation
        fields = ["id", "kind", "intent", "bbox", "confidence", "resolved_by"]


class AnswerBlockSerializer(serializers.ModelSerializer):
    question_id = serializers.IntegerField(source="evaluation.question_id", read_only=True)
    crop_image_url = serializers.SerializerMethodField()
    annotations = AnnotationSerializer(many=True, read_only=True)

    class Meta:
        model = AnswerBlock
        fields = [
            "id",
            "question_id",
            "crop_image_url",
            "image_width",
            "image_height",
            "quality_score",
            "content_type",
            "ocr_engine",
            "raw_text",
            "reconstructed_text",
            "annotations",
        ]

    def get_crop_image_url(self, obj) -> str:
        return obj.crop_image.url if obj.crop_image else ""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Students never see the raw scan or the OCR's raw pass (§8 screen 12)
        # — only reconstructed_text and the annotation summary.
        if self.context.get("for_student"):
            data["crop_image_url"] = ""
            data["raw_text"] = ""
        return data


class ConceptScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConceptScore
        fields = [
            "id",
            "concept_id",
            "concept_text",
            "status",
            "similarity",
            "marks",
            "max_marks",
            "evidence",
            "disagreed",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # The retrieved evidence chunk is the teacher's audit trail, not
        # student-facing feedback (§8 screen 12).
        if self.context.get("for_student"):
            data.pop("evidence", None)
        return data


class QuestionEvaluationSerializer(serializers.ModelSerializer):
    """Output-only — nested inside SheetSerializer and used to render the
    PATCH /evaluations/{id}/ response. Writes to override_marks/comment go
    through EvaluationOverrideSerializer + explicit view logic, never through
    this serializer's own validated_data.

    No explicit `question_id` field needed — DRF's ModelSerializer auto-maps
    a "<fk>_id" name in Meta.fields to a ReadOnlyField() (verified directly
    against this model rather than assumed)."""

    concept_scores = ConceptScoreSerializer(many=True, read_only=True)
    blocks = AnswerBlockSerializer(many=True, read_only=True)
    feedback = serializers.SerializerMethodField()

    class Meta:
        model = Evaluation
        fields = [
            "id",
            "question_id",
            "question_number",
            "question_text",
            "max_marks",
            "auto_marks",
            "override_marks",
            "override_comment",
            "confidence",
            "band",
            "concept_scores",
            "feedback",
            "blocks",
        ]
        read_only_fields = fields

    def get_feedback(self, obj) -> dict:
        return {
            "strengths": obj.feedback_strengths,
            "gaps": obj.feedback_gaps,
            "suggestions": obj.feedback_suggestions,
        }


class EvaluationOverrideSerializer(serializers.Serializer):
    """PATCH /api/evaluations/{id}/ body. `override_marks: null` clears the
    override (frontend/src/api/evaluations.ts clearOverride) — DecimalField
    with allow_null handles both the set and the clear in one serializer."""

    override_marks = serializers.DecimalField(
        max_digits=6, decimal_places=2, allow_null=True, required=False
    )
    override_comment = serializers.CharField(allow_blank=True, allow_null=True, required=False)

    def validate_override_marks(self, value):
        if value is None:
            return value
        max_marks = self.context["evaluation"].max_marks
        if value < 0 or value > max_marks:
            raise serializers.ValidationError(f"Must be between 0 and {max_marks}.")
        return value


class SheetSerializer(serializers.ModelSerializer, MarksMixin):
    exam_name = serializers.CharField(source="exam.name", read_only=True)
    student = StudentSerializer(read_only=True)
    total_marks = serializers.SerializerMethodField()
    max_marks = serializers.SerializerMethodField()
    evaluations = QuestionEvaluationSerializer(many=True, read_only=True)

    class Meta:
        model = AnswerSheet
        fields = [
            "id",
            "exam",
            "exam_name",
            "student",
            "status",
            "stage",
            "page_count",
            "total_marks",
            "max_marks",
            "confidence",
            "band",
            "error_message",
            "started_at",
            "approved_at",
            "evaluations",
        ]
        read_only_fields = fields


class SheetListItemSerializer(serializers.ModelSerializer, MarksMixin):
    """GET /api/exams/{id}/sheets/ row shape — the review queue (§3.3).
    Deliberately excludes `evaluations`: the queue lists dozens of sheets and
    doesn't need each one's full nested blocks/annotations/concept scores."""

    student = StudentSerializer(read_only=True)
    total_marks = serializers.SerializerMethodField()
    max_marks = serializers.SerializerMethodField()

    class Meta:
        model = AnswerSheet
        fields = [
            "id",
            "student",
            "status",
            "stage",
            "band",
            "confidence",
            "total_marks",
            "max_marks",
            "approved_at",
        ]


class SheetStatusSerializer(serializers.ModelSerializer):
    """The lightweight shape polled every 2s (§6) — deliberately excludes
    everything else on AnswerSheet so the poll stays cheap."""

    class Meta:
        model = AnswerSheet
        fields = ["id", "status", "stage", "started_at", "error_message"]


class StudentResultSerializer(serializers.ModelSerializer, MarksMixin):
    sheet_id = serializers.IntegerField(source="id", read_only=True)
    # No `source="exam_id"` — DRF rejects a source equal to the field's own
    # name as redundant (verified: this raises an AssertionError at
    # serialization time, not import time, so it only surfaces once a request
    # actually hits this serializer). "exam_id" alone in Meta.fields below is
    # enough; DRF auto-maps it exactly like "question_id" elsewhere.
    exam_id = serializers.IntegerField(read_only=True)
    exam_name = serializers.CharField(source="exam.name", read_only=True)
    subject = serializers.CharField(source="exam.subject", read_only=True)
    exam_date = serializers.DateField(source="exam.exam_date", read_only=True)
    total_marks = serializers.SerializerMethodField()
    max_marks = serializers.SerializerMethodField()

    class Meta:
        model = AnswerSheet
        fields = [
            "sheet_id",
            "exam_id",
            "exam_name",
            "subject",
            "exam_date",
            "total_marks",
            "max_marks",
            "approved_at",
        ]
