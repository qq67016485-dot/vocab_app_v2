import django.db.models.deletion
from django.db import migrations, models


SET_NAMES = ['Set 1', 'Set 2', 'Set 3']


def seed_sets_and_clone(apps, schema_editor):
    """Create 3 config sets, attach existing step configs to Set 1 (active),
    then clone Set 1's rows into Sets 2 and 3 so all three are usable."""
    LLMConfigSet = apps.get_model('vocabulary', 'LLMConfigSet')
    LLMStepConfig = apps.get_model('vocabulary', 'LLMStepConfig')

    sets = []
    for idx, name in enumerate(SET_NAMES, start=1):
        sets.append(LLMConfigSet.objects.create(
            name=name, position=idx, is_active=(idx == 1),
        ))
    set1, set2, set3 = sets

    # Attach pre-existing rows (config_set was just added as nullable) to Set 1.
    existing = list(LLMStepConfig.objects.filter(config_set__isnull=True))
    for row in existing:
        row.config_set = set1
        row.save(update_fields=['config_set'])

    # Clone Set 1's configs into Sets 2 and 3.
    for target in (set2, set3):
        for row in existing:
            LLMStepConfig.objects.create(
                config_set=target,
                step_key=row.step_key,
                primary_site=row.primary_site,
                primary_model=row.primary_model,
                fallback_site=row.fallback_site,
                fallback_model=row.fallback_model,
            )


def reverse_to_single_set(apps, schema_editor):
    """Keep only the active set's rows (or Set 1's) so the unique-on-step_key
    constraint can be restored, then drop all sets."""
    LLMConfigSet = apps.get_model('vocabulary', 'LLMConfigSet')
    LLMStepConfig = apps.get_model('vocabulary', 'LLMStepConfig')

    keep = LLMConfigSet.objects.filter(is_active=True).order_by('position').first()
    if keep is None:
        keep = LLMConfigSet.objects.order_by('position').first()
    if keep is not None:
        LLMStepConfig.objects.exclude(config_set=keep).delete()
        LLMStepConfig.objects.filter(config_set=keep).update(config_set=None)
    LLMConfigSet.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('vocabulary', '0030_useranswer_vocabulary__user_id_a04db8_idx_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='LLMConfigSet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('position', models.PositiveSmallIntegerField(help_text='Stable display/sort order (1-based).', unique=True)),
                ('is_active', models.BooleanField(default=False, help_text='Exactly one set is active; the pipeline uses it.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'LLM Config Set',
                'ordering': ['position'],
            },
        ),
        # Add FK as nullable first so existing rows survive, then backfill.
        migrations.AddField(
            model_name='llmstepconfig',
            name='config_set',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='step_configs',
                to='vocabulary.llmconfigset',
            ),
        ),
        # Drop the old single-set uniqueness on step_key.
        migrations.AlterField(
            model_name='llmstepconfig',
            name='step_key',
            field=models.CharField(
                choices=[
                    ('word_lookup', 'Word Lookup'), ('translation', 'Translation'),
                    ('question_gen', 'Question Generation'), ('primer_gen', 'Primer Generation'),
                    ('pack_creation', 'Pack Grouping'), ('gn_team_selection', 'GN: Team Selection'),
                    ('gn_router_premises', 'GN: Router Premises'), ('gn_premise_scoring', 'GN: Premise Scoring'),
                    ('gn_cloze_gen', 'GN: Cloze Generation'), ('gn_beat_sheet', 'GN: Beat Sheet'),
                    ('gn_final_script', 'GN: Final Script'),
                ],
                max_length=30,
            ),
        ),
        migrations.RunPython(seed_sets_and_clone, reverse_to_single_set),
        # Now that every row has a set, make the FK non-null and add the
        # per-(set, step) uniqueness.
        migrations.AlterField(
            model_name='llmstepconfig',
            name='config_set',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='step_configs',
                to='vocabulary.llmconfigset',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='llmstepconfig',
            unique_together={('config_set', 'step_key')},
        ),
    ]
