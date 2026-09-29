from django.urls import path

from . import views

urlpatterns = [
    path("exams/<int:exam_id>/sheets/", views.ExamSheetsView.as_view(), name="exam-sheets"),
    path("exams/<int:exam_id>/summary/", views.ExamSummaryView.as_view(), name="exam-summary"),
    path("sheets/<int:sheet_id>/status/", views.SheetStatusView.as_view(), name="sheet-status"),
    path("sheets/<int:sheet_id>/retry/", views.SheetRetryView.as_view(), name="sheet-retry"),
    path("sheets/<int:sheet_id>/approve/", views.SheetApproveView.as_view(), name="sheet-approve"),
    path("sheets/<int:sheet_id>/", views.SheetDetailView.as_view(), name="sheet-detail"),
    path(
        "evaluations/<int:evaluation_id>/",
        views.EvaluationDetailView.as_view(),
        name="evaluation-detail",
    ),
    path("results/", views.StudentResultListView.as_view(), name="result-list"),
    path("results/<int:sheet_id>/", views.StudentResultDetailView.as_view(), name="result-detail"),
]
