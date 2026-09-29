from django.contrib import admin

from .models import Enrollment, Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ["usn", "name", "email", "user"]
    search_fields = ["usn", "name", "email"]


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ["student", "exam", "created_at"]
    list_filter = ["exam"]
