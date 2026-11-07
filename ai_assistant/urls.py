from django.urls import path
from . import views

urlpatterns = [
    path("", views.chat, name="ai_chat"),
    path("new/", views.new_conversation, name="ai_new_conversation"),
    path("send/", views.send_message, name="ai_send_message"),
    path("conversation/<int:conversation_id>/", views.open_conversation, name="ai_open_conversation"),
    path("conversation/<int:conversation_id>/rename/", views.rename_conversation, name="ai_rename_conversation"),
    path("conversation/<int:conversation_id>/delete/", views.delete_conversation, name="ai_delete_conversation"),
    path("clear/", views.clear_chat, name="ai_clear_chat"),
]
