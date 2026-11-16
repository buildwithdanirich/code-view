"""Validated signup, login, OTP recovery, and profile forms for ColabVerse."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm, UserCreationForm
from django.core.exceptions import ValidationError

from allauth.socialaccount.forms import SignupForm

from .models import DeveloperProfile


User = get_user_model()


# ============================================================
# 1. NORMAL REGISTRATION
# ============================================================


class RegisterForm(UserCreationForm):
    """Register a developer with their full name and email."""

    first_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "given-name",
                "placeholder": "Enter your first name",
            }
        ),
    )

    last_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "family-name",
                "placeholder": "Enter your last name",
            }
        ),
    )

    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "placeholder": "you@example.com",
            }
        ),
    )

    class Meta:
        model = User

        fields = (
            "first_name",
            "last_name",
            "username",
            "email",
            "password1",
            "password2",
        )

        widgets = {
            "username": forms.TextInput(
                attrs={
                    "autocomplete": "username",
                    "placeholder": "Choose a username",
                }
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["password1"].widget.attrs.update(
            {
                "autocomplete": "new-password",
                "placeholder": "Create a password",
            }
        )

        self.fields["password2"].widget.attrs.update(
            {
                "autocomplete": "new-password",
                "placeholder": "Confirm your password",
            }
        )

    def clean_first_name(self):
        """Remove unnecessary spaces from the first name."""

        first_name = self.cleaned_data["first_name"].strip()

        if not first_name:
            raise ValidationError("Please enter your first name.")

        return first_name

    def clean_last_name(self):
        """Remove unnecessary spaces from the last name."""

        last_name = self.cleaned_data["last_name"].strip()

        if not last_name:
            raise ValidationError("Please enter your last name.")

        return last_name

    def clean_email(self):
        """Normalize email and prevent duplicate registrations."""

        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                "This email address is already registered."
            )

        return email

    def save(self, commit=True):
        """Save the developer's name and email to their account."""

        user = super().save(commit=False)

        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]

        if commit:
            user.save()

        return user


# ============================================================
# 2. LOGIN
# ============================================================


class LoginForm(forms.Form):
    """Authenticate using a username or email address."""

    identifier = forms.CharField(
        max_length=254,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
                "placeholder": "Username or email",
            }
        ),
    )

    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "placeholder": "Your password",
            }
        )
    )

    remember_me = forms.BooleanField(required=False)


# ============================================================
# 3. PASSWORD RECOVERY
# ============================================================


class RequestResetForm(forms.Form):
    """Collect the developer's email address for password recovery."""

    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "placeholder": "you@example.com",
            }
        ),
    )

    def clean_email(self):
        """Normalize the email without revealing account existence."""

        return self.cleaned_data["email"].strip().lower()


class VerifyPasswordResetOTPForm(forms.Form):
    """
    Collect a six-digit password-reset verification code.

    This form validates the format only.
    The verification service must check the actual OTP,
    expiration, attempt limits, and account ownership.
    """

    code = forms.CharField(
        min_length=6,
        max_length=6,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "placeholder": "Enter 6-digit code",
                "maxlength": "6",
            }
        ),
    )

    def clean_code(self):
        """Require exactly six ASCII digits."""

        code = self.cleaned_data["code"]

        if len(code) != 6 or not all(
            character in "0123456789"
            for character in code
        ):
            raise ValidationError(
                "Enter a valid 6-digit verification code."
            )

        return code


class CodeViewSetPasswordForm(SetPasswordForm):
    """
    Validate and save a new password.

    Django's SetPasswordForm checks:
    - Password confirmation.
    - Configured password validators.

    The view must ensure OTP verification succeeded
    before displaying or accepting this form.
    """

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)

        self.fields["new_password1"].widget.attrs.update(
            {
                "autocomplete": "new-password",
                "placeholder": "Create a new password",
            }
        )

        self.fields["new_password2"].widget.attrs.update(
            {
                "autocomplete": "new-password",
                "placeholder": "Confirm your new password",
            }
        )


# ============================================================
# 4. GOOGLE SIGNUP
# ============================================================


class CodeViewGoogleSignupForm(SignupForm):
    """
    Validate Google signup for ColabVerse.

    Requirements:
    - Google must provide a verified email.
    - The email must not belong to an existing account.
    - The developer must choose a unique username.
    """

    def clean_username(self):
        """Ensure the selected username is unique."""

        username = self.cleaned_data["username"].strip()

        if User.objects.filter(
            username__iexact=username
        ).exists():
            raise ValidationError(
                "This username is already taken. Choose another."
            )

        return username

    def clean(self):
        """Validate the verified Google email before registration."""

        cleaned_data = super().clean()

        # Google email addresses are supplied by Allauth.
        google_emails = self.sociallogin.email_addresses

        # Only accept email addresses verified by Google.
        verified_emails = [
            address.email.strip().lower()
            for address in google_emails
            if address.verified and address.email
        ]

        if not verified_emails:
            raise ValidationError(
                "Google did not provide a verified email address. "
                "Please try signing in with Google again."
            )

        # Use the verified Google email, not a manually entered address.
        google_email = verified_emails[0]

        # Prevent new Google registrations using an existing email.
        if User.objects.filter(
            email__iexact=google_email
        ).exists():
            raise ValidationError(
                "An account already exists with this email address. "
                "Please sign in using your existing ColabVerse account."
            )

        # Keep the signup email consistent with Google's verified email.
        cleaned_data["email"] = google_email

        return cleaned_data


# ============================================================
# 5. DEVELOPER PROFILE
# ============================================================


class DeveloperProfileForm(forms.ModelForm):
    """Validate public profile fields and optional image upload."""

    first_name = forms.CharField(
        max_length=150,
        required=False,
    )

    last_name = forms.CharField(
        max_length=150,
        required=False,
    )

    class Meta:
        model = DeveloperProfile

        fields = (
            "avatar",
            "first_name",
            "last_name",
            "title",
            "bio",
            "location",
            "skills",
            "github_url",
            "linkedin_url",
            "portfolio_url",
        )

        widgets = {
            "bio": forms.Textarea(
                attrs={"rows": 4}
            ),
            "avatar": forms.ClearableFileInput(
                attrs={
                    "accept": "image/jpeg,image/png,image/webp"
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields["first_name"].initial = (
                self.instance.user.first_name
            )

            self.fields["last_name"].initial = (
                self.instance.user.last_name
            )

    def clean_avatar(self):
        """Validate the uploaded profile picture."""

        avatar = self.cleaned_data.get("avatar")

        if avatar and hasattr(avatar, "size"):

            if avatar.size > 3 * 1024 * 1024:
                raise ValidationError(
                    "Choose an image smaller than 3 MB."
                )

            from PIL import Image, UnidentifiedImageError

            try:
                avatar.seek(0)

                with Image.open(avatar) as image:

                    if image.format not in (
                        "JPEG",
                        "PNG",
                        "WEBP",
                    ):
                        raise ValidationError(
                            "Use a JPG, PNG, or WebP image."
                        )

                    if (
                        image.width > 4096
                        or image.height > 4096
                    ):
                        raise ValidationError(
                            "Image dimensions must not exceed 4096 pixels."
                        )

                    image.verify()

                avatar.seek(0)

            except (
                UnidentifiedImageError,
                OSError,
                ValueError,
            ):
                raise ValidationError(
                    "This is not a valid image."
                )

        return avatar

    def save(self, commit=True):
        """Save profile information and the developer's full name."""

        profile = super().save(commit=False)

        if commit:
            profile.save()

            user = profile.user

            user.first_name = self.cleaned_data["first_name"]
            user.last_name = self.cleaned_data["last_name"]

            user.save(
                update_fields=[
                    "first_name",
                    "last_name",
                ]
            )

        return profile