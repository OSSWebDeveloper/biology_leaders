from django import forms

from accounts.models import StudyGroup

from .models import Exam, Question

MAX_PDF_MB = 30


class ExamForm(forms.ModelForm):
    class Meta:
        model = Exam
        fields = ['title', 'subject', 'description', 'duration_min', 'groups', 'opens_at', 'closes_at',
                  'max_attempts', 'show_answers', 'is_public', 'weight_mcq', 'weight_matching', 'weight_open']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'opens_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'closes_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'groups': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('opens_at', 'closes_at'):
            self.fields[name].input_formats = ['%Y-%m-%dT%H:%M']
        groups = StudyGroup.objects.all()
        if not user.is_admin_role:
            groups = groups.filter(teacher=user)
            del self.fields['is_public']  # hammaga ochish faqat adminda
        self.fields['groups'].queryset = groups
        if not groups.exists():
            self.fields['groups'].help_text = "Hali guruh yo'q. Avval «Guruhlar» bo'limida yarating."

    def clean(self):
        data = super().clean()
        opens, closes = data.get('opens_at'), data.get('closes_at')
        if opens and closes and closes <= opens:
            self.add_error('closes_at', 'Yopilish vaqti ochilishdan keyin bo\'lsin')
        return data


class QuestionForm(forms.ModelForm):
    options_text = forms.CharField(
        label='Variantlar matni', required=False, widget=forms.Textarea(attrs={'rows': 4}),
        help_text="Har bir variant alohida qatorda. Variantlar rasmda bo'lsa, bo'sh qoldiring.")

    class Meta:
        model = Question
        fields = ['number', 'kind', 'text', 'image', 'correct', 'part_a', 'part_b', 'answer_a', 'answer_b']
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
    pdf = forms.FileField(label='PDF fayl')
    replace = forms.BooleanField(label="Mavjud savollarni almashtirish", required=False)

    def clean_pdf(self):
        pdf = self.cleaned_data['pdf']
        if pdf.size > MAX_PDF_MB * 1024 * 1024:
            raise forms.ValidationError(f'Fayl {MAX_PDF_MB} MB dan oshmasin')
        if not pdf.name.lower().endswith('.pdf'):
            raise forms.ValidationError('Faqat PDF fayl')
        return pdf
