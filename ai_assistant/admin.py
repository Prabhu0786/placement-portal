from django.contrib import admin
from .models import Conversation, Message, ResumeReview


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("role", "content", "created_at")
    can_delete = False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "created_at", "updated_at")
    search_fields = ("title", "user__username", "user__email")
    list_filter = ("created_at", "updated_at")
    inlines = [MessageInline]


@admin.register(ResumeReview)
class ResumeReviewAdmin(admin.ModelAdmin):
    list_display = ("user", "filename", "target_role", "overall_score", "created_at")
    search_fields = ("user__username", "user__email", "filename", "target_role")
    list_filter = ("created_at", "overall_score")
    readonly_fields = ("user", "filename", "target_role", "overall_score", "report", "created_at")
