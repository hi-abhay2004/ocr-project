"""
CI never touches the network — this file is the enforcement point.

Regardless of what a stray .env or CI secret sets LLM_PROVIDER to, tests always
run against ai/providers/mock.py. Real-provider tests are @pytest.mark.slow and
select a different provider explicitly inside the test, never via settings.
"""

import os

from .base import *  # noqa: F403

DEBUG = False
LLM_PROVIDER = "mock"
# The Django setting above is NOT enough on its own: ai/providers/factory.py
# reads os.environ directly, not settings.LLM_PROVIDER — deliberately, since
# ai/ has no Django dependency at all. base.py's environ.Env.read_env()
# already wrote .env's LLM_PROVIDER into os.environ by the time this module
# runs, so without this line, a real LLM_PROVIDER=nim in .env silently wins
# and the "tests never touch the network" promise above is just a comment,
# not something enforced (verified: this exact gap sent the full suite to
# the real NIM API and back with rate-limit errors once .env's default
# stopped being "mock").
os.environ["LLM_PROVIDER"] = "mock"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Celery tasks run synchronously, in-process — no worker/broker needed for
# apps/*/tests/test_*.py. Real async behavior (retries, acks_late) is covered
# by running an actual worker in the B3+ manual verification, not unit tests.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

MEDIA_ROOT = BASE_DIR / "media_test"  # noqa: F405

# See the comment on this setting in base.py — tests care about correctness,
# not the human-visible pacing of the pipeline stepper.
PIPELINE_STAGE_DELAY_SECONDS = 0.0
# Existing CV/Tesseract integration fixtures remain regression coverage; the
# VLM-first path has dedicated provider-free schema tests.
VLM_FIRST_EXTRACTION = False
