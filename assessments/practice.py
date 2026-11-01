"""Practice-session logic. Every session is stored as an Attempt with Responses (BR-5)."""
from django.db import transaction
from django.utils import timezone

from . import services
from .models import Attempt, Response


def start_practice(user, questions):
    """Create a practice Attempt (Created -> In progress) with one empty Response per question."""
    with transaction.atomic():
        attempt = Attempt.objects.create(user=user, attempt_type=Attempt.AttemptType.PRACTICE)
        Response.objects.bulk_create([Response(attempt=attempt, question=q) for q in questions])
        attempt.started_at = timezone.now()
        attempt.save(update_fields=["started_at"])
        attempt.change_status(Attempt.Status.IN_PROGRESS)
    return attempt


def submit_practice(attempt, answers):
    """Save answers, evaluate them and move the attempt Submitted -> Evaluated.

    answers: {question_id: answer text}. Does nothing unless the attempt is In progress (BR-7).
    """
    if attempt.status != Attempt.Status.IN_PROGRESS:
        return False
    services.finish_attempt(attempt, answers)
    return True


def summarise(responses):
    """Numbers and weak topics for the practice result page."""
    auto = [r for r in responses if r.is_correct is not None]
    correct = sum(1 for r in auto if r.is_correct)
    weak = []
    for r in auto:
        if not r.is_correct and r.question.topic not in weak:
            weak.append(r.question.topic)
    return {
        "auto_total": len(auto),
        "auto_correct": correct,
        "percent": round(100 * correct / len(auto)) if auto else None,
        "manual_total": len(responses) - len(auto),
        "weak_topics": weak,
    }
