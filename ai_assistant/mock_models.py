"""Mock interview records. Imported from models.py so Django registers them.

Privacy: transcripts belong to the student who created them. They are never used for reports,
progress metrics or the readiness indicator, and they are not shown to the TPO, faculty or admins.
"""
from django.conf import settings
from django.db import models

RATING_LABELS = {1: "Needs a lot of work", 2: "Needs work", 3: "Fair", 4: "Good", 5: "Excellent"}


class MockInterview(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    class Source(models.TextChoices):
        BANK = "bank", "Portal question bank"
        AI = "ai", "AI-generated questions"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mock_interviews"
    )
    topic_label = models.CharField(max_length=160, help_text="Interview type shown to the student.")
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.BANK)
    difficulty = models.CharField(max_length=10, blank=True)
    target_role = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.IN_PROGRESS)
    total_questions = models.PositiveSmallIntegerField(default=0)
    average_rating = models.FloatField(null=True, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Mock interview ({self.topic_label}) - {self.created_at:%Y-%m-%d}"


class MockInterviewTurn(models.Model):
    class FeedbackStatus(models.TextChoices):
        PENDING = "pending", "Waiting for an answer"
        DONE = "done", "Feedback ready"
        FAILED = "failed", "Feedback unavailable"

    interview = models.ForeignKey(MockInterview, on_delete=models.CASCADE, related_name="turns")
    order = models.PositiveSmallIntegerField()
    question = models.ForeignKey(
        "content.Question", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    question_text = models.TextField()
    # Snapshot of the placement team's model answer (bank questions only), shown after answering.
    reference_answer = models.TextField(blank=True)
    answer_text = models.TextField(blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    feedback = models.JSONField(default=dict, blank=True)
    feedback_status = models.CharField(
        max_length=10, choices=FeedbackStatus.choices, default=FeedbackStatus.PENDING
    )
    rating = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["order"]
        unique_together = ("interview", "order")

    @property
    def rating_label(self):
        return RATING_LABELS.get(self.rating, "")

    def __str__(self):
        return f"Q{self.order}: {self.question_text[:50]}"
