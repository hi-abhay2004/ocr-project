import pytest

from apps.evaluation.models import AnswerSheet

from .conftest import make_uploaded_file

pytestmark = pytest.mark.django_db


class TestUpload:
    def test_valid_upload_returns_202_and_queues_the_pipeline(
        self, auth_client, exam, enrolled_student
    ):
        response = auth_client.post(
            f"/api/exams/{exam.id}/sheets/",
            {"student": enrolled_student.id, "pages": [make_uploaded_file()]},
            format="multipart",
        )
        assert response.status_code == 202
        sheet_id = response.data["id"]

        # Under CELERY_TASK_ALWAYS_EAGER the task has already run by the time
        # this assertion executes, even though the response body above
        # reflects pre-task state (see conftest note) — a real async worker
        # would show the same QUEUED response and finish later; only the
        # ORDER differs, not the contract.
        sheet = AnswerSheet.objects.get(id=sheet_id)
        assert sheet.status == AnswerSheet.Status.DONE
        assert sheet.page_count == 1

    def test_rejects_a_student_not_enrolled_in_this_exam(self, auth_client, exam, student):
        # `student` exists but was never enrolled via the `enrolled_student` fixture.
        response = auth_client.post(
            f"/api/exams/{exam.id}/sheets/",
            {"student": student.id, "pages": [make_uploaded_file()]},
            format="multipart",
        )
        assert response.status_code == 400
        assert "student" in response.data

    def test_rejects_oversize_file(self, auth_client, exam, enrolled_student, settings):
        settings.MAX_UPLOAD_SIZE_BYTES = 10  # tiny, so the fixture PNG trips it
        response = auth_client.post(
            f"/api/exams/{exam.id}/sheets/",
            {"student": enrolled_student.id, "pages": [make_uploaded_file()]},
            format="multipart",
        )
        assert response.status_code == 400
        assert "pages" in response.data

    def test_rejects_disallowed_content_type(self, auth_client, exam, enrolled_student):
        from django.core.files.uploadedfile import SimpleUploadedFile

        bad_file = SimpleUploadedFile(
            "virus.exe", b"not really", content_type="application/x-msdownload"
        )
        response = auth_client.post(
            f"/api/exams/{exam.id}/sheets/",
            {"student": enrolled_student.id, "pages": [bad_file]},
            format="multipart",
        )
        assert response.status_code == 400
        assert "pages" in response.data

    def test_rejects_empty_upload(self, auth_client, exam, enrolled_student):
        response = auth_client.post(
            f"/api/exams/{exam.id}/sheets/", {"student": enrolled_student.id}, format="multipart"
        )
        assert response.status_code == 400

    def test_accepts_multiple_pages(self, auth_client, exam, enrolled_student):
        response = auth_client.post(
            f"/api/exams/{exam.id}/sheets/",
            {
                "student": enrolled_student.id,
                "pages": [make_uploaded_file("p1.png"), make_uploaded_file("p2.png")],
            },
            format="multipart",
        )
        assert response.status_code == 202
        sheet = AnswerSheet.objects.get(id=response.data["id"])
        assert sheet.page_count == 2
        assert sheet.pages.count() == 2

    def test_page_filenames_are_never_the_client_supplied_name(
        self, auth_client, exam, enrolled_student
    ):
        # Path-traversal guard: the stored filename is always a generated
        # UUID (apps/evaluation/models.py sheet_page_path), so a malicious
        # original filename like "../../etc/passwd" is simply discarded, not
        # sanitised-and-trusted.
        from django.core.files.uploadedfile import SimpleUploadedFile

        traversal_file = SimpleUploadedFile(
            "../../../etc/passwd.png", make_uploaded_file().read(), content_type="image/png"
        )
        response = auth_client.post(
            f"/api/exams/{exam.id}/sheets/",
            {"student": enrolled_student.id, "pages": [traversal_file]},
            format="multipart",
        )
        assert response.status_code == 202
        sheet = AnswerSheet.objects.get(id=response.data["id"])
        stored_name = sheet.pages.first().image.name
        assert "etc" not in stored_name
        assert "passwd" not in stored_name

    def test_another_teacher_cannot_upload_to_it(self, other_auth_client, exam, enrolled_student):
        response = other_auth_client.post(
            f"/api/exams/{exam.id}/sheets/",
            {"student": enrolled_student.id, "pages": [make_uploaded_file()]},
            format="multipart",
        )
        assert response.status_code == 404

    def test_student_cannot_upload(self, student_client, exam, enrolled_student):
        response = student_client.post(
            f"/api/exams/{exam.id}/sheets/",
            {"student": enrolled_student.id, "pages": [make_uploaded_file()]},
            format="multipart",
        )
        assert response.status_code == 403
