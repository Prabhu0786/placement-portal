"""Answer checking. Only multiple-choice questions are auto-evaluated.

Open questions (coding, technical, interview) are NOT scored by the system:
the student compares their answer with the model answer instead. This matches
the MVP boundary (no code execution, no voice or AI scoring).
"""


def normalise(text):
    return " ".join((text or "").split()).casefold()


def is_auto_evaluable(question):
    return bool(question.options)


def evaluate(question, answer):
    """Return (is_correct, marks). is_correct is None when the question is not auto-checked."""
    if not is_auto_evaluable(question):
        return None, 0.0
    if not normalise(answer):
        return False, 0.0
    if normalise(answer) == normalise(question.answer):
        return True, 1.0
    return False, 0.0
