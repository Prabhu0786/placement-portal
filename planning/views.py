from datetime import date

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import role_required

from . import services
from .forms import GoalForm
from .models import WeeklyGoal


@role_required("Student")
def recommendations(request):
    """UC-09: suggested topics, each with the reason it was suggested (BR-9)."""
    items = services.current_recommendations(request.user)
    return render(
        request,
        "planning/recommendations.html",
        {"items": items, "starting": services.is_starting(request.user), "threshold": services.STARTING_THRESHOLD},
    )


@role_required("Student")
def plan(request):
    """UC-10: the weekly plan."""
    return render(request, "planning/plan.html", services.plan_for(request.user))


@role_required("Student")
def goal_create(request):
    if request.method == "POST":
        form = GoalForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            services.sync_goals(request.user)
            messages.success(request, "Goal added to your plan.")
            return redirect("plan")
    else:
        form = GoalForm(
            user=request.user,
            initial={
                "due_date": services.end_of_week(),
                "target": 5,
                "topic": request.GET.get("topic") or None,
            },
        )
    return render(
        request,
        "content/form.html",
        {"title": "Add a weekly goal", "form": form, "cancel_url": "plan"},
    )


def _own_goal(request, pk):
    return get_object_or_404(WeeklyGoal, pk=pk, user=request.user)


@role_required("Student")
@require_POST
def goal_status(request, pk):
    goal = _own_goal(request, pk)
    try:
        services.change_goal_status(goal, request.POST.get("to", ""))
        messages.success(request, "Goal updated.")
    except services.GoalError as error:
        messages.error(request, str(error))
    services.sync_goals(request.user)
    return redirect("plan")


@role_required("Student")
@require_POST
def goal_reschedule(request, pk):
    goal = _own_goal(request, pk)
    try:
        new_due = date.fromisoformat(request.POST.get("due_date", ""))
        services.reschedule_goal(goal, new_due)
        messages.success(request, f"Goal moved to {new_due:%d %b %Y}.")
    except ValueError as error:  # also covers GoalError and a badly typed date
        messages.error(request, str(error) if isinstance(error, services.GoalError) else "Please choose a valid date.")
    services.sync_goals(request.user)
    return redirect("plan")


@role_required("Student")
@require_POST
def goal_delete(request, pk):
    _own_goal(request, pk).delete()
    messages.success(request, "Goal removed.")
    return redirect("plan")
