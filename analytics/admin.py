from django.contrib import admin

from .models import ProgressMetric


@admin.register(ProgressMetric)
class ProgressMetricAdmin(admin.ModelAdmin):
    list_display = ("user", "topic", "accuracy", "attempts", "period_start", "period_end")
    list_filter = ("topic",)
