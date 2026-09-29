import pytest
from django.core.files.base import ContentFile

from apps.evaluation.models import AnswerSheet, SheetPage
from apps.evaluation.tasks import _run
from apps.students.models import Enrollment, Student

from .conftest import render_answer_page_png

pytestmark = pytest.mark.django_db


@pytest.fixture
def linked_student(student_user, exam):
    """A Student row actually linked to a logged-in User — the results
    endpoints resolve `request.user` -> Student via this link (mirrors
    RegisterSerializer's create-or-link from Phase B1)."""
    s = Student.objects.create(usn="1BY22CS099", name="A Deepika", user=student_user)
    Enrollment.objects.create(exam=exam, student=s)
    return s


def _approved_sheet(exam, student):
    sheet = AnswerSheet.objects.create(exam=exam, student=student, page_count=1)
    page = SheetPage(sheet=sheet, index=0)
    page.image.save("page1.png", ContentFile(render_answer_page_png()), save=True)
    _run(sheet.id)
    sheet.status = AnswerSheet.Status.APPROVED
    sheet.save(update_fields=["status"])
    return sheet


class TestResultList:
    def test_lists_only_approved_sheets(self, student_client, exam, question, linked_student):
        approved = _approved_sheet(exam, linked_student)
        done_not_approved = AnswerSheet.objects.create(
            exam=exam, student=linked_student, page_count=1
        )
        _run(done_not_approved.id)

        response = student_client.get("/api/results/")
        assert response.status_code == 200
        ids = [r["sheet_id"] for r in response.data]
        assert ids == [approved.id]

    def test_a_student_with_no_account_link_gets_404_not_an_empty_list(self, student_client, exam):
        # student_user exists but has no Student row at all — the endpoint
        # cannot silently treat "no link" the same as "no results yet".
        response = student_client.get("/api/results/")
        assert response.status_code == 404

    def test_teacher_cannot_call_the_student_results_endpoint(self, auth_client):
        response = auth_client.get("/api/results/")
        assert response.status_code == 403


class TestResultDetail:
    def test_returns_the_approved_sheet(self, student_client, exam, question, linked_student):
        sheet = _approved_sheet(exam, linked_student)
        response = student_client.get(f"/api/results/{sheet.id}/")
        assert response.status_code == 200
        assert response.data["id"] == sheet.id

    def test_unapproved_sheet_is_a_404_even_for_its_own_student(
        self, student_client, exam, question, linked_student
    ):
        sheet = AnswerSheet.objects.create(exam=exam, student=linked_student, page_count=1)
        _run(sheet.id)
        sheet.refresh_from_db()
        assert sheet.status == "DONE"  # confirm it's genuinely not approved

        response = student_client.get(f"/api/results/{sheet.id}/")
        assert response.status_code == 404

    def test_another_students_approved_sheet_is_unreachable(
        self, student_client, exam, question, linked_student
    ):
        someone_else = Student.objects.create(usn="1BY22CS002", name="Someone Else")
        Enrollment.objects.create(exam=exam, student=someone_else)
        their_sheet = _approved_sheet(exam, someone_else)

        response = student_client.get(f"/api/results/{their_sheet.id}/")
        assert response.status_code == 404

    def test_evidence_and_raw_crop_are_stripped_for_students(
        self, student_client, exam, question, linked_student
    ):
        sheet = _approved_sheet(exam, linked_student)
        response = student_client.get(f"/api/results/{sheet.id}/")

        evaluation = response.data["evaluations"][0]
        for concept_score in evaluation["concept_scores"]:
            assert "evidence" not in concept_score
        for block in evaluation["blocks"]:
            assert block["crop_image_url"] == ""
            assert block["raw_text"] == ""
        # reconstructed_text and the annotation summary DO still come through
        # — students should see what was struck/underlined, just not the raw
        # scan or OCR pass (§8 screen 12).
        assert evaluation["blocks"][0]["reconstructed_text"]
        assert evaluation["blocks"][0]["annotations"]
