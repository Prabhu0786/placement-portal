from django.urls import path

from . import mock_views as views

urlpatterns = [
    path("", views.mock_home, name="ai_mock_home"),
    path("consent/", views.mock_consent, name="ai_mock_consent"),
    path("start/", views.mock_start, name="ai_mock_start"),
    path("delete-all/", views.mock_delete_all, name="ai_mock_delete_all"),
    path("<int:pk>/", views.mock_run, name="ai_mock_run"),
    path("<int:pk>/report/", views.mock_report, name="ai_mock_report"),
    path("<int:pk>/delete/", views.mock_delete, name="ai_mock_delete"),
    path("turn/<int:pk>/retry/", views.mock_retry, name="ai_mock_retry"),
]
