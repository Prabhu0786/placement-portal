from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
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
