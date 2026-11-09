from django import forms

from .models import Exam, Question
from .services import DEFAULT_SHEET

MAX_PDF_MB = 30
WORD_SIGNATURES = (b'PK\x03\x04', b'\xd0\xcf\x11\xe0')  # .docx (zip), .doc (OLE)


COUNT_FIELDS = (('mcq', "4 variantli savollar soni"), ('matching', "6 variantli savollar soni"),
                ('open', "Ochiq savollar soni"))


class ExamForm(forms.ModelForm):
    """Savollar soni maydonlari modelda emas: saqlangach set_question_counts bilan qo'llanadi."""
    count_mcq = forms.IntegerField(min_value=0, max_value=99)
    count_matching = forms.IntegerField(min_value=0, max_value=99)
    count_open = forms.IntegerField(min_value=0, max_value=99)

    class Meta:
        model = Exam
        fields = ['title', 'subject', 'description', 'duration_min', 'opens_at', 'closes_at',
                  'show_answers']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'opens_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'closes_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, label in (('opens_at', 'Boshlanish vaqti'), ('closes_at', 'Tugash vaqti')):
            self.fields[name].input_formats = ['%Y-%m-%dT%H:%M']
            self.fields[name].required = True
            self.fields[name].label = label
        current = DEFAULT_SHEET
        if self.instance.pk:
            current = {kind: self.instance.questions.filter(kind=kind).count() for kind, _ in COUNT_FIELDS}
        for kind, label in COUNT_FIELDS:
            field = self.fields[f'count_{kind}']
            field.label = label
            field.initial = current.get(kind, 0)

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
        opens, closes = data.get('opens_at'), data.get('closes_at')
        if opens and closes and closes <= opens:
            self.add_error('closes_at', "Tugash vaqti boshlanishdan keyin bo'lsin")
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
        pdf = self.cleaned_data['pdf']
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
