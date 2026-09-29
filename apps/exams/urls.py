from django.urls import path

from apps.students import views as student_views

from . import views

urlpatterns = [
    path("exams/", views.ExamListCreateView.as_view(), name="exam-list"),
    path("exams/<int:pk>/", views.ExamDetailView.as_view(), name="exam-detail"),
    path(
        "exams/<int:exam_id>/questions/",
        views.QuestionListCreateView.as_view(),
        name="question-list",
    ),
    path("questions/<int:pk>/", views.QuestionDetailView.as_view(), name="question-detail"),
    path(
        "questions/<int:question_id>/concepts/",
        views.ConceptListView.as_view(),
        name="concept-list",
    ),
    # Student endpoints are exam-scoped in the URL but live in apps.students —
    # the resource is global (one USN, one Student row); only enrolment is
    # per-exam. See apps/students/views.py.
    path(
        "exams/<int:exam_id>/students/import/",
        student_views.ExamStudentImportView.as_view(),
        name="exam-student-import",
    ),
    path(
        "exams/<int:exam_id>/students/",
        student_views.ExamStudentListCreateView.as_view(),
        name="exam-student-list",
    ),
    path(
        "exams/<int:exam_id>/students/<int:student_id>/",
        student_views.ExamStudentDeleteView.as_view(),
        name="exam-student-delete",
    ),
]
