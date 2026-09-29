from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model, set as AUTH_USER_MODEL from the very first migration —
    swapping it later requires a fresh database, so it exists in full here even
    though registration/login (apps.accounts.views) is built in Phase B1.
    """

    class Role(models.TextChoices):
        TEACHER = "TEACHER", "Teacher"
        STUDENT = "STUDENT", "Student"

    role = models.CharField(max_length=10, choices=Role.choices)
    department = models.CharField(max_length=100, blank=True, default="")
    # The signup form (frontend/src/pages/Signup.tsx) collects one "Full name"
    # field, not first/last — storing it as a single field avoids a lossy
    # split/rejoin through AbstractUser's first_name/last_name.
    full_name = models.CharField(max_length=150, blank=True, default="")

    def __str__(self):
        return f"{self.username} ({self.role})"
