from django.db import migrations, models
from django.utils import timezone


def mark_old_exams(apps, schema_editor):
    """Shu yangilanishdan oldin tugagan testlar natijasi kanalga chiqib ketmasin."""
    Exam = apps.get_model('exams', 'Exam')
    now = timezone.now()
    Exam.objects.filter(closes_at__lte=now).update(results_posted_at=now)


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0005_rasch_navbati'),
    ]

    operations = [
        migrations.AddField(
            model_name='exam',
            name='results_posted_at',
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name='Natijalar kanalga yuborilgan'),
        ),
        migrations.RunPython(mark_old_exams, migrations.RunPython.noop),
    ]
