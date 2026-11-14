"""Google social authentication rules for CodeView."""

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model


User = get_user_model()


class CodeViewSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Control how Google accounts are registered in CodeView.
    """

    def is_open_for_signup(self, request, sociallogin):
        """
        Allow new Google registrations.

        Existing accounts with the same email must not be
        silently linked to a different Google identity.
        """

        # Only allow Google as a social authentication provider.
        if sociallogin.account.provider != "google":
            return False

        return super().is_open_for_signup(request, sociallogin)

    def populate_user(self, request, sociallogin, data):
        """
        Prepare a new CodeView user using Google's profile data.

        The account is not saved to the database here.
        """

        user = super().populate_user(request, sociallogin, data)

        # Normalize the email address.
        if user.email:
            user.email = user.email.strip().lower()

        # A username will be collected during the signup process.
        user.username = ""

        return user