"""Bot handlerlari: Telegram'ga chiqmasdan, soxta sessiya orqali tekshiriladi."""
import datetime
import shutil
import tempfile
from unittest.mock import AsyncMock, patch

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import GetMe, SendDocument
from aiogram.types import CallbackQuery, Chat, Contact, Document, Message, Update, User as TgUser
from asgiref.sync import async_to_sync
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from accounts.models import StudyGroup, User
from exams.models import Exam
from tgbot.handlers import router
from tgbot.teacher_handlers import BTN_LAUNCH, BTN_NEW, parse_key_lines, parse_times
from tgbot.teacher_handlers import router as teacher_router

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


class TeacherKeyParsingTests(TransactionTestCase):
    def test_key_lines(self):
        pairs, bad = parse_key_lines('1 A\n2-c\n3.B\n4) D\n33F\n36 2√5; 16/3\n37 -1/16; 3,5\n\nyomon qator')
        self.assertEqual(pairs, [(1, 'A'), (2, 'c'), (3, 'B'), (4, 'D'), (33, 'F'), (36, '2√5; 16/3'), (37, '-1/16; 3,5')])
        self.assertEqual(bad, ['yomon qator'])

    def test_times(self):
        now = timezone.make_aware(datetime.datetime(2026, 11, 1, 8, 0))
        opens, closes = parse_times('08.11.2026 09:00\n08.11.2026 12:30', now=now)
        self.assertEqual(timezone.localtime(opens).hour, 9)
        self.assertEqual(timezone.localtime(closes).minute, 30)
        for text in ('08.11.2026 09:00', '32.11.2026 09:00\n33.11.2026 09:00',
                     '08.11.2026 12:00\n08.11.2026 09:00', '01.01.2020 09:00\n01.01.2020 12:00'):
            with self.assertRaises(ValueError):
                parse_times(text, now=now)


@override_settings(ADMIN_TELEGRAM_IDS=set(), BOT_USERNAME='biology_leaders_bot')
class TeacherBotTests(TransactionTestCase):
    def setUp(self):
        self.session = FakeSession()
        self.bot = Bot('123:TEST', session=self.session)
        teacher_router._parent_router = None
        self.dp = Dispatcher(storage=MemoryStorage())
        self.dp.include_router(teacher_router)
        self.counter = 0
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)

    def send(self, text=None, document=None, chat_type='private'):
        self.counter += 1
        user = TgUser(id=TG_ID, is_bot=False, first_name='Ali')
        message = Message(message_id=self.counter, date=datetime.datetime.now(), text=text, document=document,
                          chat=Chat(id=TG_ID, type=chat_type), from_user=user)
        self.session.sent.clear()
        async_to_sync(self.dp.feed_update)(self.bot, Update(update_id=self.counter, message=message))
        return [m.text for m in self.session.sent if hasattr(m, 'text')]

    def make_teacher(self):
        return User.objects.create(username='t', telegram_id=TG_ID, role='teacher', full_name='Ali Valiyev')

    def press(self, data):
        self.counter += 1
        user = TgUser(id=TG_ID, is_bot=False, first_name='Ali')
        shown = Message(message_id=1, date=datetime.datetime.now(), text='x', chat=Chat(id=TG_ID, type='private'))
        self.session.sent.clear()
        query = CallbackQuery(id=str(self.counter), from_user=user, chat_instance='c', data=data, message=shown)
        async_to_sync(self.dp.feed_update)(self.bot, Update(update_id=self.counter, callback_query=query))
        return [m.text for m in self.session.sent if hasattr(m, 'text')]

    def upload(self, name='Mock test.docx', data=b'PK\x03\x04word'):
        document = Document(file_id='f', file_unique_id='u', file_name=name, file_size=9)
        with patch('tgbot.teacher_handlers._download', new=AsyncMock(return_value=data)):
            self.send(BTN_NEW)
            return self.send(document=document)

    def test_stranger_is_refused_and_not_saved(self):
        replies = self.send('/start')
        self.assertIn("faqat o'qituvchilar", replies[0])
        self.assertIn(str(TG_ID), replies[0])
        self.assertFalse(User.objects.exists())
        User.objects.create(username='s', telegram_id=TG_ID, role='student')
        self.assertIn("faqat o'qituvchilar", self.send(BTN_NEW)[0])
        self.assertFalse(Exam.objects.exists())

    def test_group_messages_are_ignored(self):
        self.make_teacher()
        self.assertEqual(self.send('/start', chat_type='group'), [])

    def test_file_is_saved_without_reading(self):
        self.make_teacher()
        raw = b'%PDF-buzilgan fayl, JAVOBLAR 1 C'
        replies = self.upload('test.pdf', raw)
        self.assertIn('Savollar soni: <b>35</b>', replies[-1])
        exam = Exam.objects.get()
        self.assertEqual(exam.questions.count(), 0)
        with exam.attachment.open('rb') as saved:
            self.assertEqual(saved.read(), raw)

    def test_count_buttons(self):
        self.make_teacher()
        self.upload()
        markup = self.session.sent[-1].reply_markup
        self.assertEqual([b.text for b in markup.inline_keyboard[0]], ['+', '-', 'Tayyor'])
        self.assertIn('<b>36</b>', self.press('count:+')[0])
        self.assertIn('<b>35</b>', self.press('count:-')[0])
        self.assertIn('tugmalaridan', self.send('40')[0])
        self.press('count:ok')
        exam = Exam.objects.get()
        kinds = [exam.questions.filter(kind=k).count() for k in ('mcq', 'matching', 'open')]
        self.assertEqual(kinds, [32, 3, 0])
        self.assertEqual(self.press('count:+'), ['Bu tugma eskirgan'])
        self.assertEqual(exam.questions.count(), 35)

    def test_full_flow_to_ready_message(self):
        teacher = self.make_teacher()
        self.upload()
        exam = Exam.objects.get()
        self.assertEqual(exam.created_by, teacher)
        self.press('count:+')
        self.press('count:ok')
        self.assertEqual(exam.questions.count(), 36)
        # nomdan keyin vaqt emas, javoblar so'raladi
        self.assertIn('36 2√5', self.send('Matematika 8-noyabr')[0])

        # bo'lib yuborish va xato qator
        lines = [f'{n} A' for n in range(1, 33)] + [f'{n} F' for n in range(33, 36)]
        replies = self.send('\n'.join(lines) + '\n1 Z\n36 faqat-bitta\n99 A')
        self.assertIn('36: a) va b)', replies[0])
        self.assertIn('1: A–D', replies[0])
        self.assertIn('99:', replies[0])
        self.assertEqual(self.send(BTN_LAUNCH), ["Joriy etishga tayyor test yo'q. Avval yangi test yarating."])

        # menyuga chiqib ketganda test va javoblar yo'qolmaydi, /kalit bilan davom etadi
        self.assertTrue(Exam.objects.filter(pk=exam.pk).exists())
        self.assertIn('Javoblarni', self.send(f'/kalit {exam.access_code}')[0])
        replies = self.send('36 2√5; 16/3')
        self.assertIn('✅ Test saqlandi.', replies)
        exam.refresh_from_db()
        self.assertFalse(exam.is_published)
        self.assertIsNone(exam.opens_at)
        self.assertFalse(any(isinstance(m, SendDocument) for m in self.session.sent))
        self.assertEqual(self.session.sent[-1].reply_markup.inline_keyboard[0][0].callback_data, f'launch:{exam.pk}')

        # joriy etish: ro'yxatdan tanlash, vaqt, tayyor xabar
        self.send(BTN_LAUNCH)
        self.assertEqual(self.session.sent[-1].reply_markup.inline_keyboard[0][0].callback_data, f'launch:{exam.pk}')
        self.assertIn('ikki qatorda', self.press(f'launch:{exam.pk}')[-1])
        self.assertIn('Tugash vaqti', self.send('08.11.2030 12:00\n08.11.2030 09:00')[0])
        self.session.sent.clear()
        self.send('08.11.2030 09:00\n08.11.2030 10:00')
        exam.refresh_from_db()
        self.assertTrue(exam.is_published)
        self.assertEqual(exam.duration_min, 60)
        document = next(m for m in self.session.sent if isinstance(m, SendDocument))
        self.assertIn(exam.access_code, document.caption)
        self.assertIn('08.11.2030 09:00', document.caption)
        self.assertIn('08.11.2030 10:00', document.caption)
        self.assertIn('@biology_leaders_bot', document.caption)
        self.assertEqual(document.document.filename, 'Matematika_8-noyabr.docx')
        self.assertEqual(self.session.sent[-1].text, '☝️ Shu xabarni guruhga uzating.')

        # saqlangan test /bekor bilan o'chib ketmaydi
        self.send('/bekor')
        self.assertTrue(Exam.objects.filter(pk=exam.pk).exists())

    def test_cancel_removes_draft(self):
        self.make_teacher()
        self.upload()
        self.press('count:ok')
        self.assertTrue(Exam.objects.exists())
        self.send('/bekor')
        self.assertFalse(Exam.objects.exists())

    def test_leaving_before_count_removes_empty_draft(self):
        self.make_teacher()
        self.upload()
        self.send('/start')
        self.assertFalse(Exam.objects.exists())

    def test_cannot_touch_other_teachers_exam(self):
        self.make_teacher()
        other = User.objects.create(username='o', telegram_id=7, role='teacher')
        exam = Exam.objects.create(title='Begona', created_by=other)
        for command in ('natija', 'xabar', 'kalit'):
            self.assertIn('topilmadi', self.send(f'/{command} {exam.access_code}')[0])
        self.assertEqual(self.send('/testlar'), ["Hali test yo'q."])
        self.assertEqual(self.press(f'launch:{exam.pk}'), ['Test topilmadi'])
        self.assertEqual(self.press('launch:yomon'), ['Test topilmadi'])
