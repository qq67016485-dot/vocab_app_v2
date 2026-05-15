from django.db import migrations, models


def remove_legacy_visual_rows(apps, schema_editor):
    Question = apps.get_model('vocabulary', 'Question')
    GenerationJob = apps.get_model('vocabulary', 'GenerationJob')
    GenerationJobLog = apps.get_model('vocabulary', 'GenerationJobLog')

    legacy_steps = ['CREATIVE_DIRECTION', 'IMAGE_GEN', 'PICTURE_MATCH_GEN']
    Question.objects.filter(question_type='PICTURE_WORD_MATCH').delete()
    GenerationJobLog.objects.filter(step__in=legacy_steps).delete()
    GenerationJob.objects.filter(last_completed_step__in=legacy_steps).update(
        last_completed_step='GRAPHIC_NOVEL_IMAGES',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('vocabulary', '0019_graphic_novel_page_status'),
    ]

    operations = [
        migrations.RunPython(remove_legacy_visual_rows, migrations.RunPython.noop),
        migrations.DeleteModel(
            name='GeneratedImage',
        ),
        migrations.RemoveField(
            model_name='word',
            name='image_category',
        ),
        migrations.RemoveField(
            model_name='worddefinition',
            name='visual_scene',
        ),
        migrations.RemoveField(
            model_name='generationjob',
            name='images_created',
        ),
        migrations.AlterField(
            model_name='question',
            name='question_type',
            field=models.CharField(
                choices=[
                    ('DEFINITION_MC_SINGLE', 'Definition MC (Single Ans)'),
                    ('DEFINITION_TRUE_FALSE', 'Definition True/False'),
                    ('DEFINITION_MATCHING', 'Definition Matching'),
                    ('SYNONYM_MC_SINGLE', 'Synonym MC (Single Ans)'),
                    ('SYNONYM_MC_MULTI', 'Synonym MC (Multi Ans)'),
                    ('SYNONYM_MATCHING', 'Synonym Matching'),
                    ('ANTONYM_MC_SINGLE', 'Antonym MC (Single Ans)'),
                    ('ANTONYM_MATCHING', 'Antonym Matching'),
                    ('CONTEXT_MC_SINGLE', 'Context MC (Single Ans)'),
                    ('CONTEXT_FILL_IN_BLANK', 'Context Fill-in-Blank'),
                    ('SPELLING_FILL_IN_BLANK', 'Spelling Fill-in-Blank'),
                    ('WORD_FORM_FILL_IN_BLANK', 'Word Form Fill-in-Blank'),
                    ('WORD_FORM_MC', 'Word Form MC'),
                    ('SENTENCE_SCRAMBLE', 'Sentence Scramble'),
                    ('DIALOGUE_COMPLETION_MC', 'Dialogue Completion MC'),
                    ('ODD_ONE_OUT_MC_SINGLE', 'Odd One Out MC (Single Ans)'),
                    ('CONNOTATION_SORTING', 'Connotation Sorting'),
                    ('COLLOCATION_MC_SINGLE', 'Collocation MC (Single Ans)'),
                    ('COLLOCATION_FILL_IN_BLANK', 'Collocation Fill-in-Blank'),
                    ('COLLOCATION_MATCHING', 'Collocation Matching'),
                    ('CONCEPTUAL_ASSOCIATION_MC_SINGLE', 'Conceptual Association MC (Single Ans)'),
                    ('REVERSE_DEFINITION_MC', 'Reverse Definition MC'),
                    ('SYNONYM_IN_CONTEXT_MC', 'Synonym in Context MC'),
                    ('REVERSE_SYNONYM_IN_CONTEXT_MC', 'Reverse Synonym in Context MC'),
                    ('APPLICATION_MC', 'Application MC'),
                    ('REVERSE_ASSOCIATION_MC', 'Reverse Association MC'),
                    ('REVERSE_COLLOCATION_MC', 'Reverse Collocation MC'),
                    ('NUANCE_CONTRAST_MC', 'Nuance Contrast MC'),
                ],
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name='generationjoblog',
            name='step',
            field=models.CharField(
                choices=[
                    ('WORD_LOOKUP', 'Word Lookup'),
                    ('DEDUP', 'Deduplication'),
                    ('TRANSLATION', 'Translation'),
                    ('QUESTION_GEN', 'Question Generation'),
                    ('PACK_CREATION', 'Pack Creation'),
                    ('PRIMER_GEN', 'Primer Generation'),
                    ('STORY_CLOZE_GEN', 'Story & Cloze Generation'),
                    ('GRAPHIC_NOVEL_SCRIPT', 'Graphic Novel Script'),
                    ('GRAPHIC_NOVEL_IMAGES', 'Graphic Novel Images'),
                ],
                max_length=30,
            ),
        ),
    ]
