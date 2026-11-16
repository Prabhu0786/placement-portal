from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views
from . import otp_views

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("login/", views.PortalLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),

    # Email OTP password reset
    path("password-reset/", otp_views.password_reset_request, name="password_reset"),
    path("password-reset/sent/", otp_views.password_reset_otp_sent, name="password_reset_otp_sent"),
    path("password-reset/verify/", otp_views.password_reset_verify_otp, name="password_reset_verify_otp"),
    path("password-reset/new-password/", otp_views.password_reset_new_password, name="password_reset_new_password"),
    path("password-reset/complete/", otp_views.password_reset_complete_otp, name="password_reset_complete_otp"),

    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.profile, name="profile"),
    path("profile/edit/", views.profile_edit, name="profile_edit"),
    path("profile/achievements/add/", views.achievement_add, name="achievement_add"),
    path(
        "profile/achievements/<int:pk>/delete/",
        views.achievement_delete,
        name="achievement_delete",
    ),
]
