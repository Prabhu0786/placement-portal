from django.core.management.base import BaseCommand

from assessments.services import finalize_expired_attempts


class Command(BaseCommand):
    help = (
        "Time out and score every assessment attempt whose time limit has passed "
        "(for students who left without submitting). Run it every few minutes on a live server."
    )

    def handle(self, *args, **options):
        count = finalize_expired_attempts()
        self.stdout.write(self.style.SUCCESS(f"Finalized {count} expired attempt(s)."))
