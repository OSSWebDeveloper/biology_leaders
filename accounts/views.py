import json
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseNotFound, JsonResponse
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import User
from .services import check_login_token, get_or_create_tg_user, verify_init_data


def not_found(request, exception=None):
    """Kirmagan odamga 404 bo'sh javob (sayt nimaligi bilinmasin); kirganlarga odatdagi sahifa."""
    if not request.user.is_authenticated:
        return HttpResponseNotFound()
    return render(request, '404.html', status=404)


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
        raise Http404  # begona odamga hech narsa aytilmaydi: bo'sh sahifa
    _login_browser(request, user)
    messages.success(request, f'Xush kelibsiz, {user.display_name}!')
    return redirect('entry_teacher')  # bosh manzil brauzerda faqat «Telegram orqali kiring» ni ko'rsatadi


BROWSER_SIGNUPS_PER_HOUR = 200  # bitta IP dan (kompyuter sinfi bitta IP orqali chiqishi mumkin)


@require_POST
def browser_enter(request):
    """Sinov rejimi: oddiy brauzerda ism-familiya yozib o'quvchi sifatida kirish (Telegram'siz).

    Har kirishda yangi o'quvchi yoziladi; shaxs va kanal obunasi tekshirilmaydi.
    """
    if not settings.BROWSER_STUDENTS:
        raise Http404
    name = ' '.join(request.POST.get('full_name', '').split())[:150]
    if len(name) < 5 or ' ' not in name:
        messages.error(request, "Ism va familiyangizni to'liq yozing.")
        return redirect('home')
    key = f'br-new:{_client_ip(request)}'
    count = cache.get(key, 0)
    if count >= BROWSER_SIGNUPS_PER_HOUR:
        messages.error(request, "Juda ko'p kirish bo'ldi. Birozdan keyin urinib ko'ring.")
        return redirect('home')
    cache.set(key, count + 1, 60 * 60)
    user = User(username=f'br{secrets.token_hex(8)}', full_name=name)
    user.set_unusable_password()
    user.save()
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return redirect('exam_list')


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
    if request.method == 'POST':
        error = _password_login(request)
        if error is None:
            return redirect(request.path)
    else:
        error = None
    return render(request, 'accounts/browser_login.html', {
        'browser_only': browser_only, 'hide_nav': True, 'error': error})


MAX_TRIES = 5
LOCK_SECONDS = 15 * 60


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return forwarded.split(',')[0].strip() or request.META.get('REMOTE_ADDR', '')


def _password_login(request):
    """Parol bilan kirish (kompyuter brauzeri). Xato bo'lsa xabar, kirsa None qaytaradi."""
    key = f'pwd-tries:{_client_ip(request)}'
    tries = cache.get(key, 0)
    if tries >= MAX_TRIES:
        return "Ko'p marta xato kiritildi. 15 daqiqadan keyin urinib ko'ring."
    password = request.POST.get('password', '')
    admins = User.objects.filter(role=User.Role.ADMIN, is_active=True)
    user = next((u for u in admins if password and u.check_password(password)), None)
    if user is None:
        cache.set(key, tries + 1, LOCK_SECONDS)
        return "Parol noto'g'ri."
    cache.delete(key)
    _login_browser(request, user)
    return None
