import random

from django.contrib import messages
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.permissions import role_required
from content.models import ContentStatus, Question

from . import practice, services
from .forms import PracticeSetupForm
from .models import Assessment, Attempt


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
    form = PracticeSetupForm(initial={"topic": request.GET.get("topic") or None})
    return render(request, "assessments/practice_home.html", _home_context(request, form))


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


# ============================================================ timed assessments
PUBLISHED = ContentStatus.PUBLISHED
ASSESSMENT = Attempt.AttemptType.ASSESSMENT


def _own_assessment_attempt(request, pk):
    return get_object_or_404(
        Attempt.objects.select_related("assessment"),
        pk=pk,
        user=request.user,
        attempt_type=ASSESSMENT,
    )


@role_required("Student")
def assessment_list(request):
    """Step 1 of the timed-assessment flow: choose an available assessment."""
    services.finalize_expired_attempts(request.user)  # time out anything left unfinished
    assessments = list(
        Assessment.objects.filter(status=PUBLISHED)
        .annotate(question_count=Count("assessmentquestion"))
        .filter(question_count__gt=0)
        .order_by("title")
    )
    attempts = list(
        Attempt.objects.filter(user=request.user, attempt_type=ASSESSMENT)
        .select_related("assessment")
        .order_by("-id")
    )
    active = {a.assessment_id: a for a in attempts if a.status == Attempt.Status.IN_PROGRESS}
    counts = {}
    for attempt in attempts:
        counts[attempt.assessment_id] = counts.get(attempt.assessment_id, 0) + 1
    rows = [
        {"assessment": a, "active": active.get(a.id), "attempts": counts.get(a.id, 0)}
        for a in assessments
    ]
    finished = [a for a in attempts if a.status in (Attempt.Status.EVALUATED, Attempt.Status.REVIEWED)]
    return render(
        request,
        "assessments/assessment_list.html",
        {"rows": rows, "history": finished[:15]},
    )


@role_required("Student")
@require_POST
def assessment_start(request, pk):
    # Access check: only published assessments can be started (BR-4).
    assessment = get_object_or_404(Assessment, pk=pk, status=PUBLISHED)
    if not assessment.assessmentquestion_set.exists():
        messages.error(request, "This assessment has no questions yet.")
        return redirect("assessment_list")
    attempt, _ = services.start_assessment_attempt(request.user, assessment)
    return redirect("attempt_take", pk=attempt.pk)


@role_required("Student")
def attempt_take(request, pk):
    attempt = _own_assessment_attempt(request, pk)
    if attempt.status == Attempt.Status.IN_PROGRESS and services.is_expired(attempt):
        services.finish_attempt(attempt)
        messages.info(request, "The time limit has passed. Your saved answers were scored.")
        return redirect("attempt_result", pk=pk)
    if attempt.status != Attempt.Status.IN_PROGRESS:
        return redirect("attempt_result", pk=pk)
    return render(
        request,
        "assessments/attempt_take.html",
        {
            "attempt": attempt,
            "assessment": attempt.assessment,
            "rows": services.question_rows(attempt),
            "remaining": services.remaining_seconds(attempt),
        },
    )


@role_required("Student")
@require_POST
def attempt_save(request, pk):
    """Autosave one answer (called by the page as the student answers)."""
    attempt = _own_assessment_attempt(request, pk)
    try:
        question_id = int(request.POST.get("question_id", ""))
    except ValueError:
        return JsonResponse({"saved": False, "error": "Invalid question."}, status=400)
    outcome = services.autosave_answer(attempt, question_id, request.POST.get("answer", ""))
    if outcome == "saved":
        attempt.refresh_from_db()
        return JsonResponse({"saved": True, "remaining": services.remaining_seconds(attempt)})
    if outcome in ("expired", "closed"):
        return JsonResponse(
            {"saved": False, "expired": True, "redirect": reverse("attempt_result", args=[pk])},
            status=409,
        )
    return JsonResponse({"saved": False, "error": "Unknown question."}, status=400)


@role_required("Student")
@require_POST
def attempt_submit(request, pk):
    attempt = _own_assessment_attempt(request, pk)
    if attempt.status == Attempt.Status.IN_PROGRESS:
        answers = {}
        for key, value in request.POST.items():
            if key.startswith("q_") and key[2:].isdigit():
                answers[int(key[2:])] = value
        attempt = services.finish_attempt(attempt, answers)
        if attempt.timed_out:
            messages.info(request, "The time limit had passed, so your saved answers were scored.")
        else:
            messages.success(request, "Assessment submitted.")
    return redirect("attempt_result", pk=pk)


@role_required("Student")
def attempt_result(request, pk):
    attempt = _own_assessment_attempt(request, pk)
    if attempt.status == Attempt.Status.IN_PROGRESS:
        if not services.is_expired(attempt):
            # BR-11: no feedback while the attempt is still open.
            return redirect("attempt_take", pk=pk)
        services.finish_attempt(attempt)
        attempt.refresh_from_db()
    if attempt.status not in (Attempt.Status.EVALUATED, Attempt.Status.REVIEWED):
        return redirect("assessment_list")
    if attempt.status == Attempt.Status.EVALUATED:
        attempt.change_status(Attempt.Status.REVIEWED)
    rows = services.question_rows(attempt)
    return render(
        request,
        "assessments/attempt_result.html",
        {
            "attempt": attempt,
            "assessment": attempt.assessment,
            "rows": rows,
            "summary": services.assessment_summary(attempt, rows),
        },
    )
