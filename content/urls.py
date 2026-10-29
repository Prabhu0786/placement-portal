from django.urls import path

from . import views

urlpatterns = [
    # Student pages
    path("resources/", views.resource_list, name="resource_list"),
    path("companies/", views.company_list, name="company_list"),
    path("companies/<int:pk>/", views.company_detail, name="company_detail"),
    # TPO / Faculty management
    path("manage/", views.manage_home, name="manage_home"),
    path("manage/resources/", views.manage_resources, name="manage_resources"),
    path("manage/resources/add/", views.resource_create, name="resource_create"),
    path("manage/resources/<int:pk>/edit/", views.resource_edit, name="resource_edit"),
    path("manage/resources/<int:pk>/status/", views.resource_transition, name="resource_transition"),
    path("manage/companies/", views.manage_companies, name="manage_companies"),
    path("manage/companies/add/", views.company_create, name="company_create"),
    path("manage/companies/<int:pk>/edit/", views.company_edit, name="company_edit"),
    path("manage/companies/<int:pk>/status/", views.company_transition, name="company_transition"),
    path("manage/questions/", views.manage_questions, name="manage_questions"),
    path("manage/questions/add/", views.question_create, name="question_create"),
    path("manage/questions/<int:pk>/edit/", views.question_edit, name="question_edit"),
    path("manage/questions/<int:pk>/status/", views.question_transition, name="question_transition"),
    path("manage/topics/", views.manage_topics, name="manage_topics"),
    path("manage/topics/add/", views.topic_create, name="topic_create"),
    path("manage/topics/<int:pk>/edit/", views.topic_edit, name="topic_edit"),
]
