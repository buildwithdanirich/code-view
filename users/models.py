"""Public developer profile information, separate from authentication credentials."""
from django.conf import settings
from django.db import models


class DeveloperProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="developer_profile")
    avatar = models.ImageField(upload_to="profile_avatars/", blank=True)
    title = models.CharField(max_length=100, blank=True)
    bio = models.TextField(max_length=600, blank=True)
    location = models.CharField(max_length=100, blank=True)
    skills = models.CharField(max_length=300, blank=True, help_text="Comma-separated skills")
    github_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    portfolio_url = models.URLField(blank=True)

    def __str__(self):
        return f"{self.user.username}'s profile"
