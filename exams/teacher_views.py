"""O'qituvchi va admin sahifalari."""
from io import BytesIO

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from openpyxl import Workbook

from accounts.decorators import admin_browser_required, teacher_required
from accounts.models import StudyGroup, User
from tgbot import notify

from . import stats
from .forms import ExamForm, PdfImportForm, QuestionForm
from .models import Answer, Attempt, Exam, Question
from .pdf_import import PdfImportError
from .services import attach_test_file, create_answer_sheet, discard_exam, regrade_exam, set_question_counts


def _exam_or_403(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    if not request.user.is_admin_role and exam.created_by_id != request.user.pk:
        raise PermissionDenied
    return exam


def _group_or_403(request, pk):
    group = get_object_or_404(StudyGroup, pk=pk)
    if not request.user.is_admin_role and group.teacher_id != request.user.pk:
        raise PermissionDenied
    return group


def _save_test_file(request, exam, form):
    """Formadagi test fayli: savollar soni formada berilgan, shuning uchun fayl faqat saqlanadi."""
    upload = form.cleaned_data.get('test_file')
    if upload:
        try:
            messages.success(request, attach_test_file(exam, upload))
        except PdfImportError as exc:
            messages.error(request, str(exc))


# ---------- Testlar ----------

@teacher_required
def t_exams(request):
    exams = Exam.objects.all() if request.user.is_admin_role else Exam.objects.filter(created_by=request.user)
    exams = exams.annotate(
        q_count=Count('questions', distinct=True),
        done_count=Count('attempts', filter=Q(attempts__finished_at__isnull=False), distinct=True),
    ).select_related('created_by')
    return render(request, 'teacher/exams.html', {'exams': exams, 'tab': 'teacher'})


@teacher_required
def t_exam_new(request):
    form = ExamForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        exam = form.save(commit=False)
        exam.created_by = request.user
        exam.save()
        create_answer_sheet(exam, form.counts)
        _save_test_file(request, exam, form)
        return redirect('t_exam', pk=exam.pk)
    return render(request, 'teacher/form.html', {'form': form, 'title': 'Yangi test', 'tab': 'teacher',
                                                 'back': 't_exams'})


@teacher_required
def t_exam_edit(request, pk):
    exam = _exam_or_403(request, pk)
    form = ExamForm(request.POST or None, request.FILES or None, instance=exam)
    if request.method == 'POST' and form.is_valid():
        form.save()
        set_question_counts(exam, form.counts)
        _save_test_file(request, exam, form)
        messages.success(request, 'Saqlandi')
        return redirect('t_exam', pk=pk)
    return render(request, 'teacher/form.html', {'form': form, 'title': 'Test sozlamalari', 'exam': exam, 'tab': 'teacher'})


@teacher_required
def t_exam(request, pk):
    """Savollar ro'yxati va javoblar kaliti bitta sahifada."""
    exam = _exam_or_403(request, pk)
    questions = list(exam.questions.all())
    if request.method == 'POST':
        changed = []
        for q in questions:
            if q.kind == Question.Kind.OPEN:
                q.answer_a = request.POST.get(f'a_{q.pk}', q.answer_a).strip()
                q.answer_b = request.POST.get(f'b_{q.pk}', q.answer_b).strip()
            else:
                value = request.POST.get(f'c_{q.pk}', q.correct)
                q.correct = value if value in q.letters else ''
            changed.append(q)
        Question.objects.bulk_update(changed, ['answer_a', 'answer_b', 'correct'])
        regrade_exam(exam)
        messages.success(request, 'Javoblar kaliti saqlandi')
        return redirect('t_exam', pk=pk)
    return render(request, 'teacher/exam.html', {
        'exam': exam, 'questions': questions, 'tab': 'teacher', 'now': timezone.now(),
        'attempt_count': exam.attempts.count(),
    })


@teacher_required
def t_pdf(request, pk):
    exam = _exam_or_403(request, pk)
    form = PdfImportForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        replace = form.cleaned_data['replace']
        if replace and exam.attempts.exists():
            messages.error(request, "Testni yechganlar bor: savollarni almashtirib bo'lmaydi")
            return redirect('t_exam', pk=pk)
        try:
            note = attach_test_file(exam, form.cleaned_data['pdf'], replace=replace)
        except PdfImportError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, note)
            return redirect('t_exam', pk=pk)
    return render(request, 'teacher/pdf.html', {'form': form, 'exam': exam, 'tab': 'teacher'})


@teacher_required
def t_question(request, pk, qid=None):
    exam = _exam_or_403(request, pk)
    question = get_object_or_404(Question, pk=qid, exam=exam) if qid else None
    if question is None:
        next_number = (exam.questions.order_by('-number').values_list('number', flat=True).first() or 0) + 1
        question = Question(exam=exam, number=next_number)
    form = QuestionForm(request.POST or None, request.FILES or None, instance=question)
    if request.method == 'POST' and form.is_valid():
        form.save()
        regrade_exam(exam)
        messages.success(request, f'{question.number}-savol saqlandi')
        return redirect('t_exam', pk=pk)
    return render(request, 'teacher/question.html', {'form': form, 'exam': exam, 'question': question, 'tab': 'teacher'})


@teacher_required
@require_POST
def t_question_delete(request, pk, qid):
    exam = _exam_or_403(request, pk)
    question = get_object_or_404(Question, pk=qid, exam=exam)
    if question.answers.exists():
        messages.error(request, "Bu savolga javob berilgan: o'chirib bo'lmaydi")
    else:
        question.image.delete(save=False)
        question.delete()
        messages.success(request, "Savol o'chirildi")
    return redirect('t_exam', pk=pk)


@teacher_required
@require_POST
def t_publish(request, pk):
    exam = _exam_or_403(request, pk)
    if exam.is_published:
        exam.status = Exam.Status.DRAFT
        exam.save(update_fields=['status'])
        messages.success(request, "Test e'londan olindi")
        return redirect('t_exam', pk=pk)
    missing = exam.missing_keys()
    if not exam.questions.exists():
        messages.error(request, "Testda savol yo'q")
    elif missing:
        messages.error(request, "Kalit to'ldirilmagan savollar: " + ', '.join(map(str, missing)))
    elif not exam.opens_at or not exam.closes_at:
        messages.error(request, "Avval sozlamalarda boshlanish va tugash vaqtini kiriting")
    else:
        exam.status = Exam.Status.PUBLISHED
        exam.save(update_fields=['status'])
        messages.success(request, "Test e'lon qilindi. Endi xabarni botga yuborib, guruhga uzating.")
    return redirect('t_exam', pk=pk)


@teacher_required
@require_POST
def t_send(request, pk):
    """Fayl, kod va vaqtlardan iborat tayyor xabar o'qituvchiga keladi, u guruhga uzatadi."""
    exam = _exam_or_403(request, pk)
    if not exam.is_published:
        messages.error(request, "Avval testni e'lon qiling")
    elif not exam.attachment:
        messages.error(request, 'Avval test faylini (PDF yoki Word) yuklang')
    elif not exam.opens_at or not exam.closes_at:
        messages.error(request, 'Avval boshlanish va tugash vaqtini kiriting')
    elif not request.user.telegram_id:
        messages.error(request, "Hisobingiz Telegram bilan bog'lanmagan")
    elif notify.exam_announcement(exam, request.user.telegram_id):
        messages.success(request, 'Xabar botga yuborildi. Uni guruhga uzating.')
    else:
        messages.error(request, "Xabar yuborilmadi. Botga /start bosganingizni va internetni tekshiring.")
    return redirect('t_exam', pk=pk)


@teacher_required
@require_POST
def t_exam_delete(request, pk):
    exam = _exam_or_403(request, pk)
    if exam.attempts.exists():
        messages.error(request, "Testni yechganlar bor: o'chirib bo'lmaydi. E'londan olishingiz mumkin.")
        return redirect('t_exam', pk=pk)
    discard_exam(exam)
    messages.success(request, "Test o'chirildi")
    return redirect('t_exams')


def _results_data(exam):
    attempts = list(exam.attempts.filter(finished_at__isnull=False).select_related('student').order_by('-score'))
    stats = []
    total = len(attempts)
    per_question = {}
    for answer in Answer.objects.filter(attempt__exam=exam, attempt__finished_at__isnull=False):
        row = per_question.setdefault(answer.question_id, [0, 0])
        row[0] += int(answer.correct_a)
        row[1] += int(answer.correct_b)
    for q in exam.questions.all():
        hits = sum(per_question.get(q.pk, [0, 0]))
        possible = total * q.max_items
        pct = round(100 * hits / possible) if possible else 0
        stats.append({'q': q, 'pct': pct, 'level': 'low' if pct < 35 else 'mid' if pct < 70 else 'high'})
    return attempts, stats


@teacher_required
def t_results(request, pk):
    exam = _exam_or_403(request, pk)
    attempts, stats = _results_data(exam)
    average = exam.attempts.filter(finished_at__isnull=False).aggregate(a=Avg('score'))['a']
    return render(request, 'teacher/results.html', {
        'exam': exam, 'attempts': attempts, 'stats': stats, 'average': average,
        'in_progress': exam.attempts.filter(finished_at__isnull=True, deadline__gt=timezone.now()).count(),
        'tab': 'teacher',
    })


def _safe_cell(value):
    """Excel formula sifatida bajarilmasligi uchun (ism '=' bilan boshlanishi mumkin)."""
    text = str(value)
    return "'" + text if text[:1] in ('=', '+', '-', '@') else value


@teacher_required
def t_results_xlsx(request, pk):
    exam = _exam_or_403(request, pk)
    attempts, _ = _results_data(exam)
    book = Workbook()
    sheet = book.active
    sheet.title = 'Natijalar'
    sheet.append(['#', 'F.I.Sh.', 'Telefon', "To'g'ri", 'Jami', 'Foiz', 'Ball (75)', 'Daraja', 'Tugatgan vaqti'])
    for index, a in enumerate(attempts, 1):
        sheet.append([index, _safe_cell(a.student.display_name), _safe_cell(a.student.phone), a.correct_items,
                      a.total_items, a.percent, a.score, a.grade or '—',
                      timezone.localtime(a.finished_at).strftime('%d.%m.%Y %H:%M')])
    for column, width in zip('ABCDEFGHI', (5, 32, 16, 8, 8, 8, 10, 8, 18)):
        sheet.column_dimensions[column].width = width
    buf = BytesIO()
    book.save(buf)
    response = HttpResponse(buf.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="natijalar_{exam.pk}.xlsx"'
    return response


@teacher_required
def t_attempt(request, attempt_id):
    """Bitta o'quvchining javoblari (o'qituvchi uchun doim to'liq)."""
    attempt = get_object_or_404(Attempt.objects.select_related('exam', 'student'), pk=attempt_id)
    _exam_or_403(request, attempt.exam_id)
    answers = {a.question_id: a for a in attempt.answers.all()}
    rows = []
    for q in attempt.exam.questions.all():
        a = answers.get(q.pk)
        hits = (int(a.correct_a) + int(a.correct_b)) if a else 0
        rows.append({'q': q, 'a': a, 'state': 'empty' if not a or not a.is_answered else
                     'ok' if hits == q.max_items else 'part' if hits else 'bad'})
    return render(request, 'teacher/attempt.html', {'attempt': attempt, 'exam': attempt.exam, 'rows': rows, 'tab': 'teacher'})


# ---------- Guruhlar ----------

@teacher_required
def t_groups(request):
    groups = StudyGroup.objects.all() if request.user.is_admin_role else StudyGroup.objects.filter(teacher=request.user)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()[:120]
        if name:
            group = StudyGroup.objects.create(name=name, teacher=request.user)
            return redirect('t_group', pk=group.pk)
        messages.error(request, 'Guruh nomini yozing')
    return render(request, 'teacher/groups.html', {
        'groups': groups.annotate(n=Count('students')).select_related('teacher'), 'tab': 'teacher'})


@teacher_required
def t_group(request, pk):
    group = _group_or_403(request, pk)
    return render(request, 'teacher/group.html', {
        'group': group, 'students': group.students.order_by('full_name'), 'exams': group.exams.all(), 'tab': 'teacher'})


@teacher_required
@require_POST
def t_group_remove(request, pk, user_id):
    group = _group_or_403(request, pk)
    group.students.remove(user_id)
    messages.success(request, "O'quvchi guruhdan chiqarildi")
    return redirect('t_group', pk=pk)


@teacher_required
@require_POST
def t_group_delete(request, pk):
    _group_or_403(request, pk).delete()
    messages.success(request, "Guruh o'chirildi")
    return redirect('t_groups')


# ---------- Admin ----------

@admin_browser_required
def a_dashboard(request):
    context = stats.collect()
    context.update(tab='admin', hide_nav=True)
    return render(request, 'admin_panel/dashboard.html', context)


@admin_browser_required
def a_users(request):
    query = request.GET.get('q', '').strip()
    role = request.GET.get('rol', '')
    users = User.objects.order_by('-date_joined')
    if query:
        filters = Q(full_name__icontains=query) | Q(first_name__icontains=query) | Q(phone__icontains=query)
        if query.isdigit():
            filters |= Q(telegram_id=int(query))
        users = users.filter(filters)
    if role in User.Role.values:
        users = users.filter(role=role)
    return render(request, 'admin_panel/users.html', {
        'users': users[:200], 'query': query, 'role': role, 'roles': User.Role.choices, 'tab': 'admin',
        'hide_nav': True})


@admin_browser_required
@require_POST
def a_user_update(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if target.pk == request.user.pk:
        messages.error(request, "O'z hisobingizni o'zgartira olmaysiz")
        return redirect('a_users')
    role = request.POST.get('role')
    if role in User.Role.values:
        target.role = role
    if 'toggle_active' in request.POST:
        target.is_active = not target.is_active
    target.save(update_fields=['role', 'is_active'])
    messages.success(request, f'{target.display_name}: yangilandi')
    return redirect(request.POST.get('back') if str(request.POST.get('back', '')).startswith('/boshqaruv/') else 'a_users')
