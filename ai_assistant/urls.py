from django.urls import path
from . import views

urlpatterns = [
    path("", views.chat, name="ai_chat"),
    path("clear/", views.clear_chat, name="ai_clear_chat"),
]
