from django.conf import settings
from django.db import models


class ContentReport(models.Model):
    KIND_CHOICES = [('question', 'Question'), ('comment', 'Answer / comment'), ('group', 'Group')]
    STATUS_CHOICES = [('open', 'Open'), ('reviewing', 'Reviewing'), ('resolved', 'Resolved'), ('dismissed', 'Dismissed')]
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    object_id = models.PositiveBigIntegerField()
    reason = models.TextField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='open', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)


class SupportTicket(models.Model):
    STATUS_CHOICES = [('open', 'Open'), ('in_progress', 'In progress'), ('resolved', 'Resolved')]
    PRIORITY_CHOICES = [('low', 'Low'), ('normal', 'Normal'), ('high', 'High')]
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.CharField(max_length=180)
    message = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='open', db_index=True)
    admin_reply = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class AdminAuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100)
    target = models.CharField(max_length=180)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
