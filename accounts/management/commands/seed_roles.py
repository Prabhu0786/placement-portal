from django.core.management.base import BaseCommand

from accounts.models import Role

ROLES = {
    "Student": "Manage own profile, practise, take assessments, view own progress and plan.",
    "TPO": "Publish resources, notices and contests; manage companies and assessments; view authorised reports.",
    "Faculty": "Recommend and review content; mentor students (permissions to be validated).",
    "Administrator": "Manage accounts, roles, backups and configuration (permissions to be validated).",
}


class Command(BaseCommand):
    help = "Create the four standard roles (safe to run more than once)."

    def handle(self, *args, **options):
        for name, description in ROLES.items():
            role, created = Role.objects.get_or_create(
                role_name=name, defaults={"permissions": description}
            )
            self.stdout.write(f"{'Created' if created else 'Already exists'}: {role}")
