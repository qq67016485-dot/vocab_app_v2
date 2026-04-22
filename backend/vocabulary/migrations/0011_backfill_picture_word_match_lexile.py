from django.db import migrations

LEXILE_OFFSET = 0.85
DEFAULT_LEXILE = 650


def backfill_picture_word_match_lexile(apps, schema_editor):
    Question = apps.get_model('vocabulary', 'Question')
    qs = Question.objects.filter(
        question_type='PICTURE_WORD_MATCH',
        lexile_score__isnull=True,
    ).select_related('generation_job')

    to_update = []
    for q in qs:
        if q.generation_job_id and q.generation_job:
            lexile = int(q.generation_job.target_lexile * LEXILE_OFFSET)
        else:
            lexile = int(DEFAULT_LEXILE * LEXILE_OFFSET)
        q.lexile_score = lexile
        to_update.append(q)

    if to_update:
        Question.objects.bulk_update(to_update, ['lexile_score'])


class Migration(migrations.Migration):

    dependencies = [
        ('vocabulary', '0010_level_curriculum_alter_level_name_and_more'),
    ]

    operations = [
        migrations.RunPython(
            backfill_picture_word_match_lexile,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
