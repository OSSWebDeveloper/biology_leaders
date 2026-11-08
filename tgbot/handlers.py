from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, WebAppInfo,
)
from asgiref.sync import sync_to_async
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import StudyGroup, User
from accounts.services import get_or_create_tg_user, make_login_token
from exams.models import Attempt

router = Router()

BTN_RESULTS = '📊 Natijalarim'
BTN_HELP = 'ℹ️ Yordam'


class Registration(StatesGroup):
    name = State()
    phone = State()


main_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_RESULTS), KeyboardButton(text=BTN_HELP)]],
    resize_keyboard=True,
)
phone_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text='📱 Telefon raqamni yuborish', request_contact=True)]],
    resize_keyboard=True, one_time_keyboard=True,
)


def open_app_markup():
    """Web App faqat https bilan ochiladi; manzil hali yo'q bo'lsa tugma ko'rsatilmaydi."""
    if not settings.WEBAPP_IS_HTTPS:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='📝 Testlarni ochish', web_app=WebAppInfo(url=settings.WEBAPP_URL + '/')),
    ]])


async def send_menu(message: Message, user: User):
    markup = open_app_markup()
    await message.answer(f'Assalomu alaykum, {user.display_name}!', reply_markup=main_keyboard)
    if markup:
        await message.answer('Testlarni yechish uchun ilovani oching:', reply_markup=markup)
    else:
        await message.answer("Test ilovasi hali ulanmagan. Tez orada shu yerda ochish tugmasi paydo bo'ladi.")


@sync_to_async
def _user_for(tg):
    return get_or_create_tg_user(tg.id, tg.first_name or '', tg.last_name or '')


@sync_to_async
def _join_group(user, code):
    group = StudyGroup.objects.filter(code__iexact=code).select_related('teacher').first()
    if group:
        group.students.add(user)
    return group


@sync_to_async
def _save_fields(user, **fields):
    for name, value in fields.items():
        setattr(user, name, value)
    user.save(update_fields=list(fields))


@sync_to_async
def _recent_results(user):
    attempts = (Attempt.objects.filter(student=user, finished_at__isnull=False)
                .select_related('exam').order_by('-finished_at')[:5])
    return [(a.exam.title, timezone.localtime(a.finished_at)) for a in attempts]


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    user = await _user_for(message.from_user)
    if not user.is_active:
        await message.answer('Hisobingiz bloklangan.')
        return
    arg = command.args or ''
    if arg.startswith('g_'):
        group = await _join_group(user, arg[2:])
        if group:
            await state.update_data(joined=group.name)
            await message.answer(f"✅ Siz «{group.name}» guruhiga qo'shildingiz.")
        else:
            await message.answer('Guruh topilmadi: havola eskirgan bo\'lishi mumkin.')
    if user.is_registered:
        await state.clear()
        await send_menu(message, user)
        return
    await state.set_state(Registration.name)
    await message.answer(
        'Assalomu aleykum. Iltimos ism familyangizni kiring: Masalan : Behruz Hodiyev',
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(Registration.name, F.text)
async def reg_name(message: Message, state: FSMContext):
    name = ' '.join(message.text.split())
    if not 3 <= len(name) <= 150 or name.startswith('/'):
        await message.answer("Iltimos ism familyangizni to'liq kiring: Masalan : Behruz Hodiyev")
        return
    user = await _user_for(message.from_user)
    await _save_fields(user, full_name=name)
    await state.set_state(Registration.phone)
    await message.answer('Telefon raqamingizni pastdagi tugma orqali yuboring:', reply_markup=phone_keyboard)


@router.message(Registration.phone, F.contact)
async def reg_phone(message: Message, state: FSMContext):
    if message.contact.user_id != message.from_user.id:
        await message.answer("O'zingizning raqamingizni yuboring:", reply_markup=phone_keyboard)
        return
    user = await _user_for(message.from_user)
    await _save_fields(user, phone=message.contact.phone_number)
    await state.clear()
    await send_menu(message, user)


@router.message(Registration.phone)
async def reg_phone_retry(message: Message):
    await message.answer('Pastdagi tugmani bosing:', reply_markup=phone_keyboard)


@router.message(Command('id'))
async def cmd_id(message: Message):
    await message.answer(f'Telegram ID: <code>{message.from_user.id}</code>', parse_mode='HTML')


@router.message(Command('natijalar'))
@router.message(F.text == BTN_RESULTS)
async def cmd_results(message: Message):
    user = await _user_for(message.from_user)
    rows = await _recent_results(user)
    if not rows:
        await message.answer("Hali yakunlangan testingiz yo'q.")
        return
    lines = ['<b>Yakunlangan testlaringiz</b>']
    for title, finished in rows:
        title = title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        lines.append(f"\n{title} · {finished:%d.%m.%Y %H:%M}")
    lines.append('\nNatijalar guruhga tashlanadi.')
    await message.answer('\n'.join(lines), parse_mode='HTML')


@router.message(Command('panel'))
async def cmd_panel(message: Message):
    """Kompyuter brauzerida ishlash uchun bir martalik havola: faqat o'qituvchi va adminga."""
    user = await _user_for(message.from_user)
    if not user.is_teacher:
        await message.answer("Bu buyruq faqat o'qituvchi va admin uchun.")
        return
    if not settings.WEBAPP_URL:
        await message.answer('Sayt manzili hali sozlanmagan.')
        return
    token = await sync_to_async(make_login_token)(user)
    await message.answer(
        f"Bir martalik havola (10 daqiqa):\n{settings.WEBAPP_URL}{reverse('login_link', args=[token])}\n\n"
        "Uni boshqalarga bermang.",
        disable_web_page_preview=True,
    )


@router.message(Command('yordam'))
@router.message(F.text == BTN_HELP)
async def cmd_help(message: Message):
    await message.answer(
        "Bot milliy sertifikat testlarini yechish uchun.\n\n"
        "/start — bosh menyu\n/natijalar — oxirgi natijalar\n/id — Telegram ID\n/panel — o'qituvchi uchun brauzer havolasi\n\n"
        "Natijalar Rasch modeli bilan baholanadi va guruhga tashlanadi."
    )
