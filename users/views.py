"""ColabVerse authentication, email verification, and OTP password recovery."""

import hashlib
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import (
    url_has_allowed_host_and_scheme,
    urlsafe_base64_decode,
    urlsafe_base64_encode,
)
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods, require_POST

from .email_utils import send_account_email
from .forms import (
    CodeViewSetPasswordForm,
    DeveloperProfileForm,
    LoginForm,
    RegisterForm,
    RequestResetForm,
    VerifyPasswordResetOTPForm,
)
from .models import DeveloperProfile, PasswordResetOTP
from .otp_service import (
    can_reset_password,
    send_password_reset_otp,
    verify_password_reset_otp as verify_otp_code,
)
from .registration_session import (
    clear_registration_session,
    get_pending_registration_user,
    start_registration_session,
)


logger = logging.getLogger(__name__)
User = get_user_model()


# ============================================================
# PASSWORD-RECOVERY SESSION KEYS
# ============================================================

RESET_USER_SESSION_KEY = "colabverse_reset_user_id"
RESET_VERIFIED_SESSION_KEY = "colabverse_reset_verified_at"
RESET_HASH_SESSION_KEY = "colabverse_reset_code_hash"


# ============================================================
# PASSWORD-RECOVERY REQUEST LIMITS
# ============================================================

# Maximum OTP requests for one email within one hour.
RESET_EMAIL_REQUEST_LIMIT = 5

# Maximum OTP requests from one client IP within one hour.
RESET_IP_REQUEST_LIMIT = 20

# Maximum OTP verification submissions from one IP within one hour.
RESET_VERIFY_IP_LIMIT = 50

RATE_LIMIT_WINDOW_SECONDS = 3600


# ============================================================
# AUTHENTICATION HELPERS
# ============================================================


def _safe_next(request):
    """Allow redirects only to safe URLs on this website."""

    candidate = request.POST.get("next") or request.GET.get("next", "")

    if url_has_allowed_host_and_scheme(
        candidate,
        {request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate

    return ""


def _uid(user):
    """Encode a user's ID for email verification."""

    return urlsafe_base64_encode(force_bytes(user.pk))


def _user_from_uid(uidb64):
    """Find a user using an encoded ID."""

    try:
        return User.objects.get(
            pk=force_str(urlsafe_base64_decode(uidb64))
        )

    except (
        User.DoesNotExist,
        ValueError,
        TypeError,
        OverflowError,
        UnicodeDecodeError,
    ):
        return None


def _clear_password_reset_session(request):
    """Remove temporary password-recovery authorization."""

    for key in (
        RESET_USER_SESSION_KEY,
        RESET_VERIFIED_SESSION_KEY,
        RESET_HASH_SESSION_KEY,
    ):
        request.session.pop(key, None)


def _pending_reset_user(request):
    """Find the active account attached to this recovery session."""

    user_id = request.session.get(RESET_USER_SESSION_KEY)

    if not user_id:
        return None

    return User.objects.filter(
        pk=user_id,
        is_active=True,
    ).first()


def _reset_session_is_verified(request, otp_record):
    """
    Check that this browser verified the current OTP.

    An old session cannot authorize a newly generated OTP.
    """

    if otp_record is None:
        return False

    verified_at = request.session.get(
        RESET_VERIFIED_SESSION_KEY
    )

    code_hash = request.session.get(
        RESET_HASH_SESSION_KEY
    )

    if not verified_at or not code_hash:
        return False

    return (
        otp_record.is_verified
        and not otp_record.is_used
        and not otp_record.is_expired()
        and not otp_record.has_exceeded_attempts()
        and otp_record.verified_at is not None
        and otp_record.verified_at.isoformat() == verified_at
        and otp_record.code_hash == code_hash
    )


# ============================================================
# RATE-LIMIT HELPERS
# ============================================================


def _client_ip(request):
    """
    Return the client IP address.

    REMOTE_ADDR is used instead of trusting an arbitrary
    X-Forwarded-For header supplied by a visitor.

    Behind a reverse proxy, the deployment must configure
    trusted client-IP handling separately.
    """

    return request.META.get("REMOTE_ADDR", "unknown")


def _rate_limit_key(category, identifier):
    """
    Build a cache key without exposing an email address.

    A keyed digest prevents straightforward recovery of
    an email address from a cache key.
    """

    secret = settings.SECRET_KEY.encode("utf-8")

    value = (
        f"{category}:{identifier}"
    ).encode("utf-8")

    digest = hashlib.sha256(
        secret + b":" + value
    ).hexdigest()

    return f"colabverse:rate:{category}:{digest}"


def _rate_limit_exceeded(category, identifier, limit):
    """
    Count requests within a fixed one-hour window.

    Returns True once the configured limit is exceeded.

    Production requires a shared cache backend supporting
    atomic increments, such as Redis.
    """

    key = _rate_limit_key(category, identifier)

    # Only one request should initialize the counter.
    created = cache.add(
        key,
        1,
        timeout=RATE_LIMIT_WINDOW_SECONDS,
    )

    if created:
        return False

    try:
        count = cache.incr(key)

    except ValueError:
        # The key may have expired between add() and incr().
        # Retry once without allowing an unlimited bypass.
        if cache.add(
            key,
            1,
            timeout=RATE_LIMIT_WINDOW_SECONDS,
        ):
            return False

        count = cache.incr(key)

    return count > limit


# ============================================================
# REGISTRATION
# ============================================================


def register(request):
    """Register developers and wait for verification on the original browser."""

    if request.user.is_authenticated:
        return redirect("questions:feed")

    form = RegisterForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save(commit=False)
                user.is_active = False
                user.save()

                verification_url = request.build_absolute_uri(
                    reverse(
                        "verify_email",
                        args=[
                            _uid(user),
                            default_token_generator.make_token(user),
                        ],
                    )
                )

                send_account_email(
                    "ColabVerse — Verify Your Email",
                    (
                        "Welcome to ColabVerse!\n\n"
                        "Please verify your email address:\n\n"
                        f"{verification_url}\n\n"
                        "If you did not register, ignore this email.\n\n"
                        "The ColabVerse Team"
                    ),
                    user.email,
                )

        except Exception:
            logger.exception("Could not send ColabVerse verification email")
            form.add_error(
                None,
                "We couldn't send your verification email. "
                "Please try again later.",
            )
        else:
            # Authorization belongs to the browser that submitted registration.
            # It does not authenticate the user before email verification.
            start_registration_session(request, user)
            return redirect("waiting_verification")

    return render(request, "users/register.html", {"form": form})


# ============================================================
# EMAIL VERIFICATION AND ORIGINAL-BROWSER SIGN-IN
# ============================================================


def verify_email(request, uidb64, token):
    """Activate the account; never sign in the browser opening this link."""

    user = _user_from_uid(uidb64)

    if (
        user
        and not user.is_active
        and default_token_generator.check_token(user, token)
    ):
        user.is_active = True
        user.save(update_fields=["is_active"])

        # The phone/browser that opens the link is not authenticated.
        # Only the original registration browser may complete sign-in.
        return render(
            request,
            "users/notice.html",
            {
                "heading": "Email verified successfully",
                "detail": (
                    "Your ColabVerse account is now active. "
                    "Return to the device where you registered; "
                    "it will sign you in automatically if the waiting page "
                    "is still open and the registration session is valid."
                ),
            },
        )

    return render(
        request,
        "users/notice.html",
        {
            "heading": "Link invalid or expired",
            "detail": (
                "This verification link is no longer valid. "
                "Contact support if you need help."
            ),
        },
        status=400,
    )


@ensure_csrf_cookie
def waiting_verification(request):
    """Show the waiting page only to the original registration browser."""

    if request.user.is_authenticated:
        return redirect("questions:feed")

    user = get_pending_registration_user(request)
    if user is None:
        return redirect("login")

    return render(
        request,
        "users/waiting_verification.html",
        {
            "verification_status_url": reverse("registration_verification_status"),
        },
    )


@require_http_methods(["GET", "POST"])
def registration_verification_status(request):
    """GET reports verification; CSRF-protected POST completes laptop login."""

    if request.user.is_authenticated:
        return JsonResponse(
            {"verified": True, "redirect_url": reverse("questions:feed")}
        )

    user = get_pending_registration_user(request)
    if user is None:
        return JsonResponse(
            {"verified": False, "expired": True},
            status=403,
        )

    if not user.is_active:
        return JsonResponse({"verified": False, "expired": False})

    if request.method == "GET":
        return JsonResponse({"verified": True, "expired": False})

    # The registration session identifies the exact account, and
    # Django's CSRF middleware protects the sign-in POST.
    # Never accept an account ID or email supplied by the caller.
    backend = "django.contrib.auth.backends.ModelBackend"
    if backend not in settings.AUTHENTICATION_BACKENDS:
        logger.error("ModelBackend is required for registration auto-login")
        return JsonResponse({"error": "Login unavailable"}, status=503)

    clear_registration_session(request)
    login(request, user, backend=backend)
    return JsonResponse(
        {"verified": True, "redirect_url": reverse("questions:feed")}
    )


# ============================================================
# LOGIN
# ============================================================


def user_login(request):
    """Authenticate developers using username or email."""

    if request.user.is_authenticated:
        return redirect("questions:feed")

    form = LoginForm(request.POST or None)

    if request.method == "POST" and form.is_valid():

        identifier = form.cleaned_data["identifier"].strip()
        password = form.cleaned_data["password"]

        # Try normal username authentication first.
        user = authenticate(
            request,
            username=identifier,
            password=password,
        )

        # Support email login for existing accounts.
        if user is None and "@" in identifier:

            matching_accounts = User.objects.filter(
                email__iexact=identifier,
                is_active=True,
            ).only("id", "username")

            authenticated_users = []

            for account in matching_accounts:

                candidate = authenticate(
                    request,
                    username=account.username,
                    password=password,
                )

                if candidate is not None:
                    authenticated_users.append(candidate)

                    # Never guess between matching accounts.
                    if len(authenticated_users) > 1:
                        break

            if len(authenticated_users) == 1:
                user = authenticated_users[0]

        if user is not None and user.is_active:

            login(request, user)

            if not form.cleaned_data["remember_me"]:
                request.session.set_expiry(0)

            return redirect(
                _safe_next(request) or "questions:feed"
            )

        form.add_error(
            None,
            "Invalid credentials or an unverified account.",
        )

    return render(
        request,
        "users/login.html",
        {
            "form": form,
            "next": _safe_next(request),
        },
    )


# ============================================================
# LOGOUT
# ============================================================


@require_POST
def user_logout(request):
    """Log out and return to the homepage."""

    logout(request)

    return redirect("home")


# ============================================================
# STEP 1: REQUEST PASSWORD-RESET OTP
# ============================================================


@require_http_methods(["GET", "POST"])
def forgot_password(request):
    """
    Request a password-reset OTP.

    Valid email submissions always redirect to the OTP page,
    even when the email is unknown or ineligible.

    This avoids revealing account existence through the URL.
    """

    form = RequestResetForm(request.POST or None)

    if request.method == "POST" and form.is_valid():

        email = form.cleaned_data["email"]

        # Clear any previous recovery authorization.
        _clear_password_reset_session(request)

        # Apply request limits before querying accounts.
        email_limited = _rate_limit_exceeded(
            "reset-email",
            email,
            RESET_EMAIL_REQUEST_LIMIT,
        )

        ip_limited = _rate_limit_exceeded(
            "reset-ip",
            _client_ip(request),
            RESET_IP_REQUEST_LIMIT,
        )

        if not email_limited and not ip_limited:

            # Legacy accounts may share the same email.
            # Never select an account arbitrarily.
            accounts = list(
                User.objects.filter(
                    email__iexact=email,
                    is_active=True,
                )[:2]
            )

            if len(accounts) == 1:

                user = accounts[0]

                result = send_password_reset_otp(user)

                if result == "sent":

                    # Bind this recovery request to the browser.
                    request.session[
                        RESET_USER_SESSION_KEY
                    ] = user.pk

                elif result == "cooldown":

                    # Allow this browser to enter an existing
                    # unverified, unexpired OTP.
                    otp_record = PasswordResetOTP.objects.filter(
                        user=user
                    ).first()

                    if (
                        otp_record
                        and not otp_record.is_verified
                        and not otp_record.is_used
                        and not otp_record.is_expired()
                        and not otp_record.has_exceeded_attempts()
                    ):
                        request.session[
                            RESET_USER_SESSION_KEY
                        ] = user.pk

                elif result == "error":

                    logger.warning(
                        "Password-reset OTP delivery failed "
                        "for user ID %s",
                        user.pk,
                    )

        # Always use the same destination for valid input.
        return redirect("verify_password_reset_otp")

    return render(
        request,
        "users/forgot_password.html",
        {"form": form},
    )


# ============================================================
# STEP 2: VERIFY PASSWORD-RESET OTP
# ============================================================


@require_http_methods(["GET", "POST"])
def verify_password_reset_otp(request):
    """
    Verify a six-digit OTP.

    Only a newly verified code authorizes this browser
    to create a new password.
    """

    user = _pending_reset_user(request)

    # Do not reveal whether the email was registered.
    # Visitors without an eligible recovery session see
    # the same OTP form, but cannot authorize a reset.
    form = VerifyPasswordResetOTPForm(request.POST or None)

    if user is not None:

        otp_record = PasswordResetOTP.objects.filter(
            user=user
        ).first()

        # A browser that already completed verification
        # can return to its authorized password form.
        if _reset_session_is_verified(
            request,
            otp_record,
        ):
            return redirect("reset_password_with_otp")

    if request.method == "POST" and form.is_valid():

        ip_limited = _rate_limit_exceeded(
            "verify-ip",
            _client_ip(request),
            RESET_VERIFY_IP_LIMIT,
        )

        if ip_limited:

            form.add_error(
                "code",
                "Too many attempts. Please try again later.",
            )

        elif user is None:

            form.add_error(
                "code",
                "Invalid or expired verification code.",
            )

        else:

            result = verify_otp_code(
                user,
                form.cleaned_data["code"],
            )

            if result == "verified":

                otp_record = PasswordResetOTP.objects.filter(
                    user=user
                ).first()

                if (
                    otp_record is not None
                    and can_reset_password(user)
                ):

                    # Rotate the session identifier after
                    # successful OTP verification.
                    request.session.cycle_key()

                    request.session[
                        RESET_VERIFIED_SESSION_KEY
                    ] = otp_record.verified_at.isoformat()

                    request.session[
                        RESET_HASH_SESSION_KEY
                    ] = otp_record.code_hash

                    return redirect("reset_password_with_otp")

            elif result == "expired":

                form.add_error(
                    "code",
                    "This code has expired. Request a new code.",
                )

            elif result == "locked":

                form.add_error(
                    "code",
                    "Too many incorrect attempts. "
                    "Request a new code after the lock expires.",
                )

            elif result in ("used", "already_verified"):

                form.add_error(
                    "code",
                    "This code is no longer available. "
                    "Start a new recovery request.",
                )

            else:

                form.add_error(
                    "code",
                    "Invalid verification code.",
                )

    return render(
        request,
        "users/verify_reset_otp.html",
        {"form": form},
    )


# ============================================================
# STEP 3: CREATE A NEW PASSWORD
# ============================================================


@require_http_methods(["GET", "POST"])
def reset_password_with_otp(request):
    """
    Change the password after OTP verification.

    The password change and OTP consumption happen
    inside one database transaction.
    """

    user = _pending_reset_user(request)

    if user is None:
        return redirect("forgot_password")

    otp_record = PasswordResetOTP.objects.filter(
        user=user
    ).first()

    # A visitor cannot skip OTP verification by typing
    # the new-password URL directly.
    if not _reset_session_is_verified(
        request,
        otp_record,
    ):
        return redirect("verify_password_reset_otp")

    form = CodeViewSetPasswordForm(
        user,
        request.POST or None,
    )

    if request.method == "POST" and form.is_valid():

        updated = False

        with transaction.atomic():

            # Lock the account to serialize password updates.
            locked_user = User.objects.select_for_update().get(
                pk=user.pk
            )

            # Lock the OTP so concurrent requests cannot
            # consume the same verification twice.
            locked_otp = (
                PasswordResetOTP.objects.select_for_update()
                .filter(user=locked_user)
                .first()
            )

            # Check authorization again inside the transaction.
            if _reset_session_is_verified(
                request,
                locked_otp,
            ):

                # Django securely hashes the new password.
                locked_user.set_password(
                    form.cleaned_data["new_password1"]
                )

                locked_user.save(
                    update_fields=["password"]
                )

                # Permanently consume this OTP.
                locked_otp.is_used = True

                locked_otp.save(
                    update_fields=["is_used"]
                )

                updated = True

        if updated:

            _clear_password_reset_session(request)

            messages.success(
                request,
                "Your ColabVerse password has been updated. "
                "Please sign in with your new password.",
            )

            return redirect("login")

        return redirect("forgot_password")

    return render(
        request,
        "users/reset_password.html",
        {"form": form},
    )


# ============================================================
# RETIRED PASSWORD-RESET LINK ENDPOINT
# ============================================================


def password_reset_confirm(request, uidb64, token):
    """
    Reject old password-reset links.

    Existing links must not bypass OTP verification.
    """

    return render(
        request,
        "users/notice.html",
        {
            "heading": "Password recovery has changed",
            "detail": (
                "ColabVerse now uses email verification codes "
                "for password recovery. Please start a new "
                "password-reset request."
            ),
        },
        status=410,
    )


# ============================================================
# DEVELOPER PROFILES
# ============================================================
def _profile_context(profile):
    """
    Prepare developer profile statistics.

    Includes:
    - Developer profile information
    - Groups created
    - Groups joined
    - Reputation points
    - Reputation stars
    """

    from community.models import ProjectGroup, GroupMember
    from questions.models import Reputation

    user = profile.user

    # Retrieve the developer's existing reputation.
    # Create a default record if one does not exist yet.
    reputation, _ = Reputation.objects.get_or_create(
        user=user
    )

    return {
        # Developer profile information.
        "profile": profile,

        # Number of development groups created.
        "groups_created": ProjectGroup.objects.filter(
            owner=user
        ).count(),

        # Number of development groups joined.
        "groups_joined": GroupMember.objects.filter(
            user=user
        ).count(),

        # Developer's total reputation points.
        "reputation_points": reputation.points,

        # Star level calculated by the existing reputation model.
        "reputation_stars": reputation.stars,
    }

@login_required
def my_profile(request):
    """Display the logged-in developer's profile."""

    profile, _ = DeveloperProfile.objects.get_or_create(
        user=request.user
    )

    return render(
        request,
        "users/profile.html",
        _profile_context(profile),
    )


@login_required
def public_profile(request, username):
    """Display another developer's public profile."""

    user = get_object_or_404(
        User,
        username=username,
        is_active=True,
    )

    profile, _ = DeveloperProfile.objects.get_or_create(
        user=user
    )

    context = _profile_context(profile)
    context["is_public_view"] = True

    # Read the optional return destination.
    return_to = request.GET.get("next", "")

    # Only allow safe URLs on this website.
    if return_to and url_has_allowed_host_and_scheme(
        url=return_to,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        context["return_to"] = return_to
    else:
        context["return_to"] = None

    return render(
        request,
        "users/profile.html",
        context,
    )


@login_required
@require_http_methods(["GET", "POST"])
def edit_profile(request):
    """Edit developer profile information."""

    profile, _ = DeveloperProfile.objects.get_or_create(
        user=request.user
    )

    form = DeveloperProfileForm(
        request.POST or None,
        request.FILES or None,
        instance=profile,
    )

    if request.method == "POST" and form.is_valid():

        form.save()

        messages.success(
            request,
            "Your profile has been updated.",
        )

        return redirect("my_profile")

    return render(
        request,
        "users/edit_profile.html",
        {
            "form": form,
            "profile": profile,
        },
    )


@login_required
@require_POST
def remove_profile_photo(request):
    """Remove the developer's profile photo."""

    profile, _ = DeveloperProfile.objects.get_or_create(
        user=request.user
    )

    if profile.avatar:
        profile.avatar.delete(save=True)

    messages.success(
        request,
        "Profile photo removed.",
    )

    return redirect("edit_profile")