import csv  # noqa: F401  (kept for future export tests)
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ProjectAchievement, Role, StudentProfile, User

from . import placement_services as services
from .models import Application, Company, NoticeContest, Question, Topic
from .placement_models import ChecklistProgress, ContestParticipation, ProjectNote

PASSWORD = "Str0ng-Pass-123"
FAST_HASH = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def make_user(username, role_name, consent=False, **extra):
    role = Role.objects.get_or_create(role_name=role_name)[0]
    user = User.objects.create_user(username, email=f"{username}@example.com", password=PASSWORD, role=role, **extra)
    if role_name == "Student":
        StudentProfile.objects.create(user=user, consent_given=consent)
    return user


@override_settings(PASSWORD_HASHERS=FAST_HASH)
class PlacementTestCase(TestCase):
    def setUp(self):
        self.student = make_user("stu", "Student", consent=True, first_name="Asha", last_name="Rao")
        self.other = make_user("other", "Student", consent=True)
        self.hidden = make_user("hidden", "Student", consent=False, first_name="Hidden", last_name="Person")
        self.tpo = make_user("tpo", "TPO")
        self.faculty = make_user("fac", "Faculty")
        self.today = timezone.localdate()

    def login(self, user):
        self.client.logout()
        self.client.login(username=user.username, password=PASSWORD)

    def notice(self, title="Notice", kind="notice", status="published", days=0, user=None, **kw):
        return NoticeContest.objects.create(
            title=title, kind=kind, status=status, date=self.today + timedelta(days=days), created_by=user, **kw
        )

    def company(self, name="Acme", status="published", **kw):
        return Company.objects.create(name=name, status=status, source="Careers page", **kw)

    def application(self, user=None, company=None, **kw):
        return Application.objects.create(user=user or self.student, company=company or self.company(), **kw)


# ============================================================== notices and contests
class NoticeViewTests(PlacementTestCase):
    def test_login_required_and_all_roles_can_read(self):
        self.assertEqual(self.client.get(reverse("notice_list")).status_code, 302)
        self.notice("Open to everyone")
        for user in (self.student, self.tpo, self.faculty):
            self.login(user)
            self.assertContains(self.client.get(reverse("notice_list")), "Open to everyone")

    def test_only_published_items_are_visible(self):  # BR-4
        self.notice("Live notice")
        for status in ("draft", "pending_review", "archived"):
            self.notice(f"Hidden {status}", status=status)
        self.login(self.student)
        page = self.client.get(reverse("notice_list"))
        self.assertContains(page, "Live notice")
        for status in ("draft", "pending_review", "archived"):
            self.assertNotContains(page, f"Hidden {status}")

    def test_sections_and_order(self):
        self.notice("Older notice", days=-5)
        self.notice("Newer notice", days=-1)
        self.notice("Next contest", kind="contest", days=3)
        self.notice("Old contest", kind="contest", days=-10)
        self.login(self.student)
        page = self.client.get(reverse("notice_list"))
        content = page.content.decode()
        self.assertLess(content.index("Newer notice"), content.index("Older notice"))
        self.assertLess(content.index("Upcoming contests"), content.index("Next contest"))
        self.assertLess(content.index("Next contest"), content.index("Past contests"))
        self.assertContains(page, "Old contest")

    def test_manage_link_only_for_staff_roles(self):
        self.login(self.student)
        self.assertNotContains(self.client.get(reverse("notice_list")), reverse("manage_notices"))
        self.login(self.tpo)
        self.assertContains(self.client.get(reverse("notice_list")), reverse("manage_notices"))

    def test_dashboard_shows_latest_published_notices(self):
        for i in range(5):
            self.notice(f"Dash notice {i}", days=-i)
        self.notice("Hidden draft notice", status="draft")
        self.login(self.student)
        page = self.client.get(reverse("dashboard"))
        self.assertContains(page, "Latest notices")
        self.assertContains(page, "Dash notice 0")
        self.assertContains(page, "Dash notice 2")
        self.assertNotContains(page, "Dash notice 3")        # only three
        self.assertNotContains(page, "Hidden draft notice")


class ContestRegistrationTests(PlacementTestCase):
    def test_register_and_withdraw(self):
        contest = self.notice("Coding contest", kind="contest", days=4)
        self.login(self.student)
        self.client.post(reverse("contest_register", args=[contest.pk]))
        self.client.post(reverse("contest_register", args=[contest.pk]))  # repeating is harmless
        self.assertEqual(ContestParticipation.objects.filter(user=self.student, contest=contest).count(), 1)
        self.assertContains(self.client.get(reverse("notice_list")), "Registered")
        self.client.post(reverse("contest_withdraw", args=[contest.pk]))
        self.assertFalse(ContestParticipation.objects.exists())

    def test_rules(self):
        past = self.notice("Past", kind="contest", days=-1)
        draft = self.notice("Draft", kind="contest", days=2, status="draft")
        plain = self.notice("Just a notice", kind="notice", days=2)
        self.login(self.student)
        self.client.post(reverse("contest_register", args=[past.pk]))
        self.assertEqual(self.client.post(reverse("contest_register", args=[draft.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("contest_register", args=[plain.pk])).status_code, 404)
        self.assertEqual(ContestParticipation.objects.count(), 0)

    def test_students_only_and_post_only(self):
        contest = self.notice("Contest", kind="contest", days=2)
        self.login(self.tpo)
        self.assertEqual(self.client.post(reverse("contest_register", args=[contest.pk])).status_code, 403)
        self.login(self.student)
        self.assertEqual(self.client.get(reverse("contest_register", args=[contest.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse("contest_withdraw", args=[contest.pk])).status_code, 405)

    def test_students_cannot_withdraw_each_other(self):
        contest = self.notice("Contest", kind="contest", days=2)
        ContestParticipation.objects.create(user=self.other, contest=contest)
        self.login(self.student)
        self.client.post(reverse("contest_withdraw", args=[contest.pk]))
        self.assertTrue(ContestParticipation.objects.filter(user=self.other).exists())


class ManageNoticeTests(PlacementTestCase):
    def form(self, **overrides):
        data = {"kind": "notice", "title": "Drive on Monday", "description": "Be on time.", "date": self.today.isoformat()}
        data.update(overrides)
        return data

    def test_access(self):
        self.assertEqual(self.client.get(reverse("manage_notices")).status_code, 302)
        self.login(self.student)
        for name in ("manage_notices", "notice_create"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        for user in (self.tpo, self.faculty):
            self.login(user)
            self.assertEqual(self.client.get(reverse("manage_notices")).status_code, 200)
            self.assertEqual(self.client.get(reverse("notice_create")).status_code, 200)

    def test_workflow_faculty_submits_tpo_publishes(self):
        self.login(self.faculty)
        self.client.post(reverse("notice_create"), self.form())
        item = NoticeContest.objects.get()
        self.assertEqual((item.status, item.created_by), ("draft", self.faculty))
        url = reverse("notice_transition", args=[item.pk])
        self.client.post(url, {"to": "pending_review"})
        self.assertEqual(self.client.post(url, {"to": "published"}).status_code, 403)
        self.login(self.student)
        self.assertNotContains(self.client.get(reverse("notice_list")), "Drive on Monday")
        self.login(self.tpo)
        self.client.post(url, {"to": "published"})
        self.login(self.student)
        self.assertContains(self.client.get(reverse("notice_list")), "Drive on Monday")
        self.login(self.tpo)
        self.client.post(url, {"to": "archived"})
        self.login(self.student)
        self.assertNotContains(self.client.get(reverse("notice_list")), "Drive on Monday")

    def test_illegal_transition_and_edit_rules(self):
        own = self.notice("Own", status="draft", user=self.faculty)
        published = self.notice("Live", user=self.faculty)
        self.login(self.faculty)
        self.assertEqual(self.client.get(reverse("notice_edit", args=[own.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("notice_edit", args=[published.pk])).status_code, 403)
        self.login(self.tpo)
        self.client.post(reverse("notice_transition", args=[own.pk]), {"to": "archived"})
        own.refresh_from_db()
        self.assertEqual(own.status, "draft")
        self.assertEqual(self.client.get(reverse("notice_transition", args=[own.pk])).status_code, 405)

    def test_tpo_can_edit_and_sees_participant_counts(self):
        contest = self.notice("Quiz", kind="contest", days=3, user=self.tpo)
        ContestParticipation.objects.create(user=self.student, contest=contest)
        ContestParticipation.objects.create(user=self.other, contest=contest)
        self.login(self.tpo)
        page = self.client.get(reverse("manage_notices"))
        self.assertRegex(page.content.decode(), r"(?s)Quiz.*?<td>2</td>")
        self.client.post(reverse("notice_edit", args=[contest.pk]), self.form(kind="contest", title="Quiz renamed"))
        contest.refresh_from_db()
        self.assertEqual(contest.title, "Quiz renamed")
        self.assertEqual(self.client.get(reverse("manage_notices"), {"status": "published"}).status_code, 200)

    def test_invalid_form_is_not_saved(self):
        self.login(self.tpo)
        self.client.post(reverse("notice_create"), self.form(title=""))
        self.client.post(reverse("notice_create"), self.form(date="not-a-date"))
        self.assertEqual(NoticeContest.objects.count(), 0)


# ==================================================================== applications
class ApplicationRuleTests(PlacementTestCase):
    def test_buttons_by_status_and_role(self):
        app = self.application()
        self.assertEqual([t for t, _ in services.available_actions(app, "Student")], ["applied", "withdrawn"])
        self.assertEqual(services.available_actions(app, "TPO"), [])
        app.application_status = "applied"
        self.assertEqual([t for t, _ in services.available_actions(app, "Student")], ["shortlisted", "rejected", "withdrawn"])
        self.assertEqual([t for t, _ in services.available_actions(app, "TPO")], ["shortlisted", "rejected"])
        app.application_status = "shortlisted"
        self.assertEqual([t for t, _ in services.available_actions(app, "TPO")], ["selected", "rejected"])
        for final in ("rejected", "selected", "withdrawn"):
            app.application_status = final
            self.assertEqual(services.available_actions(app, "Student"), [])
        self.assertEqual(services.available_actions(app, "Faculty"), [])

    def test_full_path_to_selected(self):
        app = self.application()
        for step in ("applied", "shortlisted", "selected"):
            services.change_status(app, step, "Student")
        app.refresh_from_db()
        self.assertEqual(app.application_status, "selected")
        with self.assertRaises(services.ApplicationError):
            services.change_status(app, "withdrawn", "Student")

    def test_illegal_steps_are_refused(self):
        app = self.application()
        for bad in ("selected", "shortlisted", "rejected", "interested", "eligible", "nonsense"):
            with self.assertRaises(services.ApplicationError, msg=bad):
                services.change_status(app, bad, "Student")
        with self.assertRaises(services.ApplicationError):
            services.change_status(app, "applied", "TPO")  # the TPO records results, not applications

    def test_cannot_apply_when_marked_not_eligible(self):
        app = self.application(eligibility_status="not_eligible")
        with self.assertRaises(services.ApplicationError):
            services.change_status(app, "applied", "Student")

    def test_eligibility_keeps_status_in_step(self):
        app = self.application()
        services.set_eligibility(app, "eligible")
        self.assertEqual(app.application_status, "eligible")
        services.set_eligibility(app, "not_eligible")
        self.assertEqual((app.eligibility_status, app.application_status), ("not_eligible", "interested"))
        services.set_eligibility(app, "eligible")
        services.change_status(app, "applied", "Student")
        services.set_eligibility(app, "not_checked")  # still open, so allowed, status unchanged
        self.assertEqual(app.application_status, "applied")

    def test_eligibility_rejects_bad_values_and_closed_applications(self):
        app = self.application()
        with self.assertRaises(services.ApplicationError):
            services.set_eligibility(app, "maybe")
        app.application_status = "rejected"
        with self.assertRaises(services.ApplicationError):
            services.set_eligibility(app, "eligible")

    def test_consent_list(self):
        self.assertEqual(services.consenting_student_ids(), {self.student.pk, self.other.pk})


class StudentApplicationViewTests(PlacementTestCase):
    def test_access(self):
        self.assertEqual(self.client.get(reverse("application_list")).status_code, 302)
        self.login(self.tpo)
        self.assertEqual(self.client.get(reverse("application_list")).status_code, 403)
        self.login(self.student)
        self.assertEqual(self.client.get(reverse("application_list")).status_code, 200)

    def test_add_published_company_once(self):
        acme, draft = self.company("Acme"), self.company("Hidden Co", status="draft")
        self.login(self.student)
        self.client.post(reverse("application_add"), {"company": acme.pk})
        self.client.post(reverse("application_add"), {"company": acme.pk})  # duplicate
        self.client.post(reverse("application_add"), {"company": draft.pk})  # unpublished
        self.assertEqual(list(Application.objects.values_list("company__name", flat=True)), ["Acme"])
        page = self.client.get(reverse("application_list"))
        self.assertContains(page, "Acme")
        self.assertNotContains(page, "Hidden Co")

    def test_track_from_company_page(self):
        acme = self.company("Acme", eligibility="60% marks")
        self.login(self.student)
        self.assertContains(self.client.get(reverse("company_detail", args=[acme.pk])), "Track this company")
        self.client.post(reverse("application_track", args=[acme.pk]))
        self.client.post(reverse("application_track", args=[acme.pk]))
        self.assertEqual(Application.objects.filter(user=self.student).count(), 1)
        self.assertContains(self.client.get(reverse("application_list")), "60% marks")
        draft = self.company("Draft Co", status="draft")
        self.assertEqual(self.client.post(reverse("application_track", args=[draft.pk])).status_code, 404)
        self.login(self.tpo)
        self.assertNotContains(self.client.get(reverse("company_detail", args=[acme.pk])), "Track this company")

    def test_status_and_eligibility_actions(self):
        app = self.application()
        self.login(self.student)
        self.client.post(reverse("application_eligibility", args=[app.pk]), {"eligibility": "eligible"})
        app.refresh_from_db()
        self.assertEqual((app.eligibility_status, app.application_status), ("eligible", "eligible"))
        self.client.post(reverse("application_status", args=[app.pk]), {"to": "applied"})
        self.client.post(reverse("application_status", args=[app.pk]), {"to": "selected"})  # skipping a step
        app.refresh_from_db()
        self.assertEqual(app.application_status, "applied")
        page = self.client.get(reverse("application_list"))
        self.assertContains(page, "Shortlisted")

    def test_delete_rules(self):
        early, applied = self.application(company=self.company("A")), self.application(company=self.company("B"), application_status="applied")
        self.login(self.student)
        self.client.post(reverse("application_delete", args=[early.pk]))
        self.client.post(reverse("application_delete", args=[applied.pk]))
        self.assertEqual(list(Application.objects.values_list("pk", flat=True)), [applied.pk])

    def test_students_cannot_touch_each_others_applications(self):
        app = self.application(user=self.other)
        self.login(self.student)
        for name, data in (("application_status", {"to": "applied"}), ("application_eligibility", {"eligibility": "eligible"}), ("application_delete", {})):
            self.assertEqual(self.client.post(reverse(name, args=[app.pk]), data).status_code, 404)
        # the other student's application must not appear in this student's tracker
        self.assertContains(self.client.get(reverse("application_list")), "You are not tracking any company yet")

    def test_state_changing_pages_need_post(self):
        app = self.application()
        self.login(self.student)
        for name in ("application_status", "application_eligibility", "application_delete"):
            self.assertEqual(self.client.get(reverse(name, args=[app.pk])).status_code, 405)


class TpoApplicationViewTests(PlacementTestCase):
    def setUp(self):
        super().setUp()
        self.acme, self.beta = self.company("Acme"), self.company("Beta")
        self.a1 = self.application(self.student, self.acme, application_status="applied")
        self.a2 = self.application(self.other, self.acme, application_status="shortlisted")
        self.a3 = self.application(self.hidden, self.acme, application_status="applied")   # no consent
        self.a4 = self.application(self.student, self.beta)

    def test_access(self):
        self.assertEqual(self.client.get(reverse("manage_applications")).status_code, 302)
        for user in (self.student, self.faculty):
            self.login(user)
            self.assertEqual(self.client.get(reverse("manage_applications")).status_code, 403)

    def test_only_consenting_students_are_listed(self):  # BR-10, BR-14
        self.login(self.tpo)
        page = self.client.get(reverse("manage_applications"))
        self.assertContains(page, "Asha Rao")
        self.assertNotContains(page, "Hidden Person")
        self.assertContains(page, "2 of 3 students")

    def test_company_summary_counts_exclude_non_consenting(self):
        self.login(self.tpo)
        rows = {r["name"]: r for r in self.client.get(reverse("manage_applications")).context["summary"]}
        self.assertEqual((rows["Acme"]["total"], rows["Acme"]["applied"], rows["Acme"]["shortlisted"]), (2, 1, 1))
        self.assertEqual((rows["Beta"]["total"], rows["Beta"]["open"]), (1, 1))

    def test_filters(self):
        self.login(self.tpo)
        page = self.client.get(reverse("manage_applications"), {"company": self.beta.pk})
        self.assertEqual([a.pk for a in page.context["page"].object_list], [self.a4.pk])
        page = self.client.get(reverse("manage_applications"), {"status": "shortlisted"})
        self.assertEqual([a.pk for a in page.context["page"].object_list], [self.a2.pk])

    def test_tpo_records_recruitment_updates(self):
        self.login(self.tpo)
        self.client.post(reverse("manage_application_status", args=[self.a2.pk]), {"to": "selected"})
        self.a2.refresh_from_db()
        self.assertEqual(self.a2.application_status, "selected")
        self.client.post(reverse("manage_application_status", args=[self.a1.pk]), {"to": "withdrawn"})  # not a TPO action
        self.a1.refresh_from_db()
        self.assertEqual(self.a1.application_status, "applied")

    def test_cannot_update_a_non_consenting_students_application(self):
        self.login(self.tpo)
        self.assertEqual(self.client.post(reverse("manage_application_status", args=[self.a3.pk]), {"to": "shortlisted"}).status_code, 404)
        self.a3.refresh_from_db()
        self.assertEqual(self.a3.application_status, "applied")

    def test_redirect_target_is_restricted(self):
        self.login(self.tpo)
        good = self.client.post(reverse("manage_application_status", args=[self.a1.pk]), {"to": "shortlisted", "next": "/manage/applications/?status=applied"})
        self.assertEqual(good["Location"], "/manage/applications/?status=applied")
        self.a1.application_status = "applied"; self.a1.save()
        bad = self.client.post(reverse("manage_application_status", args=[self.a1.pk]), {"to": "shortlisted", "next": "https://evil.example/"})
        self.assertEqual(bad["Location"], reverse("manage_applications"))

    def test_manage_page_links(self):
        self.login(self.tpo)
        self.assertContains(self.client.get(reverse("manage_home")), reverse("manage_applications"))
        self.assertContains(self.client.get(reverse("dashboard")), reverse("manage_applications"))
        self.login(self.faculty)
        self.assertNotContains(self.client.get(reverse("manage_home")), reverse("manage_applications"))


# ============================================================= preparation pages
class InterviewPrepTests(PlacementTestCase):
    def setUp(self):
        super().setUp()
        self.hr = Topic.objects.create(subject="Interview", name="HR Questions")
        self.tech = Topic.objects.create(subject="Interview", name="Technical Interview")

    def question(self, topic, text, status="published", qtype="interview", answer="Model answer text", explanation=""):
        return Question.objects.create(topic=topic, type=qtype, text=text, status=status, answer=answer, explanation=explanation)

    def test_login_required(self):
        self.assertEqual(self.client.get(reverse("interview_prep")).status_code, 302)

    def test_shows_only_published_interview_questions_grouped_by_topic(self):
        self.question(self.hr, "Tell me about yourself", explanation="Keep it short")
        self.question(self.tech, "Explain a thread")
        self.question(self.hr, "Draft interview question", status="draft")
        self.question(self.hr, "Aptitude style question", qtype="aptitude")
        for user in (self.student, self.tpo):
            self.login(user)
            page = self.client.get(reverse("interview_prep"))
            self.assertContains(page, "Interview / HR Questions")
            self.assertContains(page, "Interview / Technical Interview")
            self.assertContains(page, "Tell me about yourself")
            self.assertContains(page, "Model answer text")
            self.assertContains(page, "Keep it short")
            self.assertNotContains(page, "Draft interview question")
            self.assertNotContains(page, "Aptitude style question")

    def test_empty_state(self):
        self.login(self.student)
        self.assertContains(self.client.get(reverse("interview_prep")), "No interview questions have been published")

    def test_seed_command(self):
        call_command("seed_interview_questions", verbosity=0)
        total = Question.objects.filter(type="interview").count()
        self.assertGreaterEqual(total, 15)
        self.assertEqual(Question.objects.filter(type="interview").exclude(status="published").count(), 0)
        for q in Question.objects.filter(type="interview"):
            self.assertTrue(q.answer.strip() and q.explanation.strip(), q.text)
            self.assertEqual(q.options, [])
        call_command("seed_interview_questions", verbosity=0)
        self.assertEqual(Question.objects.filter(type="interview").count(), total)
        self.login(self.student)
        page = self.client.get(reverse("interview_prep"))
        for text in ("Behavioural Questions", "Technical Interview", "process and a thread"):
            self.assertContains(page, text)

    def test_seed_draft_option_hides_questions_from_students(self):
        call_command("seed_interview_questions", "--draft", verbosity=0)
        self.login(self.student)
        self.assertContains(self.client.get(reverse("interview_prep")), "No interview questions have been published")


class PrepareHomeTests(PlacementTestCase):
    def test_access_and_content(self):
        self.assertEqual(self.client.get(reverse("prepare_home")).status_code, 302)
        self.login(self.tpo)
        self.assertEqual(self.client.get(reverse("prepare_home")).status_code, 403)
        ProjectAchievement.objects.create(user=self.student, type="project", title="P1")
        ChecklistProgress.objects.create(user=self.student, key="contact")
        self.login(self.student)
        page = self.client.get(reverse("prepare_home"))
        self.assertContains(page, "1 of 13 checks done")
        self.assertContains(page, "1 project")
        self.assertContains(page, reverse("resume_checklist"))


class ResumeChecklistTests(PlacementTestCase):
    def test_access(self):
        self.assertEqual(self.client.get(reverse("resume_checklist")).status_code, 302)
        self.login(self.tpo)
        self.assertEqual(self.client.get(reverse("resume_checklist")).status_code, 403)

    def test_save_tick_and_untick(self):
        self.login(self.student)
        self.client.post(reverse("resume_checklist"), {"item_contact": "on", "item_length": "on", "item_bogus": "on"})
        self.assertEqual(set(ChecklistProgress.objects.filter(user=self.student).values_list("key", flat=True)), {"contact", "length"})
        page = self.client.get(reverse("resume_checklist"))
        self.assertContains(page, "2 of 13 checks done")
        self.assertContains(page, 'id="item_contact" name="item_contact" checked')
        self.client.post(reverse("resume_checklist"), {"item_contact": "on"})
        self.assertEqual(ChecklistProgress.objects.filter(user=self.student).count(), 1)
        self.client.post(reverse("resume_checklist"), {})
        self.assertEqual(ChecklistProgress.objects.count(), 0)

    def test_progress_is_per_student(self):
        ChecklistProgress.objects.create(user=self.other, key="contact")
        self.login(self.student)
        self.assertContains(self.client.get(reverse("resume_checklist")), "0 of 13 checks done")
        self.client.post(reverse("resume_checklist"), {"item_skills": "on"})
        self.assertTrue(ChecklistProgress.objects.filter(user=self.other, key="contact").exists())

    def test_every_checklist_item_has_help_text_and_unique_key(self):
        keys = [k for k, _, _ in services.RESUME_CHECKLIST]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(title and help_text for _, title, help_text in services.RESUME_CHECKLIST))


class ProjectPromptTests(PlacementTestCase):
    def setUp(self):
        super().setUp()
        self.project = ProjectAchievement.objects.create(user=self.student, type="project", title="Library app", description="A library system")
        self.cert = ProjectAchievement.objects.create(user=self.student, type="certificate", title="Python certificate")
        self.theirs = ProjectAchievement.objects.create(user=self.other, type="project", title="Secret project")

    def test_list_shows_only_own_projects(self):
        self.login(self.student)
        page = self.client.get(reverse("project_list"))
        self.assertContains(page, "Library app")
        self.assertNotContains(page, "Python certificate")
        self.assertNotContains(page, "Secret project")
        self.assertContains(page, "0 of 6 questions answered")

    def test_empty_list_points_to_profile(self):
        self.login(self.other)
        ProjectAchievement.objects.filter(user=self.other).delete()
        self.assertContains(self.client.get(reverse("project_list")), "No projects yet")

    def test_save_update_and_clear_notes(self):
        self.login(self.student)
        url = reverse("project_prepare", args=[self.project.pk])
        self.assertContains(self.client.get(url), "What problem does this project solve")
        self.client.post(url, {"problem": "Helps students find books", "role": "I built the search", "tech": ""})
        notes = dict(ProjectNote.objects.filter(project=self.project).values_list("prompt_key", "text"))
        self.assertEqual(notes, {"problem": "Helps students find books", "role": "I built the search"})
        self.assertContains(self.client.get(url), "I built the search")
        self.assertContains(self.client.get(reverse("project_list")), "2 of 6 questions answered")
        self.client.post(url, {"problem": "Updated problem text", "role": ""})
        notes = dict(ProjectNote.objects.filter(project=self.project).values_list("prompt_key", "text"))
        self.assertEqual(notes, {"problem": "Updated problem text"})

    def test_too_long_answer_is_rejected(self):
        self.login(self.student)
        self.client.post(reverse("project_prepare", args=[self.project.pk]), {"problem": "x" * 2001})
        self.assertEqual(ProjectNote.objects.count(), 0)

    def test_other_students_and_other_types_are_not_accessible(self):
        self.login(self.student)
        self.assertEqual(self.client.get(reverse("project_prepare", args=[self.theirs.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("project_prepare", args=[self.theirs.pk]), {"problem": "hack"}).status_code, 404)
        self.assertEqual(self.client.get(reverse("project_prepare", args=[self.cert.pk])).status_code, 404)
        self.assertEqual(ProjectNote.objects.count(), 0)

    def test_notes_are_private_from_the_tpo(self):  # BR-14
        ProjectNote.objects.create(project=self.project, prompt_key="role", text="my private note text")
        self.login(self.tpo)
        self.assertEqual(self.client.get(reverse("project_prepare", args=[self.project.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("project_list")).status_code, 403)
        self.assertNotContains(self.client.get(reverse("reports_home")), "my private note text")
        self.assertNotContains(self.client.get(reverse("report_student", args=[self.student.pk])), "my private note text")

    def test_deleting_a_project_removes_its_notes(self):
        ProjectNote.objects.create(project=self.project, prompt_key="role", text="x")
        self.project.delete()
        self.assertEqual(ProjectNote.objects.count(), 0)


class NavigationTests(PlacementTestCase):
    def test_student_links(self):
        self.login(self.student)
        page = self.client.get(reverse("dashboard"))
        for url in (reverse("notice_list"), reverse("application_list"), reverse("prepare_home")):
            self.assertContains(page, f'href="{url}"')
        for heading in ("Prepare for interviews", "My applications", "Latest notices"):
            self.assertContains(page, heading)

    def test_notices_link_for_every_role(self):
        for user in (self.tpo, self.faculty):
            self.login(user)
            self.assertContains(self.client.get(reverse("dashboard")), f'href="{reverse("notice_list")}"')

    def test_staff_manage_page_has_notice_card(self):
        for user in (self.tpo, self.faculty):
            self.login(user)
            self.assertContains(self.client.get(reverse("manage_home")), "Manage notices")
