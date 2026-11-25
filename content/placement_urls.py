from django.urls import path

from . import placement_views as views

urlpatterns = [
    # Notices and contests
    path("notices/", views.notice_list, name="notice_list"),
    path("notices/<int:pk>/register/", views.contest_register, name="contest_register"),
    path("notices/<int:pk>/withdraw/", views.contest_withdraw, name="contest_withdraw"),
    path("manage/notices/", views.manage_notices, name="manage_notices"),
    path("manage/notices/add/", views.notice_create, name="notice_create"),
    path("manage/notices/<int:pk>/edit/", views.notice_edit, name="notice_edit"),
    path("manage/notices/<int:pk>/status/", views.notice_transition, name="notice_transition"),
    # Applications
    path("applications/", views.application_list, name="application_list"),
    path("applications/add/", views.application_add, name="application_add"),
    path("applications/track/<int:company_pk>/", views.application_track, name="application_track"),
    path("applications/<int:pk>/status/", views.application_status, name="application_status"),
    path("applications/<int:pk>/eligibility/", views.application_eligibility, name="application_eligibility"),
    path("applications/<int:pk>/delete/", views.application_delete, name="application_delete"),
    path("manage/applications/", views.manage_applications, name="manage_applications"),
    path("manage/applications/<int:pk>/status/", views.manage_application_status, name="manage_application_status"),
    # Preparation
    path("prepare/", views.prepare_home, name="prepare_home"),
    path("interview-prep/", views.interview_prep, name="interview_prep"),
    path("resume-checklist/", views.resume_checklist, name="resume_checklist"),
    path("projects/", views.project_list, name="project_list"),
    path("projects/<int:pk>/", views.project_prepare, name="project_prepare"),
]
