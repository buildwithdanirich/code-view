from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.utils.text import slugify

class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=60, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        if not self.slug:
            raise ValidationError("Tag name must contain letters or numbers.")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Question(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="qa_questions")
    title = models.CharField(max_length=200)
    body = models.TextField()
    code = models.TextField(blank=True)
    tags = models.ManyToManyField(Tag, related_name="questions", blank=True)
    accepted_answer = models.OneToOneField("Answer", on_delete=models.SET_NULL, null=True, blank=True, related_name="accepted_for")
    view_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def score(self):
        return self.votes.aggregate(total=Sum("value"))["total"] or 0

    @property
    def is_solved(self):
        return self.accepted_answer_id is not None

    def clean(self):
        if self.accepted_answer_id and (not self.pk or self.accepted_answer.question_id != self.pk):
            raise ValidationError({"accepted_answer": "The accepted answer must belong to this question."})

class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="qa_answers")
    body = models.TextField()
    code = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Answer {self.pk} on question {self.question_id}"

    @property
    def score(self):
        return self.votes.aggregate(total=Sum("value"))["total"] or 0

class QuestionVote(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="qa_question_votes")
    value = models.SmallIntegerField(choices=((1, "Upvote"), (-1, "Downvote")))

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["question", "user"], name="qa_unique_question_vote"),
            models.CheckConstraint(condition=Q(value__in=[-1, 1]), name="qa_valid_question_vote"),
        ]

class AnswerVote(models.Model):
    answer = models.ForeignKey(Answer, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="qa_answer_votes")
    value = models.SmallIntegerField(choices=((1, "Upvote"), (-1, "Downvote")))

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["answer", "user"], name="qa_unique_answer_vote"),
            models.CheckConstraint(condition=Q(value__in=[-1, 1]), name="qa_valid_answer_vote"),
        ]
