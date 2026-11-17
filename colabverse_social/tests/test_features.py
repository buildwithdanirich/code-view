from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from colabverse_admin.models import SupportTicket
from colabverse_social.models import Follow


class FeatureTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.a = User._default_manager.create_user(username="social_a", password="TestPass123!")
        self.b = User._default_manager.create_user(username="social_b", password="TestPass123!")
        self.client.force_login(self.a)

    def test_ticket_is_owned_by_requester(self):
        response = self.client.post(reverse("colabverse_social:ticket_create"), {
            "subject": "Cannot log in", "message": "Login fails on my device.",
        })
        self.assertEqual(response.status_code, 302)
        ticket = SupportTicket.objects.get()
        self.assertEqual(ticket.requester_id, self.a.pk)
        self.client.force_login(self.b)
        self.assertEqual(self.client.get(reverse("colabverse_social:ticket_detail", args=[ticket.pk])).status_code, 404)

    def test_follow_and_unfollow(self):
        url = reverse("colabverse_social:follow_toggle", args=[self.b.pk])
        self.client.post(url, {"action": "follow"})
        self.client.post(url, {"action": "follow"})
        self.assertEqual(Follow.objects.count(), 1)
        self.client.post(url, {"action": "unfollow"})
        self.assertFalse(Follow.objects.exists())

    def test_cannot_follow_self(self):
        url = reverse("colabverse_social:follow_toggle", args=[self.a.pk])
        self.assertEqual(self.client.post(url, {"action": "follow"}).status_code, 400)
