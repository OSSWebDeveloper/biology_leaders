"""Majburiy kanal obunasi: o'quvchi kanalga a'zo ekanini Bot API orqali tekshiradi (bot kanalda admin bo'lishi kerak)."""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache

log = logging.getLogger(__name__)

MEMBER_STATUSES = {'creator', 'administrator', 'member'}
CACHE_SECONDS = 600


def is_not_member_error(description):
    """Telegram xatosi foydalanuvchi kanalda yo'qligini bildiradimi (sozlama xatosi emas)."""
    description = description.lower()
    return 'user not found' in description or 'participant_id_invalid' in description


def is_member_status(status, is_member=None):
    return status in MEMBER_STATUSES or (status == 'restricted' and bool(is_member))


def subscribe_markup():
    """Bot uchun: kanal havolasi va qayta tekshirish tugmasi (Bot API JSON ko'rinishida)."""
    rows = []
    if settings.REQUIRED_CHANNEL_URL:
        rows.append([{'text': "📢 Kanalga o'tish", 'url': settings.REQUIRED_CHANNEL_URL}])
    rows.append([{'text': "✅ Obuna bo'ldim", 'callback_data': 'sub:check'}])
    return {'inline_keyboard': rows}


SUBSCRIBE_TEXT = "Botdan foydalanish uchun kanalimizga obuna bo'ling, keyin «✅ Obuna bo'ldim» tugmasini bosing."


def required():
    return bool(settings.REQUIRED_CHANNEL_ID and settings.BOT_TOKEN)


def is_subscribed(telegram_id):
    """A'zo bo'lsa True. Telegram javob bermasa ham True: tarmoq uzilishi testni to'xtatmasin."""
    if not required() or not telegram_id:
        return True
    key = f'kanal-azo:{telegram_id}'
    if cache.get(key):
        return True
    query = urllib.parse.urlencode({'chat_id': settings.REQUIRED_CHANNEL_ID, 'user_id': telegram_id})
    try:
        with urllib.request.urlopen(
                f'https://api.telegram.org/bot{settings.BOT_TOKEN}/getChatMember?{query}', timeout=10) as response:
            member = json.load(response)['result']
    except urllib.error.HTTPError as exc:
        description = exc.read().decode(errors='replace').lower()
        if exc.code == 400 and is_not_member_error(description):
            return False
        log.warning('Obuna tekshirilmadi: HTTP %s %s', exc.code, description[:120])
        return True
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        log.warning('Obuna tekshirilmadi: %s', type(exc).__name__)
        return True
    ok = is_member_status(member.get('status'), member.get('is_member'))
    if ok:
        cache.set(key, True, CACHE_SECONDS)
    return ok


def forget(telegram_id):
    cache.delete(f'kanal-azo:{telegram_id}')
