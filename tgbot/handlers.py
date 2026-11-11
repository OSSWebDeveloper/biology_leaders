import logging
import time

from aiogram import BaseMiddleware, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, WebAppInfo,
)
from asgiref.sync import sync_to_async
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import StudyGroup, User
from accounts.services import get_or_create_tg_user, make_login_token, touch_seen
from exams.models import Attempt

from . import subscription

router = Router()
log = logging.getLogger(__name__)


class ChannelRequired(BaseMiddleware):
    """Majburiy obuna: kanalga a'zo bo'lmagan foydalanuvchi botdan foydalana olmaydi."""
    TTL = 600

    def __init__(self):
        self.passed = {}  # telegram_id -> qachongacha tekshirmaslik

    async def member(self, bot, user_id):
        if self.passed.get(user_id, 0) > time.monotonic():
            return True
        try:
            member = await bot.get_chat_member(settings.REQUIRED_CHANNEL_ID, user_id)
        except TelegramBadRequest as exc:
            if subscription.is_not_member_error(str(exc)):
                return False
            log.warning('Obuna tekshirilmadi: %s', exc)
            return True
        except Exception as exc:  # tarmoq: botni to'xtatmaslik uchun o'tkaziladi
            log.warning('Obuna tekshirilmadi: %s', type(exc).__name__)
            return True
        ok = subscription.is_member_status(member.status, getattr(member, 'is_member', None))
        if ok:
            self.passed[user_id] = time.monotonic() + self.TTL
        return ok

    async def __call__(self, handler, event, data):
        user = data.get('event_from_user')
        chat = getattr(event, 'chat', None) or getattr(getattr(event, 'message', None), 'chat', None)
        if not subscription.required() or user is None or (chat and chat.type != 'private'):
            return await handler(event, data)
        if await self.member(data['bot'], user.id):
            return await handler(event, data)
        markup = InlineKeyboardMarkup.model_validate(subscription.subscribe_markup())
        if isinstance(event, CallbackQuery):
            if event.data == 'sub:check':
                await event.answer("Hali obuna bo'lmagansiz", show_alert=True)
            else:
                await event.answer()
                await event.message.answer(subscription.SUBSCRIBE_TEXT, reply_markup=markup)
            return None
        state = data.get('state')
        text = event.text or ''
        if state is not None and text.startswith('/start g_'):
            # Guruh havolasi obunadan keyin ham ishlashi uchun: «Obuna bo'ldim» da qo'shiladi
            await state.update_data(pending_group=text.split(maxsplit=1)[1][2:] if ' ' in text else '')
        await event.answer(subscription.SUBSCRIBE_TEXT, reply_markup=markup)
        return None


channel_required = ChannelRequired()
router.message.outer_middleware(channel_required)
router.callback_query.outer_middleware(channel_required)

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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📝 Testlarni ochish', web_app=WebAppInfo(url=settings.WEBAPP_URL + '/'))],
        # Zaxira yo'l: Mini App'ni ochmaydigan (eski yoki modlashgan) Telegram mijozlari uchun.
        # Oddiy tugma har qanday mijozda ishlaydi va shaxsiy bir martalik havola beradi.
        [InlineKeyboardButton(text='🌐 Ochilmasa: brauzerda ochish', callback_data=CB_BROWSER)],
    ])


CB_BROWSER = 'open:browser'


async def send_browser_link(message: Message, tg_user):
    """Bir martalik havola: o'quvchi brauzerda o'z hisobi bilan kiradi (kanal obunasi ham tekshiriladi)."""
    user = await _user_for(tg_user)
    if not user.is_active:
        await message.answer('Hisobingiz bloklangan.')
        return
    if not user.is_registered:
        await message.answer("Avval ro'yxatdan o'ting: /start")
        return
    if not settings.WEBAPP_URL:
        await message.answer('Sayt manzili hali sozlanmagan.')
        return
    token = await sync_to_async(make_login_token)(user)
    await message.answer(
        "Testlarni brauzerda ochish uchun tugmani bosing.\n\n"
        "Havola bir martalik va 10 daqiqa amal qiladi. Uni boshqalarga bermang: u sizning hisobingizga kiritadi.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text='🌐 Brauzerda ochish', url=settings.WEBAPP_URL + reverse('login_link', args=[token]))]]),
    )


async def send_menu(message: Message, user: User):
    markup = open_app_markup()
    await message.answer(f'Assalomu alaykum, {user.display_name}!', reply_markup=main_keyboard)
    if markup:
        await message.answer('Testlarni yechish uchun ilovani oching:', reply_markup=markup)
    else:
        await message.answer("Test ilovasi hali ulanmagan. Tez orada shu yerda ochish tugmasi paydo bo'ladi.")


@sync_to_async
def _user_for(tg):
    user = get_or_create_tg_user(tg.id, tg.first_name or '', tg.last_name or '')
    touch_seen(user, 'last_bot_seen')
    return user


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


@router.callback_query(F.data == 'sub:check')
async def subscribed(callback: CallbackQuery, state: FSMContext):
    """Middleware a'zolikni tasdiqlagan: /start dagi kabi davom etadi."""
    await callback.answer('Rahmat!')
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    user = await _user_for(callback.from_user)
    if not user.is_active:
        await callback.message.answer('Hisobingiz bloklangan.')
        return
    code = (await state.get_data()).get('pending_group')
    if code:
        await state.update_data(pending_group=None)
        group = await _join_group(user, code)
        if group:
            await callback.message.answer(f"✅ Siz «{group.name}» guruhiga qo'shildingiz.")
        else:
            await callback.message.answer("Guruh topilmadi: havola eskirgan bo'lishi mumkin.")
    if user.is_registered:
        await state.clear()
        await send_menu(callback.message, user)
        return
    await state.set_state(Registration.name)
    await callback.message.answer(
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


@router.message(Command('brauzer'))
async def cmd_browser(message: Message):
    await send_browser_link(message, message.from_user)


@router.callback_query(F.data == CB_BROWSER)
async def cb_browser(callback: CallbackQuery):
    await callback.answer()
    await send_browser_link(callback.message, callback.from_user)


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


async def _open_section(message: Message, allowed, path, text):
    """Yashirin bo'limlar: ruxsati yo'q foydalanuvchiga hech narsa qaytarilmaydi."""
    user = await _user_for(message.from_user)
    if not allowed(user) or not settings.WEBAPP_IS_HTTPS:
        return
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='Ochish', web_app=WebAppInfo(url=settings.WEBAPP_URL + path)),
    ]]))


@router.message(Command('ustoz'))
async def cmd_ustoz(message: Message):
    await _open_section(message, lambda u: u.is_teacher, reverse('entry_teacher'), "🎓 O'qituvchi bo'limi")


@router.message(Command('yordam'))
@router.message(F.text == BTN_HELP)
async def cmd_help(message: Message):
    await message.answer(
        "Bot milliy sertifikat testlarini yechish uchun.\n\n"
        "/start — bosh menyu\n/natijalar — oxirgi natijalar\n/brauzer — ilova ochilmasa, testlarni brauzerda ochish\n/id — Telegram ID\n/panel — o'qituvchi uchun brauzer havolasi\n\n"
        "Natijalar Rasch modeli bilan baholanadi va guruhga tashlanadi."
    )
