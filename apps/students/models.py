from django.conf import settings
from django.db import models

from apps.exams.models import Exam


class Student(models.Model):
    """
    The USN is what joins a login to the answer sheets uploaded for that
    person (BACKEND_PLAN.md §2.1 / §B1) — created either by a teacher via CSV
    import/manual add (Phase B2), or by the person themself at signup, in
    which case `user` links back to their account.
    """

    usn = models.CharField(max_length=15, unique=True)
    name = models.CharField(max_length=150)
    email = models.EmailField(blank=True, default="")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_profile",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["usn"]

    def __str__(self):
        return f"{self.usn} — {self.name}"


class Enrollment(models.Model):
    """Join table: a Student is global (one USN, one row), an Enrollment is
    per-exam. CSV import and manual add both create/reuse the Student row and
    create the Enrollment; un-enrolling (DELETE /exams/{id}/students/{sid}/)
    removes only the Enrollment, never the Student."""

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="enrollments")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["exam", "student"], name="unique_exam_student")
        ]

    def __str__(self):
        return f"{self.student.usn} in {self.exam.name}"
