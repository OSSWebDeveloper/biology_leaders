from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404


def _role_required(check):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            if not check(request.user):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


teacher_required = _role_required(lambda u: u.is_teacher)
admin_required = _role_required(lambda u: u.is_admin_role)


def admin_browser_required(view):
    """Texnik qism: faqat admin va faqat kompyuter brauzeridagi sessiya (Telegram Web App emas)."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_admin_role
                and request.session.get('browser_login')):
            raise Http404
        return view(request, *args, **kwargs)
    return wrapped
