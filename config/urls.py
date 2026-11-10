from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

handler404 = 'accounts.views.not_found'

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('', include('accounts.urls')),
    path('', include('exams.urls')),
    # questions/ ochiq emas: savol rasmlari exams.views.question_image orqali, ruxsat bilan
    re_path(r'^media/(?P<path>(?!questions/).*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
