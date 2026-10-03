"""
Shared settings. dev.py / prod.py / test.py import * from here and override
only what genuinely differs per environment.
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-only-insecure-key-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "pgvector.django",
    # Local apps
    "apps.core",
    "apps.accounts",
    "apps.exams",
    "apps.students",
    "apps.evaluation",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ── Database ─────────────────────────────────────────────────────────────
# psycopg 3 via django's native "postgresql" engine (Django 5 talks to psycopg3
# directly — no separate django-psycopg2 shim needed).
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://evalsys:evalsys@localhost:5432/evalsys",
    )
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── DRF ──────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    # No pagination class: every list endpoint the frontend calls expects a
    # flat JSON array (Exam[], Student[], SheetListItem[] — see
    # frontend/src/types/api.ts) and reads `response.data` directly. A
    # PageNumberPagination default would silently wrap that in
    # {count, next, previous, results} and break every list screen at once.
    # Class sizes here are ~50-70 and exam counts are small; this is never a
    # real scaling concern for this project.
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.ScopedRateThrottle",),
    "DEFAULT_THROTTLE_RATES": {
        # apps/accounts throttles login/register explicitly via `scope=`.
        "auth": "20/min",
    },
    "EXCEPTION_HANDLER": "apps.core.exceptions.field_keyed_exception_handler",
    # DecimalFields (Question.max_marks) must serialize as JSON numbers, not
    # strings — the frontend types every marks field as `number`.
    "COERCE_DECIMAL_TO_STRING": False,
}

# ── SimpleJWT ────────────────────────────────────────────────────────────
# Rotation + blacklist on: presenting a used refresh token must fail. This is
# what the frontend's single-flight-refresh test (frontend/src/tests/auth.test.ts)
# exercises — a naive non-rotating setup would hide that bug entirely.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ── CORS ─────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:5173"])

# ── Celery ───────────────────────────────────────────────────────────────
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/1")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
# A stuck NIM call must not wedge the worker forever — soft limit lets the task
# catch TimeLimitExceeded and mark the sheet FAILED with a message (B7); the
# hard limit is the backstop if it doesn't.
#
# 120s was sized for the mock provider (near-instant). Measured against the
# real NIM provider (2026-08-17): a SINGLE question with 5 concepts took
# 148.5s just for L6-L8 scoring (triple-pass LLM coverage voting isn't
# free — each concept is 3 real round-trips), on top of whatever L1-L5
# CV/OCR/VLM work that question's block needed. A real exam has several
# questions, evaluated one after another, not in parallel — so the budget
# has to cover the WHOLE sheet, not one question. Generous on purpose — a
# sheet finishing early costs nothing; a sheet killed mid-evaluation loses
# a teacher's completed work and needs a manual retry.
CELERY_TASK_SOFT_TIME_LIMIT = 600
CELERY_TASK_TIME_LIMIT = 660
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
# ACKS_LATE means a task a worker was holding when it died gets redelivered
# to another worker — but only once Redis (acting as the broker) considers
# that message's delivery attempt expired. Celery's own default for that,
# on a Redis broker, is 3600s (1 hour) — far longer than
# CELERY_TASK_TIME_LIMIT above, so a worker that's SIGKILLed (not a clean
# timeout: an OOM kill, a forced process stop, a crashed pool) can leave a
# sheet showing QUEUED with no worker actually holding it for up to an
# hour before anything else picks it up. Observed directly (2026-10-01).
# Set close to the task's own time limit instead: long enough that a
# genuinely still-running task is never prematurely considered dead and
# redelivered to a second worker, short enough that a truly abandoned one
# doesn't make a teacher watch a stuck spinner for the better part of an
# hour.
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": CELERY_TASK_TIME_LIMIT + 120}

# ── Uploads ──────────────────────────────────────────────────────────────
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_CONTENT_TYPES = ["image/jpeg", "image/png", "application/pdf"]
# Per-file size alone doesn't bound total work: nothing capped how many
# files (or how many pages inside one PDF) a single upload could contain —
# a teacher account could submit an unbounded number of 10 MB files, or one
# PDF with hundreds of pages, each rendered at 200 DPI by the single Celery
# worker. These two together cap that.
MAX_UPLOAD_PAGE_COUNT = 20
MAX_UPLOAD_TOTAL_SIZE_BYTES = 40 * 1024 * 1024

# ── Evaluation pipeline (stub, Phase B3; real pipeline lands in B6) ──────
# Seconds slept between each of the 12 stub stages so a human watching the
# stepper in the browser can see it move. config/settings/test.py sets this
# near zero — under CELERY_TASK_ALWAYS_EAGER, `.delay()` runs the task
# synchronously inside the test's own request, so a human-paced delay here
# would make every upload-touching test take 4+ seconds for nothing.
PIPELINE_STAGE_DELAY_SECONDS = 0.1
# Production extraction is VLM-first: one vision call receives the complete
# page and returns question blocks, text, content type, annotations, and
# confidence. Tests can disable this temporarily to retain the CV/Tesseract
# regression path while the new structured extractor is tested independently.
VLM_FIRST_EXTRACTION = env.bool("VLM_FIRST_EXTRACTION", default=True)

# ── AI provider selection ───────────────────────────────────────────────
# mock | nim | ollama — see ai/providers/. Forced to "mock" under pytest
# regardless of this value (config/settings/test.py), so CI never touches
# the network even if a stray .env sets this to "nim".
LLM_PROVIDER = env("LLM_PROVIDER", default="mock")
NIM_API_KEY = env("NIM_API_KEY", default="")
NIM_BASE_URL = env("NIM_BASE_URL", default="https://integrate.api.nvidia.com/v1")
