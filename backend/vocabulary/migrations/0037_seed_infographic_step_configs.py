# Seed the infographic pipeline step configs (ig_design, ig_cloze) into every
# LLM config set, cloned from each set's comparable text steps.
from django.db import migrations


# Source step to clone each new infographic step's site/model from. Design is a
# text-generation step like pack creation; cloze mirrors the GN cloze step.
NEW_STEP_SOURCES = {
    'ig_design': 'pack_creation',
    'ig_cloze': 'gn_cloze_gen',
}


def seed_infographic_configs(apps, schema_editor):
    LLMConfigSet = apps.get_model('vocabulary', 'LLMConfigSet')
    LLMStepConfig = apps.get_model('vocabulary', 'LLMStepConfig')

    for config_set in LLMConfigSet.objects.all():
        for new_key, source_key in NEW_STEP_SOURCES.items():
            if LLMStepConfig.objects.filter(
                config_set=config_set, step_key=new_key,
            ).exists():
                continue

            template = (
                LLMStepConfig.objects.filter(
                    config_set=config_set, step_key=source_key,
                ).first()
                or LLMStepConfig.objects.filter(config_set=config_set).first()
            )
            if template is None:
                continue  # empty set; nothing to clone from

            LLMStepConfig.objects.create(
                config_set=config_set,
                step_key=new_key,
                primary_site=template.primary_site,
                primary_model=template.primary_model,
                fallback_site=template.fallback_site,
                fallback_model=template.fallback_model,
            )


def remove_infographic_configs(apps, schema_editor):
    LLMStepConfig = apps.get_model('vocabulary', 'LLMStepConfig')
    LLMStepConfig.objects.filter(step_key__in=list(NEW_STEP_SOURCES)).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('vocabulary', '0036_infographic_content_type'),
    ]

    operations = [
        migrations.RunPython(seed_infographic_configs, remove_infographic_configs),
    ]
