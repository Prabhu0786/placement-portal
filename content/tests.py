from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User

from .models import Company, ContentStatus, Question, Resource, Topic

PASSWORD = "Str0ng-Pass-123"
DRAFT, PENDING, PUBLISHED, ARCHIVED = "draft", "pending_review", "published", "archived"


def make_user(username, role_name):
    role = Role.objects.get_or_create(role_name=role_name)[0]
    return User.objects.create_user(
        username, email=f"{username}@example.com", password=PASSWORD, role=role
    )


class ContentTestCase(TestCase):
    def setUp(self):
        self.student = make_user("stu", "Student")
        self.tpo = make_user("tpo", "TPO")
        self.faculty = make_user("fac", "Faculty")
        self.other_faculty = make_user("fac2", "Faculty")
        self.aptitude = Topic.objects.create(subject="Aptitude", name="Percentages", difficulty="easy")
        self.dsa = Topic.objects.create(subject="Data Structures", name="Arrays", difficulty="hard")

    def login(self, user):
        self.client.login(username=user.username, password=PASSWORD)

    def resource(self, title="R", status=PUBLISHED, topic=None, created_by=None, **kw):
        return Resource.objects.create(
            topic=topic or self.aptitude,
            title=title,
            url="https://example.com/x",
            status=status,
            created_by=created_by,
            **kw,
        )

    def company(self, name="Acme", status=PUBLISHED, source="Careers page"):
        return Company.objects.create(name=name, status=status, source=source)


class StudentResourceTests(ContentTestCase):
    def test_login_required(self):
        response = self.client.get(reverse("resource_list"))
        self.assertRedirects(response, "/login/?next=/resources/")

    def test_only_published_resources_are_visible(self):
        self.resource("Visible", PUBLISHED)
        self.resource("Hidden draft", DRAFT)
        self.resource("Hidden pending", PENDING)
        self.resource("Hidden archived", ARCHIVED)
        self.login(self.student)
        response = self.client.get(reverse("resource_list"))
        self.assertContains(response, "Visible")
        for hidden in ("Hidden draft", "Hidden pending", "Hidden archived"):
            self.assertNotContains(response, hidden)

    def test_filters(self):
        self.resource("Percent basics", topic=self.aptitude, type="video")
        self.resource("Array tricks", topic=self.dsa, type="article")
        self.login(self.student)
        url = reverse("resource_list")
        r = self.client.get(url, {"subject": "Aptitude"})
        self.assertContains(r, "Percent basics"); self.assertNotContains(r, "Array tricks")
        r = self.client.get(url, {"topic": self.dsa.pk})
        self.assertContains(r, "Array tricks"); self.assertNotContains(r, "Percent basics")
        r = self.client.get(url, {"difficulty": "hard"})
        self.assertContains(r, "Array tricks"); self.assertNotContains(r, "Percent basics")
        r = self.client.get(url, {"type": "video"})
        self.assertContains(r, "Percent basics"); self.assertNotContains(r, "Array tricks")
        r = self.client.get(url, {"q": "tricks"})
        self.assertContains(r, "Array tricks"); self.assertNotContains(r, "Percent basics")

    def test_pagination_keeps_filters(self):
        for i in range(12):
            self.resource(f"Item {i:02d}", topic=self.aptitude)
        self.login(self.student)
        response = self.client.get(reverse("resource_list"), {"subject": "Aptitude"})
        self.assertContains(response, "subject=Aptitude&amp;page=2")
        self.assertEqual(self.client.get(reverse("resource_list"), {"page": 2}).status_code, 200)


class StudentCompanyTests(ContentTestCase):
    def test_only_published_companies_listed_and_openable(self):
        live = self.company("LiveCo")
        draft = self.company("DraftCo", status=DRAFT)
        self.login(self.student)
        listing = self.client.get(reverse("company_list"))
        self.assertContains(listing, "LiveCo"); self.assertNotContains(listing, "DraftCo")
        self.assertEqual(self.client.get(reverse("company_detail", args=[live.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("company_detail", args=[draft.pk])).status_code, 404)

    def test_detail_shows_source_updated_date_and_only_published_items(self):
        company = self.company("LiveCo", source="Placement notice 2026")
        company.stages = "Online test\nTechnical interview"
        company.eligibility = "60% throughout"
        company.save()
        self.resource("Good guide", company=company)
        self.resource("Draft guide", DRAFT, company=company)
        Question.objects.create(topic=self.aptitude, company=company, type="aptitude",
                                text="Published question", status=PUBLISHED)
        Question.objects.create(topic=self.aptitude, company=company, type="aptitude",
                                text="Draft question", status=DRAFT)
        self.login(self.student)
        r = self.client.get(reverse("company_detail", args=[company.pk]))
        self.assertContains(r, "Placement notice 2026")  # BR-3: source
        self.assertContains(r, "Last updated")            # BR-3: updated date
        self.assertContains(r, "Online test"); self.assertContains(r, "60% throughout")
        self.assertContains(r, "Good guide"); self.assertNotContains(r, "Draft guide")
        self.assertContains(r, "Published question"); self.assertNotContains(r, "Draft question")

    def test_company_search(self):
        self.company("Alpha Tech"); self.company("Beta Soft")
        self.login(self.student)
        r = self.client.get(reverse("company_list"), {"q": "alpha"})
        self.assertContains(r, "Alpha Tech"); self.assertNotContains(r, "Beta Soft")


class ManagementAccessTests(ContentTestCase):
    def test_student_cannot_use_management_pages(self):
        self.login(self.student)
        for name in ("manage_home", "manage_resources", "resource_create",
                     "manage_companies", "manage_topics", "topic_create"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_faculty_cannot_manage_companies(self):
        self.login(self.faculty)
        self.assertEqual(self.client.get(reverse("manage_companies")).status_code, 403)
        self.assertEqual(self.client.get(reverse("company_create")).status_code, 403)

    def test_anonymous_redirected(self):
        self.assertEqual(self.client.get(reverse("manage_home")).status_code, 302)

    def test_management_pages_load_for_tpo(self):
        self.resource("R1", DRAFT, created_by=self.tpo)
        self.company("C1", DRAFT)
        self.login(self.tpo)
        for name in ("manage_home", "manage_resources", "resource_create",
                     "manage_companies", "company_create", "manage_topics", "topic_create"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.assertEqual(self.client.get(reverse("manage_resources"), {"status": "draft"}).status_code, 200)


class WorkflowTests(ContentTestCase):
    def post_transition(self, resource, to):
        return self.client.post(reverse("resource_transition", args=[resource.pk]), {"to": to})

    def test_new_resource_starts_as_draft_and_records_author(self):
        self.login(self.faculty)
        response = self.client.post(reverse("resource_create"), {
            "topic": self.aptitude.pk, "title": "Faculty notes", "type": "notes",
            "url": "https://example.com/n", "source": "Prof. X", "company": "",
        })
        self.assertRedirects(response, reverse("manage_resources"))
        r = Resource.objects.get(title="Faculty notes")
        self.assertEqual(r.status, DRAFT)
        self.assertEqual(r.created_by, self.faculty)

    def test_full_lifecycle(self):
        r = self.resource("Cycle", DRAFT, created_by=self.faculty)
        self.login(self.faculty)
        self.post_transition(r, PENDING); r.refresh_from_db()
        self.assertEqual(r.status, PENDING)
        self.client.logout(); self.login(self.tpo)
        self.post_transition(r, PUBLISHED); r.refresh_from_db()
        self.assertEqual(r.status, PUBLISHED)
        self.client.logout(); self.login(self.student)
        self.assertContains(self.client.get(reverse("resource_list")), "Cycle")
        self.client.logout(); self.login(self.tpo)
        self.post_transition(r, ARCHIVED); r.refresh_from_db()
        self.assertEqual(r.status, ARCHIVED)
        self.client.logout(); self.login(self.student)
        self.assertNotContains(self.client.get(reverse("resource_list")), "Cycle")
        self.client.logout(); self.login(self.tpo)
        self.post_transition(r, DRAFT); r.refresh_from_db()
        self.assertEqual(r.status, DRAFT)

    def test_faculty_cannot_publish(self):
        r = self.resource("X", PENDING, created_by=self.faculty)
        self.login(self.faculty)
        self.assertEqual(self.post_transition(r, PUBLISHED).status_code, 403)
        r.refresh_from_db(); self.assertEqual(r.status, PENDING)

    def test_faculty_cannot_submit_someone_elses_draft(self):
        r = self.resource("X", DRAFT, created_by=self.other_faculty)
        self.login(self.faculty)
        self.assertEqual(self.post_transition(r, PENDING).status_code, 403)

    def test_illegal_transition_is_refused(self):
        r = self.resource("X", DRAFT, created_by=self.tpo)
        self.login(self.tpo)
        response = self.post_transition(r, ARCHIVED)
        self.assertRedirects(response, reverse("manage_resources"))
        r.refresh_from_db(); self.assertEqual(r.status, DRAFT)
        self.post_transition(r, "nonsense"); r.refresh_from_db()
        self.assertEqual(r.status, DRAFT)

    def test_transition_requires_post(self):
        r = self.resource("X", DRAFT, created_by=self.tpo)
        self.login(self.tpo)
        self.assertEqual(self.client.get(reverse("resource_transition", args=[r.pk])).status_code, 405)

    def test_faculty_edit_rules(self):
        own_draft = self.resource("Own", DRAFT, created_by=self.faculty)
        own_pending = self.resource("OwnPending", PENDING, created_by=self.faculty)
        others = self.resource("Others", DRAFT, created_by=self.other_faculty)
        self.login(self.faculty)
        self.assertEqual(self.client.get(reverse("resource_edit", args=[own_draft.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("resource_edit", args=[own_pending.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("resource_edit", args=[others.pk])).status_code, 403)

    def test_tpo_can_edit_any_resource(self):
        r = self.resource("Any", PUBLISHED, created_by=self.faculty)
        self.login(self.tpo)
        response = self.client.post(reverse("resource_edit", args=[r.pk]), {
            "topic": self.aptitude.pk, "title": "Renamed", "type": "article",
            "url": "https://example.com/y", "source": "", "company": "",
        })
        self.assertRedirects(response, reverse("manage_resources"))
        r.refresh_from_db()
        self.assertEqual(r.title, "Renamed"); self.assertEqual(r.status, PUBLISHED)


class CompanyManagementTests(ContentTestCase):
    def test_company_requires_source(self):  # BR-3
        self.login(self.tpo)
        response = self.client.post(reverse("company_create"),
                                    {"name": "NoSource", "eligibility": "", "stages": "", "source": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Company.objects.filter(name="NoSource").exists())

    def test_company_lifecycle_and_updated_date(self):
        self.login(self.tpo)
        self.client.post(reverse("company_create"), {
            "name": "NewCo", "eligibility": "60%", "stages": "Test\nHR", "source": "Notice"})
        c = Company.objects.get(name="NewCo")
        self.assertEqual(c.status, DRAFT)
        before = c.updated_at
        self.client.post(reverse("company_transition", args=[c.pk]), {"to": PUBLISHED})
        c.refresh_from_db()
        self.assertEqual(c.status, PUBLISHED)
        self.assertGreaterEqual(c.updated_at, before)

    def test_topic_created_by_faculty(self):
        self.login(self.faculty)
        self.client.post(reverse("topic_create"), {"subject": "Verbal", "name": "Grammar", "difficulty": "easy"})
        self.assertTrue(Topic.objects.filter(name="Grammar").exists())

    def test_duplicate_topic_rejected(self):
        self.login(self.tpo)
        response = self.client.post(reverse("topic_create"),
                                    {"subject": "Aptitude", "name": "Percentages", "difficulty": "easy"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Topic.objects.filter(name="Percentages").count(), 1)


class NavigationTests(ContentTestCase):
    def test_nav_links_by_role(self):
        self.login(self.student)
        self.assertNotContains(self.client.get(reverse("dashboard")), "Manage content")
        self.client.logout(); self.login(self.tpo)
        self.assertContains(self.client.get(reverse("dashboard")), "Manage content")


class QuestionManagementTests(ContentTestCase):
    def data(self, **overrides):
        data = {
            "topic": self.aptitude.pk, "company": "", "type": "aptitude", "difficulty": "easy",
            "text": "What is 10% of 200?", "options_text": "10\n20\n30", "answer": "20",
            "explanation": "Because.",
        }
        data.update(overrides)
        return data

    def test_student_cannot_manage_questions(self):
        self.login(self.student)
        self.assertEqual(self.client.get(reverse("manage_questions")).status_code, 403)

    def test_faculty_creates_mcq_as_draft(self):
        self.login(self.faculty)
        self.client.post(reverse("question_create"), self.data(answer=" 20 "))
        q = Question.objects.get()
        self.assertEqual(q.status, DRAFT)
        self.assertEqual(q.created_by, self.faculty)
        self.assertEqual(q.options, ["10", "20", "30"])
        self.assertEqual(q.answer, "20")

    def test_mcq_answer_must_match_an_option(self):
        self.login(self.tpo)
        response = self.client.post(reverse("question_create"), self.data(answer="99"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Question.objects.count(), 0)

    def test_mcq_needs_two_different_options(self):
        self.login(self.tpo)
        self.client.post(reverse("question_create"), self.data(options_text="20"))
        self.client.post(reverse("question_create"), self.data(options_text="20\n20"))
        self.assertEqual(Question.objects.count(), 0)

    def test_open_question_has_no_options(self):
        self.login(self.tpo)
        self.client.post(reverse("question_create"), self.data(
            type="coding", options_text="", answer="Use two pointers."))
        q = Question.objects.get()
        self.assertEqual(q.options, [])

    def test_edit_shows_existing_options(self):
        q = Question.objects.create(topic=self.aptitude, type="aptitude", text="T", options=["a", "b"],
                                    answer="a", status=DRAFT, created_by=self.tpo)
        self.login(self.tpo)
        self.assertContains(self.client.get(reverse("question_edit", args=[q.pk])), "a\nb")

    def test_question_lifecycle_and_faculty_limits(self):
        q = Question.objects.create(topic=self.aptitude, type="aptitude", text="T", options=["a", "b"],
                                    answer="a", status=DRAFT, created_by=self.faculty)
        url = reverse("question_transition", args=[q.pk])
        self.login(self.faculty)
        self.client.post(url, {"to": PENDING}); q.refresh_from_db()
        self.assertEqual(q.status, PENDING)
        self.assertEqual(self.client.post(url, {"to": PUBLISHED}).status_code, 403)
        self.client.logout(); self.login(self.tpo)
        self.client.post(url, {"to": PUBLISHED}); q.refresh_from_db()
        self.assertEqual(q.status, PUBLISHED)

    def test_manage_questions_filters_and_pages_load(self):
        Question.objects.create(topic=self.aptitude, type="coding", text="C", status=DRAFT, created_by=self.tpo)
        self.login(self.tpo)
        for params in ({}, {"status": "draft"}, {"type": "coding"}, {"type": "bogus"}):
            self.assertEqual(self.client.get(reverse("manage_questions"), params).status_code, 200)
        self.assertContains(self.client.get(reverse("manage_home")), "Manage questions")


class SampleQuestionDataTests(TestCase):
    """The sample data must be internally consistent, otherwise students would be marked wrong."""

    def test_every_mcq_answer_matches_an_option(self):
        from content.management.commands.seed_sample_questions import QUESTIONS, TOPICS

        topic_names = {name for _, name, _ in TOPICS}
        for item in QUESTIONS:
            self.assertIn(item["topic"], topic_names, item["text"])
            if item["options"]:
                self.assertIn(item["answer"], item["options"], item["text"])
                self.assertEqual(len(set(item["options"])), len(item["options"]), item["text"])
            else:
                self.assertTrue(item["answer"].strip(), item["text"])

    def test_command_is_repeatable_and_publishes(self):
        from django.core.management import call_command

        call_command("seed_sample_questions", verbosity=0)
        total = Question.objects.count()
        self.assertGreaterEqual(total, 25)
        self.assertEqual(Question.objects.exclude(status=PUBLISHED).count(), 0)
        call_command("seed_sample_questions", verbosity=0)
        self.assertEqual(Question.objects.count(), total)

    def test_draft_option(self):
        from django.core.management import call_command

        call_command("seed_sample_questions", "--draft", verbosity=0)
        self.assertEqual(Question.objects.exclude(status=DRAFT).count(), 0)

    def test_reference_solutions_run_correctly(self):
        from content.management.commands.seed_sample_questions import QUESTIONS

        def solution(keyword):
            return next(q["answer"] for q in QUESTIONS if keyword in q["text"])

        ns = {}
        exec(solution("reverses an array"), ns)
        self.assertEqual(ns["reverse"]([1, 2, 3, 4]), [4, 3, 2, 1])
        self.assertEqual(ns["reverse"]([]), [])
        ns2 = {}
        exec(solution("second largest"), ns2)
        self.assertEqual(ns2["second_largest"]([5, 1, 9, 7]), 7)
        self.assertEqual(ns2["second_largest"]([5, 5, 5]), None)
        self.assertEqual(ns2["second_largest"]([2, 8]), 2)
        self.assertEqual(ns2["second_largest"]([9, 9, 4]), 4)


class SampleResourceDataTests(TestCase):
    def test_data_is_consistent(self):
        from django.core.validators import URLValidator

        from content.management.commands.seed_sample_questions import TOPICS
        from content.management.commands.seed_sample_resources import RESOURCES

        topic_names = {name for _, name, _ in TOPICS}
        valid_types = set(Resource.ResourceType.values)
        validator = URLValidator(schemes=["https"])
        seen = set()
        for topic, title, rtype, url, source in RESOURCES:
            self.assertIn(topic, topic_names, title)
            self.assertIn(rtype, valid_types, title)
            validator(url)  # raises if not a valid https URL
            self.assertTrue(source, title)
            self.assertNotIn((topic, title), seen)
            seen.add((topic, title))

    def test_command_is_repeatable_and_students_see_resources(self):
        from django.core.management import call_command

        call_command("seed_sample_resources", verbosity=0)
        total = Resource.objects.count()
        self.assertGreaterEqual(total, 20)
        self.assertEqual(Resource.objects.exclude(status=PUBLISHED).count(), 0)
        call_command("seed_sample_resources", verbosity=0)
        self.assertEqual(Resource.objects.count(), total)
        student = make_user("stu", "Student")
        self.client.login(username="stu", password=PASSWORD)
        response = self.client.get(reverse("resource_list"), {"subject": "DBMS"})
        self.assertContains(response, "SQL joins")

    def test_draft_option_keeps_resources_hidden(self):
        from django.core.management import call_command

        call_command("seed_sample_resources", "--draft", verbosity=0)
        make_user("stu", "Student")
        self.client.login(username="stu", password=PASSWORD)
        self.assertNotContains(self.client.get(reverse("resource_list")), "SQL joins")

    def test_works_together_with_question_loader(self):
        from django.core.management import call_command

        call_command("seed_sample_questions", verbosity=0)
        call_command("seed_sample_resources", verbosity=0)
        self.assertEqual(Topic.objects.count(), 10)
