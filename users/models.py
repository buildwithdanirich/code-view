"""ColabVerse developer profiles and password-reset verification."""

from django.conf import settings
from django.db import models
from django.utils import timezone


# ============================================================
# DEVELOPER PROFILE
# ============================================================


class DeveloperProfile(models.Model):
    """
    Store public developer profile information.

    Authentication credentials remain in Django's user model.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="developer_profile",
    )

    avatar = models.ImageField(
        upload_to="profile_avatars/",
        blank=True,
    )

    title = models.CharField(
        max_length=100,
        blank=True,
    )

    bio = models.TextField(
        max_length=600,
        blank=True,
    )

    location = models.CharField(
        max_length=100,
        blank=True,
    )

    skills = models.CharField(
        max_length=300,
        blank=True,
        help_text="Comma-separated skills",
    )

    github_url = models.URLField(blank=True)

    linkedin_url = models.URLField(blank=True)

    portfolio_url = models.URLField(blank=True)

    def __str__(self):
        return f"{self.user.username}'s profile"


# ============================================================
# PASSWORD RESET OTP
# ============================================================


class PasswordResetOTP(models.Model):
    """
    Store password-reset OTP verification state.

    Security rules:
    - One OTP record per developer.
    - Store only a secure hash of the OTP.
    - OTP expires after a configured period.
    - Track incorrect verification attempts.
    - Prevent OTP reuse.
    """

    # Associate the OTP with one specific developer account.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_otp",
    )

    # Store a secure hash, never the actual six-digit code.
    code_hash = models.CharField(
        max_length=255,
    )

    # Time when the OTP was generated.
    created_at = models.DateTimeField(
        default=timezone.now,
    )

    # Time after which the OTP becomes invalid.
    expires_at = models.DateTimeField()

    # Number of incorrect OTP attempts.
    attempts = models.PositiveSmallIntegerField(
        default=0,
    )

    # Whether the developer successfully verified the OTP.
    is_verified = models.BooleanField(
        default=False,
    )

    # Time when the OTP was successfully verified.
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    # Time when the OTP was last sent.
    last_sent_at = models.DateTimeField(
        default=timezone.now,
    )

    # Whether the OTP has already been used to reset a password.
    is_used = models.BooleanField(
        default=False,
    )

    def is_expired(self):
        """Return True when the OTP has expired."""

        return timezone.now() >= self.expires_at

    def has_exceeded_attempts(self):
        """Return True after five incorrect attempts."""

        return self.attempts >= 5

    def can_verify(self):
        """
        Determine whether this OTP is eligible for verification.

        The verification service will also compare the submitted
        OTP against the stored hash.
        """

        return (
            not self.is_expired()
            and not self.has_exceeded_attempts()
            and not self.is_verified
            and not self.is_used
        )

    def __str__(self):
        return f"Password reset OTP for user {self.user_id}"