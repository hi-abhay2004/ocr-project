from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsStudent, IsTeacher
from apps.exams.models import Exam
from apps.students.models import Enrollment, Student

from .models import AnswerSheet, ConceptScore, Evaluation
from .serializers import (
    EvaluationOverrideSerializer,
    QuestionEvaluationSerializer,
    SheetListItemSerializer,
    SheetSerializer,
    SheetStatusSerializer,
    StudentResultSerializer,
)
from .serializers_upload import SheetUploadSerializer
from .tasks import evaluate_sheet


def _get_owned_exam(request, exam_id) -> Exam:
    return get_object_or_404(Exam, pk=exam_id, teacher=request.user)


def _get_owned_sheet(request, sheet_id) -> AnswerSheet:
    return get_object_or_404(AnswerSheet, pk=sheet_id, exam__teacher=request.user)


class ExamSheetsView(APIView):
    """
    GET  /api/exams/{id}/sheets/?band=&status=  — the review queue (§3.3)
    POST /api/exams/{id}/sheets/                — upload, multipart `pages`

    One class, not two: both are the same collection URL, and a second
    path() entry bound to an identical URL string would simply never be
    reached (Django's resolver returns the first pattern that matches the
    path, before HTTP method is even considered).
    """

    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def get(self, request, exam_id):
        exam = _get_owned_exam(request, exam_id)
        sheets = exam.sheets.select_related("student").prefetch_related("evaluations")

        band = request.query_params.get("band")
        if band:
            sheets = sheets.filter(band=band)
        sheet_status = request.query_params.get("status")
        if sheet_status:
            sheets = sheets.filter(status=sheet_status)

        return Response(SheetListItemSerializer(sheets, many=True).data)

    def post(self, request, exam_id):
        """Returns 202 immediately; evaluation runs in the Celery worker."""
        exam = _get_owned_exam(request, exam_id)
        serializer = SheetUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        student = get_object_or_404(Student, pk=serializer.validated_data["student"])
        if not Enrollment.objects.filter(exam=exam, student=student).exists():
            return Response(
                {"student": ["This student is not enrolled in this exam."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pages = serializer.validated_data["pages"]
        sheet = AnswerSheet.objects.create(exam=exam, student=student, page_count=len(pages))
        for i, page in enumerate(pages):
            sheet.pages.create(index=i, image=page)

        evaluate_sheet.delay(sheet.id)

        return Response(SheetSerializer(sheet).data, status=status.HTTP_202_ACCEPTED)


class SheetStatusView(APIView):
    """GET /api/sheets/{id}/status/ — polled every 2s (§6). Deliberately
    lightweight: no nested evaluations, no student/exam joins beyond what
    ownership scoping needs."""

    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def get(self, request, sheet_id):
        sheet = _get_owned_sheet(request, sheet_id)
        return Response(SheetStatusSerializer(sheet).data)


class SheetDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def get(self, request, sheet_id):
        sheet = _get_owned_sheet(request, sheet_id)
        return Response(SheetSerializer(sheet).data)


class SheetRetryView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def post(self, request, sheet_id):
        sheet = _get_owned_sheet(request, sheet_id)
        sheet.status = AnswerSheet.Status.QUEUED
        sheet.error_message = ""
        sheet.save(update_fields=["status", "error_message"])
        evaluate_sheet.delay(sheet.id)
        return Response(SheetSerializer(sheet).data)


class SheetApproveView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def post(self, request, sheet_id):
        sheet = _get_owned_sheet(request, sheet_id)
        if sheet.status not in (AnswerSheet.Status.DONE, AnswerSheet.Status.APPROVED):
            return Response(
                {"detail": "Only a completed evaluation can be approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sheet.status = AnswerSheet.Status.APPROVED
        sheet.approved_at = timezone.now()
        sheet.save(update_fields=["status", "approved_at"])
        return Response(SheetSerializer(sheet).data)


class ExamSummaryView(APIView):
    """GET /api/exams/{id}/summary/ (§3.2)."""

    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def get(self, request, exam_id):
        exam = _get_owned_exam(request, exam_id)
        # FAILED sheets have no meaningful marks/confidence — excluded from
        # every aggregate below, same convention the frontend mock used.
        sheets = list(
            exam.sheets.exclude(status=AnswerSheet.Status.FAILED).prefetch_related("evaluations")
        )

        bands = {"green": 0, "orange": 0, "red": 0}
        for s in sheets:
            bands[s.band.lower()] += 1

        buckets = [(0, 5), (5, 9), (9, 13), (13, 17), (17, 21)]
        mark_distribution = []
        for lo, hi in buckets:
            count = sum(1 for s in sheets if lo <= _total_marks(s) < hi)
            mark_distribution.append({"bucket": f"{lo}-{hi - 1}", "count": count})

        concept_rows = (
            ConceptScore.objects.filter(evaluation__sheet__in=sheets)
            .values("concept_text")
            .annotate(
                missing=Count("id", filter=Q(status=ConceptScore.Status.MISSING)),
                partial=Count("id", filter=Q(status=ConceptScore.Status.PARTIAL)),
                covered=Count("id", filter=Q(status=ConceptScore.Status.COVERED)),
            )
        )
        concept_miss_rate = sorted(
            (
                {
                    "concept": row["concept_text"],
                    "missing": row["missing"],
                    "partial": row["partial"],
                    "covered": row["covered"],
                }
                for row in concept_rows
            ),
            key=lambda r: r["missing"],
            reverse=True,
        )

        avg_confidence = sum(s.confidence for s in sheets) / len(sheets) if sheets else 0.0
        # VLM escalation rate: share of annotations any real pipeline would
        # have sent to the vision model. Meaningless before Phase B5/B6 exist
        # (the stub always emits the same fixed 2-of-4 split) — reported
        # anyway so the frontend chart has real, if not yet real-pipeline,
        # data to render.
        vlm_rate = _vlm_escalation_rate(sheets)

        return Response(
            {
                "sheet_count": len(sheets),
                "approved_count": sum(1 for s in sheets if s.status == AnswerSheet.Status.APPROVED),
                "bands": bands,
                "mark_distribution": mark_distribution,
                "concept_miss_rate": concept_miss_rate,
                "avg_confidence": round(avg_confidence, 4),
                "vlm_escalation_rate": vlm_rate,
            }
        )


def _total_marks(sheet: AnswerSheet) -> float:
    return float(sum((e.effective_marks for e in sheet.evaluations.all()), start=0))


def _vlm_escalation_rate(sheets: list[AnswerSheet]) -> float:
    from .models import Annotation

    qs = Annotation.objects.filter(block__evaluation__sheet__in=sheets)
    total = qs.count()
    if not total:
        return 0.0
    vlm = qs.filter(resolved_by=Annotation.ResolvedBy.VLM).count()
    return round(vlm / total, 4)


class EvaluationDetailView(APIView):
    """PATCH /api/evaluations/{id}/ — teacher override. `auto_marks` is never
    mutated; `override_marks: null` clears the override and restores the
    machine mark as the effective one (Evaluation.effective_marks)."""

    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def patch(self, request, evaluation_id):
        evaluation = get_object_or_404(
            Evaluation, pk=evaluation_id, sheet__exam__teacher=request.user
        )
        serializer = EvaluationOverrideSerializer(
            data=request.data, context={"evaluation": evaluation}
        )
        serializer.is_valid(raise_exception=True)

        if "override_marks" in serializer.validated_data:
            evaluation.override_marks = serializer.validated_data["override_marks"]
        if "override_comment" in serializer.validated_data:
            evaluation.override_comment = serializer.validated_data["override_comment"] or ""
        evaluation.save(update_fields=["override_marks", "override_comment"])

        return Response(QuestionEvaluationSerializer(evaluation).data)


class StudentResultListView(APIView):
    """GET /api/results/ — approved-only, own-only (§8 screen 11)."""

    permission_classes = [permissions.IsAuthenticated, IsStudent]

    def get(self, request):
        student = get_object_or_404(Student, user=request.user)
        sheets = (
            AnswerSheet.objects.filter(student=student, status=AnswerSheet.Status.APPROVED)
            .select_related("exam")
            .prefetch_related("evaluations")
        )
        return Response(StudentResultSerializer(sheets, many=True).data)


class StudentResultDetailView(APIView):
    """GET /api/results/{sheetId}/ — same Sheet shape as the teacher endpoint,
    with evidence and raw crops stripped by the serializer's for_student
    context. 404s for an unapproved sheet OR another student's sheet — the
    two boundaries that must hold (§8: "the easiest marks to lose in a
    viva")."""

    permission_classes = [permissions.IsAuthenticated, IsStudent]

    def get(self, request, sheet_id):
        student = get_object_or_404(Student, user=request.user)
        sheet = get_object_or_404(
            AnswerSheet, pk=sheet_id, student=student, status=AnswerSheet.Status.APPROVED
        )
        return Response(SheetSerializer(sheet, context={"for_student": True}).data)
