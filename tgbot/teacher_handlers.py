"""O'qituvchi boti: Web App'siz. Fayl yuboriladi, vaqt va javoblar kaliti oddiy qatorlar bilan yoziladi."""
import datetime
import io
import re
from pathlib import PurePath

from aiogram import BaseMiddleware, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, KeyboardButton, Message, ReplyKeyboardMarkup
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models import Avg
from django.utils import timezone

from accounts.models import User
from accounts.services import get_or_create_tg_user
from exams.forms import PdfImportForm
from exams.models import Exam, Question
from exams.pdf_import import PdfImportError
from exams.services import attach_test_file, discard_exam, regrade_exam

from . import notify

router = Router()

BTN_NEW = '➕ Yangi test'
BTN_LIST = '📋 Testlarim'
MAX_DOWNLOAD_MB = 20  # Bot API bundan kattasini yuklab bermaydi
DEFAULT_DURATION_MIN = 150

menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_NEW), KeyboardButton(text=BTN_LIST)]], resize_keyboard=True)

TIMES_HELP = ("Boshlanish va tugash vaqtini ikki qatorda yozing:\n\n"
              "<code>08.11.2026 09:00\n08.11.2026 12:00</code>")
KEYS_HELP = ("Javoblarni qatorlar bilan yuboring:\n\n"
             "<code>1 A\n2 C\n33 F\n36 2√5; 16/3</code>\n\n"
             "Yozma savolda a) va b) javoblari <code>;</code> bilan ajratiladi. "
             "Bir xabarda ham, bo'lib ham yuborsa bo'ladi.")

_DATETIME = re.compile(r'(\d{1,2})[./-](\d{1,2})[./-](\d{4})[ ,T]+(\d{1,2})[:.](\d{2})')
_LETTER_LINE = re.compile(r'^(\d{1,2})\s*[-.):]?\s*([A-Fa-f])$')
_VALUE_LINE = re.compile(r'^(\d{1,2})(?:\s*[.):]\s*|\s+)(.+)$')


class NewExam(StatesGroup):
    file = State()
    title = State()
    times = State()
    keys = State()


class TeacherOnly(BaseMiddleware):
    """Faqat shaxsiy chatda va faqat o'qituvchi/adminga javob beradi. Begona odam bazaga yozilmaydi."""

    async def __call__(self, handler, event, data):
        if event.chat.type != 'private' or not event.from_user:
            return None
        teacher = await _teacher_for(event.from_user.id)
        if teacher is None:
            await event.answer("Bu bot faqat o'qituvchilar uchun.\n"
                               f"Telegram ID: <code>{event.from_user.id}</code>", parse_mode='HTML')
            return None
        data['teacher'] = teacher
        return await handler(event, data)


router.message.outer_middleware(TeacherOnly())


@sync_to_async
def _teacher_for(tg_id):
    if tg_id in settings.ADMIN_TELEGRAM_IDS:
        return get_or_create_tg_user(tg_id)
    user = User.objects.filter(telegram_id=tg_id, is_active=True).first()
    return user if user and user.is_teacher else None


def parse_times(text, now=None):
    """Ikki qatordan (boshlanish, tugash) ni oladi; xato bo'lsa ValueError matni bilan."""
    found = _DATETIME.findall(text)
    if len(found) != 2:
        raise ValueError("Ikkita vaqt topilmadi.")
    try:
        opens, closes = (timezone.make_aware(datetime.datetime(int(y), int(m), int(d), int(h), int(mi)))
                         for d, m, y, h, mi in found)
    except ValueError:
        raise ValueError("Sana yoki vaqt noto'g'ri.") from None
    if closes <= opens:
        raise ValueError("Tugash vaqti boshlanishdan keyin bo'lsin.")
    if closes <= (now or timezone.now()):
        raise ValueError("Tugash vaqti o'tib ketgan.")
    return opens, closes


def parse_key_lines(text):
    """Qatorlardan [(raqam, qiymat)] va o'qib bo'lmagan qatorlarni qaytaradi."""
    pairs, bad = [], []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _LETTER_LINE.match(line) or _VALUE_LINE.match(line)
        if match:
            pairs.append((int(match.group(1)), match.group(2).strip()))
        else:
            bad.append(line)
    return pairs, bad


@sync_to_async
def _apply_keys(exam_id, text):
    """Kalitni saqlaydi: (saqlangan soni, xato qatorlar, kalitsiz raqamlar)."""
    exam = Exam.objects.get(pk=exam_id)
    pairs, errors = parse_key_lines(text)
    questions = {q.number: q for q in exam.questions.all()}
    saved = 0
    for number, value in pairs:
        question = questions.get(number)
        if question is None:
            errors.append(f"{number}: bunday savol yo'q")
        elif question.kind == Question.Kind.OPEN:
            parts = [part.strip() for part in value.split(';')]
            if len(parts) != 2 or not all(parts) or max(map(len, parts)) > 120:
                errors.append(f"{number}: a) va b) javobini ; bilan yozing")
                continue
            question.answer_a, question.answer_b = parts
            question.save(update_fields=['answer_a', 'answer_b'])
            saved += 1
        else:
            letter = value.upper()
            if len(letter) != 1 or letter not in question.letters:
                errors.append(f"{number}: {question.letters[0]}–{question.letters[-1]} bo'lishi kerak")
                continue
            question.correct = letter
            question.save(update_fields=['correct'])
            saved += 1
    if saved and exam.attempts.filter(finished_at__isnull=False).exists():
        regrade_exam(exam)
    return saved, errors, exam.missing_keys()


@sync_to_async
def _create_from_file(teacher, name, data):
    upload = SimpleUploadedFile(name, data)
    form = PdfImportForm({}, {'pdf': upload})
    if not form.is_valid():
        raise PdfImportError(' '.join(form.errors['pdf']))
    with transaction.atomic():
        exam = Exam.objects.create(title=PurePath(name).stem[:200] or 'Test', created_by=teacher,
                                   status=Exam.Status.DRAFT)
        note = attach_test_file(exam, form.cleaned_data['pdf'])
    return exam.pk, note


@sync_to_async
def _set_fields(exam_id, **fields):
    Exam.objects.filter(pk=exam_id).update(**fields)


@sync_to_async
def _publish(exam_id):
    Exam.objects.filter(pk=exam_id).update(status=Exam.Status.PUBLISHED)


@sync_to_async
def _discard_draft(exam_id):
    exam = Exam.objects.filter(pk=exam_id, status=Exam.Status.DRAFT).first()
    if exam and not exam.attempts.exists():
        discard_exam(exam)


@sync_to_async
def _own_exam(teacher, code):
    exams = Exam.objects.all() if teacher.is_admin_role else Exam.objects.filter(created_by=teacher)
    return exams.filter(access_code=(code or '').strip().upper()).first()


@sync_to_async
def _announcement(exam_id):
    exam = Exam.objects.get(pk=exam_id)
    if not exam.attachment:
        return None
    with exam.attachment.open('rb') as source:
        return source.read(), notify.announcement_filename(exam), notify.announcement_caption(exam)


@sync_to_async
def _list_rows(teacher):
    exams = Exam.objects.all() if teacher.is_admin_role else Exam.objects.filter(created_by=teacher)
    rows = []
    for exam in exams[:20]:
        state = '✅' if exam.is_published else '📝'
        done = exam.attempts.filter(finished_at__isnull=False).count()
        rows.append(f"{state} <code>{exam.access_code}</code> {notify.esc(exam.title)} · {done} ta yechgan")
    return rows


@sync_to_async
def _results_text(exam):
    attempts = list(exam.attempts.filter(finished_at__isnull=False).select_related('student').order_by('-score'))
    if not attempts:
        return f"<b>{notify.esc(exam.title)}</b>\nHali hech kim yakunlamagan."
    average = exam.attempts.filter(finished_at__isnull=False).aggregate(a=Avg('score'))['a']
    lines = [f"<b>{notify.esc(exam.title)}</b>", f"Yechganlar: {len(attempts)} · o'rtacha ball: {average:.1f}", '']
    for index, attempt in enumerate(attempts, 1):
        lines.append(f"{index}. {notify.esc(attempt.student.display_name)} — {attempt.score} ball, "
                     f"{attempt.grade or 'darajasiz'} ({attempt.correct_items}/{attempt.total_items})")
        if sum(map(len, lines)) > 3700:
            lines.append(f"… yana {len(attempts) - index} ta")
            break
    return '\n'.join(lines)


async def _download(bot, document):
    buffer = io.BytesIO()
    await bot.download(document, destination=buffer)
    return buffer.getvalue()


async def _abandon_draft(state):
    data = await state.get_data()
    if data.get('creating') and data.get('exam_id'):
        await _discard_draft(data['exam_id'])
    await state.clear()


async def _send_announcement(message, exam_id):
    prepared = await _announcement(exam_id)
    if prepared is None:
        await message.answer("Testda fayl yo'q, xabar tayyorlab bo'lmadi.", reply_markup=menu)
        return
    data, filename, caption = prepared
    await message.answer_document(BufferedInputFile(data, filename), caption=caption, parse_mode='HTML')
    await message.answer('☝️ Shu xabarni guruhga uzating.', reply_markup=menu)


def _format_missing(numbers):
    return ', '.join(map(str, numbers))


# ---------- Buyruqlar: istalgan bosqichda ishlaydi ----------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, teacher):
    await _abandon_draft(state)
    await message.answer(
        f"Assalomu aleykum, {teacher.display_name}.\n\n"
        "Yangi test: fayl yuborasiz, vaqtni va javoblarni qatorlar bilan yozasiz, "
        "guruhga uzatish uchun tayyor xabar olasiz.\n\n"
        "/testlar: testlarim\n/natija KOD: natijalar\n/xabar KOD: guruh xabarini qayta olish\n"
        "/kalit KOD: javoblarni o'zgartirish\n/bekor: bekor qilish",
        reply_markup=menu)


@router.message(Command('bekor'))
async def cmd_cancel(message: Message, state: FSMContext):
    await _abandon_draft(state)
    await message.answer('Bekor qilindi.', reply_markup=menu)


@router.message(Command('testlar'))
@router.message(F.text == BTN_LIST)
async def cmd_list(message: Message, teacher):
    rows = await _list_rows(teacher)
    await message.answer('\n'.join(rows) if rows else "Hali test yo'q.", parse_mode='HTML', reply_markup=menu)


@router.message(Command('natija'))
async def cmd_results(message: Message, command: CommandObject, teacher):
    exam = await _own_exam(teacher, command.args)
    if exam is None:
        await message.answer('Test topilmadi. Masalan: /natija 7KM3QX')
        return
    await message.answer(await _results_text(exam), parse_mode='HTML')


@router.message(Command('xabar'))
async def cmd_resend(message: Message, command: CommandObject, teacher):
    exam = await _own_exam(teacher, command.args)
    if exam is None or not exam.is_published or not exam.opens_at or not exam.closes_at:
        await message.answer("E'lon qilingan test topilmadi. Masalan: /xabar 7KM3QX")
        return
    await _send_announcement(message, exam.pk)


@router.message(Command('kalit'))
async def cmd_keys(message: Message, command: CommandObject, state: FSMContext, teacher):
    exam = await _own_exam(teacher, command.args)
    if exam is None:
        await message.answer('Test topilmadi. Masalan: /kalit 7KM3QX')
        return
    await _abandon_draft(state)
    await state.set_state(NewExam.keys)
    await state.update_data(exam_id=exam.pk, creating=False, editing=exam.is_published)
    await message.answer(KEYS_HELP, parse_mode='HTML')


@router.message(F.text == BTN_NEW)
async def new_exam(message: Message, state: FSMContext):
    await _abandon_draft(state)
    await state.set_state(NewExam.file)
    await message.answer('Test faylini yuboring (PDF yoki Word).')


# ---------- Yangi test bosqichlari ----------

@router.message(NewExam.file, F.document)
async def got_file(message: Message, state: FSMContext, teacher):
    document = message.document
    if (document.file_size or 0) > MAX_DOWNLOAD_MB * 1024 * 1024:
        await message.answer(f'Fayl {MAX_DOWNLOAD_MB} MB dan oshmasin.')
        return
    await message.answer("Fayl o'qilmoqda…")
    data = await _download(message.bot, document)
    try:
        exam_id, note = await _create_from_file(teacher, document.file_name or 'test.pdf', data)
    except PdfImportError as exc:
        await message.answer(f"{exc}\nBoshqa fayl yuboring yoki /bekor.")
        return
    await state.update_data(exam_id=exam_id, creating=True)
    await state.set_state(NewExam.title)
    await message.answer(f'{note}\n\nTest nomini yozing:')


@router.message(NewExam.file)
async def file_expected(message: Message):
    await message.answer('PDF yoki Word faylni hujjat sifatida yuboring.')


@router.message(NewExam.title, F.text)
async def got_title(message: Message, state: FSMContext):
    title = ' '.join(message.text.split())
    if not 3 <= len(title) <= 200 or title.startswith('/'):
        await message.answer("Nomi 3–200 belgi bo'lsin:")
        return
    data = await state.get_data()
    await _set_fields(data['exam_id'], title=title)
    await state.set_state(NewExam.times)
    await message.answer(TIMES_HELP, parse_mode='HTML')


@router.message(NewExam.times, F.text)
async def got_times(message: Message, state: FSMContext):
    try:
        opens, closes = parse_times(message.text)
    except ValueError as exc:
        await message.answer(f'{exc}\n\n{TIMES_HELP}', parse_mode='HTML')
        return
    data = await state.get_data()
    window = int((closes - opens).total_seconds() // 60)
    await _set_fields(data['exam_id'], opens_at=opens, closes_at=closes,
                      duration_min=max(1, min(DEFAULT_DURATION_MIN, window)))
    await state.set_state(NewExam.keys)
    saved, errors, missing = await _apply_keys(data['exam_id'], '')
    if not missing:  # PDF kaliti to'liq chiqqan
        await _finish(message, state, data['exam_id'])
        return
    await message.answer(f"{KEYS_HELP}\n\nKalitsiz savollar: {_format_missing(missing)}", parse_mode='HTML')


@router.message(NewExam.keys, F.text)
async def got_keys(message: Message, state: FSMContext):
    data = await state.get_data()
    saved, errors, missing = await _apply_keys(data['exam_id'], message.text)
    lines = [f'Saqlandi: {saved} ta.']
    if errors:
        lines += ["O'qilmadi:", *[notify.esc(error) for error in errors[:20]]]
    if missing:
        lines.append(f'Kalitsiz savollar: {_format_missing(missing)}')
        await message.answer('\n'.join(lines))
        return
    if errors:
        await message.answer('\n'.join(lines))
    if data.get('editing'):
        await state.clear()
        await message.answer('Javoblar yangilandi, natijalar qayta hisoblandi.', reply_markup=menu)
        return
    await _finish(message, state, data['exam_id'])


async def _finish(message, state, exam_id):
    await _publish(exam_id)
    await state.clear()
    await message.answer("✅ Test e'lon qilindi.")
    await _send_announcement(message, exam_id)


@router.message()
async def fallback(message: Message):
    await message.answer('Pastdagi tugmadan tanlang yoki /start.', reply_markup=menu)
