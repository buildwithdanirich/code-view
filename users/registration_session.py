"""Temporary registration-session authorization for ColabVerse."""

from datetime import timedelta

from django.utils import timezone


# A registration browser can automatically sign in only
# within 15 minutes of creating the account.
REGISTRATION_SESSION_MINUTES = 15

REGISTRATION_USER_KEY = "colabverse_registration_user_id"
REGISTRATION_EXPIRES_KEY = "colabverse_registration_expires_at"


def clear_registration_session(request):
    """
    Remove temporary registration authorization.

    This does not log out an already authenticated user.
    """

    request.session.pop(REGISTRATION_USER_KEY, None)
    request.session.pop(REGISTRATION_EXPIRES_KEY, None)


def start_registration_session(request, user):
    """
    Authorize the browser that originally registered the account.

    This authorization does not log the developer in.
    The account must first be verified by email.
    """

    # Discard any earlier registration authorization.
    clear_registration_session(request)

    # Rotate the session identifier to reduce session-fixation risk.
    request.session.cycle_key()

    expires_at = timezone.now() + timedelta(
        minutes=REGISTRATION_SESSION_MINUTES
    )

    # Remember the account created by this browser.
    request.session[REGISTRATION_USER_KEY] = user.pk

    # Store the expiration timestamp.
    request.session[REGISTRATION_EXPIRES_KEY] = expires_at.isoformat()

    request.session.modified = True


def get_pending_registration_user(request):
    """
    Return the account associated with this registration browser.

    Returns None when:
        - No registration is pending.
        - The authorization has expired.
        - The account no longer exists.

    An email address or username alone never grants access.
    """

    user_id = request.session.get(REGISTRATION_USER_KEY)

    expires_at_value = request.session.get(
        REGISTRATION_EXPIRES_KEY
    )

    if not user_id or not expires_at_value:
        return None

    try:
        expires_at = timezone.datetime.fromisoformat(
            expires_at_value
        )

    except (TypeError, ValueError):
        clear_registration_session(request)
        return None

    if timezone.is_naive(expires_at):
        clear_registration_session(request)
        return None

    if timezone.now() >= expires_at:
        clear_registration_session(request)
        return None

    from django.contrib.auth import get_user_model

    User = get_user_model()

    user = User.objects.filter(
        pk=user_id
    ).first()

    if user is None:
        clear_registration_session(request)
        return None

    return user


def registration_is_verified(request):
    """
    Check whether the original registration account is active.

    This function only checks status.
    It does not authenticate or log anyone in.
    """

    user = get_pending_registration_user(request)

    return bool(user and user.is_active)