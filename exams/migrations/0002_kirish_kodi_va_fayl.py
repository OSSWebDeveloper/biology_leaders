from django.db import migrations, models

import exams.models


def fill_codes(apps, schema_editor):
    Exam = apps.get_model('exams', 'Exam')
    for exam in Exam.objects.all():
        exam.access_code = exams.models.generate_access_code()
        exam.save(update_fields=['access_code'])


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='exam',
            name='access_code',
            field=models.CharField(editable=False, max_length=8, null=True, verbose_name='Kirish kodi'),
        ),
        migrations.RunPython(fill_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='exam',
            name='access_code',
            field=models.CharField(default=exams.models.generate_access_code, editable=False, max_length=8,
                                   unique=True, verbose_name='Kirish kodi'),
        ),
        migrations.AddField(
            model_name='exam',
            name='attachment',
            field=models.FileField(blank=True, upload_to=exams.models.attachment_path, verbose_name='Test fayli'),
        ),
        migrations.AlterField(
            model_name='exam',
            name='max_attempts',
            field=models.PositiveIntegerField(default=1, help_text='0 — cheklanmagan', verbose_name='Urinishlar soni'),
        ),
    ]
