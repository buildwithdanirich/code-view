from django.db import transaction
from django.db.models import F
from django.db.models.functions import Greatest
from .models import Reputation, Notification

@transaction.atomic
def adjust_reputation(user, delta):
    reputation, _ = Reputation.objects.get_or_create(user=user)
    Reputation.objects.filter(pk=reputation.pk).update(points=Greatest(F('points') + delta, 0))

def notify(recipient, actor, question, message):
    if recipient.pk != actor.pk:
        Notification.objects.create(recipient=recipient, actor=actor, question=question, message=message)
