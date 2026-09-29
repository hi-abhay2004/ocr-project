import pytest

from apps.evaluation.models import AnswerSheet
from apps.evaluation.tasks import _run
from apps.students.models import Enrollment, Student

pytestmark = pytest.mark.django_db


def _new_evaluated_sheet(exam, usn):
    student = Student.objects.create(usn=usn, name=usn)
    Enrollment.objects.create(exam=exam, student=student)
    sheet = AnswerSheet.objects.create(exam=exam, student=student, page_count=1)
    _run(sheet.id)
    # _run() fetches and mutates its OWN AnswerSheet instance internally — it
    # never touches this Python object, so without refreshing, `sheet` here
    # would still read the pre-evaluation defaults (status=QUEUED etc).
    sheet.refresh_from_db()
    return sheet


class TestExamSummary:
    def test_counts_and_shape(self, auth_client, exam, question, enrolled_student):
        _run_result = AnswerSheet.objects.create(exam=exam, student=enrolled_student, page_count=1)
        _run(_run_result.id)

        response = auth_client.get(f"/api/exams/{exam.id}/summary/")
        assert response.status_code == 200
        body = response.data
        assert body["sheet_count"] == 1
        assert body["approved_count"] == 0
        assert set(body["bands"].keys()) == {"green", "orange", "red"}
        assert sum(body["bands"].values()) == 1
        assert len(body["mark_distribution"]) == 5
        assert 0.0 <= body["avg_confidence"] <= 1.0
        assert 0.0 <= body["vlm_escalation_rate"] <= 1.0

    def test_failed_sheets_are_excluded_from_every_aggregate(
        self, auth_client, exam, question, enrolled_student
    ):
        AnswerSheet.objects.create(
            exam=exam,
            student=enrolled_student,
            page_count=1,
            status=AnswerSheet.Status.FAILED,
            error_message="boom",
        )
        response = auth_client.get(f"/api/exams/{exam.id}/summary/")
        assert response.data["sheet_count"] == 0

    def test_concept_miss_rate_is_sorted_worst_first(self, auth_client, exam, question):
        sheet1 = _new_evaluated_sheet(exam, "1BY22CS010")
        sheet2 = _new_evaluated_sheet(exam, "1BY22CS011")
        assert sheet1.status == sheet2.status == "DONE"

        response = auth_client.get(f"/api/exams/{exam.id}/summary/")
        rows = response.data["concept_miss_rate"]
        assert rows == sorted(rows, key=lambda r: r["missing"], reverse=True)
        for row in rows:
            assert set(row.keys()) == {"concept", "missing", "partial", "covered"}

    def test_zero_sheets_does_not_error(self, auth_client, exam):
        response = auth_client.get(f"/api/exams/{exam.id}/summary/")
        assert response.status_code == 200
        assert response.data["sheet_count"] == 0
        assert response.data["avg_confidence"] == 0.0

    def test_another_teacher_cannot_read_it(self, other_auth_client, exam):
        response = other_auth_client.get(f"/api/exams/{exam.id}/summary/")
        assert response.status_code == 404
