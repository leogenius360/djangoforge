"""
Initial migration — creates the OutboxEvent table.
"""

import uuid

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="OutboxEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("event_type", models.CharField(db_index=True, max_length=255)),
                ("event_id", models.CharField(help_text="Stable idempotency key.", max_length=64, unique=True)),
                ("source", models.CharField(blank=True, default="", max_length=255)),
                ("version", models.CharField(default="v1", max_length=32)),
                ("correlation_id", models.CharField(blank=True, default="", max_length=64)),
                ("tenant", models.CharField(blank=True, default="", max_length=128)),
                ("aggregate_id", models.CharField(blank=True, default="", max_length=128)),
                ("aggregate_type", models.CharField(blank=True, default="", max_length=128)),
                ("payload", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("published_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True, default="")),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="outboxevent",
            index=models.Index(fields=["published_at", "created_at"], name="outbox_pending_idx"),
        ),
    ]
