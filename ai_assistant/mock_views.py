from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import role_required
from content.models import ContentStatus, Question

from . import mock_services as services
from .mock_forms import MockSetupForm
from .mock_models import MockInterview, MockInterviewTurn


def _own_interview(request, pk):
    return get_object_or_404(MockInterview, pk=pk, user=request.user)


def _home_context(request, form):
    return {
        "consent": services.has_ai_consent(request.user),
        "form": form,
        "history": MockInterview.objects.filter(user=request.user)[:10],
        "used_today": services.interviews_today(request.user),
        "limit": services.MAX_INTERVIEWS_PER_DAY,
        "bank_count": Question.objects.filter(type="interview", status=ContentStatus.PUBLISHED).count(),
        "min_chars": services.MIN_ANSWER_CHARS,
    }


@role_required("Student")
def mock_home(request):
    return render(request, "ai_assistant/mock_home.html", _home_context(request, MockSetupForm()))


@role_required("Student")
@require_POST
def mock_consent(request):
    action = request.POST.get("action")
    if action == "grant":
        if request.POST.get("agree") != "on":
            messages.error(request, "Please tick the box to give your consent.")
        else:
            services.set_ai_consent(request.user, True)
            messages.success(request, "Thank you. AI feedback is now switched on for you.")
    elif action == "withdraw":
        services.set_ai_consent(request.user, False)
        messages.success(request, "Consent withdrawn. Nothing more will be sent to the AI service.")
    return redirect("ai_mock_home")


@role_required("Student")
@require_POST
def mock_start(request):
    form = MockSetupForm(request.POST)
    if not form.is_valid():
        return render(request, "ai_assistant/mock_home.html", _home_context(request, form))
    data = form.cleaned_data
    try:
        interview = services.start_interview(
            request.user,
            source=data["source"],
            topic=data["topic"],
            ai_type=data["ai_type"],
            difficulty=data["difficulty"],
            target_role=data["target_role"],
            count=int(data["count"]),
        )
    except services.MockInterviewError as error:
        messages.error(request, str(error))
        return redirect("ai_mock_home")
    return redirect("ai_mock_run", pk=interview.pk)


@role_required("Student")
def mock_run(request, pk):
    interview = _own_interview(request, pk)
    if interview.status == MockInterview.Status.COMPLETED:
        return redirect("ai_mock_report", pk=pk)
    turns = list(interview.turns.all())
    current = next((t for t in turns if not t.answered_at), None)
    if current is None:  # everything answered but not yet closed
        services.finish_if_done(interview)
        return redirect("ai_mock_report", pk=pk)

    draft = ""
    if request.method == "POST":
        if request.POST.get("turn") != str(current.pk):
            messages.error(request, "That question was already answered. Here is the next one.")
            return redirect("ai_mock_run", pk=pk)
        draft = request.POST.get("answer", "")
        try:
            services.submit_answer(current, draft)
        except services.MockInterviewError as error:
            messages.error(request, str(error))
        else:
            interview.refresh_from_db()
            if interview.status == MockInterview.Status.COMPLETED:
                return redirect("ai_mock_report", pk=pk)
            return redirect("ai_mock_run", pk=pk)

    return render(
        request,
        "ai_assistant/mock_run.html",
        {
            "interview": interview,
            "answered": [t for t in turns if t.answered_at],
            "current": current,
            "draft": draft,
            "min_chars": services.MIN_ANSWER_CHARS,
            "max_chars": services.MAX_ANSWER_CHARS,
            "rating_labels": services.RATING_LABELS,
        },
    )


@role_required("Student")
def mock_report(request, pk):
    interview = _own_interview(request, pk)
    if interview.status != MockInterview.Status.COMPLETED:
        return redirect("ai_mock_run", pk=pk)
    return render(
        request,
        "ai_assistant/mock_report.html",
        {
            "interview": interview,
            "turns": list(interview.turns.all()),
            "narrative": (interview.summary or {}).get("narrative", {}),
            "summary_source": (interview.summary or {}).get("source", "local"),
            "rating_labels": services.RATING_LABELS,
        },
    )


@role_required("Student")
@require_POST
def mock_retry(request, pk):
    turn = get_object_or_404(
        MockInterviewTurn.objects.select_related("interview"), pk=pk, interview__user=request.user
    )
    try:
        if services.retry_feedback(turn):
            messages.success(request, "Feedback received.")
        else:
            messages.error(request, "Feedback is still unavailable. Please try again in a little while.")
    except services.MockInterviewError as error:
        messages.error(request, str(error))
    target = "ai_mock_report" if turn.interview.status == MockInterview.Status.COMPLETED else "ai_mock_run"
    return redirect(target, pk=turn.interview_id)


@role_required("Student")
@require_POST
def mock_delete(request, pk):
    _own_interview(request, pk).delete()
    messages.success(request, "Interview deleted.")
    return redirect("ai_mock_home")


@role_required("Student")
@require_POST
def mock_delete_all(request):
    deleted, _ = MockInterview.objects.filter(user=request.user).delete()
    messages.success(request, "All your mock interviews were deleted." if deleted else "There was nothing to delete.")
    return redirect("ai_mock_home")
