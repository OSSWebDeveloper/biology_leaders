from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from exams.models import Exam
from exams.namuna_kalitlar import NAMUNALAR
from exams.services import import_pdf_into


class Command(BaseCommand):
    help = "Namuna PDF testlarni bazaga yuklaydi: python manage.py import_namunalar <papka>"

    def add_arguments(self, parser):
        parser.add_argument('papka')

    def handle(self, papka, **opts):
        folder = Path(papka)
        if not folder.is_dir():
            raise CommandError(f'Papka topilmadi: {folder}')
        for sample in NAMUNALAR:
            path = folder / sample['file']
            if not path.exists():
                self.stderr.write(f'Yo\'q: {path}')
                continue
            if Exam.objects.filter(title=sample['title']).exists():
                self.stdout.write(f"Bor: {sample['title']}")
                continue
            exam = Exam.objects.create(title=sample['title'], is_public=True)
            created, keyed = import_pdf_into(exam, path.read_bytes())
            for number, (a, b) in (sample['key'] or {}).items():
                exam.questions.filter(number=number).update(answer_a=a, answer_b=b)
            missing = exam.missing_keys()
            if not missing:
                exam.status = Exam.Status.PUBLISHED
                exam.save(update_fields=['status'])
            self.stdout.write(self.style.SUCCESS(
                f"{sample['title']}: {created} savol, kalitsiz: {len(missing)}, holat: {exam.get_status_display()}"))
