from django.conf import settings
from django.db import models

from content.models import Topic


class Recommendation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recommendations"
    )
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="recommendations")
    # BR-9: every recommendation must show a reason.
    reason = models.CharField(max_length=300)
    priority = models.PositiveSmallIntegerField(default=1, help_text="1 = most important.")
    date = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ["priority", "-date"]

    def __str__(self):
        return f"{self.user}: {self.topic} (priority {self.priority})"


class WeeklyGoal(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        RESCHEDULED = "rescheduled", "Rescheduled"
        MISSED = "missed", "Missed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="weekly_goals"
    )
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="weekly_goals")
    due_date = models.DateField()
    target = models.PositiveSmallIntegerField(default=5, help_text="Number of questions to complete.")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)

    class Meta:
        ordering = ["due_date"]

    def __str__(self):
        return f"{self.user}: {self.topic} by {self.due_date}"
