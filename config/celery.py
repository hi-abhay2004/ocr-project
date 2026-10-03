import os
import sys

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("evalsys")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Celery's default pool (prefork, via billiard) doesn't work right on
# Windows — observed 2026-10-01: a worker started with the documented
# `celery -A config worker -l info` (no --pool flag) kept spawning worker
# processes that never exited, ~30 orphaned inside an hour, enough to make
# unrelated commands on the machine fail with "insufficient system
# resources" (WinError 1450).
#
# `solo` (the first fix, same day) stopped that, but traded it for a
# different real problem, also observed the same day: solo runs exactly
# ONE task at a time, full stop, no matter how many concepts/threads
# ai.coverage uses internally — a second uploaded sheet doesn't start
# until the first is completely done. A teacher uploading several
# booklets close together watches every one past the first sit in QUEUED
# for however long the ones ahead of it take (each real-provider
# evaluation is tens of seconds to several minutes), with no sign
# anything is wrong — it reads exactly like a hung queue even though nothing
# has failed.
#
# `threads` fixes both at once: several sheets genuinely run at once
# (concurrency below), and — unlike prefork/billiard — a thread pool never
# forks OS processes, so it can't runaway-spawn orphans on Windows
# regardless of how the worker is invoked. This is what should actually be
# running in this deployment, not a stopgap.
#
# A default set HERE, rather than relying on every invocation remembering
# a CLI flag, is what actually closes the gap for good — a worker started
# a second time by someone who didn't pass `--pool`/`--concurrency`
# inherits this instead of Celery's own (Windows-broken) default. An
# explicit flag on the command line still wins over this.
if sys.platform == "win32":
    app.conf.worker_pool = "threads"
    app.conf.worker_concurrency = 4
