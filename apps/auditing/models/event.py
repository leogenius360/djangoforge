"""
Concrete audit Event model with actor attribution and outbox dispatch fields.

This is the only table written to the database for audit logging.
It combines the full event-sourcing record (from ``BaseEvent``) with:

* ``actor`` — FK to the authenticated user who triggered the event
* Outbox fields — track which optional backends (file, redis, kafka) have
  received a copy of this event
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models

from apps.auditing.models.base import BaseEvent


class Event(BaseEvent):
    """
    Concrete audit event record.

    Extends ``BaseEvent`` with actor attribution and outbox tracking fields.
    All fields inherited from ``BaseEvent`` are immutable after creation.
    The outbox fields (``backends_pending``, ``backends_dispatched``,
    ``backends_failed``) are mutable and updated by Celery dispatch tasks.
    """

    # ------------------------------------------------------------------
    # Actor attribution
    # ------------------------------------------------------------------
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )

    # ------------------------------------------------------------------
    # Transactional outbox fields
    #
    # backends_pending  — list of backend names that still need this event
    # backends_dispatched — {backend: ISO-timestamp} of successful dispatches
    # backends_failed   — {backend: {"error": "..", "attempts": N}}
    # ------------------------------------------------------------------
    backends_pending = models.JSONField(default=list, blank=True)
    backends_dispatched = models.JSONField(default=dict, blank=True)
    backends_failed = models.JSONField(default=dict, blank=True)

    # ------------------------------------------------------------------
    # Immutability overrides
    # ------------------------------------------------------------------
    IMMUTABLE_FIELDS = BaseEvent.IMMUTABLE_FIELDS | frozenset({"actor", "actor_id"})

    MUTABLE_FIELDS = BaseEvent.MUTABLE_FIELDS | frozenset(
        {"backends_pending", "backends_dispatched", "backends_failed"}
    )

    class Meta:
        db_table = "auditing_event"
        verbose_name = "Audit Event"
        verbose_name_plural = "Audit Events"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["actor", "created_at"], name="auditing_event_actor_cat_idx"),
        ]

    # ------------------------------------------------------------------
    # Integrity payload: include actor in the hash
    # ------------------------------------------------------------------

    def _integrity_payload(self) -> dict[str, Any]:
        payload = super()._integrity_payload()
        payload["actor_id"] = str(self.actor_id) if self.actor_id else None
        return payload

    # ------------------------------------------------------------------
    # Outbox convenience properties
    # ------------------------------------------------------------------

    @property
    def is_fully_dispatched(self) -> bool:
        """True when all configured backends have received this event."""
        return not self.backends_pending

    @property
    def has_dispatch_failures(self) -> bool:
        """True when at least one backend failed to receive this event."""
        return bool(self.backends_failed)

    # ------------------------------------------------------------------
    # Context helpers (from context dict)
    # ------------------------------------------------------------------

    @property
    def ip_address(self) -> str | None:
        """Client IP address from the request context dict."""
        return (self.context or {}).get("ip_address")

    @property
    def user_agent(self) -> str | None:
        """User-Agent from the request context dict."""
        return (self.context or {}).get("user_agent")

    @property
    def request_id(self) -> str | None:
        """Request / correlation ID from the context dict."""
        return (self.context or {}).get("request_id")
