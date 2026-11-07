"""Test jarayoni: ruxsat, urinish boshlash/yakunlash, PDF dan savol yaratish."""
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from tgbot import notify

from .models import Answer, Attempt, Exam, Question
from .pdf_import import PdfImportError, slice_pdf, strip_key_pages
from .scoring import grade_attempt

DEFAULT_SHEET = {'mcq': 32, 'matching': 3, 'open': 10}
DEFAULT_QUESTION_COUNT = sum(DEFAULT_SHEET.values())


def exam_by_code(code):
    """Kod bo'yicha e'lon qilingan test; o'quvchi testga faqat shu yo'l bilan kiradi."""
    code = (code or '').strip().upper()
    return Exam.objects.filter(access_code=code, status=Exam.Status.PUBLISHED).first() if code else None


def can_start(exam, user):
    """(ruxsat, sabab)"""
    if not exam.is_published:
        return False, "Test hali e'lon qilinmagan"
    now = timezone.now()
    if exam.opens_at and now < exam.opens_at:
        return False, f"Test {timezone.localtime(exam.opens_at):%d.%m.%Y %H:%M} da boshlanadi"
    if exam.closes_at and now >= exam.closes_at:
        return False, 'Test vaqti tugagan'
    if exam.max_attempts:
        used = exam.attempts.filter(student=user, finished_at__isnull=False).count()
        if used >= exam.max_attempts:
            return False, 'Urinishlar soni tugagan'
    return True, ''


def start_attempt(exam, user):
    active = exam.attempts.filter(student=user, finished_at__isnull=True).first()
    if active:
        if active.seconds_left() > 0:
            return active
        finalize(active)
    deadline = timezone.now() + timedelta(minutes=exam.duration_min)
    if exam.closes_at:
        deadline = min(deadline, exam.closes_at)
    try:
        with transaction.atomic():
            return Attempt.objects.create(exam=exam, student=user, deadline=deadline)
    except IntegrityError:  # ikki marta bosilgan
        return exam.attempts.get(student=user, finished_at__isnull=True)


def finalize(attempt):
    """Urinishni bir marta yakunlaydi, baholaydi va natijani botga yuboradi."""
    now = timezone.now()
    finished_at = min(now, attempt.deadline)
    claimed = Attempt.objects.filter(pk=attempt.pk, finished_at__isnull=True).update(finished_at=finished_at)
    attempt.refresh_from_db()
    if not claimed:
        return attempt
    grade_attempt(attempt)
    notify.attempt_result(attempt)
    return attempt


def finish_expired():
    """Vaqti tugagan, lekin yopilmagan urinishlarni yakunlaydi (bot fon vazifasi chaqiradi)."""
    expired = Attempt.objects.filter(finished_at__isnull=True, deadline__lte=timezone.now()).select_related('exam', 'student')
    count = 0
    for attempt in expired:
        finalize(attempt)
        count += 1
    return count


def regrade_exam(exam):
    for attempt in exam.attempts.filter(finished_at__isnull=False).prefetch_related('answers'):
        grade_attempt(attempt)


def save_answer(attempt, question, choice=None, value_a=None, value_b=None):
    defaults = {}
    if question.kind == Question.Kind.OPEN:
        defaults['value_a'] = (value_a or '')[:64]
        defaults['value_b'] = (value_b or '')[:64]
    else:
        choice = (choice or '').upper()
        defaults['choice'] = choice if choice in question.letters else ''
    Answer.objects.update_or_create(attempt=attempt, question=question, defaults=defaults)


@transaction.atomic
def import_pdf_into(exam, data, replace=False):
    """PDF dan savollarni yaratadi; (savollar soni, kalit kiritilgan soni) qaytaradi."""
    result = slice_pdf(data)
    if replace:
        for question in exam.questions.all():
            question.image.delete(save=False)
        exam.questions.all().delete()
        offset = 0
    else:
        offset = exam.questions.aggregate(m=Max('number'))['m'] or 0
    created = keyed = 0
    for piece in result.slices:
        for number in [piece.number, *piece.extra_numbers]:
            question = Question(exam=exam, number=number + offset, kind=piece.kind,
                                correct=result.mcq_key.get(number, '') if piece.kind != 'open' else '')
            question.image.save(f'e{exam.pk}_{number + offset}.png', ContentFile(piece.png), save=True)
            created += 1
            keyed += int(bool(question.correct))
    return created, keyed


def create_answer_sheet(exam, counts=None):
    """Javob varag'i: savol matni guruhga yuborilgan faylda, raqamlar turlar bo'yicha ketma-ket."""
    counts = counts or DEFAULT_SHEET
    kinds = [kind for kind in ('mcq', 'matching', 'open') for _ in range(counts.get(kind, 0))]
    Question.objects.bulk_create(Question(exam=exam, number=n, kind=kind) for n, kind in enumerate(kinds, 1))


def save_test_file(exam, extension, data):
    """Faylni o'qimasdan, o'zgarishsiz saqlaydi."""
    if exam.attachment:
        exam.attachment.delete(save=False)
    exam.attachment.save(f'test.{extension}', ContentFile(data), save=True)


@transaction.atomic
def attach_test_file(exam, upload, replace=False):
    """Test faylini saqlaydi va kerak bo'lsa savollarni yaratadi. Natija matnini qaytaradi."""
    extension = upload.name.lower().rsplit('.', 1)[-1]
    data = upload.read()
    has_questions = exam.questions.exists()
    note = 'Test fayli saqlandi.'
    if extension == 'pdf':
        clean = strip_key_pages(data)  # guruhga javoblarsiz nusxa ketadi
        if replace or not has_questions:
            try:
                created, keyed = import_pdf_into(exam, data, replace=replace)
            except PdfImportError:
                if replace:
                    raise
                # skaner yoki boshqa ko'rinishdagi PDF: savol faylda qoladi, javob varag'i yetarli
                create_answer_sheet(exam)
                note = (f"PDF dan savollar ajratilmadi, {DEFAULT_QUESTION_COUNT} savollik javob varag'i yaratildi. "
                        "O'quvchi savolni fayldan o'qiydi.")
            else:
                note = (f"{created} ta savol kesib olindi, {keyed} tasiga kalit topildi. "
                        "Qolgan javoblarni kiriting.")
        data = clean
    elif replace or not has_questions:
        if replace:
            for question in exam.questions.all():
                question.image.delete(save=False)
            exam.questions.all().delete()
        create_answer_sheet(exam)
        note = (f"Word fayl saqlandi va {DEFAULT_QUESTION_COUNT} savollik javob varag'i yaratildi. "
                "Javoblar kalitini kiriting.")
    save_test_file(exam, extension, data)
    return note


def discard_exam(exam):
    for question in exam.questions.all():
        question.image.delete(save=False)
    exam.attachment.delete(save=False)
    exam.delete()
