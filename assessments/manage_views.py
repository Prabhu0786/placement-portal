"""TPO / Faculty screens for building assessments (UC-13), using the same approval workflow."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import role_required
from content import workflow
from content.models import ContentStatus

from .forms import AssessmentForm
from .models import Assessment


@role_required("TPO", "Faculty")
def manage_assessments(request):
    status = request.GET.get("status", "")
    status = status if status in ContentStatus.values else ""
    assessments = Assessment.objects.select_related("created_by").order_by("-id")
    if status:
        assessments = assessments.filter(status=status)
    page = Paginator(assessments, 20).get_page(request.GET.get("page"))
    for item in page.object_list:
        item.actions = workflow.available_actions(request.user, item)
        item.editable = workflow.can_edit(request.user, item)
        item.question_total = item.assessmentquestion_set.count()
    return render(
        request,
        "assessments/manage_assessments.html",
        {
            "page": page,
            "status": status,
            "statuses": ContentStatus.choices,
            "querystring": f"status={status}" if status else "",
        },
    )


@role_required("TPO", "Faculty")
def assessment_create(request):
    if request.method == "POST":
        form = AssessmentForm(request.POST)
        if form.is_valid():
            assessment = form.save(commit=False)
            assessment.created_by = request.user
            assessment.status = ContentStatus.DRAFT
            assessment.save()
            form.save_questions(assessment)
            messages.success(request, "Assessment saved as a draft.")
            return redirect("manage_assessments")
    else:
        form = AssessmentForm()
    return render(
        request,
        "content/form.html",
        {"title": "Create an assessment", "form": form, "cancel_url": "manage_assessments"},
    )


@role_required("TPO", "Faculty")
def assessment_edit(request, pk):
    assessment = get_object_or_404(Assessment, pk=pk)
    if not workflow.can_edit(request.user, assessment):
        raise PermissionDenied
    if request.method == "POST":
        form = AssessmentForm(request.POST, instance=assessment)
        if form.is_valid():
            form.save()
            messages.success(request, "Assessment updated.")
            return redirect("manage_assessments")
    else:
        form = AssessmentForm(instance=assessment)
    note = ""
    if form.locked:
        note = ("Students have already attempted this assessment, so its questions, marks and duration "
                "are locked. You can still change the title and type.")
    return render(
        request,
        "content/form.html",
        {"title": "Edit assessment", "form": form, "cancel_url": "manage_assessments", "note": note},
    )


@role_required("TPO", "Faculty")
@require_POST
def assessment_transition(request, pk):
    assessment = get_object_or_404(Assessment, pk=pk)
    to = request.POST.get("to", "")
    outcome = workflow.check_transition(request.user, assessment, to)
    if outcome == "forbidden":
        raise PermissionDenied
    if outcome == "invalid":
        messages.error(request, "That change is not allowed for this item's current status.")
    elif to == ContentStatus.PUBLISHED and not assessment.assessmentquestion_set.exists():
        messages.error(request, "Add at least one question before publishing.")
    else:
        assessment.status = to
        assessment.save()
        messages.success(request, f"Status changed to {assessment.get_status_display()}.")
    return redirect("manage_assessments")
