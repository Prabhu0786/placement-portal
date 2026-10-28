from django.conf import settings
from django.db import models

from content.models import Topic


class ProgressMetric(models.Model):
    """BR-8: always calculated from stored attempts, never typed in by hand."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="progress_metrics"
    )
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="progress_metrics")
    accuracy = models.FloatField(default=0, help_text="Percentage, 0 to 100.")
    attempts = models.PositiveIntegerField(default=0)
    time_spent_seconds = models.PositiveIntegerField(default=0)
    period_start = models.DateField()
    period_end = models.DateField()

    class Meta:
        unique_together = ("user", "topic", "period_start")
        ordering = ["-period_start"]

    def __str__(self):
        return f"{self.user} / {self.topic}: {self.accuracy:.0f}%"
