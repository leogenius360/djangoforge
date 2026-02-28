"""
Password history model for reuse prevention.

Stores hashed passwords to enforce password-reuse policies.  Old entries
beyond ``PASSWORD_HISTORY_COUNT`` are pruned by ``PasswordService``.
Records are immutable (``BaseModel``, no soft delete).
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.db import models

from apps.core.models import BaseModel

from .enums import PasswordSetMethod


class PasswordHistoryQuerySet(models.QuerySet):
    """QuerySet for password history analysis."""

    def for_principal(self, principal: object) -> PasswordHistoryQuerySet:
        return self.filter(principal=principal)

    def recent(self, count: int) -> PasswordHistoryQuerySet:
        """Most recent *count* entries for ordering by created_at desc."""
        return self.order_by("-created_at")[:count]


class PasswordHistoryManager(models.Manager.from_queryset(PasswordHistoryQuerySet)):
    """Manager for ``PasswordHistory``."""

    def check_reuse(self, principal: object, raw_password: str, count: int = 5) -> bool:
        """Return True if *raw_password* matches any of the last *count* entries.

        Uses Django's ``check_password`` (constant-time per entry).
        """
        recent_entries = self.for_principal(principal).order_by("-created_at")[:count]
        return any(check_password(raw_password, entry.password_hash) for entry in recent_entries)

    def record(
        self,
        *,
        principal: object,
        password_hash: str,
        set_by: str = PasswordSetMethod.USER_CHANGE,
    ) -> PasswordHistory:
        """Record a new password in history."""
        return self.create(principal=principal, password_hash=password_hash, set_by=set_by)

    def prune(self, principal: object, keep: int = 5) -> int:
        """Delete entries beyond the most recent *keep* for the principal."""
        ids_to_keep = list(self.for_principal(principal).order_by("-created_at").values_list("pk", flat=True)[:keep])
        deleted_count, _ = self.for_principal(principal).exclude(pk__in=ids_to_keep).delete()
        return deleted_count


class PasswordHistory(BaseModel):
    """Historical password hash for reuse prevention.

    Uses ``BaseModel`` (UUID PK, timestamps, version) -- NOT soft-deletable
    because password history is a permanent audit record.
    """

    principal = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_history",
    )
    password_hash = models.CharField(max_length=128)
    set_by = models.CharField(
        max_length=20,
        choices=PasswordSetMethod.choices,
        default=PasswordSetMethod.USER_CHANGE,
    )

    objects = PasswordHistoryManager()

    class Meta:
        db_table = "password_history"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["principal", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Password history for {self.principal} at {self.created_at}"
