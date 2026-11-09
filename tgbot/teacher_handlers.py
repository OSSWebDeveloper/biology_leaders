"""O'qituvchi boti: Web App'siz. Fayl yuboriladi, vaqt va javoblar kaliti oddiy qatorlar bilan yoziladi."""
import datetime
import io
import re
from pathlib import PurePath

from aiogram import BaseMiddleware, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message,
    ReplyKeyboardMarkup,
)
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models import Avg
from django.utils import timezone

from accounts.models import User
from accounts.services import approve_browser_login, get_or_create_tg_user, touch_seen
from exams.forms import PdfImportForm
from exams.models import Exam, Question
from exams.pdf_import import PdfImportError
from exams.services import DEFAULT_SHEET, create_answer_sheet, discard_exam, regrade_exam, save_test_file

from . import notify

router = Router()

BTN_NEW = '➕ Yangi test'
BTN_LIST = '📋 Testlarim'
BTN_LAUNCH = '🚀 Joriy etish'
MAX_DOWNLOAD_MB = 20  # Bot API bundan kattasini yuklab bermaydi
DEFAULT_DURATION_MIN = 150
MAX_QUESTIONS = 99  # kalit qatorida raqam ikki xonali
KEY_STAGES = (('mcq', 'keys_mcq'), ('matching', 'keys_matching'), ('open', 'keys_open'))
COMPACT_HELP = {
    'mcq': ("<b>1-bo'lim: 4 variantli savollar</b> ({n} ta)\n\nTo'g'ri javoblarni shunday yuboring:\n"
            "<code>1a2b3c4d5a6b</code>"),
    'matching': ("<b>2-bo'lim: 6 variantli savollar</b> ({n} ta)\n\nTo'g'ri javoblarni shunday yuboring:\n"
                 "<code>1a2f3d</code>\n\nRaqamlar shu bo'lim ichida 1 dan boshlanadi."),
}
WRITTEN_HELP = ("<b>3-bo'lim: yozma savollar</b> ({n} ta)\n\nHar bir savolga bitta javob yuboring. "
                "Bir nechta to'g'ri javob bo'lsa, or bilan yozing:\n<code>2√5 or √20 or 4,47</code>")
KIND_LABELS = {'mcq': '4 variantli', 'matching': '6 variantli', 'open': 'Yozma ish'}

menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_NEW), KeyboardButton(text=BTN_LAUNCH)], [KeyboardButton(text=BTN_LIST)]],
    resize_keyboard=True)


def times_help():
    tomorrow = timezone.localtime() + datetime.timedelta(days=1)
    return ("Boshlanish va tugash vaqtini ikki qatorda yozing:\n\n"
            f"<code>{tomorrow:%d.%m.%Y} 09:00\n{tomorrow:%d.%m.%Y} 12:00</code>")


def _counts_text(counts):
    return f'Savollar, jami: <b>{sum(counts.values())}</b>'


def _counts_keyboard(counts):
    rows = [[InlineKeyboardButton(text=f'{label}: {counts[kind]}', callback_data='count:noop'),
             InlineKeyboardButton(text='-', callback_data=f'count:{kind}:-'),
             InlineKeyboardButton(text='+', callback_data=f'count:{kind}:+')]
            for kind, label in KIND_LABELS.items()]
    rows.append([InlineKeyboardButton(text='Tayyor', callback_data='count:ok')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


_DATETIME = re.compile(r'(\d{1,2})[./-](\d{1,2})[./-](\d{4})[ ,T]+(\d{1,2})[:.](\d{2})')
_COMPACT_PAIR = re.compile(r'(\d{1,2})([A-Za-z])')


class NewExam(StatesGroup):
    file = State()
    count = State()
    title = State()
    keys_mcq = State()
    keys_matching = State()
    keys_open = State()


class Launch(StatesGroup):
    code = State()
    times = State()


CODE_PATTERN = re.compile(r'[A-Z0-9]{3,8}')
CODE_HELP = ("Kirish kodini yozing: 3–8 ta lotin harfi yoki raqam.\n"
             "Masalan: <code>BIO15</code>")


class TeacherOnly(BaseMiddleware):
    """Faqat shaxsiy chatda va faqat o'qituvchi/adminga javob beradi. Begona odam bazaga yozilmaydi."""

    async def __call__(self, handler, event, data):
        chat = event.message.chat if isinstance(event, CallbackQuery) else event.chat
        if chat.type != 'private' or not event.from_user:
            return None
        teacher = await _teacher_for(event.from_user.id)
        if teacher is None:
            await event.answer("Bu bot faqat o'qituvchilar uchun.\n"
                               f"Telegram ID: <code>{event.from_user.id}</code>", parse_mode='HTML')
            return None
        data['teacher'] = teacher
        return await handler(event, data)


router.message.outer_middleware(TeacherOnly())
router.callback_query.outer_middleware(TeacherOnly())


@sync_to_async
def _teacher_for(tg_id):
    if tg_id in settings.ADMIN_TELEGRAM_IDS:
        user = get_or_create_tg_user(tg_id)
    else:
        user = User.objects.filter(telegram_id=tg_id, is_active=True).first()
        if not (user and user.is_teacher):
            return None
    touch_seen(user, 'last_bot_seen')
    return user


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


def parse_compact_keys(text):
    """«1a2b3c» ko'rinishidagi kalitni [(1, 'A'), ...] ga aylantiradi; boshqa ko'rinish bo'lsa None."""
    cleaned = re.sub(r'[\s,;.:)\-]+', '', text)
    if not re.fullmatch(r'(?:\d{1,2}[A-Za-z])+', cleaned):
        return None
    return [(int(number), letter.upper()) for number, letter in _COMPACT_PAIR.findall(cleaned)]


@sync_to_async
def _apply_compact(exam_id, kind, text):
    """Bo'lim kaliti: raqam bo'lim ichida 1 dan sanaladi. (saqlangan, xatolar, kalitsiz raqamlar)."""
    questions = list(Question.objects.filter(exam_id=exam_id, kind=kind).order_by('number'))
    pairs = parse_compact_keys(text)
    errors = []
    saved = 0
    if pairs is None:
        errors.append("Ko'rinishi noto'g'ri")
        pairs = []
    for number, letter in pairs:
        if not 1 <= number <= len(questions):
            errors.append(f"{number}: bu bo'limda bunday savol yo'q")
            continue
        question = questions[number - 1]
        if letter not in question.letters:
            errors.append(f"{number}{letter.lower()}: {question.letters[0]}–{question.letters[-1]} bo'lishi kerak")
            continue
        question.correct = letter
        question.save(update_fields=['correct'])
        saved += 1
    missing = [index for index, question in enumerate(questions, 1) if not question.has_key()]
    return saved, errors, missing


@sync_to_async
def _sections(exam_id):
    result = {kind: {'numbers': [], 'missing': []} for kind, _ in KEY_STAGES}
    for question in Question.objects.filter(exam_id=exam_id).order_by('number'):
        result[question.kind]['numbers'].append(question.number)
        if not question.has_key():
            result[question.kind]['missing'].append(question.number)
    return result


@sync_to_async
def _written_info(exam_id, number):
    return Question.objects.only('two_parts', 'answer_a', 'answer_b').get(exam_id=exam_id, number=number)


@sync_to_async
def _save_written(exam_id, number, text):
    """Yozma javobni saqlaydi. Eski a/b savolda ikki qism ; bilan yoziladi. Xato matni yoki None."""
    question = Question.objects.get(exam_id=exam_id, number=number)
    if question.two_parts:
        parts = [part.strip() for part in text.split(';')]
        if len(parts) != 2 or not all(parts):
            return "Bu savolda a) va b) bor: ikkalasini ; bilan yozing"
        question.answer_a, question.answer_b = parts
    else:
        question.answer_a = text.strip()
    question.save(update_fields=['answer_a', 'answer_b'])
    return None


@sync_to_async
def _is_complete(exam_id):
    return not Exam.objects.get(pk=exam_id).missing_keys()


@sync_to_async
def _regrade(exam_id):
    exam = Exam.objects.get(pk=exam_id)
    if exam.attempts.filter(finished_at__isnull=False).exists():
        regrade_exam(exam)


@sync_to_async
def _create_from_file(teacher, name, data):
    """Fayl o'qilmaydi: faqat kengaytmasi, hajmi va Word sarlavhasi tekshiriladi, keyin o'zgarishsiz saqlanadi."""
    form = PdfImportForm({}, {'pdf': SimpleUploadedFile(name, data)})
    if not form.is_valid():
        raise PdfImportError(' '.join(form.errors['pdf']))
    exam = Exam.objects.create(title=PurePath(name).stem[:200] or 'Test', created_by=teacher,
                               status=Exam.Status.DRAFT)
    save_test_file(exam, name.lower().rsplit('.', 1)[-1], data)
    return exam.pk


@sync_to_async
def _set_code(exam_id, text):
    """O'qituvchi bergan kirish kodini saqlaydi. Xato matni yoki None."""
    code = text.strip().upper()
    if not CODE_PATTERN.fullmatch(code):
        return "Kod 3–8 ta lotin harfi yoki raqamdan iborat bo'lsin, bo'sh joysiz."
    if Exam.objects.filter(access_code=code).exclude(pk=exam_id).exists():
        return 'Bu kod boshqa testda band. Boshqasini yozing.'
    Exam.objects.filter(pk=exam_id).update(access_code=code)
    return None


@sync_to_async
def _create_questions(exam_id, counts):
    create_answer_sheet(Exam.objects.get(pk=exam_id), counts)


@sync_to_async
def _set_fields(exam_id, **fields):
    Exam.objects.filter(pk=exam_id).update(**fields)


@sync_to_async
def _discard_if_empty(exam_id):
    exam = Exam.objects.filter(pk=exam_id, status=Exam.Status.DRAFT).first()
    if exam and not exam.questions.exists() and not exam.attempts.exists():
        discard_exam(exam)


@sync_to_async
def _discard_draft(exam_id):
    exam = Exam.objects.filter(pk=exam_id, status=Exam.Status.DRAFT).first()
    if exam and not exam.attempts.exists():
        discard_exam(exam)


@sync_to_async
def _own_exam(teacher, code):
    exams = Exam.objects.all() if teacher.is_admin_role else Exam.objects.filter(created_by=teacher)
    return exams.filter(access_code=(code or '').strip().upper()).first()


def _is_ready(exam):
    return bool(exam.attachment) and exam.questions.exists() and not exam.missing_keys()


@sync_to_async
def _ready_exams(teacher):
    """Joriy etsa bo'ladigan testlar: fayli bor va javoblari to'liq."""
    exams = Exam.objects.all() if teacher.is_admin_role else Exam.objects.filter(created_by=teacher)
    return [(exam.pk, exam.title) for exam in exams[:30] if _is_ready(exam)]


@sync_to_async
def _ready_exam(teacher, exam_id):
    exams = Exam.objects.all() if teacher.is_admin_role else Exam.objects.filter(created_by=teacher)
    exam = exams.filter(pk=exam_id).first()
    return exam if exam and _is_ready(exam) else None


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
        grade = f", {attempt.grade}" if attempt.grade else ''
        lines.append(f"{index}. {notify.esc(attempt.student.display_name)} — {attempt.score} ball{grade} "
                     f"({attempt.correct_items}/{attempt.total_items})")
        if sum(map(len, lines)) > 3700:
            lines.append(f"… yana {len(attempts) - index} ta")
            break
    return '\n'.join(lines)


async def _download(bot, document):
    buffer = io.BytesIO()
    await bot.download(document, destination=buffer)
    return buffer.getvalue()


async def _abandon_draft(state):
    """Faqat /bekor uchun: yaratilayotgan test o'chiriladi."""
    data = await state.get_data()
    if data.get('creating') and data.get('exam_id'):
        await _discard_draft(data['exam_id'])
    await state.clear()


async def _leave_flow(state):
    """Boshqa bo'limga o'tish: kiritilgan javoblar yo'qolmaydi, /kalit KOD bilan davom etsa bo'ladi."""
    data = await state.get_data()
    if data.get('creating') and data.get('exam_id'):
        await _discard_if_empty(data['exam_id'])
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

@router.message(CommandStart(deep_link=True, magic=F.args.startswith('login_')))
async def cmd_browser_login(message: Message, command: CommandObject):
    """Kompyuter brauzeridan kirish: sahifadagi «Telegram orqali kirish» tugmasi shu yerga olib keladi."""
    token = command.args[len('login_'):]
    await message.answer(
        "💻 Kompyuter brauzerida saytga kirish so'raldi.\n\n"
        "Agar tugmani hozir o'zingiz bosgan bo'lsangiz, tasdiqlang. Aks holda e'tibor bermang.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text='✅ Tasdiqlash', callback_data=f'blogin:{token}'),
            InlineKeyboardButton(text='Rad etish', callback_data='blogin:-'),
        ]]))


@router.callback_query(F.data.startswith('blogin:'))
async def cb_browser_login(callback: CallbackQuery, teacher):
    token = callback.data[len('blogin:'):]
    if token == '-':
        text = 'Kirish rad etildi.'
    elif await sync_to_async(approve_browser_login)(token, teacher):
        text = "✅ Tasdiqlandi. Brauzerdagi sahifa o'zi ochiladi."
    else:
        text = 'Havola eskirgan yoki ishlatilgan. Brauzerda sahifani yangilang.'
    await callback.message.edit_text(text)
    await callback.answer()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, teacher):
    await _leave_flow(state)
    await message.answer(
        f"Assalomu aleykum, {teacher.display_name}.\n\n"
        "Yangi test: fayl, savollar soni, nom va javoblar.\n"
        "Joriy etish: testni tanlaysiz, kirish kodi va vaqtni yozasiz va guruhga uzatish uchun tayyor xabar olasiz.\n\n"
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
    await _leave_flow(state)
    await state.update_data(exam_id=exam.pk, creating=False, editing=exam.is_published,
                            review=await _is_complete(exam.pk))
    await _next_section(message, state)


@router.message(Command('otkaz'))
async def cmd_skip(message: Message, state: FSMContext):
    """To'liq testni tahrirlaganda: joriy javobni o'zgartirmasdan keyingisiga o'tish."""
    data = await state.get_data()
    current = await state.get_state()
    if not data.get('review') or current not in {getattr(NewExam, name).state for _, name in KEY_STAGES}:
        await message.answer("Hozir o'tkazib bo'lmaydi.")
        return
    if current == NewExam.keys_open.state:
        await _ask_written(message, state, data['pending'][1:])
        return
    await _next_section(message, state, after='mcq' if current == NewExam.keys_mcq.state else 'matching')


@router.message(F.text == BTN_NEW)
async def new_exam(message: Message, state: FSMContext):
    await _leave_flow(state)
    await state.set_state(NewExam.file)
    await message.answer('Test faylini yuboring (PDF yoki Word).')


@router.message(F.text == BTN_LAUNCH)
async def choose_exam(message: Message, state: FSMContext, teacher):
    await _leave_flow(state)
    exams = await _ready_exams(teacher)
    if not exams:
        await message.answer("Joriy etishga tayyor test yo'q. Avval yangi test yarating.", reply_markup=menu)
        return
    buttons = [[InlineKeyboardButton(text=title[:60], callback_data=f'launch:{pk}')] for pk, title in exams]
    await message.answer('Qaysi testni joriy etasiz?', reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith('launch:'))
async def launch_selected(callback: CallbackQuery, state: FSMContext, teacher):
    pk = callback.data.split(':', 1)[1]
    exam = await _ready_exam(teacher, int(pk)) if pk.isdigit() else None
    if exam is None:
        await callback.answer('Test topilmadi')
        return
    await _leave_flow(state)
    await state.set_state(Launch.code)
    await state.update_data(exam_id=exam.pk, creating=False)
    await callback.answer()
    await callback.message.answer(f'<b>{notify.esc(exam.title)}</b>\n\n{CODE_HELP}', parse_mode='HTML')


# ---------- Yangi test bosqichlari ----------

@router.message(NewExam.file, F.document)
async def got_file(message: Message, state: FSMContext, teacher):
    document = message.document
    if (document.file_size or 0) > MAX_DOWNLOAD_MB * 1024 * 1024:
        await message.answer(f'Fayl {MAX_DOWNLOAD_MB} MB dan oshmasin.')
        return
    data = await _download(message.bot, document)
    try:
        exam_id = await _create_from_file(teacher, document.file_name or 'test.pdf', data)
    except PdfImportError as exc:
        await message.answer(f"{exc}\nBoshqa fayl yuboring yoki /bekor.")
        return
    counts = dict(DEFAULT_SHEET)
    await state.update_data(exam_id=exam_id, creating=True, counts=counts)
    await state.set_state(NewExam.count)
    await message.answer(_counts_text(counts), parse_mode='HTML', reply_markup=_counts_keyboard(counts))


@router.message(NewExam.file)
async def file_expected(message: Message):
    await message.answer('PDF yoki Word faylni hujjat sifatida yuboring.')


@router.callback_query(NewExam.count, F.data == 'count:noop')
async def count_label(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(NewExam.count, F.data == 'count:ok')
async def count_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    counts = data['counts']
    if not sum(counts.values()):
        await callback.answer('Kamida bitta savol bo\'lsin')
        return
    await _create_questions(data['exam_id'], counts)
    await state.set_state(NewExam.title)
    summary = '\n'.join(f'{label}: {counts[kind]}' for kind, label in KIND_LABELS.items())
    await callback.message.edit_text(f'{_counts_text(counts)}\n{summary}', parse_mode='HTML')
    await callback.answer()
    await callback.message.answer('Test nomini yozing:')


@router.callback_query(NewExam.count, F.data.regexp(r'^count:(mcq|matching|open):[+-]$'))
async def change_count(callback: CallbackQuery, state: FSMContext):
    _, kind, sign = callback.data.split(':')
    data = await state.get_data()
    counts = dict(data['counts'])
    counts[kind] += 1 if sign == '+' else -1
    if counts[kind] < 0 or sum(counts.values()) > MAX_QUESTIONS:
        await callback.answer(f"Jami 0–{MAX_QUESTIONS} oralig'ida bo'lsin")
        return
    await state.update_data(counts=counts)
    await callback.message.edit_text(_counts_text(counts), parse_mode='HTML', reply_markup=_counts_keyboard(counts))
    await callback.answer()


@router.callback_query()
async def stale_button(callback: CallbackQuery):
    await callback.answer('Bu tugma eskirgan')


@router.message(NewExam.count)
async def count_expected(message: Message):
    await message.answer('Yuqoridagi tugmalardan foydalaning: +, - va Tayyor.')


@router.message(NewExam.title, F.text)
async def got_title(message: Message, state: FSMContext):
    title = ' '.join(message.text.split())
    if not 3 <= len(title) <= 200 or title.startswith('/'):
        await message.answer("Nomi 3–200 belgi bo'lsin:")
        return
    data = await state.get_data()
    await _set_fields(data['exam_id'], title=title)
    await _next_section(message, state)


async def _next_section(message, state, after=None):
    """Keyingi bo'limga o'tadi: bo'sh bo'lim o'tkaziladi, tahrirda (review) to'liqlari ham ko'rsatiladi."""
    data = await state.get_data()
    sections = await _sections(data['exam_id'])
    kinds = [kind for kind, _ in KEY_STAGES]
    review = data.get('review')
    for kind, name in KEY_STAGES[kinds.index(after) + 1 if after else 0:]:
        section = sections[kind]
        if not section['numbers'] or (not review and not section['missing']):
            continue
        await state.set_state(getattr(NewExam, name))
        skip = "\n\nO'zgartirmaslik uchun: /otkaz" if review else ''
        if kind == 'open':
            await message.answer(WRITTEN_HELP.format(n=len(section['numbers'])), parse_mode='HTML')
            await _ask_written(message, state, section['numbers'] if review else section['missing'])
        else:
            await message.answer(COMPACT_HELP[kind].format(n=len(section['numbers'])) + skip, parse_mode='HTML')
        return
    await _keys_complete(message, state)


async def _ask_written(message, state, pending):
    if not pending:
        await _keys_complete(message, state)
        return
    await state.update_data(pending=pending)
    data = await state.get_data()
    question = await _written_info(data['exam_id'], pending[0])
    text = f'{pending[0]}-savol javobi:'
    if question.two_parts:
        text = f'{pending[0]}-savol javobi (a; b):'
    if data.get('review'):
        current = f'{question.answer_a}; {question.answer_b}' if question.two_parts else question.answer_a
        text += f'\nHozirgi: {current}\nO\'zgartirmaslik uchun: /otkaz'
    await message.answer(text)


async def _keys_complete(message, state):
    data = await state.get_data()
    await _regrade(data['exam_id'])
    if data.get('editing'):
        await state.clear()
        await message.answer('Javoblar yangilandi, natijalar qayta hisoblandi.', reply_markup=menu)
        return
    await _finish(message, state, data['exam_id'])


async def _got_compact(message, state, kind):
    data = await state.get_data()
    saved, errors, missing = await _apply_compact(data['exam_id'], kind, message.text)
    lines = []
    if saved:
        lines.append(f'Saqlandi: {saved} ta.')
    lines += errors[:20]
    if errors and not saved and kind in COMPACT_HELP:
        lines.append('Masalan: ' + ('1a2b3c4d' if kind == 'mcq' else '1a2f3d'))
    if missing and not data.get('review'):
        lines.append(f'Kalitsiz: {_format_missing(missing)}')
    if lines:
        await message.answer('\n'.join(lines))
    if not missing and (saved or not errors):
        await _next_section(message, state, after=kind)


@router.message(NewExam.keys_mcq, F.text)
async def got_keys_mcq(message: Message, state: FSMContext):
    await _got_compact(message, state, 'mcq')


@router.message(NewExam.keys_matching, F.text)
async def got_keys_matching(message: Message, state: FSMContext):
    await _got_compact(message, state, 'matching')


@router.message(NewExam.keys_open, F.text)
async def got_written(message: Message, state: FSMContext):
    """Bitta qator bitta savolning javobi: bir xabarda bir nechta qator ham bo'lishi mumkin."""
    data = await state.get_data()
    pending = list(data['pending'])
    for line in filter(None, map(str.strip, message.text.splitlines())):
        if not pending:
            break
        error = await _save_written(data['exam_id'], pending[0], line)
        if error:
            await message.answer(error)
            break
        pending.pop(0)
    await _ask_written(message, state, pending)


async def _finish(message, state, exam_id):
    """Test saqlanadi, lekin hali e'lon qilinmaydi: vaqt va kod joriy etishda."""
    await state.clear()
    await message.answer('✅ Test saqlandi.', reply_markup=menu)
    await message.answer('Guruhga berish vaqti kelganda joriy eting.', reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=BTN_LAUNCH, callback_data=f'launch:{exam_id}')]]))


@router.message(Launch.code, F.text)
async def got_code(message: Message, state: FSMContext):
    data = await state.get_data()
    error = await _set_code(data['exam_id'], message.text)
    if error:
        await message.answer(f'{error}\n\n{CODE_HELP}', parse_mode='HTML')
        return
    await state.set_state(Launch.times)
    await message.answer(f'Kirish kodi: <code>{message.text.strip().upper()}</code>\n\n{times_help()}', parse_mode='HTML')


@router.message(Launch.times, F.text)
async def got_times(message: Message, state: FSMContext):
    try:
        opens, closes = parse_times(message.text)
    except ValueError as exc:
        await message.answer(f'{exc}\n\n{times_help()}', parse_mode='HTML')
        return
    data = await state.get_data()
    window = int((closes - opens).total_seconds() // 60)
    await _set_fields(data['exam_id'], opens_at=opens, closes_at=closes, status=Exam.Status.PUBLISHED,
                      duration_min=max(1, min(DEFAULT_DURATION_MIN, window)))
    await state.clear()
    await message.answer('✅ Test joriy etildi.')
    await _send_announcement(message, data['exam_id'])


@router.message()
async def fallback(message: Message):
    await message.answer('Pastdagi tugmadan tanlang yoki /start.', reply_markup=menu)
