"""Django tomonidan bot orqali xabar yuborish. Sahifani kutdirmaslik uchun fon oqimida ishlaydi."""
import json
import logging
import threading
import time
import urllib.error
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)


def _post(chat_id, text, reply_markup=None):
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    request = urllib.request.Request(
        f'https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage',
        data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'},
    )
    try:
        urllib.request.urlopen(request, timeout=15).read()
    except (urllib.error.URLError, OSError) as exc:
        # Xatoda URL (token bor) logga tushmasligi uchun faqat turi yoziladi
        log.warning('Telegram xabari yuborilmadi: %s', type(exc).__name__)


def _send_many(messages):
    for index, message in enumerate(messages):
        if index:
            time.sleep(0.05)  # Telegram cheklovi: sekundiga ~30 xabar
        _post(*message)


def _background(messages):
    if settings.BOT_TOKEN and messages and not getattr(settings, 'NOTIFY_DISABLED', False):
        threading.Thread(target=_send_many, args=(messages,), daemon=True).start()


def _open_button(path, label):
    if not settings.WEBAPP_IS_HTTPS:
        return None
    return {'inline_keyboard': [[{'text': label, 'web_app': {'url': settings.WEBAPP_URL + path}}]]}


def attempt_result(attempt):
    student = attempt.student
    if not student.telegram_id:
        return
    grade = attempt.grade or 'darajasiz'
    text = (f"✅ <b>{_esc(attempt.exam.title)}</b> yakunlandi\n\n"
            f"To'g'ri: <b>{attempt.correct_items}</b> / {attempt.total_items}\n"
            f"Taxminiy ball: <b>{attempt.score}</b> / 75\n"
            f"Daraja: <b>{grade}</b>")
    _background([(student.telegram_id, text, _open_button(f'/urinish/{attempt.pk}/natija/', "📊 Tahlilni ko'rish"))])


def exam_published(exam):
    students = {}
    for group in exam.groups.prefetch_related('students'):
        for student in group.students.all():
            if student.telegram_id:
                students[student.telegram_id] = student
    text = f"🆕 Yangi test: <b>{_esc(exam.title)}</b>\nVaqt: {exam.duration_min} daqiqa"
    markup = _open_button(f'/test/{exam.pk}/', '📝 Testni ochish')
    _background([(tg_id, text, markup) for tg_id in students])


def _esc(text):
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
