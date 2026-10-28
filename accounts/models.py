from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.Model):
    """One of: Student, TPO, Faculty, Administrator."""

    role_name = models.CharField(max_length=50, unique=True)
    permissions = models.TextField(
        blank=True,
        help_text="Plain-text description of what this role is allowed to do.",
    )

    def __str__(self):
        return self.role_name


class User(AbstractUser):
    """Custom user. Login still uses username; email must be unique."""

    class AccountStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        DEACTIVATED = "deactivated", "Deactivated"

    email = models.EmailField(unique=True)
    role = models.ForeignKey(
        Role,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="users",
    )
    account_status = models.CharField(
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.ACTIVE,
    )

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def role_name(self):
        return self.role.role_name if self.role else ""

    @property
    def is_student(self):
        return self.role_name == "Student"

    @property
    def is_tpo(self):
        return self.role_name == "TPO"

    @property
    def is_faculty(self):
        return self.role_name == "Faculty"

    @property
    def is_administrator(self):
        return self.role_name == "Administrator"


class StudentProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_profile",
    )
    programme = models.CharField(max_length=100, default="MCA")
    year = models.PositiveSmallIntegerField(default=1)
    skills = models.TextField(blank=True, help_text="Comma-separated skills.")
    targets = models.TextField(blank=True, help_text="Target roles and companies.")
    # BR-14: resume, project and performance data need consent.
    consent_given = models.BooleanField(default=False)
    consent_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Profile of {self.user}"


class ProjectAchievement(models.Model):
    class RecordType(models.TextChoices):
        PROJECT = "project", "Project"
        CERTIFICATE = "certificate", "Certificate"
        ACHIEVEMENT = "achievement", "Achievement"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_achievements",
    )
    type = models.CharField(max_length=20, choices=RecordType.choices)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    evidence_link = models.URLField(blank=True, help_text="Optional GitHub/certificate link.")

    def __str__(self):
        return f"{self.get_type_display()}: {self.title}"
