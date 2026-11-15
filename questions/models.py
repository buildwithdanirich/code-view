from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.text import slugify

User = settings.AUTH_USER_MODEL

class Tag(models.Model):
    name = models.CharField(max_length=40, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    def __str__(self): return self.name

class Question(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cv_questions')
    title = models.CharField(max_length=220)
    body = models.TextField()
    tags = models.ManyToManyField(Tag, blank=True, related_name='questions')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self): return self.title

class Comment(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cv_comments')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True, related_name='replies')
    body = models.TextField()
    is_accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['question'], condition=Q(is_accepted=True), name='one_accepted_comment_per_question')]
    def __str__(self): return self.body[:80]

class QuestionLike(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user','question'], name='unique_question_like')]

class CommentLike(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user','comment'], name='unique_comment_like')]

class Reputation(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cv_reputation')
    points = models.PositiveIntegerField(default=0)
    @property
    def stars(self):
        if self.points >= 1500: return 5
        if self.points >= 700: return 4
        if self.points >= 300: return 3
        if self.points >= 100: return 2
        return 1
    def __str__(self): return f'{self.user}: {self.points} points'

class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cv_question_notifications')
    actor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cv_question_actions')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    message = models.CharField(max_length=180)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']
