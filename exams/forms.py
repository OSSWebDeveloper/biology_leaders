import datetime
import re

from django import forms
from django.core.validators import MinValueValidator

from .models import Exam, Question
from .services import DEFAULT_SHEET

MAX_PDF_MB = 30
WORD_SIGNATURES = (b'PK\x03\x04', b'\xd0\xcf\x11\xe0')  # .docx (zip), .doc (OLE)


COUNT_FIELDS = (('mcq', "4 variantli savollar soni"), ('matching', "6 variantli savollar soni"),
                ('open', "Ochiq savollar soni"))


CODE_PATTERN = re.compile(r'[A-Z0-9]{3,8}')


class ExamForm(forms.ModelForm):
    """Savollar soni maydonlari modelda emas: saqlangach set_question_counts bilan qo'llanadi."""
    code = forms.CharField(label='Kirish kodi', max_length=8,
                           help_text="O'quvchi testga shu kod bilan kiradi: 3–8 ta lotin harfi yoki raqam")
    count_mcq = forms.IntegerField(min_value=0, max_value=99)
    count_matching = forms.IntegerField(min_value=0, max_value=99)
    count_open = forms.IntegerField(min_value=0, max_value=99)
    test_file = forms.FileField(
        label='Test fayli (PDF yoki Word)', required=False,
        help_text="Guruhga shu fayl yuboriladi. PDF dagi «JAVOBLAR» sahifasi o'quvchilarga ketmaydi.")

    field_order = ['title', 'code', 'description', 'duration_min', 'opens_at',
                   'count_mcq', 'count_matching', 'count_open', 'show_answers', 'test_file']

    class Meta:
        model = Exam
        fields = ['title', 'description', 'duration_min', 'opens_at',
                  'show_answers']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'opens_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        opens = self.fields['opens_at']
        opens.input_formats = ['%Y-%m-%dT%H:%M']
        opens.required = True
        opens.label = 'Boshlanish vaqti'
        opens.help_text = "Tugash vaqti avtomatik: boshlanish + test vaqti"
        self.fields['duration_min'].label = 'Test vaqti (daqiqa)'
        self.fields['duration_min'].validators.append(MinValueValidator(1))
        if self.instance.pk:
            self.fields['code'].initial = self.instance.access_code
        else:
            self.initial['duration_min'] = None  # o'qituvchi o'zi yozadi
        current = DEFAULT_SHEET
        if self.instance.pk:
            current = {kind: self.instance.questions.filter(kind=kind).count() for kind, _ in COUNT_FIELDS}
        for kind, label in COUNT_FIELDS:
            field = self.fields[f'count_{kind}']
            field.label = label
            field.initial = current.get(kind, 0)

    def clean_code(self):
        code = self.cleaned_data['code'].strip().upper()
        if not CODE_PATTERN.fullmatch(code):
            raise forms.ValidationError("3–8 ta lotin harfi yoki raqam, bo'sh joysiz")
        if Exam.objects.filter(access_code=code).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Bu kod boshqa testda band')
        return code

    def save(self, commit=True):
        self.instance.access_code = self.cleaned_data['code']
        if 'opens_at' in self.changed_data:
            self.instance.channel_posted_at = None  # yangi vaqtda kanalga qayta e'lon qilinadi
        return super().save(commit)

    def clean_test_file(self):
        return validate_test_file(self.cleaned_data.get('test_file'))

    @property
    def counts(self):
        return {kind: self.cleaned_data[f'count_{kind}'] for kind, _ in COUNT_FIELDS}

    def clean(self):
        data = super().clean()
        if all(f'count_{kind}' in data for kind, _ in COUNT_FIELDS):
            if not any(data[f'count_{kind}'] for kind, _ in COUNT_FIELDS):
                raise forms.ValidationError("Kamida bitta savol bo'lsin")
            if self.instance.pk and self.instance.attempts.exists():
                current = {kind: self.instance.questions.filter(kind=kind).count() for kind, _ in COUNT_FIELDS}
                if self.counts != current:
                    raise forms.ValidationError("Testni yechganlar bor: savollar sonini o'zgartirib bo'lmaydi")
        opens, duration = data.get('opens_at'), data.get('duration_min')
        if opens and duration:
            self.instance.closes_at = opens + datetime.timedelta(minutes=duration)
        return data


class QuestionForm(forms.ModelForm):
    options_text = forms.CharField(
        label='Variantlar matni', required=False, widget=forms.Textarea(attrs={'rows': 4}),
        help_text="Har bir variant alohida qatorda. Variantlar rasmda bo'lsa, bo'sh qoldiring.")

    class Meta:
        model = Question
        fields = ['number', 'kind', 'text', 'image', 'correct', 'two_parts', 'part_a', 'part_b', 'answer_a', 'answer_b']
        widgets = {'text': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['options_text'].initial = '\n'.join(self.instance.options or [])

    def clean_correct(self):
        return self.cleaned_data['correct'].strip().upper()

    def clean(self):
        data = super().clean()
        kind = data.get('kind')
        letters = 'ABCDEF' if kind == Question.Kind.MATCHING else 'ABCD'
        correct = data.get('correct')
        if kind != Question.Kind.OPEN and correct and correct not in letters:
            self.add_error('correct', f"Variant {letters[0]}–{letters[-1]} bo'lishi kerak")
        if not data.get('text') and not data.get('image') and not self.instance.image:
            raise forms.ValidationError('Savol matni yoki rasmi bo\'lishi kerak')
        return data

    def save(self, commit=True):
        self.instance.options = [x.strip() for x in self.cleaned_data['options_text'].splitlines() if x.strip()]
        return super().save(commit)


class PdfImportForm(forms.Form):
    pdf = forms.FileField(label='Test fayli (PDF yoki Word)')
    replace = forms.BooleanField(label="Mavjud savollarni almashtirish", required=False)

    def clean_pdf(self):
        return validate_test_file(self.cleaned_data['pdf'])


def validate_test_file(pdf):
    if not pdf:
        return pdf
    if pdf.size > MAX_PDF_MB * 1024 * 1024:
        raise forms.ValidationError(f'Fayl {MAX_PDF_MB} MB dan oshmasin')
    name = pdf.name.lower()
    if not name.endswith(('.pdf', '.doc', '.docx')):
        raise forms.ValidationError('Faqat PDF yoki Word fayl')
    if not name.endswith('.pdf'):
        head = pdf.read(4)
        pdf.seek(0)
        if head not in WORD_SIGNATURES:
            raise forms.ValidationError("Word faylni o'qib bo'lmadi")
    return pdf
