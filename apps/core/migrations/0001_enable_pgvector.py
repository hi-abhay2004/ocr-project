from django.db import migrations


class Migration(migrations.Migration):
    """
    Runs first, before any app defines a VectorField. apps.exams's Concept
    migration (B2) depends on this one.
    """

    initial = True
    dependencies = []

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS vector;",
            reverse_sql="DROP EXTENSION IF EXISTS vector;",
        ),
    ]
