"""ColabVerse authentication, OTP recovery, and developer profile URLs."""

from django.urls import path

from . import views


urlpatterns = [
    # ============================================================
    # AUTHENTICATION
    # ============================================================

    # Register a new developer.
    path(
        "register/",
        views.register,
        name="register",
    ),

    # Log in using username/email and password.
    path(
        "login/",
        views.user_login,
        name="login",
    ),

    # Log out of ColabVerse.
    path(
        "logout/",
        views.user_logout,
        name="logout",
    ),

    # Verify a new developer's email address.
    path(
        "verify-email/<str:uidb64>/<str:token>/",
        views.verify_email,
        name="verify_email",
    ),

    # ============================================================
    # PASSWORD RECOVERY USING OTP
    # ============================================================

    # Step 1: Enter the registered email address.
    path(
        "forgot-password/",
        views.forgot_password,
        name="forgot_password",
    ),

    # Step 2: Enter the six-digit OTP received by email.
    path(
        "forgot-password/verify-otp/",
        views.verify_password_reset_otp,
        name="verify_password_reset_otp",
    ),

    # Step 3: Create a new password after OTP verification.
    path(
        "forgot-password/new-password/",
        views.reset_password_with_otp,
        name="reset_password_with_otp",
    ),

    # Preserve the old URL name for compatibility.
    # The view now rejects old reset links.
    path(
        "reset-password/<str:uidb64>/<str:token>/",
        views.password_reset_confirm,
        name="password_reset_confirm",
    ),

    # ============================================================
    # DEVELOPER PROFILES
    # ============================================================

    # View your own developer profile.
    path(
        "profile/",
        views.my_profile,
        name="my_profile",
    ),

    # Edit your developer profile.
    path(
        "profile/edit/",
        views.edit_profile,
        name="edit_profile",
    ),

    # Remove your profile picture.
    path(
        "profile/remove-photo/",
        views.remove_profile_photo,
        name="remove_profile_photo",
    ),

    # View another developer's public profile.
    path(
        "developers/<str:username>/",
        views.public_profile,
        name="public_profile",
    ),
]