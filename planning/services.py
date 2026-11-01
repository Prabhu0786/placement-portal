"""Recommendations and weekly goals (UC-09, UC-10).

Recommendations are rule-based and every one carries a visible reason (BR-9).
A student with too little history gets general starting suggestions instead (BR-12).
Nothing here is a prediction: it only reads the student's own finished attempts.
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from analytics import services as analytics
from content.models import ContentStatus, Question, Topic

from .models import Recommendation, WeeklyGoal

STARTING_THRESHOLD = 10   # scored answers needed before personal recommendations begin
STARTER_COUNT = 3
MAX_RECOMMENDATIONS = 5
DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}

Status = WeeklyGoal.Status
ACTIVE_STATUSES = (Status.PLANNED, Status.IN_PROGRESS, Status.RESCHEDULED)

# Goal state machine (from the state diagram). "Due date passes" is applied by sync_goals().
TRANSITIONS = {
    "planned": {"in_progress", "completed", "rescheduled"},
    "in_progress": {"completed", "rescheduled"},
    "rescheduled": {"in_progress", "completed", "rescheduled"},
    "missed": {"rescheduled"},
    "completed": set(),
}
ACTION_LABELS = {"in_progress": "Start", "completed": "Mark as done"}


class GoalError(ValueError):
    pass


# ============================================================== recommendations
def practice_topics():
    """Topics that have at least one published question to practise."""
    ids = Question.objects.filter(status=ContentStatus.PUBLISHED).values_list("topic_id", flat=True)
    return list(Topic.objects.filter(id__in=set(ids)))


def _topic_order(topic):
    return (DIFFICULTY_ORDER.get(topic.difficulty, 1), topic.subject, topic.name)


def is_starting(user):
    """True when the student has too few scored answers for personal recommendations (BR-12)."""
    return analytics.summarise(analytics.finished_responses([user.id]))["auto"] < STARTING_THRESHOLD


def build_recommendations(user):
    """Return [{'topic', 'reason'}] in priority order, using only the documented rules."""
    responses = analytics.finished_responses([user.id])
    topics = practice_topics()
    if analytics.summarise(responses)["auto"] < STARTING_THRESHOLD:
        starters = sorted(topics, key=_topic_order)[:STARTER_COUNT]
        return [
            {
                "topic": topic,
                "reason": (
                    f"You are just getting started, so begin with a {topic.get_difficulty_display().lower()} "
                    f"topic. {topic.name} is a good first step."
                ),
            }
            for topic in starters
        ]

    rows = {row["topic"].id: row for row in analytics.topic_breakdown(responses)}
    weak, developing, uncovered = [], [], []
    for topic in topics:
        row = rows.get(topic.id)
        if row is None:
            uncovered.append((topic, f"You have not practised {topic.name} yet. Try a short session to see where you stand."))
        elif row["level_key"] == "weak":
            weak.append((row["accuracy"], topic, (
                f"Your accuracy in {topic.name} is {row['accuracy']:.0f}% over {row['auto']} scored answers, "
                f"below {analytics.DEVELOPING_AT}%. Extra practice here will help most."
            )))
        elif row["level_key"] == "developing":
            developing.append((row["accuracy"], topic, (
                f"Your accuracy in {topic.name} is {row['accuracy']:.0f}%. "
                f"A little more practice can take it above {analytics.STRONG_AT}%."
            )))
        elif row["level_key"] == "nodata":
            uncovered.append((topic, (
                f"You have answered fewer than {analytics.MIN_ANSWERS} scored questions in {topic.name}, "
                "so there is not enough data yet. Try a short session."
            )))
        # strong topics are not recommended

    ordered = [(t, r) for _, t, r in sorted(weak, key=lambda x: (x[0], x[1].name))]
    ordered += [(t, r) for _, t, r in sorted(developing, key=lambda x: (x[0], x[1].name))]
    ordered += sorted(uncovered, key=lambda x: _topic_order(x[0]))
    return [{"topic": t, "reason": r} for t, r in ordered[:MAX_RECOMMENDATIONS]]


def refresh_recommendations(user):
    """Replace the student's recommendations with a freshly calculated set."""
    items = build_recommendations(user)
    with transaction.atomic():
        Recommendation.objects.filter(user=user).delete()
        Recommendation.objects.bulk_create(
            [
                Recommendation(user=user, topic=item["topic"], reason=item["reason"][:300], priority=index)
                for index, item in enumerate(items, start=1)
            ]
        )
    return items


def current_recommendations(user, today=None):
    """Stored recommendations, recalculated first if there are none or they are from an earlier day."""
    today = today or timezone.localdate()
    stored = list(Recommendation.objects.filter(user=user).select_related("topic"))
    stale = not stored or any(r.date < today for r in stored)
    if stale:
        refresh_recommendations(user)
        stored = list(Recommendation.objects.filter(user=user).select_related("topic"))
    return stored


# ================================================================== weekly goals
def end_of_week(today=None):
    today = today or timezone.localdate()
    return today + timedelta(days=6 - today.weekday())


def goal_window(goal):
    """Questions count if answered during the 7 days up to and including the due date."""
    return goal.due_date - timedelta(days=6), goal.due_date


def goal_progress(goal, responses):
    start, end = goal_window(goal)
    return sum(
        1
        for r in responses
        if r.question.topic_id == goal.topic_id
        and (r.answer or "").strip()
        and start <= analytics.local_day(r) <= end
    )


def sync_goals(user, today=None):
    """Apply the automatic transitions: progress reached target -> Completed, due date passed -> Missed,
    some progress -> In progress. Returns the number of goals that changed."""
    today = today or timezone.localdate()
    goals = list(WeeklyGoal.objects.filter(user=user, status__in=ACTIVE_STATUSES).select_related("topic"))
    if not goals:
        return 0
    responses = analytics.finished_responses([user.id])
    changed = 0
    for goal in goals:
        progress = goal_progress(goal, responses)
        new = None
        if progress >= goal.target:
            new = Status.COMPLETED
        elif goal.due_date < today:
            new = Status.MISSED
        elif progress > 0 and goal.status != Status.IN_PROGRESS:
            new = Status.IN_PROGRESS
        if new is not None and new != goal.status:
            goal.status = new
            goal.save(update_fields=["status"])
            changed += 1
    return changed


def change_goal_status(goal, to):
    """Student actions Start and Mark as done."""
    if to == Status.RESCHEDULED or to not in TRANSITIONS[goal.status]:
        raise GoalError("That change is not allowed for this goal.")
    goal.status = to
    goal.save(update_fields=["status"])


def reschedule_goal(goal, new_due, today=None):
    today = today or timezone.localdate()
    if "rescheduled" not in TRANSITIONS[goal.status]:
        raise GoalError("This goal can no longer be rescheduled.")
    if new_due < today:
        raise GoalError("Choose today or a later date.")
    goal.due_date = new_due
    goal.status = Status.RESCHEDULED
    goal.save(update_fields=["due_date", "status"])


def goal_actions(goal):
    return [(to, ACTION_LABELS[to]) for to in ("in_progress", "completed") if to in TRANSITIONS[goal.status]]


def plan_for(user, today=None):
    """Goals with progress figures for the plan page, split into groups."""
    today = today or timezone.localdate()
    sync_goals(user, today)
    goals = list(WeeklyGoal.objects.filter(user=user).select_related("topic"))
    responses = analytics.finished_responses([user.id]) if goals else []
    for goal in goals:
        goal.progress = goal_progress(goal, responses)
        goal.percent = min(100, round(100 * goal.progress / goal.target)) if goal.target else 0
        goal.actions = goal_actions(goal)
        goal.can_reschedule = "rescheduled" in TRANSITIONS[goal.status]
        goal.days_left = (goal.due_date - today).days
    return {
        "active": [g for g in goals if g.status in ACTIVE_STATUSES],
        "missed": [g for g in goals if g.status == Status.MISSED],
        "completed": sorted((g for g in goals if g.status == Status.COMPLETED), key=lambda g: g.due_date, reverse=True)[:10],
    }


def reminders(user, today=None):
    """In-portal reminders: goals due within 2 days, and goals missed in the last 7 days."""
    today = today or timezone.localdate()
    sync_goals(user, today)
    items = []
    goals = WeeklyGoal.objects.filter(user=user).select_related("topic")
    for goal in goals.filter(status__in=ACTIVE_STATUSES, due_date__lte=today + timedelta(days=2)).order_by("due_date"):
        days = (goal.due_date - today).days
        when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
        items.append({"kind": "due", "goal": goal, "text": f"Goal due {when}: {goal.target} questions in {goal.topic.name}."})
    for goal in goals.filter(status=Status.MISSED, due_date__gte=today - timedelta(days=7)).order_by("-due_date"):
        items.append({"kind": "missed", "goal": goal, "text": f"Missed: {goal.target} questions in {goal.topic.name}. You can reschedule it."})
    return items


def after_attempt(user):
    """Called whenever an attempt has been evaluated (step 9 of the preparation cycle)."""
    sync_goals(user)
    refresh_recommendations(user)
