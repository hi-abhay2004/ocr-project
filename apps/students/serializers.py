import re

from rest_framework import serializers

from .models import Student

USN_RE = re.compile(r"^[0-9A-Za-z]{6,15}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = ["id", "usn", "name", "email"]
        read_only_fields = ["id"]


class StudentInputSerializer(serializers.Serializer):
    """Manual single-add (POST /exams/{id}/students/) — mirrors StudentInput
    in frontend/src/api/students.ts. A malformed field here 400s the one
    request, which is correct: this is a single teacher-typed row, not a batch
    where one bad line shouldn't cost the other 49."""

    usn = serializers.CharField(max_length=15)
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True, default="")

    def validate_usn(self, value):
        value = value.strip().upper()
        if not USN_RE.fullmatch(value):
            raise serializers.ValidationError("USN looks malformed.")
        return value


class ImportRowSerializer(serializers.Serializer):
    """
    Deliberately permissive — CharField, not EmailField, and no USN format
    check. A DRF child serializer under `many=True` aborts the ENTIRE batch
    the moment any one row fails validation, which is wrong for an import:
    one malformed row must be skipped-with-an-error, not block the other 49
    good ones.

    Structural validation (right keys, string types) happens here; the actual
    business rules — malformed USN, invalid email, duplicate-in-file,
    already-enrolled — are checked per-row in ExamStudentImportView, in the
    same order frontend/src/components/CsvImportDialog.tsx's parseCsv() uses,
    so the preview the teacher saw and what the server does agree.
    """

    usn = serializers.CharField(max_length=32, allow_blank=True, required=False, default="")
    name = serializers.CharField(max_length=150, allow_blank=True, required=False, default="")
    email = serializers.CharField(max_length=254, allow_blank=True, required=False, default="")


class StudentImportSerializer(serializers.Serializer):
    rows = ImportRowSerializer(many=True)
