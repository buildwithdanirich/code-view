"""Google social authentication rules for ColabVerse."""

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model


User = get_user_model()


class CodeViewSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Control Google authentication and registration for ColabVerse.
    """

    def is_open_for_signup(self, request, sociallogin):
        """
        Allow new registrations through Google only.

        Do not automatically connect existing ColabVerse accounts
        to Google accounts based solely on matching email addresses.
        """

        # Only Google is permitted as a social authentication provider.
        if sociallogin.account.provider != "google":
            return False

        return super().is_open_for_signup(request, sociallogin)

    def populate_user(self, request, sociallogin, data):
        """
        Populate a new ColabVerse user with Google's account details.

        This method prepares the user object but does not save it.
        """

        # Let Django Allauth perform its normal population first.
        user = super().populate_user(request, sociallogin, data)

        # Normalize the Google email address.
        if user.email:
            user.email = user.email.strip().lower()

        # Retrieve the profile information supplied by Google.
        google_data = sociallogin.account.extra_data or {}

        # Google's OpenID Connect profile normally provides these fields.
        first_name = google_data.get("given_name", "")
        last_name = google_data.get("family_name", "")

        # Preserve names already populated by Django Allauth
        # when Google does not supply these fields.
        if first_name:
            user.first_name = str(first_name).strip()[:150]

        if last_name:
            user.last_name = str(last_name).strip()[:150]

        # ColabVerse collects a unique username during Google signup.
        user.username = ""

        return user