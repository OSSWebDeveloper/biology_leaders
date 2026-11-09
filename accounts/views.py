import json

from django.contrib import messages
from django.contrib.auth import login, logout
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .services import (
    check_login_token, claim_browser_login, create_browser_login, get_or_create_tg_user, verify_init_data,
)


@require_POST
def tg_auth(request):
    """Web App ochilganda JS initData ni yuboradi; imzo to'g'ri bo'lsa sessiya ochiladi."""
    try:
        init_data = json.loads(request.body or b'{}').get('init_data', '')
    except ValueError:
        init_data = ''
    tg = verify_init_data(init_data)
    if not tg:
        return JsonResponse({'ok': False, 'error': "Telegram ma'lumoti tasdiqlanmadi"}, status=403)
    user = get_or_create_tg_user(tg['id'], tg.get('first_name', ''), tg.get('last_name', ''))
    if not user.is_active:
        return JsonResponse({'ok': False, 'error': 'Hisobingiz bloklangan'}, status=403)
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return JsonResponse({'ok': True})


def login_link(request, token):
    """Bot /panel buyrug'i bergan bir martalik havola (kompyuter brauzeri uchun)."""
    user = check_login_token(token)
    if not user:
        return render(request, 'landing.html', {'link_error': True}, status=403)
    _login_browser(request, user)
    messages.success(request, f'Xush kelibsiz, {user.display_name}!')
    return redirect('home')


@require_POST
def logout_view(request):
    logout(request)
    return redirect('home')


# Yashirin kirish manzillari: /mrclayd/ — texnik qism (faqat admin, faqat kompyuter brauzeri),
# /ustoz/ — o'qituvchi bo'limi (brauzer yoki Telegram Web App).
BROWSER_SESSION_KEY = 'browser_login'
ENTRY_TARGETS = {
    'admin': ('a_dashboard', lambda u: u.is_admin_role, True),
    'teacher': ('t_exams', lambda u: u.is_teacher, False),
}


def _login_browser(request, user):
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    request.session[BROWSER_SESSION_KEY] = True


def entry(request, target):
    url_name, allowed, browser_only = ENTRY_TARGETS[target]
    user = request.user
    signed_in = user.is_authenticated and (not browser_only or request.session.get(BROWSER_SESSION_KEY))
    if signed_in:
        if user.telegram_id:  # ADMIN_TELEGRAM_IDS ga keyin qo'shilgan bo'lsa, rol shu yerda yangilanadi
            user = get_or_create_tg_user(user.telegram_id)
        if allowed(user):
            return redirect(url_name)
        if browser_only:
            raise Http404
        raise PermissionDenied
    token = create_browser_login()
    request.session['browser_login_token'] = token
    bot = settings.TEACHER_BOT_USERNAME
    return render(request, 'accounts/browser_login.html', {
        'target': target, 'browser_only': browser_only, 'hide_nav': True,
        'bot_username': bot, 'bot_link': f'https://t.me/{bot}?start=login_{token}' if bot else '',
        'status_url': reverse('browser_login_status'),
    })


def browser_login_status(request):
    """Kirish sahifasi shu yerni so'rab turadi; o'qituvchi botida tasdiqlansa sessiya ochiladi."""
    token = request.session.get('browser_login_token')
    user = claim_browser_login(token) if token else None
    if user is None:
        return JsonResponse({'ok': False})
    request.session.pop('browser_login_token', None)
    _login_browser(request, user)
    return JsonResponse({'ok': True})
