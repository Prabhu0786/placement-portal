"""Attempt life-cycle for practice sessions and timed assessments.

State flow (BR-7: never backwards):
  Created -> In progress -> Submitted | Timed out -> Evaluated -> Reviewed

The deadline (expires_at) is checked on the SERVER every time, so refreshing the page,
changing the browser clock or switching off JavaScript cannot extend the time.
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from analytics.services import recalculate_metrics

from .evaluation import evaluate
from .models import Attempt, Response

MAX_ANSWER_LENGTH = 5000


# ------------------------------------------------------------------ time helpers
def is_expired(attempt, now=None):
    return attempt.expires_at is not None and (now or timezone.now()) > attempt.expires_at


def remaining_seconds(attempt, now=None):
    if attempt.expires_at is None:
        return None
    return max(0, int((attempt.expires_at - (now or timezone.now())).total_seconds()))


# --------------------------------------------------------------------- starting
def start_assessment_attempt(user, assessment):
    """Return (attempt, created). Resumes an active attempt instead of starting a second one."""
    with transaction.atomic():
        active = Attempt.objects.filter(
            user=user, assessment=assessment, status=Attempt.Status.IN_PROGRESS
        ).first()
        if active is not None:
            if not is_expired(active):
                return active, False
            finish_attempt(active)  # the old one ran out of time; close it before retaking

        links = list(
            assessment.assessmentquestion_set.select_related("question").order_by("display_order", "id")
        )
        now = timezone.now()
        attempt = Attempt.objects.create(
            user=user, assessment=assessment, attempt_type=Attempt.AttemptType.ASSESSMENT
        )
        Response.objects.bulk_create([Response(attempt=attempt, question=link.question) for link in links])
        attempt.started_at = now
        attempt.expires_at = now + timedelta(minutes=assessment.duration)
        attempt.save(update_fields=["started_at", "expires_at"])
        attempt.change_status(Attempt.Status.IN_PROGRESS)
    return attempt, True


# ----------------------------------------------------------------- saving answers
def autosave_answer(attempt, question_id, answer):
    """Save one answer. Returns 'saved', 'unknown', or 'expired' / 'closed' when no longer allowed."""
    with transaction.atomic():
        attempt = Attempt.objects.select_for_update(of=("self",)).get(pk=attempt.pk)
        if attempt.status != Attempt.Status.IN_PROGRESS:
            return "closed"
        if is_expired(attempt):
            finish_attempt(attempt)
            return "expired"
        updated = Response.objects.filter(attempt=attempt, question_id=question_id).update(
            answer=(answer or "").strip()[:MAX_ANSWER_LENGTH]
        )
        return "saved" if updated else "unknown"


# ---------------------------------------------------------------------- finishing
def marks_by_question(attempt):
    if attempt.assessment_id is None:
        return {}
    return {
        link.question_id: link.marks
        for link in attempt.assessment.assessmentquestion_set.all()
    }


def finish_attempt(attempt, answers=None):
    """Submit or time out an In-progress attempt, then evaluate it.

    * Before the deadline: posted answers are saved and the attempt is Submitted.
    * After the deadline: posted answers are IGNORED; the attempt is Timed out and is
      scored from the answers already saved (BR-6).
    Calling this on an attempt that is not In progress does nothing (BR-7).
    """
    with transaction.atomic():
        # of=("self",): lock only the attempt row. PostgreSQL cannot lock the optional assessment join.
        attempt = Attempt.objects.select_for_update(of=("self",)).select_related("assessment").get(pk=attempt.pk)
        if attempt.status != Attempt.Status.IN_PROGRESS:
            return attempt
        now = timezone.now()
        expired = is_expired(attempt, now)
        responses = list(attempt.responses.select_related("question"))

        if expired:
            attempt.timed_out = True
            attempt.submitted_at = attempt.expires_at  # the moment time ran out
            new_status = Attempt.Status.TIMED_OUT
        else:
            for response in responses:
                if answers and response.question_id in answers:
                    response.answer = (answers[response.question_id] or "").strip()[:MAX_ANSWER_LENGTH]
            attempt.submitted_at = now
            new_status = Attempt.Status.SUBMITTED
        attempt.save(update_fields=["timed_out", "submitted_at"])
        attempt.change_status(new_status)

        # Time is measured for the whole attempt, so each question gets an equal share.
        elapsed = max(0, int((attempt.submitted_at - attempt.started_at).total_seconds())) if attempt.started_at else 0
        share = elapsed // len(responses) if responses else 0
        marks = marks_by_question(attempt)
        total = 0.0
        for response in responses:
            response.is_correct, _ = evaluate(response.question, response.answer)
            response.marks_awarded = float(marks.get(response.question_id, 1)) if response.is_correct else 0.0
            response.time_taken_seconds = share
            total += response.marks_awarded
        Response.objects.bulk_update(
            responses, ["answer", "is_correct", "marks_awarded", "time_taken_seconds"]
        )
        attempt.score = total
        attempt.save(update_fields=["score"])
        attempt.change_status(Attempt.Status.EVALUATED)
        recalculate_metrics(attempt.user, attempt.submitted_at)
        from planning import services as planning  # imported here to avoid a circular import
        planning.after_attempt(attempt.user)
    return attempt


def finalize_expired_attempts(user=None):
    """Time out every In-progress attempt whose deadline has passed. Returns how many."""
    attempts = Attempt.objects.filter(
        status=Attempt.Status.IN_PROGRESS, expires_at__lt=timezone.now()
    )
    if user is not None:
        attempts = attempts.filter(user=user)
    count = 0
    for attempt in list(attempts):
        finish_attempt(attempt)
        count += 1
    return count


# ----------------------------------------------------------------- result helpers
def question_rows(attempt):
    """Responses in the assessment's display order, each with its possible marks."""
    marks = marks_by_question(attempt)
    order = {}
    if attempt.assessment_id:
        order = {link.question_id: link.display_order for link in attempt.assessment.assessmentquestion_set.all()}
    responses = list(attempt.responses.select_related("question__topic"))
    responses.sort(key=lambda r: (order.get(r.question_id, 0), r.id))
    return [
        {"number": index, "response": response, "marks": marks.get(response.question_id, 1)}
        for index, response in enumerate(responses, start=1)
    ]


def assessment_summary(attempt, rows):
    scored = [row for row in rows if row["response"].is_correct is not None]
    max_marks = sum(row["marks"] for row in scored)
    correct = sum(1 for row in scored if row["response"].is_correct)
    unanswered = sum(1 for row in rows if not row["response"].answer)
    weak = []
    for row in scored:
        topic = row["response"].question.topic
        if not row["response"].is_correct and topic not in weak:
            weak.append(topic)
    used = None
    if attempt.started_at and attempt.submitted_at:
        used = max(0, int((attempt.submitted_at - attempt.started_at).total_seconds()))
    return {
        "score": attempt.score or 0,
        "max_marks": max_marks,
        "percent": round(100 * (attempt.score or 0) / max_marks) if max_marks else None,
        "correct": correct,
        "scored_count": len(scored),
        "unanswered": unanswered,
        "weak_topics": weak,
        "minutes_used": used // 60 if used is not None else None,
        "seconds_used": used % 60 if used is not None else None,
    }
