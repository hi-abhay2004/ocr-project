import pytest

from apps.exams.models import Exam, Question
from apps.students.models import Enrollment, Student

MODEL_ANSWER = (
    "BCNF is a normal form for relational schemas. A relation R is in BCNF if for every "
    "non-trivial functional dependency X to Y, X must be a superkey of R. It is stricter "
    "than 3NF and removes redundancy caused by transitive dependencies."
)


@pytest.fixture
def exam(teacher_user):
    return Exam.objects.create(
        teacher=teacher_user,
        name="CIE-2 DBMS",
        subject="22CS52",
        exam_date="2026-07-24",
        total_marks=30,
    )


@pytest.fixture
def question(exam):
    """CELERY_TASK_ALWAYS_EAGER=True means index_question_concepts already
    ran synchronously by the time .create() below returns — concepts exist
    immediately, no polling needed in tests."""
    from apps.exams.tasks import index_question_concepts

    q = Question.objects.create(
        exam=exam, number="1a", text="Define BCNF.", max_marks=10, model_answer=MODEL_ANSWER
    )
    index_question_concepts(q.id)
    q.refresh_from_db()
    return q


@pytest.fixture
def student():
    return Student.objects.create(
        usn="1BY22CS001", name="P Charan Chandra", email="charan@bmsit.in"
    )


@pytest.fixture
def enrolled_student(exam, student):
    Enrollment.objects.create(exam=exam, student=student)
    return student


@pytest.fixture
def evaluated_sheet(exam, question, enrolled_student):
    """A DONE sheet with a real Evaluation AND a real uploaded page (so its
    blocks/annotations are real too, not empty) — for tests about
    override/approve/results that don't care about upload mechanics
    themselves. Runs the pipeline directly rather than through the API to
    keep those tests focused."""
    from django.core.files.base import ContentFile

    from apps.evaluation.models import AnswerSheet, SheetPage
    from apps.evaluation.tasks import _run

    sheet = AnswerSheet.objects.create(exam=exam, student=enrolled_student, page_count=1)
    page = SheetPage(sheet=sheet, index=0)
    page.image.save("page1.png", ContentFile(render_answer_page_png()), save=True)

    _run(sheet.id)
    sheet.refresh_from_db()
    return sheet


def render_answer_page_png() -> bytes:
    """A REAL rendered page — question number "1a" (matching the `question`
    fixture above), one sentence VERBATIM from MODEL_ANSWER's first concept
    (so ai.pipeline's real L6-L8 scoring has something a mock embedding can
    actually match), and one struck-out word (so L3/L3.5 has a real mark to
    find). This is what apps.evaluation.pipeline_runner's real L1-L5 chain
    actually segments/detects/OCRs/reconstructs — not a stand-in blob."""
    import cv2

    from tests.unit.cv_fixtures import draw_strike, numbered_answer_page

    img, _layout = numbered_answer_page(
        [
            (
                "1a)",
                [
                    "BCNF is a normal form for relational schemas.",
                    "It removes redundancy from the schema design.",
                ],
            )
        ]
    )
    # Strike out "redundancy" on the second line (its real bbox, from a
    # clean OCR pass over this exact render) — a real mark for the real
    # detector to find, not an injected Annotation row.
    box = {"x": 234, "y": 136, "w": 194, "h": 34}
    draw_strike(img, box)

    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def render_unlabelled_answer_page_png() -> bytes:
    """A real page with real answer content but NO question-number label
    at all — what a student's upload looks like when they just write the
    answer straight onto the page (common with a single-question exam,
    where there's no real question to number). Verified (2026-08-27)
    against a real upload doing exactly this: without the single-question
    fallback in apps.evaluation.pipeline_runner.create_real_evaluations,
    this content never matches any question and the sheet silently scores
    every concept MISSING."""
    import cv2

    from tests.unit.cv_fixtures import numbered_answer_page

    img, _layout = numbered_answer_page(
        [
            (
                "",
                [
                    "BCNF is a normal form for relational schemas.",
                    "It removes redundancy from the schema design.",
                ],
            )
        ]
    )
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def render_mislabelled_answer_page_png() -> bytes:
    """A real page with a CONFIDENT but WRONG question-number label —
    what a real upload looks like when the number-reader (Tesseract, or
    its VLM fallback on handwritten/unusual labels) misreads the actual
    number rather than finding nothing. Verified (2026-08-28) against a
    real upload where a handwritten circled "1" was read back as "1a":
    the single-question fallback originally only re-homed content that
    matched NO question at all, which doesn't cover a confident wrong
    match at all — this fixture's "2)" label never matches the `question`
    fixture's real number ("1a") the same way."""
    import cv2

    from tests.unit.cv_fixtures import numbered_answer_page

    img, _layout = numbered_answer_page(
        [
            (
                "2)",
                [
                    "BCNF is a normal form for relational schemas.",
                    "It removes redundancy from the schema design.",
                ],
            )
        ]
    )
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def make_uploaded_file(name="page1.png"):
    """Deliberately NOT a 1x1 pixel: a blank page is real input too (see
    make_blank_uploaded_file / test_a_blank_page_still_produces_an_evaluation_with_no_content),
    but most tests want something for the real CV pipeline to actually find."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, render_answer_page_png(), content_type="image/png")


def make_blank_uploaded_file(name="blank.png"):
    """A genuinely blank page — real bytes, real dimensions, but nothing
    for segmentation to find. What "the student left this question
    unanswered" looks like to the real pipeline."""
    import cv2
    from django.core.files.uploadedfile import SimpleUploadedFile

    from tests.unit.cv_fixtures import blank_page

    ok, buf = cv2.imencode(".png", blank_page())
    return SimpleUploadedFile(name, buf.tobytes(), content_type="image/png")


def make_unlabelled_uploaded_file(name="unlabelled.png"):
    """Real answer content, no question-number label — see
    render_unlabelled_answer_page_png()."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(
        name, render_unlabelled_answer_page_png(), content_type="image/png"
    )


def make_mislabelled_uploaded_file(name="mislabelled.png"):
    """Real answer content under a confident but WRONG question-number
    label — see render_mislabelled_answer_page_png()."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(
        name, render_mislabelled_answer_page_png(), content_type="image/png"
    )
