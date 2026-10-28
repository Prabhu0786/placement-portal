from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import (
    AchievementForm,
    PortalAuthenticationForm,
    StudentProfileForm,
    StudentRegistrationForm,
)
from .models import ProjectAchievement, StudentProfile
from .permissions import role_required


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "accounts/home.html")


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Welcome! Your account is ready. Please complete your profile.")
            return redirect("profile_edit")
    else:
        form = StudentRegistrationForm()
    return render(request, "accounts/register.html", {"form": form})


class PortalLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = PortalAuthenticationForm
    redirect_authenticated_user = True


@login_required
def dashboard(request):
    context = {}
    if request.user.is_student:
        profile, _ = StudentProfile.objects.get_or_create(user=request.user)
        checklist = [
            ("Add your skills", bool(profile.skills.strip())),
            ("Add your target roles and companies", bool(profile.targets.strip())),
            ("Give consent for data sharing", profile.consent_given),
            (
                "Add a project, certificate or achievement",
                request.user.project_achievements.exists(),
            ),
        ]
        done = sum(1 for _, ok in checklist if ok)
        context.update(
            profile=profile,
            checklist=checklist,
            completeness=round(100 * done / len(checklist)),
        )
    return render(request, "accounts/dashboard.html", context)


@role_required("Student")
def profile(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    achievements = request.user.project_achievements.all()
    return render(
        request,
        "accounts/profile.html",
        {"profile": profile, "achievements": achievements},
    )


@role_required("Student")
def profile_edit(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = StudentProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile saved.")
            return redirect("profile")
    else:
        form = StudentProfileForm(instance=profile)
    return render(request, "accounts/profile_edit.html", {"form": form})


@role_required("Student")
def achievement_add(request):
    if request.method == "POST":
        form = AchievementForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.user = request.user
            item.save()
            messages.success(request, "Added to your profile.")
            return redirect("profile")
    else:
        form = AchievementForm()
    return render(request, "accounts/achievement_form.html", {"form": form})


@role_required("Student")
@require_POST
def achievement_delete(request, pk):
    item = get_object_or_404(ProjectAchievement, pk=pk, user=request.user)
    item.delete()
    messages.success(request, "Removed.")
    return redirect("profile")
