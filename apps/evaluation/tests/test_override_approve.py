import pytest

from apps.evaluation.models import AnswerSheet

pytestmark = pytest.mark.django_db


class TestOverride:
    def test_setting_an_override_does_not_touch_auto_marks(self, auth_client, evaluated_sheet):
        evaluation = evaluated_sheet.evaluations.first()
        auto_marks = evaluation.auto_marks

        response = auth_client.patch(
            f"/api/evaluations/{evaluation.id}/",
            {"override_marks": 8, "override_comment": "Diagram was acceptable"},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["override_marks"] == 8.0
        # response.data holds the pre-render Python Decimal (DRF's test client
        # doesn't run it through the JSON renderer) — compare Decimal-to-
        # Decimal, not Decimal-to-float, or binary float imprecision makes an
        # exact match fail (Decimal('5.01') == 5.01 is False in Python).
        assert response.data["auto_marks"] == auto_marks

        evaluation.refresh_from_db()
        assert evaluation.auto_marks == auto_marks  # untouched
        assert evaluation.override_marks == 8

    def test_rejects_negative_marks(self, auth_client, evaluated_sheet):
        evaluation = evaluated_sheet.evaluations.first()
        response = auth_client.patch(
            f"/api/evaluations/{evaluation.id}/", {"override_marks": -1}, format="json"
        )
        assert response.status_code == 400
        assert "override_marks" in response.data

    def test_rejects_marks_above_max(self, auth_client, evaluated_sheet):
        evaluation = evaluated_sheet.evaluations.first()
        response = auth_client.patch(
            f"/api/evaluations/{evaluation.id}/",
            {"override_marks": float(evaluation.max_marks) + 1},
            format="json",
        )
        assert response.status_code == 400
        assert "override_marks" in response.data

    def test_clearing_the_override_restores_the_machine_mark_as_effective(
        self, auth_client, evaluated_sheet
    ):
        evaluation = evaluated_sheet.evaluations.first()
        auth_client.patch(
            f"/api/evaluations/{evaluation.id}/", {"override_marks": 3}, format="json"
        )

        response = auth_client.patch(
            f"/api/evaluations/{evaluation.id}/",
            {"override_marks": None, "override_comment": None},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["override_marks"] is None

        evaluation.refresh_from_db()
        assert evaluation.effective_marks == evaluation.auto_marks

    def test_override_is_reflected_immediately_in_sheet_total_marks(
        self, auth_client, evaluated_sheet
    ):
        evaluation = evaluated_sheet.evaluations.first()
        auth_client.patch(
            f"/api/evaluations/{evaluation.id}/", {"override_marks": 9}, format="json"
        )

        detail = auth_client.get(f"/api/sheets/{evaluated_sheet.id}/")
        assert detail.data["total_marks"] == 9.0

    def test_another_teacher_cannot_override_it(self, other_auth_client, evaluated_sheet):
        evaluation = evaluated_sheet.evaluations.first()
        response = other_auth_client.patch(
            f"/api/evaluations/{evaluation.id}/", {"override_marks": 5}, format="json"
        )
        assert response.status_code == 404

    def test_student_cannot_override(self, student_client, evaluated_sheet):
        evaluation = evaluated_sheet.evaluations.first()
        response = student_client.patch(
            f"/api/evaluations/{evaluation.id}/", {"override_marks": 5}, format="json"
        )
        assert response.status_code == 403


class TestApprove:
    def test_approving_a_done_sheet_sets_approved_at(self, auth_client, evaluated_sheet):
        response = auth_client.post(f"/api/sheets/{evaluated_sheet.id}/approve/")
        assert response.status_code == 200
        assert response.data["status"] == "APPROVED"
        assert response.data["approved_at"] is not None

    def test_cannot_approve_a_sheet_still_running(
        self, auth_client, exam, question, enrolled_student
    ):
        sheet = AnswerSheet.objects.create(
            exam=exam, student=enrolled_student, page_count=1, status=AnswerSheet.Status.RUNNING
        )
        response = auth_client.post(f"/api/sheets/{sheet.id}/approve/")
        assert response.status_code == 400

    def test_cannot_approve_a_failed_sheet(self, auth_client, exam, question, enrolled_student):
        sheet = AnswerSheet.objects.create(
            exam=exam,
            student=enrolled_student,
            page_count=1,
            status=AnswerSheet.Status.FAILED,
            error_message="boom",
        )
        response = auth_client.post(f"/api/sheets/{sheet.id}/approve/")
        assert response.status_code == 400

    def test_another_teacher_cannot_approve_it(self, other_auth_client, evaluated_sheet):
        response = other_auth_client.post(f"/api/sheets/{evaluated_sheet.id}/approve/")
        assert response.status_code == 404
