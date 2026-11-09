import json

from django.contrib import messages
from django.contrib.auth import login, logout
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .services import check_login_token, get_or_create_tg_user, verify_init_data


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
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    messages.success(request, f'Xush kelibsiz, {user.display_name}!')
    return redirect('home')


@require_POST
def logout_view(request):
    logout(request)
    return redirect('home')


# Yashirin kirish manzillari: /mrclayd/ — admin (texnik qism), /ustoz/ — o'qituvchi bo'limi.
# Telegram ichida ochilsa initData bilan kiradi, so'ng rolga qarab yo'naltiriladi.
ENTRY_TARGETS = {
    'admin': ('a_dashboard', lambda u: u.is_admin_role, True),
    'teacher': ('t_exams', lambda u: u.is_teacher, False),
}


def entry(request, target):
    url_name, allowed, hidden = ENTRY_TARGETS[target]
    if not request.user.is_authenticated:
        return render(request, 'landing.html', {'after_login': request.path})
    user = request.user
    if user.telegram_id:  # ADMIN_TELEGRAM_IDS ga keyin qo'shilgan bo'lsa, rol shu yerda yangilanadi
        user = get_or_create_tg_user(user.telegram_id)
    if allowed(user):
        return redirect(url_name)
    if hidden:
        raise Http404
    raise PermissionDenied
