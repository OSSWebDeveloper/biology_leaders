from django.urls import path

from . import teacher_views as t
from . import views as v

urlpatterns = [
    path('', v.home, name='home'),
    path('testlar/', v.exam_list, name='exam_list'),
    path('test/<int:pk>/', v.exam_detail, name='exam_detail'),
    path('test/<int:pk>/boshlash/', v.attempt_start, name='attempt_start'),
    path('test/<int:pk>/reyting/', v.leaderboard, name='leaderboard'),
    path('urinish/<int:pk>/', v.attempt_view, name='attempt'),
    path('urinish/<int:pk>/javob/', v.attempt_answer, name='attempt_answer'),
    path('urinish/<int:pk>/yakunlash/', v.attempt_finish, name='attempt_finish'),
    path('urinish/<int:pk>/natija/', v.attempt_result, name='attempt_result'),
    path('natijalar/', v.my_results, name='my_results'),
    path('guruhga-qoshilish/', v.join_group, name='join_group'),

    path('oqituvchi/', t.t_exams, name='t_exams'),
    path('oqituvchi/test/yangi/', t.t_exam_new, name='t_exam_new'),
    path('oqituvchi/test/<int:pk>/', t.t_exam, name='t_exam'),
    path('oqituvchi/test/<int:pk>/sozlama/', t.t_exam_edit, name='t_exam_edit'),
    path('oqituvchi/test/<int:pk>/pdf/', t.t_pdf, name='t_pdf'),
    path('oqituvchi/test/<int:pk>/elon/', t.t_publish, name='t_publish'),
    path('oqituvchi/test/<int:pk>/ochirish/', t.t_exam_delete, name='t_exam_delete'),
    path('oqituvchi/test/<int:pk>/natijalar/', t.t_results, name='t_results'),
    path('oqituvchi/test/<int:pk>/natijalar.xlsx', t.t_results_xlsx, name='t_results_xlsx'),
    path('oqituvchi/test/<int:pk>/savol/yangi/', t.t_question, name='t_question_new'),
    path('oqituvchi/test/<int:pk>/savol/<int:qid>/', t.t_question, name='t_question'),
    path('oqituvchi/test/<int:pk>/savol/<int:qid>/ochirish/', t.t_question_delete, name='t_question_delete'),
    path('oqituvchi/urinish/<int:attempt_id>/', t.t_attempt, name='t_attempt'),
    path('oqituvchi/guruhlar/', t.t_groups, name='t_groups'),
    path('oqituvchi/guruh/<int:pk>/', t.t_group, name='t_group'),
    path('oqituvchi/guruh/<int:pk>/ochirish/', t.t_group_delete, name='t_group_delete'),
    path('oqituvchi/guruh/<int:pk>/chiqarish/<int:user_id>/', t.t_group_remove, name='t_group_remove'),

    path('boshqaruv/', t.a_dashboard, name='a_dashboard'),
    path('boshqaruv/foydalanuvchilar/', t.a_users, name='a_users'),
    path('boshqaruv/foydalanuvchi/<int:user_id>/', t.a_user_update, name='a_user_update'),
]
