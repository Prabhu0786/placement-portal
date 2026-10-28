from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import ProjectAchievement, Role, StudentProfile, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "account_status", "is_staff")
    list_filter = ("role", "account_status", "is_staff")
    fieldsets = UserAdmin.fieldsets + (
        ("Portal details", {"fields": ("role", "account_status")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Portal details", {"fields": ("email", "role", "account_status")}),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("role_name",)


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "programme", "year", "consent_given")


@admin.register(ProjectAchievement)
class ProjectAchievementAdmin(admin.ModelAdmin):
    list_display = ("title", "type", "user")
    list_filter = ("type",)
