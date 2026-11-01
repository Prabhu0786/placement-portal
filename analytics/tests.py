import csv
import io
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, StudentProfile, User
from assessments.models import Assessment, Attempt, Response
from content.models import Question, Topic

from . import reports, services

PASSWORD = "Str0ng-Pass-123"
FAST_HASH = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def make_user(username, role_name, consent=None, **extra):
    role = Role.objects.get_or_create(role_name=role_name)[0]
    user = User.objects.create_user(
        username, email=f"{username}@example.com", password=PASSWORD, role=role, **extra
    )
    if role_name == "Student":
        StudentProfile.objects.create(user=user, consent_given=bool(consent))
    return user


@override_settings(PASSWORD_HASHERS=FAST_HASH)
class AnalyticsTestCase(TestCase):
    def setUp(self):
        self.student = make_user("stu", "Student", consent=True)
        self.tpo = make_user("tpo", "TPO")
        self.faculty = make_user("fac", "Faculty")
        self.t1 = Topic.objects.create(subject="Aptitude", name="Percentages")
        self.t2 = Topic.objects.create(subject="Data Structures", name="Arrays")

    def login(self, user):
        self.client.logout()
        self.client.login(username=user.username, password=PASSWORD)

    def mcq(self, topic, n=1, status="published"):
        return [
            Question.objects.create(topic=topic, type="aptitude", text=f"{topic.name} Q{i}",
                                    options=["a", "b"], answer="a", status=status)
            for i in range(n)
        ]

    def open_question(self, topic):
        return Question.objects.create(topic=topic, type="coding", text=f"Open {topic.name}", status="published")

    def finished(self, user, rows, when=None, assessment=None, timed_out=False, status="evaluated"):
        """Create a finished attempt. rows: list of (question, answer, is_correct)."""
        when = when or timezone.now()
        attempt = Attempt.objects.create(
            user=user, assessment=assessment,
            attempt_type="assessment" if assessment else "practice",
            status=status, started_at=when - timedelta(minutes=5), submitted_at=when,
            score=sum(1 for _, _, ok in rows if ok), timed_out=timed_out,
        )
        for question, answer, ok in rows:
            Response.objects.create(attempt=attempt, question=question, answer=answer,
                                    is_correct=ok, marks_awarded=1.0 if ok else 0.0, time_taken_seconds=60)
        return attempt

    def answers(self, questions, correct):
        """(question, answer, is_correct) rows with the first `correct` answered right."""
        return [(q, "a" if i < correct else "b", i < correct) for i, q in enumerate(questions)]


class CalculationTests(AnalyticsTestCase):
    def test_summary_counts_only_scored_answers_for_accuracy(self):
        qs = self.mcq(self.t1, 4)
        op = self.open_question(self.t1)
        rows = self.answers(qs, 3) + [(op, "my code", None)]
        rows[3] = (qs[3], "", False)  # unanswered multiple choice counts as wrong
        self.finished(self.student, rows)
        data = services.summarise(services.finished_responses([self.student.id]))
        self.assertEqual(data["attempts"], 1)
        self.assertEqual(data["presented"], 5)
        self.assertEqual(data["answered"], 4)   # 3 answers + the open one; blank MCQ not answered
        self.assertEqual(data["auto"], 4)
        self.assertEqual(data["correct"], 3)
        self.assertEqual(data["accuracy"], 75.0)
        self.assertEqual(data["minutes"], 5)

    def test_unfinished_attempts_are_ignored(self):
        qs = self.mcq(self.t1, 2)
        self.finished(self.student, self.answers(qs, 2), status="in_progress")
        self.assertEqual(services.finished_responses([self.student.id]), [])

    def test_topic_levels_and_order(self):
        q1, q2, q3, q4 = self.mcq(self.t1, 4), self.mcq(self.t2, 4), [], []
        t3 = Topic.objects.create(subject="Verbal", name="Grammar")
        t4 = Topic.objects.create(subject="DBMS", name="SQL")
        few = self.mcq(t3, 2)
        weak = self.mcq(t4, 4)
        self.finished(self.student, self.answers(q1, 3) + self.answers(q2, 2) + self.answers(few, 2) + self.answers(weak, 1))
        rows = services.topic_breakdown(services.finished_responses([self.student.id]))
        self.assertEqual([(r["topic"].name, r["level_key"]) for r in rows],
                         [("SQL", "weak"), ("Arrays", "developing"), ("Percentages", "strong"), ("Grammar", "nodata")])
        self.assertEqual([r["accuracy"] for r in rows], [25.0, 50.0, 75.0, 100.0])

    def test_weekly_series_places_attempts_in_the_right_weeks(self):
        qs = self.mcq(self.t1, 2)
        now = timezone.now()
        self.finished(self.student, self.answers(qs, 2), when=now)
        self.finished(self.student, self.answers(qs, 1), when=now - timedelta(days=7))
        self.finished(self.student, self.answers(qs, 0), when=now - timedelta(days=21))
        series = services.weekly_series(services.finished_responses([self.student.id]), now=now)
        self.assertEqual(len(series), 8)
        self.assertEqual([w["accuracy"] for w in series[-4:]], [0.0, None, 50.0, 100.0])
        self.assertTrue(all(series[i]["start"] < series[i + 1]["start"] for i in range(7)))
        self.assertEqual(series[-1]["start"].weekday(), 0)  # weeks start on Monday

    def test_trend_chart_draws_only_weeks_with_data(self):
        qs = self.mcq(self.t1, 2)
        now = timezone.now()
        self.finished(self.student, self.answers(qs, 2), when=now)
        self.finished(self.student, self.answers(qs, 1), when=now - timedelta(days=14))
        series = services.weekly_series(services.finished_responses([self.student.id]), now=now)
        chart = services.trend_chart(series)
        self.assertTrue(chart["has_data"])
        self.assertEqual(len(chart["dots"]), 2)
        self.assertEqual(len(chart["points"].split()), 2)
        self.assertEqual(len(chart["labels"]), 8)
        self.assertFalse(services.trend_chart(services.weekly_series([], now=now))["has_data"])

    def test_readiness_rules(self):
        a, b = self.mcq(self.t1, 5), self.mcq(self.t2, 5)
        overview = services.student_overview(self.student)
        self.assertEqual(overview["readiness"]["label"], "Getting started")
        self.finished(self.student, self.answers(a, 5))
        self.assertEqual(services.student_overview(self.student)["readiness"]["label"], "Getting started")  # only 5 scored answers
        self.finished(self.student, self.answers(a, 5))
        ready = services.student_overview(self.student)["readiness"]
        self.assertEqual((ready["coverage"], ready["covered"], ready["available"]), (50, 1, 2))
        self.assertEqual(ready["label"], "Developing")        # accuracy 100, coverage 50
        self.finished(self.student, self.answers(b, 5))
        self.assertEqual(services.student_overview(self.student)["readiness"]["label"], "Strong")  # coverage 100
        self.assertEqual(services.student_overview(self.student)["readiness"]["consistency"], 1)

    def test_readiness_needs_more_practice_when_accuracy_is_low(self):
        a = self.mcq(self.t1, 10)
        self.finished(self.student, self.answers(a, 2))
        self.assertEqual(services.student_overview(self.student)["readiness"]["label"], "Needs more practice")

    def test_week_report_compares_with_previous_week(self):
        qs = self.mcq(self.t1, 2)
        now = timezone.now()
        monday = services.monday_of(timezone.localtime(now).date())
        self.finished(self.student, self.answers(qs, 2), when=now)
        self.finished(self.student, self.answers(qs, 1), when=now - timedelta(days=7))
        report = services.week_report(self.student, monday)
        self.assertEqual(report["summary"]["accuracy"], 100.0)
        self.assertEqual(report["previous"]["accuracy"], 50.0)
        self.assertEqual(report["change"], 50.0)
        self.assertEqual(report["attempts"][0]["title"], "Practice session")
        self.assertEqual(report["doing_well"][0]["topic"], self.t1)


class StudentViewTests(AnalyticsTestCase):
    def test_access_rules(self):
        self.assertEqual(self.client.get(reverse("progress")).status_code, 302)
        for user in (self.tpo, self.faculty):
            self.login(user)
            self.assertEqual(self.client.get(reverse("progress")).status_code, 403)
            self.assertEqual(self.client.get(reverse("weekly_report")).status_code, 403)

    def test_empty_state(self):
        self.login(self.student)
        page = self.client.get(reverse("progress"))
        self.assertContains(page, "Nothing to show yet")
        self.assertEqual(self.client.get(reverse("weekly_report")).status_code, 200)

    def test_progress_page_shows_numbers_and_explanation(self):
        qs = self.mcq(self.t1, 4)
        self.finished(self.student, self.answers(qs, 1))
        self.login(self.student)
        page = self.client.get(reverse("progress"))
        self.assertContains(page, "Needs work")
        self.assertContains(page, "25%")
        self.assertContains(page, "How this is calculated")
        self.assertContains(page, "Percentages")
        self.assertContains(page, "<svg")
        self.assertContains(page, f"?topic={self.t1.pk}")

    def test_students_only_see_their_own_data(self):
        other = make_user("other", "Student", consent=True)
        secret = Topic.objects.create(subject="Secret", name="Hidden topic")
        self.finished(other, self.answers(self.mcq(secret, 3), 3))
        self.login(self.student)
        self.assertNotContains(self.client.get(reverse("progress")), "Hidden topic")

    def test_weekly_report_navigation_and_clamping(self):
        qs = self.mcq(self.t1, 2)
        now = timezone.now()
        self.finished(self.student, self.answers(qs, 2), when=now)
        self.finished(self.student, self.answers(qs, 1), when=now - timedelta(days=7))
        self.login(self.student)
        current = self.client.get(reverse("weekly_report"))
        self.assertContains(current, "(this week)")
        self.assertContains(current, "up 50 points")
        self.assertContains(current, "Earlier week")
        self.assertNotContains(current, "Later week")
        last_monday = services.monday_of(timezone.localdate()) - timedelta(days=7)
        earlier = self.client.get(reverse("weekly_report"), {"week": last_monday.isoformat()})
        self.assertNotContains(earlier, "(this week)")
        self.assertContains(earlier, "Later week")
        future = self.client.get(reverse("weekly_report"), {"week": "2099-01-05"})
        self.assertContains(future, "(this week)")
        junk = self.client.get(reverse("weekly_report"), {"week": "not-a-date"})
        self.assertContains(junk, "(this week)")

    def test_weekly_report_shows_decline(self):
        qs = self.mcq(self.t1, 2)
        now = timezone.now()
        self.finished(self.student, self.answers(qs, 0), when=now)
        self.finished(self.student, self.answers(qs, 2), when=now - timedelta(days=7))
        self.login(self.student)
        self.assertContains(self.client.get(reverse("weekly_report")), "down 100 points")

    def test_practice_page_preselects_topic(self):
        self.login(self.student)
        page = self.client.get(reverse("practice_home"), {"topic": self.t2.pk})
        self.assertContains(page, f'<option value="{self.t2.pk}" selected>')

    def test_navigation_and_dashboard_links(self):
        self.login(self.student)
        dash = self.client.get(reverse("dashboard"))
        self.assertContains(dash, "View my progress")
        self.assertNotContains(dash, "Student reports")
        self.login(self.tpo)
        self.assertContains(self.client.get(reverse("dashboard")), "Student reports")


class TpoReportTests(AnalyticsTestCase):
    def setUp(self):
        super().setUp()
        self.a = make_user("alice", "Student", consent=True, first_name="Alice", last_name="A")
        self.b = make_user("bob", "Student", consent=True, first_name="Bob", last_name="B")
        self.c = make_user("carol", "Student", consent=False, first_name="Carol", last_name="C")
        self.q1, self.q2 = self.mcq(self.t1, 2), self.mcq(self.t2, 2)

    def test_access_rules(self):
        self.assertEqual(self.client.get(reverse("reports_home")).status_code, 302)
        for user in (self.student, self.faculty):
            self.login(user)
            for name in ("reports_home", "report_export"):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)
            self.assertEqual(self.client.get(reverse("report_student", args=[self.a.pk])).status_code, 403)
        self.login(self.tpo)
        self.assertEqual(self.client.get(reverse("reports_home")).status_code, 200)

    def test_cohort_numbers_exclude_students_without_consent(self):  # BR-10, BR-14
        self.finished(self.a, self.answers(self.q1, 2))                       # 100%
        self.finished(self.b, self.answers(self.q1, 1))                       # 50%
        self.finished(self.c, self.answers(self.q1, 0))                       # 0%, no consent
        report = reports.cohort_report()
        self.assertEqual(report["consenting_count"], 3)  # alice, bob and the setUp student
        self.assertEqual(report["total_students"], 4)
        self.assertEqual(report["average_accuracy"], 75.0)
        self.assertEqual(report["active_this_week"], 2)
        self.assertEqual(report["answered_total"], 4)
        names = [row["user"].username for row in report["rows"]]
        self.assertNotIn("carol", names)

    def test_topic_table_is_weakest_first_and_averaged(self):
        self.finished(self.a, self.answers(self.q1, 2) + self.answers(self.q2, 0))
        self.finished(self.b, self.answers(self.q1, 1) + self.answers(self.q2, 2))
        table = reports.cohort_report()["topic_table"]
        self.assertEqual([(r["topic"].name, r["average"], r["students"]) for r in table],
                         [("Arrays", 50.0, 2), ("Percentages", 75.0, 2)])

    def test_inactive_list(self):
        self.finished(self.a, self.answers(self.q1, 1), when=timezone.now() - timedelta(days=20))
        self.finished(self.b, self.answers(self.q1, 1))
        inactive = [row["user"].username for row in reports.cohort_report()["inactive"]]
        self.assertIn("alice", inactive)
        self.assertNotIn("bob", inactive)
        self.assertIn("stu", inactive)  # consenting student who never finished anything

    def test_report_page_text(self):
        self.finished(self.a, self.answers(self.q1, 2))
        self.login(self.tpo)
        page = self.client.get(reverse("reports_home"))
        self.assertContains(page, "3 of 4 students have consented")
        self.assertContains(page, "Alice A")
        self.assertNotContains(page, "Carol C")

    def test_individual_report_requires_consent(self):
        self.finished(self.c, self.answers(self.q1, 2))
        self.finished(self.a, self.answers(self.q1, 2))
        self.login(self.tpo)
        denied = self.client.get(reverse("report_student", args=[self.c.pk]))
        self.assertContains(denied, "No consent given")
        self.assertNotContains(denied, "Questions answered")
        allowed = self.client.get(reverse("report_student", args=[self.a.pk]))
        self.assertContains(allowed, "Questions answered")
        self.assertContains(allowed, "Percentages")

    def test_individual_report_only_for_students(self):
        self.login(self.tpo)
        self.assertEqual(self.client.get(reverse("report_student", args=[self.faculty.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("report_student", args=[9999])).status_code, 404)

    def test_csv_export(self):
        self.finished(self.a, self.answers(self.q1, 2))
        self.finished(self.c, self.answers(self.q1, 2))
        self.login(self.tpo)
        response = self.client.get(reverse("report_export"))
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment", response["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(rows[0][0], "Student")
        usernames = [r[1] for r in rows[1:]]
        self.assertIn("alice", usernames)
        self.assertNotIn("carol", usernames)
        alice = next(r for r in rows if r[1] == "alice")
        self.assertEqual(alice[4], "100.0")

    def test_csv_neutralises_spreadsheet_formulas(self):
        evil = make_user("evil", "Student", consent=True, first_name="=HYPERLINK(1)", last_name="x")
        self.login(self.tpo)
        rows = list(csv.reader(io.StringIO(self.client.get(reverse("report_export")).content.decode())))
        cell = next(r[0] for r in rows if r[1] == "evil")
        self.assertTrue(cell.startswith("'="))
