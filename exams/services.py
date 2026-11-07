"""Test jarayoni: ruxsat, urinish boshlash/yakunlash, PDF dan savol yaratish."""
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.utils import timezone

from tgbot import notify

from .models import Answer, Attempt, Exam, Question
from .pdf_import import slice_pdf
from .scoring import grade_attempt


def visible_exams(user):
    """O'quvchi ko'ra oladigan e'lon qilingan testlar."""
    return Exam.objects.filter(
        Q(is_public=True) | Q(groups__students=user),
        status=Exam.Status.PUBLISHED,
    ).distinct()


def can_start(exam, user):
    """(ruxsat, sabab)"""
    if not exam.is_published:
        return False, "Test hali e'lon qilinmagan"
    if not exam.is_open_now():
        return False, 'Test hozir ochiq emas'
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
