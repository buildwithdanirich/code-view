"""Forms for ColabVerse support tickets and content reports."""

from django import forms

from colabverse_admin.models import SupportTicket


# =========================================================
# SUPPORT TICKET FORM
# =========================================================

class TicketForm(forms.ModelForm):
    """Allow developers to contact the ColabVerse support team."""

    class Meta:
        model = SupportTicket

        fields = (
            "subject",
            "message",
        )

        widgets = {
            "message": forms.Textarea(
                attrs={"rows": 6}
            ),
        }

    def clean_subject(self):
        """Validate the support ticket subject."""

        value = self.cleaned_data["subject"].strip()

        if len(value) < 5:
            raise forms.ValidationError(
                "Enter a subject of at least 5 characters."
            )

        return value

    def clean_message(self):
        """Validate the support ticket message."""

        value = self.cleaned_data["message"].strip()

        if not 10 <= len(value) <= 10000:
            raise forms.ValidationError(
                "Enter between 10 and 10,000 characters."
            )

        return value


# =========================================================
# CONTENT REPORT FORM
# =========================================================

class ReportForm(forms.Form):
    """
    Collect the developer's reason for reporting content.

    The content type and object ID will be determined by
    the backend from the content the developer selected.
    """

    reason = forms.CharField(
        label="Why are you reporting this?",
        min_length=10,
        max_length=2000,
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "placeholder": (
                    "Explain why you believe this content "
                    "should be reviewed."
                ),
            }
        ),
        help_text=(
            "Provide enough information to help "
            "our moderation team review your report."
        ),
    )