"""Texnik qism (/mrclayd) uchun statistika."""
import datetime
import platform
import sys
from pathlib import Path

import django
from django.conf import settings
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from accounts.models import User
from tgbot import subscription

from .models import Attempt, Exam

ONLINE_MINUTES = 5
CHART_DAYS = 14
GRADES = ('A+', 'A', 'B+', 'B', 'C+', 'C')


def _dir_size(path):
    path = Path(path)
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob('*') if f.is_file())


def _mb(size):
    return round(size / 1024 / 1024, 1)


def _daily(queryset, field, since):
    rows = (queryset.filter(**{f'{field}__gte': since}).annotate(day=TruncDate(field))
            .values('day').annotate(n=Count('pk')))
    return {row['day']: row['n'] for row in rows}


def collect():
    now = timezone.now()
    today = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    online_since = now - datetime.timedelta(minutes=ONLINE_MINUTES)
    users = User.objects.all()

    seen_any = Q(last_seen__gte=online_since) | Q(last_bot_seen__gte=online_since)
    online = list(users.filter(seen_any).order_by('-last_seen'))
    for user in online:
        user.on_site = bool(user.last_seen and user.last_seen >= online_since)
        user.on_bot = bool(user.last_bot_seen and user.last_bot_seen >= online_since)
        user.seen = max(t for t in (user.last_seen, user.last_bot_seen) if t)
        user.just_now = (now - user.seen).total_seconds() < 60
    online.sort(key=lambda u: u.seen, reverse=True)

    def active_since(moment):
        return users.filter(Q(last_seen__gte=moment) | Q(last_bot_seen__gte=moment)).count()

    roles = dict(users.values_list('role').annotate(n=Count('pk')))
    finished = Attempt.objects.filter(finished_at__isnull=False)
    in_progress = (Attempt.objects.filter(finished_at__isnull=True, deadline__gt=now)
                   .select_related('student', 'exam').order_by('deadline'))

    start_day = (today - datetime.timedelta(days=CHART_DAYS - 1))
    joined = _daily(users, 'date_joined', start_day)
    solved = _daily(finished, 'finished_at', start_day)
    days = []
    for i in range(CHART_DAYS):
        day = (start_day + datetime.timedelta(days=i)).date()
        days.append({'day': day, 'joined': joined.get(day, 0), 'solved': solved.get(day, 0)})
    peak = max([1] + [d['joined'] for d in days] + [d['solved'] for d in days])
    for d in days:
        d['joined_pct'] = round(d['joined'] * 100 / peak)
        d['solved_pct'] = round(d['solved'] * 100 / peak)

    grade_counts = dict(finished.values_list('grade').annotate(n=Count('pk')))
    graded_total = sum(grade_counts.values()) or 1
    grades = [{'grade': g, 'n': grade_counts.get(g, 0), 'pct': round(grade_counts.get(g, 0) * 100 / graded_total)}
              for g in GRADES]
    other_grades = sum(n for g, n in grade_counts.items() if g not in GRADES)
    grades.append({'grade': '—', 'n': other_grades, 'pct': round(other_grades * 100 / graded_total)})

    exams = (Exam.objects.select_related('created_by')
             .annotate(done=Count('attempts', filter=Q(attempts__finished_at__isnull=False)),
                       active=Count('attempts', filter=Q(attempts__finished_at__isnull=True,
                                                         attempts__deadline__gt=now)),
                       avg=Avg('attempts__score', filter=Q(attempts__finished_at__isnull=False)))
             .order_by('-created_at')[:30])
    published = Exam.objects.filter(status=Exam.Status.PUBLISHED)
    open_now = published.filter(Q(opens_at__isnull=True) | Q(opens_at__lte=now),
                                Q(closes_at__isnull=True) | Q(closes_at__gt=now)).count()

    db_path = Path(settings.DATABASES['default']['NAME'])
    return {
        'now': now, 'online_minutes': ONLINE_MINUTES,
        'online': online,
        'online_site': sum(u.on_site for u in online), 'online_bot': sum(u.on_bot for u in online),
        'active_today': active_since(today),
        'active_week': active_since(now - datetime.timedelta(days=7)),
        'active_month': active_since(now - datetime.timedelta(days=30)),
        'total_users': users.count(),
        'students': roles.get(User.Role.STUDENT, 0), 'teachers': roles.get(User.Role.TEACHER, 0),
        'admins': roles.get(User.Role.ADMIN, 0),
        'registered': users.exclude(full_name='').exclude(phone='').count(),
        'blocked': users.filter(is_active=False).count(),
        'new_today': users.filter(date_joined__gte=today).count(),
        'new_week': users.filter(date_joined__gte=now - datetime.timedelta(days=7)).count(),
        'in_progress': in_progress,
        'exams_total': Exam.objects.count(), 'published': published.count(), 'open_now': open_now,
        'solved_total': finished.count(), 'solved_today': finished.filter(finished_at__gte=today).count(),
        'average': finished.aggregate(a=Avg('score'))['a'],
        'days': days, 'grades': grades, 'exams': exams,
        'recent': finished.select_related('student', 'exam').order_by('-finished_at')[:10],
        'tech': {
            'version': _version(), 'python': sys.version.split()[0], 'django': django.get_version(),
            'os': f'{platform.system()} {platform.release()}',
            'db_mb': _mb(db_path.stat().st_size) if db_path.exists() else 0,
            'media_mb': _mb(_dir_size(settings.MEDIA_ROOT)),
            'webapp_url': settings.WEBAPP_URL, 'debug': settings.DEBUG,
            'channel': subscription.channel_health(),
        },
    }


def _version():
    from config.context import VERSION
    return VERSION
