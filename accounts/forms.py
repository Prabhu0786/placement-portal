from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils import timezone

from .models import ProjectAchievement, Role, StudentProfile, User


class StudentRegistrationForm(UserCreationForm):
    """Public sign-up. It can only ever create STUDENT accounts (BR-2)."""

    first_name = forms.CharField(max_length=150, label="First name")
    last_name = forms.CharField(max_length=150, label="Last name")
    email = forms.EmailField(label="Email address")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")

    def save(self, commit=True):
        user = super().save(commit=False)
        role, _ = Role.objects.get_or_create(role_name="Student")
        user.role = role
        if commit:
            user.save()
            StudentProfile.objects.get_or_create(user=user)
        return user


class PortalAuthenticationForm(AuthenticationForm):
    """Login form that also refuses suspended or deactivated accounts."""

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.account_status != User.AccountStatus.ACTIVE:
            raise forms.ValidationError(
                "This account is not active. Please contact the placement coordinator.",
                code="inactive",
            )


class StudentProfileForm(forms.ModelForm):
    year = forms.IntegerField(min_value=1, max_value=6, label="Year of study")
    consent_given = forms.BooleanField(
        required=False,
        label=(
            "I agree that my profile, project and performance data may be stored "
            "and viewed by the placement coordinator."
        ),
    )

    class Meta:
        model = StudentProfile
        fields = ("programme", "year", "skills", "targets", "consent_given")
        labels = {
            "programme": "Programme",
            "skills": "Skills",
            "targets": "Target roles and companies",
        }
        widgets = {
            "skills": forms.Textarea(attrs={"rows": 3}),
            "targets": forms.Textarea(attrs={"rows": 3}),
        }

    def save(self, commit=True):
        profile = super().save(commit=False)
        if profile.consent_given and profile.consent_date is None:
            profile.consent_date = timezone.now()
        elif not profile.consent_given:
            profile.consent_date = None
        if commit:
            profile.save()
        return profile


class AchievementForm(forms.ModelForm):
    class Meta:
        model = ProjectAchievement
        fields = ("type", "title", "description", "evidence_link")
        labels = {"type": "Type", "evidence_link": "Evidence link (optional)"}
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}
