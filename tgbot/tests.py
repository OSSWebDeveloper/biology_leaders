"""Bot handlerlari: Telegram'ga chiqmasdan, soxta sessiya orqali tekshiriladi."""
import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import GetMe
from aiogram.types import Chat, Contact, Message, Update, User as TgUser
from asgiref.sync import async_to_sync
from django.test import TransactionTestCase, override_settings

from accounts.models import StudyGroup, User
from tgbot.handlers import router

TG_ID = 5001


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent = []

    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        self.sent.append(method)
        if isinstance(method, GetMe):
            return TgUser(id=1, is_bot=True, first_name='bot', username='test_bot')
        return Message(message_id=1, date=datetime.datetime.now(), chat=Chat(id=TG_ID, type='private'), text='ok')

    async def stream_content(self, *args, **kwargs):
        yield b''


@override_settings(WEBAPP_URL='https://sayt.test', WEBAPP_IS_HTTPS=True, ADMIN_TELEGRAM_IDS=set())
class BotTests(TransactionTestCase):
    def setUp(self):
        self.session = FakeSession()
        self.bot = Bot('123:TEST', session=self.session)
        # router faqat bitta Dispatcher'ga ulanadi, shuning uchun har testda ajratiladi
        router._parent_router = None
        self.dp = Dispatcher(storage=MemoryStorage())
        self.dp.include_router(router)
        self.counter = 0

    def send(self, text=None, contact=None):
        self.counter += 1
        user = TgUser(id=TG_ID, is_bot=False, first_name='Ali')
        message = Message(message_id=self.counter, date=datetime.datetime.now(), text=text, contact=contact,
                          chat=Chat(id=TG_ID, type='private'), from_user=user)
        self.session.sent.clear()
        async_to_sync(self.dp.feed_update)(self.bot, Update(update_id=self.counter, message=message))
        return [m.text for m in self.session.sent if hasattr(m, 'text')]

    def register(self):
        self.send('/start')
        self.send('Aliyev Ali')
        self.send(contact=Contact(phone_number='+998901234567', first_name='Ali', user_id=TG_ID))

    def test_registration(self):
        replies = self.send('/start')
        self.assertEqual(replies[0], 'Assalomu aleykum. Iltimos ism familyangizni kiring: Masalan : Behruz Hodiyev')
        self.send('Aliyev Ali')
        self.send('raqam emas')  # tugmasiz yozsa qayta so'raydi
        self.assertEqual(User.objects.get(telegram_id=TG_ID).phone, '')
        self.send(contact=Contact(phone_number='+998900000000', first_name='X', user_id=999))  # birovning raqami
        self.assertEqual(User.objects.get(telegram_id=TG_ID).phone, '')
        self.send(contact=Contact(phone_number='+998901234567', first_name='Ali', user_id=TG_ID))
        user = User.objects.get(telegram_id=TG_ID)
        self.assertEqual((user.full_name, user.phone), ('Aliyev Ali', '+998901234567'))
        self.assertEqual(user.role, 'student')
        markup = self.session.sent[-1].reply_markup
        self.assertEqual(markup.inline_keyboard[0][0].web_app.url, 'https://sayt.test/')

    def test_group_invite(self):
        teacher = User.objects.create(username='t', role='teacher')
        group = StudyGroup.objects.create(name='A guruh', teacher=teacher)
        replies = self.send(f'/start g_{group.code}')
        self.assertIn('A guruh', replies[0])
        self.assertTrue(group.students.filter(telegram_id=TG_ID).exists())
        self.assertIn('topilmadi', self.send('/start g_XXXXXX')[0])

    def test_panel_only_for_teachers(self):
        self.register()
        self.assertIn('faqat', self.send('/panel')[0])
        User.objects.filter(telegram_id=TG_ID).update(role='teacher')
        self.assertIn('https://sayt.test/kirish/', self.send('/panel')[0])

    def test_results_empty_and_blocked(self):
        self.register()
        self.assertIn("yo'q", self.send('/natijalar')[0])
        User.objects.filter(telegram_id=TG_ID).update(is_active=False)
        self.assertIn('bloklangan', self.send('/start')[0])
