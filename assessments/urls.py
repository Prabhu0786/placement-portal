from django.urls import path

from . import manage_views, views

urlpatterns = [
    # Practice
    path("practice/", views.practice_home, name="practice_home"),
    path("practice/start/", views.practice_start, name="practice_start"),
    path("practice/session/<int:pk>/", views.practice_session, name="practice_session"),
    path("practice/session/<int:pk>/result/", views.practice_result, name="practice_result"),
    # Timed assessments (students)
    path("assessments/", views.assessment_list, name="assessment_list"),
    path("assessments/<int:pk>/start/", views.assessment_start, name="assessment_start"),
    path("attempts/<int:pk>/take/", views.attempt_take, name="attempt_take"),
    path("attempts/<int:pk>/save/", views.attempt_save, name="attempt_save"),
    path("attempts/<int:pk>/submit/", views.attempt_submit, name="attempt_submit"),
    path("attempts/<int:pk>/result/", views.attempt_result, name="attempt_result"),
    # Assessment management (TPO / Faculty)
    path("manage/assessments/", manage_views.manage_assessments, name="manage_assessments"),
    path("manage/assessments/add/", manage_views.assessment_create, name="assessment_create"),
    path("manage/assessments/<int:pk>/edit/", manage_views.assessment_edit, name="assessment_edit"),
    path("manage/assessments/<int:pk>/status/", manage_views.assessment_transition, name="assessment_transition"),
]
