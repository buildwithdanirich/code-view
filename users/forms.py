"""Validated signup, login, and password-reset forms for CodeView."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, SetPasswordForm
from django.core.exceptions import ValidationError

User = get_user_model()


class RegisterForm(UserCreationForm):
    email = forms.EmailField(max_length=254, widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@example.com"}))

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")
        widgets = {"username": forms.TextInput(attrs={"autocomplete": "username", "placeholder": "Choose a username"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update({"autocomplete": "new-password", "placeholder": "Create a password"})
        self.fields["password2"].widget.attrs.update({"autocomplete": "new-password", "placeholder": "Confirm your password"})

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("This email address is already registered.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    identifier = forms.CharField(max_length=254, widget=forms.TextInput(attrs={"autocomplete": "username", "placeholder": "Username or email"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "Your password"}))
    remember_me = forms.BooleanField(required=False)


class RequestResetForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@example.com"}))


class CodeViewSetPasswordForm(SetPasswordForm):
    pass


# ============================================================
# GOOGLE SIGNUP FORM
# ============================================================

from allauth.socialaccount.forms import SignupForm


class CodeViewGoogleSignupForm(SignupForm):
    """
    Require a unique CodeView username during Google signup.
    """

    def clean_username(self):
        """
        Check that the selected username is available.
        """

        username = self.cleaned_data["username"].strip()

        # Prevent usernames that differ only by capitalization.
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError(
                "This username is already taken. Choose another."
            )

        return username

class DeveloperProfileForm(forms.ModelForm):
    """Validate public profile fields and optional image upload."""
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)

    class Meta:
        from .models import DeveloperProfile
        model = DeveloperProfile
        fields = ("avatar", "first_name", "last_name", "title", "bio", "location", "skills", "github_url", "linkedin_url", "portfolio_url")
        widgets = {"bio": forms.Textarea(attrs={"rows": 4}), "avatar": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["first_name"].initial = self.instance.user.first_name
            self.fields["last_name"].initial = self.instance.user.last_name

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if avatar and hasattr(avatar, "size"):
            if avatar.size > 3 * 1024 * 1024:
                raise ValidationError("Choose an image smaller than 3 MB.")
            from PIL import Image, UnidentifiedImageError
            try:
                avatar.seek(0)
                with Image.open(avatar) as image:
                    if image.format not in ("JPEG", "PNG", "WEBP"):
                        raise ValidationError("Use a JPG, PNG, or WebP image.")
                    if image.width > 4096 or image.height > 4096:
                        raise ValidationError("Image dimensions must not exceed 4096 pixels.")
                    image.verify()
                avatar.seek(0)
            except (UnidentifiedImageError, OSError, ValueError):
                raise ValidationError("This is not a valid image.")
        return avatar

    def save(self, commit=True):
        profile = super().save(commit=False)
        if commit:
            profile.save()
            user = profile.user
            user.first_name = self.cleaned_data["first_name"]
            user.last_name = self.cleaned_data["last_name"]
            user.save(update_fields=["first_name", "last_name"])
        return profile
