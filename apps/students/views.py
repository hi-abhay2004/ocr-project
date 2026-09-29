from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsTeacher
from apps.exams.models import Exam

from .models import Enrollment, Student
from .serializers import (
    EMAIL_RE,
    USN_RE,
    StudentImportSerializer,
    StudentInputSerializer,
    StudentSerializer,
)


def _get_owned_exam(request, exam_id) -> Exam:
    return get_object_or_404(Exam, pk=exam_id, teacher=request.user)


class ExamStudentListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def get(self, request, exam_id):
        exam = _get_owned_exam(request, exam_id)
        students = Student.objects.filter(enrollments__exam=exam).order_by("usn")
        return Response(StudentSerializer(students, many=True).data)

    def post(self, request, exam_id):
        """Manual single add. If the USN exists globally, we link it to this
        exam. If they are already in THIS exam, we reject as duplicate."""
        exam = _get_owned_exam(request, exam_id)
        serializer = StudentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usn = serializer.validated_data["usn"]

        student = Student.objects.filter(usn=usn).first()
        if student:
            if Enrollment.objects.filter(exam=exam, student=student).exists():
                return Response(
                    {"usn": ["This student is already enrolled in this exam."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            student = Student.objects.create(
                usn=usn,
                name=serializer.validated_data["name"],
                email=serializer.validated_data.get("email", ""),
            )

        Enrollment.objects.create(exam=exam, student=student)
        return Response(StudentSerializer(student).data, status=status.HTTP_201_CREATED)


class ExamStudentDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def delete(self, request, exam_id, student_id):
        exam = _get_owned_exam(request, exam_id)
        Enrollment.objects.filter(exam=exam, student_id=student_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExamStudentImportView(APIView):
    """
    CSV import — mirrors the client-side rules in
    frontend/src/components/CsvImportDialog.tsx (parseCsv), IN THE SAME ORDER,
    so the preview the teacher saw and what the server actually does agree:

      1. USN missing                              -> per-row error, skipped
      2. USN malformed                            -> per-row error, skipped
      3. USN duplicated within this file           -> per-row error, skipped
      4. name missing                              -> per-row error, skipped
      5. email present but not a valid shape        -> per-row error, skipped
      6. USN exists globally, already enrolled here -> per-row error, skipped
      7. otherwise: linked-or-created + enrolled

    Rows are validated one at a time rather than as a DRF `many=True` batch
    (see ImportRowSerializer) precisely so that one bad row never blocks the
    other 49 good ones — the entire point of an import endpoint.

    Unlike the manual single-add endpoint, an existing Student is a LINK here,
    not a rejection — a class list legitimately contains students who already
    have accounts or are enrolled in other exams.
    """

    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def post(self, request, exam_id):
        exam = _get_owned_exam(request, exam_id)
        serializer = StudentImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        created = 0
        skipped = 0
        errors: list[dict] = []
        seen_in_file: set[str] = set()

        for i, row in enumerate(serializer.validated_data["rows"]):
            row_num = i + 1
            usn = row["usn"].strip().upper()
            name = row["name"].strip()
            email = row["email"].strip()

            if not usn:
                skipped += 1
                errors.append({"row": row_num, "message": "USN is missing"})
                continue
            if not USN_RE.fullmatch(usn):
                skipped += 1
                errors.append({"row": row_num, "message": f"{usn} looks malformed"})
                continue
            if usn in seen_in_file:
                skipped += 1
                errors.append({"row": row_num, "message": f"{usn} is a duplicate in this file"})
                continue
            if not name:
                skipped += 1
                errors.append({"row": row_num, "message": f"{usn}: name is missing"})
                continue
            if email and not EMAIL_RE.fullmatch(email):
                skipped += 1
                errors.append({"row": row_num, "message": f"{usn}: email is not valid"})
                continue

            seen_in_file.add(usn)
            student, _ = Student.objects.get_or_create(
                usn=usn, defaults={"name": name, "email": email}
            )
            _enrollment, enrolled_now = Enrollment.objects.get_or_create(exam=exam, student=student)
            if enrolled_now:
                created += 1
            else:
                skipped += 1
                errors.append({"row": row_num, "message": f"{usn} is already enrolled"})

        return Response({"created": created, "skipped": skipped, "errors": errors})
