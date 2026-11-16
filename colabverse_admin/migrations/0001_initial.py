from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name='ContentReport', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('kind', models.CharField(choices=[('question', 'Question'), ('comment', 'Answer / comment'), ('group', 'Group')], max_length=20)),
            ('object_id', models.PositiveBigIntegerField()),
            ('reason', models.TextField()),
            ('status', models.CharField(choices=[('open', 'Open'), ('reviewing', 'Reviewing'), ('resolved', 'Resolved'), ('dismissed', 'Dismissed')], db_index=True, default='open', max_length=16)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('reviewed_at', models.DateTimeField(blank=True, null=True)),
            ('reporter', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name='SupportTicket', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('subject', models.CharField(max_length=180)),
            ('message', models.TextField()),
            ('priority', models.CharField(choices=[('low', 'Low'), ('normal', 'Normal'), ('high', 'High')], default='normal', max_length=10)),
            ('status', models.CharField(choices=[('open', 'Open'), ('in_progress', 'In progress'), ('resolved', 'Resolved')], db_index=True, default='open', max_length=16)),
            ('admin_reply', models.TextField(blank=True)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('requester', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name='AdminAuditLog', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('action', models.CharField(max_length=100)),
            ('target', models.CharField(max_length=180)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
        ], options={'ordering': ['-created_at']}),
    ]
