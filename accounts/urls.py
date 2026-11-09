from django.urls import path

from . import views

urlpatterns = [
    path('auth/telegram/', views.tg_auth, name='tg_auth'),
    path('kirish/<str:token>/', views.login_link, name='login_link'),
    path('chiqish/', views.logout_view, name='logout'),
    path('mrclayd/', views.entry, {'target': 'admin'}, name='entry_admin'),
    path('ustoz/', views.entry, {'target': 'teacher'}, name='entry_teacher'),
]
