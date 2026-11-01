from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from analytics.models import ProgressMetric
from content.models import ContentStatus, Question, Topic

from .models import Assessment, AssessmentQuestion, Attempt, Response

PASSWORD = "Str0ng-Pass-123"
FAST_HASH = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def make_user(username, role_name):
    role = Role.objects.get_or_create(role_name=role_name)[0]
    return User.objects.create_user(
        username, email=f"{username}@example.com", password=PASSWORD, role=role
    )


@override_settings(PASSWORD_HASHERS=FAST_HASH)
class TimedTestCase(TestCase):
    def setUp(self):
        self.student = make_user("stu", "Student")
        self.other = make_user("other", "Student")
        self.tpo = make_user("tpo", "TPO")
        self.faculty = make_user("fac", "Faculty")
        self.percent = Topic.objects.create(subject="Aptitude", name="Percentages")
        self.arrays = Topic.objects.create(subject="Data Structures", name="Arrays")
        self.q1 = self.mcq("What is 10% of 200?", self.percent, ["10", "20", "30"], "20")
        self.q2 = self.mcq("What is 50% of 50?", self.percent, ["20", "25", "30"], "25")
        self.q3 = self.mcq("Array index access is?", self.arrays, ["O(1)", "O(n)"], "O(1)")
        self.exam = self.assessment("Mock 1", [(self.q1, 2), (self.q2, 3), (self.q3, 5)], duration=30)

    def mcq(self, text, topic, options, answer, status="published"):
        return Question.objects.create(
            topic=topic, type="aptitude", text=text, options=options, answer=answer,
            explanation=f"Explanation for: {text}", status=status,
        )

    def assessment(self, title, items, duration=30, status="published", created_by=None):
        exam = Assessment.objects.create(title=title, duration=duration, status=status, created_by=created_by)
        for order, (question, marks) in enumerate(items, start=1):
            AssessmentQuestion.objects.create(assessment=exam, question=question, marks=marks, display_order=order)
        return exam

    def login(self, user):
        self.client.logout()
        self.client.login(username=user.username, password=PASSWORD)

    def start(self, exam=None):
        self.login(self.student)
        self.client.post(reverse("assessment_start", args=[(exam or self.exam).pk]))
        return Attempt.objects.filter(user=self.student).latest("id")

    def expire(self, attempt):
        Attempt.objects.filter(pk=attempt.pk).update(expires_at=timezone.now() - timedelta(minutes=1))

    def save_answer(self, attempt, question, answer):
        return self.client.post(
            reverse("attempt_save", args=[attempt.pk]), {"question_id": question.pk, "answer": answer}
        )

    def submit(self, attempt, **answers):
        data = {f"q_{q.pk}": a for q, a in answers.items()} if answers else {}
        return self.client.post(reverse("attempt_submit", args=[attempt.pk]), data)


class AccessAndListTests(TimedTestCase):
    def test_login_and_role_required(self):
        self.assertEqual(self.client.get(reverse("assessment_list")).status_code, 302)
        self.login(self.tpo)
        self.assertEqual(self.client.get(reverse("assessment_list")).status_code, 403)
        self.login(self.student)
        self.assertContains(self.client.get(reverse("assessment_list")), "Mock 1")

    def test_only_published_assessments_with_questions_are_listed(self):
        self.assessment("Hidden draft", [(self.q1, 1)], status="draft")
        Assessment.objects.create(title="Empty one", duration=10, status="published")
        self.login(self.student)
        page = self.client.get(reverse("assessment_list"))
        self.assertContains(page, "Mock 1")
        self.assertNotContains(page, "Hidden draft")
        self.assertNotContains(page, "Empty one")

    def test_cannot_start_unpublished_or_empty_assessment(self):
        draft = self.assessment("Draft exam", [(self.q1, 1)], status="draft")
        empty = Assessment.objects.create(title="Empty", duration=10, status="published")
        self.login(self.student)
        self.assertEqual(self.client.post(reverse("assessment_start", args=[draft.pk])).status_code, 404)
        self.client.post(reverse("assessment_start", args=[empty.pk]))
        self.assertEqual(Attempt.objects.count(), 0)

    def test_start_requires_post(self):
        self.login(self.student)
        self.assertEqual(self.client.get(reverse("assessment_start", args=[self.exam.pk])).status_code, 405)


class StartAndTakeTests(TimedTestCase):
    def test_start_creates_timed_attempt(self):
        attempt = self.start()
        self.assertEqual(attempt.attempt_type, "assessment")
        self.assertEqual(attempt.status, "in_progress")
        self.assertEqual(attempt.expires_at - attempt.started_at, timedelta(minutes=30))
        self.assertEqual(attempt.responses.count(), 3)  # BR-5: recorded from the start

    def test_starting_again_resumes_the_same_attempt(self):
        first = self.start()
        second = self.start()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Attempt.objects.count(), 1)

    def test_retake_after_finishing_creates_new_attempt(self):
        first = self.start()
        self.submit(first)
        second = self.start()
        self.assertNotEqual(first.pk, second.pk)

    def test_take_page_shows_questions_in_order_without_answers(self):
        attempt = self.start()
        page = self.client.get(reverse("attempt_take", args=[attempt.pk]))
        content = page.content.decode()
        self.assertLess(content.index("What is 10% of 200?"), content.index("What is 50% of 50?"))
        self.assertContains(page, "2 marks")
        self.assertNotContains(page, "Explanation for")  # BR-11
        self.assertRegex(page.content.decode(), r"var remaining = (1800|179\d);")

    def test_other_student_and_practice_attempts_are_not_accessible(self):
        attempt = self.start()
        practice = Attempt.objects.create(user=self.student, attempt_type="practice", status="in_progress")
        self.login(self.other)
        for name in ("attempt_take", "attempt_result"):
            self.assertEqual(self.client.get(reverse(name, args=[attempt.pk])).status_code, 404)
        self.assertEqual(self.save_answer(attempt, self.q1, "20").status_code, 404)
        self.login(self.student)
        self.assertEqual(self.client.get(reverse("attempt_take", args=[practice.pk])).status_code, 404)


class AutosaveTests(TimedTestCase):
    def test_autosave_stores_answer_and_resume_shows_it_selected(self):
        attempt = self.start()
        response = self.save_answer(attempt, self.q1, "20")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["saved"])
        self.assertGreater(response.json()["remaining"], 1700)
        self.assertEqual(Response.objects.get(attempt=attempt, question=self.q1).answer, "20")
        page = self.client.get(reverse("attempt_take", args=[attempt.pk]))
        self.assertContains(page, 'value="20" checked')

    def test_autosave_rejects_unknown_question_and_bad_input(self):
        attempt = self.start()
        stranger = self.mcq("Not in this exam", self.arrays, ["a", "b"], "a")
        self.assertEqual(self.save_answer(attempt, stranger, "a").status_code, 400)
        bad = self.client.post(reverse("attempt_save", args=[attempt.pk]), {"question_id": "x", "answer": "a"})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.client.get(reverse("attempt_save", args=[attempt.pk])).status_code, 405)

    def test_autosave_after_deadline_is_refused_and_attempt_times_out(self):
        attempt = self.start()
        self.save_answer(attempt, self.q1, "20")
        self.expire(attempt)
        response = self.save_answer(attempt, self.q2, "25")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()["expired"])
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "evaluated")
        self.assertTrue(attempt.timed_out)
        self.assertEqual(Response.objects.get(attempt=attempt, question=self.q2).answer, "")  # not saved
        self.assertEqual(attempt.score, 2.0)  # only the answer saved in time


class SubmitTests(TimedTestCase):
    def test_submitting_with_no_answers_scores_zero(self):
        attempt = self.start()
        self.submit(attempt)  # nothing posted
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 0.0)

    def test_submit_before_deadline_saves_posted_answers_and_scores(self):
        attempt = self.start()
        response = self.client.post(
            reverse("attempt_submit", args=[attempt.pk]),
            {f"q_{self.q1.pk}": "20", f"q_{self.q2.pk}": "30", f"q_{self.q3.pk}": "O(1)"},
        )
        self.assertRedirects(response, reverse("attempt_result", args=[attempt.pk]), fetch_redirect_response=False)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "evaluated")
        self.assertFalse(attempt.timed_out)
        self.assertEqual(attempt.score, 7.0)  # 2 + 0 + 5
        self.assertIsNotNone(attempt.submitted_at)
        by_q = {r.question_id: r for r in attempt.responses.all()}
        self.assertEqual(by_q[self.q1.pk].marks_awarded, 2.0)
        self.assertFalse(by_q[self.q2.pk].is_correct)
        self.assertEqual(by_q[self.q3.pk].marks_awarded, 5.0)

    def test_submit_after_deadline_ignores_posted_answers_and_uses_saved_ones(self):  # BR-6
        attempt = self.start()
        self.save_answer(attempt, self.q1, "20")      # saved in time: 2 marks
        self.expire(attempt)
        self.client.post(
            reverse("attempt_submit", args=[attempt.pk]),
            {f"q_{self.q2.pk}": "25", f"q_{self.q3.pk}": "O(1)"},  # too late: must be ignored
        )
        attempt.refresh_from_db()
        self.assertTrue(attempt.timed_out)
        self.assertEqual(attempt.status, "evaluated")
        self.assertEqual(attempt.score, 2.0)
        self.assertEqual(attempt.submitted_at, attempt.expires_at)

    def test_no_second_submission_and_no_going_back(self):  # BR-7
        attempt = self.start()
        self.client.post(reverse("attempt_submit", args=[attempt.pk]), {f"q_{self.q1.pk}": "20"})
        self.client.post(reverse("attempt_submit", args=[attempt.pk]), {f"q_{self.q1.pk}": "10", f"q_{self.q3.pk}": "O(1)"})
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 2.0)
        self.assertEqual(self.save_answer(attempt, self.q3, "O(1)").status_code, 409)
        self.assertEqual(Response.objects.get(attempt=attempt, question=self.q3).answer, "")
        with self.assertRaises(ValueError):
            attempt.change_status("in_progress")

    def test_time_is_split_across_responses(self):
        attempt = self.start()
        Attempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - timedelta(minutes=9))
        self.submit(attempt)
        self.assertTrue(all(r.time_taken_seconds >= 179 for r in attempt.responses.all()))


class ExpiryTests(TimedTestCase):
    def test_opening_expired_attempt_finalizes_it(self):
        attempt = self.start()
        self.save_answer(attempt, self.q3, "O(1)")
        self.expire(attempt)
        response = self.client.get(reverse("attempt_take", args=[attempt.pk]))
        self.assertRedirects(response, reverse("attempt_result", args=[attempt.pk]), fetch_redirect_response=False)
        attempt.refresh_from_db()
        self.assertTrue(attempt.timed_out)
        self.assertEqual(attempt.score, 5.0)

    def test_assessment_list_times_out_abandoned_attempts(self):
        attempt = self.start()
        self.expire(attempt)
        self.client.get(reverse("assessment_list"))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "evaluated")
        self.assertTrue(attempt.timed_out)

    def test_starting_after_abandoned_attempt_closes_old_and_creates_new(self):
        old = self.start()
        self.expire(old)
        new = self.start()
        old.refresh_from_db()
        self.assertTrue(old.timed_out)
        self.assertNotEqual(old.pk, new.pk)
        self.assertEqual(new.status, "in_progress")

    def test_management_command_finalizes_expired_attempts(self):
        attempt = self.start()
        self.expire(attempt)
        call_command("finalize_expired_attempts", verbosity=0)
        attempt.refresh_from_db()
        self.assertTrue(attempt.timed_out)
        self.assertEqual(attempt.status, "evaluated")

    def test_unexpired_attempts_are_left_alone(self):
        attempt = self.start()
        call_command("finalize_expired_attempts", verbosity=0)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "in_progress")


class ResultTests(TimedTestCase):
    def test_result_is_blocked_while_attempt_is_open(self):  # BR-11
        attempt = self.start()
        response = self.client.get(reverse("attempt_result", args=[attempt.pk]))
        self.assertRedirects(response, reverse("attempt_take", args=[attempt.pk]), fetch_redirect_response=False)

    def test_result_shows_feedback_and_marks_reviewed(self):
        attempt = self.start()
        self.client.post(reverse("attempt_submit", args=[attempt.pk]),
                         {f"q_{self.q1.pk}": "20", f"q_{self.q2.pk}": "30"})
        page = self.client.get(reverse("attempt_result", args=[attempt.pk]))
        self.assertContains(page, "2 of 10 marks")
        self.assertContains(page, "(20%)")
        self.assertContains(page, "Explanation for: What is 10% of 200?")
        self.assertContains(page, "Topics to revisit")
        self.assertContains(page, "Percentages")
        self.assertContains(page, "1 unanswered")
        self.assertNotContains(page, "time limit was reached")
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "reviewed")
        self.assertEqual(self.client.get(reverse("attempt_result", args=[attempt.pk])).status_code, 200)

    def test_timed_out_result_explains_what_happened(self):
        attempt = self.start()
        self.expire(attempt)
        page = self.client.get(reverse("attempt_result", args=[attempt.pk]))
        self.assertContains(page, "time limit was reached")

    def test_history_lists_finished_attempts(self):
        attempt = self.start()
        self.submit(attempt)
        page = self.client.get(reverse("assessment_list"))
        self.assertContains(page, "View feedback")
        self.assertContains(page, "Submitted")


class MetricsTests(TimedTestCase):
    def test_metrics_follow_stored_attempts(self):  # BR-8
        attempt = self.start()
        self.client.post(reverse("attempt_submit", args=[attempt.pk]),
                         {f"q_{self.q1.pk}": "20", f"q_{self.q2.pk}": "30", f"q_{self.q3.pk}": "O(1)"})
        percent = ProgressMetric.objects.get(user=self.student, topic=self.percent)
        self.assertEqual(percent.accuracy, 50.0)
        self.assertEqual(percent.attempts, 1)
        arrays = ProgressMetric.objects.get(user=self.student, topic=self.arrays)
        self.assertEqual(arrays.accuracy, 100.0)

        second = self.start()  # retake, all wrong on percentages
        self.client.post(reverse("attempt_submit", args=[second.pk]),
                         {f"q_{self.q1.pk}": "10", f"q_{self.q2.pk}": "20"})
        percent.refresh_from_db()
        self.assertEqual(percent.attempts, 2)
        self.assertEqual(percent.accuracy, 25.0)  # 1 correct out of 4 answers
        self.assertEqual(ProgressMetric.objects.filter(user=self.student, topic=self.percent).count(), 1)

    def test_practice_sessions_also_update_metrics_and_open_only_topics_are_skipped(self):
        coding_topic = Topic.objects.create(subject="Coding", name="Loops")
        open_q = Question.objects.create(topic=coding_topic, type="coding", text="Write a loop", status="published")
        self.login(self.student)
        self.client.post(reverse("practice_start"), {"count": "5", "topic": coding_topic.pk})
        practice = Attempt.objects.get(user=self.student, attempt_type="practice")
        self.client.post(reverse("practice_session", args=[practice.pk]), {f"q_{open_q.pk}": "for i in x: pass"})
        self.assertFalse(ProgressMetric.objects.filter(user=self.student, topic=coding_topic).exists())
        self.client.post(reverse("practice_start"), {"count": "5", "topic": self.percent.pk})
        practice2 = Attempt.objects.filter(user=self.student, attempt_type="practice").latest("id")
        self.client.post(reverse("practice_session", args=[practice2.pk]), {f"q_{self.q1.pk}": "20", f"q_{self.q2.pk}": "25"})
        self.assertEqual(ProgressMetric.objects.get(user=self.student, topic=self.percent).accuracy, 100.0)


class ManagementTests(TimedTestCase):
    def form_data(self, **overrides):
        data = {"title": "New mock", "type": "mixed", "duration": 20, "marks_per_question": 2,
                "questions": [self.q1.pk, self.q3.pk]}
        data.update(overrides)
        return data

    def test_students_cannot_manage_assessments(self):
        self.login(self.student)
        for name in ("manage_assessments", "assessment_create"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_create_form_offers_only_published_mcq_questions(self):
        draft_q = self.mcq("Draft question text", self.percent, ["a", "b"], "a", status="draft")
        open_q = Question.objects.create(topic=self.arrays, type="coding", text="Open coding question", status="published")
        self.login(self.tpo)
        page = self.client.get(reverse("assessment_create"))
        self.assertContains(page, "What is 10% of 200?")
        self.assertNotContains(page, "Draft question text")
        self.assertNotContains(page, "Open coding question")

    def test_create_saves_draft_with_marks_and_order(self):
        self.login(self.faculty)
        self.client.post(reverse("assessment_create"), self.form_data())
        exam = Assessment.objects.get(title="New mock")
        self.assertEqual(exam.status, "draft")
        self.assertEqual(exam.created_by, self.faculty)
        links = list(exam.assessmentquestion_set.order_by("display_order"))
        self.assertEqual([l.question for l in links], [self.q1, self.q3])
        self.assertEqual([l.marks for l in links], [2, 2])

    def test_invalid_duration_or_no_questions_rejected(self):
        self.login(self.tpo)
        self.client.post(reverse("assessment_create"), self.form_data(duration=0))
        self.client.post(reverse("assessment_create"), self.form_data(questions=[]))
        self.assertEqual(Assessment.objects.filter(title="New mock").count(), 0)

    def test_workflow_faculty_submits_tpo_publishes_student_sees(self):
        self.login(self.faculty)
        self.client.post(reverse("assessment_create"), self.form_data())
        exam = Assessment.objects.get(title="New mock")
        url = reverse("assessment_transition", args=[exam.pk])
        self.client.post(url, {"to": "pending_review"})
        self.assertEqual(self.client.post(url, {"to": "published"}).status_code, 403)
        self.login(self.student)
        self.assertNotContains(self.client.get(reverse("assessment_list")), "New mock")
        self.login(self.tpo)
        self.client.post(url, {"to": "published"})
        exam.refresh_from_db()
        self.assertEqual(exam.status, "published")
        self.login(self.student)
        self.assertContains(self.client.get(reverse("assessment_list")), "New mock")

    def test_cannot_publish_without_questions(self):
        empty = Assessment.objects.create(title="Empty draft", duration=10, status="draft", created_by=self.tpo)
        self.login(self.tpo)
        self.client.post(reverse("assessment_transition", args=[empty.pk]), {"to": "published"})
        empty.refresh_from_db()
        self.assertEqual(empty.status, "draft")

    def test_edit_updates_questions_before_any_attempt(self):
        self.login(self.tpo)
        self.client.post(reverse("assessment_edit", args=[self.exam.pk]),
                         self.form_data(title="Mock 1 renamed", questions=[self.q2.pk]))
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.title, "Mock 1 renamed")
        self.assertEqual(list(self.exam.assessmentquestion_set.values_list("question", flat=True)), [self.q2.pk])

    def test_editing_is_locked_after_students_have_attempted(self):
        self.start()
        self.login(self.tpo)
        page = self.client.get(reverse("assessment_edit", args=[self.exam.pk]))
        self.assertContains(page, "locked")
        self.assertNotContains(page, 'name="questions"')
        self.client.post(reverse("assessment_edit", args=[self.exam.pk]), {"title": "Renamed only", "type": "mixed"})
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.title, "Renamed only")
        self.assertEqual(self.exam.assessmentquestion_set.count(), 3)
        self.assertEqual(self.exam.duration, 30)

    def test_faculty_cannot_edit_published_or_others_assessments(self):
        self.login(self.faculty)
        self.assertEqual(self.client.get(reverse("assessment_edit", args=[self.exam.pk])).status_code, 403)

    def test_management_pages_and_navigation(self):
        self.login(self.tpo)
        self.assertEqual(self.client.get(reverse("manage_assessments")).status_code, 200)
        self.assertEqual(self.client.get(reverse("manage_assessments"), {"status": "published"}).status_code, 200)
        self.assertContains(self.client.get(reverse("manage_home")), "Manage assessments")
        self.login(self.student)
        self.assertContains(self.client.get(reverse("dashboard")), "View assessments")
