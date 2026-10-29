from django.urls import path

from . import views

urlpatterns = [
    path("practice/", views.practice_home, name="practice_home"),
    path("practice/start/", views.practice_start, name="practice_start"),
    path("practice/session/<int:pk>/", views.practice_session, name="practice_session"),
    path("practice/session/<int:pk>/result/", views.practice_result, name="practice_result"),
]
