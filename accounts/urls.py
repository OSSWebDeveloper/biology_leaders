from django.urls import path

from . import views

urlpatterns = [
    path('auth/telegram/', views.tg_auth, name='tg_auth'),
    path('kirish/', views.browser_enter, name='browser_enter'),  # sinov rejimi (BROWSER_STUDENTS)
    path('kirish/<str:token>/', views.login_link, name='login_link'),
    path('chiqish/', views.logout_view, name='logout'),
    # Maxsus bo'limlarga faqat shu ikki manzil orqali kiriladi (eski /mrclayd/ va /ustoz/ endi yo'q)
    path('testlar/mrclayd/', views.entry, {'target': 'admin'}, name='entry_admin'),
    path('testlar/ustoz/', views.entry, {'target': 'teacher'}, name='entry_teacher'),
]
