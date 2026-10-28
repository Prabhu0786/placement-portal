from django.conf import settings
from django.db import models

from content.models import ContentStatus, Question


class Assessment(models.Model):
    class AssessmentType(models.TextChoices):
        APTITUDE = "aptitude", "Aptitude"
        CODING = "coding", "Coding"
        VERBAL = "verbal", "Verbal"
        TECHNICAL = "technical", "Technical"
        MIXED = "mixed", "Mixed"

    title = models.CharField(max_length=200)
    type = models.CharField(
        max_length=20, choices=AssessmentType.choices, default=AssessmentType.MIXED
    )
    duration = models.PositiveIntegerField(help_text="Duration in minutes.")
    status = models.CharField(
        max_length=20, choices=ContentStatus.choices, default=ContentStatus.DRAFT
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="assessments"
    )
    questions = models.ManyToManyField(
        Question, through="AssessmentQuestion", related_name="assessments"
    )

    def __str__(self):
        return self.title


class AssessmentQuestion(models.Model):
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.PROTECT)
    marks = models.PositiveSmallIntegerField(default=1)
    display_order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        unique_together = ("assessment", "question")
        ordering = ["assessment", "display_order"]

    def __str__(self):
        return f"{self.assessment} - Q{self.display_order}"


class Attempt(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        IN_PROGRESS = "in_progress", "In progress"
        SUBMITTED = "submitted", "Submitted"
        TIMED_OUT = "timed_out", "Timed out"
        EVALUATED = "evaluated", "Evaluated"
        REVIEWED = "reviewed", "Reviewed"

    class AttemptType(models.TextChoices):
        PRACTICE = "practice", "Practice"
        ASSESSMENT = "assessment", "Timed assessment"

    # Allowed state changes. BR-7: SUBMITTED / TIMED_OUT can never go back to IN_PROGRESS.
    ALLOWED_TRANSITIONS = {
        "created": {"in_progress"},
        "in_progress": {"submitted", "timed_out"},
        "submitted": {"evaluated"},
        "timed_out": {"evaluated"},
        "evaluated": {"reviewed"},
        "reviewed": set(),
    }

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attempts"
    )
    # Empty for free practice sessions; set for timed assessments.
    assessment = models.ForeignKey(
        Assessment, null=True, blank=True, on_delete=models.PROTECT, related_name="attempts"
    )
    attempt_type = models.CharField(
        max_length=20, choices=AttemptType.choices, default=AttemptType.ASSESSMENT
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
    started_at = models.DateTimeField(null=True, blank=True)
    # Server-side deadline (started_at + duration). The timer is enforced from this value.
    expires_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)

    def change_status(self, new_status):
        """Move to a new state, refusing any transition the state diagram does not allow."""
        if new_status not in self.ALLOWED_TRANSITIONS[self.status]:
            raise ValueError(f"Cannot change attempt from '{self.status}' to '{new_status}'.")
        self.status = new_status
        self.save(update_fields=["status"])

    def __str__(self):
        return f"{self.user} - {self.assessment or 'Practice'} ({self.get_status_display()})"


class Response(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="responses")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="responses")
    answer = models.TextField(blank=True)
    is_correct = models.BooleanField(null=True, blank=True, help_text="Empty until evaluated.")
    marks_awarded = models.FloatField(default=0)
    time_taken_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("attempt", "question")

    def __str__(self):
        return f"Response to Q{self.question_id} in attempt {self.attempt_id}"
