# Seed the sentence-writing pipeline step configs (sentence_write_gen for
# generation, sentence_judge for answer-time judging) into every LLM config set,
# cloned from each set's comparable text step.
from django.db import migrations


# Source step to clone each new step's site/model from. Both are text-generation
# style calls; question_gen is the closest existing analogue.
NEW_STEP_SOURCES = {
    'sentence_write_gen': 'question_gen',
    'sentence_judge': 'question_gen',
}


def seed_sentence_write_configs(apps, schema_editor):
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


def remove_sentence_write_configs(apps, schema_editor):
    LLMStepConfig = apps.get_model('vocabulary', 'LLMStepConfig')
    LLMStepConfig.objects.filter(step_key__in=list(NEW_STEP_SOURCES)).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('vocabulary', '0038_useranswer_judge_result_alter_generationjoblog_step_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_sentence_write_configs, remove_sentence_write_configs),
    ]
