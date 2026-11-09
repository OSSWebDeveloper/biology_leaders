import datetime

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from exams.tests import make_exam

from .models import BrowserLogin, User
from .services import approve_browser_login, touch_seen


@override_settings(TEACHER_BOT_USERNAME='ustoz_bot')
class EntryLinksTests(TestCase):
    def make(self, role, tg_id):
        return User.objects.create(username=f'u{tg_id}', role=role, telegram_id=tg_id)

    def browser_login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['browser_login'] = True
        session.save()

    def test_anonymous_gets_browser_login_page(self):
        for path, browser_only in (('/mrclayd/', True), ('/ustoz/', False)):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.context['browser_only'], browser_only)
            self.assertIn('https://t.me/ustoz_bot?start=login_', r.context['bot_link'])

    def test_admin_in_browser(self):
        self.browser_login(self.make(User.Role.ADMIN, 1))
        self.assertRedirects(self.client.get('/mrclayd/'), reverse('a_dashboard'))
        self.assertRedirects(self.client.get('/ustoz/'), reverse('t_exams'))

    def test_admin_from_telegram_web_app_not_let_into_mrclayd(self):
        self.client.force_login(self.make(User.Role.ADMIN, 1))
        r = self.client.get('/mrclayd/')
        self.assertEqual(r.status_code, 200)  # kirish sahifasi, panel emas
        self.assertTrue(r.context['browser_only'])
        self.assertEqual(self.client.get(reverse('a_dashboard')).status_code, 404)
        self.assertRedirects(self.client.get('/ustoz/'), reverse('t_exams'))

    def test_teacher(self):
        self.browser_login(self.make(User.Role.TEACHER, 2))
        self.assertEqual(self.client.get('/mrclayd/').status_code, 404)
        self.assertRedirects(self.client.get('/ustoz/'), reverse('t_exams'))

    def test_student(self):
        self.client.force_login(self.make(User.Role.STUDENT, 3))
        self.assertEqual(self.client.get('/ustoz/').status_code, 403)

    @override_settings(ADMIN_TELEGRAM_IDS={4})
    def test_admin_id_promoted_with_existing_session(self):
        self.browser_login(self.make(User.Role.TEACHER, 4))
        self.assertRedirects(self.client.get('/mrclayd/'), reverse('a_dashboard'))


@override_settings(TEACHER_BOT_USERNAME='ustoz_bot')
class BrowserLoginFlowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create(username='a', role=User.Role.ADMIN, telegram_id=10)
        self.client.get('/mrclayd/')
        self.token = self.client.session['browser_login_token']

    def status(self):
        return self.client.get(reverse('browser_login_status')).json()['ok']

    def test_pending_then_approved_logs_in_once(self):
        self.assertFalse(self.status())
        self.assertTrue(approve_browser_login(self.token, self.admin))
        self.assertTrue(self.status())
        self.assertRedirects(self.client.get('/mrclayd/'), reverse('a_dashboard'))
        self.assertEqual(self.client.get(reverse('a_dashboard')).status_code, 200)
        self.assertFalse(approve_browser_login(self.token, self.admin))  # ikkinchi marta ishlamaydi

    def test_other_browser_cannot_claim_token(self):
        approve_browser_login(self.token, self.admin)
        other = self.client_class()
        self.assertFalse(other.get(reverse('browser_login_status')).json()['ok'])

    def test_expired_token(self):
        BrowserLogin.objects.update(created_at=timezone.now() - datetime.timedelta(minutes=10))
        self.assertFalse(approve_browser_login(self.token, self.admin))
        self.assertFalse(self.status())


class StatsTests(TestCase):
    def test_dashboard_shows_online_and_in_progress(self):
        admin = User.objects.create(username='a', role=User.Role.ADMIN, telegram_id=10, full_name='Admin')
        student = User.objects.create(username='s', telegram_id=11, full_name='Ali Valiyev')
        touch_seen(student, 'last_bot_seen')
        exam = make_exam(owner=admin)
        exam.attempts.create(student=student, deadline=timezone.now() + datetime.timedelta(hours=1))
        self.client.force_login(admin)
        session = self.client.session
        session['browser_login'] = True
        session.save()
        r = self.client.get(reverse('a_dashboard'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['online_bot'], 1)
        self.assertEqual(r.context['online_site'], 1)  # admin o'zi
        self.assertEqual(len(r.context['in_progress']), 1)
        self.assertContains(r, 'Ali Valiyev')
