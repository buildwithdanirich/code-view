"""Authentication views, verification, and password recovery."""
import logging
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from .email_utils import send_account_email
from .forms import LoginForm, RegisterForm, RequestResetForm, CodeViewSetPasswordForm

logger = logging.getLogger(__name__)
User = get_user_model()


def _safe_next(request):
    candidate = request.POST.get("next") or request.GET.get("next", "")
    return candidate if url_has_allowed_host_and_scheme(candidate, {request.get_host()}, require_https=request.is_secure()) else ""


def _uid(user):
    return urlsafe_base64_encode(force_bytes(user.pk))


def _user_from_uid(uidb64):
    try:
        return User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except (User.DoesNotExist, ValueError, TypeError, OverflowError, UnicodeDecodeError):
        return None


def register(request):
    if request.user.is_authenticated:
        return redirect("groups")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save(commit=False)
                user.is_active = False
                user.save()
                url = request.build_absolute_uri(reverse("verify_email", args=[_uid(user), default_token_generator.make_token(user)]))
                send_account_email("Verify your CodeView email", f"Welcome to CodeView!\n\nVerify your email by opening this link:\n{url}\n\nIf you didn't register, ignore this email.", user.email)
        except Exception:
            logger.exception("Could not send CodeView signup verification email")
            form.add_error(None, "We couldn't send your verification email. Please try again later.")
        else:
            return render(request, "users/notice.html", {"heading": "Check your inbox", "detail": "We've sent a verification link to your email. Open it to activate your account."})
    return render(request, "users/register.html", {"form": form})


def verify_email(request, uidb64, token):
    user = _user_from_uid(uidb64)
    if user and not user.is_active and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save(update_fields=["is_active"])
        messages.success(request, "Your email is verified. You can now sign in.")
        return redirect("login")
    return render(request, "users/notice.html", {"heading": "Link invalid or expired", "detail": "This verification link is no longer valid. Contact support if you need help."}, status=400)


def user_login(request):
    if request.user.is_authenticated:
        return redirect("groups")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        identifier = form.cleaned_data["identifier"].strip()
        password = form.cleaned_data["password"]
        # Look up by username first. Email login is allowed only when unambiguous.
        user = authenticate(request, username=identifier, password=password)
        if user is None and "@" in identifier:
            matches = list(User.objects.filter(email__iexact=identifier).values_list("username", flat=True)[:2])
            if len(matches) == 1:
                user = authenticate(request, username=matches[0], password=password)
        if user is not None and user.is_active:
            login(request, user)
            if not form.cleaned_data["remember_me"]:
                request.session.set_expiry(0)
            return redirect(_safe_next(request) or "groups")
        form.add_error(None, "Invalid credentials or an unverified account.")
    return render(request, "users/login.html", {"form": form, "next": _safe_next(request)})


@require_POST
def user_logout(request):
    logout(request)
    return redirect("home")


def forgot_password(request):
    form = RequestResetForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        # Never reveal whether an address belongs to a CodeView account.
        users = User.objects.filter(email__iexact=email, is_active=True)
        for user in users:
            url = request.build_absolute_uri(reverse("password_reset_confirm", args=[_uid(user), default_token_generator.make_token(user)]))
            try:
                send_account_email("Reset your CodeView password", f"To reset your password, open this link:\n{url}\n\nIf you didn't request this, ignore this email.", user.email)
            except Exception:
                logger.exception("Could not send CodeView password reset email")
        return render(request, "users/notice.html", {"heading": "Check your email", "detail": "If an active account uses that address, you'll receive a password reset link shortly."})
    return render(request, "users/forgot_password.html", {"form": form})


def password_reset_confirm(request, uidb64, token):
    user = _user_from_uid(uidb64)
    if not user or not user.is_active or not default_token_generator.check_token(user, token):
        return render(request, "users/notice.html", {"heading": "Link invalid or expired", "detail": "Request a new password reset link."}, status=400)
    form = CodeViewSetPasswordForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Password updated. Please sign in.")
        return redirect("login")
    return render(request, "users/reset_password.html", {"form": form})
