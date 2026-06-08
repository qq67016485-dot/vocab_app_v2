# Add the audiobook voice director step key + seed a config row per set.
from django.db import migrations, models


STEP_KEY_CHOICES = [
    ('word_lookup', 'Word Lookup'),
    ('translation', 'Translation'),
    ('question_gen', 'Question Generation'),
    ('primer_gen', 'Primer Generation'),
    ('pack_creation', 'Pack Grouping'),
    ('gn_team_selection', 'GN: Team Selection'),
    ('gn_router_premises', 'GN: Router Premises'),
    ('gn_premise_scoring', 'GN: Premise Scoring'),
    ('gn_cloze_gen', 'GN: Cloze Generation'),
    ('gn_beat_sheet', 'GN: Beat Sheet'),
    ('gn_final_script', 'GN: Final Script'),
    ('audiobook_director', 'Audiobook: Voice Director'),
]


def seed_director_config(apps, schema_editor):
    """Add an 'audiobook_director' step config to every config set, cloning the
    site/model from that set's final-script row (a comparable text step)."""
    LLMConfigSet = apps.get_model('vocabulary', 'LLMConfigSet')
    LLMStepConfig = apps.get_model('vocabulary', 'LLMStepConfig')

    for config_set in LLMConfigSet.objects.all():
        if LLMStepConfig.objects.filter(
            config_set=config_set, step_key='audiobook_director',
        ).exists():
            continue

        template = (
            LLMStepConfig.objects.filter(
                config_set=config_set, step_key='gn_final_script',
            ).first()
            or LLMStepConfig.objects.filter(config_set=config_set).first()
        )
        if template is None:
            continue  # empty set; nothing to clone from

        LLMStepConfig.objects.create(
            config_set=config_set,
            step_key='audiobook_director',
            primary_site=template.primary_site,
            primary_model=template.primary_model,
            fallback_site=template.fallback_site,
            fallback_model=template.fallback_model,
        )


def remove_director_config(apps, schema_editor):
    LLMStepConfig = apps.get_model('vocabulary', 'LLMStepConfig')
    LLMStepConfig.objects.filter(step_key='audiobook_director').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('vocabulary', '0032_graphicnovelpageaudio'),
    ]

    operations = [
        migrations.AlterField(
            model_name='llmstepconfig',
            name='step_key',
            field=models.CharField(choices=STEP_KEY_CHOICES, max_length=30),
        ),
        migrations.RunPython(seed_director_config, remove_director_config),
    ]
