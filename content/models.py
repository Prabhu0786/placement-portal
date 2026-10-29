from django.conf import settings
from django.db import models


class ContentStatus(models.TextChoices):
    """Workflow for content. BR-4: only PUBLISHED content is visible to students."""

    DRAFT = "draft", "Draft"
    PENDING_REVIEW = "pending_review", "Pending review"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class Difficulty(models.TextChoices):
    EASY = "easy", "Easy"
    MEDIUM = "medium", "Medium"
    HARD = "hard", "Hard"


class Topic(models.Model):
    subject = models.CharField(max_length=100, help_text="e.g. Data Structures, Aptitude")
    name = models.CharField(max_length=150, help_text="e.g. Arrays, Percentages")
    difficulty = models.CharField(
        max_length=10, choices=Difficulty.choices, default=Difficulty.EASY
    )

    class Meta:
        unique_together = ("subject", "name")
        ordering = ["subject", "name"]

    def __str__(self):
        return f"{self.subject} / {self.name}"


class Company(models.Model):
    name = models.CharField(max_length=150, unique=True)
    eligibility = models.TextField(blank=True)
    stages = models.TextField(blank=True, help_text="Recruitment stages, one per line.")
    # BR-3: company information must include a source and an updated date.
    source = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20, choices=ContentStatus.choices, default=ContentStatus.DRAFT
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "companies"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Resource(models.Model):
    class ResourceType(models.TextChoices):
        ARTICLE = "article", "Article"
        VIDEO = "video", "Video"
        NOTES = "notes", "Notes / PDF"
        LINK = "link", "External link"

    topic = models.ForeignKey(Topic, on_delete=models.PROTECT, related_name="resources")
    company = models.ForeignKey(
        Company, null=True, blank=True, on_delete=models.SET_NULL, related_name="resources"
    )
    title = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=ResourceType.choices, default=ResourceType.ARTICLE)
    url = models.URLField(blank=True)
    source = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20, choices=ContentStatus.choices, default=ContentStatus.DRAFT
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="resources"
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class Question(models.Model):
    class QuestionType(models.TextChoices):
        CODING = "coding", "Coding"
        APTITUDE = "aptitude", "Aptitude"
        VERBAL = "verbal", "Verbal"
        TECHNICAL = "technical", "Technical"
        INTERVIEW = "interview", "Interview"

    topic = models.ForeignKey(Topic, on_delete=models.PROTECT, related_name="questions")
    company = models.ForeignKey(
        Company, null=True, blank=True, on_delete=models.SET_NULL, related_name="questions"
    )
    type = models.CharField(max_length=20, choices=QuestionType.choices)
    difficulty = models.CharField(
        max_length=10, choices=Difficulty.choices, default=Difficulty.EASY
    )
    text = models.TextField(help_text="The question statement.")
    options = models.JSONField(
        default=list, blank=True, help_text='For multiple choice, e.g. ["A", "B", "C", "D"].'
    )
    answer = models.TextField(blank=True)
    explanation = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=ContentStatus.choices, default=ContentStatus.DRAFT
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="questions"
    )

    def __str__(self):
        return f"[{self.get_type_display()}] {self.text[:60]}"


class NoticeContest(models.Model):
    class Kind(models.TextChoices):
        NOTICE = "notice", "Notice"
        CONTEST = "contest", "Contest"

    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.NOTICE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="notices"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    date = models.DateField(help_text="Notice date or contest date.")
    status = models.CharField(
        max_length=20, choices=ContentStatus.choices, default=ContentStatus.DRAFT
    )

    class Meta:
        verbose_name = "notice / contest"
        verbose_name_plural = "notices and contests"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.title}"


class Application(models.Model):
    class EligibilityStatus(models.TextChoices):
        NOT_CHECKED = "not_checked", "Not checked"
        ELIGIBLE = "eligible", "Eligible"
        NOT_ELIGIBLE = "not_eligible", "Not eligible"

    class ApplicationStatus(models.TextChoices):
        INTERESTED = "interested", "Interested"
        ELIGIBLE = "eligible", "Eligible"
        APPLIED = "applied", "Applied"
        SHORTLISTED = "shortlisted", "Shortlisted"
        REJECTED = "rejected", "Rejected"
        SELECTED = "selected", "Selected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="applications"
    )
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="applications")
    eligibility_status = models.CharField(
        max_length=20, choices=EligibilityStatus.choices, default=EligibilityStatus.NOT_CHECKED
    )
    application_status = models.CharField(
        max_length=20, choices=ApplicationStatus.choices, default=ApplicationStatus.INTERESTED
    )

    class Meta:
        unique_together = ("user", "company")

    def __str__(self):
        return f"{self.user} -> {self.company} ({self.get_application_status_display()})"
