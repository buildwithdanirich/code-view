from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

class AdminAccessTests(TestCase):
    def setUp(self):
        model = get_user_model()
        self.staff = model._default_manager.create_user(username="admin_test_staff", password="safe-test-password", is_staff=True)
        self.member = model._default_manager.create_user(username="admin_test_member", password="safe-test-password")

    def test_member_cannot_access_dashboard(self):
        self.client.force_login(self.member)
        self.assertNotEqual(self.client.get(reverse("colabverse_admin:dashboard")).status_code, 200)

    def test_staff_can_access_dashboard(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("colabverse_admin:dashboard")).status_code, 200)

    def test_staff_cannot_toggle_user(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("colabverse_admin:toggle_user_active", args=[self.member.pk]))
        self.assertEqual(response.status_code, 403)
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)
