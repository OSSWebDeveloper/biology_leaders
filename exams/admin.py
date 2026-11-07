from django.contrib import admin

from .models import Answer, Attempt, Exam, Question


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    fields = ('number', 'kind', 'correct', 'answer_a', 'answer_b')


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'status', 'is_public', 'created_by', 'created_at')
    list_filter = ('status', 'is_public', 'subject')
    inlines = [QuestionInline]


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ('student', 'exam', 'started_at', 'finished_at', 'score', 'grade')
    list_filter = ('exam', 'grade')


admin.site.register(Question)
admin.site.register(Answer)
