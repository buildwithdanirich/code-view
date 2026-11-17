from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import F, Q


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="Follow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("follower", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="social_following_relations", to=settings.AUTH_USER_MODEL)),
                ("following", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="social_follower_relations", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(model_name="follow", constraint=models.UniqueConstraint(fields=("follower", "following"), name="cv_social_unique_follow")),
        migrations.AddConstraint(model_name="follow", constraint=models.CheckConstraint(condition=~Q(follower=F("following")), name="cv_social_no_self_follow")),
        migrations.AddIndex(model_name="follow", index=models.Index(fields=["following", "-created_at"], name="cv_social_followers_idx")),
    ]
