from django import template

from content.models import ContentStatus, NoticeContest

register = template.Library()


@register.simple_tag
def latest_notices(limit=3):
    """The newest published notices and contests, for the dashboard."""
    return list(NoticeContest.objects.filter(status=ContentStatus.PUBLISHED).order_by("-date", "-id")[: int(limit)])
