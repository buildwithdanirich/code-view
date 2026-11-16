"""Secure password-reset OTP services for ColabVerse."""

import logging
import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from .email_utils import send_account_email
from .models import PasswordResetOTP


logger = logging.getLogger(__name__)


# ============================================================
# OTP SECURITY CONFIGURATION
# ============================================================

OTP_EXPIRY_MINUTES = 10

OTP_MAX_ATTEMPTS = 5

OTP_RESEND_COOLDOWN_SECONDS = 60

# Limit how frequently new OTPs can be generated for an account.
# Five requests within one hour is the maximum.
OTP_MAX_REQUESTS_PER_HOUR = 5


# ============================================================
# 1. GENERATE OTP
# ============================================================


def generate_otp():
    """
    Generate a cryptographically secure six-digit OTP.

    Example:
        048291

    Leading zeros are preserved.
    """

    return f"{secrets.randbelow(1_000_000):06d}"


# ============================================================
# 2. SEND PASSWORD-RESET OTP
# ============================================================


def send_password_reset_otp(user):
    """
    Generate, securely store, and email a password-reset OTP.

    Returns:
        "sent"     - Email successfully sent.
        "cooldown" - A code was requested too recently.
        "locked"   - Existing OTP is locked after failed attempts.
        "error"    - Email delivery failed.

    Account existence must never be disclosed by the calling view.

    Note:
        A separate request-level rate limiter is still required.
        The model currently does not store hourly request history.
    """

    now = timezone.now()

    with transaction.atomic():

        # Lock the account so concurrent requests cannot generate
        # multiple OTPs for the same developer.
        type(user).objects.select_for_update().get(
            pk=user.pk
        )

        # Retrieve the existing OTP record, if one exists.
        otp_record = PasswordResetOTP.objects.filter(
            user=user
        ).first()

        if otp_record is not None:

            # Prevent rapid repeated requests.
            elapsed = (
                now - otp_record.last_sent_at
            ).total_seconds()

            if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
                return "cooldown"

            # Do not allow a locked OTP to be replaced
            # while its current expiration window is active.
            if (
                otp_record.has_exceeded_attempts()
                and not otp_record.is_expired()
            ):
                return "locked"

        # Generate a new random OTP.
        code = generate_otp()

        # Hash the OTP before saving it.
        code_hash = make_password(code)

        expires_at = now + timedelta(
            minutes=OTP_EXPIRY_MINUTES
        )

        # Store the new OTP and invalidate the previous one.
        PasswordResetOTP.objects.update_or_create(
            user=user,
            defaults={
                "code_hash": code_hash,
                "created_at": now,
                "expires_at": expires_at,
                "attempts": 0,
                "is_verified": False,
                "verified_at": None,
                "last_sent_at": now,
                "is_used": False,
            },
        )

        # Send the code to the developer's registered email.
        try:

            send_account_email(
                "ColabVerse — Password Reset Verification Code",
                (
                    "Hello,\n\n"
                    "We received a request to reset the password "
                    "for your ColabVerse account.\n\n"
                    f"Username: {user.username}\n\n"
                    f"Your verification code is: {code}\n\n"
                    "This code expires in 10 minutes.\n\n"
                    "You have a maximum of 5 attempts "
                    "to enter the correct code.\n\n"
                    "If you didn't request this password reset, "
                    "you can safely ignore this email.\n\n"
                    "The ColabVerse Team"
                ),
                user.email,
            )

        except Exception:

            logger.exception(
                "Failed to send ColabVerse password-reset OTP"
            )

            # Roll back the OTP database changes if sending fails.
            transaction.set_rollback(True)

            return "error"

    return "sent"


# ============================================================
# 3. VERIFY PASSWORD-RESET OTP
# ============================================================


def verify_password_reset_otp(user, submitted_code):
    """
    Verify a password-reset OTP.

    Returns:
        "verified"         - Correct code, newly verified.
        "invalid"          - Incorrect code.
        "expired"          - Code expired.
        "locked"           - Five incorrect attempts reached.
        "used"             - Code already consumed.
        "already_verified" - Code previously verified.
        "missing"          - No OTP exists.

    Only a newly verified OTP can authorize a browser session.
    """

    with transaction.atomic():

        # Lock the OTP record to prevent simultaneous verification.
        otp_record = (
            PasswordResetOTP.objects.select_for_update()
            .filter(user=user)
            .first()
        )

        if otp_record is None:
            return "missing"

        # A consumed OTP cannot be reused.
        if otp_record.is_used:
            return "used"

        # Expired codes cannot be accepted.
        if otp_record.is_expired():
            return "expired"

        # Stop verification after five incorrect attempts.
        if otp_record.has_exceeded_attempts():
            return "locked"

        # A previously verified code cannot authorize another session.
        if otp_record.is_verified:
            return "already_verified"

        # Compare the entered code against the stored hash.
        if not check_password(
            submitted_code,
            otp_record.code_hash,
        ):

            otp_record.attempts += 1

            otp_record.save(
                update_fields=["attempts"]
            )

            if otp_record.has_exceeded_attempts():
                return "locked"

            return "invalid"

        # The submitted OTP is correct.
        otp_record.is_verified = True
        otp_record.verified_at = timezone.now()

        otp_record.save(
            update_fields=[
                "is_verified",
                "verified_at",
            ]
        )

        return "verified"


# ============================================================
# 4. CHECK PASSWORD-RESET AUTHORIZATION
# ============================================================


def can_reset_password(user):
    """
    Check whether a valid OTP has been verified.

    This is only one security check.

    The password-reset view must additionally verify that
    the current browser session completed OTP verification.
    """

    otp_record = PasswordResetOTP.objects.filter(
        user=user
    ).first()

    if otp_record is None:
        return False

    return (
        otp_record.is_verified
        and not otp_record.is_used
        and not otp_record.is_expired()
        and not otp_record.has_exceeded_attempts()
    )


# ============================================================
# 5. CONSUME PASSWORD-RESET OTP
# ============================================================


def consume_password_reset_otp(user):
    """
    Mark a verified OTP as used.

    The password-reset view must perform password updating
    and OTP consumption inside the same database transaction.
    """

    now = timezone.now()

    return PasswordResetOTP.objects.filter(
        user=user,
        is_verified=True,
        is_used=False,
        expires_at__gt=now,
        attempts__lt=OTP_MAX_ATTEMPTS,
    ).update(
        is_used=True,
    )