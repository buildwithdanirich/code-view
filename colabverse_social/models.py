from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Follow(models.Model):
    """Directional relationship: follower follows following."""

    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="social_following_relations",
    )
    following = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="social_follower_relations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["follower", "following"], name="cv_social_unique_follow"),
            models.CheckConstraint(condition=~Q(follower=F("following")), name="cv_social_no_self_follow"),
        ]
        indexes = [models.Index(fields=["following", "-created_at"], name="cv_social_followers_idx")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.follower_id} follows {self.following_id}"
