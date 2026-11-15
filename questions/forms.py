from django import forms
from .models import Question, Comment

class QuestionForm(forms.ModelForm):
    tags_text = forms.CharField(required=False, max_length=250, help_text='Comma-separated tags (up to five)')
    class Meta:
        model = Question
        fields = ['title', 'body']
        widgets = {'body': forms.Textarea(attrs={'rows': 7, 'placeholder': 'Explain your problem and what you have tried…'})}
    def clean_tags_text(self):
        tags = [x.strip().lower() for x in self.cleaned_data['tags_text'].split(',') if x.strip()]
        tags = list(dict.fromkeys(tags))
        if len(tags) > 5 or any(len(x)>40 for x in tags):
            raise forms.ValidationError('Use up to five tags, each at most 40 characters.')
        return tags

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['body']
        widgets = {'body': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Write a helpful answer or comment…'})}
    def clean_body(self):
        body = self.cleaned_data['body'].strip()
        if len(body) < 2: raise forms.ValidationError('Please write a meaningful comment.')
        return body
