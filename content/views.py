from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import role_required

from . import workflow
from .forms import CompanyForm, QuestionForm, ResourceFilterForm, ResourceForm, TopicForm
from .models import Company, ContentStatus, Question, Resource, Topic

PUBLISHED = ContentStatus.PUBLISHED


# ---------------------------------------------------------------- student pages
@login_required
def resource_list(request):
    """UC-03: browse published resources by subject, topic and difficulty (BR-4)."""
    form = ResourceFilterForm(request.GET)
    resources = (
        Resource.objects.filter(status=PUBLISHED)
        .select_related("topic", "company")
        .order_by("topic__subject", "topic__name", "title")
    )
    if form.is_valid():
        data = form.cleaned_data
        if data["q"]:
            resources = resources.filter(
                Q(title__icontains=data["q"]) | Q(source__icontains=data["q"])
            )
        if data["subject"]:
            resources = resources.filter(topic__subject=data["subject"])
        if data["topic"]:
            resources = resources.filter(topic=data["topic"])
        if data["difficulty"]:
            resources = resources.filter(topic__difficulty=data["difficulty"])
        if data["type"]:
            resources = resources.filter(type=data["type"])
    page = Paginator(resources, 10).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "content/resource_list.html",
        {"form": form, "page": page, "querystring": params.urlencode()},
    )


@login_required
def company_list(request):
    companies = Company.objects.filter(status=PUBLISHED)
    q = request.GET.get("q", "").strip()
    if q:
        companies = companies.filter(name__icontains=q)
    return render(request, "content/company_list.html", {"companies": companies, "q": q})


@login_required
def company_detail(request, pk):
    """UC-04: eligibility, stages, source, updated date, resources and previous questions."""
    company = get_object_or_404(Company, pk=pk, status=PUBLISHED)
    resources = company.resources.filter(status=PUBLISHED).select_related("topic")
    questions = company.questions.filter(status=PUBLISHED).select_related("topic")
    return render(
        request,
        "content/company_detail.html",
        {
            "company": company,
            "stages": [line.strip() for line in company.stages.splitlines() if line.strip()],
            "resources": resources,
            "questions": questions,
        },
    )


# ------------------------------------------------------------- management pages
def _annotate(items, user):
    for obj in items:
        obj.actions = workflow.available_actions(user, obj)
        obj.editable = workflow.can_edit(user, obj)
    return items


def _apply_transition(request, obj):
    to = request.POST.get("to", "")
    outcome = workflow.check_transition(request.user, obj, to)
    if outcome == "forbidden":
        raise PermissionDenied
    if outcome == "invalid":
        messages.error(request, "That change is not allowed for this item's current status.")
        return
    obj.status = to
    obj.save()
    messages.success(request, f"Status changed to {obj.get_status_display()}.")


def _status_filter(request):
    status = request.GET.get("status", "")
    return status if status in ContentStatus.values else ""


@role_required("TPO", "Faculty")
def manage_home(request):
    resource_counts = {
        row["status"]: row["n"]
        for row in Resource.objects.values("status").annotate(n=Count("id"))
    }
    company_counts = {
        row["status"]: row["n"]
        for row in Company.objects.values("status").annotate(n=Count("id"))
    }
    question_counts = {
        row["status"]: row["n"]
        for row in Question.objects.values("status").annotate(n=Count("id"))
    }
    statuses = [
        (
            value,
            label,
            resource_counts.get(value, 0),
            company_counts.get(value, 0),
            question_counts.get(value, 0),
        )
        for value, label in ContentStatus.choices
    ]
    return render(
        request,
        "content/manage_home.html",
        {
            "statuses": statuses,
            "pending_resources": resource_counts.get("pending_review", 0),
            "pending_companies": company_counts.get("pending_review", 0),
            "pending_questions": question_counts.get("pending_review", 0),
        },
    )


@role_required("TPO", "Faculty")
def manage_resources(request):
    status = _status_filter(request)
    resources = Resource.objects.select_related("topic", "created_by").order_by("-updated_at")
    if status:
        resources = resources.filter(status=status)
    page = Paginator(resources, 20).get_page(request.GET.get("page"))
    _annotate(page.object_list, request.user)
    return render(
        request,
        "content/manage_resources.html",
        {
            "page": page,
            "status": status,
            "statuses": ContentStatus.choices,
            "querystring": f"status={status}" if status else "",
        },
    )


@role_required("TPO", "Faculty")
def resource_create(request):
    if request.method == "POST":
        form = ResourceForm(request.POST)
        if form.is_valid():
            resource = form.save(commit=False)
            resource.created_by = request.user
            resource.status = ContentStatus.DRAFT
            resource.save()
            messages.success(request, "Resource saved as a draft.")
            return redirect("manage_resources")
    else:
        form = ResourceForm()
    return render(
        request,
        "content/form.html",
        {"title": "Add a resource", "form": form, "cancel_url": "manage_resources"},
    )


@role_required("TPO", "Faculty")
def resource_edit(request, pk):
    resource = get_object_or_404(Resource, pk=pk)
    if not workflow.can_edit(request.user, resource):
        raise PermissionDenied
    if request.method == "POST":
        form = ResourceForm(request.POST, instance=resource)
        if form.is_valid():
            form.save()
            messages.success(request, "Resource updated.")
            return redirect("manage_resources")
    else:
        form = ResourceForm(instance=resource)
    return render(
        request,
        "content/form.html",
        {"title": "Edit resource", "form": form, "cancel_url": "manage_resources"},
    )


@role_required("TPO", "Faculty")
@require_POST
def resource_transition(request, pk):
    _apply_transition(request, get_object_or_404(Resource, pk=pk))
    return redirect("manage_resources")


@role_required("TPO")
def manage_companies(request):
    status = _status_filter(request)
    companies = Company.objects.order_by("name")
    if status:
        companies = companies.filter(status=status)
    page = Paginator(companies, 20).get_page(request.GET.get("page"))
    _annotate(page.object_list, request.user)
    return render(
        request,
        "content/manage_companies.html",
        {
            "page": page,
            "status": status,
            "statuses": ContentStatus.choices,
            "querystring": f"status={status}" if status else "",
        },
    )


@role_required("TPO")
def company_create(request):
    if request.method == "POST":
        form = CompanyForm(request.POST)
        if form.is_valid():
            company = form.save(commit=False)
            company.status = ContentStatus.DRAFT
            company.save()
            messages.success(request, "Company saved as a draft.")
            return redirect("manage_companies")
    else:
        form = CompanyForm()
    return render(
        request,
        "content/form.html",
        {"title": "Add a company", "form": form, "cancel_url": "manage_companies"},
    )


@role_required("TPO")
def company_edit(request, pk):
    company = get_object_or_404(Company, pk=pk)
    if request.method == "POST":
        form = CompanyForm(request.POST, instance=company)
        if form.is_valid():
            form.save()
            messages.success(request, "Company updated. The updated date has been refreshed.")
            return redirect("manage_companies")
    else:
        form = CompanyForm(instance=company)
    return render(
        request,
        "content/form.html",
        {"title": "Edit company", "form": form, "cancel_url": "manage_companies"},
    )


@role_required("TPO")
@require_POST
def company_transition(request, pk):
    _apply_transition(request, get_object_or_404(Company, pk=pk))
    return redirect("manage_companies")


@role_required("TPO", "Faculty")
def manage_topics(request):
    topics = Topic.objects.annotate(resource_count=Count("resources", distinct=True))
    return render(request, "content/manage_topics.html", {"topics": topics})


@role_required("TPO", "Faculty")
def topic_create(request):
    if request.method == "POST":
        form = TopicForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Topic added.")
            return redirect("manage_topics")
    else:
        form = TopicForm()
    return render(
        request,
        "content/form.html",
        {"title": "Add a topic", "form": form, "cancel_url": "manage_topics"},
    )


@role_required("TPO", "Faculty")
def topic_edit(request, pk):
    topic = get_object_or_404(Topic, pk=pk)
    if request.method == "POST":
        form = TopicForm(request.POST, instance=topic)
        if form.is_valid():
            form.save()
            messages.success(request, "Topic updated.")
            return redirect("manage_topics")
    else:
        form = TopicForm(instance=topic)
    return render(
        request,
        "content/form.html",
        {"title": "Edit topic", "form": form, "cancel_url": "manage_topics"},
    )


@role_required("TPO", "Faculty")
def manage_questions(request):
    status = _status_filter(request)
    qtype = request.GET.get("type", "")
    questions = Question.objects.select_related("topic", "created_by").order_by("-id")
    if status:
        questions = questions.filter(status=status)
    if qtype in Question.QuestionType.values:
        questions = questions.filter(type=qtype)
    else:
        qtype = ""
    page = Paginator(questions, 20).get_page(request.GET.get("page"))
    _annotate(page.object_list, request.user)
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "content/manage_questions.html",
        {
            "page": page,
            "status": status,
            "qtype": qtype,
            "statuses": ContentStatus.choices,
            "types": Question.QuestionType.choices,
            "querystring": params.urlencode(),
        },
    )


@role_required("TPO", "Faculty")
def question_create(request):
    if request.method == "POST":
        form = QuestionForm(request.POST)
        if form.is_valid():
            question = form.save(commit=False)
            question.created_by = request.user
            question.status = ContentStatus.DRAFT
            question.save()
            messages.success(request, "Question saved as a draft.")
            return redirect("manage_questions")
    else:
        form = QuestionForm()
    return render(
        request,
        "content/form.html",
        {"title": "Add a question", "form": form, "cancel_url": "manage_questions"},
    )


@role_required("TPO", "Faculty")
def question_edit(request, pk):
    question = get_object_or_404(Question, pk=pk)
    if not workflow.can_edit(request.user, question):
        raise PermissionDenied
    if request.method == "POST":
        form = QuestionForm(request.POST, instance=question)
        if form.is_valid():
            form.save()
            messages.success(request, "Question updated.")
            return redirect("manage_questions")
    else:
        form = QuestionForm(instance=question)
    return render(
        request,
        "content/form.html",
        {"title": "Edit question", "form": form, "cancel_url": "manage_questions"},
    )


@role_required("TPO", "Faculty")
@require_POST
def question_transition(request, pk):
    _apply_transition(request, get_object_or_404(Question, pk=pk))
    return redirect("manage_questions")
