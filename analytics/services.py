"""Progress metrics (BR-8): always calculated from stored, evaluated attempts."""
from datetime import datetime, time, timedelta

from django.utils import timezone

from assessments.models import Attempt, Response

from .models import ProgressMetric


def week_bounds(moment):
    """Monday and Sunday of the week containing `moment` (in the project time zone)."""
    day = timezone.localtime(moment).date()
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def recalculate_metrics(user, moment=None):
    """Rebuild this user's per-topic metrics for the week containing `moment`.

    Accuracy uses only auto-checked (multiple-choice) answers. Topics with no
    auto-checked answers that week get no row, because an accuracy figure would be meaningless.
    """
    moment = moment or timezone.now()
    start, end = week_bounds(moment)
    low = timezone.make_aware(datetime.combine(start, time.min))
    high = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min))

    responses = Response.objects.filter(
        attempt__user=user,
        attempt__status__in=[Attempt.Status.EVALUATED, Attempt.Status.REVIEWED],
        attempt__submitted_at__gte=low,
        attempt__submitted_at__lt=high,
    ).select_related("question")

    per_topic = {}
    for response in responses:
        data = per_topic.setdefault(
            response.question.topic_id, {"auto": 0, "correct": 0, "seconds": 0, "attempts": set()}
        )
        data["seconds"] += response.time_taken_seconds
        data["attempts"].add(response.attempt_id)
        if response.is_correct is not None:
            data["auto"] += 1
            data["correct"] += 1 if response.is_correct else 0

    for topic_id, data in per_topic.items():
        if data["auto"] == 0:
            continue
        ProgressMetric.objects.update_or_create(
            user=user,
            topic_id=topic_id,
            period_start=start,
            defaults={
                "period_end": end,
                "accuracy": round(100 * data["correct"] / data["auto"], 1),
                "attempts": len(data["attempts"]),
                "time_spent_seconds": data["seconds"],
            },
        )
