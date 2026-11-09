"""Telegram orqali kirish: initData tekshiruvi, foydalanuvchi yaratish, bir martalik havola."""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from django.conf import settings
import datetime
import secrets

from django.core import signing
from django.utils import timezone

from .models import BrowserLogin, User

INIT_DATA_MAX_AGE = 24 * 60 * 60
LOGIN_LINK_MAX_AGE = 10 * 60
_LOGIN_SALT = 'accounts.login-link'


def verify_init_data(init_data, bot_token=None, max_age=INIT_DATA_MAX_AGE):
    """Telegram Web App initData imzosini tekshiradi; to'g'ri bo'lsa user lug'atini qaytaradi.

    Algoritm: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    bot_token = bot_token or settings.BOT_TOKEN
    if not init_data or not bot_token:
        return None
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop('hash', None)
    if not received:
        return None
    check = '\n'.join(f'{k}={pairs[k]}' for k in sorted(pairs))
    secret = hmac.new(b'WebAppData', bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return None
    try:
        if time.time() - int(pairs.get('auth_date', 0)) > max_age:
            return None
        user = json.loads(pairs.get('user', ''))
    except ValueError:
        return None
    return user if isinstance(user, dict) and user.get('id') else None


def get_or_create_tg_user(tg_id, first_name='', last_name='', username=''):
    """Telegram foydalanuvchisini topadi yoki o'quvchi sifatida yaratadi."""
    tg_id = int(tg_id)
    user, created = User.objects.get_or_create(
        telegram_id=tg_id,
        defaults={'username': f'tg{tg_id}', 'first_name': (first_name or '')[:150],
                  'last_name': (last_name or '')[:150]},
    )
    if created:
        user.set_unusable_password()
    if tg_id in settings.ADMIN_TELEGRAM_IDS and user.role != User.Role.ADMIN:
        user.role = User.Role.ADMIN
        created = True
    if created:
        user.save()
    return user


def make_login_token(user):
    """Brauzer uchun bir martalik havola: kirishda last_login o'zgaradi va token bekor bo'ladi."""
    stamp = user.last_login.isoformat() if user.last_login else ''
    return signing.dumps({'u': user.pk, 'l': stamp}, salt=_LOGIN_SALT)


def check_login_token(token):
    try:
        data = signing.loads(token, salt=_LOGIN_SALT, max_age=LOGIN_LINK_MAX_AGE)
        user = User.objects.get(pk=data['u'], is_active=True)
    except (signing.BadSignature, User.DoesNotExist, KeyError):
        return None
    stamp = user.last_login.isoformat() if user.last_login else ''
    return user if stamp == data.get('l') else None


BROWSER_LOGIN_MAX_AGE = 5 * 60
SEEN_STEP = 60  # oxirgi faollik shundan tez-tez yozilmaydi


def touch_seen(user, field='last_seen'):
    """Foydalanuvchi faolligini belgilaydi (statistikadagi «hozir onlayn» uchun)."""
    now = timezone.now()
    last = getattr(user, field)
    if last and (now - last).total_seconds() < SEEN_STEP:
        return
    setattr(user, field, now)
    User.objects.filter(pk=user.pk).update(**{field: now})


def create_browser_login():
    BrowserLogin.objects.filter(
        created_at__lt=timezone.now() - datetime.timedelta(seconds=BROWSER_LOGIN_MAX_AGE)).delete()
    return BrowserLogin.objects.create(token=secrets.token_urlsafe(24)).token


def _fresh_login(token):
    since = timezone.now() - datetime.timedelta(seconds=BROWSER_LOGIN_MAX_AGE)
    return BrowserLogin.objects.filter(token=token, used=False, created_at__gte=since).first()


def approve_browser_login(token, user):
    """O'qituvchi botidagi tasdiq. Token eskirgan yoki ishlatilgan bo'lsa False."""
    login = _fresh_login(token)
    if not login or login.approved_by_id:
        return False
    login.approved_by = user
    login.save(update_fields=['approved_by'])
    return True


def claim_browser_login(token):
    """Brauzer so'raydi: tasdiqlangan bo'lsa foydalanuvchi (bir marta), aks holda None."""
    login = _fresh_login(token)
    if not login or not login.approved_by_id:
        return None
    login.used = True
    login.save(update_fields=['used'])
    user = login.approved_by
    return user if user.is_active else None
