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
