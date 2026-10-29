from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User
from content.models import Company, Question, Topic

from .evaluation import evaluate, normalise
from .models import Attempt, Response

PASSWORD = "Str0ng-Pass-123"


def make_user(username, role_name):
    role = Role.objects.get_or_create(role_name=role_name)[0]
    return User.objects.create_user(
        username, email=f"{username}@example.com", password=PASSWORD, role=role
    )


class PracticeTestCase(TestCase):
    def setUp(self):
        self.student = make_user("stu", "Student")
        self.other = make_user("other", "Student")
        self.tpo = make_user("tpo", "TPO")
        self.percent = Topic.objects.create(subject="Aptitude", name="Percentages", difficulty="easy")
        self.arrays = Topic.objects.create(subject="Data Structures", name="Arrays", difficulty="hard")

    def login(self, user):
        self.client.login(username=user.username, password=PASSWORD)

    def mcq(self, text="What is 10% of 200?", topic=None, status="published", **kw):
        return Question.objects.create(
            topic=topic or self.percent, type="aptitude", text=text,
            options=["10", "20", "30"], answer="20", explanation="10% of 200 is 20.",
            status=status, **kw,
        )

    def open_q(self, text="Reverse an array.", topic=None, status="published"):
        return Question.objects.create(
            topic=topic or self.arrays, type="coding", difficulty="hard", text=text,
            answer="Swap from both ends.", explanation="Two-pointer technique.", status=status,
        )

    def start(self, **data):
        payload = {"count": "10"}
        payload.update(data)
        return self.client.post(reverse("practice_start"), payload)


class EvaluationTests(PracticeTestCase):
    def test_normalise_ignores_case_and_spaces(self):
        self.assertEqual(normalise("  Hello   World "), "hello world")

    def test_mcq_correct_incorrect_blank_and_open(self):
        q = self.mcq()
        self.assertEqual(evaluate(q, "20"), (True, 1.0))
        self.assertEqual(evaluate(q, " 20 "), (True, 1.0))
        self.assertEqual(evaluate(q, "30"), (False, 0.0))
        self.assertEqual(evaluate(q, ""), (False, 0.0))
        self.assertEqual(evaluate(self.open_q(), "anything"), (None, 0.0))


class AccessTests(PracticeTestCase):
    def test_roles_and_login(self):
        self.assertEqual(self.client.get(reverse("practice_home")).status_code, 302)
        self.login(self.tpo)
        self.assertEqual(self.client.get(reverse("practice_home")).status_code, 403)
        self.client.logout(); self.login(self.student)
        self.assertEqual(self.client.get(reverse("practice_home")).status_code, 200)

    def test_start_requires_post(self):
        self.login(self.student)
        self.assertEqual(self.client.get(reverse("practice_start")).status_code, 405)


class StartTests(PracticeTestCase):
    def test_start_creates_in_progress_practice_attempt_with_published_questions_only(self):
        good, bad = self.mcq("Visible"), self.mcq("Hidden", status="draft")
        self.login(self.student)
        response = self.start()
        attempt = Attempt.objects.get(user=self.student)
        self.assertRedirects(response, reverse("practice_session", args=[attempt.pk]))
        self.assertEqual(attempt.attempt_type, "practice")
        self.assertEqual(attempt.status, "in_progress")
        self.assertIsNotNone(attempt.started_at)
        self.assertEqual([r.question for r in attempt.responses.all()], [good])
        self.assertNotIn(bad, [r.question for r in attempt.responses.all()])

    def test_no_matching_questions(self):
        self.mcq(status="draft")
        self.login(self.student)
        response = self.start()
        self.assertRedirects(response, reverse("practice_home"))
        self.assertEqual(Attempt.objects.count(), 0)

    def test_filters_and_count_limit(self):
        for i in range(6):
            self.mcq(f"Percent {i}")
        self.open_q("Array question")
        self.login(self.student)
        self.start(topic=self.arrays.pk)
        self.assertEqual([r.question.text for r in Attempt.objects.latest("id").responses.all()], ["Array question"])
        self.start(type="aptitude", count="5")
        self.assertEqual(Attempt.objects.latest("id").responses.count(), 5)
        self.start(difficulty="hard")
        self.assertEqual(Attempt.objects.latest("id").responses.get().question.type, "coding")

    def test_company_filter_uses_published_companies(self):
        company = Company.objects.create(name="Acme", source="x", status="published")
        self.mcq("For Acme", company=company); self.mcq("Generic")
        self.login(self.student)
        self.start(company=company.pk)
        self.assertEqual([r.question.text for r in Attempt.objects.latest("id").responses.all()], ["For Acme"])

    def test_home_lists_history(self):
        self.mcq()
        self.login(self.student)
        self.start()
        self.assertContains(self.client.get(reverse("practice_home")), "Continue")


class SessionTests(PracticeTestCase):
    def setUp(self):
        super().setUp()
        self.q1, self.q2, self.q3 = self.mcq("Q one"), self.mcq("Q two"), self.open_q("Q open")
        self.login(self.student)
        self.start()
        self.attempt = Attempt.objects.get(user=self.student)

    def answers(self, q1="20", q2="30", q3="my solution"):
        return {f"q_{self.q1.pk}": q1, f"q_{self.q2.pk}": q2, f"q_{self.q3.pk}": q3}

    def test_session_page_shows_questions_but_no_answers(self):
        response = self.client.get(reverse("practice_session", args=[self.attempt.pk]))
        for text in ("Q one", "Q two", "Q open"):
            self.assertContains(response, text)
        self.assertNotContains(response, "10% of 200 is 20")  # BR-11

    def test_result_is_blocked_before_submission(self):
        response = self.client.get(reverse("practice_result", args=[self.attempt.pk]))
        self.assertRedirects(response, reverse("practice_session", args=[self.attempt.pk]))

    def test_submit_records_evaluates_and_scores(self):
        response = self.client.post(reverse("practice_session", args=[self.attempt.pk]), self.answers())
        self.assertRedirects(
            response, reverse("practice_result", args=[self.attempt.pk]), fetch_redirect_response=False
        )
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "evaluated")  # becomes Reviewed once the result is opened
        self.assertIsNotNone(self.attempt.submitted_at)
        self.assertEqual(self.attempt.score, 1.0)
        by_q = {r.question_id: r for r in self.attempt.responses.all()}  # BR-5: stored
        self.assertTrue(by_q[self.q1.pk].is_correct)
        self.assertFalse(by_q[self.q2.pk].is_correct)
        self.assertIsNone(by_q[self.q3.pk].is_correct)
        self.assertEqual(by_q[self.q3.pk].answer, "my solution")

    def test_unanswered_mcq_counts_as_incorrect(self):
        self.client.post(reverse("practice_session", args=[self.attempt.pk]), {})
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.score, 0.0)
        self.assertFalse(self.attempt.responses.get(question=self.q1).is_correct)

    def test_result_shows_feedback_and_marks_reviewed(self):
        self.client.post(reverse("practice_session", args=[self.attempt.pk]), self.answers())
        response = self.client.get(reverse("practice_result", args=[self.attempt.pk]))
        self.assertContains(response, "10% of 200 is 20")
        self.assertContains(response, "Two-pointer technique")
        self.assertContains(response, "1 of 2 auto-checked")
        self.assertContains(response, "Topics to revisit")
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "reviewed")
        self.assertEqual(self.client.get(reverse("practice_result", args=[self.attempt.pk])).status_code, 200)

    def test_cannot_resubmit_or_reopen_after_submission(self):  # BR-7
        url = reverse("practice_session", args=[self.attempt.pk])
        self.client.post(url, self.answers())
        self.client.post(url, self.answers(q1="10", q2="10", q3="changed"))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.score, 1.0)
        self.assertEqual(self.attempt.responses.get(question=self.q3).answer, "my solution")
        self.assertRedirects(self.client.get(url), reverse("practice_result", args=[self.attempt.pk]))
        with self.assertRaises(ValueError):
            self.attempt.change_status("in_progress")

    def test_other_students_cannot_open_the_session(self):
        self.client.logout(); self.login(self.other)
        for name in ("practice_session", "practice_result"):
            self.assertEqual(self.client.get(reverse(name, args=[self.attempt.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("practice_session", args=[self.attempt.pk]), self.answers()).status_code, 404)
        self.attempt.refresh_from_db(); self.assertEqual(self.attempt.status, "in_progress")

    def test_time_is_stored_per_response(self):
        self.client.post(reverse("practice_session", args=[self.attempt.pk]), self.answers())
        self.assertTrue(all(r.time_taken_seconds >= 0 for r in Response.objects.filter(attempt=self.attempt)))
