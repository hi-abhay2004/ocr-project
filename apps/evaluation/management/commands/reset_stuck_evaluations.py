from django.core.management.base import BaseCommand
from apps.evaluation.models import AnswerSheet

class Command(BaseCommand):
    help = 'Resets answer sheets stuck in RUNNING back to FAILED'

    def handle(self, *args, **options):
        stuck_sheets = AnswerSheet.objects.filter(status=AnswerSheet.Status.RUNNING)
        count = stuck_sheets.count()
        stuck_sheets.update(
            status=AnswerSheet.Status.FAILED,
            error_message="Task automatically reset: worker was killed or disconnected during evaluation."
        )
        self.stdout.write(self.style.SUCCESS(f'Successfully reset {count} stuck sheets.'))
