"""Content workflow: Draft -> Pending review -> Published -> Archived.

One place defines who may move content between states, so views and templates
cannot disagree. Rule summary:
  * TPO and Faculty can submit their own draft for review.
  * Only the TPO can publish, return to draft, archive or restore.
  * Faculty can edit only their own items, and only while still a draft.
"""

TRANSITIONS = {
    "draft": {"pending_review": {"TPO", "Faculty"}, "published": {"TPO"}},
    "pending_review": {"published": {"TPO"}, "draft": {"TPO"}},
    "published": {"archived": {"TPO"}},
    "archived": {"draft": {"TPO"}},
}

LABELS = {
    ("draft", "pending_review"): "Submit for review",
    ("draft", "published"): "Publish",
    ("pending_review", "published"): "Approve and publish",
    ("pending_review", "draft"): "Return to draft",
    ("published", "archived"): "Archive",
    ("archived", "draft"): "Restore as draft",
}


def check_transition(user, obj, to_status):
    """Return 'ok', 'invalid' (not a legal move) or 'forbidden' (not allowed for this user)."""
    allowed_roles = TRANSITIONS.get(obj.status, {}).get(to_status)
    if allowed_roles is None:
        return "invalid"
    if user.role_name not in allowed_roles:
        return "forbidden"
    if user.role_name != "TPO" and getattr(obj, "created_by_id", None) != user.id:
        return "forbidden"
    return "ok"


def available_actions(user, obj):
    """List of (target_status, button_label) the user may apply to this item."""
    return [
        (to, LABELS[(obj.status, to)])
        for to in TRANSITIONS.get(obj.status, {})
        if check_transition(user, obj, to) == "ok"
    ]


def can_edit(user, obj):
    if user.role_name == "TPO":
        return True
    return (
        user.role_name == "Faculty"
        and getattr(obj, "created_by_id", None) == user.id
        and obj.status == "draft"
    )
