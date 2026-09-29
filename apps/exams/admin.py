from django.contrib import admin

from .models import Concept, Exam, Question


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    fields = ["number", "text", "max_marks", "concepts_indexed_at"]
    readonly_fields = ["concepts_indexed_at"]


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ["name", "subject", "teacher", "exam_date", "total_marks"]
    list_filter = ["subject"]
    search_fields = ["name", "subject"]
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["exam", "number", "max_marks", "concepts_indexed_at"]
    list_filter = ["exam"]


@admin.register(Concept)
class ConceptAdmin(admin.ModelAdmin):
    list_display = ["question", "text", "weight", "order"]
    list_filter = ["question__exam"]
