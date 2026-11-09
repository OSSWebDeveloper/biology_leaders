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




class LastSeenMiddleware:
    """Saytdagi faollik: statistikada «hozir onlayn» shu orqali hisoblanadi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            touch_seen(user)
        return self.get_response(request)
