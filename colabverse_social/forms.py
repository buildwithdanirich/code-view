from django import forms
from colabverse_admin.models import ContentReport, SupportTicket


class TicketForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = ("subject", "message")
        widgets = {"message": forms.Textarea(attrs={"rows": 6})}

    def clean_subject(self):
        value = self.cleaned_data["subject"].strip()
        if len(value) < 5:
            raise forms.ValidationError("Enter a subject of at least 5 characters.")
        return value

    def clean_message(self):
        value = self.cleaned_data["message"].strip()
        if not 10 <= len(value) <= 10000:
            raise forms.ValidationError("Enter between 10 and 10,000 characters.")
        return value


class ReportForm(forms.Form):
    kind = forms.ChoiceField(choices=ContentReport.KIND_CHOICES)
    object_id = forms.IntegerField(min_value=1)
    reason = forms.CharField(min_length=10, max_length=2000, widget=forms.Textarea(attrs={"rows": 5}))
