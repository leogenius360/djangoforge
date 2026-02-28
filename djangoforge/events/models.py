"""
OutboxEvent Django model.

Events are written to the outbox table in the *same* database transaction as the
domain state change, guaranteeing at-least-once delivery.
"""

from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class OutboxEventManager(models.Manager):
    """Custom manager with helpers for the publish worker."""

    def pending(self, batch_size: int = 50) -> models.QuerySet:
        return self.filter(published_at__isnull=True).order_by("created_at")[:batch_size]


class OutboxEvent(models.Model):
    """Transactional outbox row."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=255, db_index=True)
    event_id = models.CharField(max_length=64, unique=True, help_text="Stable idempotency key.")
    source = models.CharField(max_length=255, blank=True, default="")
    version = models.CharField(max_length=32, default="v1")
    correlation_id = models.CharField(max_length=64, blank=True, default="")
    tenant = models.CharField(max_length=128, blank=True, default="")
    aggregate_id = models.CharField(max_length=128, blank=True, default="")
    aggregate_type = models.CharField(max_length=128, blank=True, default="")
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")

    objects = OutboxEventManager()

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["published_at", "created_at"], name="outbox_pending_idx"),
        ]

    def __str__(self) -> str:
        status = "published" if self.published_at else "pending"
        return f"{self.event_type} [{status}] ({self.event_id})"

    def mark_published(self) -> None:
        self.published_at = timezone.now()
        self.save(update_fields=["published_at"])
