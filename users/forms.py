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