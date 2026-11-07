from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from accounts.models import User
from accounts.services import make_login_token


class Command(BaseCommand):
    help = "Brauzer uchun bir martalik kirish havolasini chiqaradi (10 daqiqa amal qiladi)."

    def add_arguments(self, parser):
        parser.add_argument('telegram_id', type=int)
        parser.add_argument('--asos', default='', help='Sayt manzili, masalan http://127.0.0.1:8000')

    def handle(self, telegram_id, asos, **opts):
        try:
            user = User.objects.get(telegram_id=telegram_id)
        except User.DoesNotExist as exc:
            raise CommandError('Bunday foydalanuvchi yo\'q') from exc
        base = (asos or settings.WEBAPP_URL or 'http://127.0.0.1:8000').rstrip('/')
        self.stdout.write(base + reverse('login_link', args=[make_login_token(user)]))
