"""Notices and contests, company applications, interview preparation, resume checklist and
project-explanation prompts (UC-11, UC-12, UC-13 notices, UC-15)."""
from collections import OrderedDict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import ProjectAchievement, User
from accounts.permissions import role_required

from . import placement_services as services
from . import workflow
from .models import Application, Company, ContentStatus, NoticeContest, Question
from .placement_forms import AddApplicationForm, NoticeForm, ProjectPromptsForm
from .placement_models import ChecklistProgress, ContestParticipation, ProjectNote

PUBLISHED = ContentStatus.PUBLISHED


# ============================================================ notices and contests
@login_required
def notice_list(request):
    today = timezone.localdate()
    published = NoticeContest.objects.filter(status=PUBLISHED)
    registered = set()
    if request.user.is_student:
        registered = set(
            ContestParticipation.objects.filter(user=request.user).values_list("contest_id", flat=True)
        )
    contests = list(published.filter(kind=NoticeContest.Kind.CONTEST).order_by("date", "id"))
    for contest in contests:
        contest.registered = contest.pk in registered
        contest.open = services.can_register(contest, today)
    return render(
        request,
        "content/placement/notice_list.html",
        {
            "notices": published.filter(kind=NoticeContest.Kind.NOTICE).order_by("-date", "-id")[:30],
            "upcoming": [c for c in contests if c.date >= today],
            "past": [c for c in reversed(contests) if c.date < today][:10],
            "today": today,
        },
    )


@role_required("Student")
@require_POST
def contest_register(request, pk):
    contest = get_object_or_404(NoticeContest, pk=pk, kind=NoticeContest.Kind.CONTEST, status=PUBLISHED)
    if not services.can_register(contest):
        messages.error(request, "Registration for this contest is closed.")
    else:
        _, created = ContestParticipation.objects.get_or_create(user=request.user, contest=contest)
        messages.success(request, "You are registered." if created else "You were already registered.")
    return redirect("notice_list")


@role_required("Student")
@require_POST
def contest_withdraw(request, pk):
    contest = get_object_or_404(NoticeContest, pk=pk, kind=NoticeContest.Kind.CONTEST, status=PUBLISHED)
    deleted, _ = ContestParticipation.objects.filter(user=request.user, contest=contest).delete()
    messages.success(request, "Registration withdrawn." if deleted else "You were not registered.")
    return redirect("notice_list")


@role_required("TPO", "Faculty")
def manage_notices(request):
    status = request.GET.get("status", "")
    status = status if status in ContentStatus.values else ""
    items = NoticeContest.objects.select_related("created_by").annotate(participant_count=Count("participants"))
    if status:
        items = items.filter(status=status)
    page = Paginator(items.order_by("-date", "-id"), 20).get_page(request.GET.get("page"))
    for item in page.object_list:
        item.actions = workflow.available_actions(request.user, item)
        item.editable = workflow.can_edit(request.user, item)
    return render(
        request,
        "content/placement/manage_notices.html",
        {"page": page, "status": status, "statuses": ContentStatus.choices,
         "querystring": f"status={status}" if status else ""},
    )


@role_required("TPO", "Faculty")
def notice_create(request):
    if request.method == "POST":
        form = NoticeForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.created_by = request.user
            item.status = ContentStatus.DRAFT
            item.save()
            messages.success(request, "Saved as a draft.")
            return redirect("manage_notices")
    else:
        form = NoticeForm(initial={"date": timezone.localdate()})
    return render(request, "content/form.html", {"title": "Add a notice or contest", "form": form, "cancel_url": "manage_notices"})


@role_required("TPO", "Faculty")
def notice_edit(request, pk):
    item = get_object_or_404(NoticeContest, pk=pk)
    if not workflow.can_edit(request.user, item):
        raise PermissionDenied
    if request.method == "POST":
        form = NoticeForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, "Updated.")
            return redirect("manage_notices")
    else:
        form = NoticeForm(instance=item)
    return render(request, "content/form.html", {"title": "Edit notice or contest", "form": form, "cancel_url": "manage_notices"})


@role_required("TPO", "Faculty")
@require_POST
def notice_transition(request, pk):
    item = get_object_or_404(NoticeContest, pk=pk)
    to = request.POST.get("to", "")
    outcome = workflow.check_transition(request.user, item, to)
    if outcome == "forbidden":
        raise PermissionDenied
    if outcome == "invalid":
        messages.error(request, "That change is not allowed for this item's current status.")
    else:
        item.status = to
        item.save()
        messages.success(request, f"Status changed to {item.get_status_display()}.")
    return redirect("manage_notices")


# ================================================================== applications
def _own_application(request, pk):
    return get_object_or_404(Application, pk=pk, user=request.user)


@role_required("Student")
def application_list(request):
    apps = list(Application.objects.filter(user=request.user).select_related("company").order_by("company__name"))
    for app in apps:
        app.actions = services.available_actions(app, "Student")
        app.is_final = app.application_status in services.FINAL
    return render(
        request,
        "content/placement/application_list.html",
        {
            "applications": apps,
            "form": AddApplicationForm(user=request.user),
            "eligibility_choices": Application.EligibilityStatus.choices,
        },
    )


@role_required("Student")
@require_POST
def application_add(request):
    form = AddApplicationForm(request.POST, user=request.user)
    if form.is_valid():
        Application.objects.create(user=request.user, company=form.cleaned_data["company"])
        messages.success(request, "Company added to your tracker.")
    else:
        messages.error(request, "Choose a company that is not already in your tracker.")
    return redirect("application_list")


@role_required("Student")
@require_POST
def application_track(request, company_pk):
    company = get_object_or_404(Company, pk=company_pk, status=PUBLISHED)
    _, created = Application.objects.get_or_create(user=request.user, company=company)
    messages.success(request, f"{company.name} added to your tracker." if created else f"{company.name} is already in your tracker.")
    return redirect("application_list")


@role_required("Student")
@require_POST
def application_status(request, pk):
    app = _own_application(request, pk)
    try:
        services.change_status(app, request.POST.get("to", ""), "Student")
        messages.success(request, "Status updated.")
    except services.ApplicationError as error:
        messages.error(request, str(error))
    return redirect("application_list")


@role_required("Student")
@require_POST
def application_eligibility(request, pk):
    app = _own_application(request, pk)
    try:
        services.set_eligibility(app, request.POST.get("eligibility", ""))
        messages.success(request, "Eligibility recorded.")
    except services.ApplicationError as error:
        messages.error(request, str(error))
    return redirect("application_list")


@role_required("Student")
@require_POST
def application_delete(request, pk):
    app = _own_application(request, pk)
    if app.application_status in ("interested", "eligible", "withdrawn"):
        app.delete()
        messages.success(request, "Removed from your tracker.")
    else:
        messages.error(request, "Applications you have already made cannot be removed. Withdraw it instead if you changed your mind.")
    return redirect("application_list")


@role_required("TPO")
def manage_applications(request):
    """UC-15 for the TPO: applications of students who gave consent (BR-10, BR-14)."""
    ids = services.consenting_student_ids()
    apps = Application.objects.filter(user_id__in=ids).select_related("company", "user")
    company_id, status = request.GET.get("company", ""), request.GET.get("status", "")
    if company_id.isdigit():
        apps = apps.filter(company_id=int(company_id))
    if status in Application.ApplicationStatus.values:
        apps = apps.filter(application_status=status)
    summary = OrderedDict()
    for row in Application.objects.filter(user_id__in=ids).values("company__name", "application_status").annotate(n=Count("id")).order_by("company__name"):
        summary.setdefault(row["company__name"], {})[row["application_status"]] = row["n"]
    summary_rows = []
    for name, counts in summary.items():
        summary_rows.append(
            {
                "name": name,
                "total": sum(counts.values()),
                "open": counts.get("interested", 0) + counts.get("eligible", 0),
                "applied": counts.get("applied", 0),
                "shortlisted": counts.get("shortlisted", 0),
                "selected": counts.get("selected", 0),
                "rejected": counts.get("rejected", 0),
                "withdrawn": counts.get("withdrawn", 0),
            }
        )
    page = Paginator(apps.order_by("company__name", "user__first_name", "user__username"), 25).get_page(request.GET.get("page"))
    for app in page.object_list:
        app.actions = services.available_actions(app, "TPO")
    total_students = User.objects.filter(role__role_name="Student").count()
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "content/placement/manage_applications.html",
        {
            "page": page,
            "summary": summary_rows,
            "status_choices": Application.ApplicationStatus.choices,
            "companies": Company.objects.filter(applications__user_id__in=ids).distinct().order_by("name"),
            "company_id": company_id,
            "status": status,
            "consenting": len(ids),
            "total_students": total_students,
            "querystring": params.urlencode(),
        },
    )


@role_required("TPO")
@require_POST
def manage_application_status(request, pk):
    app = get_object_or_404(Application, pk=pk, user_id__in=services.consenting_student_ids())
    try:
        services.change_status(app, request.POST.get("to", ""), "TPO")
        messages.success(request, "Status updated.")
    except services.ApplicationError as error:
        messages.error(request, str(error))
    return redirect(request.POST.get("next") if request.POST.get("next", "").startswith("/manage/applications/") else "manage_applications")


# ================================================================ preparation pages
@role_required("Student")
def prepare_home(request):
    done = ChecklistProgress.objects.filter(user=request.user).count()
    projects = request.user.project_achievements.filter(type="project").count()
    return render(
        request,
        "content/placement/prepare_home.html",
        {
            "checklist_done": done,
            "checklist_total": len(services.RESUME_CHECKLIST),
            "project_count": projects,
            "interview_count": Question.objects.filter(type="interview", status=PUBLISHED).count(),
        },
    )


@login_required
def interview_prep(request):
    """UC-11: guidance and the approved interview questions, with model answers."""
    questions = Question.objects.filter(type="interview", status=PUBLISHED).select_related("topic").order_by(
        "topic__subject", "topic__name", "id"
    )
    groups = OrderedDict()
    for question in questions:
        groups.setdefault(question.topic, []).append(question)
    return render(request, "content/placement/interview_prep.html", {"groups": list(groups.items()), "total": len(questions)})


@role_required("Student")
def resume_checklist(request):
    keys = [key for key, _, _ in services.RESUME_CHECKLIST]
    if request.method == "POST":
        selected = {key for key in keys if request.POST.get(f"item_{key}")}
        ChecklistProgress.objects.filter(user=request.user).exclude(key__in=selected).delete()
        ChecklistProgress.objects.bulk_create(
            [ChecklistProgress(user=request.user, key=key) for key in selected], ignore_conflicts=True
        )
        messages.success(request, "Checklist saved.")
        return redirect("resume_checklist")
    done = set(ChecklistProgress.objects.filter(user=request.user).values_list("key", flat=True))
    items = [{"key": k, "title": t, "help": h, "done": k in done} for k, t, h in services.RESUME_CHECKLIST]
    count = sum(1 for item in items if item["done"])
    return render(
        request,
        "content/placement/resume_checklist.html",
        {"items": items, "done": count, "total": len(items), "percent": round(100 * count / len(items))},
    )


@role_required("Student")
def project_list(request):
    total = len(services.PROJECT_PROMPTS)
    projects = list(request.user.project_achievements.filter(type="project").annotate(answered=Count("notes")))
    return render(request, "content/placement/project_list.html", {"projects": projects, "total": total})


@role_required("Student")
def project_prepare(request, pk):
    project = get_object_or_404(ProjectAchievement, pk=pk, user=request.user, type="project")
    notes = {n.prompt_key: n.text for n in project.notes.all()}
    if request.method == "POST":
        form = ProjectPromptsForm(request.POST)
        if form.is_valid():
            for key, _ in services.PROJECT_PROMPTS:
                text = form.cleaned_data[key].strip()
                if text:
                    ProjectNote.objects.update_or_create(project=project, prompt_key=key, defaults={"text": text})
                else:
                    ProjectNote.objects.filter(project=project, prompt_key=key).delete()
            messages.success(request, "Your answers are saved. Practise saying them out loud.")
            return redirect("project_prepare", pk=pk)
    else:
        form = ProjectPromptsForm(initial=notes)
    return render(request, "content/placement/project_prepare.html", {"project": project, "form": form})
