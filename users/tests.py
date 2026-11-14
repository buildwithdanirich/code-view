"""Basic authentication integration tests."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator

User = get_user_model()


class AuthenticationTests(TestCase):
    def test_login_page(self):
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)

    def test_register_page(self):
        self.assertEqual(self.client.get(reverse("register")).status_code, 200)

    def test_invalid_signup(self):
        response = self.client.post(reverse("register"), {"username": "abc", "email": "bad", "password1": "123", "password2": "123"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="abc").exists())

    def test_username_login(self):
        User.objects.create_user(username="alex", email="alex@example.com", password="StrongPassword900!")
        response = self.client.post(reverse("login"), {"identifier": "alex", "password": "StrongPassword900!"})
        self.assertEqual(response.status_code, 302)

    def test_email_login(self):
        User.objects.create_user(username="alex", email="alex@example.com", password="StrongPassword900!")
        response = self.client.post(reverse("login"), {"identifier": "alex@example.com", "password": "StrongPassword900!"})
        self.assertEqual(response.status_code, 302)

    def test_verification(self):
        user = User.objects.create_user(username="pending", email="pending@example.com", password="StrongPassword900!", is_active=False)
        response = self.client.get(reverse("verify_email", args=[urlsafe_base64_encode(force_bytes(user.pk)), default_token_generator.make_token(user)]))
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
