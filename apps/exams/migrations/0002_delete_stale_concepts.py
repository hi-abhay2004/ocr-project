# NVIDIA retired nv-embedqa-e5-v5 (2026-08-26) — see ai/config.py and
# ai/providers/nim.py. Its replacement is 2048-dim, not 1024, so every
# existing Concept's embedding is now the wrong width for the next
# migration's column-width change AND was produced by a model that no
# longer exists — there is no meaningful way to keep them.
#
# Split into its own migration, separate from the AlterField in
# 0003_alter_concept_embedding.py: doing the DELETE and the ALTER TABLE in
# one transaction fails on Postgres ("cannot ALTER TABLE ... because it has
# pending trigger events") — the DELETE queues deferred FK-constraint
# triggers (from ConceptScore/EvaluationRun's SET_NULL) that must actually
# fire before the same table can be altered.
#
# Safe to delete: apps.evaluation.models.ConceptScore/EvaluationRun both
# point at Concept via on_delete=SET_NULL with the concept's text
# snapshotted at scoring time (see those models' docstrings) — deleting
# Concept rows here does not touch any already-graded or approved result.
#
# Re-extraction: this migration does not re-populate concepts (that needs
# a real embedding-provider network call, which migrations shouldn't make)
# — apps/exams/tasks.py's index_question_concepts must be re-run for every
# affected Question afterward.

from django.db import migrations


def _delete_stale_concepts(apps, schema_editor):
    Concept = apps.get_model("exams", "Concept")
    Concept.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_delete_stale_concepts, migrations.RunPython.noop),
    ]
