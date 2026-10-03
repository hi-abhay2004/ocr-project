from django.core.management.base import BaseCommand
from django.db.models import F
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.evaluation.models import AnswerSheet

# Only RUNNING was ever covered here, on the theory that a worker crash
# mid-task is the one gap evaluate_sheet's own try/except can't close. A
# QUEUED sheet has the same failure mode one step earlier: its task message
# was lost (a worker died before ever starting it, or — observed
# 2026-10-01 — a Celery pool itself was misconfigured and never
# consistently ran) and nothing ever requeues it. Both leave a sheet stuck
# forever showing a spinner. STUCK_MINUTES is generous — a healthy queue
# drains in seconds, not minutes — so this only ever catches genuinely
# abandoned sheets, not ones mid-flight on a busy worker.
STUCK_MINUTES = 15


class Command(BaseCommand):
    help = "Resets answer sheets stuck in RUNNING, or abandoned in QUEUED, back to FAILED"

    def add_arguments(self, parser):
        parser.add_argument(
            "--queued-minutes",
            type=int,
            default=STUCK_MINUTES,
            help=f"A QUEUED sheet idle longer than this (default {STUCK_MINUTES}) is considered abandoned.",
        )

    def handle(self, *args, **options):
        running = AnswerSheet.objects.filter(status=AnswerSheet.Status.RUNNING)
        running_count = running.count()
        running.update(
            status=AnswerSheet.Status.FAILED,
            error_message="Task automatically reset: worker was killed or disconnected during evaluation.",
        )

        cutoff = timezone.now() - timezone.timedelta(minutes=options["queued_minutes"])
        # A sheet's "last known activity" is last_run_started_at if it has
        # ever actually started a run, else started_at (upload time) for
        # one that's never been picked up at all.
        stuck_queued = AnswerSheet.objects.filter(status=AnswerSheet.Status.QUEUED).annotate(
            last_activity=Coalesce(F("last_run_started_at"), F("started_at"))
        ).filter(last_activity__lt=cutoff)
        queued_count = stuck_queued.count()
        stuck_queued.update(
            status=AnswerSheet.Status.FAILED,
            error_message=(
                "Task automatically reset: queued for longer than "
                f"{options['queued_minutes']} minutes with no worker picking it up."
            ),
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully reset {running_count} RUNNING and {queued_count} abandoned QUEUED sheets."
            )
        )
