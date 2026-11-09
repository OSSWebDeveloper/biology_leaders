import hashlib
import hmac
import json
import shutil
import tempfile
import time
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlencode

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import StudyGroup, User
from accounts.services import check_login_token, make_login_token, verify_init_data

from .models import Attempt, Exam, Question
from .pdf_import import parse_mcq_key
from .scoring import answers_match, grade_for, parse_value
from .services import finish_expired

TOKEN = '123:TEST'


class RaschTests(TestCase):
    # 6 o'quvchi, 5 savol: 1-savol eng oson, 5-savol eng qiyin
    RESPONSES = [
        [1, 1, 1, 1, 1],
        [1, 1, 1, 1, 0],
        [1, 1, 1, 0, 0],
        [1, 1, 0, 1, 0],
        [1, 0, 0, 0, 0],
        [0, 0, 0, 0, 0],
    ]

    def test_more_correct_means_higher_score(self):
        from .rasch import estimate, t_scores
        thetas, difficulties = estimate(self.RESPONSES)
        scores = t_scores(thetas)
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertGreater(scores[0], scores[1])
        self.assertGreater(scores[4], scores[5])
        # bir xil xom ball: bir xil Rasch ball
        self.assertEqual(scores[2], scores[3])
        # kam o'quvchi yechgan savol qiyinroq
        self.assertLess(difficulties[0], difficulties[1])
        self.assertLess(difficulties[3], difficulties[4])
        self.assertTrue(all(0 <= s <= 75 for s in scores))
        self.assertAlmostEqual(sum(scores) / len(scores), 50, delta=1)

    def test_degenerate_cases(self):
        from .rasch import estimate, t_scores
        self.assertEqual(t_scores(estimate([[1, 0, 1]])[0]), [50])
        self.assertEqual(t_scores(estimate([[1, 1], [1, 1]])[0]), [50, 50])
        self.assertEqual(t_scores([]), [])


def signed_init_data(user_id=777, token=TOKEN, auth_date=None):
    fields = {'auth_date': str(auth_date or int(time.time())), 'query_id': 'q',
              'user': json.dumps({'id': user_id, 'first_name': 'Ali'})}
    check = '\n'.join(f'{k}={fields[k]}' for k in sorted(fields))
    secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    fields['hash'] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def make_user(tg_id, role=User.Role.STUDENT):
    return User.objects.create(username=f'tg{tg_id}', telegram_id=tg_id, role=role, full_name=f'User {tg_id}')


def make_exam(owner=None, public=True, status=Exam.Status.PUBLISHED, **extra):
    extra.setdefault('max_attempts', 0)
    exam = Exam.objects.create(title='T', created_by=owner, is_public=public, status=status, **extra)
    Question.objects.create(exam=exam, number=1, kind='mcq', text='q1', correct='B')
    Question.objects.create(exam=exam, number=2, kind='matching', text='q2', correct='F')
    Question.objects.create(exam=exam, number=3, kind='open', text='q3', answer_a='2√5', answer_b='16/3')
    return exam


class ScoringTests(TestCase):
    def test_equivalent_forms(self):
        for given, key in [('2√5', '2√5'), ('√20', '2√5'), ('16/3', '16/3'), ('5,333333333', '5.3333333333'),
                           ('3,5', '3.5'), ('8π', '8π'), ('8pi', '8π'), ('−1/16', '-1/16'), ('2√3+1', '1+2√3'),
                           ('20 sm', '20'), ("54 000 so'm", '54000'), ('3 ta', '3'), ('(1+√5)/2', '(1+√5)/2')]:
            self.assertTrue(answers_match(given, key), (given, key))

    def test_wrong_and_bad_input(self):
        for given, key in [('2√6', '2√5'), ('5', '16/3'), ('', '1'), ('   ', '1'), ('1/0', '1'), ('9^9^9^9^9', '1'),
                           ('__import__("os")', '1'), ('√-4', '2'), ('5.33', '16/3')]:
            self.assertFalse(answers_match(given, key), (given, key))

    def test_decimals_ratios_and_units(self):
        self.assertEqual(parse_value('3,5'), 3.5)
        self.assertFalse(answers_match('3,7', '3,5'))  # avval «.5» birlik deb tashlanardi
        self.assertFalse(answers_match('3', '3,5'))
        self.assertTrue(answers_match('9 : 3 : 3 : 1', '9:3:3:1'))
        self.assertFalse(answers_match('1:1', '9:3:3:1'))  # nisbat bo'lish emas
        self.assertFalse(answers_match('3:1', '3'))
        self.assertFalse(answers_match('2c', '2n'))
        self.assertTrue(answers_match('2N', '2n'))
        self.assertTrue(answers_match('1, 3, 5', '1,3,5'))
        self.assertFalse(answers_match('1,3', '1,3,5'))
        self.assertFalse(answers_match('20 kg', '20 sm'))

    def test_text_answer_and_alternatives(self):
        self.assertTrue(answers_match('(-∞;3]', '(-∞; 3]'))
        self.assertTrue(answers_match('7', '5|7'))
        self.assertTrue(answers_match('√20', '1 or 2√5 or 9 OR 8π'))
        self.assertTrue(answers_match('9', '1 or 2√5 or 9 OR 8π'))
        self.assertTrue(answers_match('8π', '1 or 2√5 or 9 OR 8π'))
        self.assertFalse(answers_match('3', '1 or 2√5 or 9 OR 8π'))
        self.assertTrue(answers_match('sor', 'sor'))  # or faqat alohida so'z bo'lganda ajratadi
        self.assertFalse(answers_match('s', 'sor'))
        self.assertIsNone(parse_value('(((('))

    def test_grades(self):
        self.assertEqual([grade_for(s) for s in (70, 69.9, 65, 60, 55, 50, 46, 45.9)],
                         ['A+', 'A', 'A', 'B+', 'B', 'C+', 'C', ''])

    def test_key_table(self):
        self.assertEqual(parse_mcq_key(['№', 'Javob', '1', 'C', '8', 'D', '36', '4', '6']), {1: 'C', 8: 'D'})


@override_settings(BOT_TOKEN=TOKEN, ADMIN_TELEGRAM_IDS={999}, NOTIFY_DISABLED=True)
class AuthTests(TestCase):
    def test_signature(self):
        self.assertEqual(verify_init_data(signed_init_data())['id'], 777)
        self.assertIsNone(verify_init_data(signed_init_data(token='123:OTHER')))
        self.assertIsNone(verify_init_data(signed_init_data() + 'x'))
        self.assertIsNone(verify_init_data(signed_init_data(auth_date=int(time.time()) - 90000)))
        self.assertIsNone(verify_init_data(''))

    @override_settings(TEACHER_BOT_TOKEN='555:TEACHER')
    def test_init_data_from_teacher_bot(self):
        self.assertEqual(verify_init_data(signed_init_data(token='555:TEACHER'))['id'], 777)

    def _post(self, data):
        return self.client.post(reverse('tg_auth'), json.dumps({'init_data': data}), content_type='application/json')

    def test_login_creates_student_and_admin_from_env(self):
        self.assertEqual(self._post(signed_init_data(777)).status_code, 200)
        self.assertEqual(User.objects.get(telegram_id=777).role, 'student')
        self._post(signed_init_data(999))
        self.assertEqual(User.objects.get(telegram_id=999).role, 'admin')

    def test_landing_gives_csrf_cookie_for_telegram_login(self):
        # Oddiy test client CSRF ni tekshirmaydi: Web App oqimini aynan brauzerdagidek takrorlaymiz
        browser = Client(enforce_csrf_checks=True)
        payload = json.dumps({'init_data': signed_init_data(777)})
        without_token = browser.post(reverse('tg_auth'), payload, content_type='application/json')
        self.assertEqual(without_token.status_code, 403)
        browser.get(reverse('home'))
        token = browser.cookies['csrftoken'].value
        response = browser.post(reverse('tg_auth'), payload, content_type='application/json',
                                headers={'X-CSRFToken': token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(browser.get(reverse('home')).url, reverse('exam_list'))

    def test_forged_and_blocked_are_rejected(self):
        self.assertEqual(self._post('user=%7B%22id%22%3A1%7D&hash=abc').status_code, 403)
        make_user(555).__class__.objects.filter(telegram_id=555).update(is_active=False)
        self.assertEqual(self._post(signed_init_data(555)).status_code, 403)

    def test_login_link_is_single_use(self):
        user = make_user(1)
        token = make_login_token(user)
        self.assertEqual(check_login_token(token), user)
        self.assertEqual(self.client.get(reverse('login_link', args=[token])).status_code, 302)
        self.assertIsNone(check_login_token(token))
        self.assertIsNone(check_login_token('soxta'))


@override_settings(NOTIFY_DISABLED=True)
class FlowTests(TestCase):
    def setUp(self):
        self.student = make_user(10)
        self.client.force_login(self.student)
        self.exam = make_exam()
        self.q1, self.q2, self.q3 = self.exam.questions.all()

    def _start(self):
        response = self.client.post(reverse('attempt_start', args=[self.exam.access_code]))
        self.assertEqual(response.status_code, 302)
        return Attempt.objects.get(student=self.student, finished_at__isnull=True)

    def _answer(self, attempt, **body):
        return self.client.post(reverse('attempt_answer', args=[attempt.pk]), json.dumps(body),
                                content_type='application/json')

    def test_extreme_students_not_all_fifty(self):
        from .services import finalize, save_answer, start_attempt
        best, worst = make_user(11), make_user(12)
        for student, right in ((best, True), (worst, False)):
            attempt = start_attempt(self.exam, student)
            save_answer(attempt, self.q1, choice='B' if right else 'A')
            save_answer(attempt, self.q2, choice='F' if right else 'A')
            save_answer(attempt, self.q3, value_a='2√5' if right else '1', value_b='16/3' if right else '1')
            finalize(attempt)
        scores = dict(Attempt.objects.values_list('student_id', 'score'))
        self.assertEqual((scores[best.pk], scores[worst.pk]), (75, 0))  # avval ikkalasi 50 (C+) olardi

    def test_question_image_needs_access(self):
        from django.core.files.base import ContentFile
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        with override_settings(MEDIA_ROOT=media):
            self.q1.image.save('e1_1.png', ContentFile(b'PNG rasm'), save=True)
            url = self.q1.image_url
            self.assertEqual(self.client.get('/media/' + self.q1.image.name).status_code, 404)  # ochiq yo'l yopiq
            self.assertEqual(self.client.get(url).status_code, 404)  # test boshlanmagan
            attempt = self._start()
            self.assertIn(url, json.dumps(self.client.get(reverse('attempt', args=[attempt.pk])).context['payload']))
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b''.join(response.streaming_content), b'PNG rasm')
            self.client.logout()
            self.assertEqual(self.client.get(url).status_code, 302)  # login so'raladi
            owner = make_user(13, 'teacher')
            Exam.objects.filter(pk=self.exam.pk).update(created_by=owner)
            self.client.force_login(owner)
            self.assertEqual(self.client.get(url).status_code, 200)
            self.client.force_login(make_user(14, 'teacher'))  # boshqa o'qituvchi
            self.assertEqual(self.client.get(url).status_code, 404)

    @override_settings(REQUIRED_CHANNEL_ID='-1001', REQUIRED_CHANNEL_URL='https://t.me/kanal')
    def test_channel_subscription_required(self):
        with patch('tgbot.subscription.is_subscribed', return_value=False) as check:
            page = self.client.get(reverse('exam_list'))
            self.assertContains(page, "Kanalga obuna bo'ling")
            self.assertContains(page, 'https://t.me/kanal')
            self.client.post(reverse('attempt_start', args=[self.exam.access_code]))
            self.assertFalse(Attempt.objects.exists())
            check.assert_called_with(self.student.telegram_id)
        with patch('tgbot.subscription.is_subscribed', return_value=True):
            self._start()

    def test_subscription_check_reads_status(self):
        from tgbot import subscription
        self.assertTrue(subscription.is_member_status('member'))
        self.assertTrue(subscription.is_member_status('restricted', True))
        self.assertFalse(subscription.is_member_status('left'))
        self.assertFalse(subscription.is_member_status('kicked'))
        self.assertTrue(subscription.is_not_member_error('Bad Request: PARTICIPANT_ID_INVALID'))
        self.assertFalse(subscription.is_not_member_error('Bad Request: chat not found'))
        with override_settings(REQUIRED_CHANNEL_ID=''):
            self.assertTrue(subscription.is_subscribed(123))  # sozlanmagan: tekshirilmaydi

    def test_full_flow(self):
        attempt = self._start()
        page = self.client.get(reverse('attempt', args=[attempt.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertNotIn('correct', json.dumps(page.context['payload']))
        self.assertNotIn('answer_a', json.dumps(page.context['payload']))
        self._answer(attempt, question=self.q1.pk, choice='B')
        self._answer(attempt, question=self.q2.pk, choice='A')
        self._answer(attempt, question=self.q3.pk, value_a='√20', value_b='5')
        self.client.post(reverse('attempt_finish', args=[attempt.pk]))
        attempt.refresh_from_db()
        self.assertEqual((attempt.correct_items, attempt.total_items), (2, 4))
        self.assertEqual(attempt.percent, 50)
        # Rasch yagona ishtirokchini ajrata olmaydi: ball to'g'ri javoblar ulushidan (75 · 50%)
        self.assertEqual(attempt.score, 37.5)
        self.assertEqual(attempt.grade, '')
        self.assertEqual(self.client.get(reverse('attempt_result', args=[attempt.pk])).status_code, 200)
        self.assertEqual(self._answer(attempt, question=self.q1.pk, choice='A').status_code, 409)

    def test_invalid_letter_ignored_and_foreign_question_rejected(self):
        attempt = self._start()
        self._answer(attempt, question=self.q1.pk, choice='F')  # A-D savolda F yo'q
        self.assertEqual(attempt.answers.get(question=self.q1).choice, '')
        other = make_exam().questions.first()
        self.assertEqual(self._answer(attempt, question=other.pk, choice='A').status_code, 400)

    def test_restart_resumes_same_attempt(self):
        first = self._start()
        self.client.post(reverse('attempt_start', args=[self.exam.access_code]))
        self.assertEqual(Attempt.objects.filter(student=self.student).count(), 1)
        self.assertEqual(Attempt.objects.get(student=self.student).pk, first.pk)

    def test_expired_attempt_is_closed_and_answers_refused(self):
        attempt = self._start()
        self._answer(attempt, question=self.q1.pk, choice='B')
        Attempt.objects.filter(pk=attempt.pk).update(deadline=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self._answer(attempt, question=self.q1.pk, choice='A').status_code, 409)
        attempt.refresh_from_db()
        self.assertTrue(attempt.is_finished)
        self.assertEqual(attempt.correct_items, 1)

    def test_background_finish(self):
        attempt = self._start()
        Attempt.objects.filter(pk=attempt.pk).update(deadline=timezone.now() - timedelta(seconds=1))
        self.assertEqual(finish_expired(), 1)
        self.assertEqual(finish_expired(), 0)

    def test_max_attempts(self):
        Exam.objects.filter(pk=self.exam.pk).update(max_attempts=1)
        attempt = self._start()
        self.client.post(reverse('attempt_finish', args=[attempt.pk]))
        self.client.post(reverse('attempt_start', args=[self.exam.access_code]))
        self.assertEqual(Attempt.objects.filter(student=self.student).count(), 1)

    def test_other_student_cannot_touch_attempt(self):
        attempt = self._start()
        self.client.force_login(make_user(11))
        for name in ('attempt', 'attempt_result'):
            self.assertEqual(self.client.get(reverse(name, args=[attempt.pk])).status_code, 403)
        self.assertEqual(self._answer(attempt, question=self.q1.pk, choice='B').status_code, 403)
        self.assertEqual(self.client.post(reverse('attempt_finish', args=[attempt.pk])).status_code, 403)

    def test_single_answer_written_question(self):
        q = Question.objects.create(exam=self.exam, number=4, kind='open', two_parts=False, answer_a='5 or 7')
        self.assertTrue(q.has_key())
        self.assertEqual(q.max_items, 1)
        attempt = self._start()
        page = self.client.get(reverse('attempt', args=[attempt.pk]))
        item = next(i for i in page.context['payload']['questions'] if i['id'] == q.pk)
        self.assertFalse(item['two_parts'])
        self._answer(attempt, question=q.pk, value_a='7')
        self.client.post(reverse('attempt_finish', args=[attempt.pk]))
        attempt.refresh_from_db()
        self.assertEqual(attempt.total_items, 5)  # yopiq 1, moslashtirish 1, a/b 2, bitta javobli 1
        self.assertEqual(attempt.correct_items, 1)
        answer = attempt.answers.get(question=q)
        self.assertTrue(answer.correct_a)
        self.assertFalse(answer.correct_b)

    def test_exam_is_reachable_only_by_code(self):
        page = self.client.get(reverse('exam_list'))
        self.assertNotContains(page, self.exam.title + '<')
        self.assertNotContains(page, self.exam.access_code)
        wrong = self.client.post(reverse('exam_list'), {'code': 'YOQ123'}, follow=True)
        self.assertContains(wrong, 'kod topilmadi')
        # kichik harf va bo'sh joy bilan yozsa ham topiladi
        response = self.client.post(reverse('exam_list'), {'code': f' {self.exam.access_code.lower()} '})
        self.assertRedirects(response, reverse('exam_detail', args=[self.exam.access_code]))
        self.assertEqual(self.client.get(f'/test/{self.exam.pk}/').status_code, 404)

    def test_draft_code_does_not_work(self):
        draft = make_exam(status=Exam.Status.DRAFT)
        self.assertEqual(self.client.get(reverse('exam_detail', args=[draft.access_code])).status_code, 404)
        self.assertEqual(self.client.post(reverse('attempt_start', args=[draft.access_code])).status_code, 404)
        self.client.post(reverse('exam_list'), {'code': draft.access_code})
        self.assertFalse(Attempt.objects.exists())

    def test_cannot_start_before_opening(self):
        Exam.objects.filter(pk=self.exam.pk).update(opens_at=timezone.now() + timedelta(hours=1))
        page = self.client.get(reverse('exam_detail', args=[self.exam.access_code]))
        self.assertContains(page, 'da boshlanadi')
        self.client.post(reverse('attempt_start', args=[self.exam.access_code]))
        self.assertFalse(Attempt.objects.exists())

    def test_student_sees_no_score(self):
        attempt = self._start()
        self.client.post(reverse('attempt_finish', args=[attempt.pk]))
        attempt.refresh_from_db()
        for page in (self.client.get(reverse('attempt_result', args=[attempt.pk])),
                     self.client.get(reverse('my_results')),
                     self.client.get(reverse('exam_detail', args=[self.exam.access_code]))):
            self.assertContains(page, 'Natijalar guruhga tashlanadi')
            self.assertNotContains(page, 'ball')
            self.assertNotContains(page, 'Javobingiz')

    def test_leaderboard_only_for_teacher(self):
        self._start()
        self.assertEqual(self.client.get(reverse('leaderboard', args=[self.exam.pk])).status_code, 404)

    def test_closed_window(self):
        Exam.objects.filter(pk=self.exam.pk).update(closes_at=timezone.now() - timedelta(minutes=1))
        self.client.post(reverse('attempt_start', args=[self.exam.access_code]))
        self.assertFalse(Attempt.objects.filter(student=self.student).exists())

    def test_deadline_capped_by_close_time(self):
        closes = timezone.now() + timedelta(minutes=5)
        Exam.objects.filter(pk=self.exam.pk).update(closes_at=closes)
        self.assertLessEqual(self._start().deadline, closes)

    def test_regrade_after_key_fix(self):
        attempt = self._start()
        self._answer(attempt, question=self.q1.pk, choice='A')
        self.client.post(reverse('attempt_finish', args=[attempt.pk]))
        teacher = make_user(30, 'admin')
        self.client.force_login(teacher)
        self.client.post(reverse('t_exam', args=[self.exam.pk]), {f'c_{self.q1.pk}': 'A', f'c_{self.q2.pk}': 'F',
                                                                  f'a_{self.q3.pk}': '1', f'b_{self.q3.pk}': '2'})
        attempt.refresh_from_db()
        self.assertEqual(attempt.correct_items, 1)


@override_settings(NOTIFY_DISABLED=True)
class RoleTests(TestCase):
    def setUp(self):
        self.teacher = make_user(40, 'teacher')
        self.other = make_user(41, 'teacher')
        self.admin = make_user(42, 'admin')
        self.student = make_user(43)
        self.exam = make_exam(owner=self.teacher, public=False, status=Exam.Status.DRAFT)

    def test_student_blocked_from_panels(self):
        self.client.force_login(self.student)
        for url in (reverse('t_exams'), reverse('t_exam', args=[self.exam.pk])):
            self.assertEqual(self.client.get(url).status_code, 403, url)
        for url in (reverse('a_dashboard'), reverse('a_users')):  # texnik qism borligi bilinmaydi
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_anonymous_redirected(self):
        for url in (reverse('exam_list'), reverse('t_exams')):
            self.assertEqual(self.client.get(url).status_code, 302, url)
        self.assertEqual(self.client.get(reverse('a_dashboard')).status_code, 404)

    def test_teacher_cannot_touch_foreign_exam_or_admin(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('t_exam', args=[self.exam.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('t_publish', args=[self.exam.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('a_users')).status_code, 404)

    def _settings(self, **extra):
        return {'title': 'T', 'code': 'KOD1', 'duration_min': 10, 'count_mcq': 1,
                'count_matching': 1, 'count_open': 1, 'opens_at': '2030-01-01T09:00', **extra}

    def kinds(self, exam):
        return list(exam.questions.order_by('number').values_list('number', 'kind'))

    def test_edit_counts_adds_removes_and_renumbers_keeping_keys(self):
        self.client.force_login(self.teacher)
        url = reverse('t_exam_edit', args=[self.exam.pk])
        r = self.client.get(url)
        self.assertContains(r, '4 variantli savollar soni')
        self.assertNotContains(r, 'vazni')
        self.assertNotContains(r, 'Urinishlar')
        self.assertNotContains(r, 'id_subject')
        self.assertNotContains(r, 'id_closes_at')
        self.assertEqual(self.client.post(url, self._settings(count_mcq=3, count_matching=0, count_open=2)).status_code, 302)
        self.assertEqual(self.kinds(self.exam), [(1, 'mcq'), (2, 'mcq'), (3, 'mcq'), (4, 'open'), (5, 'open')])
        self.assertEqual(self.exam.questions.get(number=1).correct, 'B')  # eski kalit qoldi
        self.assertEqual(self.exam.questions.get(number=4).answer_a, '2√5')

    def test_counts_locked_after_attempts(self):
        self.client.force_login(self.teacher)
        Attempt.objects.create(exam=self.exam, student=self.student, deadline=timezone.now())
        url = reverse('t_exam_edit', args=[self.exam.pk])
        r = self.client.post(url, self._settings(count_mcq=5))
        self.assertContains(r, "sonini o")
        self.assertEqual(self.client.post(url, self._settings()).status_code, 302)  # son o'zgarmasa bo'ladi

    def test_new_exam_creates_sheet(self):
        self.client.force_login(self.teacher)
        self.client.post(reverse('t_exam_new'), self._settings(count_mcq=2, count_matching=1, count_open=0))
        exam = Exam.objects.latest('pk')
        self.assertEqual(self.kinds(exam), [(1, 'mcq'), (2, 'mcq'), (3, 'matching')])

    def test_new_exam_with_word_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(reverse('t_exam_new')), 'id_test_file')
        upload = SimpleUploadedFile('test.docx', b'PK word')
        r = self.client.post(reverse('t_exam_new'), {**self._settings(count_mcq=2, count_matching=0, count_open=1),
                                                     'test_file': upload})
        exam = Exam.objects.latest('pk')
        self.assertRedirects(r, reverse('t_exam', args=[exam.pk]))
        self.assertTrue(exam.attachment.name.endswith('.docx'))
        self.assertEqual(exam.questions.count(), 3)  # fayl soni o'zgartirmaydi
        exam.attachment.delete(save=False)

    def test_new_form_code_and_empty_duration(self):
        self.client.force_login(self.teacher)
        form = self.client.get(reverse('t_exam_new')).context['form']
        self.assertIsNone(form.initial.get('duration_min'))
        self.assertEqual(list(form.fields)[:3], ['title', 'code', 'description'])
        self.client.post(reverse('t_exam_new'), self._settings(code=' abc12 '))
        self.assertEqual(Exam.objects.latest('pk').access_code, 'ABC12')
        r = self.client.post(reverse('t_exam_new'), self._settings(code='ABC12'))
        self.assertContains(r, 'boshqa testda band')
        r = self.client.post(reverse('t_exam_new'), self._settings(code='a b'))
        self.assertContains(r, "lotin harfi")

    def test_exam_page_without_extra_buttons(self):
        self.client.force_login(self.teacher)
        Question.objects.filter(exam=self.exam).update(correct='', answer_a='')
        r = self.client.get(reverse('t_exam', args=[self.exam.pk]))
        self.assertNotContains(r, 'Kalitsiz savollar')
        self.assertNotContains(r, 'Fayl yuklash')
        self.assertNotContains(r, reverse('t_results', args=[self.exam.pk]))

    def test_bad_file_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.teacher)
        r = self.client.post(reverse('t_exam_new'), {**self._settings(), 'test_file': SimpleUploadedFile('a.txt', b'x')})
        self.assertContains(r, 'Faqat PDF yoki Word')

    def test_exam_form_requires_start_and_end(self):
        self.client.force_login(self.teacher)
        url = reverse('t_exam_edit', args=[self.exam.pk])
        missing = self._settings()
        del missing['opens_at']
        self.assertEqual(self.client.post(url, missing).status_code, 200)
        self.assertEqual(self.client.post(url, self._settings(is_public='on')).status_code, 302)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.closes_at - self.exam.opens_at, timedelta(minutes=10))  # avtomatik
        self.assertFalse(self.exam.is_public)

    def test_publish_rules(self):
        self.client.force_login(self.teacher)
        self.client.post(reverse('t_publish', args=[self.exam.pk]))  # vaqt yo'q
        self.exam.refresh_from_db()
        self.assertFalse(self.exam.is_published)
        Exam.objects.filter(pk=self.exam.pk).update(opens_at=timezone.now(),
                                                    closes_at=timezone.now() + timedelta(hours=1))
        Question.objects.filter(exam=self.exam, number=1).update(correct='')
        self.client.post(reverse('t_publish', args=[self.exam.pk]))  # kalit yo'q
        self.exam.refresh_from_db()
        self.assertFalse(self.exam.is_published)
        Question.objects.filter(exam=self.exam, number=1).update(correct='A')
        self.client.post(reverse('t_publish', args=[self.exam.pk]))
        self.exam.refresh_from_db()
        self.assertTrue(self.exam.is_published)

    def login_admin_browser(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session['browser_login'] = True
        session.save()

    def test_admin_panel_only_in_browser_session(self):
        self.client.force_login(self.admin)  # Telegram Web App sessiyasi
        self.assertEqual(self.client.get(reverse('a_dashboard')).status_code, 404)
        self.login_admin_browser()
        self.assertEqual(self.client.get(reverse('a_dashboard')).status_code, 200)

    def test_admin_changes_role_but_not_self(self):
        self.login_admin_browser()
        self.client.post(reverse('a_user_update', args=[self.student.pk]), {'role': 'teacher'})
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, 'teacher')
        self.client.post(reverse('a_user_update', args=[self.admin.pk]), {'role': 'student'})
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, 'admin')

    def test_all_panel_pages_render(self):
        self.login_admin_browser()
        group = StudyGroup.objects.create(name='G', teacher=self.admin)
        q = self.exam.questions.first()
        for url in (reverse('t_exams'), reverse('t_exam_new'), reverse('t_exam', args=[self.exam.pk]),
                    reverse('t_exam_edit', args=[self.exam.pk]), reverse('t_pdf', args=[self.exam.pk]),
                    reverse('t_results', args=[self.exam.pk]), reverse('t_results_xlsx', args=[self.exam.pk]),
                    reverse('t_question', args=[self.exam.pk, q.pk]), reverse('t_question_new', args=[self.exam.pk]),
                    reverse('t_groups'), reverse('t_group', args=[group.pk]), reverse('a_dashboard'),
                    reverse('a_users'), reverse('my_results'), reverse('exam_list')):
            self.assertEqual(self.client.get(url).status_code, 200, url)


class PdfUploadViewTests(TestCase):
    def test_teacher_uploads_pdf_and_gets_keys(self):
        import pymupdf
        from django.core.files.uploadedfile import SimpleUploadedFile
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((60, 80), '1. Savol')
        page.insert_text((75, 96), 'A) 1')
        page.insert_text((60, 150), '2. Savol')
        page.insert_text((75, 166), 'A) 2')
        key = doc.new_page()
        for i, text in enumerate(['JAVOBLAR', '1', 'C', '2', 'D']):
            key.insert_text((60, 80 + i * 16), text)
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        teacher = make_user(50, 'teacher')
        exam = Exam.objects.create(title='P', created_by=teacher)
        self.client.force_login(teacher)
        with override_settings(MEDIA_ROOT=media):
            upload = SimpleUploadedFile('t.pdf', doc.tobytes(), content_type='application/pdf')
            response = self.client.post(reverse('t_pdf', args=[exam.pk]), {'pdf': upload})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(list(exam.questions.values_list('number', 'correct')), [(1, 'C'), (2, 'D')])
            self.assertEqual(self.client.get(reverse('t_exam', args=[exam.pk])).status_code, 200)
            bad = SimpleUploadedFile('t.pdf', b'emas', content_type='application/pdf')
            self.assertEqual(self.client.post(reverse('t_pdf', args=[exam.pk]), {'pdf': bad}).status_code, 200)
            # guruhga ketadigan nusxada kalit qolmasligi kerak
            exam.refresh_from_db()
            with exam.attachment.open('rb') as saved:
                clean = pymupdf.open(stream=saved.read(), filetype='pdf')
            text = ''.join(page.get_text() for page in clean)
            self.assertIn('1. Savol', text)
            self.assertNotIn('JAVOBLAR', text)

    def _teacher_exam(self, media):
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        teacher = make_user(51, 'teacher')
        self.client.force_login(teacher)
        return teacher, Exam.objects.create(title='Matematika 1', created_by=teacher,
                                            opens_at=timezone.now(), closes_at=timezone.now() + timedelta(hours=2))

    def test_word_upload_creates_answer_sheet_and_student_can_answer(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        media = tempfile.mkdtemp()
        _, exam = self._teacher_exam(media)
        with override_settings(MEDIA_ROOT=media):
            fake = SimpleUploadedFile('t.docx', b'emas', content_type='application/octet-stream')
            self.assertEqual(self.client.post(reverse('t_pdf', args=[exam.pk]), {'pdf': fake}).status_code, 200)
            word = SimpleUploadedFile('t.docx', b'PK\x03\x04word', content_type='application/octet-stream')
            self.assertEqual(self.client.post(reverse('t_pdf', args=[exam.pk]), {'pdf': word}).status_code, 302)
            exam.refresh_from_db()
            self.assertTrue(exam.attachment.name.endswith('.docx'))
            kinds = [exam.questions.filter(kind=k).count() for k in ('mcq', 'matching', 'open')]
            self.assertEqual(kinds, [32, 3, 10])
            self.assertEqual(self.client.get(reverse('t_exam', args=[exam.pk])).status_code, 200)
            exam.status = Exam.Status.PUBLISHED
            exam.save(update_fields=['status'])
            self.client.force_login(make_user(52))
            response = self.client.post(reverse('attempt_start', args=[exam.access_code]), follow=True)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.context['payload']['questions']), 45)

    def test_second_upload_keeps_questions(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        media = tempfile.mkdtemp()
        _, exam = self._teacher_exam(media)
        Question.objects.create(exam=exam, number=1, text='q', correct='A')
        with override_settings(MEDIA_ROOT=media):
            word = SimpleUploadedFile('t.doc', b'\xd0\xcf\x11\xe0word', content_type='application/octet-stream')
            self.client.post(reverse('t_pdf', args=[exam.pk]), {'pdf': word})
        self.assertEqual(exam.questions.count(), 1)

    def test_send_announcement_to_teacher(self):
        from django.core.files.base import ContentFile
        media = tempfile.mkdtemp()
        _, exam = self._teacher_exam(media)
        url = reverse('t_send', args=[exam.pk])
        with override_settings(MEDIA_ROOT=media), patch('tgbot.notify._send_document', return_value=True) as send:
            self.assertContains(self.client.post(url, follow=True), 'Avval testni')
            exam.status = Exam.Status.PUBLISHED
            exam.save(update_fields=['status'])
            self.assertContains(self.client.post(url, follow=True), 'faylini')
            send.assert_not_called()
            exam.attachment.save('t.pdf', ContentFile(b'%PDF'), save=True)
            self.assertContains(self.client.post(url, follow=True), 'guruhga uzating')
            chat_id, data, filename, caption = send.call_args.args
            self.assertEqual((chat_id, data, filename), (51, b'%PDF', 'Matematika_1.pdf'))
            self.assertIn(exam.access_code, caption)
            self.assertIn(timezone.localtime(exam.closes_at).strftime('%d.%m.%Y %H:%M'), caption)
            send.return_value = False
            self.assertContains(self.client.post(url, follow=True), 'yuborilmadi')


class PdfImportTests(TestCase):
    def test_bad_file(self):
        from .pdf_import import PdfImportError, slice_pdf
        with self.assertRaises(PdfImportError):
            slice_pdf(b'bu pdf emas')

    def test_generated_pdf(self):
        import pymupdf
        from .pdf_import import slice_pdf
        doc = pymupdf.open()
        page = doc.new_page()
        y = 80
        for n in range(1, 4):
            page.insert_text((60, y), f'{n}. Savol matni')
            page.insert_text((75, y + 16), 'A) 1')
            y += 60
        page.insert_text((60, y), '4. Yozma savol')
        page.insert_text((75, y + 16), 'a) qiymatni toping')
        key = doc.new_page()
        lines = ['JAVOBLAR', '1', 'C', '2', 'A', '3', 'B']
        for i, text in enumerate(lines):
            key.insert_text((60, 80 + i * 16), text)
        result = slice_pdf(doc.tobytes())
        self.assertEqual([s.number for s in result.slices], [1, 2, 3, 4])
        self.assertEqual(result.slices[3].kind, 'open')
        self.assertEqual(result.mcq_key, {1: 'C', 2: 'A', 3: 'B'})
        self.assertTrue(result.slices[0].png.startswith(b'\x89PNG'))
