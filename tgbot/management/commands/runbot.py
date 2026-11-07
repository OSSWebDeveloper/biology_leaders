import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from exams.services import finish_expired
from tgbot.handlers import router

log = logging.getLogger(__name__)


async def expiry_loop():
    """Vaqti tugab, o'quvchi qaytib kirmagan urinishlarni yakunlab, natijasini yuboradi."""
    while True:
        try:
            await sync_to_async(finish_expired)()
        except Exception:
            log.exception('finish_expired xatosi')
        await asyncio.sleep(60)


async def run(drop_webhook):
    bot = Bot(settings.BOT_TOKEN)
    info = await bot.get_webhook_info()
    if info.url and not drop_webhook:
        await bot.session.close()
        raise CommandError(
            "Bu tokenda webhook o'rnatilgan, polling ishlamaydi. Webhook kerak emasligiga ishonch "
            "hosil qilgach: python manage.py runbot --webhookni-ochir"
        )
    if info.url:
        await bot.delete_webhook(drop_pending_updates=False)
    await bot.set_my_commands([
        BotCommand(command='start', description='Bosh menyu'),
        BotCommand(command='natijalar', description='Oxirgi natijalar'),
        BotCommand(command='yordam', description='Yordam'),
    ])
    if settings.WEBAPP_IS_HTTPS:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
            text='Testlar', web_app=WebAppInfo(url=settings.WEBAPP_URL + '/')))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    task = asyncio.create_task(expiry_loop())
    me = await bot.get_me()
    log.info('Bot ishga tushdi: @%s', me.username)
    try:
        await dp.start_polling(bot)
    finally:
        task.cancel()
        await bot.session.close()


class Command(BaseCommand):
    help = 'Telegram botni polling rejimida ishga tushiradi.'

    def add_arguments(self, parser):
        parser.add_argument('--webhookni-ochir', action='store_true',
                            help="Tokendagi mavjud webhook'ni o'chiradi (boshqa joyda ishlayotgan bot to'xtaydi).")

    def handle(self, *args, webhookni_ochir=False, **opts):
        if not settings.BOT_TOKEN:
            raise CommandError('.env da BOT_TOKEN yo\'q')
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
        # aiohttp/aiogram loglarida token ko'rinmasligi uchun
        logging.getLogger('aiogram.event').setLevel(logging.WARNING)
        asyncio.run(run(webhookni_ochir))
