import json

from django.contrib import messages
from django.contrib.auth import login, logout
from django.http import JsonResponse
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
