from django.urls import path

from . import views

urlpatterns = [
    path("progress/", views.progress, name="progress"),
    path("progress/weekly/", views.weekly_report, name="weekly_report"),
    path("reports/", views.reports_home, name="reports_home"),
    path("reports/export.csv", views.report_export, name="report_export"),
    path("reports/student/<int:pk>/", views.report_student, name="report_student"),
]
