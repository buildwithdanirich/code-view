from django import forms
from .models import Question, Answer, Tag

class QuestionForm(forms.ModelForm):
    tag_names = forms.CharField(required=False, max_length=300, help_text="Separate tags with commas, e.g. python, django")

    class Meta:
        model = Question
        fields = ["title", "body", "code"]
        widgets = {"body": forms.Textarea(attrs={"rows": 8}), "code": forms.Textarea(attrs={"rows": 5})}

    def clean_title(self):
        value = self.cleaned_data["title"].strip()
        if len(value) < 10:
            raise forms.ValidationError("Please use at least 10 characters in your title.")
        return value

    def clean_body(self):
        value = self.cleaned_data["body"].strip()
        if len(value) < 20:
            raise forms.ValidationError("Please describe your problem in at least 20 characters.")
        return value

    def clean_tag_names(self):
        names = [name.strip().lower() for name in self.cleaned_data["tag_names"].split(",") if name.strip()]
        if len(names) > 5:
            raise forms.ValidationError("Use at most five tags.")
        if any(len(name) > 50 or not __import__('re').fullmatch(r"[a-z0-9][a-z0-9+.#-]*", name) for name in names):
            raise forms.ValidationError("Tags may contain lowercase letters, digits, +, ., # and -.")
        return list(dict.fromkeys(names))

    def save_tags(self, question):
        tags = []
        for name in self.cleaned_data["tag_names"]:
            tag, _ = Tag.objects.get_or_create(name=name, defaults={"slug": __import__('django.utils.text', fromlist=['slugify']).slugify(name)})
            tags.append(tag)
        question.tags.set(tags)

class AnswerForm(forms.ModelForm):
    class Meta:
        model = Answer
        fields = ["body", "code"]
        widgets = {"body": forms.Textarea(attrs={"rows": 6}), "code": forms.Textarea(attrs={"rows": 4})}

    def clean_body(self):
        value = self.cleaned_data["body"].strip()
        if len(value) < 10:
            raise forms.ValidationError("Please write at least 10 characters.")
        return value
