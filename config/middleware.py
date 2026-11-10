from django.contrib.auth import get_user
from django.http import HttpResponseNotFound

from accounts.services import touch_seen


class TelegramFrameMiddleware:
    """Sahifani faqat Telegram Web iframe ichida ochishga ruxsat beradi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['Content-Security-Policy'] = (
            "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org"
        )
        return response


class HiddenAdminMiddleware:
    """/django-admin/ faqat texnik qismga (/mrclayd/) parol bilan kirgan adminga ko'rinadi; qolganlarga bo'sh 404."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == '/django-admin' or request.path.startswith('/django-admin/'):
            user = get_user(request)  # AuthenticationMiddleware hali ishlamagan: sessiyadan o'zimiz olamiz
            allowed = user.is_authenticated and user.is_admin_role and request.session.get('browser_login')
            if not allowed:
                return HttpResponseNotFound()
        return self.get_response(request)


class LastSeenMiddleware:
    """Saytdagi faollik: statistikada «hozir onlayn» shu orqali hisoblanadi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            touch_seen(user)
        return self.get_response(request)
