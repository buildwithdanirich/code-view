from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="DeveloperProfile", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("avatar", models.ImageField(blank=True, upload_to="profile_avatars/")),
        ("title", models.CharField(blank=True, max_length=100)),
        ("bio", models.TextField(blank=True, max_length=600)),
        ("location", models.CharField(blank=True, max_length=100)),
        ("skills", models.CharField(blank=True, help_text="Comma-separated skills", max_length=300)),
        ("github_url", models.URLField(blank=True)),
        ("linkedin_url", models.URLField(blank=True)),
        ("portfolio_url", models.URLField(blank=True)),
        ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="developer_profile", to=settings.AUTH_USER_MODEL)),
    ])]
