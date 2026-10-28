from django.test import TestCase
from django.urls import reverse

from .models import ProjectAchievement, Role, StudentProfile, User

PASSWORD = "Str0ng-Pass-123"


def make_user(username, role_name=None, **extra):
    role = Role.objects.get_or_create(role_name=role_name)[0] if role_name else None
    return User.objects.create_user(
        username, email=f"{username}@example.com", password=PASSWORD, role=role, **extra
    )


class RegistrationTests(TestCase):
    def data(self, **overrides):
        data = {
            "username": "asha",
            "first_name": "Asha",
            "last_name": "Verma",
            "email": "asha@example.com",
            "password1": PASSWORD,
            "password2": PASSWORD,
        }
        data.update(overrides)
        return data

    def test_registration_creates_student_with_profile(self):
        response = self.client.post(reverse("register"), self.data())
        self.assertRedirects(response, reverse("profile_edit"))
        user = User.objects.get(username="asha")
        self.assertEqual(user.role.role_name, "Student")
        self.assertTrue(StudentProfile.objects.filter(user=user).exists())

    def test_duplicate_email_is_rejected(self):
        make_user("existing", "Student", )
        User.objects.filter(username="existing").update(email="asha@example.com")
        response = self.client.post(reverse("register"), self.data())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="asha").exists())

    def test_mismatched_passwords_are_rejected(self):
        response = self.client.post(reverse("register"), self.data(password2="different"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="asha").exists())

    def test_public_pages_load(self):
        for name in ("home", "register", "login"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)


class LoginAndAccessTests(TestCase):
    def test_login_and_dashboard(self):
        make_user("stu", "Student")
        self.assertTrue(self.client.login(username="stu", password=PASSWORD))
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "complete")

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, "/login/?next=/dashboard/")

    def test_suspended_account_cannot_log_in(self):
        make_user("sus", "Student", account_status=User.AccountStatus.SUSPENDED)
        response = self.client.post(reverse("login"), {"username": "sus", "password": PASSWORD})
        self.assertContains(response, "not active")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_password_is_rejected(self):
        make_user("stu", "Student")
        response = self.client.post(reverse("login"), {"username": "stu", "password": "nope"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_works_with_post_only(self):
        make_user("stu", "Student")
        self.client.login(username="stu", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.client.post(reverse("logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_user_without_role_sees_notice(self):
        make_user("norole")
        self.client.login(username="norole", password=PASSWORD)
        self.assertContains(self.client.get(reverse("dashboard")), "No role is assigned")

    def test_tpo_cannot_open_student_profile(self):
        make_user("tpo1", "TPO")
        self.client.login(username="tpo1", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("profile")).status_code, 403)
        self.assertEqual(self.client.get(reverse("profile_edit")).status_code, 403)

    def test_anonymous_user_is_redirected_from_profile(self):
        response = self.client.get(reverse("profile"))
        self.assertRedirects(response, "/login/?next=/profile/")


class ProfileTests(TestCase):
    def setUp(self):
        self.user = make_user("stu", "Student")
        self.client.login(username="stu", password=PASSWORD)

    def test_profile_pages_load(self):
        for name in ("profile", "profile_edit", "achievement_add"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_edit_profile_and_consent_date(self):
        response = self.client.post(
            reverse("profile_edit"),
            {
                "programme": "MCA",
                "year": 1,
                "skills": "Python, SQL",
                "targets": "Backend developer",
                "consent_given": "on",
            },
        )
        self.assertRedirects(response, reverse("profile"))
        profile = StudentProfile.objects.get(user=self.user)
        self.assertEqual(profile.skills, "Python, SQL")
        self.assertTrue(profile.consent_given)
        self.assertIsNotNone(profile.consent_date)

    def test_withdrawing_consent_clears_date(self):
        data = {"programme": "MCA", "year": 1, "skills": "", "targets": ""}
        self.client.post(reverse("profile_edit"), {**data, "consent_given": "on"})
        self.client.post(reverse("profile_edit"), data)
        profile = StudentProfile.objects.get(user=self.user)
        self.assertFalse(profile.consent_given)
        self.assertIsNone(profile.consent_date)

    def test_invalid_year_is_rejected(self):
        response = self.client.post(
            reverse("profile_edit"), {"programme": "MCA", "year": 99, "skills": "", "targets": ""}
        )
        self.assertEqual(response.status_code, 200)

    def test_add_and_delete_achievement(self):
        self.client.post(
            reverse("achievement_add"),
            {"type": "project", "title": "Library app", "description": "", "evidence_link": ""},
        )
        item = ProjectAchievement.objects.get(user=self.user)
        self.assertContains(self.client.get(reverse("profile")), "Library app")
        self.client.post(reverse("achievement_delete", args=[item.pk]))
        self.assertFalse(ProjectAchievement.objects.filter(pk=item.pk).exists())

    def test_cannot_delete_another_students_item(self):
        other = make_user("other", "Student")
        item = ProjectAchievement.objects.create(user=other, type="project", title="Secret")
        response = self.client.post(reverse("achievement_delete", args=[item.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ProjectAchievement.objects.filter(pk=item.pk).exists())

    def test_delete_requires_post(self):
        item = ProjectAchievement.objects.create(user=self.user, type="project", title="X")
        self.assertEqual(
            self.client.get(reverse("achievement_delete", args=[item.pk])).status_code, 405
        )
