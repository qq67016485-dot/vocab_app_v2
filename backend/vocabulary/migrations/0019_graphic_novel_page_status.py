from django.db import migrations, models


def initialize_page_status(apps, schema_editor):
    GraphicNovelPage = apps.get_model('vocabulary', 'GraphicNovelPage')
    GraphicNovelPage.objects.exclude(image='').update(generation_status='COMPLETED')


class Migration(migrations.Migration):

    dependencies = [
        ('vocabulary', '0018_graphic_novel'),
    ]

    operations = [
        migrations.AddField(
            model_name='graphicnovelpage',
            name='generation_status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending'),
                    ('RUNNING', 'Running'),
                    ('COMPLETED', 'Completed'),
                    ('FAILED', 'Failed'),
                ],
                default='PENDING',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='graphicnovelpage',
            name='generation_attempts',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='graphicnovelpage',
            name='generation_error',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='graphicnovelpage',
            name='generation_started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='graphicnovelpage',
            name='generation_completed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(initialize_page_status, migrations.RunPython.noop),
    ]
