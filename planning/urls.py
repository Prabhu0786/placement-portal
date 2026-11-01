from django.urls import path

from . import views

urlpatterns = [
    path("recommendations/", views.recommendations, name="recommendations"),
    path("plan/", views.plan, name="plan"),
    path("plan/add/", views.goal_create, name="goal_create"),
    path("plan/<int:pk>/status/", views.goal_status, name="goal_status"),
    path("plan/<int:pk>/reschedule/", views.goal_reschedule, name="goal_reschedule"),
    path("plan/<int:pk>/delete/", views.goal_delete, name="goal_delete"),
]
