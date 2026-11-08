"""O'quvchi sahifalari."""
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .models import Attempt, Exam, Question
from .services import can_start, exam_by_code, finalize, save_answer, start_attempt


@ensure_csrf_cookie  # landing dagi JS tg_auth ga token yuboradi, sahifada forma yo'q
def home(request):
    if not request.user.is_authenticated:
        return render(request, 'landing.html')
    return redirect('exam_list')


def _exam_for_code(code):
    exam = exam_by_code(code)
    if exam is None:
        raise Http404
    return exam


def _own_attempt(request, pk):
    attempt = get_object_or_404(Attempt.objects.select_related('exam', 'student'), pk=pk)
    if attempt.student_id != request.user.pk:
        raise PermissionDenied
    if not attempt.is_finished and attempt.seconds_left() <= 0:
        finalize(attempt)
    return attempt


@login_required
def exam_list(request):
    """O'quvchi bosh sahifasi: testlar ro'yxati yo'q, kirish faqat guruhdagi kod bilan."""
    if request.method == 'POST':
        exam = exam_by_code(request.POST.get('code'))
        if exam:
            return redirect('exam_detail', code=exam.access_code)
        messages.error(request, "Bunday kod topilmadi. Guruhdagi xabarni tekshiring.")
        return redirect('exam_list')
    active = [a for a in Attempt.objects.filter(student=request.user, finished_at__isnull=True).select_related('exam')
              if a.seconds_left() > 0]
    return render(request, 'student/exam_list.html', {'active': active, 'tab': 'tests'})


@login_required
def exam_detail(request, code):
    exam = _exam_for_code(code)
    attempts = exam.attempts.filter(student=request.user, finished_at__isnull=False).order_by('-finished_at')
    active = exam.attempts.filter(student=request.user, finished_at__isnull=True).first()
    if active and active.seconds_left() <= 0:
        finalize(active)
        active = None
    allowed, reason = can_start(exam, request.user)
    counts = {k: exam.questions.filter(kind=k).count() for k in Question.Kind.values}
    return render(request, 'student/exam_detail.html', {
        'exam': exam, 'attempts': attempts, 'active': active, 'allowed': allowed, 'reason': reason,
        'counts': counts, 'tab': 'tests',
    })


@login_required
@require_POST
def attempt_start(request, code):
    exam = _exam_for_code(code)
    active = exam.attempts.filter(student=request.user, finished_at__isnull=True).first()
    if not active or active.seconds_left() <= 0:
        allowed, reason = can_start(exam, request.user)
        if not allowed:
            messages.error(request, reason)
            return redirect('exam_detail', code=exam.access_code)
    return redirect('attempt', pk=start_attempt(exam, request.user).pk)


@login_required
def attempt_view(request, pk):
    attempt = _own_attempt(request, pk)
    if attempt.is_finished:
        return redirect('attempt_result', pk=attempt.pk)
    saved = {a.question_id: a for a in attempt.answers.all()}
    questions = []
    for q in attempt.exam.questions.all():
        answer = saved.get(q.pk)
        questions.append({
            'id': q.pk, 'number': q.number, 'kind': q.kind, 'text': q.text,
            'image': q.image.url if q.image else '', 'options': q.options, 'letters': q.letters,
            'part_a': q.part_a, 'part_b': q.part_b, 'two_parts': q.two_parts,
            'choice': answer.choice if answer else '',
            'value_a': answer.value_a if answer else '', 'value_b': answer.value_b if answer else '',
        })
    return render(request, 'student/attempt.html', {
        'attempt': attempt, 'hide_nav': True,
        'payload': {'questions': questions, 'seconds_left': attempt.seconds_left()},
    })


@login_required
@require_POST
def attempt_answer(request, pk):
    attempt = _own_attempt(request, pk)
    if attempt.is_finished:
        return JsonResponse({'ok': False, 'finished': True}, status=409)
    try:
        data = json.loads(request.body or b'{}')
        question = attempt.exam.questions.get(pk=int(data.get('question')))
    except (ValueError, TypeError, Question.DoesNotExist):
        return JsonResponse({'ok': False}, status=400)
    save_answer(attempt, question, data.get('choice'), data.get('value_a'), data.get('value_b'))
    return JsonResponse({'ok': True, 'seconds_left': attempt.seconds_left()})


@login_required
@require_POST
def attempt_finish(request, pk):
    attempt = _own_attempt(request, pk)
    if not attempt.is_finished:
        finalize(attempt)
    return redirect('attempt_result', pk=attempt.pk)


@login_required
def attempt_result(request, pk):
    attempt = _own_attempt(request, pk)
    if not attempt.is_finished:
        return redirect('attempt', pk=attempt.pk)
    # Ball va tahlil o'quvchiga ko'rsatilmaydi: natijalarni o'qituvchi guruhga tashlaydi
    return render(request, 'student/result.html', {'attempt': attempt, 'exam': attempt.exam, 'tab': 'results'})


@login_required
def my_results(request):
    attempts = (Attempt.objects.filter(student=request.user, finished_at__isnull=False)
                .select_related('exam').order_by('-finished_at'))
    return render(request, 'student/my_results.html', {'attempts': attempts, 'tab': 'results'})


@login_required
def leaderboard(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    is_owner = request.user.is_admin_role or (request.user.is_teacher and exam.created_by_id == request.user.pk)
    if not is_owner:  # o'quvchilar natijani guruhdan biladi
        raise Http404
    best = {}
    for attempt in (exam.attempts.filter(finished_at__isnull=False).select_related('student')
                    .order_by('-score', 'finished_at')):
        best.setdefault(attempt.student_id, attempt)
    rows = list(best.values())[:100]
    return render(request, 'student/leaderboard.html', {'exam': exam, 'rows': rows, 'tab': 'tests'})
