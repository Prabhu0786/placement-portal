from django.core.management.base import BaseCommand

from accounts.models import User
from planning.models import WeeklyGoal
from planning.services import ACTIVE_STATUSES, sync_goals


class Command(BaseCommand):
    help = "Mark overdue weekly goals as Missed and complete goals that reached their target. Run daily on a live server."

    def handle(self, *args, **options):
        user_ids = WeeklyGoal.objects.filter(status__in=ACTIVE_STATUSES).values_list("user_id", flat=True).distinct()
        changed = sum(sync_goals(user) for user in User.objects.filter(id__in=list(user_ids)))
        self.stdout.write(self.style.SUCCESS(f"Updated {changed} goal(s)."))
