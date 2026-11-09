from django.test import TestCase, override_settings
from django.urls import reverse

from .models import User


class EntryLinksTests(TestCase):
    def make(self, role, tg_id):
        return User.objects.create(username=f'u{tg_id}', role=role, telegram_id=tg_id)

    def test_anonymous_gets_login_page_returning_to_same_path(self):
        for path in ('/mrclayd/', '/ustoz/'):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.context['after_login'], path)

    def test_admin_goes_to_dashboard(self):
        self.client.force_login(self.make(User.Role.ADMIN, 1))
        self.assertRedirects(self.client.get('/mrclayd/'), reverse('a_dashboard'))
        self.assertRedirects(self.client.get('/ustoz/'), reverse('t_exams'))

    def test_teacher(self):
        self.client.force_login(self.make(User.Role.TEACHER, 2))
        self.assertEqual(self.client.get('/mrclayd/').status_code, 404)
        self.assertRedirects(self.client.get('/ustoz/'), reverse('t_exams'))

    def test_student(self):
        self.client.force_login(self.make(User.Role.STUDENT, 3))
        self.assertEqual(self.client.get('/mrclayd/').status_code, 404)
        self.assertEqual(self.client.get('/ustoz/').status_code, 403)

    @override_settings(ADMIN_TELEGRAM_IDS={4})
    def test_admin_id_promoted_with_existing_session(self):
        self.client.force_login(self.make(User.Role.TEACHER, 4))
        self.assertRedirects(self.client.get('/mrclayd/'), reverse('a_dashboard'))
