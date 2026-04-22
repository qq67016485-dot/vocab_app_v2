from django.db import migrations


def update_intervals(apps, schema_editor):
    MasteryLevel = apps.get_model('vocabulary', 'MasteryLevel')
    new_intervals = {
        1: 1,
        2: 3,
        3: 7,
        4: 10,
        5: 20,
    }
    for level_id, interval in new_intervals.items():
        MasteryLevel.objects.filter(level_id=level_id).update(interval_days=interval)


def revert_intervals(apps, schema_editor):
    MasteryLevel = apps.get_model('vocabulary', 'MasteryLevel')
    old_intervals = {
        1: 0,
        2: 1,
        3: 3,
        4: 7,
        5: 14,
    }
    for level_id, interval in old_intervals.items():
        MasteryLevel.objects.filter(level_id=level_id).update(interval_days=interval)


class Migration(migrations.Migration):

    dependencies = [
        ('vocabulary', '0012_add_retry_count_to_useranswer'),
    ]

    operations = [
        migrations.RunPython(update_intervals, revert_intervals),
    ]
