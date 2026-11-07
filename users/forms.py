from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class RegisterForm(UserCreationForm):
    # Require users to provide an email address.
    email = forms.EmailField(required=True)

    class Meta:
        # Use Django's built-in User model.
        model = User

        # Fields required for registration.
        fields = ["username", "email", "password1", "password2"]

    def clean_email(self):
        # Remove spaces and convert email to lowercase.
        email = self.cleaned_data["email"].strip().lower()

        # Reject an email that already belongs to another user.
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "This email is already registered. Please log in."
            )

        return email