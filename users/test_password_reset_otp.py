"""Security tests for ColabVerse OTP password recovery."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from users.models import PasswordResetOTP
from users.otp_service import (
    generate_otp,
    send_password_reset_otp,
    verify_password_reset_otp,
)


User = get_user_model()

TEST_CODE = "123456"
OLD_PASSWORD = "OldSecurePassword123!"
NEW_PASSWORD = "NewSecurePassword456!"


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
)
class PasswordResetOTPTests(TestCase):
    """
    Test OTP generation, verification, and password recovery.

    Django creates a separate test database, so these tests
    do not modify existing developer accounts.
    """

    def setUp(self):
        """Create a verified developer account for each test."""

        self.user = User.objects.create_user(
            username="otp_test_developer",
            email="otp-test@example.com",
            password=OLD_PASSWORD,
            is_active=True,
        )

        self.forgot_url = reverse("forgot_password")

        self.verify_url = reverse(
            "verify_password_reset_otp"
        )

        self.new_password_url = reverse(
            "reset_password_with_otp"
        )

    # ========================================================
    # TEST HELPERS
    # ========================================================

    def create_otp(
        self,
        code=TEST_CODE,
        expired=False,
        attempts=0,
        verified=False,
        used=False,
    ):
        """
        Create an OTP directly in the test database.

        This lets us test security conditions without
        sending a real email.
        """

        now = timezone.now()

        expires_at = now + timedelta(minutes=10)

        if expired:
            expires_at = now - timedelta(seconds=1)

        return PasswordResetOTP.objects.create(
            user=self.user,
            code_hash=make_password(code),
            created_at=now,
            expires_at=expires_at,
            attempts=attempts,
            is_verified=verified,
            verified_at=now if verified else None,
            last_sent_at=now,
            is_used=used,
        )

    def attach_recovery_session(self):
        """Associate the test browser with the developer."""

        session = self.client.session

        session["colabverse_reset_user_id"] = self.user.pk

        session.save()

    def verify_code_in_browser(self):
        """Submit the correct OTP through the actual Django view."""

        self.attach_recovery_session()

        return self.client.post(
            self.verify_url,
            {"code": TEST_CODE},
        )

    # ========================================================
    # 1. OTP GENERATION
    # ========================================================

    def test_generate_otp_has_six_digits(self):
        """Generated OTPs must contain exactly six digits."""

        for _ in range(20):
            code = generate_otp()

            self.assertEqual(len(code), 6)

            self.assertTrue(code.isascii())

            self.assertTrue(code.isdigit())

    # ========================================================
    # 2. CORRECT OTP
    # ========================================================

    def test_correct_otp_is_verified(self):
        """A correct OTP must be accepted."""

        self.create_otp()

        result = verify_password_reset_otp(
            self.user,
            TEST_CODE,
        )

        self.assertEqual(result, "verified")

        otp = PasswordResetOTP.objects.get(
            user=self.user
        )

        self.assertTrue(otp.is_verified)

        self.assertIsNotNone(otp.verified_at)

    # ========================================================
    # 3. INCORRECT OTP
    # ========================================================

    def test_incorrect_otp_is_rejected(self):
        """An incorrect OTP must not be accepted."""

        self.create_otp()

        result = verify_password_reset_otp(
            self.user,
            "999999",
        )

        self.assertEqual(result, "invalid")

        otp = PasswordResetOTP.objects.get(
            user=self.user
        )

        self.assertFalse(otp.is_verified)

        self.assertEqual(otp.attempts, 1)

    # ========================================================
    # 4. EXPIRED OTP
    # ========================================================

    def test_expired_otp_is_rejected(self):
        """An expired OTP cannot authorize recovery."""

        self.create_otp(expired=True)

        result = verify_password_reset_otp(
            self.user,
            TEST_CODE,
        )

        self.assertEqual(result, "expired")

    # ========================================================
    # 5. FIVE INCORRECT ATTEMPTS
    # ========================================================

    def test_five_incorrect_attempts_lock_otp(self):
        """Five incorrect codes must lock the OTP."""

        self.create_otp()

        for attempt in range(5):
            result = verify_password_reset_otp(
                self.user,
                "999999",
            )

        self.assertEqual(result, "locked")

        otp = PasswordResetOTP.objects.get(
            user=self.user
        )

        self.assertEqual(otp.attempts, 5)

        # Even the correct code must now be rejected.
        result = verify_password_reset_otp(
            self.user,
            TEST_CODE,
        )

        self.assertEqual(result, "locked")

    # ========================================================
    # 6. OTP REUSE
    # ========================================================

    def test_verified_otp_cannot_be_verified_again(self):
        """A previously verified OTP cannot be reused."""

        self.create_otp()

        first_result = verify_password_reset_otp(
            self.user,
            TEST_CODE,
        )

        second_result = verify_password_reset_otp(
            self.user,
            TEST_CODE,
        )

        self.assertEqual(first_result, "verified")

        self.assertEqual(
            second_result,
            "already_verified",
        )

    # ========================================================
    # 7. CONSUMED OTP
    # ========================================================

    def test_consumed_otp_is_rejected(self):
        """An already-used OTP cannot be verified."""

        self.create_otp(
            verified=True,
            used=True,
        )

        result = verify_password_reset_otp(
            self.user,
            TEST_CODE,
        )

        self.assertEqual(result, "used")

    # ========================================================
    # 8. BLOCK DIRECT PASSWORD RESET
    # ========================================================

    def test_password_page_requires_verification(self):
        """
        Opening the password page directly must not
        allow a developer to reset their password.
        """

        response = self.client.get(
            self.new_password_url
        )

        self.assertRedirects(
            response,
            self.forgot_url,
        )

    # ========================================================
    # 9. BROWSER OTP VERIFICATION
    # ========================================================

    def test_correct_browser_otp_opens_password_page(self):
        """
        Correct OTP verification must authorize
        the current browser session.
        """

        self.create_otp()

        response = self.verify_code_in_browser()

        self.assertRedirects(
            response,
            self.new_password_url,
        )

        password_page = self.client.get(
            self.new_password_url
        )

        self.assertEqual(
            password_page.status_code,
            200,
        )

    # ========================================================
    # 10. WRONG BROWSER OTP
    # ========================================================

    def test_wrong_browser_otp_cannot_open_password_page(self):
        """A wrong OTP must not unlock password recovery."""

        self.create_otp()

        self.attach_recovery_session()

        response = self.client.post(
            self.verify_url,
            {"code": "999999"},
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        password_page = self.client.get(
            self.new_password_url
        )

        self.assertRedirects(
            password_page,
            self.verify_url,
        )

    # ========================================================
    # 11. SUCCESSFUL PASSWORD RESET
    # ========================================================

    def test_successful_reset_changes_password(self):
        """
        A successful password reset must:

        1. Change the password.
        2. Consume the OTP.
        3. Invalidate the recovery session.
        """

        self.create_otp()

        response = self.verify_code_in_browser()

        self.assertRedirects(
            response,
            self.new_password_url,
        )

        response = self.client.post(
            self.new_password_url,
            {
                "new_password1": NEW_PASSWORD,
                "new_password2": NEW_PASSWORD,
            },
        )

        self.assertRedirects(
            response,
            reverse("login"),
        )

        self.user.refresh_from_db()

        # New password works.
        self.assertTrue(
            self.user.check_password(
                NEW_PASSWORD
            )
        )

        # Old password no longer works.
        self.assertFalse(
            self.user.check_password(
                OLD_PASSWORD
            )
        )

        # OTP is permanently consumed.
        otp = PasswordResetOTP.objects.get(
            user=self.user
        )

        self.assertTrue(otp.is_used)

        # Recovery authorization is removed.
        session = self.client.session

        self.assertNotIn(
            "colabverse_reset_verified_at",
            session,
        )

    # ========================================================
    # 12. UNKNOWN EMAIL
    # ========================================================

    def test_unknown_email_does_not_reveal_account(self):
        """
        Unknown emails should follow the same redirect
        as eligible accounts.
        """

        response = self.client.post(
            self.forgot_url,
            {
                "email": "unknown@example.com",
            },
        )

        self.assertRedirects(
            response,
            self.verify_url,
        )

        self.assertNotIn(
            "colabverse_reset_user_id",
            self.client.session,
        )

    # ========================================================
    # 13. EMAIL DELIVERY
    # ========================================================

    @patch("users.otp_service.send_account_email")
    def test_otp_is_sent_to_registered_email(self, mock_send):
        """A recovery request must send an OTP email."""

        response = self.client.post(
            self.forgot_url,
            {
                "email": self.user.email,
            },
        )

        self.assertRedirects(
            response,
            self.verify_url,
        )

        mock_send.assert_called_once()

        self.assertEqual(
            mock_send.call_args.args[2],
            self.user.email,
        )

        self.assertTrue(
            PasswordResetOTP.objects.filter(
                user=self.user
            ).exists()
        )

    # ========================================================
    # 14. RESEND COOLDOWN
    # ========================================================

    @patch("users.otp_service.send_account_email")
    def test_otp_resend_cooldown(self, mock_send):
        """
        Requesting another OTP immediately must
        not generate a second email.
        """

        first_result = send_password_reset_otp(
            self.user
        )

        second_result = send_password_reset_otp(
            self.user
        )

        self.assertEqual(
            first_result,
            "sent",
        )

        self.assertEqual(
            second_result,
            "cooldown",
        )

        self.assertEqual(
            mock_send.call_count,
            1,
        )

    # ========================================================
    # 15. LOCKED OTP CANNOT BE REISSUED IMMEDIATELY
    # ========================================================

    @patch("users.otp_service.send_account_email")
    def test_locked_otp_cannot_be_reissued(self, mock_send):
        """
        An OTP locked after five failures cannot
        be replaced during its expiration window.
        """

        otp = self.create_otp(
            attempts=5
        )

        # Move the last-send time beyond the resend cooldown.
        otp.last_sent_at = timezone.now() - timedelta(
            minutes=2
        )

        otp.save(
            update_fields=["last_sent_at"]
        )

        result = send_password_reset_otp(
            self.user
        )

        self.assertEqual(
            result,
            "locked",
        )

        mock_send.assert_not_called()