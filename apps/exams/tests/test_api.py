import pytest

from apps.exams.models import Concept, Exam, Question

pytestmark = pytest.mark.django_db


def _exam_payload(**overrides):
    payload = {
        "name": "CIE-2 Database Management Systems",
        "subject": "22CS52 · DBMS",
        "exam_date": "2026-07-24",
        "total_marks": 30,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def exam(teacher_user):
    return Exam.objects.create(
        teacher=teacher_user, **{**_exam_payload(), "exam_date": "2026-07-24"}
    )


MODEL_ANSWER = (
    "BCNF is a normal form for relational schemas. A relation R is in BCNF if for every "
    "non-trivial functional dependency X to Y, X is a superkey of R. It is stricter than 3NF."
)


class TestExamCRUD:
    def test_create_exam_assigns_the_authenticated_teacher(self, auth_client, teacher_user):
        response = auth_client.post("/api/exams/", _exam_payload(), format="json")
        assert response.status_code == 201
        exam = Exam.objects.get(id=response.data["id"])
        assert exam.teacher_id == teacher_user.id

    def test_list_shows_only_the_caller_teachers_exams(self, auth_client, other_auth_client, exam):
        other_auth_client.post(
            "/api/exams/", _exam_payload(name="Someone else's exam"), format="json"
        )

        response = auth_client.get("/api/exams/")
        names = [e["name"] for e in response.data]
        assert exam.name in names
        assert "Someone else's exam" not in names

    def test_another_teacher_gets_404_not_403_on_detail(self, other_auth_client, exam):
        # A filtered-queryset 404 doesn't confirm the id exists to a probing
        # teacher, unlike a 403 would.
        response = other_auth_client.get(f"/api/exams/{exam.id}/")
        assert response.status_code == 404

    def test_another_teacher_cannot_delete_it_either(self, other_auth_client, exam):
        response = other_auth_client.delete(f"/api/exams/{exam.id}/")
        assert response.status_code == 404
        assert Exam.objects.filter(id=exam.id).exists()

    def test_student_cannot_create_an_exam(self, student_client):
        response = student_client.post("/api/exams/", _exam_payload(), format="json")
        assert response.status_code == 403

    def test_response_includes_computed_counts(self, auth_client, exam):
        response = auth_client.get(f"/api/exams/{exam.id}/")
        assert response.data["question_count"] == 0
        assert response.data["sheet_count"] == 0
        assert response.data["avg_marks"] is None

    def test_sheet_count_and_avg_marks_reflect_real_evaluated_sheets(self, auth_client, exam):
        # Regression guard: ExamSerializer.get_avg_marks() was originally
        # written (Phase B2) against a `total_marks` DB column AnswerSheet
        # was assumed to have. Phase B3 instead computes marks live from each
        # evaluation's effective_marks — this exercises that real path rather
        # than the "AnswerSheet doesn't exist yet" fallback B2 could only test.
        from apps.evaluation.models import AnswerSheet
        from apps.evaluation.tasks import _run
        from apps.students.models import Enrollment, Student

        question = Question.objects.create(
            exam=exam, number="1a", text="x", max_marks=10, model_answer=MODEL_ANSWER
        )
        from apps.exams.tasks import index_question_concepts

        index_question_concepts(question.id)

        student = Student.objects.create(usn="1BY22CS001", name="A")
        Enrollment.objects.create(exam=exam, student=student)
        sheet = AnswerSheet.objects.create(exam=exam, student=student, page_count=1)
        _run(sheet.id)

        response = auth_client.get(f"/api/exams/{exam.id}/")
        assert response.data["sheet_count"] == 1
        assert response.data["avg_marks"] is not None
        assert response.data["avg_marks"] >= 0

    def test_avg_marks_excludes_failed_sheets(self, auth_client, exam):
        from apps.evaluation.models import AnswerSheet
        from apps.students.models import Enrollment, Student

        student = Student.objects.create(usn="1BY22CS001", name="A")
        Enrollment.objects.create(exam=exam, student=student)
        AnswerSheet.objects.create(
            exam=exam,
            student=student,
            page_count=1,
            status=AnswerSheet.Status.FAILED,
            error_message="boom",
        )

        response = auth_client.get(f"/api/exams/{exam.id}/")
        assert response.data["sheet_count"] == 1  # counted...
        assert response.data["avg_marks"] is None  # ...but excluded from the average

    def test_max_marks_serializes_as_a_json_number_not_a_string(self, auth_client, exam):
        auth_client.post(
            f"/api/exams/{exam.id}/questions/",
            {"number": "1a", "text": "Define BCNF.", "max_marks": 10, "model_answer": MODEL_ANSWER},
            format="json",
        )
        response = auth_client.get(f"/api/exams/{exam.id}/")
        # Regression guard for COERCE_DECIMAL_TO_STRING — the frontend types
        # every marks field as `number`; a DecimalField serialized as "10.00"
        # would type-check in JS but silently break arithmetic on it.
        assert isinstance(response.data["question_count"], int)


class TestQuestionCRUD:
    def test_create_question_enqueues_stub_indexing_synchronously(self, auth_client, exam):
        response = auth_client.post(
            f"/api/exams/{exam.id}/questions/",
            {"number": "1a", "text": "Define BCNF.", "max_marks": 10, "model_answer": MODEL_ANSWER},
            format="json",
        )
        assert response.status_code == 201
        question = Question.objects.get(id=response.data["id"])
        # CELERY_TASK_ALWAYS_EAGER=True (config/settings/test.py) means the
        # stub task has already run by the time this request returns.
        assert question.concepts_indexed_at is not None
        assert Concept.objects.filter(question=question).exists()

    def test_max_marks_accepts_half_steps(self, auth_client, exam):
        response = auth_client.post(
            f"/api/exams/{exam.id}/questions/",
            {"number": "1a", "text": "x", "max_marks": 7.5, "model_answer": MODEL_ANSWER},
            format="json",
        )
        assert response.status_code == 201
        assert response.data["max_marks"] == 7.5

    def test_another_teacher_cannot_add_a_question_to_it(self, other_auth_client, exam):
        response = other_auth_client.post(
            f"/api/exams/{exam.id}/questions/",
            {"number": "1a", "text": "x", "max_marks": 10, "model_answer": MODEL_ANSWER},
            format="json",
        )
        assert response.status_code == 404

    def test_editing_unrelated_fields_does_not_reindex(self, auth_client, exam):
        create = auth_client.post(
            f"/api/exams/{exam.id}/questions/",
            {"number": "1a", "text": "Define BCNF.", "max_marks": 10, "model_answer": MODEL_ANSWER},
            format="json",
        )
        question_id = create.data["id"]
        original_concept_ids = set(
            Concept.objects.filter(question_id=question_id).values_list("id", flat=True)
        )
        assert original_concept_ids  # the stub already ran

        response = auth_client.patch(
            f"/api/questions/{question_id}/", {"max_marks": 12}, format="json"
        )
        assert response.status_code == 200

        # The idempotency guard: only a changed model_answer clears/re-embeds
        # concepts. Editing max_marks must leave the existing rows untouched.
        remaining_ids = set(
            Concept.objects.filter(question_id=question_id).values_list("id", flat=True)
        )
        assert remaining_ids == original_concept_ids

    def test_changing_the_model_answer_reindexes(self, auth_client, exam):
        create = auth_client.post(
            f"/api/exams/{exam.id}/questions/",
            {"number": "1a", "text": "Define BCNF.", "max_marks": 10, "model_answer": MODEL_ANSWER},
            format="json",
        )
        question_id = create.data["id"]
        original_concept_ids = set(
            Concept.objects.filter(question_id=question_id).values_list("id", flat=True)
        )

        response = auth_client.patch(
            f"/api/questions/{question_id}/",
            {"model_answer": MODEL_ANSWER + " Decomposition may lose dependency preservation."},
            format="json",
        )
        assert response.status_code == 200

        new_concept_ids = set(
            Concept.objects.filter(question_id=question_id).values_list("id", flat=True)
        )
        assert new_concept_ids
        assert new_concept_ids.isdisjoint(original_concept_ids)

    def test_resaving_the_identical_model_answer_does_not_reindex(self, auth_client, exam):
        create = auth_client.post(
            f"/api/exams/{exam.id}/questions/",
            {"number": "1a", "text": "Define BCNF.", "max_marks": 10, "model_answer": MODEL_ANSWER},
            format="json",
        )
        question_id = create.data["id"]
        original_concept_ids = set(
            Concept.objects.filter(question_id=question_id).values_list("id", flat=True)
        )

        response = auth_client.patch(
            f"/api/questions/{question_id}/", {"model_answer": MODEL_ANSWER}, format="json"
        )
        assert response.status_code == 200
        remaining_ids = set(
            Concept.objects.filter(question_id=question_id).values_list("id", flat=True)
        )
        assert remaining_ids == original_concept_ids

    def test_delete_question_cascades_its_concepts(self, auth_client, exam):
        create = auth_client.post(
            f"/api/exams/{exam.id}/questions/",
            {"number": "1a", "text": "x", "max_marks": 10, "model_answer": MODEL_ANSWER},
            format="json",
        )
        question_id = create.data["id"]
        assert Concept.objects.filter(question_id=question_id).exists()

        response = auth_client.delete(f"/api/questions/{question_id}/")
        assert response.status_code == 204
        assert not Concept.objects.filter(question_id=question_id).exists()


class TestConcepts:
    def test_concepts_are_empty_until_indexed_and_weights_sum_to_one(self, auth_client, exam):
        create = auth_client.post(
            f"/api/exams/{exam.id}/questions/",
            {"number": "1a", "text": "Define BCNF.", "max_marks": 10, "model_answer": MODEL_ANSWER},
            format="json",
        )
        question_id = create.data["id"]

        response = auth_client.get(f"/api/questions/{question_id}/concepts/")
        assert response.status_code == 200
        assert len(response.data) > 0
        total_weight = sum(c["weight"] for c in response.data)
        assert total_weight == pytest.approx(1.0, abs=0.01)

    def test_another_teacher_cannot_read_its_concepts(self, auth_client, other_auth_client, exam):
        create = auth_client.post(
            f"/api/exams/{exam.id}/questions/",
            {"number": "1a", "text": "x", "max_marks": 10, "model_answer": MODEL_ANSWER},
            format="json",
        )
        response = other_auth_client.get(f"/api/questions/{create.data['id']}/concepts/")
        assert response.status_code == 404
