from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import StudyGroup, User


@admin.register(User)
class AppUserAdmin(UserAdmin):
    list_display = ('username', 'full_name', 'telegram_id', 'phone', 'role', 'is_active')
    list_filter = ('role', 'is_active')
    search_fields = ('username', 'full_name', 'phone', 'telegram_id')
    fieldsets = UserAdmin.fieldsets + (('Telegram', {'fields': ('role', 'telegram_id', 'full_name', 'phone')}),)


@admin.register(StudyGroup)
class StudyGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'teacher', 'code')
    filter_horizontal = ('students',)
