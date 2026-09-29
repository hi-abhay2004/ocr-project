import pytest

from apps.accounts.models import User
from apps.exams.models import Exam
from apps.students.models import Enrollment, Student

pytestmark = pytest.mark.django_db


@pytest.fixture
def exam(teacher_user):
    return Exam.objects.create(
        teacher=teacher_user,
        name="CIE-2 DBMS",
        subject="22CS52",
        exam_date="2026-07-24",
        total_marks=30,
    )


def _import(client, exam, rows):
    return client.post(f"/api/exams/{exam.id}/students/import/", {"rows": rows}, format="json")


class TestManualAdd:
    def test_add_creates_and_enrolls(self, auth_client, exam):
        response = auth_client.post(
            f"/api/exams/{exam.id}/students/",
            {"usn": "1BY22CS001", "name": "P Charan Chandra", "email": "charan@bmsit.in"},
            format="json",
        )
        assert response.status_code == 201
        student = Student.objects.get(usn="1BY22CS001")
        assert Enrollment.objects.filter(exam=exam, student=student).exists()

    def test_add_rejects_a_usn_that_already_exists_anywhere(self, auth_client, exam):
        Student.objects.create(usn="1BY22CS001", name="Existing")

        response = auth_client.post(
            f"/api/exams/{exam.id}/students/",
            {"usn": "1BY22CS001", "name": "Someone New", "email": ""},
            format="json",
        )
        # Manual add is stricter than CSV import: a duplicate USN here is
        # rejected outright, never silently linked.
        assert response.status_code == 400
        assert "usn" in response.data

    def test_another_teacher_cannot_add_to_it(self, other_auth_client, exam):
        response = other_auth_client.post(
            f"/api/exams/{exam.id}/students/",
            {"usn": "1BY22CS001", "name": "X", "email": ""},
            format="json",
        )
        assert response.status_code == 404


class TestList:
    def test_lists_only_students_enrolled_in_this_exam(self, auth_client, exam):
        enrolled = Student.objects.create(usn="1BY22CS001", name="Enrolled")
        Enrollment.objects.create(exam=exam, student=enrolled)
        Student.objects.create(usn="1BY22CS002", name="Not enrolled here")

        response = auth_client.get(f"/api/exams/{exam.id}/students/")
        usns = [s["usn"] for s in response.data]
        assert usns == ["1BY22CS001"]


class TestRemove:
    def test_delete_removes_enrolment_but_not_the_student(self, auth_client, exam):
        student = Student.objects.create(usn="1BY22CS001", name="A")
        Enrollment.objects.create(exam=exam, student=student)

        response = auth_client.delete(f"/api/exams/{exam.id}/students/{student.id}/")
        assert response.status_code == 204
        assert not Enrollment.objects.filter(exam=exam, student=student).exists()
        assert Student.objects.filter(id=student.id).exists()

    def test_another_teacher_cannot_delete_the_enrollment(self, other_auth_client, exam):
        student = Student.objects.create(usn="1BY22CS001", name="A")
        Enrollment.objects.create(exam=exam, student=student)

        response = other_auth_client.delete(f"/api/exams/{exam.id}/students/{student.id}/")
        assert response.status_code == 404
        assert Enrollment.objects.filter(exam=exam, student=student).exists()


class TestCsvImport:
    def test_imports_valid_rows(self, auth_client, exam):
        response = _import(
            auth_client,
            exam,
            [
                {"usn": "1BY22CS001", "name": "P Charan Chandra", "email": "charan@bmsit.in"},
                {"usn": "1BY22CS002", "name": "R T Kesav Reddy", "email": "kesav@bmsit.in"},
            ],
        )
        assert response.status_code == 200
        assert response.data == {"created": 2, "skipped": 0, "errors": []}
        assert Enrollment.objects.filter(exam=exam).count() == 2

    def test_one_bad_row_does_not_block_the_rest(self, auth_client, exam):
        # This is the whole point of the row-by-row design in the view: a DRF
        # `many=True` batch validator would 400 the ENTIRE request the moment
        # any one row fails, losing every good row along with the bad one.
        response = _import(
            auth_client,
            exam,
            [
                {"usn": "1BY22CS001", "name": "Good Row", "email": ""},
                {"usn": "!!", "name": "Bad USN", "email": ""},
                {"usn": "1BY22CS002", "name": "Also Good", "email": ""},
            ],
        )
        assert response.status_code == 200
        assert response.data["created"] == 2
        assert response.data["skipped"] == 1
        assert "malformed" in response.data["errors"][0]["message"]
        assert Student.objects.filter(usn="1BY22CS001").exists()
        assert Student.objects.filter(usn="1BY22CS002").exists()

    def test_duplicate_usn_within_the_file_is_flagged(self, auth_client, exam):
        response = _import(
            auth_client,
            exam,
            [
                {"usn": "1BY22CS001", "name": "First", "email": ""},
                {"usn": "1BY22CS001", "name": "Duplicate", "email": ""},
            ],
        )
        assert response.data["created"] == 1
        assert response.data["skipped"] == 1
        assert "duplicate" in response.data["errors"][0]["message"].lower()

    def test_missing_name_is_flagged(self, auth_client, exam):
        response = _import(auth_client, exam, [{"usn": "1BY22CS001", "name": "", "email": ""}])
        assert response.data["skipped"] == 1
        assert "name" in response.data["errors"][0]["message"].lower()

    def test_invalid_email_is_flagged_but_blank_email_is_fine(self, auth_client, exam):
        response = _import(
            auth_client,
            exam,
            [
                {"usn": "1BY22CS001", "name": "Bad Email", "email": "not-an-email"},
                {"usn": "1BY22CS002", "name": "No Email", "email": ""},
            ],
        )
        assert response.data["created"] == 1
        assert response.data["skipped"] == 1
        assert "email" in response.data["errors"][0]["message"].lower()

    def test_existing_unclaimed_student_is_linked_not_rejected(self, auth_client, exam):
        # Unlike manual add, import treats a pre-existing global Student as a
        # link, not a conflict — a class list legitimately overlaps with
        # students who already have accounts or other enrolments.
        Student.objects.create(usn="1BY22CS001", name="Already exists globally")

        response = _import(
            auth_client, exam, [{"usn": "1BY22CS001", "name": "Ignored on link", "email": ""}]
        )
        assert response.data["created"] == 1
        assert response.data["skipped"] == 0
        assert Enrollment.objects.filter(exam=exam, student__usn="1BY22CS001").exists()

    def test_reimporting_the_same_row_is_skipped_as_already_enrolled(self, auth_client, exam):
        rows = [{"usn": "1BY22CS001", "name": "A", "email": ""}]
        _import(auth_client, exam, rows)
        response = _import(auth_client, exam, rows)

        assert response.data["created"] == 0
        assert response.data["skipped"] == 1
        assert "already enrolled" in response.data["errors"][0]["message"]

    def test_another_teacher_cannot_import_into_it(self, other_auth_client, exam):
        response = _import(
            other_auth_client, exam, [{"usn": "1BY22CS001", "name": "X", "email": ""}]
        )
        assert response.status_code == 404


class TestRegistrationLinksAcrossPhaseB1:
    def test_a_csv_imported_student_can_later_sign_up_and_claim_their_row(self, auth_client, exam):
        # End-to-end continuity check across B1 and B2: a teacher imports the
        # class list first, and the student signs up afterward.
        _import(auth_client, exam, [{"usn": "1BY22CS077", "name": "A Deepika", "email": ""}])

        from rest_framework.test import APIClient

        response = APIClient().post(
            "/api/auth/register/",
            {
                "username": "deepika",
                "full_name": "A Deepika",
                "email": "deepika@bmsit.in",
                "password": "correct-horse-battery",
                "role": "STUDENT",
                "usn": "1by22cs077",
            },
            format="json",
        )
        assert response.status_code == 201
        student = Student.objects.get(usn="1BY22CS077")
        assert student.user is not None
        assert User.objects.get(username="deepika").id == student.user_id
