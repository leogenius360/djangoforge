"""Session credentials.

Stores hashed secrets (never raw tokens) associated with an AuthSession.

This enables:
- cookie-style session handles
- refresh tokens (with optional rotation families)

Raw token material must never be persisted.
"""

from __future__ import annotations

import uuid

from django.db import models

from apps.core.models import SoftDeleteModel
from apps.core.models.mixins import BaseActorMixin

from ..enums import SessionCredentialKind


class SessionCredential(SoftDeleteModel, BaseActorMixin):
    """Hashed credential associated with a session."""

    session = models.ForeignKey(
        "user_sessions.AuthSession",
        on_delete=models.CASCADE,
        related_name="credentials",
        db_index=True,
    )

    deleted_by = models.ForeignKey(
        "accounts.Principal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deleted_%(class)ss",
    )

    kind = models.CharField(max_length=30, choices=SessionCredentialKind.choices, db_index=True)

    # HMAC-SHA256 hex digest (64 chars)
    handle_hash = models.CharField(max_length=64, db_index=True)

    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # Refresh token rotation family
    family_id = models.UUIDField(null=True, blank=True, db_index=True, default=None)
    parent_id = models.UUIDField(null=True, blank=True, db_index=True, default=None)

    is_revoked = models.BooleanField(default=False, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "session_credentials"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session", "kind"]),
            models.Index(fields=["kind", "handle_hash"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["deleted_at"]),
        ]

    def __str__(self) -> str:
        return f"SessionCredential<{self.pk}> {self.kind} session={self.session_id}"

    @classmethod
    def new_parent_id(cls) -> uuid.UUID:
        """Generate a new parent_id value for rotation lineage."""
        return uuid.uuid4()
