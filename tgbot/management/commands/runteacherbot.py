import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from tgbot.teacher_handlers import router

log = logging.getLogger(__name__)


async def run():
    bot = Bot(settings.TEACHER_BOT_TOKEN)
    info = await bot.get_webhook_info()
    if info.url:
        await bot.session.close()
        raise CommandError("O'qituvchi botida webhook o'rnatilgan, polling ishlamaydi.")
    await bot.set_my_commands([
        BotCommand(command='start', description='Bosh menyu'),
        BotCommand(command='testlar', description='Testlarim'),
        BotCommand(command='natija', description='Natijalar: /natija KOD'),
        BotCommand(command='xabar', description='Guruh xabari: /xabar KOD'),
        BotCommand(command='kalit', description="Javoblarni o'zgartirish: /kalit KOD"),
        BotCommand(command='bekor', description='Bekor qilish'),
    ])
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    me = await bot.get_me()
    log.info("O'qituvchi boti ishga tushdi: @%s", me.username)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


class Command(BaseCommand):
    help = "O'qituvchi botini polling rejimida ishga tushiradi."

    def handle(self, *args, **opts):
        if not settings.TEACHER_BOT_TOKEN:
            raise CommandError(".env da TEACHER_BOT_TOKEN yo'q")
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
        logging.getLogger('aiogram.event').setLevel(logging.WARNING)
        asyncio.run(run())
