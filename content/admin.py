from django.contrib import admin

from .models import Application, Company, NoticeContest, Question, Resource, Topic


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("subject", "name", "difficulty")
    list_filter = ("subject", "difficulty")
    search_fields = ("subject", "name")


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "source", "updated_at")
    list_filter = ("status",)
    search_fields = ("name",)


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "topic", "type", "status", "updated_at")
    list_filter = ("status", "type", "topic")
    search_fields = ("title",)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "topic", "type", "difficulty", "status")
    list_filter = ("type", "difficulty", "status", "topic")
    search_fields = ("text",)


@admin.register(NoticeContest)
class NoticeContestAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "date", "status")
    list_filter = ("kind", "status")


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "eligibility_status", "application_status")
    list_filter = ("application_status", "eligibility_status")
