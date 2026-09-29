from decimal import Decimal

from rest_framework import serializers

from .models import Concept, Exam, Question


class ExamSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()
    sheet_count = serializers.SerializerMethodField()
    avg_marks = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = [
            "id",
            "name",
            "subject",
            "exam_date",
            "total_marks",
            "question_count",
            "sheet_count",
            "avg_marks",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_question_count(self, obj) -> int:
        return obj.questions.count()

    def get_sheet_count(self, obj) -> int:
        return obj.sheets.count()

    def get_avg_marks(self, obj) -> float | None:
        # AnswerSheet has no stored `total_marks` column — an override must be
        # reflected immediately, so it's computed live from each evaluation's
        # effective_marks (apps/evaluation/models.py), same convention as
        # MarksMixin and ExamSummaryView. FAILED sheets are excluded, matching
        # the summary endpoint's convention: they carry no meaningful marks.
        from apps.evaluation.models import AnswerSheet

        sheets = list(
            obj.sheets.exclude(status=AnswerSheet.Status.FAILED).prefetch_related("evaluations")
        )
        if not sheets:
            return None
        totals = [
            sum((e.effective_marks for e in s.evaluations.all()), Decimal("0")) for s in sheets
        ]
        return float(sum(totals) / len(totals))


class QuestionSerializer(serializers.ModelSerializer):
    concepts_indexed = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            "id",
            "exam",
            "number",
            "text",
            "max_marks",
            "model_answer",
            "concepts_indexed",
        ]
        read_only_fields = ["id", "exam"]

    def get_concepts_indexed(self, obj) -> bool:
        return obj.concepts_indexed_at is not None


class ConceptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Concept
        fields = ["id", "question", "text", "weight"]
        read_only_fields = fields
