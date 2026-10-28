from django.contrib import admin

from .models import Assessment, AssessmentQuestion, Attempt, Response


class AssessmentQuestionInline(admin.TabularInline):
    model = AssessmentQuestion
    extra = 1


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ("title", "type", "duration", "status")
    list_filter = ("type", "status")
    inlines = [AssessmentQuestionInline]


class ResponseInline(admin.TabularInline):
    model = Response
    extra = 0


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "assessment", "attempt_type", "status", "score")
    list_filter = ("status", "attempt_type")
    inlines = [ResponseInline]
