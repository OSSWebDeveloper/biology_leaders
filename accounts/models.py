import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = 'student', "O'quvchi"
        TEACHER = 'teacher', "O'qituvchi"
        ADMIN = 'admin', 'Admin'

    role = models.CharField("Rol", max_length=10, choices=Role.choices, default=Role.STUDENT)
    telegram_id = models.BigIntegerField("Telegram ID", unique=True, null=True, blank=True)
    full_name = models.CharField("F.I.Sh.", max_length=150, blank=True)
    phone = models.CharField("Telefon", max_length=20, blank=True)

    @property
    def is_teacher(self):
        return self.role in (self.Role.TEACHER, self.Role.ADMIN)

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    @property
    def display_name(self):
        return self.full_name or self.get_full_name() or self.username

    @property
    def is_registered(self):
        """Botda ism va telefonni to'ldirganmi."""
        return bool(self.full_name and self.phone)

    def __str__(self):
        return self.display_name


def _new_code():
    return secrets.token_hex(3).upper()


class StudyGroup(models.Model):
    name = models.CharField("Guruh nomi", max_length=120)
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='owned_groups', verbose_name="O'qituvchi")
    code = models.CharField("Taklif kodi", max_length=12, unique=True, default=_new_code)
    students = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True,
                                      related_name='study_groups', verbose_name="O'quvchilar")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Guruh'
        verbose_name_plural = 'Guruhlar'

    @property
    def invite_link(self):
        if settings.BOT_USERNAME:
            return f'https://t.me/{settings.BOT_USERNAME}?start=g_{self.code}'
        return ''

    def __str__(self):
        return self.name
