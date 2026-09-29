from django.contrib import admin

from .models import (
    Annotation,
    AnswerBlock,
    AnswerSheet,
    ConceptScore,
    Evaluation,
    EvaluationRun,
    SheetPage,
)


class SheetPageInline(admin.TabularInline):
    model = SheetPage
    extra = 0


class EvaluationInline(admin.TabularInline):
    model = Evaluation
    extra = 0
    fields = ["question_number", "auto_marks", "override_marks", "band"]


@admin.register(AnswerSheet)
class AnswerSheetAdmin(admin.ModelAdmin):
    list_display = ["id", "exam", "student", "status", "stage", "band", "confidence"]
    list_filter = ["status", "band", "exam"]
    inlines = [SheetPageInline, EvaluationInline]


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ["sheet", "question_number", "auto_marks", "override_marks", "band"]
    list_filter = ["band"]


admin.site.register(AnswerBlock)
admin.site.register(Annotation)
admin.site.register(ConceptScore)
admin.site.register(EvaluationRun)
