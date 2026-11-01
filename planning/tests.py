from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, StudentProfile, User
from assessments import services as attempt_services
from assessments.models import Assessment, AssessmentQuestion, Attempt, Response
from content.models import Question, Topic

from . import services
from .forms import GoalForm
from .models import Recommendation, WeeklyGoal

PASSWORD = "Str0ng-Pass-123"
FAST_HASH = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def make_user(username, role_name, consent=None):
    role = Role.objects.get_or_create(role_name=role_name)[0]
    user = User.objects.create_user(username, email=f"{username}@example.com", password=PASSWORD, role=role)
    if role_name == "Student":
        StudentProfile.objects.create(user=user, consent_given=bool(consent))
    return user


@override_settings(PASSWORD_HASHERS=FAST_HASH)
class PlanningTestCase(TestCase):
    def setUp(self):
        self.student = make_user("stu", "Student", consent=True)
        self.other = make_user("other", "Student", consent=True)
        self.tpo = make_user("tpo", "TPO")
        self.today = timezone.localdate()
        self.easy = Topic.objects.create(subject="Aptitude", name="Percentages", difficulty="easy")
        self.medium = Topic.objects.create(subject="Verbal", name="Grammar", difficulty="medium")
        self.hard = Topic.objects.create(subject="Data Structures", name="Arrays", difficulty="hard")
        self.questions = {t: self.mcq(t, 5) for t in (self.easy, self.medium, self.hard)}

    def login(self, user):
        self.client.logout()
        self.client.login(username=user.username, password=PASSWORD)

    def mcq(self, topic, n):
        return [
            Question.objects.create(topic=topic, type="aptitude", text=f"{topic.name} Q{i}",
                                    options=["a", "b"], answer="a", status="published")
            for i in range(n)
        ]

    def finished(self, user, topic, correct, wrong=0, when=None):
        """Finished attempt with `correct` right and `wrong` wrong answers in one topic."""
        when = when or timezone.now()
        qs = self.questions.setdefault(topic, [])
        if len(qs) < correct + wrong:
            qs.extend(self.mcq(topic, correct + wrong - len(qs)))
        attempt = Attempt.objects.create(user=user, attempt_type="practice", status="evaluated",
                                         started_at=when - timedelta(minutes=5), submitted_at=when)
        for i in range(correct + wrong):
            ok = i < correct
            Response.objects.create(attempt=attempt, question=qs[i], answer="a" if ok else "b",
                                    is_correct=ok, marks_awarded=1.0 if ok else 0.0, time_taken_seconds=30)
        return attempt

    def goal(self, topic=None, due=None, target=5, status="planned", user=None):
        return WeeklyGoal.objects.create(user=user or self.student, topic=topic or self.easy,
                                         due_date=due or self.today, target=target, status=status)


class StarterRecommendationTests(PlanningTestCase):
    def test_new_student_gets_general_starting_suggestions_easiest_first(self):  # BR-12
        items = services.build_recommendations(self.student)
        self.assertEqual([i["topic"] for i in items], [self.easy, self.medium, self.hard])
        self.assertTrue(all("just getting started" in i["reason"] for i in items))

    def test_every_recommendation_has_a_reason(self):  # BR-9
        for user_state in ("new", "experienced"):
            if user_state == "experienced":
                self.finished(self.student, self.easy, 1, 4)
                self.finished(self.student, self.medium, 3, 2)
            for item in services.build_recommendations(self.student):
                self.assertTrue(item["reason"].strip())

    def test_still_starting_below_ten_scored_answers(self):
        self.finished(self.student, self.easy, 5)
        self.assertTrue(services.is_starting(self.student))
        self.finished(self.student, self.medium, 5)
        self.assertFalse(services.is_starting(self.student))

    def test_no_published_questions_means_no_recommendations(self):
        Question.objects.update(status="draft")
        self.assertEqual(services.build_recommendations(self.student), [])

    def test_starter_topics_are_limited_to_three(self):
        extra = Topic.objects.create(subject="Python", name="Basics", difficulty="easy")
        self.mcq(extra, 2)
        self.assertEqual(len(services.build_recommendations(self.student)), 3)


class PersonalRecommendationTests(PlanningTestCase):
    def test_weak_then_developing_then_uncovered_and_strong_excluded(self):
        self.finished(self.student, self.easy, 1, 4)    # 20%  -> weak
        self.finished(self.student, self.medium, 3, 2)  # 60%  -> developing
        self.finished(self.student, self.hard, 5, 0)    # 100% -> strong
        items = services.build_recommendations(self.student)
        self.assertEqual([i["topic"] for i in items], [self.easy, self.medium])
        self.assertIn("20%", items[0]["reason"])
        self.assertIn("5 scored answers", items[0]["reason"])
        self.assertIn("60%", items[1]["reason"])

    def test_weakest_topic_comes_first(self):
        self.finished(self.student, self.easy, 2, 3)    # 40%
        self.finished(self.student, self.medium, 1, 4)  # 20%
        self.finished(self.student, self.hard, 0, 5)    # 0%
        items = services.build_recommendations(self.student)
        self.assertEqual([i["topic"] for i in items], [self.hard, self.medium, self.easy])

    def test_untried_and_thin_topics_are_suggested_last(self):
        self.finished(self.student, self.easy, 5, 5)    # 50% developing, 10 answers
        self.finished(self.student, self.medium, 1, 1)  # 2 answers: not enough data
        items = services.build_recommendations(self.student)
        self.assertEqual([i["topic"] for i in items], [self.easy, self.medium, self.hard])
        self.assertIn("fewer than 3", items[1]["reason"])
        self.assertIn("not practised", items[2]["reason"])

    def test_all_strong_gives_no_recommendations(self):
        for topic in (self.easy, self.medium, self.hard):
            self.finished(self.student, topic, 5)
        self.assertEqual(services.build_recommendations(self.student), [])

    def test_only_own_results_are_used(self):
        self.finished(self.other, self.easy, 0, 10)
        self.assertTrue(services.is_starting(self.student))

    def test_unfinished_attempts_do_not_count(self):
        attempt = self.finished(self.student, self.easy, 0, 10)
        Attempt.objects.filter(pk=attempt.pk).update(status="in_progress")
        self.assertTrue(services.is_starting(self.student))

    def test_recommendation_count_is_capped(self):
        topics = [Topic.objects.create(subject="S", name=f"T{i}", difficulty="easy") for i in range(8)]
        for t in topics:
            self.mcq(t, 3)
        self.finished(self.student, self.easy, 10)
        self.assertEqual(len(services.build_recommendations(self.student)), services.MAX_RECOMMENDATIONS)


class RefreshTests(PlanningTestCase):
    def test_refresh_replaces_old_set_with_sequential_priorities(self):
        services.refresh_recommendations(self.student)
        first = list(Recommendation.objects.filter(user=self.student).values_list("topic_id", flat=True))
        services.refresh_recommendations(self.student)
        rows = list(Recommendation.objects.filter(user=self.student).order_by("priority"))
        self.assertEqual(len(rows), len(first))
        self.assertEqual([r.priority for r in rows], list(range(1, len(rows) + 1)))

    def test_refresh_does_not_touch_other_students(self):
        services.refresh_recommendations(self.other)
        count = Recommendation.objects.filter(user=self.other).count()
        services.refresh_recommendations(self.student)
        self.assertEqual(Recommendation.objects.filter(user=self.other).count(), count)

    def test_stale_recommendations_are_recalculated(self):
        services.refresh_recommendations(self.student)
        Recommendation.objects.filter(user=self.student).update(date=self.today - timedelta(days=1), reason="old")
        fresh = services.current_recommendations(self.student)
        self.assertTrue(all(r.date == self.today and r.reason != "old" for r in fresh))

    def test_finishing_an_attempt_refreshes_plan_and_recommendations(self):  # step 9 of the cycle
        exam = Assessment.objects.create(title="Mock", duration=30, status="published")
        for order, q in enumerate(self.questions[self.easy], start=1):
            AssessmentQuestion.objects.create(assessment=exam, question=q, marks=1, display_order=order)
        goal = self.goal(self.easy, due=self.today, target=5)
        Recommendation.objects.create(user=self.student, topic=self.hard, reason="old", priority=1)
        attempt, _ = attempt_services.start_assessment_attempt(self.student, exam)
        wrong = {q.pk: "b" for q in self.questions[self.easy]}
        attempt_services.finish_attempt(attempt, wrong)
        goal.refresh_from_db()
        self.assertEqual(goal.status, "completed")  # 5 answers reached the target of 5
        reasons = list(Recommendation.objects.filter(user=self.student).values_list("reason", flat=True))
        self.assertNotIn("old", reasons)
        self.assertTrue(reasons and all("just getting started" in r for r in reasons))  # 5 scored answers: still starting


class GoalSyncTests(PlanningTestCase):
    def test_progress_counts_only_answered_questions_of_the_topic_in_the_window(self):
        goal = self.goal(self.easy, due=self.today, target=5)
        self.finished(self.student, self.easy, 2, 1)                                   # counts: 3
        self.finished(self.student, self.medium, 4)                                    # other topic
        self.finished(self.student, self.easy, 2, when=timezone.now() - timedelta(days=10))  # outside window
        blank = self.finished(self.student, self.easy, 0, 1)
        Response.objects.filter(attempt=blank).update(answer="")                       # unanswered
        responses = services.analytics.finished_responses([self.student.id])
        self.assertEqual(services.goal_progress(goal, responses), 3)

    def test_auto_completion_and_auto_start(self):
        done = self.goal(self.easy, due=self.today, target=3)
        started = self.goal(self.medium, due=self.today, target=5)
        untouched = self.goal(self.hard, due=self.today, target=5)
        self.finished(self.student, self.easy, 3)
        self.finished(self.student, self.medium, 2)
        services.sync_goals(self.student)
        for goal in (done, started, untouched):
            goal.refresh_from_db()
        self.assertEqual((done.status, started.status, untouched.status), ("completed", "in_progress", "planned"))

    def test_due_date_passing_marks_goal_missed(self):
        goal = self.goal(self.easy, due=self.today - timedelta(days=1), target=5)
        self.finished(self.student, self.easy, 2, when=timezone.now() - timedelta(days=2))
        services.sync_goals(self.student)
        goal.refresh_from_db()
        self.assertEqual(goal.status, "missed")

    def test_target_reached_in_time_beats_missed(self):
        goal = self.goal(self.easy, due=self.today - timedelta(days=1), target=2)
        self.finished(self.student, self.easy, 2, when=timezone.now() - timedelta(days=2))
        services.sync_goals(self.student)
        goal.refresh_from_db()
        self.assertEqual(goal.status, "completed")

    def test_completed_and_missed_goals_are_not_changed_automatically(self):
        completed = self.goal(self.easy, status="completed", due=self.today - timedelta(days=3))
        missed = self.goal(self.medium, status="missed", due=self.today - timedelta(days=3), target=1)
        self.finished(self.student, self.medium, 3)
        services.sync_goals(self.student)
        completed.refresh_from_db(); missed.refresh_from_db()
        self.assertEqual((completed.status, missed.status), ("completed", "missed"))

    def test_other_students_progress_is_ignored(self):
        goal = self.goal(self.easy, due=self.today, target=1)
        self.finished(self.other, self.easy, 5)
        services.sync_goals(self.student)
        goal.refresh_from_db()
        self.assertEqual(goal.status, "planned")

    def test_management_command_marks_overdue_goals(self):
        goal = self.goal(self.easy, due=self.today - timedelta(days=2))
        call_command("update_goal_statuses", verbosity=0)
        goal.refresh_from_db()
        self.assertEqual(goal.status, "missed")


class GoalStateTests(PlanningTestCase):
    def test_start_and_complete(self):
        goal = self.goal()
        services.change_goal_status(goal, "in_progress")
        services.change_goal_status(goal, "completed")
        goal.refresh_from_db()
        self.assertEqual(goal.status, "completed")

    def test_illegal_changes_are_refused(self):
        completed = self.goal(status="completed")
        missed = self.goal(self.medium, status="missed")
        for goal, to in ((completed, "in_progress"), (missed, "in_progress"), (missed, "completed"), (completed, "planned")):
            with self.assertRaises(services.GoalError):
                services.change_goal_status(goal, to)
        with self.assertRaises(services.GoalError):
            services.change_goal_status(self.goal(self.hard), "rescheduled")  # needs a date

    def test_reschedule_moves_date_and_sets_status(self):
        for status in ("planned", "in_progress", "rescheduled", "missed"):
            goal = self.goal(status=status, due=self.today - timedelta(days=1) if status == "missed" else self.today)
            services.reschedule_goal(goal, self.today + timedelta(days=3))
            goal.refresh_from_db()
            self.assertEqual((goal.status, goal.due_date), ("rescheduled", self.today + timedelta(days=3)), status)

    def test_cannot_reschedule_into_the_past_or_a_completed_goal(self):
        with self.assertRaises(services.GoalError):
            services.reschedule_goal(self.goal(), self.today - timedelta(days=1))
        with self.assertRaises(services.GoalError):
            services.reschedule_goal(self.goal(self.medium, status="completed"), self.today + timedelta(days=1))

    def test_rescheduled_goal_can_be_started_and_completed(self):
        goal = self.goal(status="rescheduled")
        services.change_goal_status(goal, "in_progress")
        services.change_goal_status(goal, "completed")
        goal.refresh_from_db()
        self.assertEqual(goal.status, "completed")


class GoalFormTests(PlanningTestCase):
    def form(self, **overrides):
        data = {"topic": self.easy.pk, "due_date": self.today.isoformat(), "target": 5}
        data.update(overrides)
        return GoalForm(data, user=self.student)

    def test_valid_goal(self):
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)
        goal = form.save()
        self.assertEqual((goal.user, goal.status), (self.student, "planned"))

    def test_rejects_past_date_bad_target_and_duplicates(self):
        self.assertFalse(self.form(due_date=(self.today - timedelta(days=1)).isoformat()).is_valid())
        self.assertFalse(self.form(target=0).is_valid())
        self.assertFalse(self.form(target=51).is_valid())
        self.goal(self.easy, due=self.today)
        self.assertFalse(self.form().is_valid())
        self.assertTrue(self.form(topic=self.medium.pk).is_valid())

    def test_missed_goal_does_not_block_a_new_one(self):
        self.goal(self.easy, due=self.today, status="missed")
        self.assertTrue(self.form().is_valid())


class ViewTests(PlanningTestCase):
    def test_access_rules(self):
        for name in ("recommendations", "plan", "goal_create"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)
        self.login(self.tpo)
        for name in ("recommendations", "plan", "goal_create"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_recommendations_page_shows_reasons_and_starting_note(self):
        self.login(self.student)
        page = self.client.get(reverse("recommendations"))
        self.assertContains(page, "general starting suggestions")
        self.assertContains(page, "Why:")
        self.assertContains(page, "Percentages")
        self.assertContains(page, f"/practice/?topic={self.easy.pk}")
        self.assertContains(page, f"/plan/add/?topic={self.easy.pk}")

    def test_personal_recommendations_page_has_no_starting_note(self):
        self.finished(self.student, self.easy, 1, 9)
        self.login(self.student)
        page = self.client.get(reverse("recommendations"))
        self.assertNotContains(page, "general starting suggestions")
        self.assertContains(page, "10 scored answers")

    def test_recommendations_empty_state(self):
        Question.objects.update(status="draft")
        self.login(self.student)
        self.assertContains(self.client.get(reverse("recommendations")), "No suggestions right now")

    def test_create_goal_form_is_prefilled(self):
        self.login(self.student)
        page = self.client.get(reverse("goal_create"), {"topic": self.hard.pk})
        self.assertContains(page, f'value="{services.end_of_week(self.today).isoformat()}"')
        self.assertContains(page, f'<option value="{self.hard.pk}" selected>')
        self.assertContains(page, 'value="5"')

    def test_create_goal_and_plan_shows_progress(self):
        self.login(self.student)
        response = self.client.post(reverse("goal_create"),
                                    {"topic": self.easy.pk, "due_date": self.today.isoformat(), "target": 4})
        self.assertRedirects(response, reverse("plan"))
        self.finished(self.student, self.easy, 3)
        page = self.client.get(reverse("plan"))
        self.assertContains(page, "3 of 4 questions answered")
        self.assertContains(page, "In progress")

    def test_invalid_goal_is_not_saved(self):
        self.login(self.student)
        self.client.post(reverse("goal_create"), {"topic": self.easy.pk, "due_date": "2000-01-01", "target": 4})
        self.assertEqual(WeeklyGoal.objects.count(), 0)

    def test_status_actions(self):
        goal = self.goal()
        self.login(self.student)
        self.client.post(reverse("goal_status", args=[goal.pk]), {"to": "in_progress"})
        goal.refresh_from_db(); self.assertEqual(goal.status, "in_progress")
        self.client.post(reverse("goal_status", args=[goal.pk]), {"to": "completed"})
        goal.refresh_from_db(); self.assertEqual(goal.status, "completed")
        self.client.post(reverse("goal_status", args=[goal.pk]), {"to": "in_progress"})  # not allowed
        goal.refresh_from_db(); self.assertEqual(goal.status, "completed")
        self.assertEqual(self.client.get(reverse("goal_status", args=[goal.pk])).status_code, 405)

    def test_reschedule_view(self):
        goal = self.goal(due=self.today - timedelta(days=1), status="missed")
        self.login(self.student)
        new = self.today + timedelta(days=4)
        self.client.post(reverse("goal_reschedule", args=[goal.pk]), {"due_date": new.isoformat()})
        goal.refresh_from_db()
        self.assertEqual((goal.status, goal.due_date), ("rescheduled", new))
        self.client.post(reverse("goal_reschedule", args=[goal.pk]), {"due_date": "garbage"})
        self.client.post(reverse("goal_reschedule", args=[goal.pk]), {"due_date": (self.today - timedelta(days=1)).isoformat()})
        goal.refresh_from_db()
        self.assertEqual(goal.due_date, new)

    def test_delete_goal(self):
        goal = self.goal()
        self.login(self.student)
        self.client.post(reverse("goal_delete", args=[goal.pk]))
        self.assertFalse(WeeklyGoal.objects.filter(pk=goal.pk).exists())

    def test_students_cannot_touch_each_others_goals(self):
        goal = self.goal(user=self.other)
        self.login(self.student)
        for name, data in (("goal_status", {"to": "completed"}), ("goal_reschedule", {"due_date": self.today.isoformat()}), ("goal_delete", {})):
            self.assertEqual(self.client.post(reverse(name, args=[goal.pk]), data).status_code, 404)
        goal.refresh_from_db(); self.assertEqual(goal.status, "planned")
        self.assertNotContains(self.client.get(reverse("plan")), "Percentages")

    def test_missed_goals_are_listed_with_reschedule(self):
        self.goal(due=self.today - timedelta(days=2), status="planned")
        self.login(self.student)
        page = self.client.get(reverse("plan"))
        self.assertContains(page, "Missed goals")
        self.assertContains(page, "Reschedule")

    def test_dashboard_shows_reminders_and_top_recommendations(self):
        self.goal(self.easy, due=self.today + timedelta(days=1), target=4)
        self.goal(self.medium, due=self.today - timedelta(days=1), target=3)
        self.login(self.student)
        page = self.client.get(reverse("dashboard"))
        self.assertContains(page, "Goal due tomorrow: 4 questions in Percentages.")
        self.assertContains(page, "Missed: 3 questions in Grammar.")
        self.assertContains(page, "Recommended next")
        self.assertContains(page, "Open my plan")

    def test_no_reminders_for_goals_far_in_future(self):
        self.goal(due=self.today + timedelta(days=6))
        self.login(self.student)
        self.assertNotContains(self.client.get(reverse("dashboard")), "Goal due")

    def test_navigation_links(self):
        self.login(self.student)
        page = self.client.get(reverse("dashboard"))
        self.assertContains(page, 'href="/plan/"')
        self.assertContains(page, 'href="/recommendations/"')

    def test_resource_link_from_recommendation_preselects_topic(self):
        self.login(self.student)
        page = self.client.get(reverse("resource_list"), {"topic": self.hard.pk})
        self.assertContains(page, f'<option value="{self.hard.pk}" selected>')


class TpoAggregateTests(PlanningTestCase):
    def test_goal_summary_counts_only_consenting_students_this_week(self):
        hidden = make_user("hidden", "Student", consent=False)
        week_end = services.end_of_week(self.today)
        self.goal(self.easy, due=week_end, status="completed")
        self.goal(self.medium, due=week_end, status="in_progress")
        self.goal(self.hard, due=week_end, status="planned", user=self.other)
        self.goal(self.easy, due=week_end, status="missed", user=hidden)           # no consent
        self.goal(self.easy, due=week_end + timedelta(days=30), status="planned")  # other week
        self.login(self.tpo)
        page = self.client.get(reverse("reports_home"))
        self.assertContains(page, "3 goals set by included students")
        self.assertContains(page, "<strong>1</strong> completed")
        self.assertContains(page, "<strong>2</strong> still open")
        self.assertContains(page, "<strong>0</strong> missed")
