from django.db import migrations, models


NEW_LEVELS = {
    1: {'level_name': 'Novice', 'interval_days': 1, 'points_to_promote': 2, 'is_hidden': False},
    2: {'level_name': 'Familiar', 'interval_days': 3, 'points_to_promote': 4, 'is_hidden': False},
    3: {'level_name': 'Confident', 'interval_days': 7, 'points_to_promote': 7, 'is_hidden': False},
    4: {'level_name': 'Proficient', 'interval_days': 10, 'points_to_promote': 10, 'is_hidden': False},
    5: {'level_name': 'Mastered', 'interval_days': 17, 'points_to_promote': 15, 'is_hidden': False},
    6: {'level_name': 'Long-Term Retention', 'interval_days': 30, 'points_to_promote': 25, 'is_hidden': True},
    7: {'level_name': 'Long-Term Mastery', 'interval_days': 60, 'points_to_promote': 999, 'is_hidden': True},
}

OLD_INTERVALS = {
    1: 1,
    2: 3,
    3: 7,
    4: 10,
    5: 20,
}


def apply_mastery_schedule(apps, schema_editor):
    MasteryLevel = apps.get_model('vocabulary', 'MasteryLevel')
    for level_id, values in NEW_LEVELS.items():
        MasteryLevel.objects.update_or_create(level_id=level_id, defaults=values)


def revert_mastery_schedule(apps, schema_editor):
    MasteryLevel = apps.get_model('vocabulary', 'MasteryLevel')
    MasteryLevel.objects.filter(level_id__in=[6, 7]).delete()
    for level_id, interval_days in OLD_INTERVALS.items():
        defaults = {
            'interval_days': interval_days,
            'is_hidden': False,
        }
        if level_id == 5:
            defaults['points_to_promote'] = 999
        MasteryLevel.objects.filter(level_id=level_id).update(**defaults)


class Migration(migrations.Migration):

    dependencies = [
        ('vocabulary', '0016_add_visual_scene_and_creative_direction_step'),
    ]

    operations = [
        migrations.AddField(
            model_name='masterylevel',
            name='is_hidden',
            field=models.BooleanField(
                default=False,
                help_text='Hidden levels are used for scheduling but not shown in student mastery summaries.',
            ),
        ),
        migrations.RunPython(apply_mastery_schedule, revert_mastery_schedule),
    ]
