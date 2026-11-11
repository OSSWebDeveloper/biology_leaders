"""Loyiha sozlamalari. Maxfiy qiymatlar .env faylidan olinadi (.env.example ga qarang)."""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


def _list(name):
    return [x.strip() for x in os.environ.get(name, '').split(',') if x.strip()]


SECRET_KEY = os.environ['SECRET_KEY']
DEBUG = os.environ.get('DEBUG', '0') == '1'

BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
BOT_USERNAME = os.environ.get('BOT_USERNAME', '')
TEACHER_BOT_TOKEN = os.environ.get('TEACHER_BOT_TOKEN', '')
WEBAPP_URL = os.environ.get('WEBAPP_URL', '').rstrip('/')
ADMIN_TELEGRAM_IDS = {int(x) for x in _list('ADMIN_TELEGRAM_IDS')}
WEBAPP_IS_HTTPS = WEBAPP_URL.startswith('https://')
# Majburiy obuna: o'quvchi shu kanalga a'zo bo'lmasa bot va testlar ochilmaydi (bo'sh bo'lsa tekshirilmaydi)
REQUIRED_CHANNEL_ID = os.environ.get('REQUIRED_CHANNEL_ID', '').strip()
REQUIRED_CHANNEL_URL = os.environ.get('REQUIRED_CHANNEL_URL', '').strip()
# Test boshlanganda e'lon shu kanalga ketadi (bo'sh bo'lsa majburiy obuna kanali)
ANNOUNCE_CHANNEL_ID = os.environ.get('ANNOUNCE_CHANNEL_ID', '').strip() or REQUIRED_CHANNEL_ID
# SINOV REJIMI: 1 bo'lsa oddiy brauzerda (Telegram'siz) ism-familiya yozib test ishlash mumkin.
# Bunda shaxs ham, kanal obunasi ham tekshirilmaydi: haqiqiy ishga tushirishda yoqilmaydi.
BROWSER_STUDENTS = os.environ.get('BROWSER_STUDENTS', '0') == '1'
if sys.argv[1:2] == ['test']:  # testlar Telegram'ga so'rov yubormasin
    REQUIRED_CHANNEL_ID = ''
    BROWSER_STUDENTS = False  # testlar .env ga bog'liq bo'lmasin; kerakli testlar o'zi yoqadi

ALLOWED_HOSTS = ['localhost', '127.0.0.1', *_list('ALLOWED_HOSTS')]
CSRF_TRUSTED_ORIGINS = _list('CSRF_TRUSTED_ORIGINS')
if WEBAPP_URL:
    ALLOWED_HOSTS.append(urlparse(WEBAPP_URL).hostname)
    CSRF_TRUSTED_ORIGINS.append(WEBAPP_URL)

# Telegram Web (brauzer) Web App'ni iframe ichida ochadi, shuning uchun https da
# cookie SameSite=None bo'lishi kerak. X-Frame-Options o'rniga frame-ancestors ishlatiladi.
if WEBAPP_IS_HTTPS:
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = CSRF_COOKIE_SAMESITE = 'None'
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'exams',
    'tgbot',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    # CommonMiddleware dan oldin: aks holda /django-admin 301 qaytarib, manzil borligini bildirib qo'yadi
    'config.middleware.HiddenAdminMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'config.middleware.TelegramFrameMiddleware',
    'config.middleware.LastSeenMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
        'config.context.app_info',
    ]},
}]

DATABASES = {'default': {
    'ENGINE': 'django.db.backends.sqlite3',
    'NAME': BASE_DIR / 'db.sqlite3',
    # Bosim sinovi (2026-11-11): 50 o'quvchida javoblarning yarmi «database is locked» bilan yo'qolardi.
    # IMMEDIATE: yozuvchi so'rov darhol xato olmay navbat kutadi; WAL: o'qish yozishni to'smaydi.
    'OPTIONS': {
        'timeout': 20,
        'transaction_mode': 'IMMEDIATE',
        'init_command': 'PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;',
    },
}}

AUTH_USER_MODEL = 'accounts.User'
LOGIN_URL = 'home'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LANGUAGE_CODE = 'uz'
TIME_ZONE = 'Asia/Tashkent'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DATA_UPLOAD_MAX_MEMORY_SIZE = 40 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30
