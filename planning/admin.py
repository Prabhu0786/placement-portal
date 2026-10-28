from django.contrib import admin

from .models import Recommendation, WeeklyGoal


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ("user", "topic", "priority", "date")


@admin.register(WeeklyGoal)
class WeeklyGoalAdmin(admin.ModelAdmin):
    list_display = ("user", "topic", "due_date", "target", "status")
    list_filter = ("status",)
