"""TPO reports. Privacy (BR-10, BR-14): only students who gave consent are included,
and everything is read-only. Exact access rules still need validating with the TPO."""
import csv
from collections import Counter, defaultdict
from datetime import timedelta

from django.utils import timezone

from accounts.models import StudentProfile, User
from planning.models import WeeklyGoal

from . import services

INACTIVE_AFTER_DAYS = 14


def has_consent(user):
    return StudentProfile.objects.filter(user=user, consent_given=True).exists()


def cohort_report(now=None):
    now = now or timezone.now()
    current_week = services.monday_of(timezone.localtime(now).date())
    students = User.objects.filter(role__role_name="Student")
    consenting_ids = set(
        StudentProfile.objects.filter(consent_given=True, user__in=students).values_list("user_id", flat=True)
    )
    users = list(students.filter(id__in=consenting_ids).order_by("first_name", "last_name", "username"))

    by_user = defaultdict(list)
    for response in services.finished_responses(consenting_ids):
        by_user[response.attempt.user_id].append(response)

    rows, topic_scores = [], defaultdict(list)
    for user in users:
        responses = by_user[user.id]
        topics = services.topic_breakdown(responses)
        classified = [t for t in topics if t["level_key"] != "nodata"]
        for entry in topics:
            if entry["accuracy"] is not None:
                topic_scores[entry["topic"]].append(entry["accuracy"])
        this_week = [r for r in responses if services.monday_of(services.local_day(r)) == current_week]
        rows.append(
            {
                "user": user,
                "summary": services.summarise(responses),
                "week": services.summarise(this_week),
                "weakest": classified[0]["topic"] if classified else None,
                "last_active": max((r.attempt.submitted_at for r in responses), default=None),
            }
        )

    accuracies = [row["summary"]["accuracy"] for row in rows if row["summary"]["accuracy"] is not None]
    cutoff = now - timedelta(days=INACTIVE_AFTER_DAYS)
    topic_table = [
        {"topic": topic, "students": len(scores), "average": round(sum(scores) / len(scores), 1)}
        for topic, scores in topic_scores.items()
    ]
    topic_table.sort(key=lambda r: (r["average"], r["topic"].name))
    week_goals = Counter(
        WeeklyGoal.objects.filter(
            user_id__in=consenting_ids,
            due_date__gte=current_week,
            due_date__lte=current_week + timedelta(days=6),
        ).values_list("status", flat=True)
    )
    return {
        "goals": {
            "total": sum(week_goals.values()),
            "completed": week_goals["completed"],
            "open": week_goals["planned"] + week_goals["in_progress"] + week_goals["rescheduled"],
            "missed": week_goals["missed"],
        },
        "total_students": students.count(),
        "consenting_count": len(users),
        "rows": rows,
        "average_accuracy": round(sum(accuracies) / len(accuracies), 1) if accuracies else None,
        "active_this_week": sum(1 for row in rows if row["week"]["attempts"]),
        "answered_total": sum(row["summary"]["answered"] for row in rows),
        "topic_table": topic_table,
        "inactive": [row for row in rows if row["last_active"] is None or row["last_active"] < cutoff],
        "inactive_days": INACTIVE_AFTER_DAYS,
    }


def _safe_cell(value):
    """Stop spreadsheet programs from running text such as =CMD() as a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def write_cohort_csv(response, report):
    writer = csv.writer(response)
    writer.writerow(
        ["Student", "Username", "Completed attempts", "Questions answered", "Accuracy %",
         "Study minutes", "Attempts this week", "Weakest topic", "Last active"]
    )
    for row in report["rows"]:
        summary = row["summary"]
        writer.writerow(
            [
                _safe_cell(row["user"].get_full_name() or row["user"].username),
                _safe_cell(row["user"].username),
                summary["attempts"],
                summary["answered"],
                "" if summary["accuracy"] is None else summary["accuracy"],
                summary["minutes"],
                row["week"]["attempts"],
                _safe_cell(row["weakest"].name if row["weakest"] else ""),
                timezone.localtime(row["last_active"]).strftime("%Y-%m-%d") if row["last_active"] else "",
            ]
        )
