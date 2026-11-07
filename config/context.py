from pathlib import Path

from django.conf import settings


def _version():
    try:
        return (Path(settings.BASE_DIR) / 'versiya.txt').read_text(encoding='utf-8-sig').strip()
    except OSError:
        return ''


VERSION = _version()


def app_info(request):
    return {'APP_VERSION': VERSION, 'BOT_USERNAME': settings.BOT_USERNAME}
