from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from accounts.models import Role
from .models import Conversation, Message


class ConversationModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="student_test",
            email="student@example.com",
            password="test-password-123",
        )

    def test_conversation_and_messages_are_saved(self):
        conversation = Conversation.objects.create(user=self.user, title="DSA practice")
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content="Explain arrays",
        )
        self.assertEqual(conversation.messages.count(), 1)
        self.assertEqual(conversation.messages.first().content, "Explain arrays")

    def test_student_only_sees_own_conversations(self):
        other = get_user_model().objects.create_user(
            username="other_student",
            email="other@example.com",
            password="test-password-123",
        )
        conversation = Conversation.objects.create(user=other, title="Private chat")
        self.client.force_login(self.user)
        response = self.client.get(reverse("ai_open_conversation", args=[conversation.id]))
        self.assertEqual(response.status_code, 404)

    def test_chat_page_requires_login(self):
        response = self.client.get(reverse("ai_chat"))
        self.assertEqual(response.status_code, 302)


class ResumeReviewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.student_role = Role.objects.create(role_name="Student")
        self.student = User.objects.create_user(
            username="resume_student",
            email="resume_student@example.com",
            password="test-password-123",
            role=self.student_role,
        )
        self.other_role = Role.objects.create(role_name="Faculty")
        self.faculty = User.objects.create_user(
            username="resume_faculty",
            email="resume_faculty@example.com",
            password="test-password-123",
            role=self.other_role,
        )

    def test_resume_analyzer_is_student_only(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("resume_analyzer"))
        self.assertEqual(response.status_code, 200)

        self.client.force_login(self.faculty)
        response = self.client.get(reverse("resume_analyzer"))
        self.assertEqual(response.status_code, 403)

    def test_resume_review_is_associated_with_owner(self):
        from .models import ResumeReview
        review = ResumeReview.objects.create(
            user=self.student,
            filename="resume.pdf",
            target_role="Software Developer",
            overall_score=76,
            report={"summary": "Clear and concise."},
        )
        self.assertEqual(review.user_id, self.student.id)
        self.assertEqual(review.report["summary"], "Clear and concise.")
