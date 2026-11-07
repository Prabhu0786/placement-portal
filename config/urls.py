from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("content.urls")),
    path("", include("assessments.urls")),
    path("", include("analytics.urls")),
    path("", include("planning.urls")),
    path("ai-assistant/", include("ai_assistant.urls")),
]
