from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from accounts.services import get_or_create_tg_user


class Command(BaseCommand):
    help = "Telegram ID bo'yicha rol beradi: python manage.py rol 123456789 admin"

    def add_arguments(self, parser):
        parser.add_argument('telegram_id', type=int)
        parser.add_argument('rol', choices=[r.value for r in User.Role])

    def handle(self, telegram_id, rol, **opts):
        if telegram_id <= 0:
            raise CommandError("Telegram ID musbat son bo'lishi kerak")
        user = get_or_create_tg_user(telegram_id)
        user.role = rol
        user.save(update_fields=['role'])
        self.stdout.write(self.style.SUCCESS(f'{telegram_id}: rol = {rol}'))
