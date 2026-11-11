"""Test jarayoni: ruxsat, urinish boshlash/yakunlash, PDF dan savol yaratish."""
from datetime import timedelta

from django.core.files.base import ContentFile
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from tgbot import notify

from .models import Answer, Attempt, Exam, Question
from .pdf_import import PdfImportError, slice_pdf, strip_key_pages
from . import rasch
from .scoring import SCALE_MAX, grade_attempt, grade_for

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
    # Yakunlash va tekshirish bitta tranzaksiyada: qayta hisob yarim tekshirilgan urinishni ko'rmasin
    with transaction.atomic():
        claimed = Attempt.objects.filter(pk=attempt.pk, finished_at__isnull=True).update(finished_at=finished_at)
        attempt.refresh_from_db()
        if not claimed:
            return attempt
        grade_attempt(attempt)  # vaqtincha ball: to'g'ri javoblar ulushidan
        Exam.objects.filter(pk=attempt.exam_id).update(needs_rescore=True)
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


def is_ready(exam):
    """E'lon qilsa bo'ladimi: savollar bor, kalit to'liq, vaqtlar kiritilgan."""
    return bool(exam.opens_at and exam.closes_at and exam.questions.exists() and not exam.missing_keys())


def publish_due(now=None):
    """Boshlanish vaqti kelgan testlar: qoralama bo'lsa e'lon qilinadi va kanalga bir marta xabar ketadi.

    Kalit to'liq bo'lmagan qoralama e'lon qilinmaydi (o'qituvchi to'ldirsa, keyingi aylanishda chiqadi).
    Kanalga yuborilmasa keyingi aylanishda yana urinadi; tugash vaqtidan keyin urinilmaydi.
    """
    now = now or timezone.now()
    channel = settings.ANNOUNCE_CHANNEL_ID
    due = Exam.objects.filter(opens_at__lte=now, closes_at__gt=now, channel_posted_at__isnull=True)
    posted = 0
    for exam in due:
        if not exam.is_published:
            if not is_ready(exam):
                continue
            exam.status = Exam.Status.PUBLISHED
            exam.save(update_fields=['status'])
        if not channel:
            continue
        if notify.channel_announcement(exam, channel):
            Exam.objects.filter(pk=exam.pk).update(channel_posted_at=timezone.now())
            posted += 1
    return posted


RESULTS_POST_WINDOW = timedelta(days=1)  # tugaganidan keyin shuncha vaqt ichida yuborilmasa, boshqa urinilmaydi


def best_attempts(exam):
    """Har o'quvchining eng yaxshi yakunlangan urinishi, ball bo'yicha kamayish tartibida."""
    best = {}
    for attempt in (exam.attempts.filter(finished_at__isnull=False).select_related('student')
                    .order_by('-score', 'finished_at')):
        best.setdefault(attempt.student_id, attempt)
    return list(best.values())


def post_results_due(now=None):
    """Tugagan testlarning natijasi kanalga bir marta yuboriladi (bot fon aylanishi chaqiradi).

    Shartlar: tugash vaqti o'tgan, ochiq urinish qolmagan (finish_expired yopgan) va Rasch balli
    hisoblab bo'lingan (rescore_pending). Hech kim yechmagan test uchun xabar yuborilmaydi.
    Yuborilmasa keyingi aylanishda yana urinadi.
    """
    now = now or timezone.now()
    channel = settings.ANNOUNCE_CHANNEL_ID
    if not channel:
        return 0
    due = Exam.objects.filter(status=Exam.Status.PUBLISHED, closes_at__lte=now, closes_at__gt=now - RESULTS_POST_WINDOW,
                              results_posted_at__isnull=True, needs_rescore=False)
    posted = 0
    for exam in due:
        if exam.attempts.filter(finished_at__isnull=True).exists():
            continue
        attempts = best_attempts(exam)
        if attempts and notify.channel_results(exam, channel, attempts):
            Exam.objects.filter(pk=exam.pk).update(results_posted_at=timezone.now())
            posted += 1
    return posted


def regrade_exam(exam):
    """Kalit o'zgargach: javoblar qayta tekshiriladi, Rasch balli bot aylanishida yangilanadi."""
    with transaction.atomic():
        for attempt in exam.attempts.filter(finished_at__isnull=False).prefetch_related('answers'):
            grade_attempt(attempt)
        Exam.objects.filter(pk=exam.pk).update(needs_rescore=True)


def rescore_pending():
    """Bot fon aylanishi chaqiradi: yangi yakunlangan yoki kaliti o'zgargan testlarning Rasch balli."""
    count = 0
    for exam in Exam.objects.filter(needs_rescore=True):
        # Avval belgini olib qo'yamiz: hisob paytida yangi urinish yakunlansa, belgi yana qo'yiladi
        if Exam.objects.filter(pk=exam.pk, needs_rescore=True).update(needs_rescore=False):
            rasch_rescore(exam)
            count += 1
    return count


MIN_RASCH_RESPONDENTS = 20  # bundan kam bo'lsa ball to'g'ri javoblar ulushidan (Rasch kichik guruhda ishonchsiz)


def _is_blank(attempt):
    return not any(a.choice or a.value_a.strip() or a.value_b.strip() for a in attempt.answers.all())


def rasch_rescore(exam):
    """Shu testni yakunlaganlarning ballini qayta hisoblaydi.

    Javob bergan o'quvchilar kamida MIN_RASCH_RESPONDENTS bo'lsa Rasch modeli (ball guruhga nisbatan),
    aks holda yoki model ishonchli baho bera olmasa: 75 x to'g'ri javoblar ulushi. Bo'sh varaq
    (birorta ham javob yo'q) Rasch hisobiga kirmaydi, chunki u boshqalarning ballini buzadi; unga 0.
    """
    items = [(q.pk, part) for q in exam.questions.all() if q.has_key()
             for part in (('a', 'b') if q.max_items == 2 else ('a',))]
    attempts = list(exam.attempts.filter(finished_at__isnull=False).prefetch_related('answers'))
    if not attempts:
        return
    answered = [a for a in attempts if not _is_blank(a)]
    scores = {}
    if len(answered) >= MIN_RASCH_RESPONDENTS:
        responses = []
        for attempt in answered:
            answers = {a.question_id: a for a in attempt.answers.all()}
            responses.append([int(bool(answers.get(pk) and getattr(answers[pk], 'correct_' + part)))
                              for pk, part in items])
        thetas, difficulties = rasch.estimate(responses)
        if difficulties is not None:
            t = rasch.t_scores(thetas)
            if len(set(t)) > 1:
                scores = {attempt.pk: score for attempt, score in zip(answered, t)}
    for attempt in attempts:
        if _is_blank(attempt):
            attempt.score = 0
        elif attempt.pk in scores:
            attempt.score = scores[attempt.pk]
        else:
            attempt.score = round(SCALE_MAX * attempt.percent / 100, 1)
        attempt.grade = grade_for(attempt.score)
    Attempt.objects.bulk_update(attempts, ['score', 'grade'])


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
    Question.objects.bulk_create(Question(exam=exam, number=n, kind=kind, two_parts=False)
                                 for n, kind in enumerate(kinds, 1))


def set_question_counts(exam, counts):
    """Savollar sonini turlar bo'yicha moslaydi: kam bo'lsa oxiriga qo'shadi, ko'p bo'lsa oxiridan
    o'chiradi, so'ng 4 variantli, 6 variantli, ochiq tartibida qayta raqamlaydi. Kalitlar saqlanadi."""
    kept = []
    for kind in ('mcq', 'matching', 'open'):
        existing = list(exam.questions.filter(kind=kind).order_by('number'))
        need = counts.get(kind, 0)
        for question in existing[need:]:
            question.image.delete(save=False)
            question.delete()
        kept += existing[:need]
        kept += [Question(exam=exam, kind=kind, two_parts=False) for _ in range(need - len(existing))]
    with transaction.atomic():
        top = (exam.questions.aggregate(m=Max('number'))['m'] or 0) + 1000
        for i, question in enumerate(q for q in kept if q.pk):  # raqam to'qnashmasin
            Question.objects.filter(pk=question.pk).update(number=top + i)
        for number, question in enumerate(kept, 1):
            question.number = number
            question.save()


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
