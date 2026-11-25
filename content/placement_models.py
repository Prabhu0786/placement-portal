"""Phase 8 records: contest sign-ups, resume checklist progress and project-explanation notes.

Imported from models.py so Django registers them. Checklist progress and project notes are private to
the student (resume and project data need consent and restricted access, BR-14): no report, TPO page
or admin screen shows them.
"""
from django.conf import settings
from django.db import models


class ContestParticipation(models.Model):
    """A student's registration for a contest."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contest_registrations"
    )
    contest = models.ForeignKey("content.NoticeContest", on_delete=models.CASCADE, related_name="participants")
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "contest")

    def __str__(self):
        return f"{self.user} -> {self.contest}"


class ChecklistProgress(models.Model):
    """One ticked item of the resume checklist."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="checklist_progress"
    )
    key = models.CharField(max_length=50)
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "key")

    def __str__(self):
        return f"{self.user}: {self.key}"


class ProjectNote(models.Model):
    """A student's own answer to one project-explanation prompt."""

    project = models.ForeignKey("accounts.ProjectAchievement", on_delete=models.CASCADE, related_name="notes")
    prompt_key = models.CharField(max_length=50)
    text = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("project", "prompt_key")

    def __str__(self):
        return f"{self.project}: {self.prompt_key}"
