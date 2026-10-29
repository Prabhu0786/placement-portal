import random

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import role_required
from content.models import ContentStatus, Question

from . import practice
from .forms import PracticeSetupForm
from .models import Attempt


def _own_practice_attempt(request, pk):
    return get_object_or_404(
        Attempt, pk=pk, user=request.user, attempt_type=Attempt.AttemptType.PRACTICE
    )


def _home_context(request, form):
    attempts = (
        Attempt.objects.filter(user=request.user, attempt_type=Attempt.AttemptType.PRACTICE)
        .annotate(question_count=Count("responses"))
        .order_by("-id")[:10]
    )
    return {
        "form": form,
        "attempts": attempts,
        "available": Question.objects.filter(status=ContentStatus.PUBLISHED).count(),
    }


@role_required("Student")
def practice_home(request):
    return render(request, "assessments/practice_home.html", _home_context(request, PracticeSetupForm()))


@role_required("Student")
@require_POST
def practice_start(request):
    form = PracticeSetupForm(request.POST)
    if not form.is_valid():
        return render(request, "assessments/practice_home.html", _home_context(request, form))
    data = form.cleaned_data
    questions = Question.objects.filter(status=ContentStatus.PUBLISHED)
    if data["type"]:
        questions = questions.filter(type=data["type"])
    if data["topic"]:
        questions = questions.filter(topic=data["topic"])
    if data["difficulty"]:
        questions = questions.filter(difficulty=data["difficulty"])
    if data["company"]:
        questions = questions.filter(company=data["company"])
    ids = list(questions.values_list("id", flat=True))
    if not ids:
        messages.error(request, "No published questions match those choices. Try fewer filters.")
        return redirect("practice_home")
    chosen = random.sample(ids, min(int(data["count"]), len(ids)))
    attempt = practice.start_practice(request.user, Question.objects.filter(id__in=chosen))
    return redirect("practice_session", pk=attempt.pk)


@role_required("Student")
def practice_session(request, pk):
    attempt = _own_practice_attempt(request, pk)
    if attempt.status in (Attempt.Status.EVALUATED, Attempt.Status.REVIEWED):
        return redirect("practice_result", pk=pk)
    if attempt.status != Attempt.Status.IN_PROGRESS:
        messages.error(request, "This practice session cannot be opened.")
        return redirect("practice_home")
    responses = list(attempt.responses.select_related("question__topic").order_by("id"))
    if request.method == "POST":
        answers = {r.question_id: request.POST.get(f"q_{r.question_id}", "") for r in responses}
        practice.submit_practice(attempt, answers)
        messages.success(request, "Submitted. Here is your feedback.")
        return redirect("practice_result", pk=pk)
    return render(
        request,
        "assessments/practice_session.html",
        {"attempt": attempt, "responses": responses},
    )


@role_required("Student")
def practice_result(request, pk):
    attempt = _own_practice_attempt(request, pk)
    # BR-11: feedback is released only after the attempt has been submitted and evaluated.
    if attempt.status not in (Attempt.Status.EVALUATED, Attempt.Status.REVIEWED):
        return redirect("practice_session", pk=pk)
    if attempt.status == Attempt.Status.EVALUATED:
        attempt.change_status(Attempt.Status.REVIEWED)
    responses = list(attempt.responses.select_related("question__topic").order_by("id"))
    return render(
        request,
        "assessments/practice_result.html",
        {"attempt": attempt, "responses": responses, "summary": practice.summarise(responses)},
    )
