"""
Add adaptive interval support:
- Rename next_review_date (DateField) → next_review_at (DateTimeField)
- Add learning_speed field to UserWordProgress
- Backfill existing dates to midnight datetimes
"""
from django.db import migrations, models
from django.utils import timezone as tz


def backfill_next_review_at(apps, schema_editor):
    UserWordProgress = apps.get_model('vocabulary', 'UserWordProgress')
    for progress in UserWordProgress.objects.all().iterator(chunk_size=500):
        if progress.next_review_at is None and progress.next_review_date is not None:
            progress.next_review_at = tz.make_aware(
                tz.datetime.combine(progress.next_review_date, tz.datetime.min.time())
            )
            progress.save(update_fields=['next_review_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('vocabulary', '0013_update_mastery_level_intervals'),
    ]

    operations = [
        # Step 1: Add learning_speed
        migrations.AddField(
            model_name='userwordprogress',
            name='learning_speed',
            field=models.FloatField(
                default=1.0,
                help_text='Per-student-word adaptive multiplier for review intervals.',
            ),
        ),
        # Step 2: Add new DateTimeField (nullable initially for backfill)
        migrations.AddField(
            model_name='userwordprogress',
            name='next_review_at',
            field=models.DateTimeField(null=True),
        ),
        # Step 3: Backfill from old DateField
        migrations.RunPython(backfill_next_review_at, migrations.RunPython.noop),
        # Step 4: Remove old DateField
        migrations.RemoveField(
            model_name='userwordprogress',
            name='next_review_date',
        ),
        # Step 5: Make new field non-nullable
        migrations.AlterField(
            model_name='userwordprogress',
            name='next_review_at',
            field=models.DateTimeField(),
        ),
    ]
