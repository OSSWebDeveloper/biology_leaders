import datetime

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from exams.tests import make_exam

from .models import User
from .services import touch_seen


class EntryLinksTests(TestCase):
    def make(self, role, tg_id):
        return User.objects.create(username=f'u{tg_id}', role=role, telegram_id=tg_id)

    def browser_login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['browser_login'] = True
        session.save()

    def test_anonymous_gets_password_page(self):
        for path, browser_only in (('/mrclayd/', True), ('/ustoz/', False)):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.context['browser_only'], browser_only)
            self.assertContains(r, 'type="password"')

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


class PasswordLoginTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create(username='a', role=User.Role.ADMIN, telegram_id=10)
        self.admin.set_password("to'g'ri-parol")
        self.admin.save()
        cache.clear()

    def test_correct_password_opens_admin_and_teacher(self):
        r = self.client.post('/mrclayd/', {'password': "to'g'ri-parol"})
        self.assertRedirects(r, '/mrclayd/', target_status_code=302)
        self.assertEqual(self.client.get(reverse('a_dashboard')).status_code, 200)
        self.assertRedirects(self.client.get('/ustoz/'), reverse('t_exams'))

    def test_password_on_ustoz(self):
        self.client.post('/ustoz/', {'password': "to'g'ri-parol"})
        self.assertRedirects(self.client.get('/ustoz/'), reverse('t_exams'))

    def test_wrong_password_and_lockout(self):
        for _ in range(5):
            r = self.client.post('/mrclayd/', {'password': 'xato'})
            self.assertContains(r, "Parol noto")
        r = self.client.post('/mrclayd/', {'password': "to'g'ri-parol"})
        self.assertContains(r, "marta xato kiritildi")
        self.assertEqual(self.client.get(reverse('a_dashboard')).status_code, 404)

    def test_teacher_password_not_accepted(self):
        teacher = User.objects.create(username='t', role=User.Role.TEACHER, telegram_id=11)
        teacher.set_password('ustoz-parol')
        teacher.save()
        self.assertContains(self.client.post('/mrclayd/', {'password': 'ustoz-parol'}), "Parol noto")


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
