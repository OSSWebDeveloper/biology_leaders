import secrets
import uuid
from pathlib import PurePath

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

CODE_ALPHABET = '23456789ABCDEFGHJKMNPQRSTUVWXYZ'  # 0/O, 1/I/L adashmasligi uchun
CODE_LENGTH = 6


def generate_access_code():
    while True:
        code = ''.join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if not Exam.objects.filter(access_code=code).exists():
            return code


def attachment_path(instance, filename):
    # Media ochiq xizmat qilinadi: manzilni taxmin qilib bo'lmasligi kerak
    return f'exam_files/{uuid.uuid4().hex}{PurePath(filename).suffix.lower()}'


class Exam(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Qoralama'
        PUBLISHED = 'published', "E'lon qilingan"

    title = models.CharField("Test nomi", max_length=200)
    subject = models.CharField("Fan", max_length=80, default='Matematika')
    description = models.TextField("Izoh", blank=True)
    duration_min = models.PositiveIntegerField("Vaqt (daqiqa)", default=150)
    status = models.CharField("Holati", max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name='created_exams')
    is_public = models.BooleanField("Hamma uchun ochiq", default=False,
                                    help_text="Faqat admin belgilaydi. Aks holda test tanlangan guruhlarga ko'rinadi.")
    groups = models.ManyToManyField('accounts.StudyGroup', blank=True, related_name='exams',
                                    verbose_name='Guruhlar')
    opens_at = models.DateTimeField("Ochilish vaqti", null=True, blank=True)
    closes_at = models.DateTimeField("Yopilish vaqti", null=True, blank=True)
    max_attempts = models.PositiveIntegerField("Urinishlar soni", default=1, help_text='0 — cheklanmagan')
    access_code = models.CharField("Kirish kodi", max_length=8, unique=True, editable=False,
                                   default=generate_access_code)
    attachment = models.FileField("Test fayli", upload_to=attachment_path, blank=True)
    show_answers = models.BooleanField("Tugagach to'g'ri javoblar ko'rinsin", default=True)
    weight_mcq = models.FloatField("Yopiq test vazni (1–32)", default=1)
    weight_matching = models.FloatField("Moslashtirish vazni (33–35)", default=1)
    weight_open = models.FloatField("Yozma band vazni (36–45, a/b har biri)", default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Test'
        verbose_name_plural = 'Testlar'

    def __str__(self):
        return self.title

    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED

    def is_open_now(self):
        now = timezone.now()
        return (not self.opens_at or self.opens_at <= now) and (not self.closes_at or now < self.closes_at)

    def weight_for(self, kind):
        return {Question.Kind.MCQ: self.weight_mcq, Question.Kind.MATCHING: self.weight_matching,
                Question.Kind.OPEN: self.weight_open}[kind]

    def missing_keys(self):
        """Javob kaliti to'ldirilmagan savol raqamlari."""
        return [q.number for q in self.questions.all() if not q.has_key()]


class Question(models.Model):
    class Kind(models.TextChoices):
        MCQ = 'mcq', 'Yopiq test (A–D)'
        MATCHING = 'matching', 'Moslashtirish (A–F)'
        OPEN = 'open', 'Yozma javob'

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='questions')
    number = models.PositiveIntegerField("Raqami")
    kind = models.CharField("Turi", max_length=10, choices=Kind.choices, default=Kind.MCQ)
    text = models.TextField("Matn", blank=True, help_text="Formula uchun LaTeX: $x^2+1$")
    image = models.ImageField("Rasm", upload_to='questions/%Y/%m/', blank=True)
    options = models.JSONField("Variantlar matni", default=list, blank=True,
                               help_text="Bo'sh bo'lsa, variantlar rasmda deb hisoblanadi")
    correct = models.CharField("To'g'ri variant", max_length=1, blank=True)
    part_a = models.CharField("a) band matni", max_length=300, blank=True)
    part_b = models.CharField("b) band matni", max_length=300, blank=True)
    two_parts = models.BooleanField("a) va b) bandli", default=True,
                                    help_text="Belgilanmasa, yozma savolga bitta javob yoziladi")
    answer_a = models.TextField("Javob (a)", blank=True,
                                help_text="Bir nechta to'g'ri javob: 2√5 or √20")
    answer_b = models.TextField("b) javobi", blank=True)

    class Meta:
        ordering = ['number']
        constraints = [models.UniqueConstraint(fields=['exam', 'number'], name='uniq_exam_question_number')]
        verbose_name = 'Savol'
        verbose_name_plural = 'Savollar'

    def __str__(self):
        return f'{self.exam_id}/{self.number}'

    @property
    def image_url(self):
        """Rasm ochiq /media/ orqali emas, ruxsat tekshiradigan sahifa orqali beriladi."""
        if not self.image:
            return ''
        from django.urls import reverse
        return reverse('question_image', args=[self.pk])

    @property
    def letters(self):
        return 'ABCDEF' if self.kind == self.Kind.MATCHING else 'ABCD'

    def has_key(self):
        if self.kind == self.Kind.OPEN:
            return bool(self.answer_a.strip() and (self.answer_b.strip() or not self.two_parts))
        return bool(self.correct)

    @property
    def max_items(self):
        return 2 if self.kind == self.Kind.OPEN and self.two_parts else 1


class Attempt(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attempts')
    started_at = models.DateTimeField(auto_now_add=True)
    deadline = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    correct_items = models.PositiveIntegerField(default=0)
    total_items = models.PositiveIntegerField(default=0)
    percent = models.FloatField(default=0)
    score = models.FloatField("Ball (75 lik)", default=0)
    grade = models.CharField("Daraja", max_length=4, blank=True)

    class Meta:
        ordering = ['-started_at']
        constraints = [models.UniqueConstraint(fields=['exam', 'student'], condition=Q(finished_at__isnull=True),
                                               name='uniq_active_attempt')]

    def __str__(self):
        return f'{self.student} — {self.exam}'

    @property
    def is_finished(self):
        return self.finished_at is not None

    def seconds_left(self):
        return max(0, int((self.deadline - timezone.now()).total_seconds()))

    @property
    def spent_minutes(self):
        end = self.finished_at or timezone.now()
        return max(0, round((end - self.started_at).total_seconds() / 60))


class Answer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    choice = models.CharField(max_length=1, blank=True)
    value_a = models.CharField(max_length=64, blank=True)
    value_b = models.CharField(max_length=64, blank=True)
    correct_a = models.BooleanField(default=False)  # yopiq savolda natija shu maydonda
    correct_b = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['attempt', 'question'], name='uniq_attempt_question')]

    @property
    def is_answered(self):
        return bool(self.choice or self.value_a or self.value_b)
