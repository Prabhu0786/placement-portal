"""Progress metrics (BR-8): always calculated from stored, evaluated attempts."""
from datetime import datetime, time, timedelta

from django.utils import timezone

from assessments.models import Attempt, Response
from content.models import ContentStatus, Question

from .models import ProgressMetric

FINISHED = (Attempt.Status.EVALUATED, Attempt.Status.REVIEWED)

# How a topic is labelled. These numbers are shown to students on the Progress page (BR-13).
MIN_ANSWERS = 3      # fewer auto-checked answers than this: "Not enough data"
STRONG_AT = 75       # accuracy % at or above: Strong
DEVELOPING_AT = 50   # accuracy % at or above: Developing, below: Needs work


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


# ====================================================================== reporting
# Everything below is calculated from stored, finished attempts (BR-8).
# "Accuracy" = correct answers / auto-checked (multiple-choice) questions presented.
# An unanswered multiple-choice question counts as incorrect, exactly as in scoring.

LEVELS = {
    "strong": "Strong",
    "developing": "Developing",
    "weak": "Needs work",
    "nodata": f"Not enough data (under {MIN_ANSWERS} answers)",
}


def monday_of(day):
    return day - timedelta(days=day.weekday())


def local_day(response):
    return timezone.localtime(response.attempt.submitted_at).date()


def finished_responses(user_ids):
    return list(
        Response.objects.filter(attempt__user_id__in=list(user_ids), attempt__status__in=FINISHED)
        .select_related("attempt__assessment", "question__topic")
    )


def summarise(responses):
    auto = [r for r in responses if r.is_correct is not None]
    correct = sum(1 for r in auto if r.is_correct)
    seconds = sum(r.time_taken_seconds for r in responses)
    return {
        "attempts": len({r.attempt_id for r in responses}),
        "presented": len(responses),
        "answered": sum(1 for r in responses if (r.answer or "").strip()),
        "auto": len(auto),
        "correct": correct,
        "accuracy": round(100 * correct / len(auto), 1) if auto else None,
        "seconds": seconds,
        "minutes": round(seconds / 60),
    }


def level_for(accuracy, auto):
    if accuracy is None or auto < MIN_ANSWERS:
        return "nodata"
    if accuracy >= STRONG_AT:
        return "strong"
    if accuracy >= DEVELOPING_AT:
        return "developing"
    return "weak"


def topic_breakdown(responses):
    """One row per topic, weakest first; topics without enough data come last."""
    grouped = {}
    for response in responses:
        grouped.setdefault(response.question.topic, []).append(response)
    rows = []
    for topic, items in grouped.items():
        data = summarise(items)
        key = level_for(data["accuracy"], data["auto"])
        rows.append({"topic": topic, **data, "level_key": key, "level_label": LEVELS[key]})
    rows.sort(
        key=lambda r: (
            r["level_key"] == "nodata",
            r["accuracy"] if r["accuracy"] is not None else 101,
            r["topic"].name,
        )
    )
    return rows


def weekly_series(responses, weeks=8, now=None):
    """Oldest to newest list of per-week summaries ending with the current week."""
    now = now or timezone.now()
    current = monday_of(timezone.localtime(now).date())
    starts = [current - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    buckets = {start: [] for start in starts}
    for response in responses:
        week = monday_of(local_day(response))
        if week in buckets:
            buckets[week].append(response)
    series = []
    for start in starts:
        data = summarise(buckets[start])
        data.update(start=start, end=start + timedelta(days=6), label=start.strftime("%d %b"))
        series.append(data)
    return series


def trend_chart(series):
    """Coordinates for a simple SVG line chart (weekly accuracy, 0-100%)."""
    width, height, left, right, top, bottom = 640, 220, 48, 16, 16, 40
    plot_w, plot_h = width - left - right, height - top - bottom
    step = plot_w / (len(series) - 1) if len(series) > 1 else 0

    def x(index):
        return left + index * step

    def y(percent):
        return top + plot_h * (1 - percent / 100)

    dots = [
        {"x": f"{x(i):.1f}", "y": f"{y(p['accuracy']):.1f}", "label": p["label"], "value": p["accuracy"]}
        for i, p in enumerate(series)
        if p["accuracy"] is not None
    ]
    return {
        "width": width,
        "height": height,
        "left": left,
        "right": width - right,
        "label_y": height - 14,
        "text_x": left - 6,
        "has_data": bool(dots),
        "points": " ".join(f"{d['x']},{d['y']}" for d in dots),
        "dots": dots,
        "labels": [{"x": f"{x(i):.1f}", "text": p["label"]} for i, p in enumerate(series)],
        "grid": [{"y": f"{y(v):.1f}", "text": f"{v}%"} for v in (0, 25, 50, 75, 100)],
    }


def available_topic_count():
    """Topics that have at least one published multiple-choice question to practise."""
    return (
        Question.objects.filter(status=ContentStatus.PUBLISHED)
        .exclude(options=[])
        .values("topic")
        .distinct()
        .count()
    )


def readiness(summary, topics, available, series):
    """A plain, rule-based preparation indicator (BR-13). It describes practice so far;
    it does NOT predict placement results."""
    covered = sum(1 for t in topics if t["auto"] >= MIN_ANSWERS)
    coverage = round(100 * covered / available) if available else 0
    consistency = sum(1 for week in series[-4:] if week["attempts"])
    accuracy = summary["accuracy"]
    if summary["auto"] < 10 or accuracy is None:
        label = "Getting started"
    elif accuracy >= 75 and coverage >= 60:
        label = "Strong"
    elif accuracy >= 50 and coverage >= 30:
        label = "Developing"
    else:
        label = "Needs more practice"
    return {
        "label": label,
        "accuracy": accuracy,
        "coverage": coverage,
        "covered": covered,
        "available": available,
        "consistency": consistency,
    }


def student_overview(user, now=None):
    responses = finished_responses([user.id])
    summary = summarise(responses)
    topics = topic_breakdown(responses)
    series = weekly_series(responses, now=now)
    return {
        "has_data": bool(responses),
        "summary": summary,
        "topics": topics,
        "series": series,
        "chart": trend_chart(series),
        "readiness": readiness(summary, topics, available_topic_count(), series),
    }


def week_report(user, start, now=None):
    """The weekly report for the week beginning on Monday `start`."""
    responses = finished_responses([user.id])
    this_week = [r for r in responses if monday_of(local_day(r)) == start]
    last_week = [r for r in responses if monday_of(local_day(r)) == start - timedelta(days=7)]
    summary, previous = summarise(this_week), summarise(last_week)
    topics = topic_breakdown(this_week)
    attempts = {}
    for response in this_week:
        attempts[response.attempt_id] = response.attempt
    finished = sorted(attempts.values(), key=lambda a: a.submitted_at)
    change = None
    if summary["accuracy"] is not None and previous["accuracy"] is not None:
        change = round(summary["accuracy"] - previous["accuracy"], 1)
    return {
        "start": start,
        "end": start + timedelta(days=6),
        "summary": summary,
        "previous": previous,
        "change": change,
        "topics": topics,
        "needs_work": [t for t in topics if t["accuracy"] is not None and t["accuracy"] < DEVELOPING_AT],
        "doing_well": [t for t in topics if t["accuracy"] is not None and t["accuracy"] >= STRONG_AT],
        "attempts": [
            {
                "title": a.assessment.title if a.assessment_id else "Practice session",
                "when": a.submitted_at,
                "score": a.score,
                "timed_out": a.timed_out,
                "is_assessment": bool(a.assessment_id),
                "pk": a.pk,
            }
            for a in finished
        ],
    }
