"""Django tomonidan bot orqali xabar yuborish. Sahifani kutdirmaslik uchun fon oqimida ishlaydi."""
import json
import logging
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import PurePath

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.utils import timezone
from django.utils.text import get_valid_filename

log = logging.getLogger(__name__)


def send_text(chat_id, text):
    """Sinxron matnli xabar; yuborildimi."""
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    request = urllib.request.Request(
        f'https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage',
        data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'},
    )
    try:
        urllib.request.urlopen(request, timeout=15).read()
    except (urllib.error.URLError, OSError) as exc:
        log.warning('Kanal xabari yuborilmadi: %s', type(exc).__name__)
        return False
    return True


def channel_announcement(exam, chat_id):
    """Kanalga e'lon: fayl bo'lsa fayl bilan, bo'lmasa matn."""
    if getattr(settings, 'NOTIFY_DISABLED', False) or not settings.BOT_TOKEN:
        return False
    if exam.attachment:
        return exam_announcement(exam, chat_id)
    return send_text(chat_id, announcement_caption(exam))


MESSAGE_LIMIT = 3800  # Telegram cheklovi 4096 belgi


def results_messages(exam, attempts):
    """Natijalar ro'yxati: bitta xabarga sig'masa bir nechtaga bo'linadi."""
    own = sum(1 for a in attempts if a.finished_at < a.deadline)
    head = (f"📊 <b>{esc(exam.title)}</b>: natijalar\n\n"
            f"👥 Qatnashdi: {len(attempts)}\n"
            f"✅ O'zi topshirdi: {own}\n"
            f"⏱ Vaqt tugab yakunlandi: {len(attempts) - own}\n\n"
            "<b>№. F.I.Sh. — to'g'ri — ball — daraja</b>")
    messages, current = [], head
    for index, a in enumerate(attempts, 1):
        line = (f"{index}. {esc(a.student.display_name)} — {a.correct_items}/{a.total_items} — "
                f"{a.score:g} — {a.grade or '—'}")
        if len(current) + len(line) + 1 > MESSAGE_LIMIT:
            messages.append(current)
            current = line
        else:
            current += '\n' + line
    messages.append(current)
    return messages


def channel_results(exam, chat_id, attempts):
    """Natijalarni kanalga yuboradi. Birinchi xabar ketmasa False (keyin qayta uriniladi);
    keyingilari ketmasa ham True: qayta urinish ro'yxat boshini ikki marta chiqarib qo'ymasin."""
    if getattr(settings, 'NOTIFY_DISABLED', False) or not settings.BOT_TOKEN:
        return False
    for index, text in enumerate(results_messages(exam, attempts)):
        if index:
            time.sleep(1)  # kanalga ketma-ket xabar: Telegram cheklovi
        if not send_text(chat_id, text):
            if not index:
                return False
            log.warning('Natijalar ro\'yxatining %s-qismi kanalga yuborilmadi', index + 1)
            break
    return True


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
    text = f"✅ <b>{esc(attempt.exam.title)}</b> yakunlandi.\n\nNatijalar guruhga tashlanadi."
    _background([(student.telegram_id, text, None)])


def announcement_caption(exam):
    bot = f'@{settings.BOT_USERNAME}' if settings.BOT_USERNAME else 'botga kiring'
    return (f"📝 <b>{esc(exam.title)}</b>\n\n"
            f"🔑 Kirish kodi: <code>{exam.access_code}</code>\n"
            f"🕘 Boshlanish: {timezone.localtime(exam.opens_at):%d.%m.%Y %H:%M}\n"
            f"🏁 Tugash: {timezone.localtime(exam.closes_at):%d.%m.%Y %H:%M}\n"
            f"⏱ Vaqt: {exam.duration_min} daqiqa\n\n"
            f"Testni yechish: {bot} → «Testlar» → kirish kodini yozing.")


def announcement_filename(exam):
    extension = PurePath(exam.attachment.name).suffix
    try:
        return get_valid_filename(exam.title) + extension
    except SuspiciousFileOperation:  # nomi faqat belgilardan iborat
        return 'test' + extension


def exam_announcement(exam, chat_id):
    """Guruhga uzatiladigan xabar: fayl + kod + vaqtlar. Natijani o'qituvchiga aytish uchun sinxron."""
    with exam.attachment.open('rb') as source:
        return _send_document(chat_id, source.read(), announcement_filename(exam), announcement_caption(exam))


def _send_document(chat_id, data, filename, caption):
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in (('chat_id', str(chat_id)), ('caption', caption), ('parse_mode', 'HTML')):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{filename}"\r\n'
                 'Content-Type: application/octet-stream\r\n\r\n'.encode())
    parts += [data, f'\r\n--{boundary}--\r\n'.encode()]
    request = urllib.request.Request(
        f'https://api.telegram.org/bot{settings.BOT_TOKEN}/sendDocument', data=b''.join(parts),
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
    )
    try:
        urllib.request.urlopen(request, timeout=120).read()
    except (urllib.error.URLError, OSError) as exc:
        # Xatoda URL (token bor) logga tushmasligi uchun faqat turi yoziladi
        log.warning('Test fayli yuborilmadi: %s', type(exc).__name__)
        return False
    return True


def esc(text):
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
