from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('vocabulary', '0017_hidden_mastery_level'),
    ]

    operations = [
        migrations.CreateModel(
            name='GraphicNovel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('synopsis', models.TextField(help_text='Story synopsis for character/scene continuity')),
                ('style_prompt', models.TextField(help_text='Art style directive used for all pages')),
                ('reading_level', models.IntegerField(help_text='Lexile score')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('pack', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='graphic_novel', to='vocabulary.wordpack')),
            ],
        ),
        migrations.CreateModel(
            name='GraphicNovelPage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('page_number', models.IntegerField()),
                ('image', models.ImageField(blank=True, upload_to='graphic_novels/')),
                ('prompt_used', models.TextField(blank=True)),
                ('panel_count', models.IntegerField(help_text='Number of panels on this page (1-4)')),
                ('layout_description', models.TextField(blank=True)),
                ('panel_descriptions', models.JSONField(default=list, help_text='Per-panel metadata for accessibility/tooltips')),
                ('vocab_words_used', models.JSONField(default=list, help_text='All vocab words appearing on this page')),
                ('novel', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pages', to='vocabulary.graphicnovel')),
            ],
            options={
                'ordering': ['page_number'],
                'unique_together': {('novel', 'page_number')},
            },
        ),
        migrations.AddField(
            model_name='generationjob',
            name='graphic_novels_created',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='generationjoblog',
            name='step',
            field=models.CharField(choices=[
                ('WORD_LOOKUP', 'Word Lookup'),
                ('DEDUP', 'Deduplication'),
                ('TRANSLATION', 'Translation'),
                ('QUESTION_GEN', 'Question Generation'),
                ('PACK_CREATION', 'Pack Creation'),
                ('PRIMER_GEN', 'Primer Generation'),
                ('STORY_CLOZE_GEN', 'Story & Cloze Generation'),
                ('GRAPHIC_NOVEL_SCRIPT', 'Graphic Novel Script'),
                ('GRAPHIC_NOVEL_IMAGES', 'Graphic Novel Images'),
                ('CREATIVE_DIRECTION', 'Creative Direction'),
                ('IMAGE_GEN', 'Image Generation'),
                ('PICTURE_MATCH_GEN', 'Picture-Word Match Generation'),
            ], max_length=30),
        ),
    ]
